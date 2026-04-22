"""
决策上下文构建服务
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from app.services.market_data_gateway import market_data_gateway
from app.models.schemas import AccountInput, AccountPosition, StockInput
from app.data.tushare_client import is_sector_scan_board_eligible, tushare_client
from app.services.market_env import market_env_service
from app.services.portfolio_service import portfolio_service
from app.services.sector_scan import sector_scan_service
from app.services.sector_scan_snapshot import (
    resolve_snapshot_lookup_trade_date,
    sector_scan_snapshot_service,
)
from app.services.strategy_config import (
    DEFAULT_STOCK_FILTER_STRATEGY,
    StockFilterStrategyConfig,
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
    realtime_sector_scan: object = None


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
    realtime_sector_scan: object = None


class DecisionContextService:
    """统一构建市场、板块、候选股、持仓和账户上下文。"""

    MAINLINE_PULLBACK_SOURCE_TAG = "主线回踩补充"
    MAINLINE_LOW_SUCK_SOURCE_TAG = "主线低吸补充"

    def __init__(self, strategy: Optional[StockFilterStrategyConfig] = None):
        self.strategy = strategy or DEFAULT_STOCK_FILTER_STRATEGY

    async def _resolve_selection_trade_date(self, trade_date: str) -> str:
        """三池/选股默认跟随板块页的稳定快照日。"""
        return await resolve_snapshot_lookup_trade_date(trade_date)

    def _should_build_realtime_confirmation_context(
        self,
        trade_date: str,
        selection_trade_date: str,
    ) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        return bool(
            trade_date
            and selection_trade_date
            and trade_date == today
            and selection_trade_date != trade_date
        )

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

    def _append_candidate_source_tag(self, current: str, new_source: str) -> str:
        parts = [part.strip() for part in str(current or "").split("/") if part.strip()]
        if new_source and new_source not in parts:
            parts.append(new_source)
        return "/".join(parts)

    def _merge_candidate_stocks(
        self,
        base_stocks: List[StockInput],
        extra_stocks: List[StockInput],
    ) -> List[StockInput]:
        if not extra_stocks:
            return base_stocks

        merged = list(base_stocks)
        index_by_code = {
            market_data_gateway.normalize_ts_code(stock.ts_code): index
            for index, stock in enumerate(merged)
        }
        for extra in extra_stocks:
            normalized = market_data_gateway.normalize_ts_code(extra.ts_code)
            existing_index = index_by_code.get(normalized)
            if existing_index is None:
                index_by_code[normalized] = len(merged)
                merged.append(extra)
                continue

            existing = merged[existing_index]
            existing.candidate_source_tag = self._append_candidate_source_tag(
                existing.candidate_source_tag,
                extra.candidate_source_tag,
            )
            if extra.concept_names:
                existing.concept_names = list(
                    dict.fromkeys(
                        list(existing.concept_names or []) + list(extra.concept_names or [])
                    )
                )
            if (
                (not existing.sector_name or existing.sector_name == "未知")
                and extra.sector_name
            ):
                existing.sector_name = extra.sector_name
            if existing.avg_price is None and extra.avg_price is not None:
                existing.avg_price = extra.avg_price
            if existing.volume is None and extra.volume is not None:
                existing.volume = extra.volume
        return merged

    def _iter_mainline_sector_targets(self, sector_scan) -> List[tuple[str, str]]:
        if not sector_scan:
            return []

        targets: List[tuple[str, str]] = []
        seen = set()
        groups = [
            getattr(sector_scan, "theme_leaders", []),
            getattr(sector_scan, "industry_leaders", []),
            getattr(sector_scan, "mainline_sectors", []),
            getattr(sector_scan, "sub_mainline_sectors", []),
        ]
        for group in groups:
            for sector in list(group or []):
                name = str(getattr(sector, "sector_name", "") or "").strip()
                source_type = str(getattr(sector, "sector_source_type", "") or "").strip()
                if not name:
                    continue
                key = (name, source_type)
                if key in seen:
                    continue
                seen.add(key)
                targets.append(key)
        return targets

    def _close_quality_from_row(
        self,
        close: float,
        low: float,
        high: float,
    ) -> float:
        intraday_range = float(high or 0) - float(low or 0)
        if intraday_range <= 0:
            return 0.5
        return max(0.0, min(1.0, (float(close or 0) - float(low or 0)) / intraday_range))

    def _has_upper_shadow_risk_from_row(
        self,
        *,
        open_price: float,
        close: float,
        high: float,
        low: float,
    ) -> bool:
        intraday_range = float(high or 0) - float(low or 0)
        if intraday_range <= 0:
            return False
        upper_shadow = float(high or 0) - max(float(open_price or 0), float(close or 0))
        return (upper_shadow / intraday_range) >= 0.35

    def _classify_mainline_recall_source(
        self,
        *,
        close: float,
        open_price: float,
        high: float,
        low: float,
        pre_close: float,
        change_pct: float,
        avg_price: Optional[float],
        vol_ratio: Optional[float],
    ) -> Optional[str]:
        close_quality = self._close_quality_from_row(close, low, high)
        upper_shadow_risk = self._has_upper_shadow_risk_from_row(
            open_price=open_price,
            close=close,
            high=high,
            low=low,
        )
        if upper_shadow_risk:
            return None

        anchor_distances = [
            abs(float(close) - float(anchor)) / max(float(close), 0.01)
            for anchor in [avg_price, pre_close, open_price]
            if anchor is not None and float(anchor) > 0
        ]
        nearest_anchor = min(anchor_distances) if anchor_distances else 999.0

        if (
            self.strategy.mainline_pullback_change_min <= float(change_pct or 0) <= self.strategy.mainline_pullback_change_max
            and float(close or 0) >= float(pre_close or 0) * self.strategy.mainline_pullback_close_floor_vs_preclose
            and close_quality >= self.strategy.mainline_pullback_close_quality_min
            and nearest_anchor <= self.strategy.mainline_pullback_anchor_gap_max
        ):
            return self.MAINLINE_PULLBACK_SOURCE_TAG

        if (
            self.strategy.mainline_low_suck_change_min <= float(change_pct or 0) <= self.strategy.mainline_low_suck_change_max
            and close_quality >= self.strategy.mainline_low_suck_close_quality_min
            and float(vol_ratio or 1.0) >= self.strategy.mainline_low_suck_min_vol_ratio
        ):
            return self.MAINLINE_LOW_SUCK_SOURCE_TAG

        return None

    def _mainline_recall_sort_key(
        self,
        source_tag: str,
        *,
        close: float,
        high: float,
        low: float,
        change_pct: float,
        amount: float,
        vol_ratio: Optional[float],
        avg_price: Optional[float],
        pre_close: float,
        open_price: float,
    ) -> tuple:
        close_quality = self._close_quality_from_row(close, low, high)
        anchor_distances = [
            abs(float(close) - float(anchor)) / max(float(close), 0.01)
            for anchor in [avg_price, pre_close, open_price]
            if anchor is not None and float(anchor) > 0
        ]
        nearest_anchor = min(anchor_distances) if anchor_distances else 999.0
        if source_tag == self.MAINLINE_PULLBACK_SOURCE_TAG:
            return (
                -nearest_anchor,
                -abs(float(change_pct or 0) - 1.5),
                close_quality,
                float(amount or 0),
                float(vol_ratio or 1.0),
            )
        return (
            close_quality,
            float(vol_ratio or 1.0),
            -abs(float(change_pct or 0)),
            float(amount or 0),
            -nearest_anchor,
        )

    def _build_mainline_pullback_candidates(
        self,
        trade_date: str,
        sector_scan,
        existing_stocks: List[StockInput],
    ) -> List[StockInput]:
        target_specs = self._iter_mainline_sector_targets(sector_scan)
        if not target_specs:
            return []

        payload = market_data_gateway.fetch_recent_stock_daily_df(trade_date)
        df = payload.get("df")
        if df is None or bool(getattr(df, "empty", False)):
            return []

        stock_meta_map = market_data_gateway.get_stock_basic_snapshot_map()
        data_trade_date = str(payload.get("data_trade_date") or str(trade_date).replace("-", ""))
        daily_basic_df = market_data_gateway.get_daily_basic_df(
            trade_date=data_trade_date,
            fields="ts_code,turnover_rate,volume_ratio",
        )

        source_df = market_data_gateway.build_daily_stock_source_df(
            df,
            stock_meta_map,
            daily_basic_df=daily_basic_df,
        )
        if source_df is None or source_df.empty:
            return []

        existing_codes = {
            market_data_gateway.normalize_ts_code(stock.ts_code)
            for stock in existing_stocks
        }
        concept_cache: Dict[str, List[str]] = {}
        grouped: Dict[str, Dict[str, List[tuple[tuple, StockInput]]]] = {
            name: {
                self.MAINLINE_PULLBACK_SOURCE_TAG: [],
                self.MAINLINE_LOW_SUCK_SOURCE_TAG: [],
            }
            for name, _source_type in target_specs
        }

        for _, row in source_df.iterrows():
            ts_code = str(row.get("ts_code") or "").strip()
            if not ts_code or not is_sector_scan_board_eligible(ts_code):
                continue
            normalized = market_data_gateway.normalize_ts_code(ts_code)
            if normalized in existing_codes:
                continue

            stock_name = str(row.get("stock_name") or ts_code).strip()
            if "ST" in stock_name.upper():
                continue

            close = float(row.get("close") or 0)
            high = float(row.get("high") or 0)
            low = float(row.get("low") or 0)
            open_price = float(row.get("open") or 0)
            pre_close = float(row.get("pre_close") or 0)
            amount = float(row.get("amount") or 0)
            if min(close, high, low, open_price, pre_close) <= 0:
                continue
            if close < 2.0 or amount < 30000:
                continue

            industry = str(row.get("industry") or "未知").strip() or "未知"
            concept_names = concept_cache.get(normalized)
            if concept_names is None:
                concept_names = tushare_client._get_ths_concept_names_for_stock(ts_code)
                concept_cache[normalized] = concept_names

            matched_name = None
            for name, source_type in target_specs:
                if source_type == "concept":
                    if name in concept_names:
                        matched_name = name
                        break
                elif industry == name:
                    matched_name = name
                    break
            if not matched_name:
                continue

            change_pct = float(row.get("pct_change") or 0)
            vol_ratio = row.get("volume_ratio")
            avg_price = row.get("avg_price")
            source_tag = self._classify_mainline_recall_source(
                close=close,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=pre_close,
                change_pct=change_pct,
                avg_price=float(avg_price) if avg_price is not None else None,
                vol_ratio=float(vol_ratio) if vol_ratio is not None else None,
            )
            if not source_tag:
                continue

            candidate = StockInput(
                ts_code=ts_code,
                stock_name=stock_name,
                sector_name=matched_name,
                close=close,
                change_pct=change_pct,
                turnover_rate=float(row.get("turnover_rate") or 0),
                amount=amount,
                vol_ratio=float(vol_ratio) if vol_ratio is not None else None,
                high=high,
                low=low,
                open=open_price,
                pre_close=pre_close,
                trend_tag="上升" if close >= pre_close else "震荡",
                stage_tag="回调" if source_tag == self.MAINLINE_PULLBACK_SOURCE_TAG else "启动",
                candidate_source_tag=source_tag,
                volume=float(row.get("volume") or 0) if row.get("volume") is not None else None,
                avg_price=float(avg_price) if avg_price is not None else None,
                quote_time=row.get("quote_time"),
                data_source="daily",
                concept_names=list(concept_names or []),
            )
            grouped.setdefault(matched_name, {}).setdefault(source_tag, []).append(
                (
                    self._mainline_recall_sort_key(
                        source_tag,
                        close=close,
                        high=high,
                        low=low,
                        change_pct=change_pct,
                        amount=amount,
                        vol_ratio=float(vol_ratio) if vol_ratio is not None else None,
                        avg_price=float(avg_price) if avg_price is not None else None,
                        pre_close=pre_close,
                        open_price=open_price,
                    ),
                    candidate,
                )
            )

        extras: List[StockInput] = []
        for name, _source_type in target_specs:
            buckets = grouped.get(name) or {}
            pullback_rows = list(buckets.get(self.MAINLINE_PULLBACK_SOURCE_TAG) or [])
            low_suck_rows = list(buckets.get(self.MAINLINE_LOW_SUCK_SOURCE_TAG) or [])
            pullback_rows.sort(key=lambda item: item[0], reverse=True)
            low_suck_rows.sort(key=lambda item: item[0], reverse=True)
            extras.extend(
                candidate
                for _score, candidate in pullback_rows[: self.strategy.mainline_pullback_per_sector_limit]
            )
            extras.extend(
                candidate
                for _score, candidate in low_suck_rows[: self.strategy.mainline_low_suck_per_sector_limit]
            )
        return extras

    def get_candidate_stocks(
        self,
        trade_date: str,
        top_gainers: int,
        holdings_list: Optional[List[dict]] = None,
        include_holdings: bool = False,
        prefer_today: bool = False,
        sector_scan=None,
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
        stocks = self._merge_candidate_stocks(
            stocks,
            self._build_mainline_pullback_candidates(
                trade_date,
                sector_scan,
                stocks,
            ),
        )

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
        realtime_sector_scan = sector_scan
        if self._should_build_realtime_confirmation_context(trade_date, selection_trade_date):
            try:
                realtime_sector_scan = sector_scan_service.scan(
                    trade_date,
                    limit_output=False,
                    market_env=realtime_market_env,
                    prefer_today=True,
                )
            except TypeError:
                realtime_sector_scan = sector_scan_service.scan(
                    trade_date,
                    limit_output=False,
                    market_env=realtime_market_env,
                )
        candidate_payload = self.get_candidate_stocks(
            selection_trade_date,
            top_gainers=top_gainers,
            holdings_list=None,
            include_holdings=False,
            sector_scan=sector_scan,
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
            realtime_sector_scan=realtime_sector_scan,
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
            realtime_sector_scan=shared_context.realtime_sector_scan,
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
