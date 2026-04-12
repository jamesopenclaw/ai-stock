"""
个股全面体检服务
"""
# flake8: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional

import pandas as pd

from app.services.market_data_gateway import market_data_gateway
from app.models.schemas import (
    StockCheckupBasicInfo,
    StockCheckupBuyView,
    StockCheckupDailyStructure,
    StockCheckupDirectionPosition,
    StockCheckupFinalConclusion,
    StockCheckupFundQuality,
    StockCheckupIntradayStrength,
    StockCheckupKeyLevels,
    StockCheckupMarketContext,
    StockCheckupPeerComparison,
    StockCheckupPeerItem,
    StockCheckupResponse,
    StockCheckupRuleSnapshot,
    StockCheckupSellView,
    StockCheckupStrategy,
    StockCheckupTarget,
    StockCheckupValuationProfile,
    StockOutput,
    StockPoolTag,
    StructureStateTag,
)
from app.services.buy_point import buy_point_service
from app.services.decision_context import decision_context_service
from app.services.llm_explainer import llm_explainer_service
from app.services.sell_point import sell_point_service
from app.services.stock_filter import stock_filter_service


class StockCheckupService:
    """聚合规则结果与 LLM 输出的单股体检服务。"""

    SECTION_TITLES = {
        "basic_info": "1）基本信息",
        "market_context": "2）市场环境",
        "direction_position": "3）方向地位",
        "daily_structure": "4）日线结构",
        "intraday_strength": "5）短线强度",
        "fund_quality": "6）资金质量",
        "peer_comparison": "7）同类对比",
        "valuation_profile": "8）估值与属性",
        "key_levels": "9）关键位",
        "strategy": "10）策略结论",
        "final_conclusion": "11）一句话结论",
    }

    async def checkup(
        self,
        ts_code: str,
        trade_date: str,
        checkup_target: StockCheckupTarget = StockCheckupTarget.OBSERVE,
        *,
        account_id: Optional[str] = None,
        force_llm_refresh: bool = False,
    ) -> StockCheckupResponse:
        normalized_code = market_data_gateway.normalize_ts_code(ts_code)
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=120,
            include_holdings=True,
            account_id=account_id,
        )
        stocks, found_in_candidates = decision_context_service.merge_single_stock_into_context(
            trade_date,
            context.stocks,
            normalized_code,
        )
        target_input = self._resolve_target_input(stocks, normalized_code)
        if target_input is None:
            raise ValueError(f"未找到目标股票: {normalized_code}")
        scored_stocks = stock_filter_service.filter_with_context(
            trade_date,
            stocks,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
            account=context.account,
            holdings=context.holdings_list,
        )
        target_scored = self._resolve_target_scored_stock(
            normalized_code,
            scored_stocks,
            target_input,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
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
        sell_analysis = sell_point_service.analyze(
            trade_date,
            context.holdings,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
        )
        stock_pools = stock_filter_service.attach_sell_analysis(stock_pools, sell_analysis)
        target_pool_stock, pool_tag = self._resolve_target_pool_stock(stock_pools, normalized_code)
        if target_pool_stock:
            target_scored = target_pool_stock
        else:
            target_scored.stock_pool_tag = StockPoolTag.NOT_IN_POOL

        buy_view = None
        if pool_tag != StockPoolTag.HOLDING_PROCESS:
            target_scored.stock_pool_tag = pool_tag
            buy_point = buy_point_service._analyze_stock_buy_point(
                target_scored,
                context.market_env,
                context.account,
            )
            buy_view = StockCheckupBuyView(
                buy_signal_tag=buy_point.buy_signal_tag.value,
                buy_point_type=buy_point.buy_point_type.value,
                buy_trigger_cond=buy_point.buy_trigger_cond,
                buy_confirm_cond=buy_point.buy_confirm_cond,
                buy_invalid_cond=buy_point.buy_invalid_cond,
                buy_comment=buy_point.buy_comment,
            )

        sell_view = None
        target_holding = self._resolve_target_holding(context.holdings, normalized_code)
        if target_holding:
            sell_point = self._resolve_target_sell_point(sell_analysis, normalized_code)
            if sell_point:
                sell_view = StockCheckupSellView(
                    sell_signal_tag=sell_point.sell_signal_tag.value,
                    sell_point_type=sell_point.sell_point_type.value,
                    sell_trigger_cond=sell_point.sell_trigger_cond,
                    sell_reason=sell_point.sell_reason,
                    reduce_reason_code=sell_point.reduce_reason_code,
                    sell_comment=sell_point.sell_comment,
                    can_sell_today=sell_point.can_sell_today,
                )

        history_rows, valuation_row, resolved_trade_date = self._load_history_payload(
            normalized_code,
            trade_date,
        )
        moneyflow_rows = self._load_moneyflow_rows(
            normalized_code,
            resolved_trade_date or trade_date,
        )
        rule_snapshot = self._build_rule_snapshot(
            trade_date=trade_date,
            target_input=target_input,
            target_stock=target_scored,
            context=context,
            scored_stocks=scored_stocks,
            history_rows=history_rows,
            valuation_row=valuation_row,
            moneyflow_rows=moneyflow_rows,
            checkup_target=checkup_target,
            buy_view=buy_view,
            sell_view=sell_view,
        )
        llm_report, llm_status = await llm_explainer_service.explain_stock_checkup_with_status(
            rule_snapshot,
            trade_date=trade_date,
            checkup_target=checkup_target,
            account_id=account_id,
            force_refresh=force_llm_refresh,
        )
        return StockCheckupResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date or context.resolved_stock_trade_date,
            checkup_target=checkup_target,
            stock_found_in_candidates=found_in_candidates,
            rule_snapshot=rule_snapshot,
            llm_report=llm_report,
            llm_status=llm_status,
        )

    def _resolve_target_input(self, stocks, ts_code: str):
        for stock in stocks:
            if market_data_gateway.normalize_ts_code(stock.ts_code) == ts_code:
                return stock
        return None

    def _resolve_target_scored_stock(
        self,
        ts_code: str,
        scored_stocks: List[StockOutput],
        target_input,
        *,
        market_env,
        sector_scan,
    ) -> StockOutput:
        for stock in scored_stocks:
            if market_data_gateway.normalize_ts_code(stock.ts_code) == ts_code:
                return stock

        sector_map = stock_filter_service._build_sector_map(sector_scan) if sector_scan else {}
        fallback = stock_filter_service._score_stock(target_input, market_env, sector_map)
        fallback.stock_pool_tag = StockPoolTag.NOT_IN_POOL
        return fallback

    def _resolve_target_pool_stock(
        self,
        stock_pools,
        ts_code: str,
    ) -> tuple[Optional[StockOutput], StockPoolTag]:
        groups = [
            (stock_pools.holding_process_pool, StockPoolTag.HOLDING_PROCESS),
            (stock_pools.account_executable_pool, StockPoolTag.ACCOUNT_EXECUTABLE),
            (stock_pools.market_watch_pool, StockPoolTag.MARKET_WATCH),
        ]
        for group, pool_tag in groups:
            for stock in group:
                if market_data_gateway.normalize_ts_code(stock.ts_code) == ts_code:
                    return stock, pool_tag
        return None, StockPoolTag.NOT_IN_POOL

    def _resolve_target_holding(self, holdings, ts_code: str):
        for holding in holdings:
            if market_data_gateway.normalize_ts_code(holding.ts_code) == ts_code:
                return holding
        return None

    def _resolve_target_sell_point(self, sell_analysis, ts_code: str):
        for group in (
            sell_analysis.sell_positions,
            sell_analysis.reduce_positions,
            sell_analysis.hold_positions,
        ):
            for point in group:
                if market_data_gateway.normalize_ts_code(point.ts_code) == ts_code:
                    return point
        return None

    def _load_history_payload(
        self,
        ts_code: str,
        trade_date: str,
    ) -> tuple[List[Dict], Dict, Optional[str]]:
        if not market_data_gateway.token or not market_data_gateway.pro:
            return [], {}, None
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        resolved_trade_date = market_data_gateway.resolve_trade_date(compact_trade_date)
        start_date = (
            datetime.strptime(resolved_trade_date, "%Y%m%d") - timedelta(days=140)
        ).strftime("%Y%m%d")
        history_rows: List[Dict] = []
        valuation_row: Dict = {}
        try:
            df = market_data_gateway.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=resolved_trade_date,
            )
            if df is not None and not df.empty:
                work = df.copy()
                work["trade_date"] = work["trade_date"].astype(str)
                work = work.sort_values("trade_date")
                history_rows = work.to_dict("records")
        except Exception:
            history_rows = []

        daily_basic = getattr(market_data_gateway.pro, "daily_basic", None)
        if callable(daily_basic):
            try:
                basic_df = daily_basic(
                    ts_code=ts_code,
                    trade_date=resolved_trade_date,
                    fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv,circ_mv",
                )
            except TypeError:
                basic_df = daily_basic(
                    ts_code=ts_code,
                    trade_date=resolved_trade_date,
                )
            except Exception:
                basic_df = None
            if basic_df is not None and not basic_df.empty:
                valuation_row = basic_df.iloc[0].to_dict()
        return history_rows, valuation_row, self._format_trade_date(resolved_trade_date)

    def _load_moneyflow_rows(
        self,
        ts_code: str,
        trade_date: str,
        *,
        days: int = 5,
    ) -> List[Dict]:
        if not market_data_gateway.token or not market_data_gateway.pro:
            return []
        moneyflow = getattr(market_data_gateway.pro, "moneyflow", None)
        if not callable(moneyflow):
            return []

        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        if not compact_trade_date:
            return []
        resolved_trade_date = market_data_gateway.resolve_trade_date(compact_trade_date)
        recent_dates = market_data_gateway.recent_open_dates(
            resolved_trade_date,
            count=max(days, 1),
        )
        start_date = recent_dates[-1] if recent_dates else resolved_trade_date
        fields = (
            "ts_code,trade_date,buy_lg_amount,sell_lg_amount,"
            "buy_elg_amount,sell_elg_amount,net_mf_amount"
        )
        try:
            df = moneyflow(
                ts_code=ts_code,
                start_date=start_date,
                end_date=resolved_trade_date,
                fields=fields,
            )
        except TypeError:
            try:
                df = moneyflow(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=resolved_trade_date,
                )
            except Exception:
                return []
        except Exception:
            return []

        if df is None or df.empty:
            return []
        work = df.copy()
        if "trade_date" in work.columns:
            work["trade_date"] = work["trade_date"].astype(str)
            work = work.sort_values("trade_date")
        return work.to_dict("records")

    def _build_rule_snapshot(
        self,
        *,
        trade_date: str,
        target_input,
        target_stock: StockOutput,
        context,
        scored_stocks: List[StockOutput],
        history_rows: List[Dict],
        valuation_row: Dict,
        moneyflow_rows: List[Dict],
        checkup_target: StockCheckupTarget,
        buy_view: Optional[StockCheckupBuyView],
        sell_view: Optional[StockCheckupSellView],
    ) -> StockCheckupRuleSnapshot:
        peer_comparison = self._build_peer_comparison(target_stock, scored_stocks)
        strategy = self._build_strategy(target_stock, checkup_target, buy_view, sell_view)
        return StockCheckupRuleSnapshot(
            basic_info=self._build_basic_info(target_input),
            market_context=self._build_market_context(context.market_env, target_stock),
            direction_position=self._build_direction_position(
                target_stock,
                context.sector_scan,
                peer_comparison.relative_strength,
            ),
            daily_structure=self._build_daily_structure(target_input, target_stock, history_rows),
            intraday_strength=self._build_intraday_strength(target_input, target_stock),
            fund_quality=self._build_fund_quality(
                target_input,
                target_stock,
                moneyflow_rows,
            ),
            peer_comparison=peer_comparison,
            valuation_profile=self._build_valuation_profile(valuation_row, target_stock),
            key_levels=self._build_key_levels(target_input, history_rows),
            buy_view=buy_view,
            sell_view=sell_view,
            strategy=strategy,
            final_conclusion=StockCheckupFinalConclusion(
                one_line_conclusion=self._build_one_line_conclusion(strategy, target_stock, checkup_target),
                summary_note=f"体检目标：{checkup_target.value}；交易日：{trade_date}",
            ),
        )

    def _build_basic_info(self, target_input) -> StockCheckupBasicInfo:
        tags: List[str] = []
        name = (target_input.stock_name or "").upper()
        code = str(target_input.ts_code).split(".")[0]
        if "ST" in name:
            tags.append("ST")
        if code.startswith("688"):
            tags.append("科创板")
        elif code.startswith("300"):
            tags.append("创业板")
        elif target_input.ts_code.endswith(".BJ"):
            tags.append("北交所")
        else:
            tags.append("主板")
        if abs(float(target_input.change_pct or 0)) >= 8 or float(target_input.turnover_rate or 0) >= 20:
            tags.append("高波动")
        return StockCheckupBasicInfo(
            ts_code=target_input.ts_code,
            stock_name=target_input.stock_name,
            sector_name=target_input.sector_name,
            board=self._resolve_board(target_input.ts_code),
            special_tags=tags,
            data_source=target_input.data_source,
            quote_time=target_input.quote_time,
        )

    def _build_market_context(self, market_env, target_stock: StockOutput) -> StockCheckupMarketContext:
        env_tag = getattr(getattr(market_env, "market_env_tag", None), "value", "")
        is_aligned = target_stock.stock_tradeability_tag.value == "可交易"
        return StockCheckupMarketContext(
            market_env_tag=env_tag,
            market_phase=env_tag or "中性",
            market_comment=getattr(market_env, "market_comment", ""),
            stock_market_alignment="顺市场" if is_aligned else "逆市场或容错偏低",
            tolerance_comment=(
                "当前环境下还有容错率"
                if is_aligned
                else "当前环境下追错和拿错的代价偏大"
            ),
        )

    def _build_direction_position(
        self,
        target_stock: StockOutput,
        sector_scan,
        relative_strength: str,
    ) -> StockCheckupDirectionPosition:
        sector = self._resolve_sector(target_stock.sector_name, sector_scan)
        sector_level = (
            getattr(getattr(sector, "sector_mainline_tag", None), "value", "非主流方向")
            if sector
            else "非主流方向"
        )
        sector_trend = (
            getattr(getattr(sector, "sector_continuity_tag", None), "value", "需确认")
            if sector
            else "需确认"
        )
        sector_linkage = (
            getattr(getattr(sector, "sector_tradeability_tag", None), "value", "需确认")
            if sector
            else "需确认"
        )
        return StockCheckupDirectionPosition(
            direction_name=target_stock.sector_name,
            sector_level=sector_level,
            sector_trend=f"板块当前偏{sector_trend}",
            sector_linkage=f"联动与交易性：{sector_linkage}",
            stock_role=getattr(target_stock.stock_role_tag, "value", target_stock.stock_core_tag.value),
            relative_strength=relative_strength,
        )

    def _build_daily_structure(
        self,
        target_input,
        target_stock: StockOutput,
        history_rows: List[Dict],
    ) -> StockCheckupDailyStructure:
        closes = [float(row.get("close") or 0) for row in history_rows if float(row.get("close") or 0) > 0]
        ma5 = self._calc_ma(closes, 5)
        ma10 = self._calc_ma(closes, 10)
        ma20 = self._calc_ma(closes, 20)
        ma60 = self._calc_ma(closes, 60)
        price = float(target_input.close or 0)
        ma_summary_bits = []
        for label, value in (("MA5", ma5), ("MA10", ma10), ("MA20", ma20), ("MA60", ma60)):
            if value is None:
                ma_summary_bits.append(f"{label}[需确认]")
            else:
                ma_summary_bits.append(f"{'站上' if price >= value else '跌破'}{label}")
        range20 = self._range_position(closes[-20:], price)
        range60 = self._range_position(closes[-60:], price)
        pattern = self._pattern_integrity(target_input, target_stock, ma20)
        return StockCheckupDailyStructure(
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            ma_position_summary="，".join(ma_summary_bits),
            stage_position=getattr(target_stock.structure_state_tag, "value", "需确认"),
            range_position_20d=range20,
            range_position_60d=range60,
            pattern_integrity=pattern,
            structure_conclusion=self._structure_conclusion(target_stock, range60),
        )

    def _build_intraday_strength(
        self,
        target_input,
        target_stock: StockOutput,
    ) -> StockCheckupIntradayStrength:
        close_quality = self._close_quality(target_input)
        candle_label = getattr(target_stock.day_strength_tag, "value", "需确认")
        return StockCheckupIntradayStrength(
            change_pct=target_input.change_pct,
            turnover_rate=target_input.turnover_rate,
            vol_ratio=target_input.vol_ratio,
            close_position=(
                "收盘靠近高位"
                if close_quality >= 0.7
                else "收盘中性"
                if close_quality >= 0.45
                else "收盘偏弱"
            ),
            candle_label=candle_label,
            volume_state=(
                "明显放量" if float(target_input.vol_ratio or 0) >= 2 else "量能一般"
            ),
            strength_level=self._strength_level(target_stock),
        )

    def _build_fund_quality(
        self,
        target_input,
        target_stock: StockOutput,
        moneyflow_rows: Optional[List[Dict]] = None,
    ) -> StockCheckupFundQuality:
        vol_ratio = float(target_input.vol_ratio or 0)
        close_quality = self._close_quality(target_input)
        moneyflow_rows = moneyflow_rows or []
        if moneyflow_rows:
            recent_rows = moneyflow_rows[-5:]
            latest = recent_rows[-1]
            recent_net = sum(self._safe_float(row.get("net_mf_amount")) or 0 for row in recent_rows)
            latest_net = self._safe_float(latest.get("net_mf_amount")) or 0
            big_net = (
                (self._safe_float(latest.get("buy_lg_amount")) or 0)
                + (self._safe_float(latest.get("buy_elg_amount")) or 0)
                - (self._safe_float(latest.get("sell_lg_amount")) or 0)
                - (self._safe_float(latest.get("sell_elg_amount")) or 0)
            )
            if latest_net > 0 and big_net > 0 and close_quality >= 0.55:
                quality = "资金净流入，质量较好"
                note = "moneyflow 显示今日净流入且大单/超大单同步净流入，收盘位置没有明显走弱。"
            elif latest_net > 0:
                quality = "资金净流入，但仍有分歧"
                note = "moneyflow 显示今日净流入，但大单/超大单或收盘位置仍需结合盘口确认。"
            elif latest_net < 0 and vol_ratio >= 1.5:
                quality = "放量净流出，质量偏弱"
                note = "moneyflow 显示今日净流出，叠加放量，需防范边拉边出的资金压力。"
            elif latest_net < 0:
                quality = "资金净流出，谨慎"
                note = "moneyflow 显示今日净流出，短线承接质量需要保守看。"
            else:
                quality = "资金流向中性"
                note = "moneyflow 今日净额接近持平，仍需结合盘口承接确认。"
            return StockCheckupFundQuality(
                recent_fund_flow=(
                    f"近{len(recent_rows)}日 moneyflow 净额：{self._format_amount_wan(recent_net)}"
                ),
                big_order_status=(
                    f"大单/超大单净额：{self._format_amount_wan(big_net)}"
                ),
                volume_behavior=(
                    f"量比 {vol_ratio:.1f}；今日净额 {self._format_amount_wan(latest_net)}"
                    if vol_ratio
                    else f"今日净额 {self._format_amount_wan(latest_net)}"
                ),
                cash_flow_quality=quality,
                note=note,
            )

        if vol_ratio >= 2 and close_quality >= 0.65:
            quality = "干净流入"
            note = "量能放大且收盘位置好，更像进攻而不是兑现。"
        elif vol_ratio >= 1.2:
            quality = "有分歧，但还能接受"
            note = "有量有分歧，暂未看到明显边拉边出的弱化迹象。"
        else:
            quality = "边拉边出，质量一般"
            note = "仅凭当前口径难确认主导资金方向，资金细项需确认。"
        return StockCheckupFundQuality(
            recent_fund_flow=f"近3-5日量能口径：{'偏强' if vol_ratio >= 1.5 else '一般'} [需确认]",
            big_order_status="大单/超大单明细 [需确认]",
            volume_behavior=f"量比 {vol_ratio:.1f}" if vol_ratio else "量比 [需确认]",
            cash_flow_quality=quality,
            note=note,
        )

    def _format_amount_wan(self, value: Optional[float]) -> str:
        if value is None:
            return "[需确认]"
        amount = float(value)
        if amount == 0:
            return "0万"
        label = f"{amount:+.0f}万" if abs(amount) >= 100 else f"{amount:+.1f}万"
        return label.replace("+", "流入 ").replace("-", "流出 ")

    def _build_peer_comparison(
        self,
        target_stock: StockOutput,
        scored_stocks: List[StockOutput],
    ) -> StockCheckupPeerComparison:
        same_sector = [
            stock for stock in scored_stocks
            if stock.ts_code != target_stock.ts_code and stock.sector_name == target_stock.sector_name
        ]
        peers = same_sector[:4] or [stock for stock in scored_stocks if stock.ts_code != target_stock.ts_code][:4]
        peer_items = [
            StockCheckupPeerItem(
                ts_code=peer.ts_code,
                stock_name=peer.stock_name,
                sector_name=peer.sector_name,
                change_pct=peer.change_pct,
                turnover_rate=peer.turnover_rate,
                amount=getattr(peer, "amount", None),
                role_hint=getattr(peer.stock_role_tag, "value", peer.stock_core_tag.value),
                relative_note=peer.pool_decision_summary or peer.stock_comment,
            )
            for peer in peers
        ]
        all_codes = [target_stock.ts_code] + [peer.ts_code for peer in peers]
        all_scores = [target_stock.stock_score] + [peer.stock_score for peer in peers]
        rank = sorted(all_scores, reverse=True).index(target_stock.stock_score) + 1 if all_scores else 1
        if rank == 1:
            relative_strength = "板块内相对强"
            recognizability = "具备辨识度"
        elif rank <= max(2, len(all_codes) // 2 + 1):
            relative_strength = "板块内相对中"
            recognizability = "辨识度一般"
        else:
            relative_strength = "板块内相对弱"
            recognizability = "更像陪跑"
        note = "优先和同板块可比票横向看强弱；若可比样本不足，结论仅供参考。"
        return StockCheckupPeerComparison(
            peers=peer_items,
            relative_strength=relative_strength,
            recognizability=recognizability,
            note=note,
        )

    def _build_valuation_profile(
        self,
        valuation_row: Dict,
        target_stock: StockOutput,
    ) -> StockCheckupValuationProfile:
        pe = self._safe_float(valuation_row.get("pe_ttm"))
        pb = self._safe_float(valuation_row.get("pb"))
        ps = self._safe_float(valuation_row.get("ps_ttm"))
        total_mv = self._safe_float(valuation_row.get("total_mv"))
        if total_mv is not None:
            total_mv = round(total_mv / 10000, 2)
        if pe is None and pb is None and ps is None:
            valuation_level = "估值 [需确认]"
        elif pe is not None and pe > 60:
            valuation_level = "偏高"
        elif pe is not None and pe < 15:
            valuation_level = "偏低"
        else:
            valuation_level = "估值正常"
        if target_stock.stock_core_tag.value == "核心" and target_stock.stock_tradeability_tag.value == "可交易":
            drive_type = "资金博弈 + 题材情绪"
        elif target_stock.sector_profile_tag and target_stock.sector_profile_tag.value.startswith("A"):
            drive_type = "题材情绪"
        else:
            drive_type = "修复反抽或基本面待确认"
        return StockCheckupValuationProfile(
            pe=pe,
            pb=pb,
            ps=ps,
            market_value=total_mv,
            valuation_level=valuation_level,
            drive_type=drive_type,
            note="估值口径来自 daily_basic；缺失时请以外部终端复核。",
        )

    def _build_key_levels(
        self,
        target_input,
        history_rows: List[Dict],
    ) -> StockCheckupKeyLevels:
        highs = [float(row.get("high") or 0) for row in history_rows if float(row.get("high") or 0) > 0]
        lows = [float(row.get("low") or 0) for row in history_rows if float(row.get("low") or 0) > 0]
        closes = [float(row.get("close") or 0) for row in history_rows if float(row.get("close") or 0) > 0]
        ma10 = self._calc_ma(closes, 10)
        ma20 = self._calc_ma(closes, 20)
        key_level_input = self._stable_key_level_input(target_input, history_rows)
        pressure = self._unique_prices([
            max(highs[-20:]) if len(highs) >= 20 else None,
            max(highs[-60:]) if len(highs) >= 60 else None,
            key_level_input.high if float(key_level_input.high or 0) > 0 else None,
        ])
        support = self._unique_prices([
            ma10,
            ma20,
            min(lows[-20:]) if len(lows) >= 20 else None,
            key_level_input.low if float(key_level_input.low or 0) > 0 else None,
        ])
        defense_level = support[-1] if support else None
        return StockCheckupKeyLevels(
            pressure_levels=pressure,
            support_levels=support,
            defense_level=defense_level,
            note="压力位优先看前高与区间高点，支撑位优先看均线与前低；盘中默认锚定上一交易日结构，实时强弱请结合盘口确认。",
        )

    def _stable_key_level_input(self, target_input, history_rows: List[Dict]):
        """关键位默认锚定到上一已完成交易日，避免盘中高低点导致防守线漂移。"""
        if not self._is_realtime_quote(target_input) or not history_rows:
            return target_input
        anchor_row = history_rows[-1] or {}
        anchor_high = self._safe_float(anchor_row.get("high"))
        anchor_low = self._safe_float(anchor_row.get("low"))
        if anchor_high is None and anchor_low is None:
            return target_input
        return SimpleNamespace(
            **{
                **getattr(target_input, "__dict__", {}),
                "high": anchor_high if anchor_high is not None else getattr(target_input, "high", None),
                "low": anchor_low if anchor_low is not None else getattr(target_input, "low", None),
            }
        )

    def _build_strategy(
        self,
        target_stock: StockOutput,
        checkup_target: StockCheckupTarget,
        buy_view: Optional[StockCheckupBuyView],
        sell_view: Optional[StockCheckupSellView],
    ) -> StockCheckupStrategy:
        characterization = self._characterization(target_stock)
        current_role = getattr(target_stock.stock_role_tag, "value", target_stock.stock_core_tag.value)
        risk_points = self._collect_risk_points(target_stock, sell_view)
        strategy = "观察"
        reason = "当前更适合继续观察确认。"
        if sell_view and sell_view.sell_signal_tag == "卖出":
            strategy = "放弃"
            reason = sell_view.sell_reason or "持仓逻辑已偏弱，优先退出。"
        elif buy_view and buy_view.buy_signal_tag == "可买":
            if buy_view.buy_point_type == "低吸":
                strategy = "低吸"
            elif buy_view.buy_point_type == "突破":
                strategy = "突破确认"
            else:
                strategy = "观察"
            reason = buy_view.buy_comment or "买点条件相对明确，但仍需确认。"
        elif checkup_target == StockCheckupTarget.HOLDING and sell_view and sell_view.sell_signal_tag == "减仓":
            strategy = "观察"
            reason = sell_view.sell_reason or "持仓优先降风险，不宜继续加码。"
        elif target_stock.stock_tradeability_tag.value == "不建议":
            strategy = "放弃"
            reason = "结构和交易性不支持当前参与。"
        return StockCheckupStrategy(
            current_characterization=characterization,
            current_role=current_role,
            current_strategy=strategy,
            strategy_reason=reason,
            risk_points=risk_points,
        )

    def _build_one_line_conclusion(
        self,
        strategy: StockCheckupStrategy,
        target_stock: StockOutput,
        checkup_target: StockCheckupTarget,
    ) -> str:
        if strategy.current_strategy == "放弃":
            return f"这票当前更像{strategy.current_characterization}，先别因为红盘或题材去脑补。"
        if checkup_target == StockCheckupTarget.HOLDING:
            return "这票还能看，但持仓上先按风控处理，不适合把犹豫当成持有理由。"
        if strategy.current_strategy == "突破确认":
            return "这票强度够，但更适合等突破确认，不舒服的位置别提前赌。"
        if strategy.current_strategy == "低吸":
            return "这票结构还在，适合等回踩承接，而不是情绪一来就追。"
        return f"这票能看，但当前更偏{strategy.current_characterization}，先观察再决定是否动手。"

    def _resolve_sector(self, sector_name: str, sector_scan):
        for group in (
            sector_scan.mainline_sectors,
            sector_scan.sub_mainline_sectors,
            sector_scan.follow_sectors,
            sector_scan.trash_sectors,
        ):
            for sector in group:
                if sector.sector_name == sector_name:
                    return sector
        return None

    def _resolve_board(self, ts_code: str) -> str:
        code = str(ts_code).split(".")[0]
        if str(ts_code).endswith(".BJ"):
            return "北交所"
        if code.startswith("688"):
            return "科创板"
        if code.startswith("300"):
            return "创业板"
        return "主板"

    def _calc_ma(self, closes: List[float], window: int) -> Optional[float]:
        if len(closes) < window:
            return None
        segment = closes[-window:]
        return round(sum(segment) / window, 2)

    def _range_position(self, closes: List[float], price: float) -> str:
        if not closes:
            return "区间位置 [需确认]"
        highest = max(closes)
        lowest = min(closes)
        if highest == lowest:
            return "区间中位"
        pct = (price - lowest) / (highest - lowest)
        if pct >= 0.8:
            return "区间高位"
        if pct <= 0.2:
            return "区间低位"
        return "区间中位"

    def _pattern_integrity(self, target_input, target_stock: StockOutput, ma20: Optional[float]) -> str:
        close_quality = self._close_quality(target_input)
        if close_quality >= 0.7 and float(target_input.change_pct or 0) > 0:
            if ma20 is not None and float(target_input.close or 0) >= ma20:
                return "趋势性 + 承接尚可"
            return "有进攻形态，但中期均线支撑待确认"
        if close_quality < 0.35:
            return "冲高回落，形态完整性一般"
        if getattr(target_stock.structure_state_tag, "value", "") == StructureStateTag.REPAIR.value:
            return "修复中，等待结构进一步确认"
        return "平台整理或分歧中"

    def _structure_conclusion(self, target_stock: StockOutput, range60: str) -> str:
        state = getattr(target_stock.structure_state_tag, "value", "")
        if state in {StructureStateTag.ACCELERATE.value, StructureStateTag.START.value}:
            return "当前日线结构偏强趋势。"
        if state == StructureStateTag.REPAIR.value:
            return "当前日线结构更像弱修复，仍需确认。"
        if state == StructureStateTag.LATE_STAGE.value or range60 == "区间高位":
            return "当前日线结构处在高位危险区。"
        return "当前日线结构偏分歧，强弱解释权要结合市场再看。"

    def _close_quality(self, target_input) -> float:
        high = float(target_input.high or 0)
        low = float(target_input.low or 0)
        close = float(target_input.close or 0)
        if high <= low:
            return 0.5
        return max(0.0, min(1.0, (close - low) / (high - low)))

    def _strength_level(self, target_stock: StockOutput) -> str:
        day_strength = getattr(target_stock.day_strength_tag, "value", "")
        if day_strength in {"涨停级别强", "趋势大阳强"}:
            return "很强"
        if day_strength == "分歧转强":
            return "偏强"
        if day_strength == "只是跟涨":
            return "一般"
        if day_strength == "冲高回落":
            return "偏弱"
        return "弱"

    def _safe_float(self, value) -> Optional[float]:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    def _is_realtime_quote(self, target_input) -> bool:
        return str(getattr(target_input, "data_source", "") or "").startswith("realtime_")

    def _unique_prices(self, values: List[Optional[float]]) -> List[float]:
        result: List[float] = []
        for value in values:
            if value is None:
                continue
            rounded = round(float(value), 2)
            if rounded > 0 and rounded not in result:
                result.append(rounded)
        return result

    def _characterization(self, target_stock: StockOutput) -> str:
        state = getattr(target_stock.structure_state_tag, "value", "")
        if state in {StructureStateTag.START.value, StructureStateTag.ACCELERATE.value}:
            return "强趋势"
        if state == StructureStateTag.REPAIR.value:
            return "修复"
        if state == StructureStateTag.LATE_STAGE.value:
            return "高位危险"
        if target_stock.stock_strength_tag.value == "弱":
            return "弱势"
        return "分歧"

    def _collect_risk_points(
        self,
        target_stock: StockOutput,
        sell_view: Optional[StockCheckupSellView],
    ) -> List[str]:
        risks: List[str] = []
        if getattr(target_stock.stock_continuity_tag, "value", "") == "末端谨慎":
            risks.append("高位末端")
        if getattr(target_stock.day_strength_tag, "value", "") == "冲高回落":
            risks.append("冲高回落")
        if target_stock.stock_tradeability_tag.value == "不建议":
            risks.append("弱市容错差")
        if target_stock.stock_falsification_cond:
            risks.append(target_stock.stock_falsification_cond)
        if sell_view and sell_view.sell_signal_tag in {"卖出", "减仓"}:
            risks.append("持仓处理优先")
        deduped: List[str] = []
        for risk in risks:
            if risk and risk not in deduped:
                deduped.append(risk)
        return deduped[:5] or ["板块掉队"]

    def _format_trade_date(self, trade_date: Optional[str]) -> Optional[str]:
        if not trade_date:
            return None
        raw = str(trade_date)
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw


stock_checkup_service = StockCheckupService()
