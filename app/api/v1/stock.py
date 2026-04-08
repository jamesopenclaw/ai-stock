"""
个股筛选 API
"""
import asyncio
import time
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime
import logging

from app.models.schemas import (
    ApiResponse,
    LlmCallStatus,
    StockCheckupTarget,
)
from app.services.stock_filter import (
    stock_filter_service,
)
from app.services.decision_context import decision_context_service
from app.services.decision_flow import decision_flow_service
from app.services.sell_point import sell_point_service
from app.services.stock_checkup import stock_checkup_service
from app.services.buy_point_sop import buy_point_sop_service
from app.services.sell_point_sop import sell_point_sop_service
from app.services.review_snapshot import review_snapshot_service
from app.services.sector_scan_snapshot import resolve_snapshot_lookup_trade_date
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.data.tushare_client import tushare_client
from app.core.config import settings
from app.core.security import AuthenticatedAccount, get_current_account

router = APIRouter()
logger = logging.getLogger(__name__)
STOCK_POOLS_SNAPSHOT_VERSION = 6
_stock_pools_refresh_tasks: dict[str, asyncio.Task] = {}
RADAR_POOLS_CACHE_TTL_SECONDS = 20
_radar_stock_pools_cache: dict[str, dict] = {}


def _resolve_account_id(current_account: Optional[AuthenticatedAccount]) -> Optional[str]:
    """兼容 FastAPI 依赖注入与直接函数调用。"""
    account_id = getattr(current_account, "id", None)
    if isinstance(account_id, str) and account_id:
        return account_id
    return None


def _stock_pools_refresh_key(trade_date: str, candidate_limit: int, account_id: Optional[str] = None) -> str:
    return f"{trade_date}:{candidate_limit}:{account_id or ''}"


def _is_stock_pools_refresh_running(trade_date: str, candidate_limit: int, account_id: Optional[str] = None) -> bool:
    task = _stock_pools_refresh_tasks.get(_stock_pools_refresh_key(trade_date, candidate_limit, account_id))
    return bool(task and not task.done())


def _radar_cache_key(trade_date: str, candidate_limit: int, account_id: Optional[str] = None) -> str:
    return f"{trade_date}:{candidate_limit}:{account_id or ''}"


def _get_cached_radar_result(trade_date: str, candidate_limit: int, account_id: Optional[str] = None):
    payload = _radar_stock_pools_cache.get(_radar_cache_key(trade_date, candidate_limit, account_id))
    if not payload:
        return None
    if time.monotonic() - float(payload.get("fetched_at") or 0.0) > RADAR_POOLS_CACHE_TTL_SECONDS:
        _radar_stock_pools_cache.pop(_radar_cache_key(trade_date, candidate_limit, account_id), None)
        return None
    return payload.get("result")


def _cache_radar_result(trade_date: str, candidate_limit: int, result, account_id: Optional[str] = None) -> None:
    _radar_stock_pools_cache[_radar_cache_key(trade_date, candidate_limit, account_id)] = {
        "fetched_at": time.monotonic(),
        "result": result,
    }


def _summarize_sector_list(sectors, limit: int = 5):
    if not sectors:
        return []
    return list(sectors[:limit])


def _attach_stock_pools_context_snapshot(result, *, market_env=None, sector_scan=None):
    result.market_env = market_env
    result.mainline_sectors = _summarize_sector_list(getattr(sector_scan, "mainline_sectors", []), 5)
    result.sub_mainline_sectors = _summarize_sector_list(getattr(sector_scan, "sub_mainline_sectors", []), 3)
    return result


def _unpack_candidate_result(candidate_result):
    if isinstance(candidate_result, tuple):
        if len(candidate_result) >= 4:
            return candidate_result[0], candidate_result[1], candidate_result[2], candidate_result[3]
        if len(candidate_result) >= 2:
            return candidate_result[0], candidate_result[1], None, None
    return candidate_result, None, None, None


