"""
单股卖点分析 SOP 服务
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional

from loguru import logger

from app.data.tushare_client import normalize_ts_code
from app.models.schemas import (
    AccountPosition,
    IntradayFeatureSet,
    MarketEnvTag,
    SellPointOutput,
    SellPointSopAccountContext,
    SellPointSopBasicInfo,
    SellPointSopDailyJudgement,
    SellPointSopExecution,
    SellPointSopIntradayJudgement,
    SellPointSopOrderPlan,
    SellPointSopResponse,
    SellSignalTag,
    StockOutput,
    StructureStateTag,
)
from app.services.account_adapter import AccountAdapterService
from app.services.decision_context import decision_context_service
from app.services.sell_point import sell_point_service
from app.services.stock_checkup import stock_checkup_service
from app.services.stock_filter import stock_filter_service


@dataclass
class SellDailyLevels:
    ma5: Optional[float]
    ma10: Optional[float]
    ma20: Optional[float]
    prev_high: Optional[float]
    prev_low: Optional[float]
    range_high_20d: Optional[float]
    range_low_20d: Optional[float]


@dataclass
class SellPlanAnchor:
    price: float
    target_input: object
    levels: SellDailyLevels


class SellPointSopService:
    """按卖点 SOP 输出单只持仓的结构化处理建议。"""

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
    ) -> SellPointSopResponse:
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=120,
            include_holdings=True,
            account_id=account_id,
        )
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )
        full_sell_analysis = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=getattr(context, "realtime_market_env", None) or context.market_env,
            sector_scan=context.sector_scan,
        )
        return self._analyze_from_context(
            normalize_ts_code(ts_code),
            trade_date,
            context,
            scored_stocks,
            full_sell_analysis,
        )

    async def analyze_many(
        self,
        ts_codes: List[str],
        trade_date: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, SellPointSopResponse]:
        """批量生成 SOP，复用同一次决策上下文，避免卖点页 N 次重复全量计算。"""
        normalized_codes = [normalize_ts_code(code) for code in ts_codes if code]
        if not normalized_codes:
            return {}

        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=120,
            include_holdings=True,
            account_id=account_id,
        )
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            context.stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )
        full_sell_analysis = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=getattr(context, "realtime_market_env", None) or context.market_env,
            sector_scan=context.sector_scan,
        )

        results: Dict[str, SellPointSopResponse] = {}
        for code in normalized_codes:
            try:
                results[code] = self._analyze_from_context(
                    code,
                    trade_date,
                    context,
                    scored_stocks,
                    full_sell_analysis,
                )
            except Exception as exc:
                logger.warning(f"批量卖点 SOP 生成失败 ts_code={code}: {exc}")
        return results

    def _analyze_from_context(
        self,
        normalized_code: str,
        trade_date: str,
        context,
        scored_stocks: List[StockOutput],
        full_sell_analysis,
    ) -> SellPointSopResponse:
        stable_market_env = context.market_env
        realtime_market_env = getattr(context, "realtime_market_env", None) or stable_market_env
        target_holding = self._find_holding(context.holdings, normalized_code)
        if target_holding is None:
            raise ValueError("目标股票不在当前持仓中")

        try:
            target_input = decision_context_service.build_single_stock_input(
                normalized_code,
                trade_date,
                candidate_source_tag="卖点分析",
            )
        except Exception:
            try:
                target_input = next(
                    stock for stock in context.stocks if normalize_ts_code(stock.ts_code) == normalized_code
                )
            except StopIteration:
                target_input = self._build_fallback_target_input(target_holding)
            target_input.quote_time = target_holding.quote_time or target_input.quote_time
            target_input.data_source = target_holding.data_source or target_input.data_source
            if getattr(target_holding, "market_price", None):
                target_input.close = target_holding.market_price

        target_scored = self._find_scored_stock(scored_stocks, normalized_code)
        target_sell_point = self._find_sell_point(full_sell_analysis, normalized_code)
        if target_sell_point is None:
            raise ValueError("未找到目标持仓的卖点结果")

        history_rows, resolved_trade_date = self._load_history_payload(
            normalized_code,
            trade_date,
        )
        levels = self._build_daily_levels(target_input, history_rows)
        account_context = self._build_account_context(
            context.account,
            target_holding,
            target_sell_point,
            full_sell_analysis,
        )
        daily_judgement = self._build_daily_judgement(
            target_input,
            target_holding,
            target_scored,
            target_sell_point,
            stable_market_env,
            levels,
        )
        intraday_judgement = self._build_intraday_judgement(
            target_input,
            target_holding,
            target_sell_point,
            daily_judgement.sell_point_level,
            levels,
        )
        order_plan = self._build_order_plan(
            target_input,
            target_holding,
            target_scored,
            target_sell_point,
            account_context,
            daily_judgement,
            intraday_judgement,
            levels,
            history_rows,
        )
        execution = self._build_execution(
            target_holding,
            target_sell_point,
            daily_judgement,
            intraday_judgement,
            order_plan,
        )

        return SellPointSopResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date or context.resolved_stock_trade_date,
            stock_found_in_holdings=True,
            basic_info=SellPointSopBasicInfo(
                ts_code=target_holding.ts_code,
                stock_name=target_holding.stock_name,
                market_env_tag=realtime_market_env.market_env_tag.value,
                stable_market_env_tag=stable_market_env.market_env_tag.value,
                realtime_market_env_tag=realtime_market_env.market_env_tag.value,
                sell_signal_tag=target_sell_point.sell_signal_tag.value,
                sell_point_type=target_sell_point.sell_point_type.value,
                quote_time=target_input.quote_time or target_holding.quote_time,
                data_source=target_input.data_source or target_holding.data_source,
            ),
            account_context=account_context,
            daily_judgement=daily_judgement,
            intraday_judgement=intraday_judgement,
            order_plan=order_plan,
            execution=execution,
        )

    def _find_holding(self, holdings: List[AccountPosition], ts_code: str) -> Optional[AccountPosition]:
        for holding in holdings:
            if normalize_ts_code(holding.ts_code) == ts_code:
                return holding
        return None

    def _find_scored_stock(self, stocks: List[StockOutput], ts_code: str) -> Optional[StockOutput]:
        for stock in stocks:
            if normalize_ts_code(stock.ts_code) == ts_code:
                return stock
        return None

    def _find_sell_point(self, response, ts_code: str) -> Optional[SellPointOutput]:
        for group in (response.sell_positions, response.reduce_positions, response.hold_positions):
            for point in group:
                if normalize_ts_code(point.ts_code) == ts_code:
                    return point
        return None

    def _build_fallback_target_input(self, holding: AccountPosition):
        """当单股行情输入不可用时，退化为基于持仓快照的最小分析输入。"""
        price = float(getattr(holding, "market_price", None) or getattr(holding, "cost_price", None) or 0)
        pre_close = float(getattr(holding, "cost_price", None) or price or 0)
        change_pct = float(getattr(holding, "pnl_pct", None) or 0)
        return SimpleNamespace(
            ts_code=holding.ts_code,
            stock_name=holding.stock_name,
            sector_name="未知",
            close=price,
            open=price,
            high=price,
            low=price,
            pre_close=pre_close,
            change_pct=change_pct,
            turnover_rate=0.0,
            amount=0.0,
            avg_price=price,
            intraday_volume_ratio=None,
            vol_ratio=0.0,
            quote_time=getattr(holding, "quote_time", None),
            data_source=getattr(holding, "data_source", None) or "holding_snapshot",
        )

    def _build_daily_levels(self, target_input, history_rows: List[Dict]) -> SellDailyLevels:
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
        return SellDailyLevels(
            ma5=self._calc_ma(closes, 5),
            ma10=self._calc_ma(closes, 10),
            ma20=self._calc_ma(closes, 20),
            prev_high=self._round_price(prev_row.get("high")) if prev_row else None,
            prev_low=self._round_price(prev_row.get("low")) if prev_row else None,
            range_high_20d=self._round_price(max(highs_20)) if highs_20 else self._round_price(target_input.high),
            range_low_20d=self._round_price(min(lows_20)) if lows_20 else self._round_price(target_input.low),
        )

    def _build_account_context(
        self,
        account,
        holding: AccountPosition,
        sell_point: SellPointOutput,
        full_sell_analysis,
    ) -> SellPointSopAccountContext:
        position_status = self._position_status(account.total_position_ratio, account.holding_count)
        pnl_status = self._pnl_status(holding.pnl_pct)
        role = self._role_status(holding)
        priority = self._priority_status(holding, sell_point, full_sell_analysis)
        return SellPointSopAccountContext(
            position_status=position_status,
            pnl_status=pnl_status,
            role=role,
            priority=priority,
            context_summary=f"{position_status}{pnl_status}{role}",
        )

    def _build_daily_judgement(
        self,
        target_input,
        holding: AccountPosition,
        target_scored: Optional[StockOutput],
        sell_point: SellPointOutput,
        market_env,
        levels: SellDailyLevels,
    ) -> SellPointSopDailyJudgement:
        price = float(target_input.close or holding.market_price or 0)
        change_pct = float(target_input.change_pct or 0)
        below_prev_low = levels.prev_low is not None and price < levels.prev_low
        below_ma5 = levels.ma5 is not None and price < levels.ma5
        below_ma10 = levels.ma10 is not None and price < levels.ma10
        high_zone = levels.range_high_20d is not None and price >= levels.range_high_20d * 0.94
        close_quality = self._close_quality(target_input)
        high_volume_fade = high_zone and float(target_input.vol_ratio or 0) >= 1.5 and close_quality < 0.35

        stage = self._resolve_daily_stage(target_scored, change_pct, price, levels, high_zone)
        signals = []
        if below_prev_low:
            signals.append("跌破前一日低点")
        if below_ma5:
            signals.append("跌破5日线")
        if high_volume_fade:
            signals.append("高位放量冲高回落")
        if not signals:
            signals.append("日线结构暂未明显破坏")

        if sell_point.sell_signal_tag == SellSignalTag.SELL:
            level = "D"
        elif sell_point.sell_signal_tag == SellSignalTag.REDUCE or stage == "高潮":
            level = "C"
        elif sell_point.sell_signal_tag in {SellSignalTag.HOLD, SellSignalTag.OBSERVE} or stage == "松动":
            level = "B"
        else:
            level = "A"

        reason_bits = [
            f"当前阶段偏{stage}",
            "已经跌破前一日低点，日内承接转弱" if below_prev_low else "尚未跌破前一日低点",
            "已经跌破5日线，短线强度下降" if below_ma5 else "仍在5日线附近，暂未完全走坏",
            "高位放量回落，先防利润回吐" if high_volume_fade else "暂未看到典型高位派发",
        ]
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            reason_bits.append("市场偏防守，卖点容错要求更高")
        if below_ma10:
            reason_bits.append("已经触及10日线下方，结构保护优先")

        return SellPointSopDailyJudgement(
            current_stage=stage,
            sell_signal="，".join(signals),
            sell_point_level=level,
            reason="；".join(reason_bits),
        )

    def _build_intraday_judgement(
        self,
        target_input,
        holding: AccountPosition,
        sell_point: SellPointOutput,
        daily_level: str,
        levels: SellDailyLevels,
    ) -> SellPointSopIntradayJudgement:
        realtime = str(target_input.data_source or "").startswith("realtime_")
        price = float(target_input.close or holding.market_price or 0)
        features = self._build_intraday_features(target_input, levels)
        structure = self._resolve_intraday_structure(features)
        volume_quality = self._resolve_intraday_volume_quality(features.volume_ratio, structure)

        if not holding.can_sell_today:
            return SellPointSopIntradayJudgement(
                price_vs_avg_line=self._resolve_price_vs_avg_line(target_input, holding.market_price),
                intraday_structure=structure,
                volume_quality=volume_quality,
                conclusion="拿",
                note="当前持仓受 T+1 约束，今天只能观察，等下个可卖时点处理。",
            )

        if not realtime:
            conclusion = "拿"
            if daily_level == "D":
                conclusion = "清"
            elif daily_level == "C":
                conclusion = "减"
            elif sell_point.sell_signal_tag == SellSignalTag.REDUCE:
                conclusion = "减"
            return SellPointSopIntradayJudgement(
                price_vs_avg_line="均价线关系 [需确认]",
                intraday_structure=f"{structure} [需确认]",
                volume_quality=volume_quality,
                conclusion=conclusion,
                note="当前不是实时分时口径，具体卖法要结合盘中承接和回流再确认。",
            )

        if structure == "跌破关键低点":
            conclusion = "清"
        elif structure in {"冲高回落偏弱", "弱反抽"}:
            conclusion = "减" if sell_point.sell_signal_tag != SellSignalTag.SELL else "清"
        elif structure in {"冲高回落但承接尚可", "均价线附近拉扯"}:
            conclusion = "拿" if daily_level in {"A", "B"} else "减"
        elif structure == "强势横住":
            conclusion = "拿"
        else:
            conclusion = "减" if sell_point.sell_signal_tag == SellSignalTag.REDUCE else "拿"

        return SellPointSopIntradayJudgement(
            price_vs_avg_line=self._resolve_price_vs_avg_line(target_input, price),
            intraday_structure=structure,
            volume_quality=volume_quality,
            conclusion=conclusion,
            note="已结合实时分时结构与均价线关系，具体执行仍建议配合盘口观察。",
        )

    def _build_order_plan(
        self,
        target_input,
        holding: AccountPosition,
        target_scored: Optional[StockOutput],
        sell_point: SellPointOutput,
        account_context: SellPointSopAccountContext,
        daily_judgement: SellPointSopDailyJudgement,
        intraday_judgement: SellPointSopIntradayJudgement,
        levels: SellDailyLevels,
        history_rows: List[Dict],
    ) -> SellPointSopOrderPlan:
        live_holding_price = self._round_price(getattr(holding, "market_price", None))
        live_price = float(live_holding_price or target_input.close or 0)
        plan_anchor = self._build_plan_anchor(target_input, levels, history_rows)
        sell_style = self._resolve_sell_style(
            target_scored,
            account_context,
            daily_judgement,
            intraday_judgement,
            sell_point,
            holding,
        )
        proactive_ref = self._select_proactive_ref(
            live_price,
            target_input,
            levels,
            sell_style,
            holding,
        )
        rebound_ref = self._select_rebound_ref(
            plan_anchor.price,
            plan_anchor.target_input,
            plan_anchor.levels,
            sell_style,
            holding,
        )
        stop_ref = self._select_stop_ref(
            plan_anchor.price,
            plan_anchor.target_input,
            plan_anchor.levels,
            sell_style,
            daily_judgement.sell_point_level,
        )
        priority_exit_ref = self._select_priority_exit_ref(
            live_price,
            target_input,
            sell_style,
            intraday_judgement.conclusion,
        )
        observe_ref = self._select_observe_ref(
            plan_anchor.price,
            plan_anchor.target_input,
            plan_anchor.levels,
            sell_style,
            intraday_judgement.conclusion,
        )
        allow_proactive_take_profit = proactive_ref is not None and (
            sell_style == "strong_profit"
            or (
                holding.pnl_pct > 0
                and intraday_judgement.conclusion == "减"
                and sell_style != "weak_exit"
            )
        )

        priority_exit_zone = (
            self._format_zone(priority_exit_ref, self._priority_exit_buffer_pct(target_input))
            if priority_exit_ref is not None and intraday_judgement.conclusion == "清"
            else "[当前不适用]"
        )
        proactive_zone = (
            self._format_zone(proactive_ref, self._proactive_buffer_pct(sell_style, target_input))
            if allow_proactive_take_profit
            else "[当前不适用]"
        )
        rebound_zone = (
            self._format_zone(rebound_ref, self._rebound_buffer_pct(sell_style, plan_anchor.target_input))
            if rebound_ref is not None and sell_style in {"observation_exit", "weak_exit"}
            else "[当前不适用]"
        )
        stop_price = self._display_price(stop_ref)
        observe_price = (
            self._display_price(observe_ref)
            if observe_ref is not None and (intraday_judgement.conclusion == "拿" or sell_style == "strong_profit")
            else "[当前不适用]"
        )

        priority_exit_condition = "当前不是优先现价退出阶段。"
        take_profit_condition = "当前以防守或退出为主，不设置主动兑现位。"
        rebound_condition = "当前不以弱反抽退出为主。"
        hold_condition = "当前不是继续观察阶段。"

        if intraday_judgement.conclusion == "清" and priority_exit_ref is not None:
            priority_exit_condition = (
                f"能直接在 {priority_exit_zone} 一带处理，就优先直接退出；不要把最后失效线当成第一卖点。"
            )
        if sell_style == "strong_profit":
            take_profit_condition = (
                f"冲到 {proactive_zone} 一带，若量能放缓或冲高后不能继续站稳，先兑现 1/3~1/2。"
            )
            hold_condition = (
                f"守住 {self._display_price(observe_ref)} 且没有明显派发，可以继续拿剩余仓位观察。"
                if observe_ref is not None
                else "继续观察位 [需确认]"
            )
        elif allow_proactive_take_profit:
            take_profit_condition = (
                f"当前位置已有利润垫，冲到 {proactive_zone} 一带若继续放缓或站不稳，可先兑现 1/3 锁利润。"
            )
        elif sell_style in {"observation_exit", "weak_exit"}:
            rebound_condition = (
                f"弱反抽到 {rebound_zone} 一带但站不稳，优先借反抽减仓或退出。"
                if rebound_ref is not None
                else "反抽卖出位 [需确认]"
            )
            hold_condition = (
                f"只有重新站回 {self._display_price(observe_ref)} 上方并稳住，才值得继续看。"
                if observe_ref is not None and intraday_judgement.conclusion != "清"
                else "当前不建议继续以观察为主。"
            )

        return SellPointSopOrderPlan(
            priority_exit_price=priority_exit_zone,
            proactive_take_profit_price=proactive_zone,
            rebound_sell_price=rebound_zone,
            break_stop_price=stop_price,
            observe_level=observe_price,
            priority_exit_condition=priority_exit_condition,
            take_profit_condition=take_profit_condition,
            rebound_condition=rebound_condition,
            stop_condition=f"跌破 {stop_price} 且 3-5 分钟无法收回，就按结构失效处理。",
            hold_condition=hold_condition,
        )

    def _build_plan_anchor(
        self,
        target_input,
        levels: SellDailyLevels,
        history_rows: List[Dict],
    ) -> SellPlanAnchor:
        """盘中计划位默认锚定到上一已完成交易日，避免随实时价漂移。"""
        fallback_price = self._round_price(getattr(target_input, "close", None)) or 0.0
        if not self._is_realtime_quote(target_input) or not history_rows:
            return SellPlanAnchor(
                price=float(fallback_price),
                target_input=target_input,
                levels=levels,
            )

        anchor_row = history_rows[-1] or {}
        anchor_close = self._round_price(anchor_row.get("close")) or fallback_price
        anchor_open = self._round_price(anchor_row.get("open")) or anchor_close
        anchor_high = self._round_price(anchor_row.get("high")) or anchor_close
        anchor_low = self._round_price(anchor_row.get("low")) or anchor_close
        anchor_pre_close = (
            self._round_price(history_rows[-2].get("close"))
            if len(history_rows) >= 2
            else self._round_price(getattr(target_input, "pre_close", None))
        ) or anchor_close
        anchor_input = SimpleNamespace(
            ts_code=getattr(target_input, "ts_code", None),
            stock_name=getattr(target_input, "stock_name", None),
            sector_name=getattr(target_input, "sector_name", None),
            close=anchor_close,
            open=anchor_open,
            high=anchor_high,
            low=anchor_low,
            pre_close=anchor_pre_close,
            change_pct=0.0,
            turnover_rate=getattr(target_input, "turnover_rate", 0.0),
            amount=0.0,
            avg_price=anchor_close,
            intraday_volume_ratio=None,
            vol_ratio=0.0,
            quote_time=None,
            data_source="previous_daily_plan_anchor",
        )
        anchor_levels = SellDailyLevels(
            ma5=levels.ma5,
            ma10=levels.ma10,
            ma20=levels.ma20,
            prev_high=anchor_high,
            prev_low=anchor_low,
            range_high_20d=levels.range_high_20d,
            range_low_20d=levels.range_low_20d,
        )
        return SellPlanAnchor(
            price=float(anchor_close),
            target_input=anchor_input,
            levels=anchor_levels,
        )

    def _build_execution(
        self,
        holding: AccountPosition,
        sell_point: SellPointOutput,
        daily_judgement: SellPointSopDailyJudgement,
        intraday_judgement: SellPointSopIntradayJudgement,
        order_plan: SellPointSopOrderPlan,
    ) -> SellPointSopExecution:
        if not holding.can_sell_today:
            return SellPointSopExecution(
                action="拿",
                partial_plan="今天不分批，受 T+1 限制只能观察。",
                key_level=order_plan.observe_level,
                reason="今日不能卖，重点盯住观察位，等下个可卖时点按计划执行。",
            )

        if intraday_judgement.conclusion == "清":
            return SellPointSopExecution(
                action="清",
                partial_plan="不分批或只给一次弱反抽机会，核心是退出效率。",
                key_level=(
                    order_plan.priority_exit_price
                    if order_plan.priority_exit_price != "[当前不适用]"
                    else order_plan.break_stop_price
                ),
                reason="当前更像结构失效或分时明显转弱，优先退出，避免后续更被动。",
            )

        if intraday_judgement.conclusion == "减":
            key_level = (
                order_plan.proactive_take_profit_price
                if order_plan.proactive_take_profit_price != "[当前不适用]"
                else order_plan.rebound_sell_price
            )
            return SellPointSopExecution(
                action="减",
                partial_plan="分批处理，先兑现一部分，再看反抽强度或关键位是否失守。",
                key_level=key_level,
                reason="当前更像强度下降或高位分歧，先减仓防守，比死扛或一把清掉都更稳。",
            )

        return SellPointSopExecution(
            action="拿",
            partial_plan="暂不分批，先观察关键位是否继续守住。",
            key_level=order_plan.observe_level,
            reason="日线和分时都还没到必须处理的程度，先看承接是否延续。",
        )

    def _position_status(self, ratio: float, holding_count: int) -> str:
        if ratio >= AccountAdapterService.POSITION_HIGH or holding_count >= AccountAdapterService.HOLDING_COUNT_HIGH:
            return "重仓"
        if ratio >= AccountAdapterService.POSITION_MEDIUM or holding_count >= AccountAdapterService.HOLDING_COUNT_MEDIUM:
            return "中仓"
        return "轻仓"

    def _pnl_status(self, pnl_pct: float) -> str:
        if pnl_pct <= -8:
            return "深亏"
        if pnl_pct < 0:
            return "小亏"
        if pnl_pct >= sell_point_service.REDUCE_PCT:
            return "厚利"
        return "微利"

    def _role_status(self, holding: AccountPosition) -> str:
        reason = str(holding.holding_reason or "")
        if any(tag in reason for tag in ["待处理", "失效", "证伪", "不成立"]):
            return "待处理仓"
        if any(tag in reason for tag in ["观察", "试错", "测试"]):
            return "观察仓"
        if any(tag in reason for tag in ["修复", "反抽"]):
            return "修复仓"
        return "进攻仓" if holding.pnl_pct >= 0 else "修复仓"

    def _priority_status(self, holding: AccountPosition, sell_point: SellPointOutput, full_sell_analysis) -> str:
        ordered = [
            *full_sell_analysis.sell_positions,
            *full_sell_analysis.reduce_positions,
            *full_sell_analysis.hold_positions,
        ]
        rank = next(
            (idx + 1 for idx, point in enumerate(ordered) if normalize_ts_code(point.ts_code) == normalize_ts_code(holding.ts_code)),
            None,
        )
        if rank is not None and rank <= 2:
            return f"高，当前应优先处理（序位 {rank}）"
        if sell_point.sell_signal_tag in {SellSignalTag.SELL, SellSignalTag.REDUCE}:
            return "中，需要尽快处理"
        return "低，当前不是第一优先"

    def _resolve_daily_stage(
        self,
        target_scored: Optional[StockOutput],
        change_pct: float,
        price: float,
        levels: SellDailyLevels,
        high_zone: bool,
    ) -> str:
        state = getattr(getattr(target_scored, "structure_state_tag", None), "value", "")
        if state == StructureStateTag.START.value:
            return "强趋势"
        if state == StructureStateTag.REPAIR.value:
            return "中继"
        if state == StructureStateTag.DIVERGENCE.value:
            return "松动"
        if state == StructureStateTag.LATE_STAGE.value:
            return "高潮"
        if change_pct < -2 or (levels.ma10 is not None and price < levels.ma10):
            return "退潮"
        if high_zone:
            return "高潮"
        return "中继"

    def _build_intraday_features(self, target_input, levels: SellDailyLevels) -> IntradayFeatureSet:
        high = float(target_input.high or 0)
        low = float(target_input.low or 0)
        close = float(target_input.close or 0)
        open_price = float(target_input.open or 0)
        change_pct = float(target_input.change_pct or 0)
        close_quality = self._close_quality(target_input)
        avg_price = self._extract_avg_price(target_input)
        above_avg = avg_price is not None and close >= avg_price
        pullback_ratio = 0.0
        if high > low:
            pullback_ratio = max(0.0, min(1.0, (high - close) / (high - low)))
        rebound_strength = 0.0
        if close > 0 and low > 0 and close >= low:
            rebound_strength = max(0.0, min(1.0, (close - low) / max(close, low)))
        reclaims_avg_line = avg_price is not None and open_price > 0 and open_price < avg_price <= close
        afternoon_rebound = bool(change_pct >= 0 and rebound_strength >= 0.015 and close_quality >= 0.45)
        volume_ratio = float(getattr(target_input, "intraday_volume_ratio", None) or getattr(target_input, "vol_ratio", None) or 0)
        return IntradayFeatureSet(
            above_avg_line=above_avg if avg_price is not None else None,
            close_quality=close_quality,
            pullback_ratio=pullback_ratio,
            rebound_strength=rebound_strength,
            breaks_prev_low=bool(levels.prev_low is not None and close < levels.prev_low),
            reclaims_avg_line=bool(reclaims_avg_line),
            afternoon_rebound=afternoon_rebound,
            volume_ratio=volume_ratio,
        )

    def _resolve_intraday_structure(self, features: IntradayFeatureSet) -> str:
        if features.above_avg_line is None:
            return "分时结构 [需确认]"
        if features.breaks_prev_low:
            return "跌破关键低点"
        if features.above_avg_line and features.close_quality >= 0.72:
            return "强势横住"
        if (
            features.pullback_ratio >= 0.35
            and features.pullback_ratio < 0.6
            and features.close_quality >= 0.4
            and features.above_avg_line
        ):
            return "冲高回落但承接尚可"
        if features.close_quality < 0.35 and not features.above_avg_line:
            return "冲高回落偏弱"
        if features.reclaims_avg_line or (features.above_avg_line is not None and abs(features.pullback_ratio - 0.5) > 0.45 and 0.45 <= features.close_quality <= 0.6):
            return "均价线附近拉扯"
        if features.rebound_strength <= 0.015 and features.close_quality < 0.5:
            return "弱反抽"
        return "震荡待定"

    def _resolve_intraday_volume_quality(self, volume_ratio: float, structure: str) -> str:
        weak_structures = {"跌破关键低点", "冲高回落偏弱", "弱反抽"}
        if volume_ratio >= 1.5 and structure in weak_structures:
            return f"实时放量回落 = 派发（相对放量 {volume_ratio:.1f}）"
        if volume_ratio >= 1.5:
            return f"实时放量稳住 = 承接（相对放量 {volume_ratio:.1f}）"
        if volume_ratio > 0:
            return f"实时缩量横盘 = 观望（相对放量 {volume_ratio:.1f}）"
        return "量能 [需确认]"

    def _resolve_price_vs_avg_line(self, target_input, fallback_price: float) -> str:
        price = self._round_price(getattr(target_input, "close", None) or fallback_price)
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

    def _is_realtime_quote(self, target_input) -> bool:
        return str(getattr(target_input, "data_source", "") or "").startswith("realtime_")

    def _resolve_sell_style(
        self,
        target_scored: Optional[StockOutput],
        account_context: SellPointSopAccountContext,
        daily_judgement: SellPointSopDailyJudgement,
        intraday_judgement: SellPointSopIntradayJudgement,
        sell_point: SellPointOutput,
        holding: AccountPosition,
    ) -> str:
        role = account_context.role
        pnl_status = account_context.pnl_status
        strength_tag = getattr(getattr(target_scored, "stock_strength_tag", None), "value", "")
        core_tag = getattr(getattr(target_scored, "stock_core_tag", None), "value", "")

        if (
            role == "待处理仓"
            or pnl_status == "深亏"
            or sell_point.sell_signal_tag == SellSignalTag.SELL
            or daily_judgement.sell_point_level == "D"
            or intraday_judgement.conclusion == "清"
        ):
            return "weak_exit"

        if (
            pnl_status in {"厚利", "微利"}
            and role == "进攻仓"
            and strength_tag == "强"
            and core_tag == "核心"
            and daily_judgement.current_stage in {"强趋势", "中继", "高潮"}
        ):
            return "strong_profit"

        return "observation_exit"

    def _select_proactive_ref(
        self,
        price: float,
        target_input,
        levels: SellDailyLevels,
        sell_style: str,
        holding: AccountPosition,
    ) -> Optional[float]:
        if sell_style == "weak_exit" or holding.pnl_pct <= 0:
            return None
        candidates = self._positive_prices(
            target_input.high,
            levels.prev_high,
            levels.range_high_20d,
            self._round_price(self._round_pressure(price)),
        )
        if not candidates:
            return None
        above_now = [value for value in candidates if value >= price * 0.995]
        return self._round_price(min(above_now) if above_now else max(candidates))

    def _select_rebound_ref(
        self,
        price: float,
        target_input,
        levels: SellDailyLevels,
        sell_style: str,
        holding: AccountPosition,
    ) -> Optional[float]:
        if sell_style not in {"observation_exit", "weak_exit"}:
            return None
        candidates: List[float] = []
        if sell_style == "weak_exit":
            candidates.extend(self._positive_prices(target_input.open, target_input.high))
        if levels.prev_low is not None and price < levels.prev_low:
            candidates.append(levels.prev_low)
        if levels.ma5 is not None and price < levels.ma5:
            candidates.append(levels.ma5)
        if levels.ma10 is not None and price < levels.ma10:
            candidates.append(levels.ma10)
        if sell_style == "observation_exit" and holding.cost_price and holding.pnl_pct < 0:
            candidates.append(holding.cost_price)
        if not candidates:
            candidates = self._positive_prices(levels.ma5, levels.prev_low, levels.ma10)
        if not candidates:
            return None
        above_now = [value for value in candidates if value >= price]
        return self._round_price(min(above_now) if above_now else max(candidates))

    def _select_stop_ref(
        self,
        price: float,
        target_input,
        levels: SellDailyLevels,
        sell_style: str,
        daily_level: str,
    ) -> Optional[float]:
        if sell_style == "strong_profit":
            anchor = self._nearest_support_below(price, levels.ma10, levels.prev_low, levels.ma20, levels.range_low_20d)
        elif sell_style == "observation_exit":
            anchor = self._nearest_support_below(price, levels.prev_low, levels.ma5, levels.ma10, target_input.low, levels.range_low_20d)
        else:
            anchor = self._nearest_support_below(price, target_input.low, levels.prev_low, levels.range_low_20d, levels.ma10)
        if anchor is None:
            return None
        buffer = self._stop_buffer_pct(sell_style, daily_level, target_input)
        return self._round_price(anchor * (1 - buffer))

    def _select_observe_ref(
        self,
        price: float,
        target_input,
        levels: SellDailyLevels,
        sell_style: str,
        intraday_conclusion: str,
    ) -> Optional[float]:
        if intraday_conclusion == "清":
            return None
        if sell_style == "strong_profit":
            return self._nearest_reference(price, levels.ma5, levels.prev_low, levels.ma10)
        if sell_style == "observation_exit":
            return self._nearest_reference(price, levels.prev_low, levels.ma5, target_input.low)
        return self._nearest_reference(price, levels.prev_low, target_input.low)

    def _select_priority_exit_ref(
        self,
        price: float,
        target_input,
        sell_style: str,
        intraday_conclusion: str,
    ) -> Optional[float]:
        if intraday_conclusion != "清" or sell_style != "weak_exit":
            return None
        candidates = self._positive_prices(
            price,
            target_input.close,
            target_input.open if float(getattr(target_input, "open", 0) or 0) <= price * 1.02 else None,
        )
        if not candidates:
            return None
        return self._round_price(max(candidates))

    def _proactive_buffer_pct(self, sell_style: str, target_input) -> float:
        if sell_style != "strong_profit":
            return 0.003
        ratio = float(target_input.vol_ratio or 0)
        if ratio >= 2:
            return 0.008
        if ratio >= 1.3:
            return 0.005
        return 0.003

    def _priority_exit_buffer_pct(self, target_input) -> float:
        ratio = float(getattr(target_input, "intraday_volume_ratio", None) or getattr(target_input, "vol_ratio", None) or 0)
        if ratio >= 1.5:
            return 0.004
        return 0.003

    def _rebound_buffer_pct(self, sell_style: str, target_input) -> float:
        if sell_style == "weak_exit":
            return 0.008
        ratio = float(target_input.vol_ratio or 0)
        if ratio >= 1.5:
            return 0.006
        return 0.004

    def _stop_buffer_pct(self, sell_style: str, daily_level: str, target_input) -> float:
        ratio = float(target_input.vol_ratio or 0)
        if sell_style == "weak_exit" or daily_level == "D":
            return 0.005 if ratio < 1.5 else 0.008
        if sell_style == "strong_profit":
            return 0.012 if ratio >= 1.5 else 0.01
        return 0.008 if ratio >= 1.5 else 0.006

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

    def _close_quality(self, target_input) -> float:
        high = float(target_input.high or 0)
        low = float(target_input.low or 0)
        close = float(target_input.close or 0)
        if high <= low:
            return 0.5
        return max(0.0, min(1.0, (close - low) / (high - low)))

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


sell_point_sop_service = SellPointSopService()
