"""
决策分析 API - 卖点与完整决策
"""
from fastapi import APIRouter, Query, Body, Depends
from typing import Optional
from datetime import datetime
import logging
from collections import OrderedDict

from app.models.schemas import (
    AccountInput,
    AccountPosition,
    SellPointResponse,
    FullDecisionResponse,
    DecisionSummary,
    LlmCallStatus,
    ApiResponse
)
from app.services.sell_point import sell_point_service
from app.services.account_adapter import account_adapter_service
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service, merge_holdings_into_candidate_stocks
from app.services.buy_point import buy_point_service
from app.data.tushare_client import tushare_client
from app.models.schemas import StockInput
from app.services.decision_context import decision_context_service
from app.services.decision_flow import decision_flow_service
from app.services.review_snapshot import review_snapshot_service
from app.services.llm_explainer import llm_explainer_service
from app.core.security import AuthenticatedAccount, get_current_account
from app.services.sector_scan_snapshot import resolve_snapshot_lookup_trade_date

router = APIRouter()
logger = logging.getLogger(__name__)
STOCK_POOLS_SNAPSHOT_VERSION = 3


def _resolve_account_id(current_account: Optional[AuthenticatedAccount]) -> Optional[str]:
    """兼容 FastAPI 依赖注入与直接函数调用。"""
    account_id = getattr(current_account, "id", None)
    if isinstance(account_id, str) and account_id:
        return account_id
    return None


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
        stock_pools.trend_recognition_pool,
        stock_pools.market_watch_pool,
    ):
        for stock in group:
            deduped.setdefault(stock.ts_code, stock)
    return list(deduped.values())


@router.get("/sell-point", response_model=ApiResponse)
async def analyze_sell_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    force_llm_refresh: bool = Query(False, description="是否强制刷新 LLM 解读缓存"),
    include_llm: bool = Query(True, description="是否包含 LLM 卖点解读"),
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

    try:
        account_id = _resolve_account_id(current_account)
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=100,
            include_holdings=False,
            account_id=account_id,
        )

        # 卖点分析
        result = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
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
                context.market_env,
                force_refresh=force_llm_refresh,
                **llm_kwargs,
            )

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "hold_positions": [p.model_dump() for p in result.hold_positions],
                "reduce_positions": [p.model_dump() for p in result.reduce_positions],
                "sell_positions": [p.model_dump() for p in result.sell_positions],
                "total_count": result.total_count,
                "llm_summary": llm_summary.model_dump() if llm_summary else None,
                "llm_status": llm_status.model_dump(),
            }
        )
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
        expected_sector_scan_trade_date = await resolve_snapshot_lookup_trade_date(trade_date)
        snapshot_kwargs = {"account_id": account_id} if account_id else {}
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
                "market_env_tag": result.market_env_tag.value,
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
        if data.get("pending_outcome_count", 0) > 0 and not data.get("refresh_in_progress"):
            started = review_snapshot_service.ensure_background_refresh(limit_days=limit_days)
            if started:
                data["refresh_in_progress"] = True
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

    # 判断今天 action
    if not account_output.new_position_allowed:
        today_action = "少出手或不出手"
    elif market_env.market_env_tag.value == "进攻":
        today_action = "可适度出手"
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