def _serialize_stock_pools_result(
    result,
    *,
    refresh_in_progress: bool = False,
    refresh_requested: bool = False,
    stale_snapshot: bool = False,
    mode: str = "stable",
    include_watch_candidates: bool = False,
):
    payload = {
        "trade_date": result.trade_date,
        "resolved_trade_date": result.resolved_trade_date,
        "sector_scan_trade_date": result.sector_scan_trade_date,
        "sector_scan_resolved_trade_date": result.sector_scan_resolved_trade_date,
        "candidate_data_status": getattr(result, "candidate_data_status", None),
        "candidate_data_message": getattr(result, "candidate_data_message", None),
        "snapshot_status_message": getattr(result, "snapshot_status_message", None),
        "market_env": result.market_env.model_dump() if getattr(result, "market_env", None) else None,
        "mainline_sectors": [sector.model_dump() for sector in getattr(result, "mainline_sectors", [])],
        "sub_mainline_sectors": [sector.model_dump() for sector in getattr(result, "sub_mainline_sectors", [])],
        "global_trade_gate": result.global_trade_gate.model_dump(),
        "market_watch_pool": [s.model_dump() for s in result.market_watch_pool],
        "account_executable_pool": [s.model_dump() for s in result.account_executable_pool],
        "holding_process_pool": [s.model_dump() for s in result.holding_process_pool],
        "total_count": result.total_count,
        "llm_summary": None,
        "llm_status": LlmCallStatus(
            enabled=False,
            success=False,
            status="disabled",
            message="三池分类已改为纯规则输出，不再调用 LLM",
        ).model_dump(),
        "refresh_in_progress": refresh_in_progress,
        "refresh_requested": refresh_requested,
        "stale_snapshot": stale_snapshot,
        "mode": mode,
        "is_realtime": mode == "radar",
        "radar_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if mode == "radar" else None,
    }
    if include_watch_candidates:
        candidates = [s.model_dump() for s in getattr(result, "market_watch_candidates", [])]
        payload["market_watch_candidates"] = candidates
        payload["market_watch_candidate_count"] = len(candidates)
    return payload


async def _compute_stock_pools_result(
    trade_date: str,
    candidate_limit: int,
    *,
    account_id: Optional[str] = None,
):
    bundle = await decision_flow_service.build_candidate_analysis(
        trade_date,
        top_gainers=candidate_limit,
        include_holdings=True,
        account_id=account_id,
    )
    result = bundle.stock_pools
    result.resolved_trade_date = bundle.context.resolved_stock_trade_date
    result.candidate_data_status = getattr(bundle.context, "candidate_data_status", None)
    result.candidate_data_message = getattr(bundle.context, "candidate_data_message", None)
    result.sector_scan_trade_date = bundle.context.sector_scan_trade_date
    result.sector_scan_resolved_trade_date = bundle.context.sector_scan_resolved_trade_date
    result.snapshot_version = STOCK_POOLS_SNAPSHOT_VERSION
    _attach_stock_pools_context_snapshot(
        result,
        market_env=bundle.context.market_env,
        sector_scan=bundle.context.sector_scan,
    )
    sell_analysis = sell_point_service.analyze(
        trade_date,
        bundle.context.holdings,
        market_env=bundle.context.market_env,
        sector_scan=bundle.context.sector_scan,
    )
    result = stock_filter_service.attach_sell_analysis(result, sell_analysis)
    return result


