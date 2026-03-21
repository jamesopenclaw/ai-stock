"""
账户管理 API
"""
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json
import os
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

# 持仓数据存储文件
HOLDINGS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "holdings.json"
HOLDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_holdings() -> List[dict]:
    """加载持仓数据"""
    if HOLDINGS_FILE.exists():
        try:
            with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    # 返回默认数据
    return [
        {
            "id": "1",
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
            "id": "2",
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
            "id": "3",
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


def save_holdings(holdings: List[dict]):
    """保存持仓数据"""
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)


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
    ts_code: str = Body(..., description="股票代码，如 000001.SZ")
    holding_qty: int = Body(..., description="持仓数量")
    cost_price: float = Body(..., description="持仓成本价")
    buy_date: str = Body(..., description="买入日期，格式 YYYY-MM-DD")
    holding_reason: Optional[str] = Body(None, description="买入理由")


def refresh_holdings_prices():
    """刷新持仓现价和盈亏"""
    holdings = load_holdings()
    trade_date = datetime.now().strftime("%Y%m%d")
    
    for h in holdings:
        try:
            # 从 Tushare 获取现价
            detail = tushare_client.get_stock_detail(h["ts_code"], trade_date)
            if detail:
                h["market_price"] = detail.get("close", h.get("cost_price", 0))
                # 计算盈亏
                if h.get("cost_price") and h.get("market_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                # 计算市值
                h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                # T+1 判断
                buy_date = datetime.strptime(h["buy_date"], "%Y-%m-%d")
                today = datetime.now()
                h["can_sell_today"] = (today - buy_date).days > 0
        except Exception as e:
            print(f"刷新价格失败: {h['ts_code']}, {e}")
    
    save_holdings(holdings)
    return holdings


@router.get("/profile", response_model=ApiResponse)
async def get_profile() -> ApiResponse:
    """获取账户概况"""
    try:
        # 刷新最新价格
        holdings = refresh_holdings_prices()
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
        # 刷新最新价格
        holdings = refresh_holdings_prices()

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
            # 自动补齐后缀
            if ts_code.startswith('6'):
                ts_code += '.SH'
            else:
                ts_code += '.SZ'

        # 从 Tushare 获取股票名称
        trade_date = datetime.now().strftime("%Y%m%d")
        detail = tushare_client.get_stock_detail(ts_code, trade_date)
        stock_name = detail.get("stock_name", ts_code) if detail else ts_code

        # 获取现价
        market_price = detail.get("close", request.cost_price) if detail else request.cost_price

        # 生成 ID
        holdings = load_holdings()
        new_id = str(int(datetime.now().timestamp() * 1000))

        # 计算市值和盈亏
        holding_market_value = request.holding_qty * market_price
        pnl_pct = round((market_price - request.cost_price) / request.cost_price * 100, 2) if request.cost_price else 0

        # T+1 判断
        buy_date = datetime.strptime(request.buy_date, "%Y-%m-%d")
        today = datetime.now()
        can_sell_today = (today - buy_date).days > 0

        # 新增持仓
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

        holdings.append(new_holding)
        save_holdings(holdings)

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
        holdings = load_holdings()
        
        # 查找并删除
        original_len = len(holdings)
        holdings = [h for h in holdings if str(h.get("id")) != position_id]
        
        if len(holdings) == original_len:
            return ApiResponse(code=404, message="持仓不存在")
        
        save_holdings(holdings)

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
        holdings = load_holdings()
        
        # 查找
        found = False
        for h in holdings:
            if str(h.get("id")) == position_id:
                found = True
                # 更新字段
                if holding_qty is not None:
                    h["holding_qty"] = holding_qty
                if cost_price is not None:
                    h["cost_price"] = cost_price
                if holding_reason is not None:
                    h["holding_reason"] = holding_reason
                
                # 重新计算
                if h.get("market_price") and h.get("cost_price"):
                    h["pnl_pct"] = round((h["market_price"] - h["cost_price"]) / h["cost_price"] * 100, 2)
                if h.get("holding_qty") and h.get("market_price"):
                    h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                break
        
        if not found:
            return ApiResponse(code=404, message="持仓不存在")
        
        save_holdings(holdings)

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
        holdings = refresh_holdings_prices()
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
        holdings = refresh_holdings_prices()
        holdings_obj = [AccountPosition(**h) for h in holdings]
        profile = account_adapter_service.get_profile(MOCK_ACCOUNT, holdings_obj)
        result = account_adapter_service.adapt("2026-03-20", MOCK_ACCOUNT, holdings_obj)

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
