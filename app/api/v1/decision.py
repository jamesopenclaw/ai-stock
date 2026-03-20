"""
决策分析 API - 买点分析
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from app.models.schemas import (
    BuyPointRequest,
    BuyPointResponse,
    ApiResponse
)
from app.services.buy_point import buy_point_service
from app.data.tushare_client import tushare_client
from app.models.schemas import StockInput

router = APIRouter()


@router.get("/buy-point", response_model=ApiResponse)
async def analyze_buy_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(50, description="分析股票数量限制", ge=1, le=200)
) -> ApiResponse:
    """
    买点分析

    分析候选股票的买点，返回：
    - available_buy_points: 可买候选
    - observe_buy_points: 观察候选
    - not_buy_points: 不建议买
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 获取候选股票
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

        # 买点分析
        result = buy_point_service.analyze(trade_date, stocks)

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "market_env_tag": result.market_env_tag.value,
                "available_buy_points": [bp.model_dump() for bp in result.available_buy_points],
                "observe_buy_points": [bp.model_dump() for bp in result.observe_buy_points],
                "not_buy_points": [bp.model_dump() for bp in result.not_buy_points],
                "total_count": result.total_count
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"买点分析失败: {str(e)}")


@router.post("/buy-point/analyze", response_model=ApiResponse)
async def analyze_buy_point_custom(request: BuyPointRequest) -> ApiResponse:
    """
    买点分析（自定义股票列表）

    使用自定义股票列表进行分析
    """
    try:
        result = buy_point_service.analyze(request.trade_date, [])

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "market_env_tag": result.market_env_tag.value,
                "available_buy_points": [bp.model_dump() for bp in result.available_buy_points],
                "observe_buy_points": [bp.model_dump() for bp in result.observe_buy_points],
                "not_buy_points": [bp.model_dump() for bp in result.not_buy_points],
                "total_count": result.total_count
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"买点分析失败: {str(e)}")
