"""
账户管理 API - PostgreSQL 存储
"""
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from app.models.schemas import (
    AccountInput,
    AccountOutput,
    AccountProfile,
    AccountPosition,
    ApiResponse
)
from app.services.account_adapter import account_adapter_service
from app.data.tushare_client import tushare_client
from app.models.holding import Holding
from app.core.database import async_session_factory

router = APIRouter()

# 模拟账户数据
MOCK_ACCOUNT = AccountInput(
    total_asset=1000000,
    available_cash=400000,
    total_position_ratio=0.6,
    holding_count=4,
    today_new_buy_count=1,
    t1_locked_positions=[]
)


async def init_db():
    """初始化数据库表"""
    try:
        from app.core.database import engine
        from app.core.database import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("数据库表初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {e}")


async def get_holdings_from_db() -> List[dict]:
    """从数据库获取持仓"""
    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(Holding))
        holdings = result.scalars().all()
        return [h.to_dict() for h in holdings]


async def save_holding_to_db(holding_data: dict) -> dict:
    """保存持仓到数据库"""
    async with async_session_factory() as session:
        holding = Holding(**holding_data)
        session.add(holding)
        await session.commit()
        # 刷新获取完整数据
        await session.refresh(holding)
        return holding.to_dict()


async def delete_holding_from_db(holding_id: str):
    """从数据库删除持仓"""
    async with async_session_factory() as session:
        from sqlalchemy import delete, select
        result = await session.execute(select(Holding).where(Holding.id == holding_id))
        holding = result.scalar_one_or_none()
        if holding:
            await session.delete(holding)
            await session.commit()


async def update_holding_in_db(holding_id: str, **kwargs):
    """更新持仓"""
    async with async_session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(Holding).where(Holding.id == holding_id).values(**kwargs)
        )
        await session.commit()


class AddPositionRequest(BaseModel):
    """新增持仓请求"""
    ts_code: str = Body(..., description="股票代码，如 000001.SZ")
    holding_qty: int = Body(..., description="持仓数量")
    cost_price: float = Body(..., description="持仓成本价")
    buy_date: str = Body(..., description="买入日期，格式 YYYY-MM-DD")
    holding_reason: Optional[str] = Body(None, description="买入理由")


# 数据库初始化（在应用启动时调用）


async def refresh_holdings_prices():
    """刷新持仓现价和盈亏"""
    holdings = await get_holdings_from_db()
    
    if not holdings:
        return []
    
    trade_date = datetime.now().strftime("%Y%m%d")
    
    for h in holdings:
        try:
            detail = tushare_client.get_stock_detail(h["ts_code"], trade_date)
            if detail and detail.get("close"):
                market_price = detail.get("close")
                pnl_pct = round((market_price - h["cost_price"]) / h["cost_price"] * 100, 2) if h.get("cost_price") else 0
                holding_market_value = h["holding_qty"] * market_price
                
                buy_date = datetime.strptime(h["buy_date"], "%Y-%m-%d")
                today = datetime.now()
                can_sell_today = (today - buy_date).days > 0
                
                # 更新数据库
                await update_holding_in_db(
                    h["id"],
                    market_price=market_price,
                    pnl_pct=pnl_pct,
                    holding_market_value=holding_market_value,
                    can_sell_today=can_sell_today
                )
                
                # 更新内存数据
                h["market_price"] = market_price
                h["pnl_pct"] = pnl_pct
                h["holding_market_value"] = holding_market_value
                h["can_sell_today"] = can_sell_today
                
        except Exception as e:
            print(f"刷新价格失败: {h['ts_code']}, {e}")
    
    return holdings


