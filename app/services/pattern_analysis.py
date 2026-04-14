"""
股票形态分析服务
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import (
    LlmCallStatus,
    StockPatternAnalysisResponse,
    StockPatternAnnotation,
    StockPatternBasicInfo,
    StockPatternCandidate,
    StockPatternCandle,
    StockPatternChartPayload,
    StockPatternFeatureSnapshot,
    StockPatternLine,
    StockPatternResult,
    StockPatternZone,
    StockOutput,
    StockPoolTag,
)
from app.services.decision_context import decision_context_service
from app.services.llm_explainer import llm_explainer_service
from app.services.market_data_gateway import market_data_gateway
from app.services.stock_checkup import stock_checkup_service
from app.services.stock_filter import stock_filter_service


class PatternAnalysisService:
    """基于规则特征与 LLM 解释的股票形态分析服务。"""

    CORE_PATTERNS = (
        "平台整理",
        "平台突破临界",
        "箱体震荡",
        "三角收敛",
        "回踩确认",
        "旗形中继",
        "上升趋势延续",
        "假突破/突破失败",
        "双顶风险",
        "双底修复",
        "V形修复",
        "圆弧底修复",
        "高位震荡/派发嫌疑",
        "弱修复反弹",
        "下跌通道反抽",
    )

    async def analyze(
        self,
        ts_code: str,
        trade_date: str,
        *,
        account_id: Optional[str] = None,
        force_llm_refresh: bool = False,
    ) -> StockPatternAnalysisResponse:
        normalized_code = market_data_gateway.normalize_ts_code(ts_code)
        context = await decision_context_service.build_context(
            trade_date,
            top_gainers=120,
            include_holdings=True,
            account_id=account_id,
        )
        stocks, _found_in_candidates = decision_context_service.merge_single_stock_into_context(
            trade_date,
            context.stocks,
            normalized_code,
            candidate_source_tag="形态分析",
        )
        target_input = stock_checkup_service._resolve_target_input(stocks, normalized_code)
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
        target_scored = stock_checkup_service._resolve_target_scored_stock(
            normalized_code,
            scored_stocks,
            target_input,
            market_env=context.market_env,
            sector_scan=context.sector_scan,
        )
        history_rows, _valuation_row, resolved_trade_date = stock_checkup_service._load_history_payload(
            normalized_code,
            trade_date,
        )
        if not history_rows:
            history_rows = [self._target_input_to_history_row(target_input, trade_date)]

        basic_info = self._build_basic_info(
            target_input,
            trade_date,
            resolved_trade_date or context.resolved_stock_trade_date or trade_date,
        )
        feature_snapshot = self._build_feature_snapshot(target_input, history_rows)
        candidates = self._build_pattern_candidates(feature_snapshot, target_input, target_scored, history_rows)
        rule_result = self._build_rule_result(feature_snapshot, candidates, target_input, target_scored, history_rows)
        chart_payload = self._build_chart_payload(
            history_rows,
            feature_snapshot,
            rule_result,
        )

        llm_result, llm_status = await llm_explainer_service.explain_stock_pattern_with_status(
            basic_info=basic_info,
            feature_snapshot=feature_snapshot,
            pattern_analysis=rule_result,
            trade_date=trade_date,
            account_id=account_id,
            force_refresh=force_llm_refresh,
        )
        if llm_result:
            rule_result = self._merge_llm_result(rule_result, llm_result)

        return StockPatternAnalysisResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date or context.resolved_stock_trade_date or trade_date,
            basic_info=basic_info,
            feature_snapshot=feature_snapshot,
            chart_payload=chart_payload,
            pattern_analysis=rule_result,
            llm_status=llm_status,
        )

    def _target_input_to_history_row(self, target_input, trade_date: str) -> Dict:
        return {
            "trade_date": str(trade_date).replace("-", ""),
            "open": float(target_input.open or 0),
            "high": float(target_input.high or 0),
            "low": float(target_input.low or 0),
            "close": float(target_input.close or 0),
            "vol": float(getattr(target_input, "volume", 0) or 0),
        }

    def _build_basic_info(self, target_input, trade_date: str, resolved_trade_date: str) -> StockPatternBasicInfo:
        return StockPatternBasicInfo(
            ts_code=target_input.ts_code,
            stock_name=target_input.stock_name,
            sector_name=target_input.sector_name,
            board=stock_checkup_service._resolve_board(target_input.ts_code),
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date,
            data_source=target_input.data_source,
            quote_time=target_input.quote_time,
        )

    def _build_feature_snapshot(
        self,
        target_input,
        history_rows: List[Dict],
    ) -> StockPatternFeatureSnapshot:
        closes = [self._safe_float(row.get("close")) for row in history_rows]
        highs = [self._safe_float(row.get("high")) for row in history_rows]
        lows = [self._safe_float(row.get("low")) for row in history_rows]
        volumes = [self._safe_float(row.get("vol")) or self._safe_float(row.get("volume")) for row in history_rows]

        closes = [value for value in closes if value is not None]
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        volume_values = [value for value in volumes if value is not None]

        ma5 = stock_checkup_service._calc_ma(closes, 5)
        ma10 = stock_checkup_service._calc_ma(closes, 10)
        ma20 = stock_checkup_service._calc_ma(closes, 20)
        ma60 = stock_checkup_service._calc_ma(closes, 60)
        price = float(target_input.close or 0)
        range20_closes = closes[-20:] if len(closes) >= 20 else closes
        range60_closes = closes[-60:] if len(closes) >= 60 else closes
        range20_high = round(max(highs[-20:]), 2) if len(highs) >= 20 else (round(max(highs), 2) if highs else None)
        range20_low = round(min(lows[-20:]), 2) if len(lows) >= 20 else (round(min(lows), 2) if lows else None)
        range60_high = round(max(highs[-60:]), 2) if len(highs) >= 60 else (round(max(highs), 2) if highs else None)
        range60_low = round(min(lows[-60:]), 2) if len(lows) >= 60 else (round(min(lows), 2) if lows else None)
        center_shift_20d_pct = self._center_shift_pct(closes[-40:-20], closes[-20:]) if len(closes) >= 40 else None
        latest_volume = volume_values[-1] if volume_values else None
        avg_volume_5 = self._avg(volume_values[-6:-1]) if len(volume_values) >= 6 else self._avg(volume_values[:-1])
        breakout_ready = bool(range20_high and price >= range20_high * 0.985 and price <= range20_high * 1.03)
        retrace_ready = bool(ma10 and ma20 and price >= ma20 and price <= max(ma10, ma20) * 1.02)
        swing_high_points = self._swing_points(history_rows, mode="high")
        swing_low_points = self._swing_points(history_rows, mode="low")
        swing_highs = [point["price"] for point in swing_high_points]
        swing_lows = [point["price"] for point in swing_low_points]
        neckline_level = self._estimate_neckline(history_rows, swing_high_points, swing_low_points)
        platform_upper, platform_lower = self._estimate_platform(highs, lows)
        flag_info = self._flag_structure(history_rows)
        notes: List[str] = []
        if len(closes) < 60:
            notes.append("历史数据不足 60 根，复杂形态只做保守判断。")
        if breakout_ready:
            notes.append("最新价格已靠近近 20 日箱体上沿。")
        if retrace_ready:
            notes.append("价格回到中短均线附近，存在回踩确认语义。")

        return StockPatternFeatureSnapshot(
            history_window=len(closes),
            sufficient_history=len(closes) >= 60,
            latest_close=round(price, 2) if price else None,
            latest_change_pct=self._safe_float(getattr(target_input, "change_pct", None)),
            latest_turnover_rate=self._safe_float(getattr(target_input, "turnover_rate", None)),
            latest_vol_ratio=self._safe_float(getattr(target_input, "vol_ratio", None)),
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            ma_alignment=self._ma_alignment(price, ma5, ma10, ma20, ma60),
            ma_slope_10=self._ma_slope(closes, 10, 3),
            ma_slope_20=self._ma_slope(closes, 20, 5),
            ma_slope_60=self._ma_slope(closes, 60, 10),
            range20_high=range20_high,
            range20_low=range20_low,
            range60_high=range60_high,
            range60_low=range60_low,
            range20_position=stock_checkup_service._range_position(range20_closes, price),
            range60_position=stock_checkup_service._range_position(range60_closes, price),
            amplitude_20d_pct=self._amplitude_pct(range20_high, range20_low),
            amplitude_60d_pct=self._amplitude_pct(range60_high, range60_low),
            center_shift_20d_pct=center_shift_20d_pct,
            close_quality=round(stock_checkup_service._close_quality(target_input), 3),
            volume_pattern=self._volume_pattern(latest_volume, avg_volume_5, getattr(target_input, "vol_ratio", None)),
            candle_bias=self._candle_bias(target_input),
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            neckline_level=neckline_level,
            platform_upper=platform_upper,
            platform_lower=platform_lower,
            breakout_ready=breakout_ready,
            retrace_ready=retrace_ready,
            notes=notes,
            flag_pole_high=round(flag_info["pole_end_price"], 2) if flag_info else None,
            flag_pole_start=round(flag_info["pole_start_price"], 2) if flag_info else None,
            flag_pole_gain_pct=flag_info["pole_gain_pct"] if flag_info else None,
            flag_pullback_pct=flag_info["pullback_pct"] if flag_info else None,
            flag_face_high=round(flag_info["flag_high"], 2) if flag_info else None,
            flag_face_low=round(flag_info["flag_low"], 2) if flag_info else None,
        )

    def _build_pattern_candidates(
        self,
        feature_snapshot: StockPatternFeatureSnapshot,
        target_input,
        target_scored: StockOutput,
        history_rows: List[Dict],
    ) -> List[StockPatternCandidate]:
        candidates: List[StockPatternCandidate] = []
        price = float(target_input.close or 0)
        latest_change = float(target_input.change_pct or 0)
        close_quality = float(feature_snapshot.close_quality or 0)
        amplitude20 = float(feature_snapshot.amplitude_20d_pct or 0)
        amplitude60 = float(feature_snapshot.amplitude_60d_pct or 0)
        center_shift = float(feature_snapshot.center_shift_20d_pct or 0)
        ma_slope_10 = float(feature_snapshot.ma_slope_10 or 0)
        ma_slope_20 = float(feature_snapshot.ma_slope_20 or 0)
        ma_slope_60 = float(feature_snapshot.ma_slope_60 or 0)
        ma20 = feature_snapshot.ma20
        ma60 = feature_snapshot.ma60
        ma10 = feature_snapshot.ma10
        platform_upper = feature_snapshot.platform_upper
        platform_lower = feature_snapshot.platform_lower
        swing_highs = feature_snapshot.swing_highs
        swing_lows = feature_snapshot.swing_lows
        volume_pattern = feature_snapshot.volume_pattern
        candle_bias = feature_snapshot.candle_bias
        intraday_high = float(target_input.high or price or 0)
        amplitude_contracting = bool(amplitude20 and amplitude60 and amplitude20 <= amplitude60 * 0.72)
        amplitude_compressing = bool(amplitude20 and amplitude60 and amplitude20 <= amplitude60 * 0.85)
        swing_high_points = self._swing_points(history_rows, mode="high")
        swing_low_points = self._swing_points(history_rows, mode="low")
        descending_highs = (
            len(swing_highs) >= 2 and swing_highs[-1] < swing_highs[-2] and
            abs(swing_highs[-2] - swing_highs[-1]) / max(swing_highs[-2], 0.01) >= 0.015
        )
        rising_lows = (
            len(swing_lows) >= 2 and swing_lows[-1] > swing_lows[-2] and
            abs(swing_lows[-1] - swing_lows[-2]) / max(swing_lows[-2], 0.01) >= 0.012
        )
        triangle_structure = self._triangle_structure(history_rows)

        if not feature_snapshot.sufficient_history:
            candidates.append(
                StockPatternCandidate(
                    name="未识别明确形态",
                    score=0.35,
                    confidence="低",
                    phase="数据不足",
                    summary="历史日线不足，先按趋势和关键位保守处理。",
                    rule_hits=["历史数据不足 60 根"],
                    conflict_points=[],
                )
            )
            return candidates

        if platform_upper and platform_lower and amplitude20 <= 16:
            score = 0.58
            hits = [
                "近 20 日振幅受控，区间上沿与下沿相对稳定",
                f"平台上下沿约 {platform_lower:.2f}-{platform_upper:.2f}",
            ]
            phase = "构建中"
            if feature_snapshot.breakout_ready:
                score += 0.17
                hits.append("最新价格已靠近平台上沿")
                phase = "临近突破"
            if latest_change >= 3 and close_quality >= 0.65:
                score += 0.08
                hits.append("当天阳线质量较好")
            candidates.append(
                StockPatternCandidate(
                    name="平台突破临界" if feature_snapshot.breakout_ready else "平台整理",
                    score=min(score, 0.92),
                    confidence=self._score_confidence(score),
                    phase=phase,
                    summary="平台结构相对完整，重点看上沿是否放量突破。",
                    rule_hits=hits,
                    conflict_points=["箱体振幅过大时容易退化成高位震荡"] if amplitude20 > 12 else [],
                )
            )

        if (
            platform_upper
            and platform_lower
            and 8 <= amplitude20 <= 18
            and not feature_snapshot.breakout_ready
            and feature_snapshot.range20_position in {"区间中位", "区间高位", "区间低位"}
            and feature_snapshot.ma_alignment == "均线纠缠"
        ):
            score = 0.55
            if volume_pattern == "缩量":
                score += 0.05
            candidates.append(
                StockPatternCandidate(
                    name="箱体震荡",
                    score=min(score, 0.84),
                    confidence=self._score_confidence(score),
                    phase="箱体来回切换",
                    summary="更像边界清晰的箱体震荡，先按上沿压力和下沿支撑来读。",
                    rule_hits=[
                        f"近 20 日区间边界约 {platform_lower:.2f}-{platform_upper:.2f}",
                        "均线偏纠缠，趋势方向没有完全打开",
                        f"当前处于 {feature_snapshot.range20_position}",
                    ],
                    conflict_points=["一旦带量突破箱体上沿，箱体震荡会切换成突破类形态"],
                )
            )

        if triangle_structure is not None and amplitude_compressing:
            score = 0.6
            tri_type = triangle_structure.get("triangle_type", "三角收敛")
            up0, up1 = triangle_structure['upper_points'][0]['price'], triangle_structure['upper_points'][1]['price']
            lo0, lo1 = triangle_structure['lower_points'][0]['price'], triangle_structure['lower_points'][1]['price']
            if tri_type == "上升三角":
                hits = [
                    f"低点持续抬高：{lo0:.2f}->{lo1:.2f}，顶部压力区相对平坦",
                    f"当前投影边界约 {triangle_structure['projected_lower']:.2f}-{triangle_structure['projected_upper']:.2f}",
                ]
                summary = f"低点抬高、顶部平坦，{tri_type}结构，等待有效向上突破。"
            elif tri_type == "下降三角":
                hits = [
                    f"高点持续下移：{up0:.2f}->{up1:.2f}，底部支撑区相对平坦",
                    f"当前投影边界约 {triangle_structure['projected_lower']:.2f}-{triangle_structure['projected_upper']:.2f}",
                ]
                summary = f"高点下移、底部平坦，{tri_type}结构，方向选择前偏谨慎。"
            else:
                hits = [
                    f"高点下移：{up0:.2f}->{up1:.2f}，低点抬高：{lo0:.2f}->{lo1:.2f}",
                    f"当前投影收敛边界约 {triangle_structure['projected_lower']:.2f}-{triangle_structure['projected_upper']:.2f}",
                ]
                summary = "高点下移、低点抬高，对称三角收敛，等待方向选择。"
            phase = "收敛中"
            if price >= triangle_structure["projected_upper"] * 0.995:
                score += 0.07
                phase = "突破尝试"
                summary = "局部收敛仍成立，但价格已经逼近或试探收敛上沿，下一步看能否有效确认。"
                hits.append("价格已逼近收敛上沿投影")
            elif triangle_structure["current_gap_pct"] <= 6:
                score += 0.04
                phase = "收敛末端"
                hits.append("当前上下边界间距已明显收窄")
            candidates.append(
                StockPatternCandidate(
                    name="三角收敛",
                    score=min(score, 0.87),
                    confidence=self._score_confidence(score),
                    phase=phase,
                    summary=summary,
                    rule_hits=hits,
                    conflict_points=["如果后续量能始终跟不上，收敛也可能继续拖成普通震荡"],
                )
            )

        if (
            ma20 is not None
            and ma60 is not None
            and price >= ma20 >= ma60
            and ma_slope_20 > 0
            and ma_slope_60 >= 0
        ):
            score = 0.63
            hits = [
                "价格位于 MA20 和 MA60 之上",
                "中期均线仍在上行",
            ]
            if close_quality >= 0.65 and latest_change > 0:
                score += 0.08
                hits.append("收盘位置较好，趋势延续性更强")
            if feature_snapshot.retrace_ready:
                score += 0.06
                hits.append("价格回到趋势均线附近，存在回踩确认语义")
                name = "回踩确认"
                phase = "回踩后待确认"
                summary = "趋势没坏，关键看均线附近的承接和次日确认。"
            else:
                name = "上升趋势延续"
                phase = "趋势延续"
                summary = "中期结构仍偏多头，优先把它当趋势延续处理。"
            candidates.append(
                StockPatternCandidate(
                    name=name,
                    score=min(score, 0.9),
                    confidence=self._score_confidence(score),
                    phase=phase,
                    summary=summary,
                    rule_hits=hits,
                    conflict_points=["如果后续跌回 MA20 下方，趋势延续判断会明显转弱"],
                )
            )

        flag_pole_high = feature_snapshot.flag_pole_high
        flag_pole_start = feature_snapshot.flag_pole_start
        flag_pole_gain_pct = feature_snapshot.flag_pole_gain_pct or 0
        flag_face_high = feature_snapshot.flag_face_high
        flag_face_low = feature_snapshot.flag_face_low
        flag_pullback_pct = feature_snapshot.flag_pullback_pct or 0

        # 大结构明显压制时（均线死叉且价格在 MA60 下方）不识别旗形中继
        flag_large_struct_broken = bool(
            ma60 and price < ma60
            and feature_snapshot.ma_slope_60 is not None
            and feature_snapshot.ma_slope_60 < 0
        )

        if flag_pole_high is not None and flag_face_low is not None and not flag_large_struct_broken:
            score = 0.65
            hits = [
                f"旗杆：从 {flag_pole_start:.2f} 涨至 {flag_pole_high:.2f}（+{flag_pole_gain_pct:.1f}%）",
                f"旗面回调 {flag_pullback_pct:.1f}%，整理结构健康",
            ]
            phase = "旗面整理中"

            # 价格已逼近或突破旗杆高点（旗面突破阶段）
            if price >= flag_pole_high * 0.97:
                score += 0.10
                phase = "突破旗面上沿"
                hits.append("价格已重新逼近或突破旗杆高点，突破信号明确")
            elif flag_face_high and price >= flag_face_high * 0.98:
                score += 0.05
                phase = "逼近旗面上沿"
                hits.append("价格逼近旗面上沿，观察是否有效放量突破")

            # 量能配合
            if volume_pattern == "缩量":
                score += 0.04
                hits.append("旗面整理期间量能收缩，回调性质健康")
            elif volume_pattern in {"明显放量", "温和放量"} and "突破" in phase:
                score += 0.05
                hits.append("突破伴随量能放大，有效性更强")

            # 大结构完整（MA60 未破）
            if ma60 and price >= ma60:
                score += 0.03
                hits.append("价格仍在 MA60 上方，大结构完整")

            candidates.append(
                StockPatternCandidate(
                    name="旗形中继",
                    score=min(score, 0.91),
                    confidence=self._score_confidence(score),
                    phase=phase,
                    summary="检测到旗杆 + 旗面收敛结构，关键看旗面能否重新向上打开。",
                    rule_hits=hits,
                    conflict_points=["若旗面整理跌破旗杆起点附近，旗形中继会退化成普通震荡或趋势反转"],
                )
            )

        if (
            (
                feature_snapshot.range20_position == "区间高位"
                or (platform_upper is not None and intraday_high >= platform_upper * 1.002)
            )
            and (
                feature_snapshot.breakout_ready
                or (platform_upper is not None and intraday_high >= platform_upper * 1.002)
            )
            and candle_bias == "冲高回落"
            and volume_pattern in {"明显放量", "温和放量"}
        ):
            score = 0.62
            candidates.append(
                StockPatternCandidate(
                    name="假突破/突破失败",
                    score=score,
                    confidence=self._score_confidence(score),
                    phase="冲高回落",
                    summary="价格摸到上沿但收盘发虚，更像突破尝试失败而不是有效打开。",
                    rule_hits=[
                        "价格已触及或逼近上沿压力",
                        "K 线呈冲高回落，收盘质量偏弱",
                        f"量能状态为{volume_pattern}",
                    ],
                    conflict_points=["如果次日能重新站回突破线并放量，假突破判断会被推翻"],
                )
            )

        if (
            feature_snapshot.range60_position == "区间高位"
            and amplitude20 <= 12
            and close_quality < 0.55
            and latest_change <= 2
        ):
            score = 0.57
            candidates.append(
                StockPatternCandidate(
                    name="高位震荡/派发嫌疑",
                    score=score,
                    confidence=self._score_confidence(score),
                    phase="高位分歧",
                    summary="位置偏高但推进效率一般，先按高位震荡看而不是直接预设突破。",
                    rule_hits=[
                        "60 日区间位置处在高位",
                        "近 20 日振幅不大但收盘强度不足",
                    ],
                    conflict_points=["若后续放量有效突破平台上沿，会切换成平台突破临界"],
                )
            )

        if (
            len(swing_high_points) >= 2
            and feature_snapshot.range60_position == "区间高位"
            and close_quality < 0.5
        ):
            sh_a, sh_b = swing_high_points[-2], swing_high_points[-1]
            time_gap = sh_b["index"] - sh_a["index"]
            if (
                time_gap >= 10
                and abs(sh_a["price"] - sh_b["price"]) / max(sh_a["price"], 0.01) <= 0.05
            ):
                score = 0.61
                candidates.append(
                    StockPatternCandidate(
                        name="双顶风险",
                        score=score,
                        confidence=self._score_confidence(score),
                        phase="二次冲顶后分歧",
                        summary="两个高点接近，当前位置更要防二次冲顶失败。",
                        rule_hits=[
                            f"两个波段高点接近：{sh_a['price']:.2f}/{sh_b['price']:.2f}（间隔 {time_gap} 根）",
                            "高位区收盘质量偏弱",
                        ],
                        conflict_points=["若后续有效站上两个高点，会失去双顶语义"],
                    )
                )

        if (
            len(swing_low_points) >= 2
            and feature_snapshot.range60_position != "区间高位"
            and latest_change >= 0
            and (
                close_quality >= 0.5
                or center_shift >= 2
                or volume_pattern in {"明显放量", "温和放量"}
            )
        ):
            sl_a, sl_b = swing_low_points[-2], swing_low_points[-1]
            sl_time_gap = sl_b["index"] - sl_a["index"]
            if (
                sl_time_gap >= 10
                and abs(sl_a["price"] - sl_b["price"]) / max(sl_a["price"], 0.01) <= 0.08
                and feature_snapshot.neckline_level is not None
                and feature_snapshot.neckline_level > max(sl_a["price"], sl_b["price"])
            ):
                score = 0.56
                if center_shift >= 2:
                    score += 0.04
                if volume_pattern in {"明显放量", "温和放量"}:
                    score += 0.03
                candidates.append(
                    StockPatternCandidate(
                        name="双底修复",
                        score=min(score, 0.86),
                        confidence=self._score_confidence(score),
                        phase="颈线附近修复",
                        summary="两个低点接近，当前位置更像双底修复而不是单日反弹。",
                        rule_hits=[
                            f"两个波段低点接近：{sl_a['price']:.2f}/{sl_b['price']:.2f}（间隔 {sl_time_gap} 根）",
                            f"两底之间的中间高点约 {feature_snapshot.neckline_level:.2f}",
                            "收盘位置和修复动能不差",
                        ],
                        conflict_points=["颈线未确认前，仍可能只是弱修复反弹"],
                    )
                )

        # V形结构验证：近15根K线中，低点前有明显下跌，低点后有明显反弹
        _v_closes = [self._safe_float(row.get("close")) for row in history_rows[-15:]]
        _v_closes = [c for c in _v_closes if c is not None]
        is_v_shape = False
        v_drop_pct = 0.0
        v_recovery_pct = 0.0
        if len(_v_closes) >= 8:
            _pre = _v_closes[:-1]
            _v_low = min(_pre)
            _v_idx = _pre.index(_v_low)
            # 低点必须在窗口中间段（不是第一根也不是最后两根），才说明有下跌+回升过程
            if 1 <= _v_idx <= len(_pre) - 2:
                _v_start = _v_closes[0]
                _v_current = _v_closes[-1]
                if _v_start > 0 and _v_low > 0:
                    v_drop_pct = (_v_start - _v_low) / _v_start * 100
                    v_recovery_pct = (_v_current - _v_low) / _v_low * 100
                    is_v_shape = v_drop_pct >= 7 and v_recovery_pct >= 6

        if (
            is_v_shape
            and center_shift >= 2
            and ma_slope_10 > 0
            and latest_change >= 1
            and close_quality >= 0.58
            and feature_snapshot.range20_position in {"区间中位", "区间高位"}
        ):
            score = 0.57
            if volume_pattern in {"明显放量", "温和放量"}:
                score += 0.05
            candidates.append(
                StockPatternCandidate(
                    name="V形修复",
                    score=min(score, 0.86),
                    confidence=self._score_confidence(score),
                    phase="快速修复",
                    summary="近期急跌后快速回升，更像快速 V 形修复而不是横向磨底。",
                    rule_hits=[
                        f"近 15 日内急跌 {v_drop_pct:.1f}% 后回升 {v_recovery_pct:.1f}%，V 形结构成立",
                        f"近 20 日重心变化 {center_shift:.2f}%，短期均线斜率转正",
                        f"收盘质量 {close_quality:.2f}，日内承接不差",
                    ],
                    conflict_points=["V 形修复最怕上冲后再次回落，不能把反弹速度直接等同于结构确认"],
                )
            )

        if (
            len(swing_lows) >= 2
            and ma_slope_20 > 0
            and center_shift > 0.8
            and amplitude_contracting
            and feature_snapshot.range60_position != "区间高位"
        ):
            first_low, second_low = swing_lows[-2], swing_lows[-1]
            if second_low >= first_low * 0.97:
                score = 0.55
                candidates.append(
                    StockPatternCandidate(
                        name="圆弧底修复",
                        score=score,
                        confidence=self._score_confidence(score),
                        phase="缓慢抬升",
                        summary="低点没有急拉急杀，更像底部缓慢抬起的圆弧修复。",
                        rule_hits=[
                            f"两个低点没有继续创新低：{first_low:.2f}/{second_low:.2f}",
                            "近 20 日振幅较长周期收敛，节奏偏缓",
                            "MA20 斜率转正，底部抬升更平滑",
                        ],
                        conflict_points=["如果后续再次回到前低附近，圆弧底语义会明显削弱"],
                    )
                )

        structure_state = getattr(getattr(target_scored, "structure_state_tag", None), "value", "")
        if structure_state == "修复" and close_quality >= 0.45:
            score = 0.49
            candidates.append(
                StockPatternCandidate(
                    name="弱修复反弹",
                    score=score,
                    confidence=self._score_confidence(score),
                    phase="修复中",
                    summary="结构有修复动作，但暂时还谈不上强趋势确认。",
                    rule_hits=[
                        "规则结构标签偏修复",
                        "收盘没有完全走弱",
                    ],
                    conflict_points=["如果后续重新跌破关键均线，修复语义会失效"],
                )
            )

        if (
            ma20 is not None
            and ma60 is not None
            and price < ma20 < ma60
            and ma_slope_20 < 0
            and ma_slope_60 <= 0
        ):
            score = 0.54
            if latest_change > 0 or close_quality >= 0.45:
                score += 0.03
            candidates.append(
                StockPatternCandidate(
                    name="下跌通道反抽",
                    score=min(score, 0.82),
                    confidence=self._score_confidence(score),
                    phase="弱势反抽",
                    summary="大结构仍受均线压制，当前更像下跌通道里的反抽而不是反转。",
                    rule_hits=[
                        "价格仍处在 MA20 和 MA60 下方",
                        "中长期均线斜率没有转正",
                        f"当前 K 线表现为{candle_bias}",
                    ],
                    conflict_points=["只有重新站回 MA20 并持续放量，弱势反抽才可能升级为修复结构"],
                )
            )

        if not candidates:
            fallback_score = 0.38 if amplitude60 > 0 else 0.28
            candidates.append(
                StockPatternCandidate(
                    name="未识别明确形态",
                    score=fallback_score,
                    confidence=self._score_confidence(fallback_score),
                    phase="待观察",
                    summary="当前没有足够清晰的形态边界，更适合围绕关键位做观察。",
                    rule_hits=["规则候选未命中核心形态"],
                    conflict_points=[],
                )
            )

        deduped: Dict[str, StockPatternCandidate] = {}
        for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
            if candidate.name not in deduped:
                deduped[candidate.name] = candidate
        return list(deduped.values())[:3]

    def _build_rule_result(
        self,
        feature_snapshot: StockPatternFeatureSnapshot,
        candidates: List[StockPatternCandidate],
        target_input,
        target_scored: StockOutput,
        history_rows: List[Dict],
    ) -> StockPatternResult:
        primary = candidates[0] if candidates else StockPatternCandidate(name="未识别明确形态")
        triangle_structure = self._triangle_structure(history_rows) if primary.name == "三角收敛" else None
        base_support_levels = self._unique_prices(
            [
                feature_snapshot.platform_lower,
                feature_snapshot.ma10,
                feature_snapshot.ma20,
                feature_snapshot.range20_low,
            ]
        )
        base_pressure_levels = self._unique_prices(
            [
                feature_snapshot.platform_upper,
                feature_snapshot.range20_high,
                feature_snapshot.range60_high,
            ]
        )
        if primary.name == "双顶风险" and feature_snapshot.neckline_level is not None:
            support_levels = self._unique_prices([feature_snapshot.neckline_level, *base_support_levels])
        elif primary.name == "三角收敛" and triangle_structure is not None:
            support_levels = self._unique_prices([triangle_structure["projected_lower"], *base_support_levels])
        elif primary.name == "旗形中继" and feature_snapshot.flag_face_low is not None:
            support_levels = self._unique_prices([
                feature_snapshot.flag_face_low,
                feature_snapshot.ma20,
                feature_snapshot.ma60,
            ])
        else:
            support_levels = base_support_levels
        if primary.name == "双底修复" and feature_snapshot.neckline_level is not None:
            pressure_levels = self._unique_prices([feature_snapshot.neckline_level, *base_pressure_levels])
        elif primary.name == "三角收敛" and triangle_structure is not None:
            pressure_levels = self._unique_prices([triangle_structure["projected_upper"], *base_pressure_levels])
        elif primary.name == "旗形中继" and feature_snapshot.flag_face_high is not None:
            pressure_levels = self._unique_prices([
                feature_snapshot.flag_face_high,
                feature_snapshot.flag_pole_high,
                feature_snapshot.range60_high,
            ])
        else:
            pressure_levels = base_pressure_levels
        if primary.name in {"双底修复", "双顶风险"} and feature_snapshot.neckline_level is not None:
            breakout_level = round(feature_snapshot.neckline_level, 2)
        elif primary.name == "三角收敛" and triangle_structure is not None:
            breakout_level = triangle_structure["projected_upper"]
        elif primary.name == "旗形中继" and feature_snapshot.flag_face_high is not None:
            breakout_level = feature_snapshot.flag_face_high
        else:
            breakout_level = pressure_levels[0] if pressure_levels else None
        if primary.name == "三角收敛" and triangle_structure is not None:
            defense_level = triangle_structure["projected_lower"]
        elif primary.name == "旗形中继" and feature_snapshot.flag_face_low is not None:
            defense_level = feature_snapshot.flag_face_low
        else:
            defense_level = support_levels[0] if support_levels else None
        key_annotations = self._build_key_annotations(
            feature_snapshot,
            target_input,
            history_rows,
            primary.name,
            breakout_level,
            defense_level,
        )
        invalid_if = self._build_invalid_if(primary.name, defense_level, breakout_level)
        pattern_summary = primary.summary or "当前更适合围绕关键位观察。"
        rationale = "；".join(primary.rule_hits[:3]) if primary.rule_hits else "以价格位置、均线关系和区间结构做保守判断。"
        execution_hint = self._build_execution_hint(primary.name, breakout_level, defense_level)
        risk_hint = self._build_risk_hint(primary.name, target_scored, primary.conflict_points)
        return StockPatternResult(
            primary_pattern=primary.name,
            secondary_patterns=[item.name for item in candidates[1:]],
            confidence=primary.confidence or self._score_confidence(primary.score),
            pattern_phase=primary.phase or "待确认",
            pattern_summary=pattern_summary,
            pattern_rationale=rationale,
            execution_hint=execution_hint,
            risk_hint=risk_hint,
            support_levels=support_levels,
            pressure_levels=pressure_levels,
            breakout_level=breakout_level,
            defense_level=defense_level,
            invalid_if=invalid_if,
            key_annotations=key_annotations,
            candidates=candidates,
        )

    def _build_chart_payload(
        self,
        history_rows: List[Dict],
        feature_snapshot: StockPatternFeatureSnapshot,
        pattern_result: StockPatternResult,
    ) -> StockPatternChartPayload:
        rows = history_rows[-100:]
        closes = [self._safe_float(row.get("close")) or 0 for row in rows]
        candles = [
            StockPatternCandle(
                trade_date=self._format_trade_date(str(row.get("trade_date") or "")),
                open=round(self._safe_float(row.get("open")) or 0, 2),
                high=round(self._safe_float(row.get("high")) or 0, 2),
                low=round(self._safe_float(row.get("low")) or 0, 2),
                close=round(self._safe_float(row.get("close")) or 0, 2),
                volume=self._safe_float(row.get("vol")) or self._safe_float(row.get("volume")),
            )
            for row in rows
        ]
        moving_averages = {
            "ma5": self._moving_average_series(closes, 5),
            "ma10": self._moving_average_series(closes, 10),
            "ma20": self._moving_average_series(closes, 20),
            "ma60": self._moving_average_series(closes, 60),
        }
        upper_label, lower_label = self._pattern_boundary_labels(pattern_result.primary_pattern)
        triangle_structure = self._triangle_structure(rows) if pattern_result.primary_pattern == "三角收敛" else None
        price_lines: List[StockPatternLine] = []
        for index, price in enumerate(pattern_result.pressure_levels[:2]):
            price_lines.append(
                StockPatternLine(
                    label=upper_label if index == 0 and upper_label else "压力位",
                    line_type="pressure",
                    price=price,
                )
            )
        for index, price in enumerate(pattern_result.support_levels[:2]):
            price_lines.append(
                StockPatternLine(
                    label=lower_label if index == 0 and lower_label else "支撑位",
                    line_type="support",
                    price=price,
                )
            )
        if pattern_result.primary_pattern == "三角收敛" and triangle_structure is not None:
            price_lines = [
                StockPatternLine(
                    label="收敛上沿",
                    line_type="pressure",
                    price=triangle_structure["projected_upper"],
                    start_trade_date=triangle_structure["upper_points"][0]["trade_date"],
                    end_trade_date=rows[-1] and self._format_trade_date(str(rows[-1].get("trade_date") or "")),
                    start_price=triangle_structure["upper_points"][0]["price"],
                    end_price=triangle_structure["projected_upper"],
                ),
                StockPatternLine(
                    label="收敛下沿",
                    line_type="support",
                    price=triangle_structure["projected_lower"],
                    start_trade_date=triangle_structure["lower_points"][0]["trade_date"],
                    end_trade_date=rows[-1] and self._format_trade_date(str(rows[-1].get("trade_date") or "")),
                    start_price=triangle_structure["lower_points"][0]["price"],
                    end_price=triangle_structure["projected_lower"],
                ),
            ]
        if pattern_result.breakout_level is not None:
            breakout_exists = any(
                line.line_type == "pressure" and abs(line.price - pattern_result.breakout_level) <= 0.01
                for line in price_lines
            )
            if not breakout_exists:
                price_lines.append(
                    StockPatternLine(
                        label="颈线" if pattern_result.primary_pattern in {"双底修复", "双顶风险"} else "突破线",
                        line_type="breakout",
                        price=pattern_result.breakout_level,
                    )
                )
        if pattern_result.defense_level is not None:
            defense_exists = any(
                line.line_type == "support" and abs(line.price - pattern_result.defense_level) <= 0.01
                for line in price_lines
            )
            if not defense_exists:
                price_lines.append(
                    StockPatternLine(label="防守线", line_type="defense", price=pattern_result.defense_level)
                )

        zones: List[StockPatternZone] = []
        if feature_snapshot.platform_upper and feature_snapshot.platform_lower and candles:
            start_trade_date = candles[max(0, len(candles) - 20)].trade_date
            end_trade_date = candles[-1].trade_date
            zones.append(
                StockPatternZone(
                    label="平台区",
                    zone_type="platform",
                    start_trade_date=start_trade_date,
                    end_trade_date=end_trade_date,
                    low_price=feature_snapshot.platform_lower,
                    high_price=feature_snapshot.platform_upper,
                )
            )
        if (
            feature_snapshot.neckline_level is not None
            and pattern_result.primary_pattern in {"双顶风险", "双底修复"}
            and candles
        ):
            zones.append(
                StockPatternZone(
                    label="颈线观察区",
                    zone_type="neckline",
                    start_trade_date=candles[max(0, len(candles) - 30)].trade_date,
                    end_trade_date=candles[-1].trade_date,
                    low_price=round(feature_snapshot.neckline_level * 0.995, 2),
                    high_price=round(feature_snapshot.neckline_level * 1.005, 2),
                )
            )
        return StockPatternChartPayload(
            candles=candles,
            moving_averages=moving_averages,
            price_lines=price_lines,
            zones=zones,
            annotations=pattern_result.key_annotations,
            default_window=min(100, len(candles) or 100),
        )

    def _merge_llm_result(self, rule_result: StockPatternResult, llm_result: Dict) -> StockPatternResult:
        merged = rule_result.model_copy(deep=True)
        merged.primary_pattern = str(llm_result.get("primary_pattern") or merged.primary_pattern)
        merged.secondary_patterns = [
            str(item).strip() for item in (llm_result.get("secondary_patterns") or merged.secondary_patterns)
            if str(item or "").strip()
        ]
        merged.confidence = str(llm_result.get("confidence") or merged.confidence)
        merged.pattern_phase = str(llm_result.get("pattern_phase") or merged.pattern_phase)
        merged.pattern_summary = str(llm_result.get("pattern_summary") or merged.pattern_summary)
        merged.pattern_rationale = str(llm_result.get("pattern_rationale") or merged.pattern_rationale)
        merged.execution_hint = str(llm_result.get("execution_hint") or merged.execution_hint)
        merged.risk_hint = str(llm_result.get("risk_hint") or merged.risk_hint)
        merged.invalid_if = str(llm_result.get("invalid_if") or merged.invalid_if)
        return merged

    def _build_key_annotations(
        self,
        feature_snapshot: StockPatternFeatureSnapshot,
        target_input,
        history_rows: List[Dict],
        pattern_name: str,
        breakout_level: Optional[float],
        defense_level: Optional[float],
    ) -> List[StockPatternAnnotation]:
        annotations: List[StockPatternAnnotation] = []
        quote_time = self._extract_trade_date(target_input.quote_time)
        swing_high_points = self._swing_points(history_rows, mode="high")
        swing_low_points = self._swing_points(history_rows, mode="low")
        upper_label, lower_label = self._pattern_boundary_labels(pattern_name)
        triangle_structure = self._triangle_structure(history_rows) if pattern_name == "三角收敛" else None

        if breakout_level is not None and pattern_name != "三角收敛":
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=breakout_level,
                    label="颈线" if pattern_name in {"双底修复", "双顶风险"} else "突破线",
                    annotation_type="neckline" if pattern_name in {"双底修复", "双顶风险"} else "breakout",
                )
            )
        if defense_level is not None and pattern_name != "三角收敛":
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=defense_level,
                    label="防守线",
                    annotation_type="defense",
                )
            )
        if pattern_name == "三角收敛" and triangle_structure is not None:
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=triangle_structure["projected_upper"],
                    label="收敛上沿",
                    annotation_type="pattern_upper",
                )
            )
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=triangle_structure["projected_lower"],
                    label="收敛下沿",
                    annotation_type="pattern_lower",
                )
            )
        elif upper_label and feature_snapshot.platform_upper is not None:
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=feature_snapshot.platform_upper,
                    label=upper_label,
                    annotation_type="pattern_upper",
                )
            )
        if lower_label and feature_snapshot.platform_lower is not None and pattern_name != "三角收敛":
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=feature_snapshot.platform_lower,
                    label=lower_label,
                    annotation_type="pattern_lower",
                )
            )

        if pattern_name == "双底修复" and len(swing_low_points) >= 2:
            left_low, right_low = swing_low_points[-2], swing_low_points[-1]
            annotations.extend(
                [
                    StockPatternAnnotation(
                        trade_date=left_low["trade_date"],
                        price=left_low["price"],
                        label="左底",
                        annotation_type="left_bottom",
                    ),
                    StockPatternAnnotation(
                        trade_date=right_low["trade_date"],
                        price=right_low["price"],
                        label="右底",
                        annotation_type="right_bottom",
                    ),
                ]
            )
            neckline_point = self._neckline_point_between(history_rows, left_low["index"], right_low["index"], mode="double_bottom")
            if neckline_point is not None:
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=neckline_point["trade_date"],
                        price=neckline_point["price"],
                        label="颈线",
                        annotation_type="neckline",
                    )
                )
        elif pattern_name == "双顶风险" and len(swing_high_points) >= 2:
            left_high, right_high = swing_high_points[-2], swing_high_points[-1]
            annotations.extend(
                [
                    StockPatternAnnotation(
                        trade_date=left_high["trade_date"],
                        price=left_high["price"],
                        label="左顶",
                        annotation_type="left_top",
                    ),
                    StockPatternAnnotation(
                        trade_date=right_high["trade_date"],
                        price=right_high["price"],
                        label="右顶",
                        annotation_type="right_top",
                    ),
                ]
            )
            neckline_point = self._neckline_point_between(history_rows, left_high["index"], right_high["index"], mode="double_top")
            if neckline_point is not None:
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=neckline_point["trade_date"],
                        price=neckline_point["price"],
                        label="颈线",
                        annotation_type="neckline",
                    )
                )
        elif pattern_name == "三角收敛":
            triangle_high_points = swing_high_points[-2:]
            triangle_low_points = swing_low_points[-2:]
            if len(triangle_high_points) < 2 or len(triangle_low_points) < 2:
                fallback_high_points, fallback_low_points = self._triangle_anchor_points(history_rows)
                if len(triangle_high_points) < 2:
                    triangle_high_points = fallback_high_points
                if len(triangle_low_points) < 2:
                    triangle_low_points = fallback_low_points
            if len(triangle_high_points) >= 2:
                left_high, right_high = triangle_high_points[-2], triangle_high_points[-1]
                annotations.extend(
                    [
                        StockPatternAnnotation(
                            trade_date=left_high["trade_date"],
                            price=left_high["price"],
                            label="左高点",
                            annotation_type="left_top",
                        ),
                        StockPatternAnnotation(
                            trade_date=right_high["trade_date"],
                            price=right_high["price"],
                            label="右高点",
                            annotation_type="right_top",
                        ),
                    ]
                )
            if len(triangle_low_points) >= 2:
                left_low, right_low = triangle_low_points[-2], triangle_low_points[-1]
                annotations.extend(
                    [
                        StockPatternAnnotation(
                            trade_date=left_low["trade_date"],
                            price=left_low["price"],
                            label="左低点",
                            annotation_type="left_bottom",
                        ),
                        StockPatternAnnotation(
                            trade_date=right_low["trade_date"],
                            price=right_low["price"],
                            label="右低点",
                            annotation_type="right_bottom",
                        ),
                    ]
                )
        else:
            if swing_high_points:
                last_high = swing_high_points[-1]
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=last_high["trade_date"],
                        price=last_high["price"],
                        label="波段高点",
                        annotation_type="swing_high",
                    )
                )
            if swing_low_points:
                last_low = swing_low_points[-1]
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=last_low["trade_date"],
                        price=last_low["price"],
                        label="波段低点",
                        annotation_type="swing_low",
                    )
                )
        if (
            feature_snapshot.neckline_level is not None
            and pattern_name not in {"双底修复", "双顶风险"}
        ):
            annotations.append(
                StockPatternAnnotation(
                    trade_date=quote_time,
                    price=feature_snapshot.neckline_level,
                    label="颈线",
                    annotation_type="neckline",
                )
            )
        deduped: List[StockPatternAnnotation] = []
        seen = set()
        for item in annotations:
            key = (item.label, item.trade_date, round(item.price, 2))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:8]

    def _triangle_anchor_points(self, history_rows: List[Dict]) -> tuple[List[Dict], List[Dict]]:
        if len(history_rows) < 12:
            return [], []
        window = history_rows[-24:] if len(history_rows) >= 24 else history_rows[:]
        start_offset = max(0, len(history_rows) - len(window))
        midpoint = max(4, len(window) // 2)
        left_segment = window[:midpoint]
        right_segment = window[midpoint:]
        high_points = [
            self._segment_extreme_point(left_segment, mode="high", offset=start_offset),
            self._segment_extreme_point(right_segment, mode="high", offset=start_offset + midpoint),
        ]
        low_points = [
            self._segment_extreme_point(left_segment, mode="low", offset=start_offset),
            self._segment_extreme_point(right_segment, mode="low", offset=start_offset + midpoint),
        ]
        return [item for item in high_points if item], [item for item in low_points if item]

    def _segment_extreme_point(self, rows: List[Dict], *, mode: str, offset: int = 0) -> Optional[Dict]:
        if not rows:
            return None
        field = "high" if mode == "high" else "low"
        chosen_row = None
        chosen_price = None
        chosen_index = None
        for index, row in enumerate(rows):
            value = self._safe_float(row.get(field))
            if value is None:
                continue
            if chosen_price is None:
                chosen_price = value
                chosen_row = row
                chosen_index = index
                continue
            if mode == "high" and value > chosen_price:
                chosen_price = value
                chosen_row = row
                chosen_index = index
            if mode == "low" and value < chosen_price:
                chosen_price = value
                chosen_row = row
                chosen_index = index
        if chosen_row is None or chosen_price is None or chosen_index is None:
            return None
        return {
            "index": chosen_index + offset,
            "trade_date": self._format_trade_date(str(chosen_row.get("trade_date") or "")),
            "price": round(chosen_price, 2),
        }

    def _triangle_structure(self, history_rows: List[Dict]) -> Optional[Dict]:
        swing_high_points = self._swing_points(history_rows, mode="high")
        swing_low_points = self._swing_points(history_rows, mode="low")
        upper_points = swing_high_points[-2:]
        lower_points = swing_low_points[-2:]
        if len(upper_points) < 2 or len(lower_points) < 2:
            fallback_high_points, fallback_low_points = self._triangle_anchor_points(history_rows)
            if len(upper_points) < 2:
                upper_points = fallback_high_points[-2:]
            if len(lower_points) < 2:
                lower_points = fallback_low_points[-2:]
        if len(upper_points) < 2 or len(lower_points) < 2:
            return None

        # 判断对称/上升/下降三角
        upper_change_pct = (upper_points[1]["price"] - upper_points[0]["price"]) / max(upper_points[0]["price"], 0.01) * 100
        lower_change_pct = (lower_points[1]["price"] - lower_points[0]["price"]) / max(lower_points[0]["price"], 0.01) * 100
        is_descending_highs = upper_change_pct <= -1.0   # 高点下移 ≥1%
        is_rising_lows = lower_change_pct >= 1.0          # 低点上移 ≥1%

        # 至少一个方向收敛；且另一侧不能明显反向（否则是趋势而非三角）
        if not is_descending_highs and not is_rising_lows:
            return None
        if not is_descending_highs and upper_change_pct > 2.0:  # 顶部明显上扬 = 趋势，非三角
            return None
        if not is_rising_lows and lower_change_pct < -2.0:      # 底部明显下移 = 趋势，非三角
            return None

        target_index = len(history_rows) - 1
        # 收敛侧做线性投影，平坦侧用第二个点价格作为水平延伸
        if is_descending_highs:
            projected_upper = self._project_line_price(upper_points[0], upper_points[1], target_index)
        else:
            projected_upper = round(upper_points[1]["price"], 2)
        if is_rising_lows:
            projected_lower = self._project_line_price(lower_points[0], lower_points[1], target_index)
        else:
            projected_lower = round(lower_points[1]["price"], 2)

        initial_gap = upper_points[0]["price"] - lower_points[0]["price"]
        current_gap = projected_upper - projected_lower
        if initial_gap <= 0 or current_gap <= 0:
            return None
        if current_gap >= initial_gap:
            return None

        if is_descending_highs and is_rising_lows:
            triangle_type = "对称三角"
        elif is_rising_lows:
            triangle_type = "上升三角"
        else:
            triangle_type = "下降三角"

        return {
            "upper_points": upper_points,
            "lower_points": lower_points,
            "projected_upper": projected_upper,
            "projected_lower": projected_lower,
            "initial_gap_pct": round(initial_gap / max(lower_points[0]["price"], 0.01) * 100, 2),
            "current_gap_pct": round(current_gap / max(projected_lower, 0.01) * 100, 2),
            "triangle_type": triangle_type,
        }

    def _project_line_price(self, left_point: Dict, right_point: Dict, target_index: int) -> float:
        left_index = int(left_point["index"])
        right_index = int(right_point["index"])
        left_price = float(left_point["price"])
        right_price = float(right_point["price"])
        if right_index == left_index:
            return round(right_price, 2)
        slope = (right_price - left_price) / (right_index - left_index)
        projected_price = right_price + slope * (target_index - right_index)
        return round(projected_price, 2)

    def _pattern_boundary_labels(self, pattern_name: str) -> tuple[Optional[str], Optional[str]]:
        if pattern_name in {"平台整理", "平台突破临界"}:
            return "平台上沿", "平台下沿"
        if pattern_name == "箱体震荡":
            return "箱体上沿", "箱体下沿"
        if pattern_name == "三角收敛":
            return "收敛上沿", "收敛下沿"
        if pattern_name == "旗形中继":
            return "旗面上沿", "旗面下沿"
        return None, None

    def _build_invalid_if(self, pattern_name: str, defense_level: Optional[float], breakout_level: Optional[float]) -> str:
        if defense_level is not None:
            return f"有效跌破 {defense_level:.2f} 并且收不回，当前形态语义明显转弱。"
        if breakout_level is not None:
            return f"冲击 {breakout_level:.2f} 后不能站稳，当前形态需要降级为观察。"
        if pattern_name == "未识别明确形态":
            return "关键位失守后不要继续脑补新形态。"
        return "关键均线和区间低点失守后，需要重新评估。"

    def _build_execution_hint(self, pattern_name: str, breakout_level: Optional[float], defense_level: Optional[float]) -> str:
        if pattern_name == "平台突破临界" and breakout_level is not None:
            return f"先盯 {breakout_level:.2f} 一线是否放量站稳，确认前不要把临界态当成已突破。"
        if pattern_name in {"箱体震荡", "三角收敛"} and breakout_level is not None and defense_level is not None:
            return f"先看 {defense_level:.2f}-{breakout_level:.2f} 这段边界怎么选方向，区间内更适合等确认。"
        if pattern_name in {"回踩确认", "双底修复"} and defense_level is not None:
            return f"先看 {defense_level:.2f} 附近承接是否有效，再决定修复能否升级。"
        if pattern_name in {"旗形中继", "V形修复", "圆弧底修复"} and breakout_level is not None:
            return f"下一步重点看 {breakout_level:.2f} 一线能否被有效收复或突破，修复类形态不能只看反弹速度。"
        if pattern_name == "假突破/突破失败" and defense_level is not None:
            return f"先别把上冲当成新趋势，重点看回落后 {defense_level:.2f} 一线是否还能守住。"
        if pattern_name == "双顶风险":
            return "优先观察高位回落后的承接质量，不把二次冲高自动等同于再起一波。"
        if pattern_name == "下跌通道反抽" and breakout_level is not None:
            return f"反抽先看 {breakout_level:.2f} 附近是否遇压，不站回关键均线前不要把它当成趋势反转。"
        return "先围绕关键位处理，不提前预设走势。"

    def _build_risk_hint(
        self,
        pattern_name: str,
        target_scored: StockOutput,
        conflict_points: List[str],
    ) -> str:
        risk_bits = []
        if target_scored.stock_tradeability_tag.value == "不建议":
            risk_bits.append("当前交易性偏弱，形态再好也不该脱离环境单看。")
        if conflict_points:
            risk_bits.append(conflict_points[0])
        if pattern_name == "未识别明确形态":
            risk_bits.append("现在最容易犯的错，是把普通震荡硬解释成确定性形态。")
        if pattern_name == "假突破/突破失败":
            risk_bits.append("最容易误判的点，是把一次冲高误读成已经完成突破。")
        if pattern_name == "下跌通道反抽":
            risk_bits.append("最容易误判的点，是把弱势反抽直接当成主升起点。")
        return "；".join(risk_bits[:2]) or "最主要的风险，是形态边界还不够硬。"

    def _ma_alignment(
        self,
        price: float,
        ma5: Optional[float],
        ma10: Optional[float],
        ma20: Optional[float],
        ma60: Optional[float],
    ) -> str:
        levels = [value for value in (ma5, ma10, ma20, ma60) if value is not None]
        if not levels:
            return "均线关系待确认"
        if ma5 and ma10 and ma20 and ma60 and price >= ma5 >= ma10 >= ma20 >= ma60:
            return "多头排列"
        if ma5 and ma10 and ma20 and price >= ma10 >= ma20:
            return "中短均线偏多"
        if ma20 and ma60 and price < ma20 < ma60:
            return "均线压制"
        return "均线纠缠"

    def _ma_slope(self, closes: List[float], window: int, lookback: int) -> Optional[float]:
        if len(closes) < window + lookback:
            return None
        prev = stock_checkup_service._calc_ma(closes[:-lookback], window)
        latest = stock_checkup_service._calc_ma(closes, window)
        if prev is None or latest is None or prev == 0:
            return None
        return round((latest - prev) / prev * 100, 2)

    def _avg(self, values: List[Optional[float]]) -> Optional[float]:
        valid = [float(value) for value in values if value is not None]
        if not valid:
            return None
        return sum(valid) / len(valid)

    def _amplitude_pct(self, high: Optional[float], low: Optional[float]) -> Optional[float]:
        if high is None or low is None or low <= 0 or high < low:
            return None
        return round((high - low) / low * 100, 2)

    def _center_shift_pct(self, previous: List[float], current: List[float]) -> Optional[float]:
        if not previous or not current:
            return None
        prev_avg = sum(previous) / len(previous)
        current_avg = sum(current) / len(current)
        if prev_avg == 0:
            return None
        return round((current_avg - prev_avg) / prev_avg * 100, 2)

    def _volume_pattern(
        self,
        latest_volume: Optional[float],
        avg_volume_5: Optional[float],
        vol_ratio: Optional[float],
    ) -> str:
        if vol_ratio and float(vol_ratio) >= 2:
            return "明显放量"
        if latest_volume and avg_volume_5 and latest_volume >= avg_volume_5 * 1.3:
            return "温和放量"
        if latest_volume and avg_volume_5 and latest_volume <= avg_volume_5 * 0.85:
            return "缩量"
        return "量能中性"

    def _candle_bias(self, target_input) -> str:
        close_quality = stock_checkup_service._close_quality(target_input)
        latest_change = float(target_input.change_pct or 0)
        if latest_change >= 3 and close_quality >= 0.68:
            return "强阳靠高收"
        if latest_change >= 0 and close_quality >= 0.5:
            return "偏强收盘"
        if close_quality < 0.35:
            return "冲高回落"
        return "中性K线"

    def _swing_points(self, history_rows: List[Dict], *, mode: str) -> List[Dict]:
        if len(history_rows) < 5:
            return []
        field = "high" if mode == "high" else "low"
        points: List[Dict] = []
        for index in range(2, len(history_rows) - 2):
            current = self._safe_float(history_rows[index].get(field))
            if current is None:
                continue
            window = [
                self._safe_float(history_rows[window_index].get(field))
                for window_index in range(index - 2, index + 3)
            ]
            valid_window = [value for value in window if value is not None]
            if len(valid_window) < 5:
                continue
            is_swing = (mode == "high" and current == max(valid_window)) or (mode == "low" and current == min(valid_window))
            if not is_swing:
                continue
            rounded = round(current, 2)
            if points and abs(points[-1]["price"] - rounded) / max(rounded, 0.01) <= 0.015:
                continue
            points.append(
                {
                    "index": index,
                    "trade_date": self._format_trade_date(str(history_rows[index].get("trade_date") or "")),
                    "price": rounded,
                }
            )
        return points[-5:]

    def _swing_levels(self, values: List[float], *, mode: str) -> List[float]:
        if len(values) < 5:
            return []
        result: List[float] = []
        for index in range(2, len(values) - 2):
            current = values[index]
            window = values[index - 2:index + 3]
            if mode == "high" and current == max(window):
                rounded = round(current, 2)
                if not result or abs(result[-1] - rounded) / max(rounded, 0.01) > 0.015:
                    result.append(rounded)
            if mode == "low" and current == min(window):
                rounded = round(current, 2)
                if not result or abs(result[-1] - rounded) / max(rounded, 0.01) > 0.015:
                    result.append(rounded)
        return result[-3:]

    def _neckline_point_between(self, history_rows: List[Dict], left_index: int, right_index: int, *, mode: str) -> Optional[Dict]:
        if left_index >= right_index - 1:
            return None
        segment = history_rows[left_index + 1:right_index]
        if not segment:
            return None
        field = "high" if mode == "double_bottom" else "low"
        best_row = None
        best_price = None
        for row in segment:
            value = self._safe_float(row.get(field))
            if value is None:
                continue
            if best_price is None:
                best_price = value
                best_row = row
                continue
            if mode == "double_bottom" and value > best_price:
                best_price = value
                best_row = row
            if mode == "double_top" and value < best_price:
                best_price = value
                best_row = row
        if best_row is None or best_price is None:
            return None
        return {
            "trade_date": self._format_trade_date(str(best_row.get("trade_date") or "")),
            "price": round(best_price, 2),
        }

    def _estimate_neckline(
        self,
        history_rows: List[Dict],
        swing_high_points: List[Dict],
        swing_low_points: List[Dict],
    ) -> Optional[float]:
        if len(swing_low_points) >= 2:
            neckline_point = self._neckline_point_between(
                history_rows,
                swing_low_points[-2]["index"],
                swing_low_points[-1]["index"],
                mode="double_bottom",
            )
            if neckline_point is not None:
                return neckline_point["price"]
        if len(swing_high_points) >= 2:
            neckline_point = self._neckline_point_between(
                history_rows,
                swing_high_points[-2]["index"],
                swing_high_points[-1]["index"],
                mode="double_top",
            )
            if neckline_point is not None:
                return neckline_point["price"]
        return None

    def _flag_structure(self, history_rows: List[Dict]) -> Optional[Dict]:
        """检测旗形结构：旗杆（快速集中拉升）+ 旗面（缩幅整理回调）。

        核心约束：
        1. 旗杆顶点必须是波段高点（swing high），不接受任意 K 线
        2. 旗杆起点必须是旗杆顶之前的波段低点（swing low），且距离 ≤ 20 根
        3. 旗杆效率：平均每根 K 线涨幅 ≥ 1%（避免缓慢漂移被误判）
        4. 旗杆最小涨幅 15%（提高门槛）
        5. 旗面回调 ≤ 旗杆涨幅的 55%（收敛整理，不是深度回调）
        6. 旗面振幅 < 旗杆涨幅的 80%（振幅收敛）
        """
        if len(history_rows) < 30:
            return None
        closes = [self._safe_float(row.get("close")) for row in history_rows]
        closes = [c for c in closes if c is not None]
        if len(closes) < 30:
            return None

        search_window = min(80, len(closes))
        tail_rows = history_rows[-search_window:]
        sc = closes[-search_window:]
        n = len(sc)
        current_price = sc[-1]

        swing_highs = self._swing_points(tail_rows, mode="high")
        swing_lows = self._swing_points(tail_rows, mode="low")

        best_result = None
        best_score = 0.0

        for sh in swing_highs:
            pole_end = sh["index"]
            pole_end_price = sh["price"]

            # 旗杆顶点需在 [5, n-5) 范围内，后面留足旗面空间
            if pole_end < 5 or pole_end >= n - 5:
                continue

            # 在旗杆顶点之前找最近的波段低点作为旗杆起点（距离 ≤ 20 根）
            pole_start_sl = None
            for sl in reversed(swing_lows):
                gap = pole_end - sl["index"]
                if 3 <= gap <= 20:
                    pole_start_sl = sl
                    break
            if pole_start_sl is None:
                continue

            pole_start_price = pole_start_sl["price"]
            pole_bars = pole_end - pole_start_sl["index"]
            if pole_start_price <= 0 or pole_bars <= 0:
                continue

            pole_gain_pct = (pole_end_price - pole_start_price) / pole_start_price * 100

            # 约束1：最小旗杆涨幅 15%
            if pole_gain_pct < 15:
                continue

            # 约束2：旗杆效率 ≥ 1% / 根（拒绝缓慢漂移）
            if pole_gain_pct / pole_bars < 1.0:
                continue

            # 旗面段：旗杆顶点之后，直到收盘再次站上旗杆顶或末尾
            flag_face_end = n
            for j in range(pole_end + 1, n):
                if sc[j] >= pole_end_price * 1.005:
                    flag_face_end = j
                    break
            flag_segment = sc[pole_end:flag_face_end]
            if len(flag_segment) < 3:
                continue

            flag_low = min(flag_segment)
            flag_high = max(flag_segment)

            # 约束3：旗面回调 ≤ 旗杆涨幅的 55%
            pullback_pct = (pole_end_price - flag_low) / pole_end_price * 100
            if pullback_pct > pole_gain_pct * 0.55:
                continue

            # 约束4：当前价未跌回旗杆起点
            if current_price < pole_start_price * 0.97:
                continue

            # 约束5：旗面振幅 < 旗杆涨幅的 80%
            flag_amplitude_pct = (flag_high - flag_low) / max(flag_low, 0.01) * 100
            if flag_amplitude_pct >= pole_gain_pct * 0.80:
                continue

            score = pole_gain_pct - pullback_pct * 0.4
            if score > best_score:
                best_score = score
                best_result = {
                    "pole_start_price": round(pole_start_price, 2),
                    "pole_end_price": round(pole_end_price, 2),
                    "pole_gain_pct": round(pole_gain_pct, 1),
                    "pullback_pct": round(pullback_pct, 1),
                    "flag_high": round(flag_high, 2),
                    "flag_low": round(flag_low, 2),
                    "flag_amplitude_pct": round(flag_amplitude_pct, 1),
                }

        return best_result

    def _estimate_platform(self, highs: List[float], lows: List[float]) -> tuple[Optional[float], Optional[float]]:
        if len(highs) < 20 or len(lows) < 20:
            return None, None
        recent_highs = highs[-20:]
        recent_lows = lows[-20:]
        upper = round(sum(sorted(recent_highs, reverse=True)[:3]) / 3, 2)
        lower = round(sum(sorted(recent_lows)[:3]) / 3, 2)
        if lower <= 0 or upper <= lower:
            return None, None
        if (upper - lower) / lower * 100 > 18:
            return None, None
        return upper, lower

    def _score_confidence(self, score: float) -> str:
        if score >= 0.75:
            return "高"
        if score >= 0.55:
            return "中"
        return "低"

    def _moving_average_series(self, closes: List[float], window: int) -> List[Optional[float]]:
        series: List[Optional[float]] = []
        for index in range(len(closes)):
            if index + 1 < window:
                series.append(None)
                continue
            value = sum(closes[index - window + 1:index + 1]) / window
            series.append(round(value, 2))
        return series

    def _unique_prices(self, values: List[Optional[float]]) -> List[float]:
        result: List[float] = []
        for value in values:
            if value is None:
                continue
            rounded = round(float(value), 2)
            if rounded <= 0:
                continue
            if rounded not in result:
                result.append(rounded)
        return result

    def _safe_float(self, value) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _extract_trade_date(self, quote_time: Optional[str]) -> Optional[str]:
        raw = str(quote_time or "").strip()
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10]
        return None

    def _format_trade_date(self, trade_date: str) -> str:
        raw = str(trade_date or "")
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw


pattern_analysis_service = PatternAnalysisService()
