"""
买点分析服务
"""
from typing import Dict, List, Optional, Tuple

from app.data.tushare_client import normalize_ts_code, tushare_client
from app.models.schemas import (
    StockInput,
    StockOutput,
    BuyPointOutput,
    BuyPointResponse,
    BuyPointType,
    BuySignalTag,
    MarketEnvTag,
    RiskLevel,
    StockStrengthTag,
    StockContinuityTag,
    StockCoreTag,
    StockTradeabilityTag,
    NextTradeabilityTag,
    AccountInput,
    StockPoolTag,
    StockPoolsOutput,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service
from app.services.account_adapter import AccountAdapterService
from app.services.strategy_config import (
    BuyPointStrategyConfig,
    DEFAULT_BUY_POINT_STRATEGY,
)


class BuyPointService:
    """买点分析服务"""

    def __init__(self, strategy: Optional[BuyPointStrategyConfig] = None):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service
        self.stock_filter_service = stock_filter_service
        self.strategy = strategy or DEFAULT_BUY_POINT_STRATEGY

    def _bucket_structure_bonus(self, bucket_tag: Optional[str]) -> float:
        bucket = str(bucket_tag or "").strip()
        if bucket == "强势确认":
            return 2.0
        if bucket == "趋势回踩":
            return 0.5
        if bucket == "异动预备":
            return -3.0
        return 0.0

    def _summarize_sector_list(self, sectors, limit: int = 3):
        if not sectors:
            return []
        return list(sectors[:limit])

    def _stock_direction_candidates(self, stock) -> List[str]:
        names: List[str] = []
        for name in getattr(stock, "concept_names", []) or []:
            name_s = str(name or "").strip()
            if name_s and name_s not in names:
                names.append(name_s)
        sector_name = str(getattr(stock, "sector_name", "") or "").strip()
        if sector_name and sector_name not in names:
            names.append(sector_name)
        return names

    def _build_direction_context(self, sector_scan=None, stock_pools: Optional[StockPoolsOutput] = None) -> Dict[str, List[object]]:
        context_source = stock_pools or sector_scan
        return {
            "theme_leaders": list(getattr(context_source, "theme_leaders", []) or []),
            "industry_leaders": list(getattr(context_source, "industry_leaders", []) or []),
            "mainline_sectors": list(getattr(context_source, "mainline_sectors", []) or []),
            "sub_mainline_sectors": list(getattr(context_source, "sub_mainline_sectors", []) or []),
        }

    def _resolve_direction_match(self, stock: StockOutput, direction_context: Dict[str, List[object]]) -> Dict[str, Optional[str]]:
        candidates = self._stock_direction_candidates(stock)
        if not candidates:
            return {
                "direction_match_name": None,
                "direction_match_source_type": None,
                "direction_match_role": None,
                "direction_match_note": None,
            }

        ordered_groups = [
            ("theme", direction_context.get("theme_leaders", []), "命中主线题材"),
            ("industry", direction_context.get("industry_leaders", []), "命中承接行业"),
            ("mainline", direction_context.get("mainline_sectors", []), "命中主线候选"),
            ("sub_mainline", direction_context.get("sub_mainline_sectors", []), "命中次主线候选"),
        ]
        for role, rows, note_prefix in ordered_groups:
            sector_map = {
                str(getattr(row, "sector_name", "") or "").strip(): row
                for row in rows or []
                if str(getattr(row, "sector_name", "") or "").strip()
            }
            for candidate in candidates:
                sector = sector_map.get(candidate)
                if not sector:
                    continue
                sector_name = str(getattr(sector, "sector_name", "") or "").strip() or candidate
                source_type = str(getattr(sector, "sector_source_type", "") or "").strip() or None
                return {
                    "direction_match_name": sector_name,
                    "direction_match_source_type": source_type,
                    "direction_match_role": role,
                    "direction_match_note": f"{note_prefix} {sector_name}",
                }

        return {
            "direction_match_name": None,
            "direction_match_source_type": None,
            "direction_match_role": None,
            "direction_match_note": None,
        }

    def _attach_direction_match(
        self,
        buy_point: BuyPointOutput,
        stock: StockOutput,
        direction_context: Dict[str, List[object]],
    ) -> BuyPointOutput:
        match_info = self._resolve_direction_match(stock, direction_context)
        buy_point.direction_match_name = match_info["direction_match_name"]
        buy_point.direction_match_source_type = match_info["direction_match_source_type"]
        buy_point.direction_match_role = match_info["direction_match_role"]
        buy_point.direction_match_note = match_info["direction_match_note"]
        return buy_point

    def _direction_match_rank_bonus(self, point: BuyPointOutput) -> float:
        role = str(point.direction_match_role or "").strip()
        if role == "theme":
            return 3.0
        if role == "industry":
            return 2.0
        if role == "mainline":
            return 1.0
        if role == "sub_mainline":
            return 0.5
        return 0.0

    def analyze(
        self,
        trade_date: str,
        stocks: List[StockInput],
        account: Optional[AccountInput] = None,
        market_env=None,
        sector_scan=None,
        scored_stocks: Optional[List[StockOutput]] = None,
        stock_pools: Optional[StockPoolsOutput] = None,
        review_bias_profile: Optional[Dict] = None,
    ) -> BuyPointResponse:
        """
        买点分析

        Args:
            trade_date: 交易日
            stocks: 候选个股列表

        Returns:
            买点分析结果
        """
        # 获取市场环境
        market_env = market_env or self.market_env_service.get_current_env(trade_date)

        # 筛选评分
        scored_stocks = scored_stocks or self.stock_filter_service.filter_with_context(
            trade_date,
            stocks,
            market_env=market_env,
            sector_scan=sector_scan,
        )
        stock_pools = stock_pools or self.stock_filter_service.classify_pools(
            trade_date,
            stocks,
            holdings=[],
            account=account,
            market_env=market_env,
            sector_scan=sector_scan,
            scored_stocks=scored_stocks,
            review_bias_profile=review_bias_profile,
        )
        pool_tag_by_code = {}
        execution_reference_by_code = {}
        for stock in stock_pools.market_watch_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.MARKET_WATCH
            execution_reference_by_code[normalize_ts_code(stock.ts_code)] = stock
        for stock in stock_pools.account_executable_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.ACCOUNT_EXECUTABLE
            execution_reference_by_code[normalize_ts_code(stock.ts_code)] = stock
        for stock in stock_pools.holding_process_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.HOLDING_PROCESS
        direction_context = self._build_direction_context(sector_scan=sector_scan, stock_pools=stock_pools)

        # 分析每个股票的买点
        available = []   # 可买
        observe = []    # 观察
        not_buy = []    # 不买
        analyzed_count = 0
        display_quote_map = self._build_display_quote_map(trade_date, scored_stocks)

        for stock in scored_stocks:
            stock.stock_pool_tag = pool_tag_by_code.get(stock.ts_code, StockPoolTag.NOT_IN_POOL)
            self._attach_execution_reference_from_pool(
                stock,
                execution_reference_by_code.get(normalize_ts_code(stock.ts_code)),
            )
            if stock.stock_pool_tag == StockPoolTag.HOLDING_PROCESS:
                continue

            buy_point = self._analyze_stock_buy_point(stock, market_env, account, review_bias_profile)
            buy_point = self._attach_direction_match(buy_point, stock, direction_context)
            buy_point = self._apply_display_quote(buy_point, stock, display_quote_map)
            buy_point = self._downgrade_far_from_trigger_available(buy_point, stock)
            buy_point = self._apply_recommended_order_sizing(buy_point, stock, market_env, account)
            analyzed_count += 1

            if (
                buy_point.buy_signal_tag == BuySignalTag.CAN_BUY
                and stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE
            ):
                available.append(buy_point)
            elif (
                buy_point.buy_signal_tag == BuySignalTag.OBSERVE
                and stock.stock_pool_tag in {
                StockPoolTag.MARKET_WATCH,
                StockPoolTag.ACCOUNT_EXECUTABLE,
                }
            ):
                observe.append(buy_point)
            else:
                not_buy.append(buy_point)

        available.sort(key=lambda point: self._buy_point_rank_key(point, market_env), reverse=True)
        observe.sort(key=lambda point: self._buy_point_rank_key(point, market_env), reverse=True)
        not_buy.sort(key=lambda point: self._buy_point_rank_key(point, market_env), reverse=True)

        return BuyPointResponse(
            trade_date=trade_date,
            market_env_tag=market_env.market_env_tag,
            theme_leaders=self._summarize_sector_list(direction_context.get("theme_leaders", []), 3),
            industry_leaders=self._summarize_sector_list(direction_context.get("industry_leaders", []), 3),
            available_buy_points=available[:self.strategy.max_available],
            observe_buy_points=observe[:self.strategy.max_observe],
            not_buy_points=not_buy[:self.strategy.max_not_buy],
            total_count=analyzed_count
        )

    def _build_display_quote_map(
        self,
        trade_date: str,
        stocks: List[StockOutput],
    ) -> Dict[str, Dict]:
        """为买点展示层批量准备实时行情，不改变三池/评分口径。"""
        if not stocks or not tushare_client._should_use_realtime_quote(trade_date):
            return {}
        return tushare_client._fetch_realtime_stock_quote_map([stock.ts_code for stock in stocks])

    def _apply_display_quote(
        self,
        buy_point: BuyPointOutput,
        stock: StockOutput,
        display_quote_map: Dict[str, Dict],
    ) -> BuyPointOutput:
        """仅覆盖展示层的最新价、涨跌幅和时间戳。"""
        realtime = display_quote_map.get(normalize_ts_code(stock.ts_code))
        if not realtime:
            return buy_point

        current_price = round(realtime["close"], 2) if realtime.get("close") else None
        current_change_pct = (
            round(realtime["change_pct"], 2)
            if realtime.get("change_pct") is not None
            else None
        )
        buy_point.buy_current_price = current_price
        buy_point.buy_current_change_pct = current_change_pct
        buy_point.buy_quote_time = realtime.get("quote_time")
        buy_point.buy_data_source = realtime.get("data_source")
        buy_point.buy_trigger_gap_pct = self._price_gap_pct(
            current_price,
            buy_point.buy_trigger_price,
        )
        buy_point.execution_reference_gap_pct = self._price_gap_pct(
            current_price,
            buy_point.execution_reference_price,
        )
        buy_point.buy_invalid_gap_pct = self._price_gap_pct(
            current_price,
            buy_point.buy_invalid_price,
        )
        return buy_point

    def _downgrade_far_from_trigger_available(
        self,
        buy_point: BuyPointOutput,
        stock: StockOutput,
    ) -> BuyPointOutput:
        """
        可买列表强调“当前接近执行位”，不是“将来某个位置可买”。
        对回踩/低吸型，如果现价离执行位仍明显偏远，就降回观察。
        """
        if buy_point.buy_signal_tag != BuySignalTag.CAN_BUY:
            return buy_point
        if stock.stock_pool_tag != StockPoolTag.ACCOUNT_EXECUTABLE:
            return buy_point
        if buy_point.buy_point_type not in {BuyPointType.RETRACE_SUPPORT, BuyPointType.LOW_SUCK}:
            return buy_point
        gap_pct = (
            buy_point.execution_reference_gap_pct
            if buy_point.execution_reference_gap_pct is not None
            else buy_point.buy_trigger_gap_pct
        )
        if gap_pct is None:
            return buy_point
        if gap_pct >= self._available_trigger_gap_floor_pct(stock.ts_code):
            return buy_point

        buy_point.buy_signal_tag = BuySignalTag.OBSERVE
        if buy_point.buy_comment:
            buy_point.buy_comment = f"{buy_point.buy_comment}，现价离执行位仍偏远，先等回到计划位附近再看"
        else:
            buy_point.buy_comment = "现价离执行位仍偏远，先等回到计划位附近再看"
        buy_point.recommended_order_pct = None
        buy_point.recommended_order_amount = None
        buy_point.recommended_shares = None
        buy_point.recommended_lots = None
        buy_point.sizing_reference_price = None
        buy_point.sizing_note = None
        return buy_point

    def _available_trigger_gap_floor_pct(self, ts_code: str) -> float:
        """
        可买列表要求当前价离执行位足够近。
        返回的是 execution_reference_gap_pct 的下限，单位为百分比。
        例如 -1.5 代表当前价最多只能高出执行位约 1.5%。
        """
        code = str(ts_code or "").upper()
        if code.endswith(".BJ"):
            return -4.0
        if code.startswith(("300", "301", "688")):
            return -2.5
        return -1.5

    def _attach_execution_reference_from_pool(
        self,
        stock: StockOutput,
        pool_stock: Optional[StockOutput],
    ) -> None:
        if pool_stock is None:
            return
        stock.execution_reference_price = pool_stock.execution_reference_price
        stock.execution_reference_gap_pct = pool_stock.execution_reference_gap_pct
        stock.execution_proximity_tag = pool_stock.execution_proximity_tag
        stock.execution_proximity_note = pool_stock.execution_proximity_note

    def _apply_recommended_order_sizing(
        self,
        buy_point: BuyPointOutput,
        stock: StockOutput,
        market_env,
        account: Optional[AccountInput],
    ) -> BuyPointOutput:
        if not account or buy_point.buy_signal_tag != BuySignalTag.CAN_BUY:
            return buy_point
        if stock.stock_pool_tag != StockPoolTag.ACCOUNT_EXECUTABLE:
            return buy_point

        order_pct = self._resolve_recommended_order_pct(stock, market_env)
        current_price = buy_point.buy_current_price
        if current_price is None or current_price <= 0 or order_pct <= 0:
            return buy_point

        total_asset = float(getattr(account, "total_asset", 0) or 0)
        available_cash = max(float(getattr(account, "available_cash", 0) or 0), 0.0)
        if total_asset <= 0 or available_cash <= 0:
            return buy_point

        effective_order_pct = min(order_pct, available_cash / total_asset if total_asset > 0 else 0.0)
        if effective_order_pct <= 0:
            return buy_point

        lot_size = 100
        lot_cost = float(current_price) * lot_size
        if lot_cost <= 0:
            return buy_point

        desired_amount = min(total_asset * effective_order_pct, available_cash)
        lots = int(desired_amount // lot_cost)
        if lots <= 0:
            buy_point.recommended_order_pct = round(effective_order_pct, 4)
            buy_point.sizing_reference_price = round(float(current_price), 2)
            buy_point.sizing_note = (
                f"按当前价 {float(current_price):.2f} 测算，可用资金不足以买入 1 手（100 股），先不下单。"
            )
            return buy_point

        shares = lots * lot_size
        amount = round(shares * float(current_price), 2)
        buy_point.recommended_order_pct = round(effective_order_pct, 4)
        buy_point.recommended_order_amount = amount
        buy_point.recommended_shares = shares
        buy_point.recommended_lots = lots
        buy_point.sizing_reference_price = round(float(current_price), 2)
        buy_point.sizing_note = (
            f"按当前价 {float(current_price):.2f} 测算，并按 A 股 100 股整手取整；"
            f"建议先买 {shares} 股左右，预计占用 {amount:.2f} 元。"
        )
        return buy_point

    def _resolve_recommended_order_pct(self, stock: StockOutput, market_env) -> float:
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        entry_mode = str(getattr(stock, "account_entry_mode", "") or "")
        if entry_mode == "defense_trial":
            return 0.1
        if entry_mode == "aggressive_trial":
            return 0.1 if market_env.market_env_tag != MarketEnvTag.ATTACK else 0.15
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return 0.1
        if market_profile == "弱中性":
            return 0.1
        if market_profile == "中性偏谨慎":
            return 0.12
        if market_profile == "中性偏强":
            return 0.18
        if market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            return 0.15
        return 0.2

    def _analyze_stock_buy_point(
        self,
        stock: StockOutput,
        market_env,
        account: Optional[AccountInput] = None,
        review_bias_profile: Optional[Dict] = None,
    ) -> BuyPointOutput:
        """
        分析单个股票的买点

        Args:
            stock: 评分后的个股
            market_env: 市场环境

        Returns:
            买点分析结果
        """
        # 判断买点类型
        buy_type = self._determine_buy_type(stock, market_env)

        # 判断是否可买
        signal_tag = self._determine_buy_signal(stock, market_env, buy_type, account)

        # 生成触发/确认/失效条件
        trigger_price = self._estimate_trigger_price(stock, buy_type)
        invalid_price = self._estimate_invalid_price(stock, buy_type)
        trigger_cond = self._generate_trigger_cond(stock, buy_type, trigger_price)
        confirm_cond = self._generate_confirm_cond(stock, buy_type, trigger_price, invalid_price)
        invalid_cond = self._generate_invalid_cond(stock, buy_type)
        current_price = self._current_price(stock)
        current_change_pct = self._current_change_pct(stock)
        trigger_gap_pct = self._price_gap_pct(current_price, trigger_price)
        invalid_gap_pct = self._price_gap_pct(current_price, invalid_price)
        display_type = self._resolve_display_buy_point_type(stock, buy_type)
        execution_context = self._resolve_execution_context(stock)
        required_volume_ratio = self._required_volume_ratio(buy_type)
        requires_sector_resonance = self._requires_sector_resonance(buy_type)

        # 评估风险等级
        risk_level = self._assess_risk(stock, market_env, buy_type)

        # 评估账户适合度
        account_fit = self._assess_account_fit(stock, market_env, account)

        # 生成买点简评
        comment = self._generate_buy_comment(stock, buy_type, signal_tag)
        review_bias = self._resolve_review_bias(stock, signal_tag, review_bias_profile)

        return BuyPointOutput(
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            sector_name=stock.sector_name,
            candidate_source_tag=stock.candidate_source_tag,
            candidate_bucket_tag=stock.candidate_bucket_tag,
            stock_pool_tag=stock.stock_pool_tag.value if stock.stock_pool_tag else "",
            pool_entry_reason=stock.pool_entry_reason or "",
            account_entry_mode=stock.account_entry_mode or "",
            execution_reference_price=stock.execution_reference_price,
            execution_reference_gap_pct=stock.execution_reference_gap_pct,
            execution_proximity_tag=stock.execution_proximity_tag,
            execution_proximity_note=stock.execution_proximity_note,
            hard_filter_failed_rules=list(stock.hard_filter_failed_rules or []),
            hard_filter_failed_count=int(stock.hard_filter_failed_count or 0),
            hard_filter_pass_count=int(stock.hard_filter_pass_count or 0),
            hard_filter_summary=stock.hard_filter_summary or "",
            buy_signal_tag=signal_tag,
            buy_point_type=buy_type,
            buy_display_type=display_type,
            buy_execution_context=execution_context,
            buy_trigger_cond=trigger_cond,
            buy_confirm_cond=confirm_cond,
            buy_invalid_cond=invalid_cond,
            buy_current_price=current_price,
            buy_current_change_pct=current_change_pct,
            buy_quote_time=stock.quote_time,
            buy_data_source=stock.data_source,
            buy_trigger_price=trigger_price,
            buy_invalid_price=invalid_price,
            buy_trigger_gap_pct=trigger_gap_pct,
            buy_invalid_gap_pct=invalid_gap_pct,
            buy_required_volume_ratio=required_volume_ratio,
            buy_requires_sector_resonance=requires_sector_resonance,
            buy_risk_level=risk_level,
            buy_account_fit=account_fit,
            buy_comment=comment,
            recommended_order_pct=None,
            recommended_order_amount=None,
            recommended_shares=None,
            recommended_lots=None,
            sizing_reference_price=None,
            sizing_note=None,
            review_bias_score=review_bias["score"],
            review_bias_label=review_bias["label"],
            review_bias_reason=review_bias["reason"],
        )

    def _resolve_display_buy_point_type(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        tradeability_tag = self._normalize_next_tradeability_tag(stock.next_tradeability_tag)
        if (
            tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
            and buy_type == BuyPointType.RETRACE_SUPPORT
        ):
            return "突破后回踩"
        return buy_type.value

    def _resolve_execution_context(self, stock: StockOutput) -> str:
        tradeability_tag = self._normalize_next_tradeability_tag(stock.next_tradeability_tag)
        if tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            return "突破确认"
        if tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            return "回踩确认"
        if tradeability_tag == NextTradeabilityTag.LOW_SUCK:
            return "低吸预备"
        return tradeability_tag.value if tradeability_tag else ""

    def _normalize_next_tradeability_tag(
        self,
        value: Optional[NextTradeabilityTag | str],
    ) -> Optional[NextTradeabilityTag]:
        if isinstance(value, NextTradeabilityTag):
            return value
        raw = str(value or "").strip()
        if not raw:
            return None
        for item in NextTradeabilityTag:
            if raw in {item.name, item.value}:
                return item
        return None

    def _resolve_review_bias(
        self,
        stock: StockOutput,
        signal_tag: BuySignalTag,
        review_bias_profile: Optional[Dict],
    ) -> Dict:
        if not review_bias_profile:
            return {"score": 0.0, "label": None, "reason": None}

        snapshot_type = "buy_available" if signal_tag == BuySignalTag.CAN_BUY else "buy_observe"
        bucket = stock.candidate_bucket_tag or "未分层"
        exact = (review_bias_profile.get("exact") or {}).get((snapshot_type, bucket))
        bucket_entry = (review_bias_profile.get("bucket") or {}).get(bucket)
        entry = exact or bucket_entry
        if not entry:
            return {"score": 0.0, "label": None, "reason": None}
        return {
            "score": round(float(entry.get("score") or 0.0) + self._bucket_structure_bonus(bucket), 2),
            "label": entry.get("label"),
            "reason": (
                f"{entry.get('reason') or ''}"
                f"{' 结构修正：强势确认优先。' if bucket == '强势确认' else ''}"
                f"{' 结构修正：趋势回踩保留。' if bucket == '趋势回踩' else ''}"
                f"{' 结构修正：异动预备降权。' if bucket == '异动预备' else ''}"
            ).strip(),
        }

    def _buy_point_rank_key(self, point: BuyPointOutput, market_env=None):
        return (
            float(point.review_bias_score or 0),
            self._direction_match_rank_bonus(point),
            self._bucket_structure_bonus(point.candidate_bucket_tag),
            1 if point.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE.value else 0,
            self._buy_point_type_priority(point.buy_point_type, market_env),
            float(point.buy_current_change_pct or 0),
        )

    def _buy_point_type_priority(self, buy_point_type: BuyPointType, market_env=None) -> int:
        market_tag = getattr(market_env, "market_env_tag", None)
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        prefer_breakthrough = (
            market_tag == MarketEnvTag.ATTACK
            or market_profile in {"中性偏强", "中性偏进攻"}
        )
        if prefer_breakthrough:
            if buy_point_type == BuyPointType.BREAKTHROUGH:
                return 3
            if buy_point_type == BuyPointType.RETRACE_SUPPORT:
                return 2
            if buy_point_type == BuyPointType.LOW_SUCK:
                return 1
            return 0
        if buy_point_type == BuyPointType.RETRACE_SUPPORT:
            return 3
        if buy_point_type == BuyPointType.BREAKTHROUGH:
            return 2
        if buy_point_type == BuyPointType.LOW_SUCK:
            return 1
        return 0

    def _is_breakthrough_candidate(self, stock: StockOutput, market_env) -> bool:
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        if market_profile in {"中性偏谨慎", "弱中性"}:
            return False
        if not getattr(market_env, "breakout_allowed", False):
            return False
        if stock.stock_tradeability_tag != StockTradeabilityTag.TRADABLE:
            return False
        if self._has_upper_shadow_risk(stock):
            return False

        change_pct = float(stock.change_pct or 0)
        breakout_type_ceiling = self._breakthrough_type_ceiling_pct(stock.ts_code)
        if not (3.0 <= change_pct <= breakout_type_ceiling):
            return False

        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            return True

        return (
            stock.stock_strength_tag == StockStrengthTag.STRONG
            and stock.stock_core_tag == StockCoreTag.CORE
            and stock.stock_continuity_tag != StockContinuityTag.CAUTION
            and getattr(market_env, "market_env_tag", None) in {MarketEnvTag.ATTACK, MarketEnvTag.NEUTRAL}
        )

    def _determine_buy_type(self, stock: StockOutput, market_env) -> BuyPointType:
        """确定买点类型"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        breakout_quality_ok = self._is_breakthrough_candidate(stock, market_env)
        # 强势股 -> 突破
        if stock.stock_strength_tag == StockStrengthTag.STRONG:
            if breakout_quality_ok:
                return BuyPointType.BREAKTHROUGH
            if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
                return BuyPointType.LOW_SUCK
            if market_profile in {"中性偏谨慎", "弱中性"}:
                return BuyPointType.RETRACE_SUPPORT
            return BuyPointType.RETRACE_SUPPORT

        # 中等强度 -> 不再默认一刀切回踩
        if stock.stock_strength_tag == StockStrengthTag.MEDIUM:
            if (
                breakout_quality_ok
                and stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
                and stock.stock_core_tag in {StockCoreTag.CORE, StockCoreTag.FOLLOW}
            ):
                return BuyPointType.BREAKTHROUGH
            if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
                return BuyPointType.LOW_SUCK
            return BuyPointType.RETRACE_SUPPORT

        # 弱势 -> 修复转强（需要更多条件）
        return BuyPointType.REPAIR_STRENGTHEN

    def _determine_buy_signal(
        self,
        stock: StockOutput,
        market_env,
        buy_type: BuyPointType,
        account: Optional[AccountInput]
    ) -> BuySignalTag:
        """确定买点信号"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        if stock.stock_pool_tag == StockPoolTag.HOLDING_PROCESS:
            return BuySignalTag.NOT_BUY
        if stock.stock_pool_tag == StockPoolTag.NOT_IN_POOL:
            return BuySignalTag.NOT_BUY

        # 市场环境过滤
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            # 防守环境默认不开新仓，只给三池明确放行的极少数票轻仓试错
            if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE:
                if (
                    stock.stock_core_tag == StockCoreTag.CORE
                    and stock.stock_strength_tag == StockStrengthTag.STRONG
                    and "防守" in (stock.pool_entry_reason or "")
                ):
                    return BuySignalTag.CAN_BUY
                return BuySignalTag.OBSERVE
            if stock.stock_core_tag.value == "核心" and stock.stock_strength_tag == StockStrengthTag.STRONG:
                return BuySignalTag.OBSERVE
            return BuySignalTag.NOT_BUY

        if market_profile == "弱中性":
            if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE and stock.stock_core_tag == StockCoreTag.CORE:
                return BuySignalTag.OBSERVE
            return BuySignalTag.NOT_BUY

        # 交易性标签过滤
        if stock.stock_tradeability_tag.value == "不建议":
            return BuySignalTag.NOT_BUY

        if account and account.available_cash < AccountAdapterService.AVAILABLE_CASH_MIN:
            return BuySignalTag.NOT_BUY

        constrained_account = bool(
            account and (
                account.total_position_ratio >= AccountAdapterService.POSITION_MEDIUM
                or account.holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH
                or account.today_new_buy_count >= AccountAdapterService.NEW_BUY_COUNT_LIMIT
            )
        )

        if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE:
            if (
                buy_type == BuyPointType.RETRACE_SUPPORT
                and stock.stock_tradeability_tag in {
                    StockTradeabilityTag.TRADABLE,
                    StockTradeabilityTag.CAUTION,
                }
            ):
                if stock.stock_strength_tag in {StockStrengthTag.STRONG, StockStrengthTag.MEDIUM}:
                    return BuySignalTag.OBSERVE if constrained_account else BuySignalTag.CAN_BUY

        if stock.stock_tradeability_tag.value == "谨慎":
            return BuySignalTag.OBSERVE

        # 核心强势股 -> 可买
        if stock.stock_core_tag.value == "核心" and stock.stock_strength_tag == StockStrengthTag.STRONG:
            if stock.stock_pool_tag == StockPoolTag.MARKET_WATCH:
                return BuySignalTag.OBSERVE
            if constrained_account:
                return BuySignalTag.OBSERVE
            return BuySignalTag.CAN_BUY

        # 其他 -> 观察
        return BuySignalTag.OBSERVE

    def _generate_trigger_cond(
        self,
        stock: StockOutput,
        buy_type: BuyPointType,
        trigger_price: Optional[float] = None,
    ) -> str:
        """生成触发条件"""
        if buy_type == BuyPointType.BREAKTHROUGH:
            ref_price = trigger_price or self._estimate_trigger_price(stock, buy_type)
            day_high = stock.high or stock.close or stock.pre_close
            if ref_price and day_high:
                return (
                    f"放量突破当日高点 {day_high:.2f} 并站上触发价 {ref_price:.2f} 时触发"
                )
            if ref_price:
                return f"放量站上触发价 {ref_price:.2f} 时触发"
            return "放量突破关键压力位并站稳时触发"
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            anchor_label, anchor_price = self._resolve_retrace_anchor(stock, trigger_price)
            if anchor_label and anchor_price:
                if anchor_label == "执行位":
                    return f"先到执行位 {anchor_price:.2f} 附近再开始盯盘"
                return f"先等回踩到{anchor_label} {anchor_price:.2f} 附近企稳，再看承接"
            if trigger_price:
                return f"先等回踩到触发价 {trigger_price:.2f} 一带企稳，再看承接"
            return "先等回踩到关键支撑附近企稳，再看承接"
        elif buy_type == BuyPointType.LOW_SUCK:
            if trigger_price:
                return f"先等价格回到低吸参考位 {trigger_price:.2f} 附近止跌，再看试错"
            return "先等价格回到低吸参考位附近止跌，再看试错"
        else:
            if trigger_price:
                return f"先看能否重新站回触发价 {trigger_price:.2f} 并维持强势，再看转强确认"
            return "先看能否重新站回关键位并维持强势，再看转强确认"

    def _generate_confirm_cond(
        self,
        stock: StockOutput,
        buy_type: BuyPointType,
        trigger_price: Optional[float] = None,
        invalid_price: Optional[float] = None,
    ) -> str:
        """生成确认条件"""
        conds = []

        # 都需要量能配合
        conds.append("成交量放大至前一交易日1.2倍以上")

        if buy_type == BuyPointType.BREAKTHROUGH:
            if trigger_price:
                conds.append(f"突破后不回落到触发价 {trigger_price:.2f} 下方")
            else:
                conds.append("突破后不回落到关键位下方")
            conds.append("有板块或指数共振")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            anchor_label, anchor_price = self._resolve_retrace_anchor(stock, trigger_price)
            if anchor_label and anchor_price:
                if anchor_label == "执行位":
                    conds.append(f"先看能否靠近执行位 {anchor_price:.2f} 并重新站稳")
                else:
                    conds.append(f"回踩到{anchor_label} {anchor_price:.2f} 后收出止跌K线")
            elif trigger_price:
                conds.append(f"回踩到触发价 {trigger_price:.2f} 后收出止跌K线")
            else:
                conds.append("在支撑位收出止跌K线")
            if invalid_price:
                conds.append(f"分时企稳后不再跌回失效价 {invalid_price:.2f} 下方")
            else:
                conds.append("分时走势企稳")
        elif buy_type == BuyPointType.LOW_SUCK:
            if trigger_price:
                conds.append(f"靠近低吸参考位 {trigger_price:.2f} 时出现止跌承接")
            else:
                conds.append("靠近支撑时出现止跌承接")
            if invalid_price:
                conds.append(f"试错后不再跌回失效价 {invalid_price:.2f} 下方")
            else:
                conds.append("止跌后不再快速走弱")
        else:
            if trigger_price:
                conds.append(f"重新站回触发价 {trigger_price:.2f} 后维持强势")
            else:
                conds.append("出现明显反转信号")
            conds.append("板块整体回暖")

        return "；".join(conds)

    def _generate_invalid_cond(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        """生成失效条件"""
        conds = []

        # 通用失效条件
        conds.append("收盘跌破今日最低价，视为突破失败")
        conds.append("次日开盘跌破今日收盘价3%以上")

        if buy_type == BuyPointType.BREAKTHROUGH:
            conds.append("炸板（涨停被打开）")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            conds.append("跌破支撑位2%以上无法收回")

        # 个股特定失效
        if stock.stock_falsification_cond:
            conds.append(stock.stock_falsification_cond)

        return "；".join(conds[:3])  # 最多3条

    def _estimate_trigger_price(self, stock: StockOutput, buy_type: BuyPointType) -> Optional[float]:
        """估算结构化触发价格。"""
        if buy_type == BuyPointType.BREAKTHROUGH:
            base = stock.high or stock.close or stock.pre_close
            return round(base * 1.002, 2) if base else None
        if buy_type == BuyPointType.RETRACE_SUPPORT:
            tradeability_tag = self._normalize_next_tradeability_tag(stock.next_tradeability_tag)
            if (
                tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
                and stock.execution_reference_price
                and float(stock.execution_reference_price) > 0
            ):
                return round(float(stock.execution_reference_price), 2)
            _, base = self._preferred_retrace_anchor(stock)
            return round(base, 2) if base else None
        base = stock.close or stock.pre_close
        return round(base * 1.01, 2) if base else None

    def _estimate_invalid_price(self, stock: StockOutput, buy_type: BuyPointType) -> Optional[float]:
        """估算结构化失效价格。"""
        if buy_type == BuyPointType.BREAKTHROUGH:
            base = stock.low or stock.pre_close or stock.close
            return round(base, 2) if base else None
        if buy_type == BuyPointType.RETRACE_SUPPORT:
            base = stock.open or stock.low or stock.pre_close
            return round(base * 0.98, 2) if base else None
        base = stock.low or stock.close or stock.pre_close
        return round(base * 0.99, 2) if base else None

    def _resolve_retrace_anchor(
        self,
        stock: StockOutput,
        trigger_price: Optional[float],
    ) -> Tuple[Optional[str], Optional[float]]:
        """给回踩承接类文案找最近的锚点名称。"""
        if not trigger_price:
            return None, None

        candidates = self._preferred_retrace_anchor_candidates(stock)
        valid = [
            (label, float(price))
            for label, price in candidates
            if price is not None and float(price) > 0
        ]
        if not valid:
            return "触发价", round(float(trigger_price), 2)

        tolerance = max(0.02, abs(float(trigger_price)) * 0.001)
        for label, price in valid:
            if abs(price - float(trigger_price)) <= tolerance:
                return label, round(price, 2)
        label, price = min(valid, key=lambda item: abs(item[1] - float(trigger_price)))
        return label, round(price, 2)

    def _preferred_retrace_anchor(self, stock: StockOutput) -> Tuple[Optional[str], Optional[float]]:
        candidates = [
            (label, float(price))
            for label, price in self._preferred_retrace_anchor_candidates(stock)
            if price is not None and float(price) > 0
        ]
        if not candidates:
            return None, None
        return candidates[0][0], round(candidates[0][1], 2)

    def _preferred_retrace_anchor_candidates(
        self,
        stock: StockOutput,
    ) -> List[Tuple[str, Optional[float]]]:
        tradeability_tag = self._normalize_next_tradeability_tag(stock.next_tradeability_tag)
        candidates: List[Tuple[str, Optional[float]]] = []
        if (
            tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
            and stock.execution_reference_price
            and float(stock.execution_reference_price) > 0
        ):
            candidates.append(("执行位", stock.execution_reference_price))
        candidates.extend(
            [
                ("日内均价", stock.avg_price),
                ("前收价", stock.pre_close),
                ("开盘价", stock.open),
                ("最低价", stock.low),
            ]
        )
        return candidates

    def _required_volume_ratio(self, buy_type: BuyPointType) -> float:
        """返回结构化量能门槛。"""
        if buy_type == BuyPointType.BREAKTHROUGH:
            return 1.2
        if buy_type == BuyPointType.RETRACE_SUPPORT:
            return 1.1
        return 1.0

    def _current_price(self, stock: StockOutput) -> Optional[float]:
        """返回最新可用价格。"""
        price = stock.close or stock.pre_close or stock.open
        return round(price, 2) if price else None

    def _current_change_pct(self, stock: StockOutput) -> Optional[float]:
        """返回最新可用涨跌幅。"""
        return round(stock.change_pct, 2) if stock.change_pct is not None else None

    def _breakthrough_type_ceiling_pct(self, ts_code: Optional[str]) -> float:
        code = normalize_ts_code(ts_code or "")
        if code.endswith(".BJ"):
            return 14.0
        if code.startswith("300") or code.startswith("301") or code.startswith("688"):
            return 8.8
        return 7.4

    def _has_upper_shadow_risk(self, stock: StockOutput) -> bool:
        intraday_range = float((stock.high or 0) - (stock.low or 0))
        if intraday_range <= 0:
            return False
        upper_shadow = float((stock.high or 0) - max(float(stock.open or 0), float(stock.close or 0)))
        return upper_shadow / intraday_range >= 0.35

    def _price_gap_pct(self, current_price: Optional[float], target_price: Optional[float]) -> Optional[float]:
        """返回当前价到目标价的相对距离。"""
        if not current_price or not target_price:
            return None
        return round((target_price - current_price) / current_price * 100, 2)

    def _requires_sector_resonance(self, buy_type: BuyPointType) -> bool:
        """标记是否要求板块共振。"""
        return buy_type in {BuyPointType.BREAKTHROUGH, BuyPointType.REPAIR_STRENGTHEN}

    def _assess_risk(self, stock: StockOutput, market_env, buy_type: BuyPointType) -> RiskLevel:
        """评估风险等级"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        # 市场风险
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return RiskLevel.HIGH
        if market_profile in {"中性偏谨慎", "弱中性"}:
            return RiskLevel.HIGH if buy_type == BuyPointType.BREAKTHROUGH else RiskLevel.MEDIUM
        elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            return RiskLevel.MEDIUM

        # 买点类型风险
        if buy_type == BuyPointType.BREAKTHROUGH:
            # 突破本身风险较高
            if market_env.market_env_tag == MarketEnvTag.ATTACK:
                return RiskLevel.MEDIUM
            return RiskLevel.HIGH
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.MEDIUM

    def _assess_account_fit(
        self,
        stock: StockOutput,
        market_env,
        account: Optional[AccountInput]
    ) -> str:
        """评估账户适合度"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        if not account:
            return "一般"

        # 防守环境
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE:
                return "一般"
            return "不适合"
        if market_profile == "弱中性":
            return "一般" if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE else "不适合"
        if market_profile == "中性偏谨慎" and stock.stock_core_tag != StockCoreTag.CORE:
            return "一般"

        # 资金或仓位硬约束
        if account.available_cash < AccountAdapterService.AVAILABLE_CASH_MIN:
            return "不适合"
        if account.total_position_ratio >= AccountAdapterService.POSITION_HIGH:
            return "不适合"
        if (
            account.total_position_ratio >= AccountAdapterService.POSITION_MEDIUM
            or account.holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH
            or account.today_new_buy_count >= AccountAdapterService.NEW_BUY_COUNT_LIMIT
        ):
            return "一般"

        # 核心强势股
        if stock.stock_core_tag == StockCoreTag.CORE and stock.stock_strength_tag == StockStrengthTag.STRONG:
            # 还要看仓位
            if market_env.market_env_tag == MarketEnvTag.ATTACK:
                return "适合"
            if market_profile == "中性偏强":
                return "适合"
            return "一般"

        # 普通股票
        return "一般"

    def _generate_buy_comment(
        self,
        stock: StockOutput,
        buy_type: BuyPointType,
        signal_tag: BuySignalTag
    ) -> str:
        """生成买点简评"""
        comments = []

        # 买点类型
        if buy_type == BuyPointType.BREAKTHROUGH:
            comments.append("突破型买点")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            comments.append("回踩承接型")
        elif buy_type == BuyPointType.REPAIR_STRENGTHEN:
            comments.append("修复转强型")
        else:
            comments.append("低吸型")

        # 信号
        if signal_tag == BuySignalTag.CAN_BUY:
            comments.append("可执行")
        elif signal_tag == BuySignalTag.OBSERVE:
            comments.append("需观察")
        else:
            comments.append("不建议")

        if signal_tag == BuySignalTag.CAN_BUY and stock.stock_tradeability_tag == StockTradeabilityTag.NOT_RECOMMENDED:
            comments.append("防守试错")

        # 风险提示
        if stock.stock_continuity_tag.value == "末端谨慎":
            comments.append("注意末端风险")

        return "，".join(comments)


# 全局服务实例
buy_point_service = BuyPointService()