@router.get("/profile", response_model=ApiResponse)
async def get_profile() -> ApiResponse:
    """获取账户概况"""
    try:
        holdings = await refresh_holdings_prices()
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings_obj)

        return ApiResponse(
            data=profile.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败: {str(e)}")


@router.get("/positions", response_model=ApiResponse)
async def get_positions() -> ApiResponse:
    """获取持仓明细"""
    try:
        holdings = await refresh_holdings_prices()

        return ApiResponse(
            data={
                "positions": holdings,
                "total": len(holdings)
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"获取持仓明细失败: {str(e)}")


@router.post("/positions", response_model=ApiResponse)
async def add_position(request: AddPositionRequest) -> ApiResponse:
    """新增持仓"""
    try:
        # 标准化股票代码
        ts_code = request.ts_code.upper().strip()
        if not ts_code.endswith(('.SH', '.SZ')):
            ts_code += '.SH' if ts_code.startswith('6') else '.SZ'

        # 获取股票名称和现价
        trade_date = datetime.now().strftime("%Y%m%d")
        detail = tushare_client.get_stock_detail(ts_code, trade_date)
        stock_name = detail.get("stock_name", ts_code) if detail else ts_code
        market_price = detail.get("close", request.cost_price) if detail else request.cost_price

        # 生成 ID
        new_id = str(uuid.uuid4())

        # 计算市值和盈亏
        holding_market_value = request.holding_qty * market_price
        pnl_pct = round((market_price - request.cost_price) / request.cost_price * 100, 2) if request.cost_price else 0

        # T+1 判断
        buy_date = datetime.strptime(request.buy_date, "%Y-%m-%d")
        today = datetime.now()
        can_sell_today = (today - buy_date).days > 0

        # 保存到数据库
        new_holding = {
            "id": new_id,
            "ts_code": ts_code,
            "stock_name": stock_name,
            "holding_qty": request.holding_qty,
            "cost_price": request.cost_price,
            "market_price": market_price,
            "pnl_pct": pnl_pct,
            "holding_market_value": holding_market_value,
            "buy_date": request.buy_date,
            "can_sell_today": can_sell_today,
            "holding_reason": request.holding_reason or ""
        }

        await save_holding_to_db(new_holding)

        return ApiResponse(
            data={
                "message": "持仓添加成功",
                "position": new_holding
            }
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"添加持仓失败: {str(e)}")


@router.delete("/positions/{position_id}", response_model=ApiResponse)
async def delete_position(position_id: str) -> ApiResponse:
    """删除持仓"""
    try:
        await delete_holding_from_db(position_id)
        return ApiResponse(
            data={"message": "持仓删除成功"}
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"删除持仓失败: {str(e)}")


@router.put("/positions/{position_id}", response_model=ApiResponse)
async def update_position(
    position_id: str,
    holding_qty: Optional[int] = Body(None, description="持仓数量"),
    cost_price: Optional[float] = Body(None, description="持仓成本价"),
    holding_reason: Optional[str] = Body(None, description="买入理由")
) -> ApiResponse:
    """更新持仓"""
    try:
        # 先获取现有数据
        holdings = await get_holdings_from_db()
        holding = next((h for h in holdings if h.get("id") == position_id), None)
        
        if not holding:
            return ApiResponse(code=404, message="持仓不存在")
        
        # 更新字段
        update_data = {}
        if holding_qty is not None:
            update_data["holding_qty"] = holding_qty
        if cost_price is not None:
            update_data["cost_price"] = cost_price
        if holding_reason is not None:
            update_data["holding_reason"] = holding_reason
        
        # 如果更新了成本或数量，重新计算
        if holding_qty is not None or cost_price is not None:
            qty = holding_qty if holding_qty is not None else holding.get("holding_qty")
            cost = cost_price if cost_price is not None else holding.get("cost_price")
            market = holding.get("market_price", 0)
            
            update_data["pnl_pct"] = round((market - cost) / cost * 100, 2) if cost else 0
            update_data["holding_market_value"] = qty * market
        
        await update_holding_in_db(position_id, **update_data)

        return ApiResponse(
            data={"message": "持仓更新成功"}
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"更新持仓失败: {str(e)}")


@router.post("/adapt", response_model=ApiResponse)
async def adapt_account(
    trade_date: str = Body(..., description="交易日"),
    account: Optional[AccountInput] = Body(None, description="账户信息，为空则使用默认")
) -> ApiResponse:
    """账户适配分析"""
    try:
        account = account or MOCK_ACCOUNT
        holdings = await refresh_holdings_prices()
        holdings_obj = [AccountPosition(**h) for h in holdings]

        result = account_adapter_service.adapt(trade_date, account, holdings_obj)

        return ApiResponse(
            data=result.model_dump()
        )
    except Exception as e:
        return ApiResponse(code=500, message=f"账户适配分析失败: {str(e)}")


@router.get("/status", response_model=ApiResponse)
async def get_account_status() -> ApiResponse:
    """获取账户状态快速检查"""
    try:
        holdings = await refresh_holdings_prices()
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings_obj)
        result = account_adapter_service.adapt("2026-03-21", MOCK_ACCOUNT, holdings_obj)

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
