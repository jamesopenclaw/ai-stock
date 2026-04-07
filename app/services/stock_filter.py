"""
个股筛选服务
"""
from typing import List, Dict, Optional
from loguru import logger

from app.models.schemas import (
    StockInput,
    StockOutput,
    StockStrengthTag,
    StockContinuityTag,
    StockTradeabilityTag,
    StockCoreTag,
    StockPoolTag,
    SectorProfileTag,
    StockRoleTag,
    RepresentativeRoleTag,
    DayStrengthTag,
    StructureStateTag,
    NextTradeabilityTag,
    StockPoolsOutput,
    GlobalTradeGateOutput,
    HoldingActionBucket,
    SectorMainlineTag,
    SectorTradeabilityTag,
    SectorTierTag,
    AccountInput,
    SellPointResponse,
    MarketEnvTag,
    TradeGateStatus,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.account_adapter import AccountAdapterService
from app.data.tushare_client import tushare_client, normalize_ts_code
from app.services.strategy_config import (
    DEFAULT_STOCK_FILTER_STRATEGY,
    StockFilterStrategyConfig,
)


def merge_holdings_into_candidate_stocks(
    trade_date: str,
    stocks: List[StockInput],
    holdings: Optional[List[Dict]],
) -> List[StockInput]:
    """
    将持仓标的并入候选行情列表。

    get_expanded_stock_list 合并涨幅前列/涨停/量比异动，持仓股仍可能不在其中；
    若不合并则 classify_pools 无法将其划入持仓处理池。
    """
    if not holdings:
        return stocks

    date_compact = trade_date.replace("-", "")
    stock_by_code = {normalize_ts_code(s.ts_code): s for s in stocks}
    seen = set(stock_by_code.keys())
    extra: List[StockInput] = []

    for h in holdings:
        raw = (h.get("ts_code") or "").strip()
        if not raw:
            continue
        tc = normalize_ts_code(raw)
        if tc in seen:
            existing = stock_by_code.get(tc)
            if existing and "持仓补齐" not in (existing.candidate_source_tag or ""):
                existing.candidate_source_tag = "/".join(
                    part for part in [existing.candidate_source_tag, "持仓补齐"] if part
                )
            continue
        try:
            detail = tushare_client.get_stock_detail(tc, date_compact)
        except Exception as e:
            logger.warning(f"合并持仓行情失败 {tc}: {e}")
            continue
        if not detail:
            continue

        extra.append(
            StockInput(
                ts_code=detail["ts_code"],
                stock_name=detail.get("stock_name") or h.get("stock_name") or tc,
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
                candidate_source_tag="持仓补齐",
                volume=detail.get("volume"),
                avg_price=detail.get("avg_price"),
                concept_names=detail.get("concept_names") or [],
                quote_time=detail.get("quote_time"),
                data_source=detail.get("data_source"),
            )
        )
        seen.add(tc)

    if not extra:
        return stocks
    return stocks + extra


class StockFilterService:
    """个股筛选服务"""

    def __init__(self, strategy: Optional[StockFilterStrategyConfig] = None):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service
        self.strategy = strategy or DEFAULT_STOCK_FILTER_STRATEGY
        self.HARD_FILTER_RULE_LABELS = dict(self.strategy.hard_filter_rule_labels)
        self.HARD_FILTER_FAIL_LABELS = dict(self.strategy.hard_filter_fail_labels)
        self.STRONG_CHANGE_THRESHOLD = self.strategy.strong_change_threshold
        self.MEDIUM_CHANGE_THRESHOLD = self.strategy.medium_change_threshold
        self.STRONG_SCORE_CONFIRM = self.strategy.strong_score_confirm
        self.MEDIUM_SCORE_THRESHOLD = self.strategy.medium_score_threshold
        self.HIGH_TURNOVER = self.strategy.high_turnover
        self.MEDIUM_TURNOVER = self.strategy.medium_turnover
        self.MIN_AMOUNT = self.strategy.min_amount
        self.MIN_CLOSE_PRICE = self.strategy.min_close_price
        self.WATCH_POOL_MIN_SCORE = self.strategy.watch_pool_min_score
        self.DEFENSE_TRIAL_MIN_SCORE = self.strategy.defense_trial_min_score
        self.PURE_EMOTION_AMOUNT_MAX = self.strategy.pure_emotion_amount_max
        self.HIGH_VOLATILITY_PCT = self.strategy.high_volatility_pct
        self.MARKET_WATCH_LIMIT = self.strategy.market_watch_limit
        self.MARKET_WATCH_PER_SECTOR_LIMIT = self.strategy.market_watch_per_sector_limit
        self.ACCOUNT_EXECUTABLE_LIMIT = self.strategy.account_executable_limit
        self.SECTOR_REPRESENTATIVE_LIMIT = self.strategy.sector_representative_limit

    def filter(self, trade_date: str, stocks: List[StockInput]) -> List[StockOutput]:
        return self.filter_with_context(trade_date, stocks)

    def filter_with_context(
        self,
        trade_date: str,
        stocks: List[StockInput],
        market_env=None,
        sector_scan=None,
        account: Optional[AccountInput] = None,
        holdings: Optional[List[Dict]] = None,
    ) -> List[StockOutput]:
        """
        个股筛选

        Args:
            trade_date: 交易日
            stocks: 个股列表

        Returns:
            筛选后的个股列表
        """
        # 获取市场环境和板块数据
        market_env = market_env or self.market_env_service.get_current_env(trade_date)
        sector_scan = sector_scan or self.sector_scan_service.scan(trade_date, limit_output=False)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 筛选评分
        result = []
        raw_stock_map = {}
        for stock in stocks:
            raw_stock_map[normalize_ts_code(stock.ts_code)] = stock
            if self._should_skip_stock(stock):
                continue
            output = self._score_stock(stock, market_env, sector_map)
            result.append(output)

        result = self._apply_hard_filters(
            result,
            raw_stock_map,
            market_env=market_env,
            account=account,
            holdings=holdings,
            sector_map=sector_map,
        )

        # 按综合分排序，涨幅作为次级排序键
        result.sort(key=lambda x: (x.stock_score, x.change_pct), reverse=True)

        return result

    def classify_pools(
        self,
        trade_date: str,
        stocks: List[StockInput],
        holdings: List[Dict] = None,
        account: Optional[AccountInput] = None,
        market_env=None,
        sector_scan=None,
        scored_stocks: Optional[List[StockOutput]] = None,
        review_bias_profile: Optional[Dict] = None,
    ) -> StockPoolsOutput:
        """
        三池分类

        Args:
            trade_date: 交易日
            stocks: 候选个股列表
            holdings: 当前持仓列表

        Returns:
            三池分类结果
        """
        scored_stocks = scored_stocks or self.filter_with_context(
            trade_date,
            stocks,
            market_env=market_env,
            sector_scan=sector_scan,
            account=account,
            holdings=holdings,
        )
        market_env = market_env or self.market_env_service.get_current_env(trade_date)
        sector_scan = sector_scan or self.sector_scan_service.scan(trade_date, limit_output=False)
        sector_map = self._build_sector_map(sector_scan)

        holding_codes = {
            normalize_ts_code((h.get("ts_code") or "").strip())
            for h in (holdings or [])
            if (h.get("ts_code") or "").strip()
        }
        raw_stock_map = {
            normalize_ts_code(stock.ts_code): stock
            for stock in stocks
        }
        holding_map = {
            normalize_ts_code((h.get("ts_code") or "").strip()): h
            for h in (holdings or [])
            if (h.get("ts_code") or "").strip()
        }
        scored_by_code = {
            normalize_ts_code(stock.ts_code): stock
            for stock in scored_stocks
        }
        holding_profile = self._build_holding_profile(
            holdings,
            account,
            raw_stock_map=raw_stock_map,
            scored_by_code=scored_by_code,
            sector_map=sector_map,
        )
        allowed_new_pool_profiles = self._resolve_new_pool_profiles(
            scored_stocks,
            holding_codes,
        )
        allowed_new_pool_sectors = self._resolve_new_pool_sector_names(
            sector_scan,
            scored_stocks,
            holding_codes,
            allowed_new_pool_profiles,
            market_env=market_env,
        )
        representative_codes = self._select_representative_codes(
            scored_stocks,
            holding_codes,
            allowed_new_pool_profiles,
            allowed_new_pool_sectors,
        )
        execution_priority_codes = self._select_account_executable_candidate_codes(
            scored_stocks,
            holding_codes,
            allowed_new_pool_profiles,
            allowed_new_pool_sectors,
        )
        holding_process = self.build_holding_process_pool(
            holding_codes,
            scored_by_code,
            raw_stock_map,
            holding_map,
            market_env,
            sector_map,
        )
        global_trade_gate = self.build_global_trade_gate(
            market_env,
            account,
            holding_process,
        )
        market_watch_candidates = self._build_market_watch_candidates(
            scored_stocks,
            holding_codes,
            allowed_new_pool_profiles,
            allowed_new_pool_sectors,
            representative_codes,
            execution_priority_codes,
            account,
            market_env,
            holding_profile,
            global_trade_gate,
            review_bias_profile=review_bias_profile,
        )
        market_watch = self._select_visible_market_watch(
            market_watch_candidates,
            allowed_sector_names=allowed_new_pool_sectors,
        )
        account_executable = self.build_account_executable_pool(
            market_watch_candidates,
            holding_codes,
            account,
            market_env,
            holding_profile,
            global_trade_gate,
            review_bias_profile=review_bias_profile,
        )

        return StockPoolsOutput(
            trade_date=trade_date,
            resolved_trade_date=None,
            global_trade_gate=global_trade_gate,
            market_watch_pool=market_watch,
            market_watch_candidates=market_watch_candidates,
            account_executable_pool=account_executable,
            holding_process_pool=holding_process,
            total_count=(
                len(market_watch)
                + len(account_executable)
                + len(holding_process)
            ),
        )

    def _select_visible_account_executable(
        self,
        account_executable: List[StockOutput],
        limit: int = 10,
    ) -> List[StockOutput]:
        """账户可参与池展示时保留强主线优先，但不给单一方向垄断全部席位。"""
        return self._rank_account_executable_candidates(account_executable, limit)

    def build_holding_process_pool(
        self,
        holding_codes: set[str],
        scored_by_code: Dict[str, StockOutput],
        raw_stock_map: Dict[str, StockInput],
        holding_map: Dict[str, Dict],
        market_env,
        sector_map: Dict,
    ) -> List[StockOutput]:
        """持仓池覆盖全部持仓，先按持仓问题输出，不参与账户新开仓清单。"""
        holding_process: List[StockOutput] = []
        for holding_code in holding_codes:
            scored = scored_by_code.get(holding_code)
            if not scored:
                raw_stock = raw_stock_map.get(holding_code)
                if not raw_stock:
                    continue
                scored = self._score_stock(raw_stock, market_env, sector_map)
            scored = self._apply_holding_context(scored, holding_map.get(holding_code))
            cloned = self._clone_for_pool(
                scored,
                StockPoolTag.HOLDING_PROCESS,
                why_this_pool="这是当前持仓，先回答今天该怎么处理，而不是给新的开仓答案。",
                not_other_pools=[
                    "持仓处理池优先回答旧仓动作。",
                    "当前已持仓，因此不进入账户可参与池。",
                ],
                pool_decision_summary="先看这只持仓对账户是贡献还是拖累，再决定卖、减、看还是强留。",
            )
            cloned.holding_action_bucket = self._assign_holding_action_bucket(cloned)
            holding_process.append(cloned)

        holding_process.sort(key=self._holding_process_sort_key)
        return holding_process

    def _build_market_watch_candidates(
        self,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        allowed_profiles: set[SectorProfileTag],
        allowed_sector_names: set[str],
        representative_codes: set[str],
        execution_priority_codes: set[str],
        account: Optional[AccountInput],
        market_env,
        holding_profile: Dict,
        global_trade_gate: GlobalTradeGateOutput,
        *,
        review_bias_profile: Optional[Dict] = None,
    ) -> List[StockOutput]:
        """观察池候选全集：先回答“值得盯谁”，再由展示层截断。"""
        market_watch: List[StockOutput] = []
        for stock in scored_stocks:
            normalized_code = normalize_ts_code(stock.ts_code)
            is_holding = normalized_code in holding_codes
            if not self._should_enter_market_watch(stock):
                continue
            if not is_holding:
                if not self._allows_new_pool_entry(stock, allowed_profiles, allowed_sector_names):
                    continue
                if (
                    representative_codes
                    and normalized_code not in representative_codes
                    and normalized_code not in execution_priority_codes
                ):
                    continue

            account_ok, account_reason, _, _ = self._evaluate_account_pool_candidate(
                stock,
                is_holding=is_holding,
                account=account,
                market_env=market_env,
                holding_profile=holding_profile,
                global_trade_gate=global_trade_gate,
            )
            why = self._why_market_watch(stock, is_holding=is_holding)
            market_watch.append(
                self._clone_for_pool(
                    stock,
                    StockPoolTag.MARKET_WATCH,
                    why_this_pool=why,
                    not_other_pools=self._build_not_other_pool_reasons(
                        StockPoolTag.MARKET_WATCH,
                        account_ok=account_ok,
                        account_reason=account_reason,
                        is_holding=is_holding,
                    ),
                    pool_decision_summary=self._build_pool_summary(
                        stock,
                        StockPoolTag.MARKET_WATCH,
                        why,
                    ),
                    review_bias_profile=review_bias_profile,
                )
            )

        return market_watch

    def build_market_watch_pool(
        self,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        allowed_profiles: set[SectorProfileTag],
        allowed_sector_names: set[str],
        representative_codes: set[str],
        execution_priority_codes: set[str],
        account: Optional[AccountInput],
        market_env,
        holding_profile: Dict,
        global_trade_gate: GlobalTradeGateOutput,
        *,
        review_bias_profile: Optional[Dict] = None,
    ) -> List[StockOutput]:
        """观察池只回答市场最强和值得盯的票。"""
        market_watch = self._build_market_watch_candidates(
            scored_stocks,
            holding_codes,
            allowed_profiles,
            allowed_sector_names,
            representative_codes,
            execution_priority_codes,
            account,
            market_env,
            holding_profile,
            global_trade_gate,
            review_bias_profile=review_bias_profile,
        )
        return self._select_visible_market_watch(
            market_watch,
            allowed_sector_names=allowed_sector_names,
        )

    def build_global_trade_gate(
        self,
        market_env,
        account: Optional[AccountInput],
        holding_process_pool: List[StockOutput],
    ) -> GlobalTradeGateOutput:
        """三池前的总闸门，统一约束今天是否该看新票。"""
        reasons: List[str] = []
        immediate_count = sum(
            1 for stock in holding_process_pool
            if stock.holding_action_bucket == HoldingActionBucket.IMMEDIATE
        )
        reduce_count = sum(
            1 for stock in holding_process_pool
            if stock.holding_action_bucket == HoldingActionBucket.REDUCE_FIRST
        )
        total_position_ratio = float(account.total_position_ratio or 0.0) if account else 0.0
        cash_ok = bool(account and account.available_cash >= AccountAdapterService.AVAILABLE_CASH_MIN)
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        discipline_ok = bool(
            not account
            or (
                account.today_new_buy_count < AccountAdapterService.NEW_BUY_COUNT_LIMIT
                and account.holding_count < AccountAdapterService.HOLDING_COUNT_HIGH
            )
        )

        if immediate_count > 0:
            reasons.append(f"持仓池存在{immediate_count}只立即处理票，旧仓优先级高于新机会。")
        if reduce_count >= 2 and total_position_ratio >= AccountAdapterService.POSITION_LOW:
            reasons.append("持仓池出现多只优先减仓票，且当前仓位不轻。")
        if reasons:
            return GlobalTradeGateOutput(
                status=TradeGateStatus.HOLDINGS_FIRST,
                allow_new_positions=False,
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=0,
            )

        if market_env.market_env_tag == MarketEnvTag.ATTACK and total_position_ratio < AccountAdapterService.POSITION_LOW and cash_ok and discipline_ok:
            reasons.append("市场环境进攻，账户仓位不重，允许按计划主动筛选新票。")
            return GlobalTradeGateOutput(
                status=TradeGateStatus.ATTACK,
                allow_new_positions=True,
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=self.ACCOUNT_EXECUTABLE_LIMIT,
            )

        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            reasons.append("市场环境偏防守，新开仓只能保留极少数高确定性试错。")
            return GlobalTradeGateOutput(
                status=TradeGateStatus.DEFENSE,
                allow_new_positions=bool(cash_ok and total_position_ratio < AccountAdapterService.POSITION_MEDIUM),
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=1 if cash_ok else 0,
            )

        if market_profile == "弱中性":
            reasons.append("市场弱中性，先压缩新开仓，只保留最强确认机会。")
            return GlobalTradeGateOutput(
                status=TradeGateStatus.TRIAL,
                allow_new_positions=bool(cash_ok and discipline_ok and total_position_ratio < AccountAdapterService.POSITION_MEDIUM),
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=1 if cash_ok else 0,
            )

        if market_profile == "中性偏谨慎":
            reasons.append("市场中性偏谨慎，允许试错，但只做低吸或回踩确认。")
            return GlobalTradeGateOutput(
                status=TradeGateStatus.TRIAL,
                allow_new_positions=bool(cash_ok and discipline_ok),
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=2 if cash_ok else 0,
            )

        if market_profile == "中性偏强":
            reasons.append("市场中性偏强，可围绕主线做确认后的试错。")
            return GlobalTradeGateOutput(
                status=TradeGateStatus.TRIAL,
                allow_new_positions=bool(cash_ok),
                dominant_reason=reasons[0],
                reasons=reasons,
                account_pool_limit=4 if cash_ok else 0,
            )

        reasons.append("环境与账户都不算极端，允许试错但先过账户过滤。")
        if total_position_ratio >= AccountAdapterService.POSITION_MEDIUM:
            reasons.append("当前仓位偏高，账户池数量需要收缩。")
        if not discipline_ok:
            reasons.append("当日节奏或持仓数量偏满，优先控制新开仓数量。")
        return GlobalTradeGateOutput(
            status=TradeGateStatus.TRIAL,
            allow_new_positions=bool(cash_ok),
            dominant_reason=reasons[0],
            reasons=reasons,
            account_pool_limit=3 if cash_ok else 0,
        )

    def build_account_executable_pool(
        self,
        market_watch_pool: List[StockOutput],
        holding_codes: set[str],
        account: Optional[AccountInput],
        market_env,
        holding_profile: Dict,
        global_trade_gate: GlobalTradeGateOutput,
        *,
        review_bias_profile: Optional[Dict] = None,
    ) -> List[StockOutput]:
        """账户池只从观察池前排里筛，回答当前账户现在能做谁。"""
        if not global_trade_gate.allow_new_positions or global_trade_gate.account_pool_limit <= 0:
            return []

        account_executable: List[StockOutput] = []
        for stock in market_watch_pool:
            normalized_code = normalize_ts_code(stock.ts_code)
            if normalized_code in holding_codes:
                continue

            account_ok, account_reason, account_position_hint, account_entry_mode = self._evaluate_account_pool_candidate(
                stock,
                is_holding=False,
                account=account,
                market_env=market_env,
                holding_profile=holding_profile,
                global_trade_gate=global_trade_gate,
            )
            if not account_ok:
                continue

            account_clone = self._clone_for_pool(
                stock,
                StockPoolTag.ACCOUNT_EXECUTABLE,
                why_this_pool=account_reason,
                not_other_pools=self._build_not_other_pool_reasons(
                    StockPoolTag.ACCOUNT_EXECUTABLE,
                    account_ok=account_ok,
                    account_reason=account_reason,
                    is_holding=False,
                ),
                pool_decision_summary=self._build_pool_summary(
                    stock,
                    StockPoolTag.ACCOUNT_EXECUTABLE,
                    account_reason,
                ),
                review_bias_profile=review_bias_profile,
            )
            account_clone.account_entry_mode = account_entry_mode
            account_clone.pool_entry_reason = account_reason
            account_clone.position_hint = account_position_hint
            self._annotate_execution_proximity(account_clone)
            account_executable.append(account_clone)

        return self._select_visible_account_executable(
            account_executable,
            limit=global_trade_gate.account_pool_limit,
        )

    def _select_visible_market_watch(
        self,
        market_watch: List[StockOutput],
        *,
        allowed_sector_names: set[str],
    ) -> List[StockOutput]:
        """观察池按强度排序后，再做单方向数量控制。"""
        ranked = sorted(
            market_watch,
            key=lambda stock: (
                self._market_watch_vote_count(stock),
                float(stock.review_bias_score or 0),
                self._representative_total_score(stock),
                float(stock.market_strength_score or 0),
                float(stock.stock_score or 0),
            ),
            reverse=True,
        )
        visible: List[StockOutput] = []
        sector_counts: Dict[str, int] = {}
        for stock in ranked:
            sector_key = self._market_watch_sector_key(stock, allowed_sector_names)
            current_count = sector_counts.get(sector_key, 0)
            if current_count >= self.MARKET_WATCH_PER_SECTOR_LIMIT:
                continue
            visible.append(stock)
            sector_counts[sector_key] = current_count + 1
            if len(visible) >= self.MARKET_WATCH_LIMIT:
                break
        return visible

    def _market_watch_sector_key(self, stock: StockOutput, allowed_sector_names: set[str]) -> str:
        matched = self._resolve_allowed_sector_name_for_stock(stock, allowed_sector_names)
        return matched or str(stock.sector_name or "未标记方向")

    def _evaluate_account_pool_candidate(
        self,
        stock: StockOutput,
        *,
        is_holding: bool,
        account: Optional[AccountInput],
        market_env,
        holding_profile: Dict,
        global_trade_gate: GlobalTradeGateOutput,
    ) -> tuple[bool, str, Optional[str], Optional[str]]:
        if is_holding:
            return False, "当前已持仓，三池里的账户可参与池不重复回答加仓问题。", None, None
        if not global_trade_gate.allow_new_positions or global_trade_gate.account_pool_limit <= 0:
            return False, global_trade_gate.dominant_reason, None, None

        account_ok, account_reason, account_position_hint, account_entry_mode = self._should_enter_account_pool(
            stock,
            account,
            market_env,
        )
        if not account_ok:
            return False, account_reason or "当前不满足账户可参与条件。", None, None

        holding_ok, holding_reason, holding_position_extra, holding_score_delta = self._assess_holding_fit(
            stock,
            holding_profile,
            account,
        )
        if not holding_ok:
            return False, holding_reason or "当前持仓结构不适合新增同方向仓位。", None, None

        if holding_reason:
            account_reason = " ".join(part for part in [account_reason, holding_reason] if part)
        account_position_hint = self._merge_position_hint(account_position_hint, holding_position_extra)

        if account_entry_mode == "defense_trial":
            if holding_score_delta:
                stock.account_entry_score = round(
                    max(0.0, float(stock.account_entry_score or 0) + holding_score_delta),
                    1,
                )
            return True, account_reason, account_position_hint, account_entry_mode

        account_vote_ok, account_vote_reason = self._passes_account_participation_gate(
            stock,
            account,
            holding_profile,
        )
        if not account_vote_ok:
            return False, account_vote_reason or "当前更像观察票，还不是账户最优执行答案。", None, None

        if global_trade_gate.status == TradeGateStatus.DEFENSE and account_entry_mode != "defense_trial":
            return False, "当前以防守为主，仅保留极少数高确定性轻仓试错票。", None, None

        if holding_score_delta:
            stock.account_entry_score = round(
                max(0.0, float(stock.account_entry_score or 0) + holding_score_delta),
                1,
            )
        return True, account_reason, account_position_hint, account_entry_mode

    def _assign_holding_action_bucket(self, stock: StockOutput) -> HoldingActionBucket:
        """将持仓处理池统一映射到四档动作。"""
        if stock.sell_signal_tag == "卖出":
            return HoldingActionBucket.IMMEDIATE
        if stock.sell_signal_tag == "减仓":
            return HoldingActionBucket.REDUCE_FIRST
        if stock.sell_signal_tag in {"持有", "观察"}:
            if (
                stock.sell_signal_tag == "持有"
                and stock.stock_core_tag == StockCoreTag.CORE
                and stock.stock_continuity_tag == StockContinuityTag.SUSTAINABLE
                and float(stock.market_strength_score or 0) >= 75
                and (stock.pnl_pct is None or float(stock.pnl_pct) >= 0)
            ):
                return HoldingActionBucket.HOLD_STRONG
            return HoldingActionBucket.OBSERVE

        pnl_pct = float(stock.pnl_pct or 0.0)
        if pnl_pct <= -5.0 or (
            stock.stock_continuity_tag == StockContinuityTag.CAUTION
            and stock.structure_state_tag == StructureStateTag.LATE_STAGE
        ):
            return HoldingActionBucket.IMMEDIATE
        if (
            pnl_pct >= 8.0
            or stock.day_strength_tag == DayStrengthTag.SPIKE_FADE
            or stock.stock_continuity_tag == StockContinuityTag.CAUTION
        ):
            return HoldingActionBucket.REDUCE_FIRST
        if (
            stock.stock_core_tag == StockCoreTag.CORE
            and stock.stock_continuity_tag == StockContinuityTag.SUSTAINABLE
            and stock.structure_state_tag in {
                StructureStateTag.START,
                StructureStateTag.DIVERGENCE,
                StructureStateTag.REPAIR,
            }
        ):
            return HoldingActionBucket.HOLD_STRONG
        return HoldingActionBucket.OBSERVE

    def _holding_process_sort_key(self, stock: StockOutput):
        bucket_order = {
            HoldingActionBucket.IMMEDIATE: 0,
            HoldingActionBucket.REDUCE_FIRST: 1,
            HoldingActionBucket.OBSERVE: 2,
            HoldingActionBucket.HOLD_STRONG: 3,
        }
        priority_order = {"高": 0, "中": 1, "低": 2, None: 3}
        pnl = abs(float(stock.pnl_pct or 0.0))
        return (
            bucket_order.get(stock.holding_action_bucket, 9),
            priority_order.get(stock.sell_priority, 3),
            -pnl,
            -float(stock.market_strength_score or 0),
            stock.ts_code,
        )

    def _resolve_new_pool_profiles(
        self,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
    ) -> set[SectorProfileTag]:
        """主线优先，但保留一个新强化方向的观察席位。"""
        available_profiles = {
            stock.sector_profile_tag
            for stock in scored_stocks
            if normalize_ts_code(stock.ts_code) not in holding_codes
            and self._is_new_pool_code_allowed(stock.ts_code)
        }
        if SectorProfileTag.A_MAINLINE in available_profiles:
            profiles = {SectorProfileTag.A_MAINLINE}
            if SectorProfileTag.B_SUB_MAINLINE in available_profiles and any(
                self._is_strengthening_direction_candidate(stock)
                for stock in scored_stocks
                if stock.sector_profile_tag == SectorProfileTag.B_SUB_MAINLINE
            ):
                profiles.add(SectorProfileTag.B_SUB_MAINLINE)
            return profiles
        if SectorProfileTag.B_SUB_MAINLINE in available_profiles:
            return {SectorProfileTag.B_SUB_MAINLINE}
        return set()

    def _allows_new_pool_entry(
        self,
        stock: StockOutput,
        allowed_profiles: set[SectorProfileTag],
        allowed_sector_names: set[str],
    ) -> bool:
        """新开仓三池只放行当前允许的主线档位。"""
        matched_visible_sector = self._resolve_allowed_sector_name_for_stock(
            stock,
            allowed_sector_names,
        )
        return (
            self._is_new_pool_code_allowed(stock.ts_code)
            and
            bool(allowed_profiles)
            and bool(allowed_sector_names)
            and stock.sector_profile_tag in allowed_profiles
            and bool(matched_visible_sector)
        )

    def _resolve_new_pool_sector_names(
        self,
        sector_scan,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        allowed_profiles: set[SectorProfileTag],
        market_env=None,
    ) -> set[str]:
        """三池新开仓范围以当前前排主线为主，并保留一个新强化方向。"""
        if not sector_scan or not allowed_profiles:
            return set()

        def _visible_names(rows: List[object], limit: int) -> List[str]:
            names: List[str] = []
            for row in list(rows or [])[:limit]:
                name = str(getattr(row, "sector_name", "") or "").strip()
                if name and name not in names:
                    names.append(name)
            return names

        candidate_names: List[str] = []
        if SectorProfileTag.A_MAINLINE in allowed_profiles:
            candidate_names.extend(_visible_names(getattr(sector_scan, "mainline_sectors", []), 5))
        if SectorProfileTag.B_SUB_MAINLINE in allowed_profiles:
            strengthening_names = self._select_strengthening_sector_names(
                getattr(sector_scan, "sub_mainline_sectors", []),
                scored_stocks,
                holding_codes,
                market_env=market_env,
            )
            for name in strengthening_names:
                if name not in candidate_names:
                    candidate_names.append(name)

        available_names = set()
        for stock in scored_stocks:
            if normalize_ts_code(stock.ts_code) in holding_codes:
                continue
            if not self._is_new_pool_code_allowed(stock.ts_code):
                continue
            if stock.sector_profile_tag not in allowed_profiles:
                continue
            available_names.update(
                {
                    name
                    for name in self._stock_sector_candidates(stock)
                    if name in candidate_names
                }
            )
        return {
            name for name in candidate_names
            if name in available_names
        }

    def _select_strengthening_sector_names(
        self,
        sectors: List[object],
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        market_env=None,
    ) -> List[str]:
        """从次主线里挑强化方向；进攻环境允许保留两个竞争中的强化席位。"""
        sector_by_name = {
            str(getattr(sector, "sector_name", "") or "").strip(): sector
            for sector in sectors or []
            if str(getattr(sector, "sector_name", "") or "").strip()
        }
        candidates: List[tuple[float, str, str]] = []
        for name, sector in sector_by_name.items():
            related = [
                stock for stock in scored_stocks
                if normalize_ts_code(stock.ts_code) not in holding_codes
                and self._is_new_pool_code_allowed(stock.ts_code)
                and name in self._stock_sector_candidates(stock)
            ]
            if not related:
                continue
            best = max(
                related,
                key=lambda stock: (
                    float(stock.market_strength_score or 0),
                    float(stock.execution_opportunity_score or 0),
                    float(stock.stock_score or 0),
                ),
            )
            sector_signal = self._infer_sector_rotation_state(sector)
            signal_boost = {
                "强化中": 18.0,
                "切换中": 14.0,
                "稳定主线": 4.0,
                "衰减中": -12.0,
            }.get(sector_signal, 0.0)
            score = (
                float(getattr(sector, "sector_score", 0.0) or 0.0)
                + float(best.market_strength_score or 0.0)
                + signal_boost
            )
            if self._is_strengthening_direction_candidate(best):
                score += 12.0
            candidates.append((score, name, sector_signal))

        candidates.sort(reverse=True)
        if not candidates:
            return []

        slot_limit = 1
        if (
            getattr(market_env, "market_env_tag", None) == MarketEnvTag.ATTACK
            and len(candidates) >= 2
        ):
            top_score = float(candidates[0][0] or 0.0)
            second_score = float(candidates[1][0] or 0.0)
            second_signal = candidates[1][2]
            if second_signal in {"强化中", "切换中"} and second_score >= top_score - 8.0:
                slot_limit = 2

        return [name for _, name, _ in candidates[:slot_limit]]

    def _resolve_allowed_sector_name_for_stock(
        self,
        stock: StockOutput,
        allowed_sector_names: set[str],
    ) -> Optional[str]:
        """返回股票命中的可见主线名，用于三池新开仓范围收口。"""
        if not stock or not allowed_sector_names:
            return None
        for name in self._stock_sector_candidates(stock):
            if name in allowed_sector_names:
                return name
        return None

    def _is_new_pool_code_allowed(self, ts_code: str) -> bool:
        """新开仓三池默认排除科创板和北交所股票。"""
        normalized = normalize_ts_code(str(ts_code or "").strip())
        if not normalized:
            return False

        code, _, market = normalized.partition(".")
        market = market.upper()

        if market == "BJ":
            return False
        if code.startswith("688"):
            return False
        # 兼容未带后缀的北交所原始代码。
        if code.startswith(("4", "8", "92")):
            return False
        return True

    def _select_representative_codes(
        self,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        allowed_profiles: set[SectorProfileTag],
        allowed_sector_names: set[str],
    ) -> set[str]:
        """每条主线先压缩为 2-4 只代表票，再参与三池分类。"""
        if not allowed_profiles or not allowed_sector_names:
            return set()

        grouped: Dict[str, List[StockOutput]] = {}
        for stock in scored_stocks:
            normalized_code = normalize_ts_code(stock.ts_code)
            if normalized_code in holding_codes:
                continue
            if not self._is_new_pool_code_allowed(stock.ts_code):
                continue
            if stock.sector_profile_tag not in allowed_profiles:
                continue
            matched_sector_name = self._resolve_allowed_sector_name_for_stock(
                stock,
                allowed_sector_names,
            )
            if not matched_sector_name:
                continue
            grouped.setdefault(matched_sector_name, []).append(stock)

        selected_codes: set[str] = set()
        for sector_stocks in grouped.values():
            for stock in self._pick_sector_representatives(sector_stocks):
                selected_codes.add(normalize_ts_code(stock.ts_code))
        return selected_codes

    def _pick_sector_representatives(
        self,
        sector_stocks: List[StockOutput],
    ) -> List[StockOutput]:
        """观察池代表票以辨识度为主，但允许强化票补位。"""
        if not sector_stocks:
            return []

        ranked = sorted(
            sector_stocks,
            key=lambda stock: (
                float(stock.review_bias_score or 0),
                self._representative_total_score(stock),
                float(stock.stock_score or 0),
                float(stock.account_entry_score or 0),
                float(stock.change_pct or 0),
            ),
            reverse=True,
        )
        eligible = [
            stock for stock in ranked
            if self._representative_role_bucket(stock) != "follow"
        ]
        if not eligible:
            return []

        target_count = min(self.SECTOR_REPRESENTATIVE_LIMIT, len(eligible))
        selected: List[StockOutput] = []
        selected_codes: set[str] = set()

        selectors = [
            lambda stocks: self._pick_best_matching(
                stocks,
                lambda stock: self._representative_role_bucket(stock) == "leader",
                lambda stock: (
                    self._front_strength_score(stock),
                    self._representative_total_score(stock),
                ),
            ),
            lambda stocks: self._pick_best_matching(
                stocks,
                lambda stock: self._representative_role_bucket(stock) == "mid_cap",
                lambda stock: (
                    self._capacity_recognition_score(stock),
                    self._representative_total_score(stock),
                ),
            ),
            lambda stocks: self._pick_best_matching(
                stocks,
                lambda stock: self._representative_role_bucket(stock) == "trend_core",
                lambda stock: (
                    self._continuity_potential_score(stock),
                    self._trade_setup_score(stock),
                ),
            ),
            lambda stocks: self._pick_best_matching(
                stocks,
                lambda stock: self._representative_role_bucket(stock) == "elastic_front",
                lambda stock: (
                    float(stock.change_pct or 0),
                    float(stock.vol_ratio or 0),
                    self._representative_total_score(stock),
                ),
            ),
        ]

        for selector in selectors:
            candidate = selector(eligible)
            if candidate and candidate.ts_code not in selected_codes:
                selected.append(candidate)
                selected_codes.add(candidate.ts_code)
            if len(selected) >= target_count:
                break

        minimum_count = min(2, target_count)
        for stock in eligible:
            if len(selected) >= minimum_count:
                break
            if stock.ts_code in selected_codes:
                continue
            selected.append(stock)
            selected_codes.add(stock.ts_code)

        for stock in eligible:
            if len(selected) >= target_count:
                break
            if stock.ts_code in selected_codes:
                continue
            selected.append(stock)
            selected_codes.add(stock.ts_code)

        return sorted(
            selected,
            key=lambda stock: (
                float(stock.review_bias_score or 0),
                self._representative_total_score(stock),
                float(stock.market_strength_score or 0),
            ),
            reverse=True,
        )

    def _select_account_executable_candidate_codes(
        self,
        scored_stocks: List[StockOutput],
        holding_codes: set[str],
        allowed_profiles: set[SectorProfileTag],
        allowed_sector_names: set[str],
    ) -> set[str]:
        """账户池单独保留执行优先支路，不被代表票逻辑一刀切截断。"""
        if not allowed_profiles or not allowed_sector_names:
            return set()

        grouped: Dict[str, List[StockOutput]] = {}
        for stock in scored_stocks:
            normalized_code = normalize_ts_code(stock.ts_code)
            if normalized_code in holding_codes:
                continue
            if not self._is_new_pool_code_allowed(stock.ts_code):
                continue
            if stock.sector_profile_tag not in allowed_profiles:
                continue
            matched_sector_name = self._resolve_allowed_sector_name_for_stock(
                stock,
                allowed_sector_names,
            )
            if not matched_sector_name:
                continue
            grouped.setdefault(matched_sector_name, []).append(stock)

        selected_codes: set[str] = set()
        for sector_stocks in grouped.values():
            ranked = sorted(
                sector_stocks,
                key=lambda stock: (
                    float(stock.execution_opportunity_score or 0),
                    float(stock.account_entry_score or 0),
                    float(stock.market_strength_score or 0),
                ),
                reverse=True,
            )
            for stock in ranked[: min(3, len(ranked))]:
                selected_codes.add(normalize_ts_code(stock.ts_code))
        return selected_codes

    def _representative_role_bucket(self, stock: StockOutput) -> str:
        """主线代表样本角色：龙头 / 中军 / 趋势核心 / 弹性前排 / 跟风。"""
        tag = self._representative_role_tag(stock)
        if tag == RepresentativeRoleTag.LEADER:
            return "leader"
        if tag == RepresentativeRoleTag.MID_CAPTAIN:
            return "mid_cap"
        if tag == RepresentativeRoleTag.TREND_CORE:
            return "trend_core"
        if tag == RepresentativeRoleTag.ELASTIC_FRONT:
            return "elastic_front"
        return "follow"

    def _representative_role_tag(
        self,
        stock: StockOutput,
    ) -> Optional[RepresentativeRoleTag]:
        """返回主线样本角色标签，用于前端解释为何入选样本。"""
        if stock.stock_role_tag == StockRoleTag.LEADER:
            return RepresentativeRoleTag.LEADER
        if stock.stock_role_tag == StockRoleTag.MID_CAPTAIN or (
            stock.stock_core_tag == StockCoreTag.CORE and float(stock.amount or 0) >= 180000
        ):
            return RepresentativeRoleTag.MID_CAPTAIN
        if (
            stock.stock_core_tag == StockCoreTag.CORE
            and stock.stock_continuity_tag != StockContinuityTag.CAUTION
            and stock.structure_state_tag in {
                StructureStateTag.START,
                StructureStateTag.DIVERGENCE,
                StructureStateTag.REPAIR,
            }
        ):
            return RepresentativeRoleTag.TREND_CORE
        if (
            stock.stock_role_tag == StockRoleTag.FRONT
            and stock.next_tradeability_tag in {
                NextTradeabilityTag.RETRACE_CONFIRM,
                NextTradeabilityTag.LOW_SUCK,
                NextTradeabilityTag.BREAKTHROUGH,
            }
        ):
            return RepresentativeRoleTag.ELASTIC_FRONT
        if self._is_intraday_strengthening_stock(stock):
            return RepresentativeRoleTag.ELASTIC_FRONT
        return None

    def _pick_best_matching(
        self,
        stocks: List[StockOutput],
        predicate,
        score_key,
    ) -> Optional[StockOutput]:
        matched = [stock for stock in stocks if predicate(stock)]
        if not matched:
            return None
        return max(matched, key=score_key)

    def _representative_total_score(self, stock: StockOutput) -> float:
        return round(
            self._front_strength_score(stock)
            + self._capacity_recognition_score(stock)
            + self._continuity_potential_score(stock)
            + self._trade_setup_score(stock),
            2,
        )

    def _front_strength_score(self, stock: StockOutput) -> float:
        score = float(stock.change_pct or 0) * 3
        score += self._calculate_close_quality(stock) * 18
        if stock.day_strength_tag == DayStrengthTag.LIMIT_STRONG:
            score += 14
        elif stock.day_strength_tag == DayStrengthTag.TREND_STRONG:
            score += 10
        elif stock.day_strength_tag == DayStrengthTag.REBOUND_STRONG:
            score += 6
        if self._has_upper_shadow_risk(stock):
            score -= 10
        if float(stock.close or 0) < float(stock.open or 0):
            score -= 4
        return score

    def _capacity_recognition_score(self, stock: StockOutput) -> float:
        amount = float(stock.amount or 0)
        if amount >= 300000:
            score = 16.0
        elif amount >= 180000:
            score = 12.0
        elif amount >= 100000:
            score = 8.0
        else:
            score = 4.0

        score += {
            StockRoleTag.MID_CAPTAIN: 10.0,
            StockRoleTag.LEADER: 8.0,
            StockRoleTag.FRONT: 6.0,
            StockRoleTag.FOLLOW: 2.0,
            StockRoleTag.TRASH: 0.0,
        }.get(stock.stock_role_tag, 0.0)
        if stock.stock_core_tag == StockCoreTag.CORE:
            score += 6.0
        return score

    def _continuity_potential_score(self, stock: StockOutput) -> float:
        score = {
            StockContinuityTag.SUSTAINABLE: 12.0,
            StockContinuityTag.OBSERVABLE: 7.0,
            StockContinuityTag.CAUTION: -8.0,
        }.get(stock.stock_continuity_tag, 0.0)
        score += {
            StructureStateTag.START: 10.0,
            StructureStateTag.DIVERGENCE: 12.0,
            StructureStateTag.REPAIR: 11.0,
            StructureStateTag.ACCELERATE: 4.0,
            StructureStateTag.LATE_STAGE: -10.0,
        }.get(stock.structure_state_tag, 0.0)
        return score

    def _trade_setup_score(self, stock: StockOutput) -> float:
        score = {
            NextTradeabilityTag.RETRACE_CONFIRM: 15.0,
            NextTradeabilityTag.LOW_SUCK: 14.0,
            NextTradeabilityTag.BREAKTHROUGH: 10.0,
            NextTradeabilityTag.CHASE_ONLY: -8.0,
            NextTradeabilityTag.NO_GOOD_ENTRY: -12.0,
        }.get(stock.next_tradeability_tag, 0.0)
        score += {
            StockTradeabilityTag.TRADABLE: 6.0,
            StockTradeabilityTag.CAUTION: 2.0,
            StockTradeabilityTag.NOT_RECOMMENDED: -6.0,
        }.get(stock.stock_tradeability_tag, 0.0)
        return score

    def _rank_account_executable_candidates(
        self,
        account_executable: List[StockOutput],
        limit: int,
    ) -> List[StockOutput]:
        """账户可参与池单组排序，保留结构多样性，避免单一买法占满前排。"""
        ranked = sorted(
            account_executable,
            key=lambda stock: (
                float(stock.review_bias_score or 0),
                float(stock.execution_opportunity_score or 0),
                float(stock.account_entry_score or 0),
                float(stock.market_strength_score or 0),
                float(stock.change_pct or 0),
            ),
            reverse=True,
        )
        if len(ranked) <= limit:
            return ranked

        comfortable_entries = [
            stock for stock in ranked
            if stock.next_tradeability_tag in {
                NextTradeabilityTag.RETRACE_CONFIRM,
                NextTradeabilityTag.LOW_SUCK,
            }
        ]
        breakthrough_entries = [
            stock for stock in ranked
            if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
        ]
        if not comfortable_entries or not breakthrough_entries:
            return ranked[:limit]

        reserved_comfortable = comfortable_entries[: min(3, len(comfortable_entries), max(2, limit // 3))]
        reserved_breakthrough = breakthrough_entries[: min(3, len(breakthrough_entries), max(2, limit // 3))]

        visible = reserved_comfortable + reserved_breakthrough
        selected_codes = {stock.ts_code for stock in visible}
        for stock in ranked:
            if stock.ts_code in selected_codes:
                continue
            visible.append(stock)
            if len(visible) >= limit:
                break
        return sorted(
            visible[:limit],
            key=lambda stock: (
                float(stock.review_bias_score or 0),
                float(stock.execution_opportunity_score or 0),
                float(stock.account_entry_score or 0),
                float(stock.market_strength_score or 0),
                float(stock.change_pct or 0),
            ),
            reverse=True,
        )

    def _build_holding_profile(
        self,
        holdings: Optional[List[Dict]],
        account: Optional[AccountInput],
        raw_stock_map: Optional[Dict[str, StockInput]] = None,
        scored_by_code: Optional[Dict[str, StockOutput]] = None,
        sector_map: Optional[Dict] = None,
    ) -> Dict:
        """提炼持仓结构，用于判断新开仓是否与现有暴露冲突。"""
        sector_market_value: Dict[str, float] = {}
        sector_holding_count: Dict[str, int] = {}
        weak_holding_count = 0
        t1_locked_count = 0
        total_market_value = 0.0

        for holding in holdings or []:
            code = normalize_ts_code((holding.get("ts_code") or "").strip())
            market_value = float(holding.get("holding_market_value") or 0)
            pnl_pct = holding.get("pnl_pct")
            can_sell_today = holding.get("can_sell_today")
            ref = (scored_by_code or {}).get(code) or (raw_stock_map or {}).get(code)
            sector_name = self._resolve_sector_name_for_stock(ref, sector_map or {})
            if not sector_name:
                sector_name = str(holding.get("sector_name") or "").strip()

            total_market_value += market_value
            if sector_name:
                sector_market_value[sector_name] = sector_market_value.get(sector_name, 0.0) + market_value
                sector_holding_count[sector_name] = sector_holding_count.get(sector_name, 0) + 1

            if pnl_pct is not None and float(pnl_pct) <= -3:
                weak_holding_count += 1
            if can_sell_today is False:
                t1_locked_count += 1

        if total_market_value <= 0 and account:
            total_market_value = max(float(account.total_asset or 0) - float(account.available_cash or 0), 0.0)

        return {
            "sector_market_value": sector_market_value,
            "sector_holding_count": sector_holding_count,
            "weak_holding_count": weak_holding_count,
            "t1_locked_count": t1_locked_count,
            "total_market_value": total_market_value,
        }

    def _assess_holding_fit(
        self,
        stock: StockOutput,
        holding_profile: Dict,
        account: Optional[AccountInput],
    ) -> tuple[bool, Optional[str], Optional[str], float]:
        """根据当前持仓结构修正账户可参与池准入与排序。"""
        if not holding_profile:
            return True, None, None, 0.0

        sector_name = str(stock.sector_name or "").strip()
        sector_market_value = float(holding_profile.get("sector_market_value", {}).get(sector_name, 0.0))
        same_sector_count = int(holding_profile.get("sector_holding_count", {}).get(sector_name, 0))
        total_market_value = float(holding_profile.get("total_market_value") or 0.0)
        weak_holding_count = int(holding_profile.get("weak_holding_count") or 0)
        t1_locked_count = int(holding_profile.get("t1_locked_count") or 0)
        total_asset = float(account.total_asset or 0) if account else 0.0
        total_position_ratio = float(account.total_position_ratio or 0) if account else 0.0
        sector_asset_ratio = sector_market_value / total_asset if total_asset > 0 else 0.0
        sector_hold_ratio = sector_market_value / total_market_value if total_market_value > 0 else 0.0

        reason_notes: List[str] = []
        hint_notes: List[str] = []
        score_delta = 0.0

        if (
            sector_asset_ratio >= 0.35
            or (same_sector_count >= 2 and total_position_ratio >= AccountAdapterService.POSITION_LOW)
            or (sector_hold_ratio >= 0.5 and total_position_ratio >= AccountAdapterService.POSITION_MEDIUM)
        ):
            return (
                False,
                "同板块持仓已偏重，先处理已有仓位，不再新增同方向仓位。",
                None,
                -20.0,
            )

        if same_sector_count >= 1 or sector_asset_ratio >= 0.18 or sector_hold_ratio >= 0.3:
            reason_notes.append("账户内已有同板块持仓，新仓只作为补充而非主攻。")
            hint_notes.append("若执行，同方向总暴露控制在一档内")
            score_delta -= 8.0

        if weak_holding_count > 0:
            weak_reason = f"账户内仍有{weak_holding_count}只弱势/亏损持仓待处理"
            if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
                return (
                    False,
                    f"{weak_reason}，先处理旧仓，不做需要追价确认的新开仓。",
                    None,
                    -12.0,
                )
            reason_notes.append(f"{weak_reason}，新仓优先选择更舒服的回踩/低吸位。")
            hint_notes.append("先处理弱票，再考虑加新仓")
            score_delta -= 6.0

        if t1_locked_count >= 2:
            reason_notes.append("账户内 T+1 锁定仓位较多，次日可调度空间有限。")
            hint_notes.append("新仓尽量控制为试错仓")
            score_delta -= 4.0

        return (
            True,
            " ".join(reason_notes) if reason_notes else None,
            "；".join(hint_notes) if hint_notes else None,
            score_delta,
        )

    def _merge_position_hint(
        self,
        base_hint: Optional[str],
        extra_hint: Optional[str],
    ) -> Optional[str]:
        if base_hint and extra_hint:
            return f"{base_hint}；{extra_hint}"
        return base_hint or extra_hint

    def _stock_sector_candidates(self, stock) -> List[str]:
        """返回股票可用于匹配板块的候选名称，题材优先，行业兜底。"""
        if not stock:
            return []

        names: List[str] = []
        for name in getattr(stock, "concept_names", []) or []:
            name_s = str(name or "").strip()
            if name_s and name_s not in names:
                names.append(name_s)

        sector_name = str(getattr(stock, "sector_name", "") or "").strip()
        if sector_name and sector_name not in names:
            names.append(sector_name)
        return names

    def _infer_sector_rotation_state(self, sector) -> str:
        """用有限板块字段推断方向状态，给新方向和切换方向预留信号。"""
        if not sector:
            return "未知"

        rebound = float(getattr(sector, "afternoon_rebound_strength", 0.0) or 0.0)
        continuity_days = int(getattr(sector, "sector_continuity_days", 0) or 0)
        rank = int(getattr(sector, "sector_strength_rank", 9999) or 9999)
        leader_broken = bool(getattr(sector, "leader_broken", False))
        score = float(getattr(sector, "sector_score", 0.0) or 0.0)

        if leader_broken:
            return "衰减中"
        if rebound >= 0.6 or (continuity_days <= 2 and rank <= 3 and score >= 70):
            return "强化中"
        if rebound >= 0.35 or (continuity_days <= 2 and rank <= 5):
            return "切换中"
        if continuity_days >= 4 and rank <= 3:
            return "稳定主线"
        return "中性"

    def _is_intraday_strengthening_stock(self, stock: StockOutput) -> bool:
        """识别代理版盘中强化信号，用于观察池补充，并非真实过程事件识别。"""
        close_quality = self._calculate_close_quality(stock)
        vol_ratio = float(stock.vol_ratio or 0.0)
        return (
            (
                stock.day_strength_tag == DayStrengthTag.REBOUND_STRONG
                or stock.structure_state_tag in {StructureStateTag.START, StructureStateTag.REPAIR}
            )
            and close_quality >= 0.62
            and float(stock.change_pct or 0) >= 2.5
            and (
                vol_ratio >= 1.8
                or float(stock.execution_opportunity_score or 0) >= 80
            )
            and not self._has_upper_shadow_risk(stock)
        )

    def _is_strengthening_direction_candidate(self, stock: StockOutput) -> bool:
        return (
            stock.sector_profile_tag == SectorProfileTag.B_SUB_MAINLINE
            and (
                self._is_intraday_strengthening_stock(stock)
                or (
                    stock.direction_signal_tag in {"强化中", "切换中"}
                    and float(stock.execution_opportunity_score or 0) >= 70
                )
            )
            and stock.stock_continuity_tag != StockContinuityTag.CAUTION
        )

    def _resolve_direction_signal(
        self,
        stock: StockInput,
        sector,
    ) -> tuple[Optional[str], Optional[str]]:
        """生成方向切换/强化说明。当前仅基于收盘代理特征，不代表真实盘中过程识别。"""
        if not sector:
            return None, None

        sector_state = self._infer_sector_rotation_state(sector)
        if sector_state in {"强化中", "切换中"}:
            return (
                sector_state,
                f"{getattr(sector, 'sector_name', stock.sector_name)}处于{sector_state}，当前按代理版动态信号保留观察席位。"
            )
        if self._is_intraday_strengthening_raw(stock):
            return "盘中强化", "个股出现代理版动态强化信号，说明收盘特征偏强，仍需盯盘确认是否为真实盘中回流。"
        return None, None

    def _is_intraday_strengthening_raw(self, stock: StockInput) -> bool:
        """代理版动态信号：用收盘位置、量比、涨幅近似盘中强化，不等同过程识别。"""
        close_quality = self._calculate_close_quality(stock)
        return (
            close_quality >= 0.65
            and float(stock.change_pct or 0) >= 2.0
            and float(stock.vol_ratio or 0) >= 1.6
            and stock.close >= stock.open
            and stock.close >= stock.pre_close
        )

    def _resolve_sector_for_stock(self, stock, sector_map: Dict) -> tuple[Optional[object], str]:
        """按题材优先、行业兜底，为股票解析最匹配的板块。"""
        if not stock or not sector_map:
            sector_name = str(getattr(stock, "sector_name", "") or "").strip()
            return None, sector_name

        matched_sectors = []
        for index, name in enumerate(self._stock_sector_candidates(stock)):
            sector = sector_map.get(name)
            if sector:
                matched_sectors.append((sector, name, index))

        if matched_sectors:
            sector, name, _ = max(
                matched_sectors,
                key=lambda item: self._sector_match_priority(
                    sector=item[0],
                    sector_name=item[1],
                    candidate_index=item[2],
                ),
            )
            return sector, name

        sector_name = str(getattr(stock, "sector_name", "") or "").strip()
        return None, sector_name

    def _sector_match_priority(
        self,
        sector,
        sector_name: str,
        candidate_index: int,
    ) -> tuple[int, int, int, float, int, int]:
        """多个候选板块同时命中时，优先更强、更具体、更靠前的主线。"""
        return (
            self._sector_profile_priority(sector),
            self._sector_tier_priority(getattr(sector, "sector_tier", None)),
            0 if self._is_generic_sector_name(sector_name) else 1,
            float(getattr(sector, "sector_score", 0.0) or 0.0),
            -int(getattr(sector, "sector_strength_rank", 9999) or 9999),
            -candidate_index,
        )

    def _sector_profile_priority(self, sector) -> int:
        if not sector:
            return 0
        tag = getattr(sector, "sector_mainline_tag", None)
        if tag == SectorMainlineTag.MAINLINE:
            return 4
        if tag == SectorMainlineTag.SUB_MAINLINE:
            return 3
        if str(tag or "") == "跟风":
            return 2
        if str(tag or "") == "杂毛":
            return 1
        return 0

    def _sector_tier_priority(self, sector_tier) -> int:
        if sector_tier == SectorTierTag.A:
            return 3
        if sector_tier == SectorTierTag.B:
            return 2
        if sector_tier == SectorTierTag.C:
            return 1
        return 0

    def _is_generic_sector_name(self, sector_name: str) -> bool:
        name = str(sector_name or "").strip()
        if not name:
            return True
        generic_exact = {
            "融资融券",
            "深股通",
            "沪股通",
            "央企国企改革",
            "沪深300样本股",
            "上证380成份股",
            "中证500成份股",
            "同花顺果指数",
        }
        generic_keywords = (
            "样本股",
            "成份股",
            "融资融券",
            "股通",
            "同花顺",
        )
        return name in generic_exact or any(keyword in name for keyword in generic_keywords)

    def _resolve_sector_name_for_stock(self, stock, sector_map: Dict) -> str:
        """返回股票用于板块暴露统计的解析后板块名。"""
        _, sector_name = self._resolve_sector_for_stock(stock, sector_map)
        return sector_name

    def _apply_holding_context(self, stock: StockOutput, holding: Optional[Dict]) -> StockOutput:
        """将持仓字段回填到持仓处理池股票上。"""
        if not holding:
            return stock

        stock.holding_qty = int(holding.get("holding_qty") or 0)
        stock.cost_price = float(holding.get("cost_price") or 0) if holding.get("cost_price") is not None else None
        stock.holding_market_value = (
            float(holding.get("holding_market_value") or 0)
            if holding.get("holding_market_value") is not None else None
        )
        stock.pnl_pct = float(holding.get("pnl_pct") or 0) if holding.get("pnl_pct") is not None else None
        stock.buy_date = holding.get("buy_date")
        stock.can_sell_today = bool(holding.get("can_sell_today")) if holding.get("can_sell_today") is not None else None
        stock.holding_reason = holding.get("holding_reason")
        stock.holding_days = int(holding.get("holding_days") or 0) if holding.get("holding_days") is not None else None
        stock.quote_time = holding.get("quote_time") or stock.quote_time
        stock.data_source = holding.get("data_source") or stock.data_source
        return stock

    def attach_sell_analysis(
        self,
        stock_pools: StockPoolsOutput,
        sell_analysis: Optional[SellPointResponse],
    ) -> StockPoolsOutput:
        """将卖点分析结果合并到持仓处理池，便于前端直接展示动作建议。"""
        if not sell_analysis:
            return stock_pools

        sell_map = {}
        for group in (
            sell_analysis.sell_positions,
            sell_analysis.reduce_positions,
            sell_analysis.hold_positions,
        ):
            for point in group:
                sell_map[normalize_ts_code(point.ts_code)] = point

        for stock in stock_pools.holding_process_pool:
            point = sell_map.get(normalize_ts_code(stock.ts_code))
            if not point:
                stock.holding_action_bucket = self._assign_holding_action_bucket(stock)
                continue
            stock.sell_signal_tag = point.sell_signal_tag.value
            stock.sell_point_type = point.sell_point_type.value
            stock.sell_trigger_cond = point.sell_trigger_cond
            stock.sell_reason = point.sell_reason
            stock.sell_priority = point.sell_priority.value
            stock.sell_comment = point.sell_comment
            stock.holding_action_bucket = self._assign_holding_action_bucket(stock)

        stock_pools.holding_process_pool.sort(key=self._holding_process_sort_key)
        if (
            any(stock.holding_action_bucket == HoldingActionBucket.IMMEDIATE for stock in stock_pools.holding_process_pool)
            and stock_pools.global_trade_gate.status != TradeGateStatus.HOLDINGS_FIRST
        ):
            stock_pools.global_trade_gate = GlobalTradeGateOutput(
                status=TradeGateStatus.HOLDINGS_FIRST,
                allow_new_positions=False,
                dominant_reason="持仓池出现立即处理票，旧仓优先级已经高于新开仓。",
                reasons=["持仓池出现立即处理票，旧仓优先级已经高于新开仓。"],
                account_pool_limit=0,
            )
            stock_pools.account_executable_pool = []

        return stock_pools

    def _clone_for_pool(
        self,
        stock: StockOutput,
        pool_tag: StockPoolTag,
        why_this_pool: str,
        not_other_pools: List[str],
        pool_decision_summary: str,
        review_bias_profile: Optional[Dict] = None,
    ) -> StockOutput:
        """复制股票对象，并挂上池内说明。"""
        review_bias = self._resolve_review_bias(stock, pool_tag, review_bias_profile)
        why_not_exec = None
        miss_risk_note = None
        if pool_tag != StockPoolTag.ACCOUNT_EXECUTABLE:
            why_not_exec = self._build_watch_only_reason(stock, not_other_pools)
            miss_risk_note = self._build_miss_risk_note(stock, why_not_exec)
        return stock.model_copy(
            update={
                "stock_pool_tag": pool_tag,
                "why_this_pool": why_this_pool,
                "not_other_pools": not_other_pools,
                "pool_decision_summary": pool_decision_summary,
                "miss_risk_note": miss_risk_note,
                "why_not_executable_but_should_watch": why_not_exec,
                "review_bias_score": review_bias["score"],
                "review_bias_label": review_bias["label"],
                "review_bias_reason": review_bias["reason"],
            },
            deep=True,
        )

    def _resolve_review_bias(
        self,
        stock: StockOutput,
        pool_tag: StockPoolTag,
        review_bias_profile: Optional[Dict],
    ) -> Dict:
        if not review_bias_profile:
            return {"score": 0.0, "label": None, "reason": None}

        snapshot_type = "pool_account" if pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE else "pool_market"
        bucket = stock.candidate_bucket_tag or "未分层"
        exact = (review_bias_profile.get("exact") or {}).get((snapshot_type, bucket))
        bucket_entry = (review_bias_profile.get("bucket") or {}).get(bucket)
        entry = exact or bucket_entry
        if not entry:
            return {"score": 0.0, "label": None, "reason": None}
        return {
            "score": float(entry.get("score") or 0.0),
            "label": entry.get("label"),
            "reason": entry.get("reason"),
        }

    def _build_watch_only_reason(self, stock: StockOutput, not_other_pools: List[str]) -> Optional[str]:
        if stock.direction_signal_tag in {"强化中", "切换中", "盘中强化"}:
            return "方向出现代理版动态强化信号，值得继续观察，但当前更适合等确认后再执行。"
        joined = " ".join(not_other_pools or [])
        if "买点" in joined or "执行" in joined or "账户" in joined:
            return "方向可看，但当前账户节奏或买点不完全匹配。"
        if stock.execution_opportunity_score >= 78:
            return "这只票具备后续交易观察价值，但今天先归入观察池。"
        return "可观察，但还不是当前最合适的执行票。"

    def _build_miss_risk_note(self, stock: StockOutput, why_not_exec: Optional[str]) -> Optional[str]:
        if not why_not_exec:
            return None
        if stock.direction_signal_tag in {"强化中", "切换中", "盘中强化"}:
            return "若后续代理版动态强化继续兑现为真实回流，可能从观察票升级为执行票。"
        if self._is_aggressive_trial_candidate(stock):
            return "若后续承接确认，这类强势票容易从观察阶段直接演化成进攻试错机会。"
        return "当前未入执行池不等于无价值，更多是节奏与账户适配问题。"

    def _is_account_executable(self, stock: StockOutput, account: Optional[AccountInput]) -> bool:
        """校验账户是否具备执行条件。"""
        if not account:
            return True

        # 账户硬约束：高仓位/高频新开仓/资金不足均不进入可执行池
        if account.total_position_ratio >= AccountAdapterService.POSITION_MEDIUM:
            return False
        if account.holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH:
            return False
        if account.today_new_buy_count >= AccountAdapterService.NEW_BUY_COUNT_LIMIT:
            return False
        if account.available_cash < AccountAdapterService.AVAILABLE_CASH_MIN:
            return False
        return True

    def _allow_defense_trial(
        self,
        stock: StockOutput,
        account: Optional[AccountInput],
        market_env,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """防守环境下仅放行极少数最强核心股做轻仓试错。"""
        from app.models.schemas import MarketEnvTag

        if not account or market_env.market_env_tag != MarketEnvTag.DEFENSE:
            return False, None, None

        if account.available_cash < AccountAdapterService.AVAILABLE_CASH_MIN:
            return False, None, None
        if account.total_position_ratio >= AccountAdapterService.POSITION_MEDIUM:
            return False, None, None
        if account.holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH:
            return False, None, None
        if account.today_new_buy_count >= 1:
            return False, None, None

        if stock.stock_core_tag != StockCoreTag.CORE:
            return False, None, None
        if stock.stock_strength_tag != StockStrengthTag.STRONG:
            return False, None, None
        if (
            float(stock.stock_score or 0) < self.DEFENSE_TRIAL_MIN_SCORE
            and float(stock.market_strength_score or 0) < 75
        ):
            return False, None, None

        return (
            True,
            "防守日仅保留最强核心股试错",
            "轻仓试错，单票先按半仓计划或更低执行",
        )

    def _should_skip_stock(self, stock: StockInput) -> bool:
        """在评分前先去掉明显无效的候选。"""
        source = stock.candidate_source_tag or ""
        if "持仓补齐" in source:
            return False

        name = (stock.stock_name or "").upper()
        if "ST" in name or "*ST" in name:
            return True
        if stock.close <= 0 or stock.high <= 0 or stock.low <= 0:
            return True
        if stock.close < self.MIN_CLOSE_PRICE:
            return True
        if stock.amount < self.MIN_AMOUNT:
            return True
        return False

    def _apply_hard_filters(
        self,
        scored_stocks: List[StockOutput],
        raw_stock_map: Dict[str, StockInput],
        *,
        market_env,
        account: Optional[AccountInput],
        holdings: Optional[List[Dict]],
        sector_map: Dict,
    ) -> List[StockOutput]:
        """满足至少 4/5 条硬条件；若两条不满足，直接过滤。"""
        if not scored_stocks:
            return scored_stocks

        holding_codes = {
            normalize_ts_code((holding.get("ts_code") or "").strip())
            for holding in (holdings or [])
            if (holding.get("ts_code") or "").strip()
        }
        scored_by_code = {
            normalize_ts_code(stock.ts_code): stock
            for stock in scored_stocks
        }
        holding_profile = self._build_holding_profile(
            holdings,
            account,
            raw_stock_map=raw_stock_map,
            scored_by_code=scored_by_code,
            sector_map=sector_map,
        )

        filtered: List[StockOutput] = []
        for stock in scored_stocks:
            code = normalize_ts_code(stock.ts_code)
            source = str(stock.candidate_source_tag or "")
            if "持仓补齐" in source or code in holding_codes:
                self._attach_hard_filter_debug(
                    stock,
                    {key: (True, None) for key in self.HARD_FILTER_RULE_LABELS},
                )
                filtered.append(stock)
                continue

            passes = self._evaluate_hard_filter_conditions(
                stock,
                scored_stocks,
                market_env=market_env,
                account=account,
                holding_profile=holding_profile,
            )
            self._attach_hard_filter_debug(stock, passes)
            failed_count = sum(1 for passed, _ in passes.values() if not passed)
            if failed_count >= 2:
                continue
            filtered.append(stock)
        return filtered

    def _attach_hard_filter_debug(
        self,
        stock: StockOutput,
        passes: Dict[str, tuple[bool, Optional[str]]],
    ) -> None:
        failed_rules = [
            (reason or self.HARD_FILTER_FAIL_LABELS.get(key) or self.HARD_FILTER_RULE_LABELS[key])
            for key, (passed, reason) in passes.items()
            if not passed and key in self.HARD_FILTER_RULE_LABELS
        ]
        total_rules = len(self.HARD_FILTER_RULE_LABELS)
        stock.hard_filter_failed_rules = failed_rules
        stock.hard_filter_failed_count = len(failed_rules)
        stock.hard_filter_pass_count = total_rules - len(failed_rules)
        if failed_rules:
            stock.hard_filter_summary = (
                f"硬过滤 {stock.hard_filter_pass_count}/{total_rules} 通过；"
                f"未通过：{'、'.join(failed_rules)}"
            )
        else:
            stock.hard_filter_summary = f"硬过滤 {total_rules}/{total_rules} 通过"

    def _evaluate_hard_filter_conditions(
        self,
        stock: StockOutput,
        scored_stocks: List[StockOutput],
        *,
        market_env,
        account: Optional[AccountInput],
        holding_profile: Dict,
    ) -> Dict[str, tuple[bool, Optional[str]]]:
        account_style_ok, account_style_reason = self._passes_account_style_filter(
            stock,
            market_env,
            account,
            holding_profile,
        )
        return {
            "not_pure_emotion_small_cap": (self._passes_pure_emotion_filter(stock), None),
            "not_hot_but_weak_logic": (self._passes_hot_weak_logic_filter(stock), None),
            "not_weaker_than_group": (self._passes_group_trend_filter(stock, scored_stocks), None),
            "not_chase_only_tomorrow": (
                stock.next_tradeability_tag not in {
                    NextTradeabilityTag.CHASE_ONLY,
                    NextTradeabilityTag.NO_GOOD_ENTRY,
                },
                None,
            ),
            "not_account_style_conflict": (account_style_ok, account_style_reason),
        }

    def _passes_pure_emotion_filter(self, stock: StockOutput) -> bool:
        source = str(stock.candidate_source_tag or "")
        return not (
            stock.sector_profile_tag == SectorProfileTag.NON_MAINSTREAM
            and stock.stock_core_tag != StockCoreTag.CORE
            and float(stock.amount or 0) <= self.PURE_EMOTION_AMOUNT_MAX
            and (
                "涨停入选" in source
                or float(stock.change_pct or 0) >= self.STRONG_CHANGE_THRESHOLD
            )
        )

    def _passes_hot_weak_logic_filter(self, stock: StockOutput) -> bool:
        volatility_pct = self._intraday_volatility_pct(stock)
        return not (
            float(stock.turnover_rate or 0) >= 18
            and volatility_pct >= self.HIGH_VOLATILITY_PCT
            and (
                stock.stock_core_tag != StockCoreTag.CORE
                or stock.sector_profile_tag == SectorProfileTag.NON_MAINSTREAM
                or stock.stock_continuity_tag == StockContinuityTag.CAUTION
                or float(stock.stock_score or 0) < 70
            )
        )

    def _passes_group_trend_filter(
        self,
        stock: StockOutput,
        scored_stocks: List[StockOutput],
    ) -> bool:
        same_sector = [
            peer for peer in scored_stocks
            if peer.sector_name == stock.sector_name
        ]
        if len(same_sector) < 3:
            return True

        ranked = sorted(
            same_sector,
            key=lambda peer: (
                float(peer.stock_score or 0),
                float(peer.change_pct or 0),
            ),
            reverse=True,
        )
        best = ranked[0]
        try:
            rank = next(idx for idx, peer in enumerate(ranked, start=1) if peer.ts_code == stock.ts_code)
        except StopIteration:
            return True

        return not (
            rank >= 3
            and float(best.stock_score or 0) - float(stock.stock_score or 0) >= 10
            and (
                stock.stock_role_tag in {StockRoleTag.FOLLOW, StockRoleTag.TRASH}
                or stock.stock_strength_tag != StockStrengthTag.STRONG
                or stock.stock_continuity_tag != StockContinuityTag.SUSTAINABLE
            )
        )

    def _passes_account_style_filter(
        self,
        stock: StockOutput,
        market_env,
        account: Optional[AccountInput],
        holding_profile: Dict,
    ) -> tuple[bool, Optional[str]]:
        if not account:
            return True, None
        if not self._is_account_executable(stock, account):
            return False, self._account_executable_fail_reason(account)
        holding_ok, holding_reason, _, _ = self._assess_holding_fit(stock, holding_profile, account)
        if not holding_ok:
            return False, holding_reason or "当前持仓结构不适合新增同方向仓位。"
        if (
            market_env.market_env_tag == MarketEnvTag.DEFENSE
            and stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
        ):
            return False, "防守环境下不适合做需要突破确认的票。"
        return True, None

    def _account_executable_fail_reason(self, account: AccountInput) -> str:
        if account.total_position_ratio >= AccountAdapterService.POSITION_MEDIUM:
            return "账户总仓位已偏高，先控制仓位，不新增执行票。"
        if account.holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH:
            return "当前持仓数量已偏多，先收缩持仓，再考虑新机会。"
        if account.today_new_buy_count >= AccountAdapterService.NEW_BUY_COUNT_LIMIT:
            return "当日新开仓次数已到上限，先不再新增。"
        if account.available_cash < AccountAdapterService.AVAILABLE_CASH_MIN:
            return "账户可用资金不足，暂不满足新开仓条件。"
        return "账户当前不适合新增执行票。"

    def _intraday_volatility_pct(self, stock: StockOutput) -> float:
        pre_close = float(stock.pre_close or 0)
        if pre_close <= 0:
            return 0.0
        return ((float(stock.high or 0) - float(stock.low or 0)) / pre_close) * 100

    def _should_enter_market_watch(self, stock: StockOutput) -> bool:
        """观察池是机会雷达池：既看已确认强票，也看盘中强化票。"""
        if float(stock.market_strength_score or 0) < self.WATCH_POOL_MIN_SCORE:
            return False
        if float(stock.amount or 0) < self.MIN_AMOUNT:
            return False
        if float(stock.change_pct or 0) <= 0 and not self._is_intraday_strengthening_stock(stock):
            return False
        if self._has_upper_shadow_risk(stock) and float(stock.change_pct or 0) < 5:
            return False
        if (
            stock.day_strength_tag == DayStrengthTag.SPIKE_FADE
            or self._calculate_close_quality(stock) < 0.45
        ) and not self._is_intraday_strengthening_stock(stock):
            return False
        if (
            stock.sector_profile_tag not in {
                SectorProfileTag.A_MAINLINE,
                SectorProfileTag.B_SUB_MAINLINE,
            }
            and not str(stock.direction_signal_tag or "").strip()
            and not str(stock.candidate_source_tag or "").strip()
        ):
            return False
        return self._market_watch_vote_count(stock) >= 3

    def _should_enter_account_pool(
        self,
        stock: StockOutput,
        account: Optional[AccountInput],
        market_env,
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """判断是否进入账户可参与池，并返回原因、仓位提示与实际入池模式。"""
        defense_allowed, defense_reason, defense_position_hint = self._allow_defense_trial(
            stock,
            account,
            market_env,
        )
        if defense_allowed:
            return True, defense_reason, defense_position_hint, "defense_trial"

        if stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE:
            if stock.next_tradeability_tag in {
                NextTradeabilityTag.CHASE_ONLY,
                NextTradeabilityTag.NO_GOOD_ENTRY,
            } and not self._is_aggressive_trial_candidate(stock):
                return False, "方向虽强，但当前更偏情绪宣泄，先观察不直接执行。", None, None
            if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
                entry_ok, entry_reason, position_hint = self._has_comfortable_account_entry(stock)
                if not entry_ok:
                    if self._is_aggressive_trial_candidate(stock):
                        return True, "方向强度足够，虽位置不完美，但保留小仓进攻试错资格。", "仅做试错仓，确认承接后再考虑加仓", "aggressive_trial"
                    return False, entry_reason, None, None
            if self._is_account_executable(stock, account):
                if stock.next_tradeability_tag in {
                    NextTradeabilityTag.CHASE_ONLY,
                    NextTradeabilityTag.NO_GOOD_ENTRY,
                } and self._is_aggressive_trial_candidate(stock):
                    return True, "方向强度足够，虽非标准舒服位，但保留小仓进攻试错资格。", "仅做小仓试错，等分歧后确认承接", "aggressive_trial"
                return True, self._tradable_account_entry_reason(stock), self._tradable_position_hint(stock), "standard"
            return False, "账户条件未通过，先观察不直接执行。", None, None

        if stock.stock_tradeability_tag == StockTradeabilityTag.CAUTION:
            if stock.next_tradeability_tag in {
                NextTradeabilityTag.CHASE_ONLY,
                NextTradeabilityTag.NO_GOOD_ENTRY,
            } and not self._is_aggressive_trial_candidate(stock):
                return False, "方向可看，但买点尚未清晰，先留在观察池。", None, None
            if stock.next_tradeability_tag not in {
                NextTradeabilityTag.RETRACE_CONFIRM,
                NextTradeabilityTag.LOW_SUCK,
            } and not self._is_aggressive_trial_candidate(stock):
                return False, "交易性仍偏谨慎，且没有明确回踩/低吸位，先观察。", None, None
            if stock.sector_profile_tag not in {
                SectorProfileTag.A_MAINLINE,
                SectorProfileTag.B_SUB_MAINLINE,
            }:
                return False, "回踩位虽在，但不属主线/次主线，不进账户可参与池。", None, None
            entry_ok, entry_reason, position_hint = self._has_comfortable_account_entry(stock)
            entry_mode = "standard"
            if not entry_ok:
                if self._is_aggressive_trial_candidate(stock):
                    entry_reason = "方向强度足够，虽位置不完美，但保留小仓进攻试错资格。"
                    position_hint = "仅做试错仓，确认承接后再考虑加仓"
                    entry_mode = "aggressive_trial"
                else:
                    return False, entry_reason, None, None
            if self._is_account_executable(stock, account):
                return True, entry_reason, position_hint, entry_mode
            return False, "账户条件未通过，先观察不直接执行。", None, None

        return False, "交易性或账户条件不足，暂不进入账户可参与池。", None, None

    def _market_watch_vote_count(self, stock: StockOutput) -> int:
        votes = 0
        if stock.sector_profile_tag in {
            SectorProfileTag.A_MAINLINE,
            SectorProfileTag.B_SUB_MAINLINE,
        } and stock.stock_role_tag in {
            StockRoleTag.LEADER,
            StockRoleTag.FRONT,
            StockRoleTag.MID_CAPTAIN,
        }:
            votes += 1
        if stock.stock_role_tag in {StockRoleTag.LEADER, StockRoleTag.MID_CAPTAIN}:
            votes += 1
        if stock.day_strength_tag in {
            DayStrengthTag.LIMIT_STRONG,
            DayStrengthTag.TREND_STRONG,
        } or self._front_strength_score(stock) >= 38:
            votes += 1
        if (
            stock.stock_continuity_tag != StockContinuityTag.CAUTION
            and stock.structure_state_tag != StructureStateTag.LATE_STAGE
        ):
            votes += 1
        if stock.direction_signal_tag in {"强化中", "切换中", "盘中强化"}:
            votes += 1
        if self._is_intraday_strengthening_stock(stock):
            votes += 1
        return votes

    def _is_aggressive_trial_candidate(self, stock: StockOutput) -> bool:
        """给真正强势但不够完美的票保留小仓试错资格。采用硬风控+软打分，避免模板化卡边界。"""
        if stock.sector_profile_tag not in {SectorProfileTag.A_MAINLINE, SectorProfileTag.B_SUB_MAINLINE}:
            return False
        if stock.stock_strength_tag != StockStrengthTag.STRONG:
            return False
        if stock.next_tradeability_tag not in {
            NextTradeabilityTag.BREAKTHROUGH,
            NextTradeabilityTag.CHASE_ONLY,
            NextTradeabilityTag.NO_GOOD_ENTRY,
        }:
            return False
        if stock.structure_state_tag == StructureStateTag.LATE_STAGE:
            return False
        if self._has_upper_shadow_risk(stock):
            return False

        change_pct = float(stock.change_pct or 0)
        turnover_rate = float(stock.turnover_rate or 0)
        if change_pct < 2.5 or change_pct > 8.2:
            return False
        if turnover_rate > 20.5:
            return False

        return self._aggressive_trial_score(stock) >= 60.0

    def _aggressive_trial_score(self, stock: StockOutput) -> float:
        """进攻试错软评分：看强度、执行性、日内状态和拥挤度，不再用一串硬阈值卡死。"""
        score = 0.0
        market_strength_score = float(stock.market_strength_score or 0.0)
        execution_score = float(stock.execution_opportunity_score or 0.0)
        change_pct = float(stock.change_pct or 0.0)
        turnover_rate = float(stock.turnover_rate or 0.0)

        if stock.sector_profile_tag == SectorProfileTag.A_MAINLINE:
            score += 12.0
        elif stock.sector_profile_tag == SectorProfileTag.B_SUB_MAINLINE:
            score += 8.0

        if market_strength_score >= 84:
            score += 20.0
        elif market_strength_score >= 80:
            score += 16.0
        elif market_strength_score >= 76:
            score += 12.0

        if execution_score >= 76:
            score += 18.0
        elif execution_score >= 72:
            score += 14.0
        elif execution_score >= 68:
            score += 10.0

        if stock.day_strength_tag in {
            DayStrengthTag.LIMIT_STRONG,
            DayStrengthTag.TREND_STRONG,
            DayStrengthTag.REBOUND_STRONG,
        }:
            score += 10.0

        if stock.direction_signal_tag in {"强化中", "切换中", "盘中强化"}:
            score += 6.0
        if self._is_intraday_strengthening_stock(stock):
            score += 6.0

        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            score += 10.0
        else:
            score += 7.0

        if 4.0 <= change_pct <= 7.2:
            score += 10.0
        elif 3.2 <= change_pct <= 8.2:
            score += 6.0

        if turnover_rate <= 16.5:
            score += 8.0
        elif turnover_rate <= 18.5:
            score += 4.0

        return round(score, 1)

    def _passes_account_participation_gate(
        self,
        stock: StockOutput,
        account: Optional[AccountInput],
        holding_profile: Dict,
    ) -> tuple[bool, Optional[str]]:
        """账户可参与池用 5 问法做最后一道实战过滤。"""
        comfortable_breakthrough = (
            stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
            and stock.structure_state_tag in {StructureStateTag.DIVERGENCE, StructureStateTag.REPAIR}
            and float(stock.turnover_rate or 0) < 15
            and not self._has_upper_shadow_risk(stock)
        )
        has_comfortable_entry = stock.next_tradeability_tag in {
            NextTradeabilityTag.RETRACE_CONFIRM,
            NextTradeabilityTag.LOW_SUCK,
        } or comfortable_breakthrough or self._is_aggressive_trial_candidate(stock)
        weak_holding_count = int(holding_profile.get("weak_holding_count") or 0)
        t1_locked_count = int(holding_profile.get("t1_locked_count") or 0)

        votes = [
            self._is_account_executable(stock, account),
            weak_holding_count == 0,
            int(holding_profile.get("sector_holding_count", {}).get(str(stock.sector_name or "").strip(), 0)) == 0,
            has_comfortable_entry,
            float(stock.account_entry_score or 0) >= 80,
        ]
        if t1_locked_count >= 2:
            votes[4] = False

        hit_count = sum(1 for passed in votes if passed)
        if hit_count >= 4:
            return True, None

        if weak_holding_count > 0:
            return False, "账户里仍有弱票/低效仓待处理，先去弱，再考虑新机会。"
        if not has_comfortable_entry:
            return False, "方向强，但次日买点不够舒服，先观察或仅做极小仓试错。"
        if not votes[2]:
            return False, "当前持仓方向已重复暴露，先处理旧仓，不新增同方向仓位。"
        return False, "这只票值得看，但当前更像观察票，还不是账户最优执行答案。"

    def _tradable_account_entry_reason(self, stock: StockOutput) -> str:
        if stock.next_tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            return "交易性为可交易，且存在回踩确认位，可纳入账户可参与池。"
        if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
            return "交易性为可交易，且存在低吸预备位，可纳入账户可参与池。"
        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            return "交易性为可交易，且存在突破确认机会，可纳入账户可参与池。"
        return "交易性为可交易，可纳入账户可参与池。"

    def _tradable_position_hint(self, stock: StockOutput) -> str:
        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            return "只做确认突破，不做盘中盲追"
        if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
            return "优先轻仓低吸，不追单根拉升"
        if stock.next_tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            return "优先等回踩确认后执行"
        return "按计划仓位执行"

    def _annotate_execution_proximity(self, stock: StockOutput) -> None:
        reference_price, reference_label = self._estimate_execution_reference(stock)
        if not reference_price:
            stock.execution_reference_price = None
            stock.execution_reference_gap_pct = None
            stock.execution_proximity_tag = None
            stock.execution_proximity_note = None
            return

        current_price = self._current_price(stock)
        gap_pct = self._price_gap_pct(current_price, reference_price)
        stock.execution_reference_price = reference_price
        stock.execution_reference_gap_pct = gap_pct

        proximity_tag, proximity_note = self._classify_execution_proximity(
            stock,
            reference_label,
            reference_price,
            gap_pct,
        )
        stock.execution_proximity_tag = proximity_tag
        stock.execution_proximity_note = proximity_note

    def _estimate_execution_reference(self, stock: StockOutput) -> tuple[Optional[float], str]:
        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            base = float(stock.high or stock.close or stock.pre_close or 0)
            if base <= 0:
                return None, "突破确认位"
            return round(base * 1.002, 2), "突破确认位"
        if stock.next_tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            base = float(stock.open or stock.avg_price or stock.pre_close or stock.low or 0)
            if base <= 0:
                return None, "回踩确认位"
            label = self._nearest_retrace_anchor_label(stock, base)
            return round(base, 2), label
        if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
            base = float(stock.low or stock.pre_close or stock.avg_price or 0)
            if base <= 0:
                return None, "低吸参考位"
            return round(base, 2), "低吸参考位"
        return None, "执行位"

    def _nearest_retrace_anchor_label(self, stock: StockOutput, reference_price: float) -> str:
        candidates = [
            ("开盘价", stock.open),
            ("前收价", stock.pre_close),
            ("日内均价", stock.avg_price),
            ("最低价", stock.low),
        ]
        valid = [
            (label, float(price))
            for label, price in candidates
            if price is not None and float(price) > 0
        ]
        if not valid:
            return "回踩确认位"
        label, _ = min(valid, key=lambda item: abs(item[1] - reference_price))
        return label

    def _classify_execution_proximity(
        self,
        stock: StockOutput,
        reference_label: str,
        reference_price: float,
        gap_pct: Optional[float],
    ) -> tuple[Optional[str], Optional[str]]:
        if gap_pct is None:
            return None, None

        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            near_floor = self._breakthrough_gap_floor_pct(stock.ts_code)
            if gap_pct >= 0:
                return "已过确认位", f"当前价已站上{reference_label} {reference_price:.2f}，回买点页判断是否还能追。"
            if gap_pct >= near_floor:
                return "接近执行位", f"当前价距离{reference_label} {reference_price:.2f} 约 {abs(gap_pct):.2f}%，接近突破确认区。"
            return "待突破", f"当前价距离{reference_label} {reference_price:.2f} 约 {abs(gap_pct):.2f}%，先等更接近再看。"

        near_floor = self._retrace_gap_floor_pct(stock.ts_code)
        if gap_pct >= near_floor:
            return "接近执行位", f"当前价距离{reference_label} {reference_price:.2f} 约 {abs(gap_pct):.2f}%，已接近可观察执行区。"
        if gap_pct <= self._deep_retrace_gap_floor_pct(stock.ts_code):
            return "待深回踩", f"当前价高于{reference_label} {reference_price:.2f} 约 {abs(gap_pct):.2f}%，这个位置更像深回踩参考。"
        wait_label = "待低吸" if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK else "待回踩"
        action_label = "低吸参考位" if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK else reference_label
        return wait_label, f"当前价高于{action_label} {reference_price:.2f} 约 {abs(gap_pct):.2f}%，先回买点页等触发。"

    def _retrace_gap_floor_pct(self, ts_code: str) -> float:
        code = normalize_ts_code(ts_code)
        if code.endswith(".BJ"):
            return -4.0
        if code.startswith("300") or code.startswith("301") or code.startswith("688"):
            return -2.5
        return -1.5

    def _deep_retrace_gap_floor_pct(self, ts_code: str) -> float:
        code = normalize_ts_code(ts_code)
        if code.endswith(".BJ"):
            return -12.0
        if code.startswith("300") or code.startswith("301") or code.startswith("688"):
            return -8.0
        return -6.0

    def _breakthrough_gap_floor_pct(self, ts_code: str) -> float:
        code = normalize_ts_code(ts_code)
        if code.endswith(".BJ"):
            return -2.0
        if code.startswith("300") or code.startswith("301") or code.startswith("688"):
            return -1.5
        return -1.0

    def _current_price(self, stock: StockOutput) -> Optional[float]:
        price = stock.close or stock.pre_close or stock.open
        return round(float(price), 2) if price else None

    def _price_gap_pct(self, current_price: Optional[float], target_price: Optional[float]) -> Optional[float]:
        if not current_price or not target_price:
            return None
        return round((float(target_price) - float(current_price)) / float(current_price) * 100, 2)

    def _has_comfortable_account_entry(self, stock: StockOutput) -> tuple[bool, str, Optional[str]]:
        """账户可参与池必须对应相对舒服、可执行的买入位置。"""
        if stock.next_tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            return (
                True,
                "趋势回踩确认位较舒服，可纳入账户可参与池。",
                "优先等回踩确认后执行",
            )
        if stock.next_tradeability_tag == NextTradeabilityTag.LOW_SUCK:
            return (
                True,
                "存在低吸预备位，可纳入账户可参与池。",
                "优先轻仓低吸，不追单根拉升",
            )
        if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            if (
                stock.structure_state_tag in {StructureStateTag.DIVERGENCE, StructureStateTag.REPAIR}
                and float(stock.turnover_rate or 0) < 15
                and not self._has_upper_shadow_risk(stock)
            ):
                return (
                    True,
                    "分歧/修复段仍有确认承接位，可纳入账户可参与池。",
                    "优先等回踩确认或分歧转强后执行",
                )
            change_pct = float(stock.change_pct or 0)
            turnover_rate = float(stock.turnover_rate or 0)
            if change_pct > 7.2:
                return False, "需要突破确认，但当日涨幅已偏大，不算舒服买点。", None
            if change_pct > 6.5 and turnover_rate >= 8:
                return False, "需要突破确认，当前涨幅已偏大且换手开始抬升，更像加速追价。", None
            if turnover_rate >= 15:
                return False, "需要突破确认，但换手偏高，追价舒适度不足。", None
            if self._has_upper_shadow_risk(stock):
                return False, "盘中上影偏长，突破承接一般，不算舒服买点。", None
            if change_pct > 6.5:
                return (
                    True,
                    "突破延续但换手仍可控，可纳入账户可参与池。",
                    "只做分时确认，不做加速追高",
                )
            return (
                True,
                "突破位距离尚可，且承接没有明显走坏，可纳入账户可参与池。",
                "只做放量确认突破，不做盲追",
            )
        if self._is_aggressive_trial_candidate(stock):
            return (
                True,
                "方向强度足够，允许作为进攻试错票保留。",
                "试错仓参与，确认后再扩大仓位",
            )
        return False, "当前缺少清晰、舒服的买入点，不进账户可参与池。", None

    def _build_sector_map(self, sector_scan) -> Dict:
        """构建板块映射（包含全部分类，确保个股都能找到所属板块）"""
        sector_map = {}
        for group in [
            sector_scan.mainline_sectors,
            sector_scan.sub_mainline_sectors,
            sector_scan.follow_sectors,
            sector_scan.trash_sectors,
        ]:
            for s in group:
                sector_map[s.sector_name] = s
        return sector_map

    def _score_stock(
        self,
        stock: StockInput,
        market_env,
        sector_map: Dict
    ) -> StockOutput:
        """
        评分个股

        Args:
            stock: 个股数据
            market_env: 市场环境
            sector_map: 板块映射

        Returns:
            评分后的个股
        """
        # 获取所属板块：优先题材映射，其次行业兜底
        sector, resolved_sector_name = self._resolve_sector_for_stock(stock, sector_map)

        # 计算强度评分
        market_strength_score = self._calculate_strength_score(stock, sector)

        # 确定强弱标签
        strength_tag = self._determine_strength_tag(stock.change_pct, market_strength_score)

        # 确定连续性标签
        continuity_tag = self._determine_continuity_tag(market_strength_score, stock)

        # 确定核心属性
        core_tag = self._determine_core_tag(stock, sector, market_strength_score)

        # 确定交易性标签
        tradeability_tag = self._determine_tradeability_tag(
            strength_tag, continuity_tag, core_tag, market_env
        )

        # 确定候选分层
        bucket_tag = self._determine_candidate_bucket(stock, strength_tag, tradeability_tag)

        # 确定池标签（暂不赋值，由 classify_pools 处理）
        pool_tag = StockPoolTag.MARKET_WATCH

        # 生成证伪条件
        falsification = self._generate_falsification(stock, sector, core_tag)

        # 生成简评
        comment = self._generate_stock_comment(
            strength_tag, continuity_tag, tradeability_tag, sector, stock.candidate_source_tag, bucket_tag
        )
        sector_profile_tag = self._determine_sector_profile_tag(sector)
        stock_role_tag = self._determine_stock_role_tag(
            stock,
            sector,
            core_tag,
            market_strength_score,
        )
        day_strength_tag = self._determine_day_strength_tag(stock, strength_tag)
        structure_state_tag = self._determine_structure_state_tag(stock, bucket_tag)
        next_tradeability_tag = self._determine_next_tradeability_tag(
            stock,
            bucket_tag,
            tradeability_tag,
        )
        execution_opportunity_score = self._calculate_execution_opportunity_score(
            stock,
            strength_tag,
            continuity_tag,
            core_tag,
            tradeability_tag,
            sector,
            structure_state_tag,
            next_tradeability_tag,
        )
        account_entry_score = self._calculate_account_entry_score(
            stock,
            strength_tag,
            continuity_tag,
            core_tag,
            tradeability_tag,
            sector_profile_tag,
            structure_state_tag,
            next_tradeability_tag,
        )
        direction_signal_tag, direction_signal_reason = self._resolve_direction_signal(stock, sector)
        pool_decision_summary = self._build_stock_decision_summary(
            sector_profile_tag,
            stock_role_tag,
            day_strength_tag,
            structure_state_tag,
            next_tradeability_tag,
        )

        output = StockOutput(
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            sector_name=resolved_sector_name or stock.sector_name,
            change_pct=stock.change_pct,
            amount=stock.amount,
            close=stock.close,
            open=stock.open,
            high=stock.high,
            low=stock.low,
            pre_close=stock.pre_close,
            vol_ratio=stock.vol_ratio,
            turnover_rate=stock.turnover_rate,
            stock_score=round((market_strength_score * 0.6) + (execution_opportunity_score * 0.4), 1),
            market_strength_score=market_strength_score,
            execution_opportunity_score=execution_opportunity_score,
            account_entry_score=account_entry_score,
            candidate_source_tag=stock.candidate_source_tag,
            candidate_bucket_tag=bucket_tag,
            volume=stock.volume,
            avg_price=stock.avg_price,
            quote_time=stock.quote_time,
            data_source=stock.data_source,
            concept_names=list(stock.concept_names or []),
            stock_strength_tag=strength_tag,
            stock_continuity_tag=continuity_tag,
            stock_tradeability_tag=tradeability_tag,
            stock_core_tag=core_tag,
            stock_pool_tag=pool_tag,
            sector_profile_tag=sector_profile_tag,
            sector_tier_tag=getattr(sector, "sector_tier", None) if sector else None,
            stock_role_tag=stock_role_tag,
            day_strength_tag=day_strength_tag,
            structure_state_tag=structure_state_tag,
            next_tradeability_tag=next_tradeability_tag,
            direction_signal_tag=direction_signal_tag,
            direction_signal_reason=direction_signal_reason,
            stock_falsification_cond=falsification,
            stock_comment=comment,
            pool_decision_summary=pool_decision_summary,
        )
        output.representative_role_tag = self._representative_role_tag(output)
        return output

    def _calculate_strength_score(self, stock: StockInput, sector) -> float:
        """计算强度评分 (0-100)"""
        score = 50  # 基础分

        # 涨跌幅得分
        if stock.change_pct >= self.STRONG_CHANGE_THRESHOLD:
            score += 30
        elif stock.change_pct >= self.MEDIUM_CHANGE_THRESHOLD:
            score += 15
        elif stock.change_pct > 0:
            score += 5
        else:
            score -= 10

        # 换手率得分
        if stock.turnover_rate >= self.HIGH_TURNOVER:
            score += 10
        elif stock.turnover_rate >= self.MEDIUM_TURNOVER:
            score += 5

        # 量比得分
        if stock.vol_ratio:
            if stock.vol_ratio >= 2:
                score += 10
            elif stock.vol_ratio >= 1.5:
                score += 5
            elif stock.vol_ratio < 0.5:
                score -= 10

        # 流动性得分：保留能承接的品种
        if stock.amount >= 300000:
            score += 10
        elif stock.amount >= 150000:
            score += 6
        elif stock.amount >= 80000:
            score += 3
        else:
            score -= 6

        # 收盘位置：收在高位说明承接更强
        close_quality = self._calculate_close_quality(stock)
        if close_quality >= 0.8:
            score += 10
        elif close_quality >= 0.65:
            score += 6
        elif close_quality >= 0.45:
            score += 2
        else:
            score -= 8

        # 日内承接：收红且站上昨收更偏强
        if stock.close > stock.open and stock.close > stock.pre_close:
            score += 6
        elif stock.close > stock.pre_close:
            score += 3
        elif stock.close < stock.open and stock.change_pct < 0:
            score -= 4

        # 过热惩罚：长上影、高位爆量不宜机械抬分
        if self._has_upper_shadow_risk(stock):
            score -= 8
        if stock.change_pct >= 9 and stock.turnover_rate >= 25:
            score -= 10

        # 候选来源加权
        score += self._source_bonus(stock)

        # 板块加分
        if sector:
            if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
                score += 20
            elif sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
                score += 10
            elif sector.sector_mainline_tag == SectorMainlineTag.FOLLOW:
                score += 5

        return max(0, min(100, score))

    def _calculate_execution_opportunity_score(
        self,
        stock: StockInput,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        core_tag: StockCoreTag,
        tradeability_tag: StockTradeabilityTag,
        sector,
        structure_state_tag: StructureStateTag,
        next_tradeability_tag: NextTradeabilityTag,
    ) -> float:
        """执行机会分，强调次日可参与性和盘中承接，而不是纯静态榜单强度。"""
        score = 48.0

        score += {
            NextTradeabilityTag.RETRACE_CONFIRM: 22.0,
            NextTradeabilityTag.LOW_SUCK: 19.0,
            NextTradeabilityTag.BREAKTHROUGH: 15.0,
            NextTradeabilityTag.CHASE_ONLY: -8.0,
            NextTradeabilityTag.NO_GOOD_ENTRY: -14.0,
        }.get(next_tradeability_tag, 0.0)
        score += {
            StockTradeabilityTag.TRADABLE: 10.0,
            StockTradeabilityTag.CAUTION: 4.0,
            StockTradeabilityTag.NOT_RECOMMENDED: -8.0,
        }.get(tradeability_tag, 0.0)
        score += {
            StructureStateTag.REPAIR: 10.0,
            StructureStateTag.DIVERGENCE: 9.0,
            StructureStateTag.START: 8.0,
            StructureStateTag.ACCELERATE: 1.0,
            StructureStateTag.LATE_STAGE: -12.0,
        }.get(structure_state_tag, 0.0)

        close_quality = self._calculate_close_quality(stock)
        score += close_quality * 10.0
        if stock.close > stock.open:
            score += 5.0
        if stock.close > stock.pre_close:
            score += 4.0
        if self._is_intraday_strengthening_raw(stock):
            score += 8.0
        if self._has_upper_shadow_risk(stock):
            score -= 8.0

        if strength_tag == StockStrengthTag.STRONG:
            score += 5.0
        if continuity_tag == StockContinuityTag.CAUTION:
            score -= 10.0
        if core_tag == StockCoreTag.CORE:
            score += 4.0

        change_pct = float(stock.change_pct or 0.0)
        if 2.0 <= change_pct <= 6.8:
            score += 6.0
        elif change_pct > 9.0:
            score -= 8.0

        turnover_rate = float(stock.turnover_rate or 0.0)
        if 5.0 <= turnover_rate <= 14.0:
            score += 6.0
        elif turnover_rate >= 20.0:
            score -= 6.0

        if sector:
            rotation_state = self._infer_sector_rotation_state(sector)
            score += {
                "强化中": 10.0,
                "切换中": 7.0,
                "稳定主线": 5.0,
                "衰减中": -10.0,
            }.get(rotation_state, 0.0)

        return round(max(0.0, min(100.0, score)), 1)

    def _calculate_account_entry_score(
        self,
        stock: StockInput,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        core_tag: StockCoreTag,
        tradeability_tag: StockTradeabilityTag,
        sector_profile_tag: SectorProfileTag,
        structure_state_tag: StructureStateTag,
        next_tradeability_tag: NextTradeabilityTag,
    ) -> float:
        """账户可参与池排序分，更强调买点舒适度。"""
        score = {
            NextTradeabilityTag.RETRACE_CONFIRM: 89.0,
            NextTradeabilityTag.LOW_SUCK: 84.0,
            NextTradeabilityTag.BREAKTHROUGH: 85.0,
            NextTradeabilityTag.CHASE_ONLY: 16.0,
            NextTradeabilityTag.NO_GOOD_ENTRY: 10.0,
        }.get(next_tradeability_tag, 10.0)

        if tradeability_tag == StockTradeabilityTag.TRADABLE:
            score += 5
        elif tradeability_tag == StockTradeabilityTag.CAUTION:
            score -= 2

        if sector_profile_tag == SectorProfileTag.A_MAINLINE:
            score += 4
        elif sector_profile_tag == SectorProfileTag.B_SUB_MAINLINE:
            score += 2

        if core_tag == StockCoreTag.CORE:
            score += 4
        elif core_tag == StockCoreTag.FOLLOW:
            score += 1

        if strength_tag == StockStrengthTag.STRONG:
            score += 2
        elif strength_tag == StockStrengthTag.WEAK:
            score -= 8

        if continuity_tag == StockContinuityTag.SUSTAINABLE:
            score += 3
        elif continuity_tag == StockContinuityTag.CAUTION:
            score -= 6

        if structure_state_tag in {StructureStateTag.DIVERGENCE, StructureStateTag.REPAIR}:
            score += 4
        elif structure_state_tag == StructureStateTag.ACCELERATE:
            score -= 4

        if self._has_upper_shadow_risk(stock):
            score -= 8

        change_pct = float(stock.change_pct or 0)
        turnover_rate = float(stock.turnover_rate or 0)
        if next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH:
            if 4.5 <= change_pct <= 6.8:
                score += 4
            if change_pct > 6.5:
                score -= min((change_pct - 6.5) * 4, 12)
            if turnover_rate >= 15:
                score -= 6
        elif next_tradeability_tag == NextTradeabilityTag.RETRACE_CONFIRM:
            if 1 <= change_pct <= 5.5:
                score += 2
        elif next_tradeability_tag == NextTradeabilityTag.LOW_SUCK and (stock.vol_ratio or 0) >= 2:
            score += 2

        return round(max(score, 0.0), 1)

    def _calculate_close_quality(self, stock: StockInput) -> float:
        """计算收盘位置，越接近最高越强。"""
        intraday_range = stock.high - stock.low
        if intraday_range <= 0:
            return 0.5
        return max(0.0, min(1.0, (stock.close - stock.low) / intraday_range))

    def _has_upper_shadow_risk(self, stock: StockInput) -> bool:
        """长上影说明冲高承接较弱。"""
        intraday_range = stock.high - stock.low
        if intraday_range <= 0:
            return False
        upper_shadow = stock.high - max(stock.open, stock.close)
        return upper_shadow / intraday_range >= 0.35

    def _source_bonus(self, stock: StockInput) -> float:
        """候选来源补正。"""
        source = stock.candidate_source_tag or ""
        bonus = 0.0
        if "涨停入选" in source:
            bonus += 8
        if "量比异动" in source:
            bonus += 4
        if "涨幅前列" in source:
            bonus += 3
        if "持仓补齐" in source:
            bonus -= 2
        return bonus

    def _determine_strength_tag(self, change_pct: float, strength_score: float) -> StockStrengthTag:
        """确定强弱标签"""
        if change_pct >= self.STRONG_CHANGE_THRESHOLD:
            return StockStrengthTag.STRONG
        if change_pct >= 5 and strength_score >= self.STRONG_SCORE_CONFIRM:
            return StockStrengthTag.STRONG
        if change_pct >= 0 or strength_score >= self.MEDIUM_SCORE_THRESHOLD:
            return StockStrengthTag.MEDIUM
        return StockStrengthTag.WEAK

    def _determine_continuity_tag(self, strength_score: float, stock: StockInput) -> StockContinuityTag:
        """确定连续性标签"""
        # 简化判断：高位放量可能末端
        if stock.change_pct >= 9 and stock.turnover_rate >= 25:
            return StockContinuityTag.CAUTION

        if strength_score >= 70:
            return StockContinuityTag.SUSTAINABLE
        elif strength_score >= 40:
            return StockContinuityTag.OBSERVABLE
        else:
            return StockContinuityTag.CAUTION

    def _determine_core_tag(
        self,
        stock: StockInput,
        sector,
        strength_score: float
    ) -> StockCoreTag:
        """确定核心属性"""
        # 有板块支撑且强度高 -> 核心
        if sector and strength_score >= 60:
            if sector.sector_mainline_tag in [SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE]:
                return StockCoreTag.CORE

        # 有板块支撑但强度一般 -> 跟随
        if sector:
            return StockCoreTag.FOLLOW

        # 无板块支撑 -> 杂毛
        return StockCoreTag.TRASH

    def _determine_tradeability_tag(
        self,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        core_tag: StockCoreTag,
        market_env
    ) -> StockTradeabilityTag:
        """确定交易性标签"""
        from app.models.schemas import MarketEnvTag

        # 弱市不交易
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 末端谨慎
        if continuity_tag == StockContinuityTag.CAUTION:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 杂毛不建议
        if core_tag == StockCoreTag.TRASH:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 核心且持续 -> 可交易
        if core_tag == StockCoreTag.CORE and strength_tag == StockStrengthTag.STRONG:
            return StockTradeabilityTag.TRADABLE

        # 中等强度 -> 谨慎
        if strength_tag == StockStrengthTag.MEDIUM:
            return StockTradeabilityTag.CAUTION

        return StockTradeabilityTag.CAUTION

    def _determine_sector_profile_tag(self, sector) -> SectorProfileTag:
        """板块属性画像。"""
        if not sector:
            return SectorProfileTag.NON_MAINSTREAM
        if sector.sector_profile_tag if hasattr(sector, "sector_profile_tag") else None:
            if str(sector.sector_profile_tag).startswith("A"):
                return SectorProfileTag.A_MAINLINE
            if str(sector.sector_profile_tag).startswith("B"):
                return SectorProfileTag.B_SUB_MAINLINE
        if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
            return SectorProfileTag.A_MAINLINE
        if sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
            return SectorProfileTag.B_SUB_MAINLINE
        return SectorProfileTag.NON_MAINSTREAM

    def _determine_stock_role_tag(
        self,
        stock: StockInput,
        sector,
        core_tag: StockCoreTag,
        strength_score: float,
    ) -> StockRoleTag:
        """个股地位画像，仅作解释字段，不直接决定池子命运。"""
        if core_tag == StockCoreTag.TRASH:
            return StockRoleTag.TRASH
        if core_tag == StockCoreTag.FOLLOW:
            return StockRoleTag.FOLLOW
        source = stock.candidate_source_tag or ""
        if "涨停入选" in source and stock.change_pct >= 9 and float(stock.amount or 0) >= 80000:
            return StockRoleTag.LEADER
        if stock.amount >= 250000 and strength_score >= 70:
            return StockRoleTag.MID_CAPTAIN
        if stock.change_pct >= 4 or self._is_intraday_strengthening_raw(stock):
            return StockRoleTag.FRONT
        return StockRoleTag.FOLLOW

    def _determine_day_strength_tag(
        self,
        stock: StockInput,
        strength_tag: StockStrengthTag,
    ) -> DayStrengthTag:
        """当日强度画像。"""
        if stock.change_pct >= 9:
            return DayStrengthTag.LIMIT_STRONG
        if (
            strength_tag == StockStrengthTag.STRONG
            and stock.change_pct >= 5
            and self._calculate_close_quality(stock) >= 0.65
            and not self._has_upper_shadow_risk(stock)
        ):
            return DayStrengthTag.TREND_STRONG
        if (
            stock.close > stock.open
            and stock.close > stock.pre_close
            and self._calculate_close_quality(stock) >= 0.55
        ):
            return DayStrengthTag.REBOUND_STRONG
        if self._has_upper_shadow_risk(stock):
            return DayStrengthTag.SPIKE_FADE
        return DayStrengthTag.FOLLOW_RISE

    def _determine_structure_state_tag(
        self,
        stock: StockInput,
        bucket_tag: str,
    ) -> StructureStateTag:
        """结构状态画像。"""
        stage = str(stock.stage_tag or "").strip()
        if "启动" in stage:
            return StructureStateTag.START
        if "主升" in stage or "加速" in stage:
            return StructureStateTag.ACCELERATE
        if "回调" in stage or "分歧" in stage:
            return StructureStateTag.DIVERGENCE
        if "修复" in stage:
            return StructureStateTag.REPAIR
        if "高位" in stage:
            return StructureStateTag.LATE_STAGE
        if bucket_tag == "趋势回踩":
            return StructureStateTag.REPAIR
        if bucket_tag == "强势确认":
            return StructureStateTag.ACCELERATE
        if bucket_tag == "异动预备":
            return StructureStateTag.START
        return StructureStateTag.DIVERGENCE

    def _determine_next_tradeability_tag(
        self,
        stock: StockInput,
        bucket_tag: str,
        tradeability_tag: StockTradeabilityTag,
    ) -> NextTradeabilityTag:
        """次日可交易性画像。"""
        if tradeability_tag == StockTradeabilityTag.NOT_RECOMMENDED:
            return NextTradeabilityTag.NO_GOOD_ENTRY
        if stock.change_pct >= 9 or (
            stock.change_pct >= 7 and stock.turnover_rate >= 18
        ):
            return NextTradeabilityTag.CHASE_ONLY
        if bucket_tag == "趋势回踩":
            return NextTradeabilityTag.RETRACE_CONFIRM
        if bucket_tag == "强势确认":
            return NextTradeabilityTag.BREAKTHROUGH
        if bucket_tag == "异动预备":
            return NextTradeabilityTag.LOW_SUCK
        return NextTradeabilityTag.NO_GOOD_ENTRY

    def _build_stock_decision_summary(
        self,
        sector_profile_tag: SectorProfileTag,
        stock_role_tag: StockRoleTag,
        day_strength_tag: DayStrengthTag,
        structure_state_tag: StructureStateTag,
        next_tradeability_tag: NextTradeabilityTag,
    ) -> str:
        """组合五项画像摘要。"""
        return " / ".join(
            [
                sector_profile_tag.value,
                stock_role_tag.value,
                day_strength_tag.value,
                structure_state_tag.value,
                next_tradeability_tag.value,
            ]
        )

    def _why_market_watch(self, stock: StockOutput, *, is_holding: bool = False) -> str:
        sector_label = stock.sector_profile_tag.value if stock.sector_profile_tag else "当前强势方向"
        role_label = stock.stock_role_tag.value if stock.stock_role_tag else "前排样本"
        day_label = stock.day_strength_tag.value if stock.day_strength_tag else "强势结构"
        if is_holding:
            return f"这只持仓仍属于{sector_label}里的{role_label}，当日保持{day_label}，值得继续作为市场强票盯着看。"
        return f"{sector_label}里的{role_label}，当日属于{day_label}，强度、地位和结构都还在观察池前列。"

    def _build_not_other_pool_reasons(
        self,
        target_pool: StockPoolTag,
        *,
        account_ok: bool,
        is_holding: bool,
        account_reason: Optional[str] = None,
    ) -> List[str]:
        """生成未进入其他池的原因说明。"""
        reasons: List[str] = []
        if target_pool == StockPoolTag.ACCOUNT_EXECUTABLE:
            reasons.append("若同票也出现在观察池，仍以账户执行清单的条件说明为准。")
            return reasons

        if is_holding:
            reasons.append("当前已持仓，因此不再进入账户可参与池回答新开仓问题。")
            return reasons

        if not account_ok:
            reasons.append(account_reason or "未进账户可参与池：账户、节奏或买点条件未同时满足。")
        else:
            reasons.append("虽具备执行条件，但当前池更强调观察视角。")
        return reasons

    def _build_pool_summary(
        self,
        stock: StockOutput,
        pool_tag: StockPoolTag,
        why_this_pool: str,
    ) -> str:
        return f"{stock.stock_name}归入{pool_tag.value}：{why_this_pool}"

    def _determine_candidate_bucket(
        self,
        stock: StockInput,
        strength_tag: StockStrengthTag,
        tradeability_tag: StockTradeabilityTag,
    ) -> str:
        """为候选股打交易视角标签。"""
        source = stock.candidate_source_tag or ""
        if "持仓补齐" in source:
            return "持仓映射"
        if "涨停入选" in source or (
            strength_tag == StockStrengthTag.STRONG and stock.change_pct >= 5 and tradeability_tag == StockTradeabilityTag.TRADABLE
        ):
            return "强势确认"
        if strength_tag in {StockStrengthTag.STRONG, StockStrengthTag.MEDIUM} and stock.change_pct >= 1:
            return "趋势回踩"
        if "量比异动" in source or (stock.vol_ratio and stock.vol_ratio >= 2.5):
            return "异动预备"
        return "观察补充"

    def _generate_falsification(self, stock: StockInput, sector, core_tag: StockCoreTag) -> str:
        """生成证伪条件"""
        conds = []

        # 跌破关键位
        if stock.change_pct > 5:
            conds.append(f"收盘跌破今日涨幅的50%")

        # 板块走弱
        if sector:
            if sector.sector_tradeability_tag == SectorTradeabilityTag.NOT_RECOMMENDED:
                conds.append("板块转为不建议交易")

        # 杂毛
        if core_tag == StockCoreTag.TRASH:
            conds.append("无板块支撑，走势孤立")

        # 放量滞涨
        if stock.vol_ratio and stock.vol_ratio > 3 and stock.change_pct < 3:
            conds.append("放量滞涨")

        return "；".join(conds) if conds else "跌破5日均线"

    def _generate_stock_comment(
        self,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        tradeability_tag: StockTradeabilityTag,
        sector,
        source_tag: str,
        bucket_tag: str,
    ) -> str:
        """生成个股简评"""
        comments = []

        if bucket_tag:
            comments.append(bucket_tag)

        # 强度
        if strength_tag == StockStrengthTag.STRONG:
            comments.append("强势股")
        elif strength_tag == StockStrengthTag.MEDIUM:
            comments.append("中性")
        else:
            comments.append("弱势")

        # 板块
        if sector:
            if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
                comments.append("主线")
            elif sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
                comments.append("次主线")

        # 连续性
        if continuity_tag == StockContinuityTag.CAUTION:
            comments.append("注意末端")

        # 交易建议
        if tradeability_tag == StockTradeabilityTag.TRADABLE:
            comments.append("可交易")
        elif tradeability_tag == StockTradeabilityTag.CAUTION:
            comments.append("谨慎")
        else:
            comments.append("不建议")

        if source_tag:
            comments.append(f"来源:{source_tag}")

        return "，".join(comments)


# 全局服务实例
stock_filter_service = StockFilterService()
