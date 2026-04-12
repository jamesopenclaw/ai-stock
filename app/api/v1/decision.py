"""
决策分析 API - 卖点与完整决策
"""
import asyncio
import copy
import time
import re
from fastapi import APIRouter, Query, Body, Depends
from typing import Optional
from datetime import datetime
import logging
from collections import OrderedDict

from app.models.schemas import (
    AccountInput,
    AccountPosition,
    SellPointResponse,
    SellPointOutput,
    SellSignalTag,
    FullDecisionResponse,
    DecisionSummary,
    LlmCallStatus,
    ApiResponse
)
from app.services.sell_point import sell_point_service
from app.services.account_adapter import account_adapter_service
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service, merge_holdings_into_candidate_stocks, StockFilterService
from app.services.buy_point import buy_point_service
from app.services.buy_point_sop import buy_point_sop_service
from app.services.sell_point_sop import sell_point_sop_service
from app.data.tushare_client import normalize_ts_code, tushare_client
from app.models.schemas import StockInput
from app.services.decision_context import decision_context_service, DecisionContextService
from app.services.decision_flow import decision_flow_service
from app.services.review_snapshot import review_snapshot_service
from app.services.llm_explainer import llm_explainer_service
from app.core.security import AuthenticatedAccount, get_current_account
from app.services.sector_scan_snapshot import resolve_snapshot_lookup_trade_date, sector_scan_snapshot_service
from app.services.strategy_config import build_stock_filter_strategy

router = APIRouter()
logger = logging.getLogger(__name__)
STOCK_POOLS_SNAPSHOT_VERSION = 7
SELL_POINT_CACHE_TTL_SECONDS = 20
_sell_point_page_cache: dict[str, dict] = {}


def _resolve_account_id(current_account: Optional[AuthenticatedAccount]) -> Optional[str]:
    """兼容 FastAPI 依赖注入与直接函数调用。"""
    account_id = getattr(current_account, "id", None)
    if isinstance(account_id, str) and account_id:
        return account_id
    return None


def _normalize_strategy_style(style: Optional[str]) -> str:
    normalized = str(style or "balanced").strip().lower()
    if normalized not in {"balanced", "left", "right"}:
        return "balanced"
    return normalized


def _is_default_strategy_style(style: Optional[str]) -> bool:
    return _normalize_strategy_style(style) == "balanced"


def _resolve_strategy_services(strategy_style: Optional[str]):
    normalized_style = _normalize_strategy_style(strategy_style)
    if normalized_style == "balanced":
        return decision_context_service, stock_filter_service

    strategy = build_stock_filter_strategy(normalized_style)
    return DecisionContextService(strategy=strategy), StockFilterService(strategy=strategy)


def _sell_point_cache_key(
    trade_date: str,
    account_id: Optional[str],
    include_llm: bool,
    include_add_signals: bool,
) -> str:
    return f"{trade_date}:{account_id or ''}:{int(include_llm)}:{int(include_add_signals)}"


def _get_cached_sell_point_payload(cache_key: str) -> Optional[dict]:
    cached = _sell_point_page_cache.get(cache_key)
    if not cached:
        return None
    if time.monotonic() - float(cached.get("fetched_at") or 0) > SELL_POINT_CACHE_TTL_SECONDS:
        _sell_point_page_cache.pop(cache_key, None)
        return None
    return copy.deepcopy(cached.get("data"))


def _cache_sell_point_payload(cache_key: str, payload: dict) -> None:
    _sell_point_page_cache[cache_key] = {
        "fetched_at": time.monotonic(),
        "data": copy.deepcopy(payload),
    }


async def _enrich_buy_point_pool_execution_references(
    stock_pools,
    trade_date: str,
    *,
    account_id: Optional[str] = None,
) -> None:
    if stock_pools is None:
        return

    deduped_stocks = OrderedDict()
    for stock in list(getattr(stock_pools, "account_executable_pool", []) or []) + list(
        getattr(stock_pools, "market_watch_pool", []) or []
    ):
        code = normalize_ts_code(getattr(stock, "ts_code", "") or "")
        if (
            code
            and code not in deduped_stocks
            and getattr(stock, "execution_reference_price", None) is None
        ):
            deduped_stocks[code] = stock

    if not deduped_stocks:
        return

    await buy_point_sop_service.enrich_execution_proximity(
        list(deduped_stocks.values()),
        trade_date,
        account_id=account_id,
    )