async def _compute_radar_stock_pools_result(
    trade_date: str,
    candidate_limit: int,
    *,
    account_id: Optional[str] = None,
):
    account_context = await decision_context_service.build_account_context(
        trade_date,
        account_id=account_id,
    )
    market_env = market_env_service.get_current_env(trade_date)
    sector_scan = sector_scan_service.scan(
        trade_date,
        limit_output=False,
        market_env=market_env,
        prefer_today=True,
    )
    stocks, resolved_stock_trade_date, candidate_data_status, candidate_data_message = _unpack_candidate_result(
        decision_context_service.get_candidate_stocks(
        trade_date,
        top_gainers=candidate_limit,
        holdings_list=account_context.holdings_list,
        include_holdings=True,
        prefer_today=True,
    ))
    scored_stocks = stock_filter_service.filter_with_context(
        trade_date,
        stocks,
        market_env=market_env,
        sector_scan=sector_scan,
        account=account_context.account,
        holdings=account_context.holdings_list,
    )
    review_bias_profile = await review_snapshot_service.get_review_bias_profile_safe(
        limit_days=10,
        account_id=account_id,
    )
    result = stock_filter_service.classify_pools(
        trade_date,
        stocks,
        account_context.holdings_list,
        account_context.account,
        market_env=market_env,
        sector_scan=sector_scan,
        scored_stocks=scored_stocks,
        review_bias_profile=review_bias_profile,
    )
    result.resolved_trade_date = resolved_stock_trade_date or trade_date
    result.candidate_data_status = candidate_data_status
    result.candidate_data_message = candidate_data_message
    result.sector_scan_trade_date = trade_date
    result.sector_scan_resolved_trade_date = getattr(sector_scan, "resolved_trade_date", None) or trade_date
    result.snapshot_version = STOCK_POOLS_SNAPSHOT_VERSION
    _attach_stock_pools_context_snapshot(
        result,
        market_env=market_env,
        sector_scan=sector_scan,
    )
    sell_analysis = sell_point_service.analyze(
        trade_date,
        account_context.holdings,
        market_env=market_env,
        sector_scan=sector_scan,
    )
    return stock_filter_service.attach_sell_analysis(result, sell_analysis)


async def _persist_stock_pools_result(
    trade_date: str,
    candidate_limit: int,
    result,
    *,
    account_id: Optional[str] = None,
) -> None:
    snapshot_kwargs = {"account_id": account_id} if account_id else {}
    await review_snapshot_service.save_analysis_snapshot_safe(
        trade_date,
        stock_pools=result,
        **snapshot_kwargs,
    )
    await review_snapshot_service.save_stock_pools_page_snapshot_safe(
        trade_date,
        candidate_limit,
        result,
        **snapshot_kwargs,
    )


def _ensure_stock_pools_background_refresh(
    trade_date: str,
    candidate_limit: int,
    *,
    account_id: Optional[str] = None,
) -> bool:
    key = _stock_pools_refresh_key(trade_date, candidate_limit, account_id)
    if _is_stock_pools_refresh_running(trade_date, candidate_limit, account_id):
        return False

    async def _runner():
        try:
            result = await _compute_stock_pools_result(
                trade_date,
                candidate_limit,
                account_id=account_id,
            )
            await _persist_stock_pools_result(
                trade_date,
                candidate_limit,
                result,
                account_id=account_id,
            )
            logger.info(
                "三池后台刷新完成: trade_date=%s candidate_limit=%s account_id=%s",
                trade_date,
                candidate_limit,
                account_id or "",
            )
        except Exception as exc:
            logger.warning(
                "三池后台刷新失败: trade_date=%s candidate_limit=%s account_id=%s err=%s",
                trade_date,
                candidate_limit,
                account_id or "",
                exc,
            )
        finally:
            _stock_pools_refresh_tasks.pop(key, None)

    _stock_pools_refresh_tasks[key] = asyncio.create_task(_runner())
    return True


@router.get("/filter", response_model=ApiResponse)
async def filter_stocks(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(50, description="返回数量限制", ge=1, le=200),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    个股筛选

    根据当日行情数据，筛选出符合条件的个股
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account) if settings.auth_enabled else None
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=max(100, min(limit, 200)),
            include_holdings=False,
            account_id=account_id,
        )

        # 筛选
        result = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "stocks": [s.model_dump() for s in result],
                "total": len(result)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"个股筛选失败: {str(e)}")


