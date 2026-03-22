"""
个股筛选 API
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from app.models.schemas import (
    StockInput,
    ApiResponse
)
from app.services.stock_filter import (
    stock_filter_service,
)
from app.services.decision_context import decision_context_service
from app.services.sell_point import sell_point_service
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
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=max(100, min(limit, 200)),
            include_holdings=False,
        )

        # 筛选
        result = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
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
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=max(100, min(limit, 300)),
            include_holdings=True,
        )
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
        )

        # 三池分类
        result = stock_filter_service.classify_pools(
            trade_date,
            context.stocks,
            context.holdings_list,
            context.account,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            scored_stocks=scored_stocks,
        )
        sell_analysis = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
        )
        result = stock_filter_service.attach_sell_analysis(result, sell_analysis)

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