def _resolve_add_signal_from_buy_sop(point: SellPointOutput, buy_sop_result) -> tuple[Optional[str], Optional[str]]:
    """基于买点 SOP 结果为持有观察票补充加仓提示。"""
    pnl_pct = getattr(point, "pnl_pct", None)
    if pnl_pct is None or pnl_pct < 0:
        return None, None

    account_context = getattr(buy_sop_result, "account_context", None)
    if getattr(account_context, "current_use", "") != "加仓":
        return None, None

    add_position_decision = getattr(buy_sop_result, "add_position_decision", None)
    if add_position_decision:
        decision = getattr(add_position_decision, "decision", "")
        reason = getattr(add_position_decision, "reason", "") or None
        if decision == "可加":
            return "建议加仓", reason
        if decision == "仅可小加":
            return "仅可小加", reason
        if decision == "不加":
            return None, None

    basic_info = getattr(buy_sop_result, "basic_info", None)
    position_advice = getattr(buy_sop_result, "position_advice", None)
    execution = getattr(buy_sop_result, "execution", None)

    buy_signal_tag = getattr(basic_info, "buy_signal_tag", "")
    suggestion = getattr(position_advice, "suggestion", "")
    execution_action = getattr(execution, "action", "")

    if buy_signal_tag == "不买" or suggestion == "不出手" or execution_action == "放弃":
        return None, None

    if pnl_pct >= 1 and execution_action == "买":
        return "建议加仓", getattr(execution, "reason", "") or getattr(position_advice, "reason", "")

    if pnl_pct >= 0 and buy_signal_tag in {"可买", "观察"}:
        if execution_action == "等":
            return "可关注加仓", getattr(execution, "reason", "") or getattr(position_advice, "reason", "")
        if execution_action == "买":
            return "可关注加仓", "结构已有加仓信号，但当前利润垫还不够厚，先关注，不急着扩大仓位。"

    return None, None


def _rewrite_hold_trigger_for_current_price(point: SellPointOutput, hold_condition: str) -> str:
    """卖点页持有观察卡片按当前价翻译观察条件，避免“已经站上方却还写重新站回”."""
    text = str(hold_condition or "").strip()
    if not text:
        return text

    market_price = getattr(point, "market_price", None)
    if market_price is None:
        return text

    match = re.search(r"重新站回\s*(\d+(?:\.\d+)?)\s*上方", text)
    if not match:
        return text

    observe_level = float(match.group(1))
    if float(market_price) < observe_level:
        return text

    return re.sub(
        r"只有重新站回\s*(\d+(?:\.\d+)?)\s*上方并稳住，才值得继续看。",
        rf"当前已经站在 \1 上方，接下来重点看能否继续稳在 \1 上方。",
        text,
    )


def _resolve_sell_trigger_for_display(order_plan, fallback: str) -> str:
    """卖点页对清仓票优先展示先处理区，最后失效线只做兜底。"""
    for field in ("priority_exit_condition", "rebound_condition", "stop_condition"):
        text = str(getattr(order_plan, field, "") or "").strip()
        if not text:
            continue
        if field == "priority_exit_condition" and "不是优先现价退出阶段" in text:
            continue
        if field == "rebound_condition" and "当前不以弱反抽退出为主" in text:
            continue
        return text
    return fallback


