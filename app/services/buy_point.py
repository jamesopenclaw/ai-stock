"""
买点分析服务
"""
from typing import Dict, List, Optional

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
        for stock in stock_pools.trend_recognition_pool:
            pool_tag_by_code[stock.ts_code] = StockPoolTag.TREND_RECOGNITION
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
                StockPoolTag.TREND_RECOGNITION,
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
        confirm_cond = self._generate_confirm_cond(stock, buy_type)
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
        # 强势股 -> 突破
        if stock.stock_strength_tag == StockStrengthTag.STRONG:
            change_pct = float(stock.change_pct or 0)
            if (
                market_env.market_env_tag == MarketEnvTag.ATTACK
                and market_env.breakout_allowed
                and 5 <= change_pct < 7
                and stock.stock_core_tag == StockCoreTag.CORE
                and stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE
            ):
                return BuyPointType.BREAKTHROUGH
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
            if stock.stock_pool_tag == StockPoolTag.TREND_RECOGNITION:
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
            return "回踩至今日开盘价附近企稳时触发"
        else:
            return "出现分时反转信号、量能配合时触发"

    def _generate_confirm_cond(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        """生成确认条件"""
        conds = []

        # 都需要量能配合
        conds.append("成交量放大至前一交易日1.2倍以上")

        if buy_type == BuyPointType.BREAKTHROUGH:
            conds.append("突破后不回落到关键位下方")
            conds.append("有板块或指数共振")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            conds.append("在支撑位收出止跌K线")
            conds.append("分时走势企稳")
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
        # 市场风险
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return RiskLevel.HIGH
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
        if not account:
            return "一般"

        # 防守环境
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE:
                return "一般"
            return "不适合"

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
