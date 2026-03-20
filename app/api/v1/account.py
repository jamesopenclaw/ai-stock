"""
账户管理 API
"""
from fastapi import APIRouter, Body
from typing import Optional

from app.models.schemas import (
    AccountInput,
    AccountOutput,
    AccountProfile,
    AccountPosition,
    ApiResponse
)
from app.services.account_adapter import account_adapter_service

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


@router.get("/profile", response_model=ApiResponse)
async def get_profile() -> ApiResponse:
    """
    获取账户概况

    返回账户基本信息和持仓统计
    """
    try:
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings)

        return ApiResponse(
            data=profile.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败: {str(e)}")


@router.get("/positions", response_model=ApiResponse)
async def get_positions() -> ApiResponse:
    """
    获取持仓明细

    返回当前所有持仓的详细信息
    """
    try:
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]

        return ApiResponse(
            data={
                "positions": [h.model_dump() for h in holdings],
                "total": len(holdings)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取持仓明细失败: {str(e)}")


@router.post("/adapt", response_model=ApiResponse)
async def adapt_account(
    trade_date: str = Body(..., description="交易日"),
    account: Optional[AccountInput] = Body(None, description="账户信息，为空则使用默认")
) -> ApiResponse:
    """
    账户适配分析

    根据市场环境和账户状态，判断是否适合新开仓
    """
    try:
        account = account or MOCK_ACCOUNT
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]

        result = account_adapter_service.adapt(trade_date, account, holdings)

        return ApiResponse(
            data=result.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"账户适配分析失败: {str(e)}")


@router.get("/status", response_model=ApiResponse)
async def get_account_status() -> ApiResponse:
    """
    获取账户状态快速检查

    返回账户是否可以交易的快速判断
    """
    try:
        holdings = [AccountPosition(**h) for h in MOCK_HOLDINGS]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings)
        result = account_adapter_service.adapt("2026-03-20", MOCK_ACCOUNT, holdings)

        return ApiResponse(
            data={
                "can_trade": result.new_position_allowed,
                "action": result.account_action_tag,
                "priority": result.priority_action,
                "position_ratio": profile.total_position_ratio,
                "available_cash": profile.available_cash,
                "holding_count": profile.holding_count
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户状态失败: {str(e)}")
