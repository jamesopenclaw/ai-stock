"""
个股筛选 API
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from datetime import datetime

from app.models.schemas import (
    StockInput,
    StockOutput,
    StockPoolsOutput,
    ApiResponse
)
from app.services.stock_filter import stock_filter_service
from app.data.tushare_client import tushare_client

router = APIRouter()


@router.get("/filter", response_model=ApiResponse)
async def filter_stocks(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(50, description="返回数量限制", ge=1, le=200)
) -> ApiResponse:
    """
    个股筛选

    根据当日行情数据，筛选出符合条件的个股
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 获取个股数据
        stock_list = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=limit)

        # 转换为输入模型
        stocks = [
            StockInput(
                ts_code=s["ts_code"],
                stock_name=s["stock_name"],
                sector_name=s.get("sector_name", "未知"),
                close=s["close"],
                change_pct=s["change_pct"],
                turnover_rate=s["turnover_rate"],
                amount=s["amount"],
                vol_ratio=s.get("vol_ratio"),
                high=s["high"],
                low=s["low"],
                open=s["open"],
                pre_close=s["pre_close"],
            )
            for s in stock_list
        ]

        # 筛选
        result = stock_filter_service.filter(trade_date, stocks)

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
    limit: int = Query(100, description="候选股数量限制", ge=1, le=500)
) -> ApiResponse:
    """
    三池分类

    返回：
    - market_watch_pool: 市场最强观察池
    - account_executable_pool: 账户可参与池
    - holding_process_pool: 持仓处理池
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 获取个股数据
        stock_list = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=limit)

        # 转换为输入模型
        stocks = [
            StockInput(
                ts_code=s["ts_code"],
                stock_name=s["stock_name"],
                sector_name=s.get("sector_name", "未知"),
                close=s["close"],
                change_pct=s["change_pct"],
                turnover_rate=s["turnover_rate"],
                amount=s["amount"],
                vol_ratio=s.get("vol_ratio"),
                high=s["high"],
                low=s["low"],
                open=s["open"],
                pre_close=s["pre_close"],
            )
            for s in stock_list
        ]

        # 模拟持仓（实际从账户系统获取）
        holdings = []

        # 三池分类
        result = stock_filter_service.classify_pools(trade_date, stocks, holdings)

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "market_watch_pool": [s.model_dump() for s in result.market_watch_pool],
                "account_executable_pool": [s.model_dump() for s in result.account_executable_pool],
                "holding_process_pool": [s.model_dump() for s in result.holding_process_pool],
                "total_count": result.total_count
            }
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
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

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
