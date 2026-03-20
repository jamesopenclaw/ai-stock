"""
决策分析 API - 卖点与完整决策
"""
from fastapi import APIRouter, Query, Body
from typing import Optional
from datetime import datetime

from app.models.schemas import (
    AccountInput,
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

router = APIRouter()


# 模拟账户数据（实际从账户系统获取）
MOCK_ACCOUNT = AccountInput(
    total_asset=1000000,
    available_cash=400000,
    total_position_ratio=0.6,
    holding_count=4,
    today_new_buy_count=1,
    t1_locked_positions=[]
)

# 模拟持仓（实际从账户系统获取）
MOCK_HOLDINGS = [
    {
        "ts_code": "000001.SZ",
        "stock_name": "平安银行",
        "holding_qty": 10000,
        "cost_price": 12.0,
        "market_price": 12.5,
        "pnl_pct": 4.17,
        "holding_market_value": 125000,
        "buy_date": "2026-03-18",
        "can_sell_today": True,
        "holding_reason": "银行板块反弹"
    },
    {
        "ts_code": "600519.SH",
        "stock_name": "贵州茅台",
        "holding_qty": 100,
        "cost_price": 1800.0,
        "market_price": 1850.0,
        "pnl_pct": 2.78,
        "holding_market_value": 185000,
        "buy_date": "2026-03-17",
        "can_sell_today": True,
        "holding_reason": "白酒龙头"
    },
    {
        "ts_code": "300750.SZ",
        "stock_name": "宁德时代",
        "holding_qty": 500,
        "cost_price": 190.0,
        "market_price": 185.0,
        "pnl_pct": -2.63,
        "holding_market_value": 92500,
        "buy_date": "2026-03-19",
        "can_sell_today": False,
        "holding_reason": "新能源反弹"
    },
]


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
        # 获取持仓（模拟，实际从账户系统获取）
        from app.models.schemas import AccountPosition
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]

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


@router.get("/account/profile", response_model=ApiResponse)
async def get_account_profile(
) -> ApiResponse:
    """
    获取账户概况
    """
    try:
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings)

        return ApiResponse(
            data=profile.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败: {str(e)}")


@router.get("/account/positions", response_model=ApiResponse)
async def get_positions(
    trade_date: Optional[str] = Query(None, description="交易日，格式YYYY-MM-DD，默认今天")
) -> ApiResponse:
    """
    获取持仓明细
    """
    try:
        from app.models.schemas import AccountPosition
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]

        return ApiResponse(
            data={
                "trade_date": trade_date or datetime.now().strftime("%Y-%m-%d"),
                "positions": [h.model_dump() for h in holdings],
                "total": len(holdings)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取持仓明细失败: {str(e)}")


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

        # 获取账户适配
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]
        account_output = account_adapter_service.adapt(trade_date, MOCK_ACCOUNT, holdings)

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
        stock_pools = stock_filter_service.classify_pools(trade_date, stocks, MOCK_HOLDINGS)

        # 4. 买点分析
        buy_analysis = buy_point_service.analyze(trade_date, stocks)

        # 5. 卖点分析
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]
        sell_analysis = sell_point_service.analyze(trade_date, holdings)

        # 6. 账户适配
        account_fit = account_adapter_service.adapt(trade_date, MOCK_ACCOUNT, holdings)

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
