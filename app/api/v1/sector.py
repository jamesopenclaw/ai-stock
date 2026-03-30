"""
板块扫描 API
"""
import copy
import time
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from app.data.tushare_client import tushare_client
from app.models.schemas import (
    SectorOutput,
    SectorScanResponse,
    LeaderSectorResponse,
    ApiResponse
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.sector_scan_snapshot import sector_scan_snapshot_service

router = APIRouter()
SECTOR_SCAN_CACHE_TTL_SECONDS = 20
_sector_scan_route_cache: dict[str, dict] = {}


def _format_trade_date(trade_date: str) -> str:
    compact = str(trade_date).replace("-", "").strip()[:8]
    if len(compact) != 8:
        return str(trade_date)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _today_trade_date() -> str:
    return tushare_client._now_sh().strftime("%Y-%m-%d")


def _previous_open_trade_date(trade_date: str) -> str:
    compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
    resolved_trade_date = tushare_client._resolve_trade_date(compact_trade_date)
    recent_dates = tushare_client._recent_open_dates(resolved_trade_date, count=2)
    if len(recent_dates) >= 2:
        return _format_trade_date(recent_dates[1])
    return _format_trade_date(resolved_trade_date)


async def _resolve_snapshot_lookup_trade_date(trade_date: str) -> str:
    """
    默认打开板块页时优先返回稳定快照：
    - 盘中：显示前一交易日
    - 盘后：若当天未刷新生成快照，仍显示前一交易日
    - 一旦当天已刷新生成快照，则直接显示当天
    """
    today_trade_date = _today_trade_date()
    if trade_date != today_trade_date:
        return trade_date

    today_snapshot = await sector_scan_snapshot_service.get_snapshot(trade_date)
    if today_snapshot:
        return trade_date

    last_completed_trade_date = _format_trade_date(
        tushare_client.get_last_completed_trade_date(trade_date)
    )
    if last_completed_trade_date != trade_date:
        return last_completed_trade_date

    return _previous_open_trade_date(trade_date)


async def _resolve_snapshot_lookup(trade_date: str) -> tuple[str, Optional[SectorScanResponse]]:
    """
    返回实际用于读取快照的交易日；若当天快照已存在，直接返回该快照，避免重复查询。
    """
    today_trade_date = _today_trade_date()
    if trade_date != today_trade_date:
        return trade_date, None

    today_snapshot = await sector_scan_snapshot_service.get_snapshot(trade_date)
    if today_snapshot:
        return trade_date, today_snapshot

    last_completed_trade_date = _format_trade_date(
        tushare_client.get_last_completed_trade_date(trade_date)
    )
    if last_completed_trade_date != trade_date:
        return last_completed_trade_date, None

    return _previous_open_trade_date(trade_date), None


def _scan_cache_key(trade_date: str) -> str:
    return str(trade_date or "").strip()


def _get_cached_scan_payload(trade_date: str) -> Optional[dict]:
    cached = _sector_scan_route_cache.get(_scan_cache_key(trade_date))
    if not cached:
        return None
    if time.monotonic() - float(cached.get("fetched_at") or 0) > SECTOR_SCAN_CACHE_TTL_SECONDS:
        _sector_scan_route_cache.pop(_scan_cache_key(trade_date), None)
        return None
    return copy.deepcopy(cached.get("payload"))


def _cache_scan_payload(trade_date: str, payload: dict) -> None:
    _sector_scan_route_cache[_scan_cache_key(trade_date)] = {
        "fetched_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }


async def _get_or_refresh_sector_scan(
    trade_date: str,
    *,
    refresh: bool = False,
):
    """读取稳定板块扫描快照；强刷时按请求日重新计算并覆盖。"""
    snapshot_trade_date = trade_date
    if not refresh:
        snapshot_trade_date, cached = await _resolve_snapshot_lookup(trade_date)
        if cached:
            return cached
        cached = await sector_scan_snapshot_service.get_snapshot(snapshot_trade_date)
        if cached:
            return cached

    market_env = market_env_service.get_current_env(snapshot_trade_date)
    result = sector_scan_service.scan(
        snapshot_trade_date,
        limit_output=False,
        market_env=market_env,
    )
    try:
        await sector_scan_snapshot_service.save_snapshot(snapshot_trade_date, result)
    except Exception:
        pass
    return result


@router.get("/scan", response_model=ApiResponse)
async def scan_sectors(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    refresh: bool = Query(False, description="是否强制重新计算并覆盖当天板块扫描快照"),
) -> ApiResponse:
    """
    板块扫描

    返回当日板块分类：
    - mainline_sectors: 主线板块（可交易）
    - sub_mainline_sectors: 次主线板块
    - follow_sectors: 跟风板块（谨慎）
    - trash_sectors: 杂毛板块（不建议）
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        if not refresh:
            cached_payload = _get_cached_scan_payload(trade_date)
            if cached_payload is not None:
                return ApiResponse(data=cached_payload)
        full_result = await _get_or_refresh_sector_scan(trade_date, refresh=refresh)
        result = sector_scan_service.limit_scan_result(full_result)
        payload = {
            "trade_date": result.trade_date,
            "resolved_trade_date": result.resolved_trade_date,
            "sector_data_mode": result.sector_data_mode,
            "concept_data_status": result.concept_data_status,
            "concept_data_message": result.concept_data_message,
            "threshold_profile": result.threshold_profile,
            "mainline_sectors": [s.model_dump() for s in result.mainline_sectors],
            "sub_mainline_sectors": [s.model_dump() for s in result.sub_mainline_sectors],
            "follow_sectors": [s.model_dump() for s in result.follow_sectors],
            "trash_sectors": [s.model_dump() for s in result.trash_sectors],
            "total_sectors": result.total_sectors
        }
        _cache_scan_payload(trade_date, payload)
        return ApiResponse(data=payload)
    except Exception as e:
        return ApiResponse(code=500, message=f"板块扫描失败: {str(e)}")


@router.get("/leader", response_model=ApiResponse)
async def get_leader_sector(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    refresh: bool = Query(False, description="是否强制重新计算并覆盖当天板块扫描快照"),
) -> ApiResponse:
    """
    获取当日主线板块

    返回最重要的主线板块，用于决策参考
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        scan_result = await _get_or_refresh_sector_scan(trade_date, refresh=refresh)
        result = sector_scan_service.build_leader_from_scan(trade_date, scan_result)
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "resolved_trade_date": result.resolved_trade_date,
                "sector_data_mode": result.sector_data_mode,
                "threshold_profile": result.threshold_profile,
                "concept_data_status": result.concept_data_status,
                "concept_data_message": result.concept_data_message,
                "sector": result.sector.model_dump(),
                "leader_stocks": [s.model_dump() for s in result.leader_stocks],
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取主线板块失败: {str(e)}")


@router.get("/list", response_model=ApiResponse)
async def list_sectors(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(20, description="返回数量限制", ge=1, le=100),
    tradeable_only: bool = Query(False, description="仅返回可交易板块"),
    refresh: bool = Query(False, description="是否强制重新计算并覆盖当天板块扫描快照"),
) -> ApiResponse:
    """
    获取板块列表

    返回当日板块按涨幅排序列表
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await _get_or_refresh_sector_scan(trade_date, refresh=refresh)

        # 合并所有板块
        all_sectors = (
            result.mainline_sectors +
            result.sub_mainline_sectors +
            result.follow_sectors +
            result.trash_sectors
        )

        # 按涨幅排序
        all_sectors.sort(key=lambda x: x.sector_change_pct, reverse=True)

        # 过滤可交易
        if tradeable_only:
            from app.models.schemas import SectorTradeabilityTag
            all_sectors = [s for s in all_sectors
                          if s.sector_tradeability_tag == SectorTradeabilityTag.TRADABLE]

        # 限制数量
        all_sectors = all_sectors[:limit]

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "resolved_trade_date": result.resolved_trade_date,
                "sector_data_mode": result.sector_data_mode,
                "concept_data_status": result.concept_data_status,
                "concept_data_message": result.concept_data_message,
                "threshold_profile": result.threshold_profile,
                "sectors": [s.model_dump() for s in all_sectors],
                "total": len(all_sectors)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取板块列表失败: {str(e)}")


@router.get("/top-stocks", response_model=ApiResponse)
async def get_sector_top_stocks(
    sector_name: str = Query(..., description="板块名称"),
    sector_source_type: Optional[str] = Query(None, description="板块来源类型"),
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(10, description="返回数量限制", ge=1, le=20),
    refresh: bool = Query(False, description="是否强制重新计算并覆盖当天板块扫描快照"),
) -> ApiResponse:
    """获取指定板块的 Top 股票。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        scan_result = await _get_or_refresh_sector_scan(trade_date, refresh=refresh)
        result = sector_scan_service.build_sector_top_stocks_from_scan(
            trade_date,
            scan_result,
            sector_name=sector_name,
            sector_source_type=sector_source_type,
            limit=limit,
        )
        if not result:
            return ApiResponse(code=404, message=f"未找到板块: {sector_name}")
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "resolved_trade_date": result.resolved_trade_date,
                "sector_data_mode": result.sector_data_mode,
                "threshold_profile": result.threshold_profile,
                "concept_data_status": result.concept_data_status,
                "concept_data_message": result.concept_data_message,
                "sector": result.sector.model_dump(),
                "top_stocks": [stock.model_dump() for stock in result.top_stocks],
                "total": result.total,
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取板块 Top 股票失败: {str(e)}")
