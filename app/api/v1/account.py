"""
账户管理 API - PostgreSQL 存储
"""
from fastapi import APIRouter, Body
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
from sqlalchemy import select, delete

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


class AddPositionRequest(BaseModel):
    """新增持仓请求"""
    ts_code: str
    holding_qty: int
    cost_price: float
    buy_date: str
    holding_reason: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    """修改持仓请求"""
    holding_qty: Optional[int] = None
    cost_price: Optional[float] = None
    holding_reason: Optional[str] = None


def normalize_ts_code(ts_code: str) -> str:
    """标准化股票代码"""
    ts_code = ts_code.upper().strip()
    if not ts_code.endswith(('.SH', '.SZ')):
        ts_code += '.SH' if ts_code.startswith('6') else '.SZ'
    return ts_code


async def get_stock_name(ts_code: str) -> str:
    """获取股票名称"""
    try:
        detail = tushare_client.get_stock_detail(ts_code, datetime.now().strftime("%Y%m%d"))
        return detail.get("stock_name", ts_code)
    except:
        return ts_code


async def get_holdings_from_db() -> List[dict]:
    """从数据库获取持仓"""
    async with async_session_factory() as session:
        result = await session.execute(select(Holding))
        holdings = result.scalars().all()
        return [h.to_dict() for h in holdings]


async def save_holding_to_db(holding_data: dict) -> dict:
    """保存持仓到数据库"""
    async with async_session_factory() as session:
        holding = Holding(**holding_data)
        session.add(holding)
        await session.commit()
        await session.refresh(holding)
        return holding.to_dict()


async def delete_holding_from_db(ts_code: str) -> bool:
    """从数据库删除持仓"""
    async with async_session_factory() as session:
        result = await session.execute(select(Holding).where(Holding.ts_code == ts_code))
        holding = result.scalar_one_or_none()
        if holding:
            await session.delete(holding)
            await session.commit()
            return True
        return False


async def update_holding_in_db(ts_code: str, **kwargs) -> Optional[dict]:
    """更新持仓"""
    async with async_session_factory() as session:
        result = await session.execute(select(Holding).where(Holding.ts_code == ts_code))
        holding = result.scalar_one_or_none()
        if holding:
            for key, value in kwargs.items():
                if hasattr(holding, key) and value is not None:
                    setattr(holding, key, value)
            await session.commit()
            await session.refresh(holding)
            return holding.to_dict()
        return None


def refresh_holdings_price(holdings: List[dict]):
    """刷新持仓现价（内存中）"""
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


@router.get("/profile", response_model=ApiResponse)
async def get_profile() -> ApiResponse:
    """获取账户概况"""
    try:
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings_obj)
        return ApiResponse(data=profile.model_dump())
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败：{str(e)}")


@router.get("/positions", response_model=ApiResponse)
async def get_positions() -> ApiResponse:
    """获取持仓明细"""
    try:
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        return ApiResponse(data={"positions": holdings, "total": len(holdings)})
    except Exception as e:
        return ApiResponse(code=500, message=f"获取持仓明细失败：{str(e)}")


@router.post("/positions", response_model=ApiResponse)
async def add_position(request: AddPositionRequest) -> ApiResponse:
    """新增持仓"""
    try:
        # 标准化股票代码
        ts_code = normalize_ts_code(request.ts_code)
        
        # 获取股票名称
        stock_name = await get_stock_name(ts_code)
        
        # 获取现价
        try:
            detail = tushare_client.get_stock_detail(ts_code, datetime.now().strftime("%Y%m%d"))
            market_price = detail.get("close", request.cost_price)
        except:
            market_price = request.cost_price
        
        # 计算市值和盈亏
        holding_market_value = request.holding_qty * market_price
        pnl_pct = round((market_price - request.cost_price) / request.cost_price * 100, 2) if request.cost_price else 0
        
        # T+1 判断
        buy_date = datetime.strptime(request.buy_date, "%Y-%m-%d")
        today = datetime.now()
        can_sell_today = (today - buy_date).days > 0
        
        # 创建持仓数据
        holding_data = {
            "id": str(uuid.uuid4()),
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
        
        # 保存到数据库
        saved_holding = await save_holding_to_db(holding_data)
        
        return ApiResponse(data={"message": "持仓添加成功", "position": saved_holding})
    except Exception as e:
        return ApiResponse(code=500, message=f"添加持仓失败：{str(e)}")


@router.put("/positions/{ts_code}", response_model=ApiResponse)
async def update_position(ts_code: str, request: UpdatePositionRequest) -> ApiResponse:
    """修改持仓"""
    try:
        ts_code = normalize_ts_code(ts_code)
        
        # 更新数据库
        updated = await update_holding_in_db(ts_code, **request.model_dump(exclude_unset=True))
        
        if updated:
            return ApiResponse(data={"message": "持仓更新成功", "position": updated})
        else:
            return ApiResponse(code=404, message="持仓不存在")
    except Exception as e:
        return ApiResponse(code=500, message=f"更新持仓失败：{str(e)}")


@router.delete("/positions/{ts_code}", response_model=ApiResponse)
async def delete_position(ts_code: str) -> ApiResponse:
    """删除持仓"""
    try:
        ts_code = normalize_ts_code(ts_code)
        
        # 从数据库删除
        deleted = await delete_holding_from_db(ts_code)
        
        if deleted:
            return ApiResponse(data={"message": "持仓删除成功"})
        else:
            return ApiResponse(code=404, message="持仓不存在")
    except Exception as e:
        return ApiResponse(code=500, message=f"删除持仓失败：{str(e)}")


@router.post("/adapt", response_model=ApiResponse)
async def adapt_account(
    trade_date: str = Body(..., description="交易日"),
    account: Optional[AccountInput] = Body(None, description="账户信息")
) -> ApiResponse:
    """账户适配分析"""
    try:
        account = account or MOCK_ACCOUNT
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        result = account_adapter_service.adapt(trade_date, account, holdings_obj)
        return ApiResponse(data=result.model_dump())
    except Exception as e:
        return ApiResponse(code=500, message=f"账户适配分析失败：{str(e)}")


@router.get("/status", response_model=ApiResponse)
async def get_account_status() -> ApiResponse:
    """获取账户状态快速检查"""
    try:
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings_obj)
        result = account_adapter_service.adapt("2026-03-21", MOCK_ACCOUNT, holdings_obj)
        
        return ApiResponse(data={
            "can_trade": result.new_position_allowed,
            "action": result.account_action_tag,
            "priority": result.priority_action,
            "position_ratio": profile.total_position_ratio,
            "available_cash": profile.available_cash,
            "holding_count": profile.holding_count
        })
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户状态失败：{str(e)}")