async def _align_sell_point_display_with_sop(
    trade_date: str,
    account_id: Optional[str],
    result: SellPointResponse,
) -> SellPointResponse:
    """卖点页展示动作以 SOP 最终执行为准，避免列表页与 SOP 抽屉冲突。"""
    ordered_points = [
        *list(result.sell_positions),
        *list(result.reduce_positions),
        *list(result.hold_positions),
    ]
    if not ordered_points:
        return result

    try:
        sop_map = await sell_point_sop_service.analyze_many(
            [point.ts_code for point in ordered_points],
            trade_date,
            account_id=account_id,
        )
    except Exception as exc:
        logger.warning("sell-point sop batch align failed error=%s", exc)
        sop_map = {}

    async def enrich_point(point: SellPointOutput) -> SellPointOutput:
        sop = sop_map.get(normalize_ts_code(point.ts_code))
        if sop is None:
            return point

        execution = getattr(sop, "execution", None)
        order_plan = getattr(sop, "order_plan", None)
        intraday = getattr(sop, "intraday_judgement", None)
        action = str(getattr(execution, "action", "") or "")
        if action == "清":
            point.sell_signal_tag = SellSignalTag.SELL
            point.sell_reason = getattr(execution, "reason", "") or point.sell_reason
            point.sell_trigger_cond = _resolve_sell_trigger_for_display(order_plan, point.sell_trigger_cond)
            point.sell_comment = getattr(intraday, "note", "") or point.sell_comment
        elif action == "减":
            point.sell_signal_tag = SellSignalTag.REDUCE
            point.sell_reason = getattr(execution, "reason", "") or point.sell_reason
            point.sell_trigger_cond = (
                getattr(order_plan, "take_profit_condition", "")
                or getattr(order_plan, "rebound_condition", "")
                or point.sell_trigger_cond
            )
            point.sell_comment = getattr(intraday, "note", "") or point.sell_comment
        elif action == "拿":
            point.sell_signal_tag = SellSignalTag.HOLD
            point.sell_reason = getattr(execution, "reason", "") or point.sell_reason
            point.sell_trigger_cond = _rewrite_hold_trigger_for_current_price(
                point,
                getattr(order_plan, "hold_condition", "") or point.sell_trigger_cond,
            )
            point.sell_comment = getattr(intraday, "note", "") or point.sell_comment
        return point

    updated_points = await asyncio.gather(*(enrich_point(point) for point in ordered_points))

    result.sell_positions = [point for point in updated_points if point.sell_signal_tag == SellSignalTag.SELL]
    result.reduce_positions = [point for point in updated_points if point.sell_signal_tag == SellSignalTag.REDUCE]
    result.hold_positions = [
        point
        for point in updated_points
        if point.sell_signal_tag not in {SellSignalTag.SELL, SellSignalTag.REDUCE}
    ]
    return result


