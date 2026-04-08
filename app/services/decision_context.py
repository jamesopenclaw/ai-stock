"""
决策上下文构建服务
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from app.services.market_data_gateway import market_data_gateway
from app.models.schemas import AccountInput, AccountPosition, StockInput
from app.services.market_env import market_env_service
from app.services.portfolio_service import portfolio_service
from app.services.sector_scan import sector_scan_service
from app.services.sector_scan_snapshot import (
    resolve_snapshot_lookup_trade_date,
    sector_scan_snapshot_service,
)
from app.services.stock_filter import merge_holdings_into_candidate_stocks


@dataclass
class SharedDecisionContext:
    """与账户无关、可跨账户复用的市场共享上下文。"""

    trade_date: str
    selection_trade_date: str
    resolved_stock_trade_date: Optional[str]
    sector_scan_trade_date: Optional[str]
    sector_scan_resolved_trade_date: Optional[str]
    market_env: object
    realtime_market_env: object
    sector_scan: object
    stocks: List[StockInput]
    candidate_data_status: Optional[str] = None
    candidate_data_message: Optional[str] = None


@dataclass
class AccountDecisionContext:
    """与账户强相关的私有上下文。"""

    trade_date: str
    account_id: Optional[str]
    holdings_list: List[dict]
    holdings: List[AccountPosition]
    account: AccountInput


@dataclass
class DecisionContext:
    """单次决策请求的完整上下文，由共享层和账户层组合而成。"""

    trade_date: str
    resolved_stock_trade_date: Optional[str]
    candidate_data_status: Optional[str]
    candidate_data_message: Optional[str]
    sector_scan_trade_date: Optional[str]
    sector_scan_resolved_trade_date: Optional[str]
    market_env: object
    realtime_market_env: object
    sector_scan: object
    stocks: List[StockInput]
    holdings_list: List[dict]
    holdings: List[AccountPosition]
    account: AccountInput
    shared_context: SharedDecisionContext
    account_context: AccountDecisionContext


class DecisionContextService:
    """统一构建市场、板块、候选股、持仓和账户上下文。"""

    async def _resolve_selection_trade_date(self, trade_date: str) -> str:
        """三池/选股默认跟随板块页的稳定快照日。"""
        return await resolve_snapshot_lookup_trade_date(trade_date)

    def _enrich_holding_time_fields(
        self,
        holding: dict,
        trade_date: Optional[str] = None,
    ) -> dict:
        """补充持有天数与 T+1 可卖状态。"""
        return portfolio_service.enrich_holding_time_fields(holding, trade_date)

    def _count_today_new_buys(
        self,
        holdings: List[dict],
        trade_date: str,
    ) -> int:
        """根据持仓买入日期估算当日新开仓数量。"""
        return portfolio_service.count_today_new_buys(holdings, trade_date)

    async def get_holdings_from_db(
        self,
        account_id: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> List[dict]:
        """从数据库获取持仓，并按目标交易日刷新价格。"""
        return await portfolio_service.get_holdings_from_db(account_id, trade_date)

    async def build_account_input_from_holdings(
        self,
        holdings: List[dict],
        account_id: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> AccountInput:
        """根据持仓动态构建账户信息。"""
        return await portfolio_service.build_account_input_from_holdings(
            holdings,
            account_id,
            trade_date,
        )

    def get_candidate_stocks(
        self,
        trade_date: str,
        top_gainers: int,
        holdings_list: Optional[List[dict]] = None,
        include_holdings: bool = False,
        prefer_today: bool = False,
    ) -> tuple[List[StockInput], Optional[str], Optional[str], Optional[str]]:
        """获取候选股，并按需将持仓并入候选池。"""
        stock_payload = market_data_gateway.get_expanded_stock_list_with_meta(
            trade_date,
            top_gainers=top_gainers,
            prefer_today=prefer_today,
        )
        stock_list = stock_payload.get("rows") or []
        resolved_trade_date = stock_payload.get("data_trade_date")
        candidate_data_status = stock_payload.get("data_status")
        candidate_data_message = stock_payload.get("data_message")
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
                concept_names=s.get("concept_names") or [],
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

        return stocks, resolved_trade_date_fmt, candidate_data_status, candidate_data_message

    async def build_shared_context(
        self,
        trade_date: str,
        top_gainers: int = 100,
    ) -> SharedDecisionContext:
        """构建只依赖市场与板块数据的共享上下文。"""
        selection_trade_date = await self._resolve_selection_trade_date(trade_date)
        market_env = market_env_service.get_current_env(selection_trade_date)
        realtime_market_env = (
            market_env
            if selection_trade_date == trade_date
            else market_env_service.get_current_env(trade_date)
        )
        sector_scan = await sector_scan_snapshot_service.get_snapshot(selection_trade_date)
        if not sector_scan:
            sector_scan = sector_scan_service.scan(
                selection_trade_date,
                limit_output=False,
                market_env=market_env,
            )
        candidate_payload = self.get_candidate_stocks(
            selection_trade_date,
            top_gainers=top_gainers,
            holdings_list=None,
            include_holdings=False,
        )
        if len(candidate_payload) == 4:
            stocks, resolved_stock_trade_date, candidate_data_status, candidate_data_message = candidate_payload
        else:
            stocks, resolved_stock_trade_date = candidate_payload
            candidate_data_status = None
            candidate_data_message = None
        return SharedDecisionContext(
            trade_date=trade_date,
            selection_trade_date=selection_trade_date,
            resolved_stock_trade_date=resolved_stock_trade_date,
            candidate_data_status=candidate_data_status,
            candidate_data_message=candidate_data_message,
            sector_scan_trade_date=getattr(sector_scan, "trade_date", None),
            sector_scan_resolved_trade_date=getattr(sector_scan, "resolved_trade_date", None),
            market_env=market_env,
            realtime_market_env=realtime_market_env,
            sector_scan=sector_scan,
            stocks=stocks,
        )

    async def build_account_context(
        self,
        trade_date: str,
        account_id: Optional[str] = None,
    ) -> AccountDecisionContext:
        """构建只依赖账户维度的私有上下文。"""
        holdings_list = await self.get_holdings_from_db(account_id, trade_date)
        holdings = [AccountPosition(**h) for h in holdings_list]
        account = await self.build_account_input_from_holdings(
            holdings_list,
            account_id,
            trade_date,
        )
        return AccountDecisionContext(
            trade_date=trade_date,
            account_id=account_id,
            holdings_list=holdings_list,
            holdings=holdings,
            account=account,
        )

    def compose_context(
        self,
        shared_context: SharedDecisionContext,
        account_context: AccountDecisionContext,
        *,
        include_holdings: bool = False,
    ) -> DecisionContext:
        """将共享层与账户层拼成完整决策上下文。"""
        stocks = shared_context.stocks
        if include_holdings:
            stocks = merge_holdings_into_candidate_stocks(
                shared_context.selection_trade_date,
                shared_context.stocks,
                account_context.holdings_list,
            )

        return DecisionContext(
            trade_date=shared_context.trade_date,
            resolved_stock_trade_date=shared_context.resolved_stock_trade_date,
            candidate_data_status=shared_context.candidate_data_status,
            candidate_data_message=shared_context.candidate_data_message,
            sector_scan_trade_date=shared_context.sector_scan_trade_date,
            sector_scan_resolved_trade_date=shared_context.sector_scan_resolved_trade_date,
            market_env=shared_context.market_env,
            realtime_market_env=shared_context.realtime_market_env,
            sector_scan=shared_context.sector_scan,
            stocks=stocks,
            holdings_list=account_context.holdings_list,
            holdings=account_context.holdings,
            account=account_context.account,
            shared_context=shared_context,
            account_context=account_context,
        )

    def build_single_stock_input(
        self,
        ts_code: str,
        trade_date: str,
        *,
        candidate_source_tag: str = "单股体检",
    ) -> StockInput:
        """基于个股详情构造单只股票的规则输入对象。"""
        detail = market_data_gateway.get_stock_detail(ts_code, trade_date)
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
            concept_names=detail.get("concept_names") or [],
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
        normalized_target = market_data_gateway.normalize_ts_code(str(ts_code or "").strip())
        for stock in stocks:
            if market_data_gateway.normalize_ts_code(str(stock.ts_code).strip()) == normalized_target:
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
        account_id: Optional[str] = None,
    ) -> DecisionContext:
        """构建单次请求的完整上下文。"""
        shared_context = await self.build_shared_context(
            trade_date,
            top_gainers=top_gainers,
        )
        account_context = await self.build_account_context(
            trade_date,
            account_id=account_id,
        )
        return self.compose_context(
            shared_context,
            account_context,
            include_holdings=include_holdings,
        )


decision_context_service = DecisionContextService()
