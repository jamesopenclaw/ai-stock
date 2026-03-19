"""
市场环境 API
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

from app.models.schemas import (
    MarketEnvInput,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    IndexQuote,
    ApiResponse
)
from app.services.market_env import market_env_service
from app.data.tushare_client import tushare_client

router = APIRouter()


@router.get("/env", response_model=ApiResponse)
async def get_market_env(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取市场环境判定

    根据当日行情数据，输出：
    - market_env_tag: 进攻/中性/防守
    - breakout_allowed: 是否允许突破型操作
    - risk_level: 低/中/高
    - market_comment: 市场简评
    """
    # 默认今天
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = market_env_service.get_current_env(trade_date)
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "market_env_tag": result.market_env_tag.value,
                "breakout_allowed": result.breakout_allowed,
                "risk_level": result.risk_level.value,
                "market_comment": result.market_comment,
                "index_score": result.index_score,
                "sentiment_score": result.sentiment_score,
                "overall_score": result.overall_score
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取市场环境失败: {str(e)}")


@router.post("/env/analyze", response_model=ApiResponse)
async def analyze_market_env(input_data: MarketEnvInput) -> ApiResponse:
    """
    分析市场环境（自定义输入）

    使用自定义数据进行分析，用于测试或特殊场景
    """
    try:
        result = market_env_service.analyze(input_data)
        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "market_env_tag": result.market_env_tag.value,
                "breakout_allowed": result.breakout_allowed,
                "risk_level": result.risk_level.value,
                "market_comment": result.market_comment,
                "index_score": result.index_score,
                "sentiment_score": result.sentiment_score,
                "overall_score": result.overall_score
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"分析失败: {str(e)}")


@router.get("/index", response_model=ApiResponse)
async def get_index_quote(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取主要指数行情

    返回上证指数、深证成指、创业板指的实时行情
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        quotes = tushare_client.get_index_quote(trade_date.replace("-", ""))
        return ApiResponse(
            data={
                "trade_date": trade_date,
                "indexes": quotes
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取指数行情失败: {str(e)}")


@router.get("/stats", response_model=ApiResponse)
async def get_market_stats(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取市场情绪统计

    返回涨跌停数量、炸板率等情绪指标
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        stats = tushare_client.get_limit_stats(trade_date.replace("-", ""))
        turnover = tushare_client.get_market_turnover(trade_date.replace("-", ""))
        up_down = tushare_client.get_up_down_ratio(trade_date.replace("-", ""))

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "limit_up_count": stats.get("limit_up_count", 0),
                "limit_down_count": stats.get("limit_down_count", 0),
                "broken_board_rate": stats.get("broken_board_rate", 0),
                "market_turnover": turnover,
                "up_down_ratio": up_down
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取市场统计失败: {str(e)}")
