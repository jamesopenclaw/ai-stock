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
    DayStrengthTag,
    StructureStateTag,
    NextTradeabilityTag,
    StockPoolsOutput,
    SectorMainlineTag,
    SectorTradeabilityTag,
    AccountInput,
    SellPointResponse,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.account_adapter import AccountAdapterService
from app.data.tushare_client import tushare_client, normalize_ts_code


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

    # 涨跌幅阈值
    STRONG_CHANGE_THRESHOLD = 7.0   # 涨幅 > 7% 为强势
    MEDIUM_CHANGE_THRESHOLD = 3.0  # 涨幅 > 3% 为中等
    STRONG_SCORE_CONFIRM = 85.0    # 中高涨幅配合高分才升格为强势
    MEDIUM_SCORE_THRESHOLD = 55.0  # 分数较高但涨幅一般时，保留为中性观察

    # 换手率阈值
    HIGH_TURNOVER = 15.0   # 高换手
    MEDIUM_TURNOVER = 8.0  # 中等换手

    # 选股预过滤阈值
    MIN_AMOUNT = 30000.0  # 过低成交额不进入选股结果
    MIN_CLOSE_PRICE = 2.0  # 低价股噪声较大

    # 观察池最低标准
    WATCH_POOL_MIN_SCORE = 55.0
    DEFENSE_TRIAL_MIN_SCORE = 85.0

    def __init__(self):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service

    def filter(self, trade_date: str, stocks: List[StockInput]) -> List[StockOutput]:
        return self.filter_with_context(trade_date, stocks)

    def filter_with_context(
        self,
        trade_date: str,
        stocks: List[StockInput],
        market_env=None,
        sector_scan=None,
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
        for stock in stocks:
            if self._should_skip_stock(stock):
                continue
            output = self._score_stock(stock, market_env, sector_map)
            result.append(output)

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
        # 筛选评分
        scored_stocks = scored_stocks or self.filter_with_context(
            trade_date,
            stocks,
            market_env=market_env,
            sector_scan=sector_scan,
        )

        # 获取市场环境和板块
        market_env = market_env or self.market_env_service.get_current_env(trade_date)
        sector_scan = sector_scan or self.sector_scan_service.scan(trade_date, limit_output=False)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 三池分类
        market_watch = []    # 市场最强观察池
        trend_recognition = []  # 趋势辨识度观察池
        account_executable = []  # 账户可参与池
        holding_process = []  # 持仓处理池

        # 持仓代码集合
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
        holding_process_codes = set()

        # 持仓必须全量进入持仓处理池，即使未通过预过滤也要兜底补评分。
        for holding_code in holding_codes:
            scored = scored_by_code.get(holding_code)
            if not scored:
                raw_stock = raw_stock_map.get(holding_code)
                if not raw_stock:
                    continue
                scored = self._score_stock(raw_stock, market_env, sector_map)
            scored = self._apply_holding_context(scored, holding_map.get(holding_code))
            holding_process.append(
                self._clone_for_pool(
                    scored,
                    StockPoolTag.HOLDING_PROCESS,
                    why_this_pool="持仓票与新开仓票分离，优先进入持仓处理池。",
                    not_other_pools=[
                        "持仓票不进入市场最强观察池。",
                        "持仓票不进入趋势辨识度观察池。",
                        "持仓票不进入账户可参与池。",
                    ],
                    pool_decision_summary="持仓票单独处理，先看卖点和风险控制。",
                )
            )
            holding_process_codes.add(holding_code)

        for stock in scored_stocks:
            normalized_code = normalize_ts_code(stock.ts_code)
            # 分类到对应池
            if normalized_code in holding_codes:
                # 持仓处理池
                if normalized_code not in holding_process_codes:
                    stock = self._apply_holding_context(stock, holding_map.get(normalized_code))
                    holding_process.append(
                        self._clone_for_pool(
                            stock,
                            StockPoolTag.HOLDING_PROCESS,
                            why_this_pool="持仓票与新开仓票分离，优先进入持仓处理池。",
                            not_other_pools=[
                                "持仓票不进入市场最强观察池。",
                                "持仓票不进入趋势辨识度观察池。",
                                "持仓票不进入账户可参与池。",
                            ],
                            pool_decision_summary="持仓票单独处理，先看卖点和风险控制。",
                        )
                    )
                    holding_process_codes.add(normalized_code)
            else:
                market_ok = self._should_enter_market_watch(stock)
                trend_ok = self._should_enter_trend_recognition(stock)
                account_ok, account_reason, account_position_hint = self._should_enter_account_pool(
                    stock,
                    account,
                    market_env,
                )
                if market_ok:
                    why = self._why_market_watch(stock)
                    market_watch.append(
                        self._clone_for_pool(
                            stock,
                            StockPoolTag.MARKET_WATCH,
                            why_this_pool=why,
                            not_other_pools=self._build_not_other_pool_reasons(
                                StockPoolTag.MARKET_WATCH,
                                market_ok=market_ok,
                                trend_ok=trend_ok,
                                account_ok=account_ok,
                                account_reason=account_reason,
                            ),
                            pool_decision_summary=self._build_pool_summary(
                                stock,
                                StockPoolTag.MARKET_WATCH,
                                why,
                            ),
                        )
                    )
                if trend_ok:
                    why = self._why_trend_recognition(stock)
                    trend_recognition.append(
                        self._clone_for_pool(
                            stock,
                            StockPoolTag.TREND_RECOGNITION,
                            why_this_pool=why,
                            not_other_pools=self._build_not_other_pool_reasons(
                                StockPoolTag.TREND_RECOGNITION,
                                market_ok=market_ok,
                                trend_ok=trend_ok,
                                account_ok=account_ok,
                                account_reason=account_reason,
                            ),
                            pool_decision_summary=self._build_pool_summary(
                                stock,
                                StockPoolTag.TREND_RECOGNITION,
                                why,
                            ),
                        )
                    )
                if account_ok:
                    account_clone = self._clone_for_pool(
                        stock,
                        StockPoolTag.ACCOUNT_EXECUTABLE,
                        why_this_pool=account_reason,
                        not_other_pools=self._build_not_other_pool_reasons(
                            StockPoolTag.ACCOUNT_EXECUTABLE,
                            market_ok=market_ok,
                            trend_ok=trend_ok,
                            account_ok=account_ok,
                            account_reason=account_reason,
                        ),
                        pool_decision_summary=self._build_pool_summary(
                            stock,
                            StockPoolTag.ACCOUNT_EXECUTABLE,
                            account_reason,
                        ),
                    )
                    account_clone.pool_entry_reason = account_reason
                    account_clone.position_hint = account_position_hint
                    account_executable.append(account_clone)

        visible_market_watch = market_watch[:20]
        visible_trend_recognition = trend_recognition[:10]
        visible_account_executable = self._select_visible_account_executable(account_executable, limit=10)

        return StockPoolsOutput(
            trade_date=trade_date,
            resolved_trade_date=None,
            market_watch_pool=visible_market_watch,   # 最多20只
            trend_recognition_pool=visible_trend_recognition,
            account_executable_pool=visible_account_executable,  # 最多10只
            holding_process_pool=holding_process,  # 全部持仓
            total_count=(
                len(visible_market_watch)
                + len(visible_trend_recognition)
                + len(visible_account_executable)
                + len(holding_process)
            ),
        )

    def _select_visible_account_executable(
        self,
        account_executable: List[StockOutput],
        limit: int = 10,
    ) -> List[StockOutput]:
        """账户可参与池展示时保留结构多样性，避免单一买法占满前排。"""
        ranked = sorted(
            account_executable,
            key=lambda stock: (
                float(stock.account_entry_score or 0),
                float(stock.stock_score or 0),
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
                float(stock.account_entry_score or 0),
                float(stock.stock_score or 0),
                float(stock.change_pct or 0),
            ),
            reverse=True,
        )

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
                continue
            stock.sell_signal_tag = point.sell_signal_tag.value
            stock.sell_point_type = point.sell_point_type.value
            stock.sell_trigger_cond = point.sell_trigger_cond
            stock.sell_reason = point.sell_reason
            stock.sell_priority = point.sell_priority.value
            stock.sell_comment = point.sell_comment

        return stock_pools

    def _clone_for_pool(
        self,
        stock: StockOutput,
        pool_tag: StockPoolTag,
        why_this_pool: str,
        not_other_pools: List[str],
        pool_decision_summary: str,
    ) -> StockOutput:
        """复制股票对象，并挂上池内说明。"""
        return stock.model_copy(
            update={
                "stock_pool_tag": pool_tag,
                "why_this_pool": why_this_pool,
                "not_other_pools": not_other_pools,
                "pool_decision_summary": pool_decision_summary,
            },
            deep=True,
        )

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
        if stock.stock_continuity_tag != StockContinuityTag.SUSTAINABLE:
            return False, None, None
        if stock.stock_score < self.DEFENSE_TRIAL_MIN_SCORE:
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

    def _should_enter_market_watch(self, stock: StockOutput) -> bool:
        """观察池只保留值得继续跟踪的候选。"""
        if stock.sector_profile_tag == SectorProfileTag.NON_MAINSTREAM:
            return False
        if stock.stock_role_tag in {StockRoleTag.LEADER, StockRoleTag.FRONT} and (
            stock.day_strength_tag in {DayStrengthTag.LIMIT_STRONG, DayStrengthTag.TREND_STRONG}
        ):
            return True
        if stock.stock_role_tag == StockRoleTag.MID_CAPTAIN and stock.stock_score >= 88:
            return True
        return False

    def _should_enter_trend_recognition(self, stock: StockOutput) -> bool:
        """趋势辨识度观察池：不看谁最炸，看谁更耐打。"""
        if stock.sector_profile_tag == SectorProfileTag.NON_MAINSTREAM:
            return False
        if stock.stock_role_tag not in {
            StockRoleTag.LEADER,
            StockRoleTag.FRONT,
            StockRoleTag.MID_CAPTAIN,
        }:
            return False
        if stock.structure_state_tag not in {
            StructureStateTag.START,
            StructureStateTag.DIVERGENCE,
            StructureStateTag.REPAIR,
        }:
            return False
        if stock.next_tradeability_tag in {
            NextTradeabilityTag.CHASE_ONLY,
            NextTradeabilityTag.NO_GOOD_ENTRY,
        }:
            return False
        return stock.stock_continuity_tag != StockContinuityTag.CAUTION

    def _should_enter_account_pool(
        self,
        stock: StockOutput,
        account: Optional[AccountInput],
        market_env,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """判断是否进入账户可参与池，并返回原因与仓位提示。"""
        if stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE:
            if stock.next_tradeability_tag in {
                NextTradeabilityTag.CHASE_ONLY,
                NextTradeabilityTag.NO_GOOD_ENTRY,
            }:
                return False, "只能追高或缺少舒服买点，不进账户可参与池。", None
            if self._is_account_executable(stock, account):
                return True, self._tradable_account_entry_reason(stock), self._tradable_position_hint(stock)
            return False, "账户条件未通过，先观察不直接执行。", None

        if stock.stock_tradeability_tag == StockTradeabilityTag.CAUTION:
            if stock.next_tradeability_tag in {
                NextTradeabilityTag.CHASE_ONLY,
                NextTradeabilityTag.NO_GOOD_ENTRY,
            }:
                return False, "只能追高或缺少舒服买点，不进账户可参与池。", None
            if stock.next_tradeability_tag not in {
                NextTradeabilityTag.RETRACE_CONFIRM,
                NextTradeabilityTag.LOW_SUCK,
            }:
                return False, "交易性仍偏谨慎，且没有明确回踩/低吸位，先观察。", None
            if stock.sector_profile_tag not in {
                SectorProfileTag.A_MAINLINE,
                SectorProfileTag.B_SUB_MAINLINE,
            }:
                return False, "回踩位虽在，但不属主线/次主线，不进账户可参与池。", None
            entry_ok, entry_reason, position_hint = self._has_comfortable_account_entry(stock)
            if not entry_ok:
                return False, entry_reason, None
            if self._is_account_executable(stock, account):
                return True, entry_reason, position_hint
            return False, "账户条件未通过，先观察不直接执行。", None

        defense_allowed, defense_reason, defense_position_hint = self._allow_defense_trial(
            stock,
            account,
            market_env,
        )
        if defense_allowed:
            return True, defense_reason, defense_position_hint
        return False, "交易性或账户条件不足，暂不进入账户可参与池。", None

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
            if float(stock.change_pct or 0) > 6.5:
                return False, "需要突破确认，但当日涨幅已偏大，不算舒服买点。", None
            if float(stock.turnover_rate or 0) >= 15:
                return False, "需要突破确认，但换手偏高，追价舒适度不足。", None
            if self._has_upper_shadow_risk(stock):
                return False, "盘中上影偏长，突破承接一般，不算舒服买点。", None
            return (
                True,
                "突破位距离尚可，且承接没有明显走坏，可纳入账户可参与池。",
                "只做放量确认突破，不做盲追",
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
        # 获取所属板块
        sector = sector_map.get(stock.sector_name)

        # 计算强度评分
        strength_score = self._calculate_strength_score(stock, sector)

        # 确定强弱标签
        strength_tag = self._determine_strength_tag(stock.change_pct, strength_score)

        # 确定连续性标签
        continuity_tag = self._determine_continuity_tag(strength_score, stock)

        # 确定核心属性
        core_tag = self._determine_core_tag(stock, sector, strength_score)

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
            strength_score,
        )
        day_strength_tag = self._determine_day_strength_tag(stock, strength_tag)
        structure_state_tag = self._determine_structure_state_tag(stock, bucket_tag)
        next_tradeability_tag = self._determine_next_tradeability_tag(
            stock,
            bucket_tag,
            tradeability_tag,
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
        pool_decision_summary = self._build_stock_decision_summary(
            sector_profile_tag,
            stock_role_tag,
            day_strength_tag,
            structure_state_tag,
            next_tradeability_tag,
        )

        return StockOutput(
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            sector_name=stock.sector_name,
            change_pct=stock.change_pct,
            close=stock.close,
            open=stock.open,
            high=stock.high,
            low=stock.low,
            pre_close=stock.pre_close,
            vol_ratio=stock.vol_ratio,
            turnover_rate=stock.turnover_rate,
            stock_score=strength_score,
            account_entry_score=account_entry_score,
            candidate_source_tag=stock.candidate_source_tag,
            candidate_bucket_tag=bucket_tag,
            volume=stock.volume,
            avg_price=stock.avg_price,
            quote_time=stock.quote_time,
            data_source=stock.data_source,
            stock_strength_tag=strength_tag,
            stock_continuity_tag=continuity_tag,
            stock_tradeability_tag=tradeability_tag,
            stock_core_tag=core_tag,
            stock_pool_tag=pool_tag,
            sector_profile_tag=sector_profile_tag,
            stock_role_tag=stock_role_tag,
            day_strength_tag=day_strength_tag,
            structure_state_tag=structure_state_tag,
            next_tradeability_tag=next_tradeability_tag,
            stock_falsification_cond=falsification,
            stock_comment=comment,
            pool_decision_summary=pool_decision_summary,
        )

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
        """个股地位画像。"""
        if core_tag == StockCoreTag.TRASH:
            return StockRoleTag.TRASH
        if core_tag == StockCoreTag.FOLLOW:
            return StockRoleTag.FOLLOW
        source = stock.candidate_source_tag or ""
        if "涨停入选" in source and stock.change_pct >= 9:
            return StockRoleTag.LEADER
        if stock.amount >= 250000 and strength_score >= 70:
            return StockRoleTag.MID_CAPTAIN
        if stock.change_pct >= 5:
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

    def _why_market_watch(self, stock: StockOutput) -> str:
        return (
            f"{stock.sector_profile_tag.value}里的{stock.stock_role_tag.value}，"
            f"当日属于{stock.day_strength_tag.value}，更能代表今天最强偏好。"
        )

    def _why_trend_recognition(self, stock: StockOutput) -> str:
        return (
            f"{stock.stock_role_tag.value}结构更清晰，当前处于{stock.structure_state_tag.value}，"
            f"且次日具备{stock.next_tradeability_tag.value}。"
        )

    def _build_not_other_pool_reasons(
        self,
        target_pool: StockPoolTag,
        *,
        market_ok: bool,
        trend_ok: bool,
        account_ok: bool,
        account_reason: Optional[str] = None,
    ) -> List[str]:
        """生成未进入其他池的原因说明。"""
        reasons: List[str] = []
        if target_pool != StockPoolTag.MARKET_WATCH and not market_ok:
            reasons.append("未进市场最强观察池：当天强度或辨识度还不够最强。")
        elif target_pool == StockPoolTag.ACCOUNT_EXECUTABLE and market_ok:
            reasons.append("若同时在观察池出现，也以执行清单优先。")

        if target_pool != StockPoolTag.TREND_RECOGNITION and not trend_ok:
            reasons.append("未进趋势辨识度观察池：结构或连续性还不足以长期跟踪。")

        if target_pool != StockPoolTag.ACCOUNT_EXECUTABLE and not account_ok:
            reasons.append(account_reason or "未进账户可参与池：账户、节奏或买点条件未同时满足。")
        elif target_pool != StockPoolTag.ACCOUNT_EXECUTABLE and account_ok:
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