@router.get("/pools", response_model=ApiResponse)
async def get_stock_pools(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(100, description="候选股数量限制", ge=1, le=500),
    refresh: bool = Query(False, description="是否强制重新计算三池结果并覆盖快照"),
    mode: str = Query("stable", description="三池模式：stable 稳定快照，radar 实时雷达"),
    include_watch_candidates: bool = Query(False, description="是否返回观察候选全集，仅用于排查"),
    force_llm_refresh: bool = Query(False, description="保留字段，三池页当前不再触发 LLM"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """
    三池分类

    返回：
    - global_trade_gate: 三池总闸门
    - market_watch_pool: 市场最强观察池
    - account_executable_pool: 账户可参与池
    - holding_process_pool: 持仓处理池
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account) if settings.auth_enabled else None
        candidate_limit = max(100, min(limit, 300))
        normalized_mode = str(mode or "stable").strip().lower()
        if normalized_mode not in {"stable", "radar"}:
            normalized_mode = "stable"

        if normalized_mode == "radar":
            if refresh:
                _radar_stock_pools_cache.pop(_radar_cache_key(trade_date, candidate_limit, account_id), None)
            cached_radar = None if refresh else _get_cached_radar_result(trade_date, candidate_limit, account_id)
            if cached_radar:
                return ApiResponse(
                    data=_serialize_stock_pools_result(
                        cached_radar,
                        refresh_in_progress=False,
                        refresh_requested=False,
                        stale_snapshot=False,
                        mode="radar",
                    )
                )
            result = await _compute_radar_stock_pools_result(
                trade_date,
                candidate_limit,
                account_id=account_id,
            )
            _cache_radar_result(trade_date, candidate_limit, result, account_id)
            return ApiResponse(
                data=_serialize_stock_pools_result(
                    result,
                    refresh_in_progress=False,
                    refresh_requested=False,
                    stale_snapshot=False,
                    mode="radar",
                    include_watch_candidates=include_watch_candidates,
                )
            )

        expected_sector_scan_trade_date = await resolve_snapshot_lookup_trade_date(trade_date)
        snapshot_kwargs = {"account_id": account_id} if account_id else {}
        cached = await review_snapshot_service.get_stock_pools_page_snapshot(
            trade_date,
            candidate_limit,
            **snapshot_kwargs,
        )
        cache_valid = bool(
            cached
            and cached.snapshot_version == STOCK_POOLS_SNAPSHOT_VERSION
            and cached.sector_scan_trade_date
            and cached.sector_scan_trade_date == expected_sector_scan_trade_date
        )

        if refresh:
            started = _ensure_stock_pools_background_refresh(
                trade_date,
                candidate_limit,
                account_id=account_id,
            )
            if cached:
                snapshot_status_message = None
                if not cache_valid:
                    snapshot_status_message = (
                        f"当前先展示旧稳定快照（候选 {cached.resolved_trade_date or '-'} / 板块 {cached.sector_scan_resolved_trade_date or '-'}），"
                        f"后台正在按 {trade_date} 重算。"
                    )
                    cached.snapshot_status_message = snapshot_status_message
                return ApiResponse(
                    data=_serialize_stock_pools_result(
                        cached,
                        refresh_in_progress=_is_stock_pools_refresh_running(trade_date, candidate_limit, account_id),
                        refresh_requested=started,
                        stale_snapshot=not cache_valid,
                        mode="stable",
                        include_watch_candidates=include_watch_candidates,
                    )
                )

            return ApiResponse(
                data={
                    "trade_date": trade_date,
                    "resolved_trade_date": "",
                    "sector_scan_trade_date": expected_sector_scan_trade_date,
                    "sector_scan_resolved_trade_date": "",
                    "market_env": None,
                    "mainline_sectors": [],
                    "sub_mainline_sectors": [],
                    "global_trade_gate": {
                        "status": "允许试错",
                        "allow_new_positions": True,
                        "dominant_reason": "等待后台刷新后再给出正式总闸门。",
                        "reasons": [],
                        "account_pool_limit": 3,
                    },
                    "market_watch_pool": [],
                    "account_executable_pool": [],
                    "holding_process_pool": [],
                    "total_count": 0,
                    "llm_summary": None,
                    "llm_status": LlmCallStatus(
                        enabled=False,
                        success=False,
                        status="disabled",
                        message="三池分类已改为纯规则输出，不再调用 LLM",
                    ).model_dump(),
                    "refresh_in_progress": True,
                    "refresh_requested": started,
                    "stale_snapshot": False,
                    "candidate_data_status": None,
                    "candidate_data_message": None,
                    "snapshot_status_message": f"后台正在按 {trade_date} 生成稳定快照。",
                    "mode": "stable",
                    "is_realtime": False,
                    "radar_generated_at": None,
                },
                message="已触发后台刷新，当前暂无可展示的三池快照",
            )

        if cache_valid:
            return ApiResponse(
                data=_serialize_stock_pools_result(
                    cached,
                    refresh_in_progress=_is_stock_pools_refresh_running(trade_date, candidate_limit, account_id),
                    refresh_requested=False,
                    stale_snapshot=False,
                    mode="stable",
                    include_watch_candidates=include_watch_candidates,
                )
            )

        result = await _compute_stock_pools_result(
            trade_date,
            candidate_limit,
            account_id=account_id,
        )
        await _persist_stock_pools_result(
            trade_date,
            candidate_limit,
            result,
            account_id=account_id,
        )

        return ApiResponse(
            data=_serialize_stock_pools_result(
                result,
                refresh_in_progress=False,
                refresh_requested=False,
                stale_snapshot=False,
                mode="stable",
                include_watch_candidates=include_watch_candidates,
            )
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取三池失败: {str(e)}")


@router.get("/detail/{ts_code}", response_model=ApiResponse)
async def get_stock_detail(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取个股详情
    """
    # 处理 trade_date，确保是字符串
    if trade_date is None or not isinstance(trade_date, str):
        trade_date = datetime.now().strftime("%Y-%m-%d")

    # 确保是字符串
    trade_date = str(trade_date)

    try:
        detail = tushare_client.get_stock_detail(ts_code, trade_date.replace("-", ""))

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "stock": detail
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取个股详情失败: {str(e)}")


@router.get("/checkup/{ts_code}", response_model=ApiResponse)
async def get_stock_checkup(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    checkup_target: StockCheckupTarget = Query(
        StockCheckupTarget.OBSERVE,
        description="体检目标：观察型 / 持仓型 / 交易型",
    ),
    force_llm_refresh: bool = Query(False, description="是否强制刷新 LLM 缓存"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取单只股票的全面体检结果。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account) if settings.auth_enabled else None
        result = await stock_checkup_service.checkup(
            ts_code,
            trade_date,
            checkup_target,
            account_id=account_id,
            force_llm_refresh=force_llm_refresh,
        )
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取个股体检失败: {str(e)}")


@router.get("/buy-analysis/{ts_code}", response_model=ApiResponse)
async def get_stock_buy_analysis(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    source_pool_tag: Optional[str] = Query(None, description="来源池标签，来自三池页时用于保持解释语境一致"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取单只股票的详细买点 SOP 分析。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account) if settings.auth_enabled else None
        result = await buy_point_sop_service.analyze(
            ts_code,
            trade_date,
            account_id=account_id,
            preferred_pool_tag=source_pool_tag,
        )
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取买点分析失败: {str(e)}")


@router.get("/sell-analysis/{ts_code}", response_model=ApiResponse)
async def get_stock_sell_analysis(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取单只持仓的详细卖点 SOP 分析。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        account_id = _resolve_account_id(current_account) if settings.auth_enabled else None
        result = await sell_point_sop_service.analyze(
            ts_code,
            trade_date,
            account_id=account_id,
        )
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取卖点分析失败: {str(e)}")
