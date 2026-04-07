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
                "trade_date": trade_date,
                "resolved_trade_date": result.trade_date,
                "market_env_tag": result.market_env_tag.value,
                "market_env_profile": result.market_env_profile,
                "breakout_allowed": result.breakout_allowed,
                "risk_level": result.risk_level.value,
                "market_comment": result.market_comment,
                "market_headline": result.market_headline,
                "market_subheadline": result.market_subheadline,
                "trading_tempo_label": result.trading_tempo_label,
                "dominant_factor_label": result.dominant_factor_label,
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
                "market_env_profile": result.market_env_profile,
                "breakout_allowed": result.breakout_allowed,
                "risk_level": result.risk_level.value,
                "market_comment": result.market_comment,
                "market_headline": result.market_headline,
                "market_subheadline": result.market_subheadline,
                "trading_tempo_label": result.trading_tempo_label,
                "dominant_factor_label": result.dominant_factor_label,
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
        payload = tushare_client.get_index_quote_with_meta(trade_date.replace("-", ""))
        return ApiResponse(
            data={
                "trade_date": trade_date,
                "resolved_trade_date": f"{str(payload.get('data_trade_date'))[:4]}-{str(payload.get('data_trade_date'))[4:6]}-{str(payload.get('data_trade_date'))[6:8]}" if payload.get("data_trade_date") else trade_date,
                "used_mock": bool(payload.get("used_mock")),
                "indexes": payload.get("rows", []),
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
        compact_trade_date = trade_date.replace("-", "")
        stats_payload = tushare_client.get_limit_stats_with_meta(compact_trade_date)
        turnover_payload = tushare_client.get_market_turnover_with_meta(compact_trade_date)
        up_down_payload = tushare_client.get_up_down_ratio_with_meta(compact_trade_date)
        resolved_trade_date = str(
            stats_payload.get("data_trade_date")
            or turnover_payload.get("data_trade_date")
            or up_down_payload.get("data_trade_date")
            or compact_trade_date
        )

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "resolved_trade_date": f"{resolved_trade_date[:4]}-{resolved_trade_date[4:6]}-{resolved_trade_date[6:8]}",
                "used_mock": bool(stats_payload.get("used_mock") or turnover_payload.get("used_mock") or up_down_payload.get("used_mock")),
                "limit_up_count": stats_payload.get("stats", {}).get("limit_up_count", 0),
                "limit_down_count": stats_payload.get("stats", {}).get("limit_down_count", 0),
                "broken_board_rate": stats_payload.get("stats", {}).get("broken_board_rate", 0),
                "market_turnover": turnover_payload.get("market_turnover", 0),
                "up_down_ratio": up_down_payload.get("up_down_ratio", {}),
                "limit_stats_data_source": stats_payload.get("data_source", "limit_list_d"),
                "limit_stats_quote_time": stats_payload.get("quote_time"),
                "turnover_data_source": turnover_payload.get("data_source", "index_daily"),
                "turnover_quote_time": turnover_payload.get("quote_time"),
                "up_down_data_source": up_down_payload.get("data_source", "daily"),
                "up_down_quote_time": up_down_payload.get("quote_time"),
                "realtime_status": (
                    stats_payload.get("status")
                    or turnover_payload.get("status")
                    or up_down_payload.get("status")
                    or "stable"
                ),
                "realtime_is_stale": bool(
                    stats_payload.get("is_stale")
                    or turnover_payload.get("is_stale")
                    or up_down_payload.get("is_stale")
                ),
                "realtime_stale_from_quote_time": (
                    stats_payload.get("stale_from_quote_time")
                    or turnover_payload.get("stale_from_quote_time")
                    or up_down_payload.get("stale_from_quote_time")
                ),
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取市场统计失败: {str(e)}")