async def _enrich_hold_positions_with_add_signals(
    trade_date: str,
    hold_positions: list[SellPointOutput],
    account_id: Optional[str],
) -> dict[str, object]:
    """为持有观察票补充加仓提示。"""
    if not hold_positions:
        return {}

    tasks = [
        buy_point_sop_service.analyze(point.ts_code, trade_date, account_id=account_id)
        for point in hold_positions
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    result_map: dict[str, object] = {}

    for point, result in zip(hold_positions, results):
        if isinstance(result, Exception):
            logger.warning(
                "sell-point add-signal enrich failed ts_code=%s error=%s",
                point.ts_code,
                result,
            )
            continue

        result_map[point.ts_code] = result
        add_signal_tag, add_signal_reason = _resolve_add_signal_from_buy_sop(point, result)
        point.add_signal_tag = add_signal_tag
        point.add_signal_reason = add_signal_reason
    return result_map


def _build_add_position_snapshot_inputs(
    hold_positions: list[SellPointOutput],
    buy_sop_results: dict[str, object],
) -> list[dict]:
    """从卖点持有观察和买点 SOP 结果中提取加仓快照样本。"""
    rows: list[dict] = []
    for point in hold_positions:
        buy_sop_result = buy_sop_results.get(point.ts_code)
        if not buy_sop_result:
            continue

        account_context = getattr(buy_sop_result, "account_context", None)
        if getattr(account_context, "current_use", "") != "加仓":
            continue

        add_position_decision = getattr(buy_sop_result, "add_position_decision", None)
        decision = getattr(add_position_decision, "decision", "")
        if decision not in {"可加", "仅可小加"}:
            continue

        basic_info = getattr(buy_sop_result, "basic_info", None)
        rows.append(
            {
                "ts_code": point.ts_code,
                "stock_name": point.stock_name,
                "candidate_source_tag": getattr(basic_info, "candidate_source_tag", "") or "",
                "candidate_bucket_tag": getattr(basic_info, "candidate_bucket_tag", "") or "",
                "buy_signal_tag": getattr(basic_info, "buy_signal_tag", "") or "",
                "buy_point_type": getattr(basic_info, "buy_point_type", "") or "",
                "stock_score": getattr(add_position_decision, "score_total", 0) or 0,
                "base_price": point.market_price or 0.0,
                "trade_mode": "加仓",
                "add_position_decision": decision,
                "add_position_score_total": getattr(add_position_decision, "score_total", 0) or 0,
                "add_position_scene": getattr(add_position_decision, "trigger_scene", "") or "",
            }
        )
    return rows


async def get_holdings_from_db(
    trade_date: Optional[str] = None,
    account_id: Optional[str] = None,
) -> list:
    """兼容旧调用，委托给共享上下文服务。"""
    return await decision_context_service.get_holdings_from_db(account_id, trade_date)


def refresh_holdings_price(holdings: list, trade_date: Optional[str] = None):
    """刷新持仓现价（内存中）"""
    from app.data.tushare_client import tushare_client
    compact_date = (trade_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    for h in holdings:
        try:
            detail = tushare_client.get_stock_detail(h["ts_code"], compact_date)
            if detail and detail.get("close"):
                h["market_price"] = detail.get("close")
                if h.get("cost_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                if h.get("holding_qty"):
                    h["holding_market_value"] = h["holding_qty"] * h["market_price"]
        except:
            pass


async def build_account_input_from_holdings(
    holdings: list,
    trade_date: Optional[str] = None,
    account_id: Optional[str] = None,
) -> AccountInput:
    """兼容旧调用，委托给共享上下文服务。"""
    return await decision_context_service.build_account_input_from_holdings(holdings, account_id, trade_date)


def build_risk_alerts(market_env, account: AccountInput, buy_analysis, holdings) -> list:
    """构建 PRD 9.2 风控提醒。"""
    alerts = []
    if market_env.market_env_tag.value == "防守" and account.today_new_buy_count >= 2:
        alerts.append("市场防守期仍频繁开仓，建议降频")
    if (
        buy_analysis is not None
        and market_env.market_env_tag.value == "防守"
        and len(buy_analysis.available_buy_points) > 0
    ):
        alerts.append("弱市仍出现可买信号，请提高买点门槛")
    if account.today_new_buy_count >= 3:
        alerts.append("当日开仓次数偏高，注意节奏风险")
    if any(h.pnl_pct < -3 for h in holdings) and account.total_position_ratio >= 0.5:
        alerts.append("弱票未充分处理前不宜继续加新仓")
    return alerts


def _stock_pools_snapshot_valid(stock_pools, expected_sector_scan_trade_date: str) -> bool:
    return bool(
        stock_pools
        and stock_pools.snapshot_version == STOCK_POOLS_SNAPSHOT_VERSION
        and stock_pools.sector_scan_trade_date
        and stock_pools.sector_scan_trade_date == expected_sector_scan_trade_date
    )


def _collect_buy_point_source_stocks(stock_pools) -> list:
    """买点页只分析非持仓处理池，优先复用三池页已有评分结果。"""
    deduped = OrderedDict()
    for group in (
        stock_pools.account_executable_pool,
        stock_pools.market_watch_pool,
    ):
        for stock in group:
            deduped.setdefault(stock.ts_code, stock)
    return list(deduped.values())


async def _compute_buy_point_bundle(
    trade_date: str,
    candidate_limit: int,
    *,
    account_id: Optional[str] = None,
    strategy_style: str = "balanced",
):
    context_service, filter_service = _resolve_strategy_services(strategy_style)
    context = await context_service.build_context(
        trade_date,
        top_gainers=candidate_limit,
        include_holdings=False,
        account_id=account_id,
    )
    review_bias_profile = await review_snapshot_service.get_review_bias_profile_safe(
        limit_days=10,
        account_id=account_id,
    )
    scored_stocks = filter_service.filter_with_context(
        trade_date,
        context.stocks,
        market_env=context.market_env,
        sector_scan=context.sector_scan,
        account=context.account,
        holdings=context.holdings_list,
    )
    stock_pools = filter_service.classify_pools(
        trade_date,
        context.stocks,
        context.holdings_list,
        context.account,
        market_env=context.market_env,
        sector_scan=context.sector_scan,
        scored_stocks=scored_stocks,
        review_bias_profile=review_bias_profile,
    )
    return {
        "context": context,
        "scored_stocks": scored_stocks,
        "stock_pools": stock_pools,
        "review_bias_profile": review_bias_profile,
    }


@router.get("/sell-point", response_model=ApiResponse)
async def analyze_sell_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    refresh: bool = Query(False, description="是否跳过卖点页短缓存"),
    force_llm_refresh: bool = Query(False, description="是否强制刷新 LLM 解读缓存"),
    include_llm: bool = Query(True, description="是否包含 LLM 卖点解读"),
    include_add_signals: bool = Query(True, description="是否为持有观察票补充加仓提示"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    卖点分析

    分析当前持仓，输出：
    - hold_positions: 持有观察
    - reduce_positions: 建议减仓
    - sell_positions: 建议卖出
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    include_llm = include_llm if isinstance(include_llm, bool) else True
    include_add_signals = include_add_signals if isinstance(include_add_signals, bool) else True

    try:
        account_id = _resolve_account_id(current_account)
        should_use_cache = not refresh and not force_llm_refresh and not include_llm
        cache_key = _sell_point_cache_key(trade_date, account_id, include_llm, include_add_signals)
        if should_use_cache:
            cached_payload = _get_cached_sell_point_payload(cache_key)
            if cached_payload is not None:
                return ApiResponse(data=cached_payload)

        selection_trade_date = await resolve_snapshot_lookup_trade_date(trade_date)
        holdings_list = await decision_context_service.get_holdings_from_db(account_id, trade_date)
        holdings = [AccountPosition(**holding) for holding in holdings_list]
        market_env = market_env_service.get_current_env(selection_trade_date)
        sector_scan = await sector_scan_snapshot_service.get_snapshot(selection_trade_date)
        if not sector_scan:
            sector_scan = sector_scan_service.scan(
                selection_trade_date,
                limit_output=False,
                market_env=market_env,
            )

        # 卖点分析
        result = sell_point_service.analyze(
            trade_date,
            holdings,
            market_env=market_env,
            sector_scan=sector_scan,
        )
        result = await _align_sell_point_display_with_sop(
            trade_date,
            account_id,
            result,
        )
        if include_add_signals:
            buy_sop_results = await _enrich_hold_positions_with_add_signals(
                trade_date,
                result.hold_positions,
                account_id,
            )
            snapshot_kwargs = {"account_id": account_id} if account_id else {}
            await review_snapshot_service.save_analysis_snapshot_safe(
                trade_date,
                add_position_analysis=_build_add_position_snapshot_inputs(result.hold_positions, buy_sop_results),
                **snapshot_kwargs,
            )
        llm_summary = None
        llm_status = LlmCallStatus(
            enabled=False,
            success=False,
            status="skipped",
            message="已跳过 LLM 卖点解读",
        )
        if include_llm:
            llm_kwargs = {"account_id": account_id} if account_id else {}
            llm_summary, llm_status = await llm_explainer_service.rewrite_sell_points_with_status(
                result,
                market_env,
                force_refresh=force_llm_refresh,
                **llm_kwargs,
            )

        payload = {
            "trade_date": result.trade_date,
            "market_env_tag": market_env.market_env_tag.value,
            "market_env_profile": getattr(market_env, "market_env_profile", "") or market_env.market_env_tag.value,
            "market_headline": getattr(market_env, "market_headline", "") or "",
            "market_subheadline": getattr(market_env, "market_subheadline", "") or "",
            "trading_tempo_label": getattr(market_env, "trading_tempo_label", "") or "",
            "hold_positions": [p.model_dump() for p in result.hold_positions],
            "reduce_positions": [p.model_dump() for p in result.reduce_positions],
            "sell_positions": [p.model_dump() for p in result.sell_positions],
            "total_count": result.total_count,
            "llm_summary": llm_summary.model_dump() if llm_summary else None,
            "llm_status": llm_status.model_dump(),
        }
        if should_use_cache:
            _cache_sell_point_payload(cache_key, payload)
        return ApiResponse(data=payload)
    except Exception as e:
        return ApiResponse(code=500, message=f"卖点分析失败: {str(e)}")


@router.get("/summary", response_model=ApiResponse)
async def get_decision_summary(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    获取执行摘要

    返回今日操作建议：
    - today_action: 今天该不该出手
    - focus: 优先看谁
    - avoid: 哪些绝对不碰
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account)
        account_context = await decision_context_service.build_account_context(
            trade_date,
            account_id=account_id,
        )
        market_env = market_env_service.get_current_env(trade_date)
        account_output = account_adapter_service.adapt(
            trade_date,
            account_context.account,
            account_context.holdings,
            market_env=market_env,
        )
        risk_alerts = build_risk_alerts(
            market_env,
            account_context.account,
            None,
            account_context.holdings,
        )

        # 生成摘要
        summary = _generate_summary(
            trade_date,
            market_env,
            account_output,
            account_context.holdings,
        )

        return ApiResponse(
            data={**summary.model_dump(), "risk_alerts": risk_alerts}
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取执行摘要失败: {str(e)}")


@router.get("/buy-point", response_model=ApiResponse)
async def analyze_buy_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(20, description="返回数量限制", ge=1, le=100),
    refresh: bool = Query(False, description="是否跳过三池快照缓存"),
    strategy_style: str = Query("balanced", description="候选风格：balanced 均衡，left 偏左侧，right 偏右侧"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    买点分析

    返回当日可买/观察/不买的候选个股列表
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account)
        candidate_limit = max(100, min(limit, 200))
        refresh_requested = refresh if isinstance(refresh, bool) else False
        normalized_strategy_style = _normalize_strategy_style(strategy_style)
        expected_sector_scan_trade_date = await resolve_snapshot_lookup_trade_date(trade_date)
        snapshot_kwargs = {"account_id": account_id} if account_id else {}
        cached_stock_pools = None
        if not refresh_requested and _is_default_strategy_style(normalized_strategy_style):
            cached_stock_pools = await review_snapshot_service.get_stock_pools_page_snapshot(
                trade_date,
                candidate_limit,
                **snapshot_kwargs,
            )
        use_cached_stock_pools = _stock_pools_snapshot_valid(
            cached_stock_pools,
            expected_sector_scan_trade_date,
        )
        review_bias_profile = await review_snapshot_service.get_review_bias_profile_safe(
            limit_days=10,
            account_id=account_id,
        )

        if use_cached_stock_pools:
            account_context = await decision_context_service.build_account_context(
                trade_date,
                account_id=account_id,
            )
            scored_stocks = _collect_buy_point_source_stocks(cached_stock_pools)
            stock_pools = cached_stock_pools
            market_env = market_env_service.get_current_env(
                stock_pools.sector_scan_trade_date or expected_sector_scan_trade_date
            )
            bundle_context_stocks = scored_stocks
            bundle_context_account = account_context.account
            bundle_context_market_env = market_env
            bundle_context_sector_scan = None
            should_persist_snapshots = True
        elif not _is_default_strategy_style(normalized_strategy_style):
            bundle = await _compute_buy_point_bundle(
                trade_date,
                candidate_limit,
                account_id=account_id,
                strategy_style=normalized_strategy_style,
            )
            scored_stocks = bundle["scored_stocks"]
            stock_pools = bundle["stock_pools"]
            review_bias_profile = bundle["review_bias_profile"]
            bundle_context_stocks = bundle["context"].stocks
            bundle_context_account = bundle["context"].account
            bundle_context_market_env = bundle["context"].market_env
            bundle_context_sector_scan = bundle["context"].sector_scan
            should_persist_snapshots = False
        else:
            bundle = await decision_flow_service.build_candidate_analysis(
                trade_date,
                top_gainers=candidate_limit,
                include_holdings=False,
                account_id=account_id,
            )
            scored_stocks = bundle.scored_stocks
            stock_pools = bundle.stock_pools
            review_bias_profile = bundle.review_bias_profile
            bundle_context_stocks = bundle.context.stocks
            bundle_context_account = bundle.context.account
            bundle_context_market_env = bundle.context.market_env
            bundle_context_sector_scan = bundle.context.sector_scan
            should_persist_snapshots = True

        await _enrich_buy_point_pool_execution_references(
            stock_pools,
            trade_date,
            account_id=account_id,
        )

        result = buy_point_service.analyze(
            trade_date,
            bundle_context_stocks,
            bundle_context_account,
            market_env=bundle_context_market_env,
            sector_scan=bundle_context_sector_scan,
            scored_stocks=scored_stocks,
            stock_pools=stock_pools,
            review_bias_profile=review_bias_profile,
        )
        if should_persist_snapshots:
            await review_snapshot_service.save_analysis_snapshot_safe(
                trade_date,
                stock_pools=None if use_cached_stock_pools else stock_pools,
                buy_analysis=result,
                **snapshot_kwargs,
            )
            if not use_cached_stock_pools:
                await review_snapshot_service.save_stock_pools_page_snapshot_safe(
                    trade_date,
                    candidate_limit,
                    stock_pools,
                    **snapshot_kwargs,
                )

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "strategy_style": normalized_strategy_style,
                "market_env_tag": result.market_env_tag.value,
                "market_env_profile": getattr(bundle_context_market_env, "market_env_profile", "") or result.market_env_tag.value,
                "market_headline": getattr(bundle_context_market_env, "market_headline", "") or "",
                "market_subheadline": getattr(bundle_context_market_env, "market_subheadline", "") or "",
                "trading_tempo_label": getattr(bundle_context_market_env, "trading_tempo_label", "") or "",
                "theme_leaders": [sector.model_dump() for sector in getattr(result, "theme_leaders", [])],
                "industry_leaders": [sector.model_dump() for sector in getattr(result, "industry_leaders", [])],
                "available_buy_points": [bp.model_dump() for bp in result.available_buy_points],
                "observe_buy_points": [bp.model_dump() for bp in result.observe_buy_points],
                "not_buy_points": [bp.model_dump() for bp in result.not_buy_points],
                "total_count": result.total_count,
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"买点分析失败: {str(e)}")


@router.post("/analyze", response_model=ApiResponse)
async def full_decision_analyze(
    trade_date: Optional[str] = Body(None, description="交易日"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    完整决策分析

    综合市场环境、板块扫描、买点分析、卖点分析、账户适配，输出完整决策建议
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account)
        bundle = await decision_flow_service.build_full_decision(
            trade_date,
            top_gainers=200,
            account_id=account_id,
        )

        # 6. 账户适配
        account_fit = account_adapter_service.adapt(
            trade_date,
            bundle.context.account,
            bundle.context.holdings,
            market_env=bundle.context.market_env,
        )

        # 7. 执行摘要
        summary = _generate_summary(
            trade_date,
            bundle.context.market_env,
            account_fit,
            bundle.context.holdings,
        )
        risk_alerts = build_risk_alerts(
            bundle.context.market_env,
            bundle.context.account,
            bundle.buy_analysis,
            bundle.context.holdings,
        )
        snapshot_kwargs = {"account_id": account_id} if account_id else {}
        snapshot_count = await review_snapshot_service.save_analysis_snapshot_safe(
            trade_date,
            stock_pools=bundle.stock_pools,
            buy_analysis=bundle.buy_analysis,
            **snapshot_kwargs,
        )

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "market_env": {
                    "market_env_tag": bundle.context.market_env.market_env_tag.value,
                    "breakout_allowed": bundle.context.market_env.breakout_allowed,
                    "risk_level": bundle.context.market_env.risk_level.value,
                    "market_comment": bundle.context.market_env.market_comment
                },
                "sector_scan": {
                    "mainline_sectors": [s.model_dump() for s in bundle.context.sector_scan.mainline_sectors[:5]],
                    "sub_mainline_sectors": [s.model_dump() for s in bundle.context.sector_scan.sub_mainline_sectors[:5]],
                    "follow_sectors": [s.model_dump() for s in bundle.context.sector_scan.follow_sectors[:10]],
                    "trash_sectors": [s.model_dump() for s in bundle.context.sector_scan.trash_sectors[:10]],
                    "mainline_count": len(bundle.context.sector_scan.mainline_sectors),
                    "sub_mainline_count": len(bundle.context.sector_scan.sub_mainline_sectors),
                },
                "stock_pools": {
                    "market_watch_count": len(bundle.stock_pools.market_watch_pool),
                    "account_executable_count": len(bundle.stock_pools.account_executable_pool),
                    "holding_process_count": len(bundle.stock_pools.holding_process_pool),
                },
                "buy_analysis": {
                    "available_count": len(bundle.buy_analysis.available_buy_points),
                    "observe_count": len(bundle.buy_analysis.observe_buy_points),
                },
                "sell_analysis": {
                    "hold_count": len(bundle.sell_analysis.hold_positions),
                    "reduce_count": len(bundle.sell_analysis.reduce_positions),
                    "sell_count": len(bundle.sell_analysis.sell_positions),
                },
                "account_fit": account_fit.model_dump(),
                "summary": summary.model_dump(),
                "risk_alerts": risk_alerts,
                "review_snapshot_count": snapshot_count,
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"完整决策分析失败: {str(e)}")


@router.get("/review-stats", response_model=ApiResponse)
async def get_review_stats(
    limit_days: int = Query(10, description="最近交易日数量", ge=1, le=30),
    refresh_outcomes: bool = Query(False, description="是否同步补齐复盘收益"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取最近若干交易日的分层复盘统计。"""
    try:
        account_id = _resolve_account_id(current_account)
        review_kwargs = {"account_id": account_id} if account_id else {}
        data = await review_snapshot_service.get_review_stats(
            limit_days=limit_days,
            refresh_outcomes=refresh_outcomes,
            **review_kwargs,
        )
        return ApiResponse(data=data)
    except Exception as e:
        return ApiResponse(code=500, message=f"获取复盘统计失败: {str(e)}")


def _generate_summary(
    trade_date: str,
    market_env,
    account_output,
    holdings
) -> DecisionSummary:
    """生成执行摘要"""
    market_profile = str(getattr(market_env, "market_env_profile", "") or "")

    # 判断今天 action
    if not account_output.new_position_allowed:
        today_action = "少出手或不出手"
    elif market_env.market_env_tag.value == "进攻":
        today_action = "可适度出手"
    elif market_profile == "中性偏强":
        today_action = "等主线确认后出手"
    elif market_profile == "中性偏谨慎":
        today_action = "只做低吸或回踩确认"
    elif market_profile == "弱中性":
        today_action = "尽量少出手"
    elif market_env.market_env_tag.value == "中性":
        today_action = "谨慎出手"
    else:
        today_action = "防守为主"

    # 判断优先看谁
    if holdings:
        # 有持仓优先处理持仓
        loss_holdings = [h for h in holdings if h.pnl_pct < 0]
        if loss_holdings:
            focus = "优先处理亏损持仓"
        else:
            focus = "持仓盈利，可考虑新机会"
    else:
        focus = "关注主线板块核心股"

    # 判断哪些不碰
    if market_env.market_env_tag.value == "防守":
        avoid = "弱势股、杂毛股、跟风股"
    elif market_profile == "中性偏强":
        avoid = "后排跟风、无量突破"
    elif market_profile == "中性偏谨慎":
        avoid = "一致性追高、尾盘抢板"
    elif market_profile == "弱中性":
        avoid = "高位追涨、纯情绪接力"
    elif market_env.market_env_tag.value == "中性":
        avoid = "高位追涨、纯跟风"
    else:
        avoid = "无明确逻辑的杂毛股"

    return DecisionSummary(
        trade_date=trade_date,
        today_action=today_action,
        focus=focus,
        avoid=avoid,
        market_env_tag=market_env.market_env_tag.value,
        breakout_allowed=market_env.breakout_allowed,
        account_action_tag=account_output.account_action_tag,
        new_position_allowed=account_output.new_position_allowed,
        priority_action=account_output.priority_action,
        buy_recommend_count=0,  # 简化
        sell_recommend_count=len([h for h in holdings if h.pnl_pct < -3])
    )
