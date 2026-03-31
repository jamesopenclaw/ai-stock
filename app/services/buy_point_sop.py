"""
单股买点分析 SOP 服务
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional

from app.data.tushare_client import normalize_ts_code, tushare_client
from app.models.schemas import (
    BuyPointType,
    BuyPointSopAddPositionDecision,
    BuyPointSopAccountContext,
    BuyPointSopBasicInfo,
    BuyPointSopDailyJudgement,
    BuyPointSopExecution,
    BuyPointSopIntradayJudgement,
    BuyPointSopOrderPlan,
    BuyPointSopPositionAdvice,
    BuyPointSopResponse,
    BuySignalTag,
    MarketEnvTag,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
    StructureStateTag,
)
from app.services.account_adapter import AccountAdapterService
from app.services.buy_point import buy_point_service
from app.services.decision_context import decision_context_service
from app.services.stock_checkup import stock_checkup_service
from app.services.stock_filter import stock_filter_service


@dataclass
class DailyLevelSnapshot:
    ma5: Optional[float]
    ma10: Optional[float]
    ma20: Optional[float]
    prev_high: Optional[float]
    prev_low: Optional[float]
    range_high_20d: Optional[float]
    range_low_20d: Optional[float]


@dataclass
class DirectionExposureSnapshot:
    has_same_code: bool
    same_sector_codes: List[str]
    summary: str


class BuyPointSopService:
    """生成符合交易 SOP 的单股买点分析结果。"""

    def _load_history_payload(
        self,
        ts_code: str,
        trade_date: str,
    ) -> tuple[List[Dict], Optional[str]]:
        history_rows, _, resolved_trade_date = stock_checkup_service._load_history_payload(
            ts_code,
            trade_date,
        )
        return history_rows, resolved_trade_date

    async def analyze(
        self,
        ts_code: str,
        trade_date: str,
        account_id: Optional[str] = None,
    ) -> BuyPointSopResponse:
        normalized_code = normalize_ts_code(ts_code)
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=120,
            include_holdings=True,
            account_id=account_id,
        )
        stable_market_env = context.market_env
        realtime_market_env = getattr(context, "realtime_market_env", None) or stable_market_env
        try:
            stocks, found_in_candidates = decision_context_service.merge_single_stock_into_context(
                trade_date,
                context.stocks,
                normalized_code,
                candidate_source_tag="买点分析",
            )
        except Exception:
            stocks = context.stocks
            found_in_candidates = any(
                normalize_ts_code(stock.ts_code) == normalized_code
                for stock in context.stocks
            )
        try:
            target_input = decision_context_service.build_single_stock_input(
                normalized_code,
                trade_date,
                candidate_source_tag="买点分析",
            )
        except Exception:
            try:
                target_input = next(
                    stock for stock in stocks if normalize_ts_code(stock.ts_code) == normalized_code
                )
            except StopIteration:
                target_input = self._build_fallback_target_input(normalized_code)
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )
        stock_pools = stock_filter_service.classify_pools(
            trade_date,
            stocks,
            context.holdings_list,
            context.account,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            scored_stocks=scored_stocks,
        )
        target_scored, pool_tag = self._resolve_target_pool_stock(stock_pools, normalized_code)
        if target_scored is None:
            target_scored = next(
                (stock for stock in scored_stocks if normalize_ts_code(stock.ts_code) == normalized_code),
                None,
            )
            pool_tag = StockPoolTag.NOT_IN_POOL
        if target_scored is None:
            target_scored = self._build_fallback_scored_stock(target_input)

        target_scored.stock_pool_tag = pool_tag
        analysis_stock = target_scored.model_copy(deep=True)
        if analysis_stock.stock_pool_tag == StockPoolTag.HOLDING_PROCESS:
            analysis_stock.stock_pool_tag = (
                StockPoolTag.ACCOUNT_EXECUTABLE
                if analysis_stock.stock_tradeability_tag != StockTradeabilityTag.NOT_RECOMMENDED
                else StockPoolTag.TREND_RECOGNITION
            )
        buy_point = buy_point_service._analyze_stock_buy_point(
            analysis_stock,
            realtime_market_env,
            context.account,
        )
        history_rows, resolved_trade_date = self._load_history_payload(
            normalized_code,
            trade_date,
        )
        levels = self._build_daily_levels(target_input, history_rows)
        direction_exposure = self._build_direction_exposure(
            normalized_code,
            target_input.sector_name,
            context.holdings_list,
            trade_date,
        )
        same_code_holding = self._find_same_code_holding(normalized_code, context.holdings_list)
        account_context = self._build_account_context(
            context.account,
            realtime_market_env,
            direction_exposure,
            target_scored,
            normalized_code,
            context.holdings_list,
        )
        daily_judgement = self._build_daily_judgement(
            target_input,
            target_scored,
            buy_point,
            stable_market_env,
            levels,
        )
        intraday_judgement = self._build_intraday_judgement(
            target_input,
            buy_point,
            daily_judgement.buy_point_level,
            levels,
        )
        add_position_decision = self._build_add_position_decision(
            target_input,
            target_scored,
            realtime_market_env,
            context.account,
            account_context,
            direction_exposure,
            daily_judgement,
            intraday_judgement,
            levels,
            same_code_holding,
        )
        order_plan = self._build_order_plan(
            target_input,
            target_scored,
            buy_point,
            realtime_market_env,
            account_context,
            daily_judgement,
            intraday_judgement,
            levels,
        )
        position_advice = self._build_position_advice(
            context.account,
            realtime_market_env,
            account_context,
            direction_exposure,
            daily_judgement,
            intraday_judgement,
            order_plan,
            add_position_decision,
        )
        execution = self._build_execution(
            account_context,
            daily_judgement,
            intraday_judgement,
            position_advice,
            add_position_decision,
        )

        return BuyPointSopResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date or context.resolved_stock_trade_date,
            stock_found_in_candidates=found_in_candidates,
            basic_info=BuyPointSopBasicInfo(
                ts_code=target_input.ts_code,
                stock_name=target_input.stock_name,
                sector_name=target_input.sector_name,
                market_env_tag=realtime_market_env.market_env_tag.value,
                stable_market_env_tag=stable_market_env.market_env_tag.value,
                realtime_market_env_tag=realtime_market_env.market_env_tag.value,
                buy_signal_tag=buy_point.buy_signal_tag.value,
                buy_point_type=buy_point.buy_point_type.value,
                candidate_bucket_tag=target_scored.candidate_bucket_tag or "",
                quote_time=target_input.quote_time,
                data_source=target_input.data_source,
            ),
            account_context=account_context,
            daily_judgement=daily_judgement,
            intraday_judgement=intraday_judgement,
            order_plan=order_plan,
            add_position_decision=add_position_decision,
            position_advice=position_advice,
            execution=execution,
        )

    def _resolve_target_pool_stock(
        self,
        stock_pools,
        ts_code: str,
    ) -> tuple[Optional[StockOutput], StockPoolTag]:
        groups = [
            (stock_pools.holding_process_pool, StockPoolTag.HOLDING_PROCESS),
            (stock_pools.account_executable_pool, StockPoolTag.ACCOUNT_EXECUTABLE),
            (stock_pools.trend_recognition_pool, StockPoolTag.TREND_RECOGNITION),
            (stock_pools.market_watch_pool, StockPoolTag.MARKET_WATCH),
        ]
        for group, pool_tag in groups:
            for stock in group:
                if normalize_ts_code(stock.ts_code) == ts_code:
                    return stock, pool_tag
        return None, StockPoolTag.NOT_IN_POOL

    def _build_fallback_target_input(self, ts_code: str):
        """当单股行情输入不可用时，退化为最小可分析输入。"""
        return SimpleNamespace(
            ts_code=ts_code,
            stock_name=ts_code,
            sector_name="未知",
            close=0.0,
            open=0.0,
            high=0.0,
            low=0.0,
            pre_close=0.0,
            change_pct=0.0,
            turnover_rate=0.0,
            amount=0.0,
            vol_ratio=0.0,
            avg_price=None,
            intraday_volume_ratio=None,
            candidate_source_tag="买点分析",
            quote_time=None,
            data_source="fallback",
            concept_names=[],
        )

    def _build_fallback_scored_stock(self, target_input) -> StockOutput:
        """当候选评分结果缺失时，构造最小可分析对象，避免 SOP 整体失败。"""
        return StockOutput(
            ts_code=target_input.ts_code,
            stock_name=target_input.stock_name,
            sector_name=getattr(target_input, "sector_name", "未知") or "未知",
            change_pct=float(getattr(target_input, "change_pct", 0) or 0),
            amount=float(getattr(target_input, "amount", 0) or 0),
            close=float(getattr(target_input, "close", 0) or 0),
            open=float(getattr(target_input, "open", 0) or 0),
            high=float(getattr(target_input, "high", 0) or 0),
            low=float(getattr(target_input, "low", 0) or 0),
            pre_close=float(getattr(target_input, "pre_close", 0) or 0),
            vol_ratio=getattr(target_input, "vol_ratio", None),
            turnover_rate=float(getattr(target_input, "turnover_rate", 0) or 0),
            stock_score=0.0,
            candidate_source_tag=getattr(target_input, "candidate_source_tag", "") or "买点分析",
            candidate_bucket_tag="",
            volume=getattr(target_input, "volume", None),
            avg_price=getattr(target_input, "avg_price", None),
            intraday_volume_ratio=getattr(target_input, "intraday_volume_ratio", None),
            quote_time=getattr(target_input, "quote_time", None),
            data_source=getattr(target_input, "data_source", None),
            concept_names=list(getattr(target_input, "concept_names", []) or []),
            stock_strength_tag=StockStrengthTag.MEDIUM,
            stock_continuity_tag=StockContinuityTag.OBSERVABLE,
            stock_tradeability_tag=StockTradeabilityTag.CAUTION,
            stock_core_tag=StockCoreTag.FOLLOW,
            stock_pool_tag=StockPoolTag.NOT_IN_POOL,
            structure_state_tag=None,
            stock_comment="候选评分缺失，按最小上下文生成买点 SOP。",
        )

    def _build_daily_levels(self, target_input, history_rows: List[Dict]) -> DailyLevelSnapshot:
        closes = [float(row.get("close") or 0) for row in history_rows if float(row.get("close") or 0) > 0]
        history_window = history_rows[:-1] if len(history_rows) > 1 else history_rows
        highs_20 = [
            float(row.get("high") or 0)
            for row in history_window[-20:]
            if float(row.get("high") or 0) > 0
        ]
        lows_20 = [
            float(row.get("low") or 0)
            for row in history_window[-20:]
            if float(row.get("low") or 0) > 0
        ]
        prev_row = history_rows[-2] if len(history_rows) >= 2 else None
        return DailyLevelSnapshot(
            ma5=self._calc_ma(closes, 5),
            ma10=self._calc_ma(closes, 10),
            ma20=self._calc_ma(closes, 20),
            prev_high=self._round_price(prev_row.get("high")) if prev_row else None,
            prev_low=self._round_price(prev_row.get("low")) if prev_row else None,
            range_high_20d=self._round_price(max(highs_20)) if highs_20 else self._round_price(target_input.high),
            range_low_20d=self._round_price(min(lows_20)) if lows_20 else self._round_price(target_input.low),
        )

    def _build_direction_exposure(
        self,
        target_code: str,
        target_sector: str,
        holdings_list: List[dict],
        trade_date: str,
    ) -> DirectionExposureSnapshot:
        same_code = False
        same_sector_codes: List[str] = []
        compact_trade_date = str(trade_date).replace("-", "")[:8]

        for holding in holdings_list:
            holding_code = normalize_ts_code(str(holding.get("ts_code") or ""))
            if not holding_code:
                continue
            if holding_code == target_code:
                same_code = True
                continue
            sector_name = str(holding.get("sector_name") or "")
            if not sector_name:
                try:
                    detail = tushare_client.get_stock_detail(holding_code, compact_trade_date)
                except Exception:
                    detail = {}
                sector_name = str(detail.get("sector_name") or "")
            if sector_name and sector_name == target_sector:
                same_sector_codes.append(holding_code)

        if same_code:
            summary = "已有同一只股票持仓，属于加仓语境。"
        elif same_sector_codes:
            summary = f"已有同方向暴露（同板块 {len(same_sector_codes)} 只），新仓必须更优。"
        else:
            summary = "暂无明显同方向重复暴露。"

        return DirectionExposureSnapshot(
            has_same_code=same_code,
            same_sector_codes=same_sector_codes,
            summary=summary,
        )

    def _find_same_code_holding(
        self,
        target_code: str,
        holdings_list: List[dict],
    ) -> Optional[dict]:
        for holding in holdings_list:
            if normalize_ts_code(str(holding.get("ts_code") or "")) == target_code:
                return holding
        return None

    def _build_account_context(
        self,
        account,
        market_env,
        direction_exposure: DirectionExposureSnapshot,
        target_stock: StockOutput,
        target_code: str,
        holdings_list: List[dict],
    ) -> BuyPointSopAccountContext:
        position_status = self._position_status(account.total_position_ratio, account.holding_count)
        current_use = "加仓" if direction_exposure.has_same_code else "新开仓"
        market_suitability = self._market_suitability(market_env.market_env_tag)
        holding_ok = True
        holding_reason = None
        same_code_holding = self._find_same_code_holding(target_code, holdings_list)

        if not direction_exposure.has_same_code:
            holding_ok, holding_reason, _, _ = self._resolve_holding_constraint(
                target_stock,
                account,
                holdings_list,
            )

        if account.total_position_ratio >= AccountAdapterService.POSITION_HIGH:
            conclusion = "当前不适合承担 T+1 风险"
        elif account.today_new_buy_count >= AccountAdapterService.NEW_BUY_COUNT_LIMIT:
            conclusion = "当前不适合承担 T+1 风险"
        elif direction_exposure.has_same_code:
            conclusion = "已有同一只股票持仓，只能按加仓语境处理"
        elif not holding_ok and holding_reason:
            conclusion = holding_reason
        elif market_env.market_env_tag == MarketEnvTag.DEFENSE:
            conclusion = "弱市环境，只能低吸，不追高"
        elif holding_reason:
            conclusion = holding_reason
        elif account.total_position_ratio < AccountAdapterService.POSITION_LOW:
            conclusion = "轻仓新开仓，可试错"
        else:
            conclusion = "仓位不算轻，只能等更舒服的确认位"

        return BuyPointSopAccountContext(
            position_status=position_status,
            same_direction_exposure=direction_exposure.summary,
            current_use=current_use,
            market_suitability=market_suitability,
            account_conclusion=conclusion,
            same_code_holding_qty=self._safe_int(same_code_holding, "holding_qty"),
            same_code_cost_price=self._safe_float(same_code_holding, "cost_price"),
            same_code_market_price=self._safe_float(same_code_holding, "market_price"),
            same_code_pnl_pct=self._safe_float(same_code_holding, "pnl_pct"),
        )

    def _resolve_holding_constraint(
        self,
        target_stock: StockOutput,
        account,
        holdings_list: List[dict],
    ) -> tuple[bool, Optional[str], Optional[str], float]:
        if not holdings_list:
            return True, None, None, 0.0
        holding_profile = stock_filter_service._build_holding_profile(
            holdings_list,
            account,
        )
        return stock_filter_service._assess_holding_fit(
            target_stock,
            holding_profile,
            account,
        )

    def _build_daily_judgement(
        self,
        target_input,
        target_stock: StockOutput,
        buy_point,
        market_env,
        levels: DailyLevelSnapshot,
    ) -> BuyPointSopDailyJudgement:
        stage = self._resolve_stage(target_stock, target_input.change_pct)
        ma_status = self._ma_status(float(target_input.close or 0), levels)
        price = float(target_input.close or 0)
        pressure_ref = max(
            value for value in [levels.prev_high, levels.range_high_20d] if value is not None
        ) if any(value is not None for value in [levels.prev_high, levels.range_high_20d]) else None
        is_near_pressure = pressure_ref is not None and price >= pressure_ref * 0.985
        distorted = float(target_input.change_pct or 0) >= 8
        strong_track = "是强势赛道" if target_stock.sector_profile_tag and str(target_stock.sector_profile_tag).startswith("SectorProfileTag.A_") else "赛道强度需结合板块再确认"

        risk_items: List[str] = []
        if is_near_pressure:
            risk_items.append("接近前高/20日区间压力，不适合无脑追。")
        if distorted:
            risk_items.append("当日涨幅偏大，位置开始失真。")
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            risk_items.append("市场环境偏防守，主动追价容错低。")
        if target_stock.stock_tradeability_tag == StockTradeabilityTag.CAUTION:
            risk_items.append("个股交易性一般，容易买在不舒服的位置。")
        if target_stock.stock_tradeability_tag == StockTradeabilityTag.NOT_RECOMMENDED:
            risk_items.append("个股交易性偏差，结构没有给出舒服买点。")
        if not risk_items:
            risk_items.append("主要风险来自盘中确认是否真实完成。")

        if (
            buy_point.buy_signal_tag == BuySignalTag.CAN_BUY
            and target_stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE
            and market_env.market_env_tag == MarketEnvTag.ATTACK
            and stage not in {"高潮", "退潮"}
            and not is_near_pressure
            and not distorted
        ):
            level = "A"
        elif buy_point.buy_signal_tag == BuySignalTag.CAN_BUY:
            level = "B"
        elif buy_point.buy_signal_tag == BuySignalTag.OBSERVE and not is_near_pressure:
            level = "B"
        elif buy_point.buy_signal_tag == BuySignalTag.OBSERVE:
            level = "C"
        else:
            level = "D"

        reference_levels = [
            f"MA5：{self._display_price(levels.ma5)}",
            f"MA10：{self._display_price(levels.ma10)}",
            f"MA20：{self._display_price(levels.ma20)}",
            f"前一日高点：{self._display_price(levels.prev_high)}",
            f"前一日低点：{self._display_price(levels.prev_low)}",
            f"近20日区间高点：{self._display_price(levels.range_high_20d)}",
            f"近20日区间低点：{self._display_price(levels.range_low_20d)}",
        ]
        reason = "；".join(
            [
                f"当前阶段偏{stage}",
                ma_status,
                "接近关键压力位" if is_near_pressure else "离关键压力还有缓冲",
                strong_track,
            ]
        )

        return BuyPointSopDailyJudgement(
            current_stage=stage,
            buy_signal=f"{buy_point.buy_point_type.value}，{buy_point.buy_signal_tag.value}",
            buy_point_level=level,
            reason=reason,
            risk_items=risk_items,
            reference_levels=reference_levels,
        )

    def _build_intraday_judgement(
        self,
        target_input,
        buy_point,
        daily_level: str,
        levels: DailyLevelSnapshot,
    ) -> BuyPointSopIntradayJudgement:
        realtime = str(target_input.data_source or "").startswith("realtime_")
        price = float(target_input.close or 0)
        breakout_ref = max(
            value for value in [levels.prev_high, levels.range_high_20d] if value is not None
        ) if any(value is not None for value in [levels.prev_high, levels.range_high_20d]) else None
        support_ref = min(
            value for value in [levels.ma5, levels.ma10, levels.prev_low] if value is not None
        ) if any(value is not None for value in [levels.ma5, levels.ma10, levels.prev_low]) else None
        volume_quality = self._volume_quality(target_input)

        if not realtime:
            conclusion = "放弃" if daily_level == "D" else "等确认"
            return BuyPointSopIntradayJudgement(
                price_vs_avg_line="均价线关系 [需确认]",
                intraday_structure="分时结构 [需确认]",
                volume_quality=volume_quality,
                key_level_status=self._key_level_status(price, breakout_ref, support_ref),
                conclusion=conclusion,
                note="当前不是实时分时口径，盘中是否真正转强需要开盘后再确认。",
            )

        structure = self._resolve_intraday_structure(target_input, breakout_ref, support_ref)
        price_vs_avg_line = self._resolve_price_vs_avg_line(target_input)
        if structure in {"回踩承接", "拉升后横住", "突破后站稳"} and daily_level == "A":
            conclusion = "买"
        elif structure == "冲高回落" or daily_level == "D":
            conclusion = "放弃"
        else:
            conclusion = "等确认"

        return BuyPointSopIntradayJudgement(
            price_vs_avg_line=price_vs_avg_line,
            intraday_structure=structure,
            volume_quality=volume_quality,
            key_level_status=self._key_level_status(price, breakout_ref, support_ref),
            conclusion=conclusion,
            note="当前口径已结合实时均价线判断强弱，具体承接质量仍建议配合盘口观察。",
        )

    def _build_order_plan(
        self,
        target_input,
        target_stock: StockOutput,
        buy_point,
        market_env,
        account_context: BuyPointSopAccountContext,
        daily_judgement: BuyPointSopDailyJudgement,
        intraday_judgement: BuyPointSopIntradayJudgement,
        levels: DailyLevelSnapshot,
    ) -> BuyPointSopOrderPlan:
        price = float(target_input.close or 0)
        structure_type = self._resolve_buy_structure_type(
            target_input,
            buy_point,
            daily_judgement,
            intraday_judgement,
            levels,
        )
        market_state = self._resolve_market_state(market_env.market_env_tag)
        account_tight = self._is_account_tight(account_context)
        low_absorb_ref = self._select_low_absorb_ref(
            price,
            target_input,
            levels,
            structure_type,
            market_state,
        )
        breakout_ref = self._select_breakout_ref(
            price,
            target_input,
            levels,
            structure_type,
        )
        retrace_confirm_ref = self._select_retrace_confirm_ref(
            price,
            target_input,
            levels,
            structure_type,
            breakout_ref,
        )
        invalid_price = self._round_price(getattr(buy_point, "buy_invalid_price", None))
        if invalid_price is None:
            invalid_price = self._select_invalid_ref(
                price,
                target_input,
                levels,
                structure_type,
                retrace_confirm_ref,
            )
        give_up_ref = self._select_give_up_ref(
            price,
            levels,
            structure_type,
            breakout_ref,
            low_absorb_ref,
            market_state,
            daily_judgement.buy_point_level,
            account_tight,
        )

        low_absorb_zone = self._format_support_zone(
            low_absorb_ref,
            *self._low_absorb_buffer_pct(structure_type, market_state, target_input, account_tight),
        )
        breakout_zone = self._format_above_zone(
            breakout_ref,
            *self._breakout_buffer_pct(structure_type, market_state, target_input, account_tight),
        )
        retrace_confirm_zone = self._format_support_zone(
            retrace_confirm_ref,
            *self._retrace_buffer_pct(structure_type, market_state, target_input, account_tight),
        )
        give_up_price = self._display_price(give_up_ref)
        structure_trigger = self._resolve_trigger_condition(
            structure_type,
            low_absorb_zone,
            breakout_zone,
            retrace_confirm_zone,
            give_up_price,
            buy_point.buy_trigger_cond,
        )
        invalid_condition = self._resolve_invalid_condition(
            self._display_price(invalid_price),
            buy_point.buy_invalid_cond,
        )

        return BuyPointSopOrderPlan(
            low_absorb_price=low_absorb_zone,
            breakout_price=breakout_zone,
            retrace_confirm_price=retrace_confirm_zone,
            give_up_price=give_up_price,
            trigger_condition=structure_trigger,
            invalid_condition=invalid_condition,
            above_no_chase=give_up_price,
            below_no_buy=self._display_price(invalid_price),
        )

    def _build_add_position_decision(
        self,
        target_input,
        target_stock: StockOutput,
        market_env,
        account,
        account_context: BuyPointSopAccountContext,
        direction_exposure: DirectionExposureSnapshot,
        daily_judgement: BuyPointSopDailyJudgement,
        intraday_judgement: BuyPointSopIntradayJudgement,
        levels: DailyLevelSnapshot,
        same_code_holding: Optional[dict],
    ) -> BuyPointSopAddPositionDecision:
        if not direction_exposure.has_same_code:
            return BuyPointSopAddPositionDecision(
                eligible=False,
                decision="不加",
                reason="当前不是加仓语境，这里仍按新开仓逻辑处理。",
            )

        pnl_pct = self._safe_float(same_code_holding, "pnl_pct")
        holding_market_value = self._safe_float(same_code_holding, "holding_market_value") or 0.0
        total_asset = float(getattr(account, "total_asset", 0) or 0)
        single_stock_ratio = holding_market_value / total_asset if total_asset > 0 else 0.0
        stage = str(getattr(daily_judgement, "current_stage", "") or "")
        structure = str(getattr(intraday_judgement, "intraday_structure", "") or "")
        volume_quality = str(getattr(intraday_judgement, "volume_quality", "") or "")
        price = float(getattr(target_input, "close", 0) or 0)
        pressure_ref = max(
            value for value in [levels.prev_high, levels.range_high_20d] if value is not None
        ) if any(value is not None for value in [levels.prev_high, levels.range_high_20d]) else None
        support_ref = min(
            value for value in [levels.ma5, levels.ma10, levels.prev_low] if value is not None
        ) if any(value is not None for value in [levels.ma5, levels.ma10, levels.prev_low]) else None
        distorted = float(getattr(target_input, "change_pct", 0) or 0) >= 8
        near_pressure = pressure_ref is not None and price >= pressure_ref * 0.985
        trigger_scene = self._resolve_add_position_scene(target_stock, structure)

        blockers: List[str] = []
        if pnl_pct is None:
            blockers.append("缺少底仓盈亏数据，不能给加仓建议。")
        elif pnl_pct < 0:
            blockers.append("底仓当前为亏损状态，禁止补仓。")
        if structure == "冲高回落":
            blockers.append("当前是冲高回落结构，不适合加仓。")
        if stage == "高潮" or distorted:
            blockers.append("当前接近短线过热区，禁止在末端加速时重加。")
        if market_env.market_env_tag == MarketEnvTag.DEFENSE and trigger_scene != "回踩确认":
            blockers.append("弱市只允许更保守的回踩确认，不适合主动扩大仓位。")
        if market_env.market_env_tag == MarketEnvTag.DEFENSE and intraday_judgement.conclusion == "放弃":
            blockers.append("弱市下分时没有确认，不能逆势加仓。")
        if account.total_position_ratio >= AccountAdapterService.POSITION_HIGH:
            blockers.append("账户总仓已偏重，再加会明显压缩撤退空间。")
        if single_stock_ratio >= 0.8:
            blockers.append("单票仓位已接近上限，不宜继续加。")
        if support_ref is None:
            blockers.append("当前无法明确失效位，不能做加仓决策。")

        trend_score = self._score_add_position_trend(daily_judgement, target_stock)
        position_score = self._score_add_position_location(
            trigger_scene,
            stage,
            near_pressure,
            distorted,
            intraday_judgement,
        )
        volume_price_score = self._score_add_position_volume_price(
            structure,
            volume_quality,
            intraday_judgement,
        )
        sector_sentiment_score = self._score_add_position_sector_sentiment(target_stock, market_env)
        account_risk_score = self._score_add_position_account_risk(
            account,
            single_stock_ratio,
            pnl_pct,
        )
        score_total = trend_score + position_score + volume_price_score + sector_sentiment_score + account_risk_score

        if blockers:
            decision = "不加"
            reason = "；".join(blockers[:2])
        elif score_total >= 8 and pnl_pct is not None and pnl_pct >= 1 and intraday_judgement.conclusion == "买":
            decision = "可加"
            reason = f"{trigger_scene} 已较明确，底仓已有利润垫，可以按计划扩大正确头寸。"
        elif score_total >= 6 and pnl_pct is not None and pnl_pct >= 0:
            decision = "仅可小加"
            reason = "结构还不错，但位置、节奏或账户容错没有好到可以标准加仓，只适合小幅推进。"
        else:
            decision = "不加"
            reason = "确认条件还不够完整，继续持有观察比现在扩大仓位更稳。"

        return BuyPointSopAddPositionDecision(
            eligible=True,
            decision=decision,
            score_total=score_total,
            trend_score=trend_score,
            position_score=position_score,
            volume_price_score=volume_price_score,
            sector_sentiment_score=sector_sentiment_score,
            account_risk_score=account_risk_score,
            trigger_scene=trigger_scene,
            blockers=blockers,
            reason=reason,
        )

    def _build_position_advice(
        self,
        account,
        market_env,
        account_context: BuyPointSopAccountContext,
        direction_exposure: DirectionExposureSnapshot,
        daily_judgement: BuyPointSopDailyJudgement,
        intraday_judgement: BuyPointSopIntradayJudgement,
        order_plan: BuyPointSopOrderPlan,
        add_position_decision: Optional[BuyPointSopAddPositionDecision] = None,
    ) -> BuyPointSopPositionAdvice:
        add_position_decision = add_position_decision or BuyPointSopAddPositionDecision(
            eligible=False,
            decision="不加",
            reason="当前不满足加仓条件。",
        )
        if direction_exposure.has_same_code:
            return self._build_add_position_advice(
                account,
                account_context,
                order_plan,
                add_position_decision,
            )

        if (
            self._account_conclusion_blocks_entry(account_context.account_conclusion)
            or daily_judgement.buy_point_level == "D"
            or intraday_judgement.conclusion == "放弃"
        ):
            suggestion = "不出手"
            if self._account_conclusion_blocks_entry(account_context.account_conclusion):
                reason = account_context.account_conclusion
            else:
                reason = "账户或结构至少有一项没有过关，不值得承担当天买错跑不掉的风险。"
        elif (
            daily_judgement.buy_point_level == "A"
            and intraday_judgement.conclusion == "买"
            and market_env.market_env_tag == MarketEnvTag.ATTACK
            and account.total_position_ratio < AccountAdapterService.POSITION_LOW
            and not direction_exposure.has_same_code
            and not direction_exposure.same_sector_codes
            and "同板块持仓" not in str(account_context.account_conclusion or "")
        ):
            suggestion = "中仓参与"
            reason = "环境、结构、分时和账户都比较匹配，可以按计划仓位参与。"
        else:
            suggestion = "轻仓试错"
            if direction_exposure.has_same_code:
                reason = "当前是加仓语境，只能等更强确认后用试错仓处理。"
            elif "同板块持仓" in str(account_context.account_conclusion or ""):
                reason = account_context.account_conclusion
            else:
                reason = "买点还需要盘中确认或账户已有约束，只适合试错仓位。"

        invalidation_level = order_plan.below_no_buy
        return BuyPointSopPositionAdvice(
            suggestion=suggestion,
            reason=reason,
            invalidation_level=invalidation_level,
            invalidation_action="跌破失效位后不再找理由硬扛，直接放弃这笔计划。",
            risk_control_action="新开仓失败直接撤退，不把试错单拖成重仓问题单。",
        )

    def _build_add_position_advice(
        self,
        account,
        account_context: BuyPointSopAccountContext,
        order_plan: BuyPointSopOrderPlan,
        add_position_decision: BuyPointSopAddPositionDecision,
    ) -> BuyPointSopPositionAdvice:
        base_position_pct = self._resolve_same_code_position_pct(account, account_context)
        max_position_pct = 0.8

        if add_position_decision.decision == "可加":
            increment_position_pct = 0.2 if base_position_pct < 0.4 else 0.1
            plan_position_pct = min(max_position_pct, base_position_pct + increment_position_pct)
            suggestion = "标准加仓"
            reason = add_position_decision.reason
        elif add_position_decision.decision == "仅可小加":
            increment_position_pct = min(0.1, max(0.0, max_position_pct - base_position_pct))
            plan_position_pct = min(max_position_pct, base_position_pct + increment_position_pct)
            suggestion = "小幅加仓"
            reason = add_position_decision.reason
        else:
            increment_position_pct = 0.0
            plan_position_pct = base_position_pct
            suggestion = "继续持有"
            reason = add_position_decision.reason or "当前不满足加仓条件，先保持底仓观察。"

        return BuyPointSopPositionAdvice(
            suggestion=suggestion,
            reason=reason,
            invalidation_level=order_plan.below_no_buy,
            invalidation_action="新增仓买的是确认延续，一旦失效先撤新增仓；主逻辑破坏再处理底仓。",
            plan_position_pct=round(plan_position_pct, 4),
            increment_position_pct=round(increment_position_pct, 4),
            max_position_pct=max_position_pct,
            risk_control_action="加仓失败先撤新增仓，不把舒服单拖成高波动重仓单。",
            exit_priority="先撤新增仓",
        )

    def _build_execution(
        self,
        account_context: BuyPointSopAccountContext,
        daily_judgement: BuyPointSopDailyJudgement,
        intraday_judgement: BuyPointSopIntradayJudgement,
        position_advice: BuyPointSopPositionAdvice,
        add_position_decision: Optional[BuyPointSopAddPositionDecision] = None,
    ) -> BuyPointSopExecution:
        add_position_decision = add_position_decision or BuyPointSopAddPositionDecision(
            eligible=False,
            decision="不加",
            reason="当前不满足加仓条件。",
        )
        if str(getattr(account_context, "current_use", "") or "") == "加仓":
            if add_position_decision.decision == "可加":
                return BuyPointSopExecution(
                    action="加",
                    reason=add_position_decision.reason,
                )
            if add_position_decision.decision == "仅可小加":
                return BuyPointSopExecution(
                    action="等",
                    reason=add_position_decision.reason,
                )
            return BuyPointSopExecution(
                action="不加",
                reason=add_position_decision.reason or "当前不满足加仓条件，继续持有观察。",
            )
        if position_advice.suggestion == "不出手" or daily_judgement.buy_point_level == "D":
            return BuyPointSopExecution(
                action="放弃",
                reason="账户、结构或位置至少一项不合格，当前不值得执行。",
            )
        if intraday_judgement.conclusion == "买":
            return BuyPointSopExecution(
                action="买",
                reason="日线通过，分时也出现了相对明确的转强/承接信号。",
            )
        return BuyPointSopExecution(
            action="等",
            reason="日线可以继续看，但分时确认还没到位，先按计划等触发。",
        )

    def _resolve_add_position_scene(self, target_stock: StockOutput, intraday_structure: str) -> str:
        if intraday_structure == "回踩承接":
            return "回踩确认"
        if intraday_structure == "突破后站稳":
            return "突破确认"
        if intraday_structure == "拉升后横住":
            return "趋势延续"
        return "无"

    def _score_add_position_trend(
        self,
        daily_judgement: BuyPointSopDailyJudgement,
        target_stock: StockOutput,
    ) -> int:
        if daily_judgement.buy_point_level == "A" and target_stock.stock_strength_tag == StockStrengthTag.STRONG:
            return 2
        if daily_judgement.buy_point_level in {"A", "B"}:
            return 1
        return 0

    def _score_add_position_location(
        self,
        trigger_scene: str,
        stage: str,
        near_pressure: bool,
        distorted: bool,
        intraday_judgement: BuyPointSopIntradayJudgement,
    ) -> int:
        if stage == "高潮" or distorted or near_pressure:
            return 0
        if trigger_scene in {"回踩确认", "突破确认"} and intraday_judgement.conclusion == "买":
            return 2
        if trigger_scene in {"回踩确认", "突破确认", "趋势延续"}:
            return 1
        return 0

    def _score_add_position_volume_price(
        self,
        structure: str,
        volume_quality: str,
        intraday_judgement: BuyPointSopIntradayJudgement,
    ) -> int:
        if structure == "冲高回落" or intraday_judgement.conclusion == "放弃":
            return 0
        if ("放量" in volume_quality and structure in {"回踩承接", "突破后站稳", "拉升后横住"}):
            return 2
        if structure in {"回踩承接", "突破后站稳", "拉升后横住"}:
            return 1
        return 0

    def _score_add_position_sector_sentiment(self, target_stock: StockOutput, market_env) -> int:
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return 0
        if (
            market_env.market_env_tag == MarketEnvTag.ATTACK
            and target_stock.stock_strength_tag == StockStrengthTag.STRONG
            and target_stock.stock_core_tag in {StockCoreTag.CORE, StockCoreTag.FOLLOW}
        ):
            return 2
        return 1 if market_env.market_env_tag == MarketEnvTag.NEUTRAL else 0

    def _score_add_position_account_risk(
        self,
        account,
        single_stock_ratio: float,
        pnl_pct: Optional[float],
    ) -> int:
        if account.total_position_ratio >= AccountAdapterService.POSITION_HIGH or single_stock_ratio >= 0.8:
            return 0
        if account.total_position_ratio < AccountAdapterService.POSITION_LOW and (pnl_pct or 0) >= 1:
            return 2
        return 1

    def _resolve_same_code_position_pct(
        self,
        account,
        account_context: BuyPointSopAccountContext,
    ) -> float:
        total_asset = float(getattr(account, "total_asset", 0) or 0)
        market_price = float(account_context.same_code_market_price or 0)
        holding_qty = int(account_context.same_code_holding_qty or 0)
        if total_asset <= 0 or market_price <= 0 or holding_qty <= 0:
            return 0.0
        return min(1.0, (market_price * holding_qty) / total_asset)

    def _safe_float(self, payload: Optional[dict], key: str) -> Optional[float]:
        if not payload:
            return None
        value = payload.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _safe_int(self, payload: Optional[dict], key: str) -> Optional[int]:
        if not payload:
            return None
        value = payload.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _position_status(self, ratio: float, holding_count: int) -> str:
        if ratio >= AccountAdapterService.POSITION_HIGH or holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH:
            return f"重仓（仓位 {ratio:.0%}）"
        if ratio >= AccountAdapterService.POSITION_MEDIUM or holding_count >= AccountAdapterService.HOLDING_COUNT_MEDIUM:
            return f"中仓（仓位 {ratio:.0%}）"
        return f"轻仓（仓位 {ratio:.0%}）"

    def _market_suitability(self, market_env_tag: MarketEnvTag) -> str:
        if market_env_tag == MarketEnvTag.ATTACK:
            return "市场允许主动试错，但仍要先等分时确认。"
        if market_env_tag == MarketEnvTag.DEFENSE:
            return "市场偏防守，只能低吸或回踩确认，不能追高。"
        return "市场中性，只做更舒服的确认位。"

    def _resolve_stage(self, target_stock: StockOutput, change_pct: float) -> str:
        state = getattr(target_stock.structure_state_tag, "value", "")
        if state == StructureStateTag.START.value:
            return "启动"
        if state == StructureStateTag.ACCELERATE.value:
            return "加速"
        if state == StructureStateTag.REPAIR.value:
            return "中继"
        if state == StructureStateTag.LATE_STAGE.value:
            return "高潮"
        if change_pct < 0:
            return "退潮"
        return "中继"

    def _ma_status(self, price: float, levels: DailyLevelSnapshot) -> str:
        bits = []
        for label, value in (("MA5", levels.ma5), ("MA10", levels.ma10), ("MA20", levels.ma20)):
            if value is None:
                bits.append(f"{label}[需确认]")
            else:
                bits.append(f"{'站上' if price >= value else '跌破'}{label}")
        return "，".join(bits)

    def _volume_quality(self, target_input) -> str:
        realtime_ratio = float(getattr(target_input, "intraday_volume_ratio", None) or 0)
        if realtime_ratio >= 1.8:
            return f"实时放量跟随（相对放量 {realtime_ratio:.1f}）"
        if realtime_ratio >= 1.1:
            return f"实时温和放量（相对放量 {realtime_ratio:.1f}）"
        if realtime_ratio > 0:
            return f"实时量能一般（相对放量 {realtime_ratio:.1f}）"

        ratio = float(getattr(target_input, "vol_ratio", None) or 0)
        if ratio >= 2:
            return f"放量跟随（量比 {ratio:.1f}）"
        if ratio >= 1.2:
            return f"温和放量（量比 {ratio:.1f}）"
        if ratio > 0:
            return f"量能一般（量比 {ratio:.1f}）"
        return "量能 [需确认]"

    def _resolve_intraday_structure(
        self,
        target_input,
        breakout_ref: Optional[float],
        support_ref: Optional[float],
    ) -> str:
        high = float(target_input.high or 0)
        low = float(target_input.low or 0)
        close = float(target_input.close or 0)
        change_pct = float(target_input.change_pct or 0)
        close_quality = 0.5 if high <= low else (close - low) / (high - low)

        if breakout_ref is not None and close >= breakout_ref * 0.998 and close_quality >= 0.7:
            return "突破后站稳"
        if support_ref is not None and close >= support_ref and close_quality >= 0.55 and change_pct > 0:
            return "回踩承接"
        if change_pct > 0 and close_quality >= 0.65:
            return "拉升后横住"
        if change_pct > 0 and close_quality < 0.35:
            return "冲高回落"
        if abs(change_pct) <= 1:
            return "横盘磨"
        return "低位磨底"

    def _key_level_status(
        self,
        price: float,
        breakout_ref: Optional[float],
        support_ref: Optional[float],
    ) -> str:
        if breakout_ref is not None and price >= breakout_ref:
            return f"已到突破关键位 {breakout_ref:.2f} 一带。"
        if support_ref is not None and price >= support_ref:
            return f"仍在支撑位 {support_ref:.2f} 上方。"
        if support_ref is not None:
            return f"已经压到支撑位 {support_ref:.2f} 下方，结构偏弱。"
        return "关键位 [需确认]"

    def _resolve_price_vs_avg_line(self, target_input) -> str:
        price = self._round_price(getattr(target_input, "close", None))
        avg_price = self._extract_avg_price(target_input)
        if price is None or avg_price is None or avg_price <= 0:
            return "均价线关系 [需确认]"
        deviation = (price - avg_price) / avg_price
        pct_text = f"{abs(deviation) * 100:.1f}%"
        if deviation >= 0.003:
            return f"站均价线上（高于均价 {pct_text}）"
        if deviation <= -0.003:
            return f"压均价线下（低于均价 {pct_text}）"
        return f"均价附近拉扯（偏离 {pct_text}）"

    def _extract_avg_price(self, target_input) -> Optional[float]:
        explicit_avg = self._round_price(getattr(target_input, "avg_price", None))
        if explicit_avg is not None and explicit_avg > 0:
            return explicit_avg
        amount = self._round_price(getattr(target_input, "amount", None))
        volume = self._round_price(getattr(target_input, "volume", None))
        price = self._round_price(getattr(target_input, "close", None))
        if amount is None or volume is None or price is None or amount <= 0 or volume <= 0:
            return None
        candidates = []
        for denominator in (volume, volume * 100):
            if denominator <= 0:
                continue
            inferred = amount / denominator
            if inferred <= 0:
                continue
            deviation = abs(inferred - price) / price
            if deviation <= 0.35:
                candidates.append((deviation, inferred))
        if not candidates:
            return None
        return self._round_price(min(candidates, key=lambda item: item[0])[1])

    def _resolve_buy_structure_type(
        self,
        target_input,
        buy_point,
        daily_judgement: BuyPointSopDailyJudgement,
        intraday_judgement: BuyPointSopIntradayJudgement,
        levels: DailyLevelSnapshot,
    ) -> str:
        price = float(target_input.close or 0)
        breakout_ref = self._select_breakout_ref(price, target_input, levels, "基础识别")

        if daily_judgement.buy_point_level == "D":
            return "冲高过热"
        if buy_point.buy_point_type == BuyPointType.BREAKTHROUGH:
            return "突破前高"
        if buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT:
            return "回踩承接"
        if buy_point.buy_point_type == BuyPointType.LOW_SUCK:
            return "趋势中继"
        if intraday_judgement.intraday_structure == "突破后站稳":
            return "突破前高"
        if breakout_ref is not None and price >= breakout_ref * 1.003:
            return "突破后回踩"
        return "趋势中继"

    def _resolve_market_state(self, market_env_tag: MarketEnvTag) -> str:
        if market_env_tag == MarketEnvTag.ATTACK:
            return "强市"
        if market_env_tag == MarketEnvTag.DEFENSE:
            return "弱市"
        return "分化市"

    def _is_account_tight(self, account_context: BuyPointSopAccountContext) -> bool:
        position_status = str(getattr(account_context, "position_status", "") or "")
        exposure = str(getattr(account_context, "same_direction_exposure", "") or "")
        current_use = str(getattr(account_context, "current_use", "") or "")
        conclusion = str(getattr(account_context, "account_conclusion", "") or "")
        return (
            position_status.startswith("中仓")
            or position_status.startswith("重仓")
            or current_use == "加仓"
            or "同方向" in exposure
            or "同一只股票持仓" in exposure
            or "同板块持仓" in conclusion
            or "弱势/亏损持仓" in conclusion
        )

    def _account_conclusion_blocks_entry(self, conclusion: str) -> bool:
        text = str(conclusion or "")
        return any(
            token in text
            for token in [
                "当前不适合承担 T+1 风险",
                "不再新增同方向仓位",
                "先处理旧仓，不做需要追价确认的新开仓",
            ]
        )

    def _select_low_absorb_ref(
        self,
        price: float,
        target_input,
        levels: DailyLevelSnapshot,
        structure_type: str,
        market_state: str,
    ) -> Optional[float]:
        if structure_type == "冲高过热" and market_state != "弱市":
            return self._nearest_support_below(price, levels.ma5, target_input.low, levels.prev_low, levels.ma10)
        if structure_type == "回踩承接":
            return self._nearest_support_below(price, target_input.low, levels.ma5, levels.prev_low, levels.ma10)
        if structure_type == "突破后回踩":
            return self._nearest_reference(price, levels.prev_high, levels.ma5, target_input.low, levels.ma10)
        if market_state == "弱市":
            return self._nearest_support_below(price, levels.ma10, levels.prev_low, levels.ma5, levels.range_low_20d)
        return self._nearest_support_below(price, levels.ma5, levels.ma10, levels.prev_low, target_input.low)

    def _select_breakout_ref(
        self,
        price: float,
        target_input,
        levels: DailyLevelSnapshot,
        structure_type: str,
    ) -> Optional[float]:
        candidates = self._positive_prices(
            levels.prev_high,
            levels.range_high_20d,
            self._round_price(target_input.high),
            self._round_pressure(price),
        )
        if not candidates:
            return None
        above_now = [value for value in candidates if value >= price * 1.002]
        if structure_type == "突破后回踩" and levels.prev_high is not None and levels.prev_high >= price * 0.99:
            return levels.prev_high
        breakout_ref = self._round_price(min(above_now) if above_now else max(candidates))
        if breakout_ref is not None and breakout_ref <= price:
            breakout_ref = self._round_price(max(price, breakout_ref) * 1.01)
        return breakout_ref

    def _select_retrace_confirm_ref(
        self,
        price: float,
        target_input,
        levels: DailyLevelSnapshot,
        structure_type: str,
        breakout_ref: Optional[float],
    ) -> Optional[float]:
        if structure_type in {"突破前高", "突破后回踩"} and breakout_ref is not None:
            return breakout_ref
        if structure_type == "回踩承接" and levels.prev_high is not None and price >= levels.prev_high * 0.99:
            return levels.prev_high
        if structure_type == "趋势中继":
            return self._nearest_reference(price, levels.ma5, levels.prev_high, levels.ma10)
        return self._nearest_reference(price, breakout_ref, levels.ma5, target_input.low)

    def _select_invalid_ref(
        self,
        price: float,
        target_input,
        levels: DailyLevelSnapshot,
        structure_type: str,
        retrace_confirm_ref: Optional[float],
    ) -> Optional[float]:
        if structure_type in {"突破前高", "突破后回踩"} and retrace_confirm_ref is not None:
            return self._round_price(retrace_confirm_ref * 0.992)
        return self._nearest_support_below(
            price,
            levels.prev_low,
            levels.ma10,
            levels.range_low_20d,
            target_input.low,
        )

    def _select_give_up_ref(
        self,
        price: float,
        levels: DailyLevelSnapshot,
        structure_type: str,
        breakout_ref: Optional[float],
        low_absorb_ref: Optional[float],
        market_state: str,
        daily_level: str,
        account_tight: bool,
    ) -> Optional[float]:
        anchor = breakout_ref or levels.prev_high or low_absorb_ref or self._round_price(price)
        if anchor is None:
            return None
        if daily_level in {"C", "D"} or structure_type == "冲高过热":
            heat_pct = 0.01
        elif market_state == "强市":
            heat_pct = 0.03
        elif market_state == "弱市":
            heat_pct = 0.018
        else:
            heat_pct = 0.024
        if account_tight:
            heat_pct = max(0.01, heat_pct - 0.006)
        return self._round_price(anchor * (1 + heat_pct))

    def _low_absorb_buffer_pct(
        self,
        structure_type: str,
        market_state: str,
        target_input,
        account_tight: bool,
    ) -> tuple[float, float]:
        ratio = float(target_input.vol_ratio or 0)
        if structure_type == "回踩承接":
            lower, upper = 0.003, 0.005
        elif market_state == "弱市":
            lower, upper = 0.002, 0.004
        else:
            lower, upper = 0.004, 0.006
        if ratio >= 1.8:
            upper += 0.002
        if account_tight:
            lower = max(0.002, lower - 0.001)
            upper = max(lower + 0.001, upper - 0.001)
        return lower, upper

    def _breakout_buffer_pct(
        self,
        structure_type: str,
        market_state: str,
        target_input,
        account_tight: bool,
    ) -> tuple[float, float]:
        ratio = float(target_input.vol_ratio or 0)
        if market_state == "强市":
            lower, upper = 0.003, 0.008
        elif market_state == "弱市":
            lower, upper = 0.006, 0.012
        else:
            lower, upper = 0.004, 0.01
        if structure_type == "突破前高":
            lower = max(0.003, lower)
        if ratio >= 2:
            upper += 0.002
        if account_tight:
            lower += 0.001
            upper += 0.001
        return lower, upper

    def _retrace_buffer_pct(
        self,
        structure_type: str,
        market_state: str,
        target_input,
        account_tight: bool,
    ) -> tuple[float, float]:
        ratio = float(target_input.vol_ratio or 0)
        if structure_type in {"突破前高", "突破后回踩"}:
            lower, upper = 0.004, 0.004
        else:
            lower, upper = 0.005, 0.004
        if market_state == "弱市":
            lower = max(0.003, lower - 0.001)
            upper = max(0.003, upper - 0.001)
        if ratio >= 2:
            lower += 0.001
            upper += 0.001
        if account_tight:
            upper = max(0.003, upper - 0.001)
        return lower, upper

    def _resolve_trigger_condition(
        self,
        structure_type: str,
        low_absorb_zone: str,
        breakout_zone: str,
        retrace_confirm_zone: str,
        give_up_price: str,
        raw_trigger: str,
    ) -> str:
        if structure_type in {"回踩承接", "趋势中继"}:
            summary = (
                f"优先看回踩 {low_absorb_zone} 一带是否缩量承接；若直接走强，则放量过 {breakout_zone} 并站稳再考虑。"
            )
        elif structure_type == "突破前高":
            summary = (
                f"放量过 {breakout_zone} 且站稳再看；若先突破，再回踩 {retrace_confirm_zone} 不破并重新拐头，可按确认位考虑。"
            )
        elif structure_type == "突破后回踩":
            summary = f"优先等回踩 {retrace_confirm_zone} 不破并重新转强，再考虑执行。"
        else:
            summary = f"当前位置更像过热区，高于 {give_up_price} 不追，只有回到支撑并重新承接才值得再看。"

        if raw_trigger:
            return f"{summary} 原始触发条件：{raw_trigger}"
        return summary

    def _resolve_invalid_condition(self, invalid_price: str, raw_invalid: str) -> str:
        summary = f"跌破 {invalid_price} 且无法快速收回，就视为买点失效，不再继续挂单。"
        if raw_invalid:
            return f"{summary} 原始失效条件：{raw_invalid}"
        return summary

    def _nearest_support_below(self, price: float, *values: Optional[float]) -> Optional[float]:
        candidates = sorted(
            {
                round(float(value), 2)
                for value in values
                if value is not None and float(value) > 0 and float(value) <= price * 1.01
            }
        )
        if not candidates:
            return None
        below_now = [value for value in candidates if value <= price]
        return below_now[-1] if below_now else candidates[0]

    def _nearest_reference(self, price: float, *values: Optional[float]) -> Optional[float]:
        candidates = self._positive_prices(*values)
        if not candidates:
            return None
        return self._round_price(min(candidates, key=lambda value: abs(value - price)))

    def _positive_prices(self, *values: Optional[float]) -> List[float]:
        result = []
        for value in values:
            rounded = self._round_price(value)
            if rounded is not None and rounded > 0:
                result.append(rounded)
        return sorted(set(result))

    def _round_pressure(self, price: float) -> float:
        if price <= 0:
            return price
        integer_part = int(price)
        decimal = price - integer_part
        if decimal <= 0.2:
            return float(integer_part + 0.2)
        if decimal <= 0.5:
            return float(integer_part + 0.5)
        if decimal <= 0.8:
            return float(integer_part + 0.8)
        return float(integer_part + 1)

    def _calc_ma(self, closes: List[float], window: int) -> Optional[float]:
        if len(closes) < window:
            return None
        return round(sum(closes[-window:]) / window, 2)

    def _format_support_zone(self, anchor: Optional[float], lower_pct: float, upper_pct: float) -> str:
        if anchor is None:
            return "[需确认]"
        low = round(anchor * (1 - lower_pct), 2)
        high = round(anchor * (1 + upper_pct), 2)
        return f"{low:.2f}-{high:.2f}"

    def _format_above_zone(self, anchor: Optional[float], lower_pct: float, upper_pct: float) -> str:
        if anchor is None:
            return "[需确认]"
        low = round(anchor * (1 + lower_pct), 2)
        high = round(anchor * (1 + upper_pct), 2)
        return f"{low:.2f}-{high:.2f}"

    def _format_zone(self, center: Optional[float], pct: float) -> str:
        if center is None:
            return "[需确认]"
        low = round(center * (1 - pct), 2)
        high = round(center * (1 + pct), 2)
        return f"{low:.2f}-{high:.2f}"

    def _display_price(self, value: Optional[float]) -> str:
        if value is None:
            return "[需确认]"
        return f"{value:.2f}"

    def _round_price(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None


buy_point_sop_service = BuyPointSopService()
