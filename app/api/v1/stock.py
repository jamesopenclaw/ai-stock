"""
个股筛选 API
"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
import logging

from app.models.schemas import (
    ApiResponse,
    StockCheckupTarget,
)
from app.services.stock_filter import (
    stock_filter_service,
)
from app.services.decision_context import decision_context_service
from app.services.sell_point import sell_point_service
from app.services.llm_explainer import llm_explainer_service
from app.services.stock_checkup import stock_checkup_service
from app.services.buy_point_sop import buy_point_sop_service
from app.services.sell_point_sop import sell_point_sop_service
from app.services.review_snapshot import review_snapshot_service
from app.data.tushare_client import tushare_client

router = APIRouter()
logger = logging.getLogger(__name__)


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
    limit: int = Query(100, description="候选股数量限制", ge=1, le=500),
    force_llm_refresh: bool = Query(False, description="是否强制刷新 LLM 解读缓存"),
) -> ApiResponse:
    """
    三池分类

    返回：
    - market_watch_pool: 市场最强观察池
    - trend_recognition_pool: 趋势辨识度观察池
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
        result.resolved_trade_date = context.resolved_stock_trade_date
        sell_analysis = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
        )
        result = stock_filter_service.attach_sell_analysis(result, sell_analysis)
        try:
            await review_snapshot_service.save_analysis_snapshot(trade_date, stock_pools=result)
        except Exception as exc:
            logger.warning("三池页快照写入失败: %s", exc)
        llm_summary, llm_status = await llm_explainer_service.summarize_stock_pools_with_status(
            result,
            context.market_env,
            force_refresh=force_llm_refresh,
            allow_live_request=force_llm_refresh,
        )

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "resolved_trade_date": result.resolved_trade_date,
                "market_watch_pool": [s.model_dump() for s in result.market_watch_pool],
                "trend_recognition_pool": [s.model_dump() for s in result.trend_recognition_pool],
                "account_executable_pool": [s.model_dump() for s in result.account_executable_pool],
                "holding_process_pool": [s.model_dump() for s in result.holding_process_pool],
                "total_count": result.total_count,
                "llm_summary": llm_summary.model_dump() if llm_summary else None,
                "llm_status": llm_status.model_dump(),
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


@router.get("/checkup/{ts_code}", response_model=ApiResponse)
async def get_stock_checkup(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    checkup_target: StockCheckupTarget = Query(
        StockCheckupTarget.OBSERVE,
        description="体检目标：观察型 / 持仓型 / 交易型",
    ),
    force_llm_refresh: bool = Query(False, description="是否强制刷新 LLM 缓存"),
) -> ApiResponse:
    """获取单只股票的全面体检结果。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await stock_checkup_service.checkup(
            ts_code,
            trade_date,
            checkup_target,
            force_llm_refresh=force_llm_refresh,
        )
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取个股体检失败: {str(e)}")


@router.get("/buy-analysis/{ts_code}", response_model=ApiResponse)
async def get_stock_buy_analysis(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
) -> ApiResponse:
    """获取单只股票的详细买点 SOP 分析。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await buy_point_sop_service.analyze(ts_code, trade_date)
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取买点分析失败: {str(e)}")


@router.get("/sell-analysis/{ts_code}", response_model=ApiResponse)
async def get_stock_sell_analysis(
    ts_code: str,
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
) -> ApiResponse:
    """获取单只持仓的详细卖点 SOP 分析。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        result = await sell_point_sop_service.analyze(ts_code, trade_date)
        return ApiResponse(data=result.model_dump(mode="json"))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取卖点分析失败: {str(e)}")
