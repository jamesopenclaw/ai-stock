"""
账户管理 API - PostgreSQL 存储
"""
import copy
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import time
import uuid

from app.models.schemas import (
    AccountInput,
    AccountOutput,
    AccountProfile,
    AccountPosition,
    ApiResponse
)
from app.services.account_adapter import account_adapter_service
from app.data.tushare_client import tushare_client, normalize_ts_code
from app.models.holding import Holding
from app.core.database import async_session_factory
from app.core.security import AuthenticatedAccount, get_current_account
from app.services.account_config_service import (
    get_config as get_account_config_from_db,
    update_config as update_account_config,
)
from app.services.portfolio_service import _safe_float, portfolio_service
from sqlalchemy import select
from loguru import logger

router = APIRouter()
ACCOUNT_OVERVIEW_CACHE_TTL_SECONDS = 20
_account_overview_cache: dict[str, dict] = {}


def _account_overview_cache_key(account_id: str) -> str:
    return str(account_id or "").strip()


def _get_cached_account_overview(account_id: str) -> Optional[dict]:
    cache_key = _account_overview_cache_key(account_id)
    cached = _account_overview_cache.get(cache_key)
    if not cached:
        return None
    if time.monotonic() - float(cached.get("fetched_at") or 0) > ACCOUNT_OVERVIEW_CACHE_TTL_SECONDS:
        _account_overview_cache.pop(cache_key, None)
        return None
    return copy.deepcopy(cached.get("payload"))


def _cache_account_overview(account_id: str, payload: dict) -> None:
    _account_overview_cache[_account_overview_cache_key(account_id)] = {
        "fetched_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }


def _invalidate_account_overview_cache(account_id: str) -> None:
    _account_overview_cache.pop(_account_overview_cache_key(account_id), None)


async def build_account_input(holdings: List[dict], account_id: Optional[str] = None) -> AccountInput:
    """根据实际持仓动态构建账户信息（总资产来自数据库配置）"""
    return await portfolio_service.build_account_input_from_holdings(holdings, account_id=account_id)


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


class AccountConfigUpdateRequest(BaseModel):
    """账户配置更新"""
    total_asset: Optional[float] = Field(None, gt=0, description="总资产(元)")


async def get_stock_name(ts_code: str) -> str:
    """获取股票名称"""
    try:
        detail = tushare_client.get_stock_detail(ts_code, datetime.now().strftime("%Y%m%d"))
        return detail.get("stock_name", ts_code)
    except:
        return ts_code


async def get_holdings_from_db(account_id: str) -> List[dict]:
    """从数据库获取持仓"""
    return await portfolio_service.get_holdings_from_db(account_id=account_id)


async def build_account_overview_payload(current_account: AuthenticatedAccount) -> dict:
    """构建账户页首屏所需的概况、状态和持仓明细。"""
    holdings = await get_holdings_from_db(current_account.id)
    enrich_holdings(holdings)
    account = await build_account_input(holdings, current_account.id)
    holdings_obj = [AccountPosition(**h) for h in holdings]
    profile = account_adapter_service.get_profile(account, holdings_obj)
    account_status = account_adapter_service.adapt(
        datetime.now().strftime("%Y-%m-%d"),
        account,
        holdings_obj,
    )
    total_pnl = sum(_safe_float(h.get("pnl_amount"), 0.0) for h in holdings)
    today_pnl = sum(_safe_float(h.get("today_pnl_amount"), 0.0) for h in holdings)
    profile_payload = profile.model_dump()
    profile_payload.update(
        {
            "total_pnl_amount": round(total_pnl, 2),
            "today_pnl_amount": round(today_pnl, 2),
            "account_id": current_account.id,
            "account_name": current_account.account_name,
            "can_trade": account_status.new_position_allowed,
            "action": account_status.account_action_tag,
            "priority": account_status.priority_action,
        }
    )

    return {
        "profile": profile_payload,
        "status": {
            "account_id": current_account.id,
            "account_name": current_account.account_name,
            "can_trade": account_status.new_position_allowed,
            "action": account_status.account_action_tag,
            "priority": account_status.priority_action,
            "position_ratio": profile.total_position_ratio,
            "available_cash": profile.available_cash,
            "holding_count": profile.holding_count,
        },
        "positions": holdings,
        "total": len(holdings),
    }


async def save_holding_to_db(holding_data: dict) -> dict:
    """保存持仓到数据库"""
    async with async_session_factory() as session:
        holding = Holding(**holding_data)
        session.add(holding)
        await session.commit()
        await session.refresh(holding)
        return holding.to_dict()


async def delete_holding_from_db(account_id: str, ts_code: str) -> bool:
    """从数据库删除持仓"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Holding).where(Holding.account_id == account_id, Holding.ts_code == ts_code)
        )
        holding = result.scalar_one_or_none()
        if holding:
            await session.delete(holding)
            await session.commit()
            return True
        return False


async def update_holding_in_db(account_id: str, ts_code: str, **kwargs) -> Optional[dict]:
    """更新持仓"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Holding).where(Holding.account_id == account_id, Holding.ts_code == ts_code)
        )
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
    """批量刷新持仓现价、昨收（统一复用个股详情链路，支持实时覆盖和交易日回退）"""
    portfolio_service.refresh_holdings_price(holdings)


