"""
决策上下文构建服务
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select

from app.core.database import async_session_factory
from app.data.tushare_client import tushare_client
from app.models.holding import Holding
from app.models.schemas import AccountInput, AccountPosition, StockInput
from app.services.account_config_service import get_total_asset
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import merge_holdings_into_candidate_stocks


@dataclass
class DecisionContext:
    """单次决策请求共享的数据上下文。"""

    trade_date: str
    resolved_stock_trade_date: Optional[str]
    market_env: object
    sector_scan: object
    stocks: List[StockInput]
    holdings_list: List[dict]
    holdings: List[AccountPosition]
    account: AccountInput


class DecisionContextService:
    """统一构建市场、板块、候选股、持仓和账户上下文。"""

    def _target_date(self, trade_date: Optional[str]) -> datetime.date:
        """将请求日期规范为 date，用于历史口径计算持仓天数。"""
        raw = str(trade_date or datetime.now().strftime("%Y-%m-%d"))[:10]
        return datetime.strptime(raw, "%Y-%m-%d").date()

    def _enrich_holding_time_fields(
        self,
        holding: dict,
        trade_date: Optional[str] = None,
    ) -> dict:
        """补充持有天数与 T+1 可卖状态。"""
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

    def _count_today_new_buys(self, holdings: List[dict], trade_date: str) -> int:
        """根据持仓买入日期估算当日新开仓数量。"""
        target = trade_date[:10]
        return sum(1 for h in holdings if str(h.get("buy_date") or "")[:10] == target)

    async def get_holdings_from_db(self, trade_date: Optional[str] = None) -> List[dict]:
        """从数据库获取持仓，并按目标交易日刷新价格。"""
        compact_date = (trade_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")

        async with async_session_factory() as session:
            result = await session.execute(select(Holding))
            holdings = result.scalars().all()
            holdings_list = [h.to_dict() for h in holdings]

            for h in holdings_list:
                self._enrich_holding_time_fields(h, trade_date)
                try:
                    detail = tushare_client.get_stock_detail(h["ts_code"], compact_date)
                    if detail and detail.get("close"):
                        h["market_price"] = detail.get("close")
                        if h.get("cost_price"):
                            h["pnl_pct"] = round(
                                (h["market_price"] - h["cost_price"]) / h["cost_price"] * 100,
                                2,
                            )
                        if h.get("holding_qty"):
                            h["holding_market_value"] = h["holding_qty"] * h["market_price"]
                except Exception:
                    pass

            return holdings_list

    async def build_account_input_from_holdings(
        self,
        holdings: List[dict],
        trade_date: Optional[str] = None,
    ) -> AccountInput:
        """根据持仓动态构建账户信息。"""
        market_value = sum(
            h.get("holding_market_value") or (h.get("holding_qty", 0) * h.get("market_price", 0))
            for h in holdings
        )
        total_asset = await get_total_asset()
        available_cash = max(total_asset - market_value, 0)
        total_position_ratio = market_value / total_asset if total_asset > 0 else 0

        return AccountInput(
            total_asset=total_asset,
            available_cash=available_cash,
            total_position_ratio=round(total_position_ratio, 4),
            holding_count=len(holdings),
            today_new_buy_count=self._count_today_new_buys(
                holdings, trade_date or datetime.now().strftime("%Y-%m-%d")
            ),
        )

    def get_candidate_stocks(
        self,
        trade_date: str,
        top_gainers: int,
        holdings_list: Optional[List[dict]] = None,
        include_holdings: bool = False,
    ) -> tuple[List[StockInput], Optional[str]]:
        """获取候选股，并按需将持仓并入候选池。"""
        stock_payload = tushare_client.get_expanded_stock_list_with_meta(
            trade_date.replace("-", ""),
            top_gainers=top_gainers,
        )
        stock_list = stock_payload.get("rows") or []
        resolved_trade_date = stock_payload.get("data_trade_date")
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
                candidate_source_tag=s.get("candidate_source_tag", ""),
            )
            for s in stock_list
        ]

        if include_holdings:
            stocks = merge_holdings_into_candidate_stocks(trade_date, stocks, holdings_list)

        resolved_trade_date_fmt = None
        if resolved_trade_date:
            resolved_trade_date = str(resolved_trade_date)
            resolved_trade_date_fmt = (
                f"{resolved_trade_date[:4]}-{resolved_trade_date[4:6]}-{resolved_trade_date[6:8]}"
            )

        return stocks, resolved_trade_date_fmt

    async def build_context(
        self,
        trade_date: str,
        top_gainers: int = 100,
        include_holdings: bool = False,
    ) -> DecisionContext:
        """构建单次请求的共享上下文。"""
        holdings_list = await self.get_holdings_from_db(trade_date)
        holdings = [AccountPosition(**h) for h in holdings_list]
        account = await self.build_account_input_from_holdings(holdings_list, trade_date)
        market_env = market_env_service.get_current_env(trade_date)
        sector_scan = sector_scan_service.scan(trade_date, limit_output=False)
        stocks, resolved_stock_trade_date = self.get_candidate_stocks(
            trade_date,
            top_gainers=top_gainers,
            holdings_list=holdings_list,
            include_holdings=include_holdings,
        )

        return DecisionContext(
            trade_date=trade_date,
            resolved_stock_trade_date=resolved_stock_trade_date,
            market_env=market_env,
            sector_scan=sector_scan,
            stocks=stocks,
            holdings_list=holdings_list,
            holdings=holdings,
            account=account,
        )


decision_context_service = DecisionContextService()
