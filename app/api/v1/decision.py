"""
决策分析 API - 卖点与完整决策
"""
from fastapi import APIRouter, Query, Body
from typing import Optional
from datetime import datetime

from app.models.schemas import (
    AccountInput,
    AccountPosition,
    SellPointResponse,
    FullDecisionResponse,
    DecisionSummary,
    ApiResponse
)
from app.services.sell_point import sell_point_service
from app.services.account_adapter import account_adapter_service
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service
from app.services.buy_point import buy_point_service
from app.data.tushare_client import tushare_client
from app.models.schemas import StockInput
from app.models.holding import Holding
from app.core.database import async_session_factory
from sqlalchemy import select

router = APIRouter()


async def get_holdings_from_db() -> list:
    """从数据库获取持仓"""
    from app.data.tushare_client import tushare_client
    
    async with async_session_factory() as session:
        result = await session.execute(select(Holding))
        holdings = result.scalars().all()
        holdings_list = [h.to_dict() for h in holdings]
        
        # 刷新现价
        for h in holdings_list:
            try:
                detail = tushare_client.get_stock_detail(h["ts_code"], datetime.now().strftime("%Y%m%d"))
                if detail and detail.get("close"):
                    h["market_price"] = detail.get("close")
                    if h.get("cost_price"):
                        h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                    if h.get("holding_qty"):
                        h["holding_market_value"] = h["holding_qty"] * h["market_price"]
            except:
                pass
        
        return holdings_list


def refresh_holdings_price(holdings: list):
    """刷新持仓现价（内存中）"""
    from app.data.tushare_client import tushare_client
    for h in holdings:
        try:
            detail = tushare_client.get_stock_detail(h["ts_code"], datetime.now().strftime("%Y%m%d"))
            if detail and detail.get("close"):
                h["market_price"] = detail.get("close")
                if h.get("cost_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                if h.get("holding_qty"):
                    h["holding_market_value"] = h["holding_qty"] * h["market_price"]
        except:
            pass


@router.get("/sell-point", response_model=ApiResponse)
async def analyze_sell_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
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
        # 从数据库获取持仓
        holdings_list = await get_holdings_from_db()
        holdings = [AccountPosition(**h) for h in holdings_list]

        # 卖点分析
        result = sell_point_service.analyze(trade_date, holdings)

        return ApiResponse(
            data={
                "trade_date": result.trade_date,
                "hold_positions": [p.model_dump() for p in result.hold_positions],
                "reduce_positions": [p.model_dump() for p in result.reduce_positions],
                "sell_positions": [p.model_dump() for p in result.sell_positions],
                "total_count": result.total_count
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"卖点分析失败: {str(e)}")


@router.get("/summary", response_model=ApiResponse)
async def get_decision_summary(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
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
        # 获取市场环境
        market_env = market_env_service.get_current_env(trade_date)

        # 从数据库获取持仓
        holdings_list = await get_holdings_from_db()
        holdings = [AccountPosition(**h) for h in holdings_list]
        
        # 获取账户信息
        from app.core.config import settings
        account = AccountInput(
            total_asset=settings.qingzhou_total_asset,
            available_cash=settings.qingzhou_available_cash,
            total_position_ratio=settings.qingzhou_total_position_ratio,
            holding_count=len(holdings),
            today_new_buy_count=0
        )
        account_output = account_adapter_service.adapt(trade_date, account, holdings)

        # 生成摘要
        summary = _generate_summary(
            trade_date,
            market_env,
            account_output,
            holdings
        )

        return ApiResponse(
            data=summary.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取执行摘要失败: {str(e)}")


@router.get("/buy-point", response_model=ApiResponse)
async def analyze_buy_point(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天"),
    limit: int = Query(20, description="返回数量限制", ge=1, le=100),
) -> ApiResponse:
    """
    买点分析

    返回当日可买/观察/不买的候选个股列表
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        stock_list = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=limit)
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
        result = buy_point_service.analyze(trade_date, stocks)

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
) -> ApiResponse:
    """
    完整决策分析

    综合市场环境、板块扫描、买点分析、卖点分析、账户适配，输出完整决策建议
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 1. 市场环境
        market_env = market_env_service.get_current_env(trade_date)

        # 2. 板块扫描
        sector_scan = sector_scan_service.scan(trade_date)

        # 3. 个股筛选/三池
        stock_list = tushare_client.get_stock_list(trade_date.replace("-", ""), limit=50)
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
        # 从数据库获取持仓
        holdings_list = await get_holdings_from_db()
        holdings = [AccountPosition(**h) for h in holdings_list]
        
        # 获取账户信息
        from app.core.config import settings
        account = AccountInput(
            total_asset=settings.qingzhou_total_asset,
            available_cash=settings.qingzhou_available_cash,
            total_position_ratio=settings.qingzhou_total_position_ratio,
            holding_count=len(holdings),
            today_new_buy_count=0
        )
        
        stock_pools = stock_filter_service.classify_pools(trade_date, stocks, holdings_list)

        # 4. 买点分析
        buy_analysis = buy_point_service.analyze(trade_date, stocks)

        # 5. 卖点分析
        sell_analysis = sell_point_service.analyze(trade_date, holdings)

        # 6. 账户适配
        account_fit = account_adapter_service.adapt(trade_date, account, holdings)

        # 7. 执行摘要
        summary = _generate_summary(trade_date, market_env, account_fit, holdings)

        return ApiResponse(
            data={
                "trade_date": trade_date,
                "market_env": {
                    "market_env_tag": market_env.market_env_tag.value,
                    "breakout_allowed": market_env.breakout_allowed,
                    "risk_level": market_env.risk_level.value,
                    "market_comment": market_env.market_comment
                },
                "sector_scan": {
                    "mainline_count": len(sector_scan.mainline_sectors),
                    "sub_mainline_count": len(sector_scan.sub_mainline_sectors),
                },
                "stock_pools": {
                    "market_watch_count": len(stock_pools.market_watch_pool),
                    "account_executable_count": len(stock_pools.account_executable_pool),
                    "holding_process_count": len(stock_pools.holding_process_pool),
                },
                "buy_analysis": {
                    "available_count": len(buy_analysis.available_buy_points),
                    "observe_count": len(buy_analysis.observe_buy_points),
                },
                "sell_analysis": {
                    "hold_count": len(sell_analysis.hold_positions),
                    "reduce_count": len(sell_analysis.reduce_positions),
                    "sell_count": len(sell_analysis.sell_positions),
                },
                "account_fit": account_fit.model_dump(),
                "summary": summary.model_dump()
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"完整决策分析失败: {str(e)}")


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
