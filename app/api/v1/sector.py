"""
板块扫描 API
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from app.models.schemas import (
    SectorOutput,
    SectorScanResponse,
    LeaderSectorResponse,
    ApiResponse
)
from app.services.sector_scan import sector_scan_service

router = APIRouter()


@router.get("/scan", response_model=ApiResponse)
async def scan_sectors(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
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
        result = sector_scan_service.scan(trade_date)
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "mainline_sectors": [s.model_dump() for s in result.mainline_sectors],
                "sub_mainline_sectors": [s.model_dump() for s in result.sub_mainline_sectors],
                "follow_sectors": [s.model_dump() for s in result.follow_sectors],
                "trash_sectors": [s.model_dump() for s in result.trash_sectors],
                "total_sectors": result.total_sectors
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"板块扫描失败: {str(e)}")


@router.get("/leader", response_model=ApiResponse)
async def get_leader_sector(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取当日主线板块

    返回最重要的主线板块，用于决策参考
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = sector_scan_service.get_leader(trade_date)
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "sector": result.sector.model_dump()
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取主线板块失败: {str(e)}")


@router.get("/list", response_model=ApiResponse)
async def list_sectors(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(20, description="返回数量限制", ge=1, le=100),
    tradeable_only: bool = Query(False, description="仅返回可交易板块")
) -> ApiResponse:
    """
    获取板块列表

    返回当日板块按涨幅排序列表
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = sector_scan_service.scan(trade_date)

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
                "sectors": [s.model_dump() for s in all_sectors],
                "total": len(all_sectors)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取板块列表失败: {str(e)}")
