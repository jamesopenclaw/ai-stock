"""
决策上下文构建服务
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select

from app.core.database import async_session_factory
from app.data.tushare_client import normalize_ts_code, tushare_client
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
    realtime_market_env: object
    sector_scan: object
    stocks: List[StockInput]
    holdings_list: List[dict]
    holdings: List[AccountPosition]
    account: AccountInput


class DecisionContextService:
    """统一构建市场、板块、候选股、持仓和账户上下文。"""

    def _resolve_selection_trade_date(self, trade_date: str) -> str:
        """三池/选股口径使用最近已完成交易日，避免盘中实时扰动。"""
        compact = tushare_client.get_last_completed_trade_date(trade_date.replace("-", ""))
        if len(compact) == 8:
            return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
        return trade_date

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

    def _count_today_new_buys(
        self,
        holdings: List[dict],
        trade_date: str,
    ) -> int:
        """根据持仓买入日期估算当日新开仓数量。"""
        target = trade_date[:10]
        return sum(
            1
            for h in holdings
            if str(h.get("buy_date") or "")[:10] == target
        )

    async def get_holdings_from_db(
        self,
        trade_date: Optional[str] = None,
    ) -> List[dict]:
        """从数据库获取持仓，并按目标交易日刷新价格。"""
        compact_date = (
            trade_date or datetime.now().strftime("%Y-%m-%d")
        ).replace("-", "")

        async with async_session_factory() as session:
            result = await session.execute(select(Holding))
            holdings = result.scalars().all()
            holdings_list = [h.to_dict() for h in holdings]

            for h in holdings_list:
                self._enrich_holding_time_fields(h, trade_date)
                try:
                    detail = tushare_client.get_stock_detail(
                        h["ts_code"],
                        compact_date,
                    )
                    if detail and detail.get("close"):
                        h["market_price"] = detail.get("close")
                        h["quote_time"] = detail.get("quote_time")
                        h["data_source"] = detail.get("data_source")
                        if h.get("cost_price"):
                            h["pnl_pct"] = round(
                                (h["market_price"] - h["cost_price"])
                                / h["cost_price"]
                                * 100,
                                2,
                            )
                        if h.get("holding_qty"):
                            h["holding_market_value"] = (
                                h["holding_qty"] * h["market_price"]
                            )
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
            h.get("holding_market_value")
            or (h.get("holding_qty", 0) * h.get("market_price", 0))
            for h in holdings
        )
        total_asset = await get_total_asset()
        available_cash = max(total_asset - market_value, 0)
        total_position_ratio = (
            market_value / total_asset if total_asset > 0 else 0
        )

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
                volume=s.get("volume"),
                avg_price=s.get("avg_price"),
                quote_time=s.get("quote_time"),
                data_source=s.get("data_source"),
            )
            for s in stock_list
        ]

        if include_holdings:
            stocks = merge_holdings_into_candidate_stocks(
                trade_date,
                stocks,
                holdings_list,
            )

        resolved_trade_date_fmt = None
        if resolved_trade_date:
            resolved_trade_date = str(resolved_trade_date)
            resolved_trade_date_fmt = (
                f"{resolved_trade_date[:4]}-{resolved_trade_date[4:6]}-{resolved_trade_date[6:8]}"
            )

        return stocks, resolved_trade_date_fmt

    def build_single_stock_input(
        self,
        ts_code: str,
        trade_date: str,
        *,
        candidate_source_tag: str = "单股体检",
    ) -> StockInput:
        """基于个股详情构造单只股票的规则输入对象。"""
        detail = tushare_client.get_stock_detail(ts_code, trade_date.replace("-", ""))
        return StockInput(
            ts_code=detail["ts_code"],
            stock_name=detail.get("stock_name") or detail["ts_code"],
            sector_name=detail.get("sector_name") or "未知",
            close=float(detail.get("close") or 0),
            change_pct=float(detail.get("change_pct") or 0),
            turnover_rate=float(detail.get("turnover_rate") or 0),
            amount=float(detail.get("amount") or 0),
            vol_ratio=detail.get("vol_ratio"),
            high=float(detail.get("high") or 0),
            low=float(detail.get("low") or 0),
            open=float(detail.get("open") or 0),
            pre_close=float(detail.get("pre_close") or 0),
            candidate_source_tag=candidate_source_tag,
            volume=detail.get("volume"),
            avg_price=detail.get("avg_price"),
            intraday_volume_ratio=detail.get("intraday_volume_ratio"),
            quote_time=detail.get("quote_time"),
            data_source=detail.get("data_source"),
        )

    def merge_single_stock_into_context(
        self,
        trade_date: str,
        stocks: List[StockInput],
        ts_code: str,
        *,
        candidate_source_tag: str = "单股体检",
    ) -> tuple[List[StockInput], bool]:
        """确保目标股存在于候选上下文中。"""
        normalized_target = normalize_ts_code(str(ts_code or "").strip())
        for stock in stocks:
            if normalize_ts_code(str(stock.ts_code).strip()) == normalized_target:
                return stocks, True
        single_stock = self.build_single_stock_input(
            ts_code,
            trade_date,
            candidate_source_tag=candidate_source_tag,
        )
        return [single_stock, *stocks], False

    async def build_context(
        self,
        trade_date: str,
        top_gainers: int = 100,
        include_holdings: bool = False,
    ) -> DecisionContext:
        """构建单次请求的共享上下文。"""
        selection_trade_date = self._resolve_selection_trade_date(trade_date)
        holdings_list = await self.get_holdings_from_db(trade_date)
        holdings = [AccountPosition(**h) for h in holdings_list]
        account = await self.build_account_input_from_holdings(
            holdings_list,
            trade_date,
        )
        market_env = market_env_service.get_current_env(selection_trade_date)
        realtime_market_env = (
            market_env
            if selection_trade_date == trade_date
            else market_env_service.get_current_env(trade_date)
        )
        sector_scan = sector_scan_service.scan(
            selection_trade_date,
            limit_output=False,
            market_env=market_env,
        )
        stocks, resolved_stock_trade_date = self.get_candidate_stocks(
            selection_trade_date,
            top_gainers=top_gainers,
            holdings_list=holdings_list,
            include_holdings=include_holdings,
        )

        return DecisionContext(
            trade_date=trade_date,
            resolved_stock_trade_date=resolved_stock_trade_date,
            market_env=market_env,
            realtime_market_env=realtime_market_env,
            sector_scan=sector_scan,
            stocks=stocks,
            holdings_list=holdings_list,
            holdings=holdings,
            account=account,
        )


decision_context_service = DecisionContextService()
