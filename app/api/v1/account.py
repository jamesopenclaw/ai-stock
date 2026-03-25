"""
账户管理 API - PostgreSQL 存储
"""
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
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
from app.data.tushare_client import tushare_client, normalize_ts_code
from app.models.holding import Holding
from app.core.database import async_session_factory
from app.services.account_config_service import (
    get_total_asset,
    get_config as get_account_config_from_db,
    update_config as update_account_config,
)
from sqlalchemy import select
from loguru import logger

router = APIRouter()


async def build_account_input(holdings: List[dict]) -> AccountInput:
    """根据实际持仓动态构建账户信息（总资产来自数据库配置）"""
    market_value = sum(
        h.get("holding_market_value") or (h.get("holding_qty", 0) * h.get("market_price", 0))
        for h in holdings
    )
    total_asset = await get_total_asset()
    available_cash = max(total_asset - market_value, 0)
    total_position_ratio = market_value / total_asset if total_asset > 0 else 0
    holding_count = len(holdings)

    return AccountInput(
        total_asset=total_asset,
        available_cash=available_cash,
        total_position_ratio=round(total_position_ratio, 4),
        holding_count=holding_count,
        today_new_buy_count=0,
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


class AccountConfigUpdateRequest(BaseModel):
    """账户配置更新"""
    total_asset: Optional[float] = Field(None, gt=0, description="总资产(元)")
    llm_enabled: Optional[bool] = Field(None, description="是否启用 LLM 辅助层")
    llm_provider: Optional[str] = Field(None, description="LLM 供应商")
    llm_base_url: Optional[str] = Field(None, description="LLM Base URL")
    llm_api_key: Optional[str] = Field(None, description="LLM API Key，留空则保持不变")
    clear_llm_api_key: Optional[bool] = Field(None, description="是否清空已保存的 API Key")
    llm_model: Optional[str] = Field(None, description="LLM 模型名")
    llm_timeout_seconds: Optional[float] = Field(None, gt=0, description="LLM 超时秒数")
    llm_temperature: Optional[float] = Field(None, ge=0, le=2, description="LLM 温度")
    llm_max_input_items: Optional[int] = Field(None, ge=1, le=20, description="单次最大输入条数")


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


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        v = float(val)
        if v != v:  # NaN
            return default
        return v
    except (TypeError, ValueError):
        return default


def refresh_holdings_price(holdings: List[dict]):
    """批量刷新持仓现价、昨收（统一复用个股详情链路，支持实时覆盖和交易日回退）"""
    if not holdings:
        return
    try:
        today = datetime.now().strftime("%Y%m%d")
        for h in holdings:
            ts_code = normalize_ts_code(h.get("ts_code") or "")
            if not ts_code:
                continue
            detail = tushare_client.get_stock_detail(ts_code, today)
            price = _safe_float(detail.get("close"), 0.0)
            pre_close = _safe_float(detail.get("pre_close"), 0.0)
            if price <= 0:
                continue

            h["ts_code"] = ts_code
            h["stock_name"] = detail.get("stock_name") or h.get("stock_name") or ts_code
            h["market_price"] = price
            h["pre_close"] = pre_close or price
            h["quote_time"] = detail.get("quote_time")
            h["data_source"] = detail.get("data_source")

            cost = _safe_float(h.get("cost_price"), 0.0)
            qty = int(h.get("holding_qty") or 0)
            if cost > 0:
                h["pnl_pct"] = round((price - cost) / cost * 100, 2)
            if qty > 0:
                h["holding_market_value"] = round(qty * price, 2)
    except Exception as e:
        logger.error(f"刷新持仓现价失败: {e}")


def enrich_holdings(holdings: List[dict]):
    """补充持股天数、浮盈金额、当日盈亏金额（依赖 refresh_holdings_price 已写入 market_price / pre_close）"""
    today = datetime.now().date()
    for h in holdings:
        try:
            buy = datetime.strptime(str(h.get("buy_date", "")), "%Y-%m-%d").date()
            h["holding_days"] = max(0, (today - buy).days)
        except Exception:
            h["holding_days"] = 0

        qty = int(h.get("holding_qty") or 0)
        cost = _safe_float(h.get("cost_price"), 0.0)
        price = _safe_float(h.get("market_price"), 0.0)
        pre_close = h.get("pre_close")
        if pre_close is None:
            pre_close = price
        else:
            pre_close = _safe_float(pre_close, price)

        h["pnl_amount"] = round((price - cost) * qty, 2)
        h["today_pnl_amount"] = round((price - pre_close) * qty, 2)


@router.get("/config", response_model=ApiResponse)
async def get_account_config() -> ApiResponse:
    """获取账户配置（总资产等）"""
    try:
        data = await get_account_config_from_db()
        return ApiResponse(data=data)
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户配置失败：{str(e)}")


@router.put("/config", response_model=ApiResponse)
async def put_account_config(request: AccountConfigUpdateRequest) -> ApiResponse:
    """更新账户配置"""
    try:
        data = await update_account_config(request.model_dump())
        return ApiResponse(data=data)
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"更新账户配置失败：{str(e)}")


@router.get("/profile", response_model=ApiResponse)
async def get_profile() -> ApiResponse:
    """获取账户概况"""
    try:
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        enrich_holdings(holdings)
        account = await build_account_input(holdings)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(account, holdings_obj)
        total_pnl = sum(_safe_float(h.get("pnl_amount"), 0.0) for h in holdings)
        today_pnl = sum(_safe_float(h.get("today_pnl_amount"), 0.0) for h in holdings)
        profile = profile.model_copy(
            update={
                "total_pnl_amount": round(total_pnl, 2),
                "today_pnl_amount": round(today_pnl, 2),
            }
        )
        return ApiResponse(data=profile.model_dump())
    except Exception as e:
        return ApiResponse(code=500, message=f"获取账户概况失败：{str(e)}")


@router.get("/positions", response_model=ApiResponse)
async def get_positions() -> ApiResponse:
    """获取持仓明细"""
    try:
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        enrich_holdings(holdings)
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
    """修改持仓（数量、成本价、买入理由等）"""
    try:
        ts_code = normalize_ts_code(ts_code)

        payload = request.model_dump(exclude_unset=True)
        if not payload:
            return ApiResponse(code=400, message="请至少修改一项")

        # 更新数据库
        updated = await update_holding_in_db(ts_code, **payload)

        if updated:
            # 与 GET 持仓一致：按当日行情刷新现价、盈亏、市值
            refresh_holdings_price([updated])
            enrich_holdings([updated])
            return ApiResponse(data={"message": "持仓更新成功", "position": updated})
        else:
            return ApiResponse(code=404, message="持仓不存在")
    except Exception as e:
        return ApiResponse(code=500, message=f"更新持仓失败：{str(e)}")


@router.delete("/positions/{position_id}", response_model=ApiResponse)
async def delete_position(position_id: str) -> ApiResponse:
    """删除持仓（按 id）"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(Holding).where(Holding.id == position_id))
            holding = result.scalar_one_or_none()
            if holding:
                await session.delete(holding)
                await session.commit()
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
        holdings = await get_holdings_from_db()
        refresh_holdings_price(holdings)
        enrich_holdings(holdings)
        account = account or await build_account_input(holdings)
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
        enrich_holdings(holdings)
        account = await build_account_input(holdings)
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(account, holdings_obj)
        trade_date = datetime.now().strftime("%Y-%m-%d")
        result = account_adapter_service.adapt(trade_date, account, holdings_obj)

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
