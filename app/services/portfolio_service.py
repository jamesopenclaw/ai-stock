"""
持仓与账户输入共享服务
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select

from app.core.database import async_session_factory
from app.data.tushare_client import normalize_ts_code, tushare_client
from app.models.holding import Holding
from app.models.schemas import AccountInput
from app.services.account_config_service import get_account_available_cash


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        v = float(val)
        if v != v:
            return default
        return v
    except (TypeError, ValueError):
        return default


class PortfolioService:
    """统一处理持仓读取、行情补齐和账户输入构建。"""

    def _target_date(self, trade_date: Optional[str]) -> datetime.date:
        raw = str(trade_date or datetime.now().strftime("%Y-%m-%d"))[:10]
        return datetime.strptime(raw, "%Y-%m-%d").date()

    def enrich_holding_time_fields(
        self,
        holding: dict,
        trade_date: Optional[str] = None,
    ) -> dict:
        target_date = self._target_date(trade_date)
        buy_date_raw = str(holding.get("buy_date") or "")[:10]

        try:
            buy_date = datetime.strptime(buy_date_raw, "%Y-%m-%d").date()
            holding["holding_days"] = max(0, (target_date - buy_date).days)
            holding["can_sell_today"] = target_date > buy_date
        except Exception:
            holding["holding_days"] = 0
            if holding.get("can_sell_today") is None:
                holding["can_sell_today"] = False

        return holding

    def count_today_new_buys(self, holdings: List[dict], trade_date: str) -> int:
        target = trade_date[:10]
        return sum(1 for h in holdings if str(h.get("buy_date") or "")[:10] == target)

    async def get_holdings_from_db(
        self,
        account_id: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> List[dict]:
        async with async_session_factory() as session:
            stmt = select(Holding)
            if account_id:
                stmt = stmt.where(Holding.account_id == account_id)
            result = await session.execute(stmt)
            holdings = [h.to_dict() for h in result.scalars().all()]

        self.refresh_holdings_price(holdings, trade_date=trade_date)
        for holding in holdings:
            self.enrich_holding_time_fields(holding, trade_date)
        return holdings

    def refresh_holdings_price(
        self,
        holdings: List[dict],
        trade_date: Optional[str] = None,
    ) -> None:
        if not holdings:
            return

        compact_date = (trade_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        quote_map = tushare_client.get_stock_quote_map(
            [holding.get("ts_code") or "" for holding in holdings],
            compact_date,
        )
        for holding in holdings:
            ts_code = normalize_ts_code(holding.get("ts_code") or "")
            if not ts_code:
                continue
            detail = quote_map.get(ts_code)
            if not detail:
                continue

            price = _safe_float(detail.get("close"), 0.0)
            pre_close = _safe_float(detail.get("pre_close"), 0.0)
            if price <= 0:
                continue

            holding["ts_code"] = ts_code
            holding["stock_name"] = detail.get("stock_name") or holding.get("stock_name") or ts_code
            holding["sector_name"] = detail.get("sector_name") or holding.get("sector_name")
            holding["market_price"] = price
            holding["pre_close"] = pre_close or price
            holding["quote_time"] = detail.get("quote_time")
            holding["data_source"] = detail.get("data_source")

            cost = _safe_float(holding.get("cost_price"), 0.0)
            qty = int(holding.get("holding_qty") or 0)
            if cost > 0:
                holding["pnl_pct"] = round((price - cost) / cost * 100, 2)
            if qty > 0:
                holding["holding_market_value"] = round(qty * price, 2)

    def enrich_holdings(
        self,
        holdings: List[dict],
        trade_date: Optional[str] = None,
    ) -> None:
        target_date = self._target_date(trade_date)
        for holding in holdings:
            self.enrich_holding_time_fields(holding, trade_date)

            qty = int(holding.get("holding_qty") or 0)
            cost = _safe_float(holding.get("cost_price"), 0.0)
            price = _safe_float(holding.get("market_price"), 0.0)
            pre_close = _safe_float(holding.get("pre_close"), price)

            holding["holding_days"] = holding.get("holding_days", 0)
            holding["pnl_amount"] = round((price - cost) * qty, 2)
            holding["today_pnl_amount"] = round((price - pre_close) * qty, 2)
            holding["trade_date"] = target_date.isoformat()

    async def build_account_input_from_holdings(
        self,
        holdings: List[dict],
        account_id: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> AccountInput:
        market_value = sum(
            h.get("holding_market_value")
            or (h.get("holding_qty", 0) * h.get("market_price", 0))
            for h in holdings
        )
        available_cash = await get_account_available_cash(account_id=account_id)
        total_asset = market_value + max(available_cash, 0)
        total_position_ratio = market_value / total_asset if total_asset > 0 else 0

        return AccountInput(
            total_asset=total_asset,
            available_cash=max(available_cash, 0),
            total_position_ratio=round(total_position_ratio, 4),
            holding_count=len(holdings),
            today_new_buy_count=self.count_today_new_buys(
                holdings,
                trade_date or datetime.now().strftime("%Y-%m-%d"),
            ),
            t1_locked_positions=[],
        )


portfolio_service = PortfolioService()
