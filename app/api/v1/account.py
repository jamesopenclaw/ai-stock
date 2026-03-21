"""
账户管理 API
"""
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid
import json
from pathlib import Path

from app.models.schemas import (
    AccountInput,
    AccountOutput,
    AccountProfile,
    AccountPosition,
    ApiResponse
)
from app.services.account_adapter import account_adapter_service
from app.data.tushare_client import tushare_client

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

# 持仓数据存储文件（备用）
HOLDINGS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "holdings.json"
HOLDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

# 数据库可用标志
DB_AVAILABLE = False

try:
    from app.models.holding import Holding
    from app.core.database import async_session_factory
    
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
            return holding.to_dict()
    
    async def delete_holding_from_db(holding_id: str):
        """从数据库删除持仓"""
        async with async_session_factory() as session:
            from sqlalchemy import delete
            await session.execute(delete(Holding).where(Holding.id == holding_id))
            await session.commit()
    
    async def update_holding_in_db(holding_id: str, **kwargs):
        """更新持仓"""
        async with async_session_factory() as session:
            from sqlalchemy import update
            await session.execute(update(Holding).where(Holding.id == holding_id).values(**kwargs))
            await session.commit()
    
    async def create_tables():
        """创建数据库表"""
        from app.core.database import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    DB_AVAILABLE = True
except Exception as e:
    print(f"数据库不可用，将使用文件存储: {e}")


def load_holdings_from_file() -> List[dict]:
    """从文件加载持仓"""
    if HOLDINGS_FILE.exists():
        try:
            with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data:
                    return data
        except Exception as e:
            print(f"加载文件失败: {e}")
    return []


def save_holdings_to_file(holdings: List[dict]):
    """保存持仓到文件"""
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)


class AddPositionRequest(BaseModel):
    """新增持仓请求"""
    ts_code: str = Body(..., description="股票代码，如 000001.SZ")
    holding_qty: int = Body(..., description="持仓数量")
    cost_price: float = Body(..., description="持仓成本价")
    buy_date: str = Body(..., description="买入日期，格式 YYYY-MM-DD")
    holding_reason: Optional[str] = Body(None, description="买入理由")


async def refresh_holdings_prices():
    """刷新持仓现价和盈亏"""
    if DB_AVAILABLE:
        try:
            holdings = await get_holdings_from_db()
        except Exception as e:
            print(f"数据库获取失败，使用文件: {e}")
            holdings = load_holdings_from_file()
    else:
        holdings = load_holdings_from_file()
    
    if not holdings:
        return []
    
    trade_date = datetime.now().strftime("%Y%m%d")
    price_updated = False
    
    for h in holdings:
        try:
            detail = tushare_client.get_stock_detail(h["ts_code"], trade_date)
            if detail and detail.get("close"):
                h["market_price"] = detail.get("close")
                if h.get("cost_price") and h.get("market_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                buy_date = datetime.strptime(h["buy_date"], "%Y-%m-%d")
                today = datetime.now()
                h["can_sell_today"] = (today - buy_date).days > 0
                price_updated = True
                
                # 更新数据库/文件
                if DB_AVAILABLE:
                    try:
                        await update_holding_in_db(
                            h["id"],
                            market_price=h["market_price"],
                            pnl_pct=h["pnl_pct"],
                            holding_market_value=h["holding_market_value"],
                            can_sell_today=h["can_sell_today"]
                        )
                    except Exception as e:
                        print(f"数据库更新失败: {e}")
        except Exception as e:
            print(f"刷新价格失败: {h['ts_code']}, {e}")
    
    # 如果数据库不可用，保存到文件
    if not DB_AVAILABLE and price_updated:
        save_holdings_to_file(holdings)
    
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
        ts_code = request.ts_code.upper().strip()
        if not ts_code.endswith(('.SH', '.SZ')):
            ts_code += '.SH' if ts_code.startswith('6') else '.SZ'

        trade_date = datetime.now().strftime("%Y%m%d")
        detail = tushare_client.get_stock_detail(ts_code, trade_date)
        stock_name = detail.get("stock_name", ts_code) if detail else ts_code
        market_price = detail.get("close", request.cost_price) if detail else request.cost_price

        new_id = str(uuid.uuid4())
        holding_market_value = request.holding_qty * market_price
        pnl_pct = round((market_price - request.cost_price) / request.cost_price * 100, 2) if request.cost_price else 0

        buy_date = datetime.strptime(request.buy_date, "%Y-%m-%d")
        today = datetime.now()
        can_sell_today = (today - buy_date).days > 0

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

        if DB_AVAILABLE:
            try:
                await save_holding_to_db(new_holding)
            except Exception as e:
                print(f"数据库保存失败: {e}")
                # 回退到文件
                holdings = load_holdings_from_file()
                holdings.append(new_holding)
                save_holdings_to_file(holdings)
        else:
            holdings = load_holdings_from_file()
            holdings.append(new_holding)
            save_holdings_to_file(holdings)

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
        if DB_AVAILABLE:
            try:
                await delete_holding_from_db(position_id)
            except Exception as e:
                print(f"数据库删除失败: {e}")
                holdings = load_holdings_from_file()
                holdings = [h for h in holdings if h.get("id") != position_id]
                save_holdings_to_file(holdings)
        else:
            holdings = load_holdings_from_file()
            holdings = [h for h in holdings if h.get("id") != position_id]
            save_holdings_to_file(holdings)

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
        if DB_AVAILABLE:
            holdings = await get_holdings_from_db()
        else:
            holdings = load_holdings_from_file()
        
        found = False
        for h in holdings:
            if h.get("id") == position_id:
                found = True
                if holding_qty is not None:
                    h["holding_qty"] = holding_qty
                if cost_price is not None:
                    h["cost_price"] = cost_price
                if holding_reason is not None:
                    h["holding_reason"] = holding_reason
                
                if h.get("market_price") and h.get("cost_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                if h.get("holding_qty") and h.get("market_price"):
                    h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                break
        
        if not found:
            return ApiResponse(code=404, message="持仓不存在")
        
        if DB_AVAILABLE:
            try:
                await update_holding_in_db(position_id, holding_qty=holding_qty, cost_price=cost_price, holding_reason=holding_reason)
            except Exception as e:
                save_holdings_to_file(holdings)
        else:
            save_holdings_to_file(holdings)

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
