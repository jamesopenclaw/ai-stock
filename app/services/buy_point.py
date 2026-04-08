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
        for stock in stock_pools.market_watch_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.MARKET_WATCH
        for stock in stock_pools.account_executable_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.ACCOUNT_EXECUTABLE
        for stock in stock_pools.holding_process_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.HOLDING_PROCESS

        # 分析每个股票的买点
        available = []   # 可买
        observe = []    # 观察
        not_buy = []    # 不买
        analyzed_count = 0
        display_quote_map = self._build_display_quote_map(trade_date, scored_stocks)

        for stock in scored_stocks:
            stock.stock_pool_tag = pool_tag_by_code.get(stock.ts_code, StockPoolTag.NOT_IN_POOL)
            if stock.stock_pool_tag == StockPoolTag.HOLDING_PROCESS:
                continue

            buy_point = self._analyze_stock_buy_point(stock, market_env, account, review_bias_profile)
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

        available.sort(key=self._buy_point_rank_key, reverse=True)
        observe.sort(key=self._buy_point_rank_key, reverse=True)
        not_buy.sort(key=self._buy_point_rank_key, reverse=True)

        return BuyPointResponse(
            trade_date=trade_date,
            market_env_tag=market_env.market_env_tag,
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
        对回踩/低吸型，如果现价离触发位仍明显偏远，就降回观察。
        """
        if buy_point.buy_signal_tag != BuySignalTag.CAN_BUY:
            return buy_point
        if stock.stock_pool_tag != StockPoolTag.ACCOUNT_EXECUTABLE:
            return buy_point
        if buy_point.buy_point_type not in {BuyPointType.RETRACE_SUPPORT, BuyPointType.LOW_SUCK}:
            return buy_point
        gap_pct = buy_point.buy_trigger_gap_pct
        if gap_pct is None:
            return buy_point
        if gap_pct >= self._available_trigger_gap_floor_pct(stock.ts_code):
            return buy_point

        buy_point.buy_signal_tag = BuySignalTag.OBSERVE
        if buy_point.buy_comment:
            buy_point.buy_comment = f"{buy_point.buy_comment}，现价离触发位仍偏远，先等回到计划位附近再看"
        else:
            buy_point.buy_comment = "现价离触发位仍偏远，先等回到计划位附近再看"
        buy_point.recommended_order_pct = None
        buy_point.recommended_order_amount = None
        buy_point.recommended_shares = None
        buy_point.recommended_lots = None
        buy_point.sizing_reference_price = None
        buy_point.sizing_note = None
        return buy_point

    def _available_trigger_gap_floor_pct(self, ts_code: str) -> float:
        """
        可买列表要求当前价离触发位足够近。
        返回的是 buy_trigger_gap_pct 的下限，单位为百分比。
        例如 -1.5 代表当前价最多只能高出触发价约 1.5%。
        """
        code = str(ts_code or "").upper()
        if code.endswith(".BJ"):
            return -4.0
        if code.startswith(("300", "301", "688")):
            return -2.5
        return -1.5

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
            hard_filter_failed_rules=list(stock.hard_filter_failed_rules or []),
            hard_filter_failed_count=int(stock.hard_filter_failed_count or 0),
            hard_filter_pass_count=int(stock.hard_filter_pass_count or 0),
            hard_filter_summary=stock.hard_filter_summary or "",
            buy_signal_tag=signal_tag,
            buy_point_type=buy_type,
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
            "score": float(entry.get("score") or 0.0),
            "label": entry.get("label"),
            "reason": entry.get("reason"),
        }

    def _buy_point_rank_key(self, point: BuyPointOutput):
        return (
            float(point.review_bias_score or 0),
            1 if point.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE.value else 0,
            self._buy_point_type_priority(point.buy_point_type),
            float(point.buy_current_change_pct or 0),
        )

    def _buy_point_type_priority(self, buy_point_type: BuyPointType) -> int:
        if buy_point_type == BuyPointType.RETRACE_SUPPORT:
            return 3
        if buy_point_type == BuyPointType.BREAKTHROUGH:
            return 2
        if buy_point_type == BuyPointType.LOW_SUCK:
            return 1
        return 0

    def _determine_buy_type(self, stock: StockOutput, market_env) -> BuyPointType:
        """确定买点类型"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        change_pct = float(stock.change_pct or 0)
        breakout_type_ceiling = self._breakthrough_type_ceiling_pct(stock.ts_code)
        breakout_quality_ok = (
            market_env.breakout_allowed
            and stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE
            and stock.stock_core_tag == StockCoreTag.CORE
            and 4.0 <= change_pct <= breakout_type_ceiling
            and not self._has_upper_shadow_risk(stock)
        )
        # 强势股 -> 突破
        if stock.stock_strength_tag == StockStrengthTag.STRONG:
            if (
                stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
                and breakout_quality_ok
                and market_env.market_env_tag in {MarketEnvTag.ATTACK, MarketEnvTag.NEUTRAL}
            ):
                return BuyPointType.BREAKTHROUGH
            if (
                market_env.market_env_tag == MarketEnvTag.ATTACK
                and breakout_quality_ok
            ):
                return BuyPointType.BREAKTHROUGH
            if market_profile in {"中性偏谨慎", "弱中性"}:
                return BuyPointType.RETRACE_SUPPORT
            return BuyPointType.RETRACE_SUPPORT

        # 中等强度 -> 回踩承接
        if stock.stock_strength_tag == StockStrengthTag.MEDIUM:
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
            base = stock.open or stock.close or stock.pre_close
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
            return "触发价", round(float(trigger_price), 2)

        label, price = min(valid, key=lambda item: abs(item[1] - float(trigger_price)))
        return label, round(price, 2)

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