def enrich_holdings(holdings: List[dict]):
    """补充持股天数、浮盈金额、当日盈亏金额（依赖 refresh_holdings_price 已写入 market_price / pre_close）"""
    portfolio_service.enrich_holdings(holdings)


@router.get("/config", response_model=ApiResponse)
async def get_account_config(
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取账户配置（总资产等）"""
    try:
        data = await get_account_config_from_db(account_id=current_account.id)
        return ApiResponse(data=data)
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户配置失败：{str(e)}")


@router.put("/config", response_model=ApiResponse)
async def put_account_config(
    request: AccountConfigUpdateRequest,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """更新账户配置"""
    try:
        data = await update_account_config(request.model_dump(), account_id=current_account.id)
        _invalidate_account_overview_cache(current_account.id)
        return ApiResponse(data=data)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"更新账户配置失败：{str(e)}")


@router.get("/profile", response_model=ApiResponse)
async def get_profile(
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取账户概况"""
    try:
        payload = await build_account_overview_payload(current_account)
        return ApiResponse(data=payload["profile"])
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败：{str(e)}")


@router.get("/overview", response_model=ApiResponse)
async def get_overview(
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取账户页首屏所需的概况、状态和持仓明细。"""
    try:
        cached_payload = _get_cached_account_overview(current_account.id)
        if cached_payload is not None:
            return ApiResponse(data=cached_payload)
        payload = await build_account_overview_payload(current_account)
        _cache_account_overview(current_account.id, payload)
        return ApiResponse(data=payload)
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户总览失败：{str(e)}")


@router.get("/positions", response_model=ApiResponse)
async def get_positions(
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取持仓明细"""
    try:
        holdings = await get_holdings_from_db(current_account.id)
        return ApiResponse(data={"positions": holdings, "total": len(holdings)})
    except Exception as e:
        return ApiResponse(code=500, message=f"获取持仓明细失败：{str(e)}")


@router.post("/positions", response_model=ApiResponse)
async def add_position(
    request: AddPositionRequest,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """新增持仓"""
    try:
        # 标准化股票代码
        ts_code = normalize_ts_code(request.ts_code)
        
        # 获取股票名称
        stock_name = await get_stock_name(ts_code)

        # 获取现价（统一复用个股详情链路，支持实时覆盖和交易日回退）
        market_price = request.cost_price
        try:
            detail = tushare_client.get_stock_detail(ts_code, datetime.now().strftime("%Y%m%d"))
            price = _safe_float(detail.get("close"), 0.0)
            if price > 0:
                market_price = price
            if detail.get("stock_name"):
                stock_name = detail["stock_name"]
        except Exception as e:
            logger.warning(f"获取 {ts_code} 现价失败，使用成本价: {e}")
        
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
            "account_id": current_account.id,
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
        _invalidate_account_overview_cache(current_account.id)
        
        return ApiResponse(data={"message": "持仓添加成功", "position": saved_holding})
    except Exception as e:
        return ApiResponse(code=500, message=f"添加持仓失败：{str(e)}")


@router.put("/positions/{ts_code}", response_model=ApiResponse)
async def update_position(
    ts_code: str,
    request: UpdatePositionRequest,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """修改持仓（数量、成本价、买入理由等）"""
    try:
        ts_code = normalize_ts_code(ts_code)

        payload = request.model_dump(exclude_unset=True)
        if not payload:
            return ApiResponse(code=400, message="请至少修改一项")

        # 更新数据库
        updated = await update_holding_in_db(current_account.id, ts_code, **payload)

        if updated:
            # 与 GET 持仓一致：按当日行情刷新现价、盈亏、市值
            refresh_holdings_price([updated])
            enrich_holdings([updated])
            _invalidate_account_overview_cache(current_account.id)
            return ApiResponse(data={"message": "持仓更新成功", "position": updated})
        else:
            return ApiResponse(code=404, message="持仓不存在")
    except Exception as e:
        return ApiResponse(code=500, message=f"更新持仓失败：{str(e)}")


@router.delete("/positions/{position_id}", response_model=ApiResponse)
async def delete_position(
    position_id: str,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """删除持仓（按 id）"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Holding).where(
                    Holding.id == position_id,
                    Holding.account_id == current_account.id,
                )
            )
            holding = result.scalar_one_or_none()
            if holding:
                await session.delete(holding)
                await session.commit()
                _invalidate_account_overview_cache(current_account.id)
                return ApiResponse(data={"message": "持仓删除成功"})
            else:
                return ApiResponse(code=404, message="持仓不存在")
    except Exception as e:
        return ApiResponse(code=500, message=f"删除持仓失败：{str(e)}")


@router.post("/adapt", response_model=ApiResponse)
async def adapt_account(
    trade_date: str = Body(..., description="交易日"),
    account: Optional[AccountInput] = Body(None, description="账户信息"),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """账户适配分析"""
    try:
        holdings = await get_holdings_from_db(current_account.id)
        account = account or await build_account_input(holdings, current_account.id)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        result = account_adapter_service.adapt(trade_date, account, holdings_obj)
        return ApiResponse(data=result.model_dump())
    except Exception as e:
        return ApiResponse(code=500, message=f"账户适配分析失败：{str(e)}")


@router.get("/status", response_model=ApiResponse)
async def get_account_status(
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取账户状态快速检查"""
    try:
        payload = await build_account_overview_payload(current_account)
        return ApiResponse(data=payload["status"])
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户状态失败：{str(e)}")
