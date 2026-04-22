"""
股票形态分析服务
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

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

        # 盘中时段：将今日（可能已被 Tushare 提前写入的不完整日线）从历史序列中剔除，
        # 确保形态判断完全基于已完结的 K 线。
        if market_data_gateway._should_use_realtime_quote(trade_date):
            today_compact = str(trade_date).replace("-", "")[:8]
            history_rows = [
                r for r in history_rows
                if str(r.get("trade_date") or "").replace("-", "")[:8] != today_compact
            ]

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

        today_candle, latest_price, latest_change_pct = self._resolve_today_candle(
            normalized_code, trade_date, history_rows, target_input=target_input
        )

        return StockPatternAnalysisResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date or context.resolved_stock_trade_date or trade_date,
            basic_info=basic_info,
            feature_snapshot=feature_snapshot,
            chart_payload=chart_payload,
            pattern_analysis=rule_result,
            llm_status=llm_status,
            latest_price=latest_price,
            latest_change_pct=latest_change_pct,
            today_candle=today_candle,
        )

    def _resolve_today_candle(
        self,
        ts_code: str,
        trade_date: str,
        history_rows: List[Dict],
        *,
        target_input=None,
    ):
        """
        返回 (today_candle, latest_price, latest_change_pct)。

        优先从 target_input（已经过实时价格覆盖）读取当日 OHLC：
        - 若 data_source 包含 "realtime" 或历史序列末尾不含今日日期，则构造虚 K 线。
        盘后或数据不足则 today_candle=None，latest_price 取最近历史收盘。
        """
        # 获取今日日期字符串（YYYY-MM-DD）
        today_str = self._format_trade_date(str(trade_date).replace("-", "")[:8])

        # 历史序列最新日期
        last_hist_date = self._format_trade_date(
            str(history_rows[-1].get("trade_date") or "")
        ) if history_rows else ""

        try:
            if market_data_gateway._should_use_realtime_quote(trade_date):
                # 优先从已做实时覆盖的 target_input 读取（避免重复 API 调用）
                # 但必须确认 data_source 是实时来源，否则值是历史日线的
                data_src = str(getattr(target_input, "data_source", "") or "") if target_input else ""
                ti_is_realtime = "realtime" in data_src

                ohlc: Optional[Dict] = None
                if ti_is_realtime and target_input is not None:
                    price = float(target_input.close or 0)
                    if price > 0:
                        op = float(target_input.open or price)
                        hi = float(target_input.high or price)
                        lo = float(target_input.low or price)
                        change_pct_raw = float(target_input.change_pct or 0)
                        vol_raw = float(getattr(target_input, "volume", 0) or 0)
                        vol_lots = vol_raw / 100  # 实时接口返回股数，转为手
                        ohlc = {
                            "trade_date": today_str,
                            "open":   round(op, 2),
                            "high":   round(hi, 2),
                            "low":    round(lo, 2),
                            "close":  round(price, 2),
                            "change_pct": round(change_pct_raw, 2),
                            "volume": round(vol_lots, 2),
                        }
                    logger.debug(f"[虚K线] {ts_code} ti_is_realtime={ti_is_realtime} price={price} ohlc={ohlc}")

                # 若 target_input 不是实时数据，直接拉实时报价接口
                if ohlc is None:
                    quote_map = market_data_gateway._fetch_realtime_quote_map([ts_code])
                    q = quote_map.get(ts_code) or {}
                    price = float(q.get("close") or 0)
                    logger.debug(f"[虚K线] {ts_code} fallback realtime price={price} q={q}")
                    if price > 0:
                        vol_raw = float(q.get("volume") or 0)
                        vol_lots = vol_raw / 100  # 实时接口返回股数，转为手
                        ohlc = {
                            "trade_date": today_str,
                            "open":   round(float(q.get("open") or price), 2),
                            "high":   round(float(q.get("high") or price), 2),
                            "low":    round(float(q.get("low") or price), 2),
                            "close":  round(price, 2),
                            "change_pct": round(float(q.get("change_pct") or 0), 2),
                            "volume": round(vol_lots, 2),
                        }

                logger.debug(f"[虚K线] {ts_code} ohlc={ohlc} today_str={today_str} last_hist_date={last_hist_date}")
                if ohlc and ohlc.get("close", 0) > 0:
                    change_pct = ohlc["change_pct"]
                    fmt_date = ohlc["trade_date"]
                    price = ohlc["close"]
                    if fmt_date != last_hist_date:
                        # 今日不在历史序列 → 追加虚 K 线
                        return ohlc, price, change_pct
                    else:
                        # 今日已在历史序列 → 仅返回最新价
                        return None, price, change_pct
        except Exception as e:
            logger.warning(f"[虚K线] {ts_code} exception: {e}", exc_info=True)

        # 盘后/无实时数据：latest_price 取最近历史收盘，不补虚 K 线
        if history_rows:
            last = history_rows[-1]
            close = float(last.get("close") or 0)
            pre_close = float(last.get("pre_close") or 0)
            pct = round((close - pre_close) / pre_close * 100, 2) if pre_close else None
            return None, (round(close, 2) if close else None), pct
        return None, None, None

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
            flag_pole_end_date=flag_info["pole_end_date"] if flag_info else None,
            flag_pole_start_date=flag_info["pole_start_date"] if flag_info else None,
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

        # ── 提前计算 V 形结构，供后续候选打分使用 ──────────────────────────────
        # 窄 V（15根）：快节奏短期 V 形
        _vpre_closes = [self._safe_float(row.get("close")) for row in history_rows[-15:]]
        _vpre_closes = [c for c in _vpre_closes if c is not None]
        is_v_shape_early = False
        if len(_vpre_closes) >= 8:
            _vpre = _vpre_closes[:-1]
            _vpre_low = min(_vpre)
            _vpre_idx = _vpre.index(_vpre_low)
            if 1 <= _vpre_idx <= len(_vpre) - 2:
                _vpre_start, _vpre_cur = _vpre_closes[0], _vpre_closes[-1]
                if _vpre_start > 0 and _vpre_low > 0:
                    _vpre_drop = (_vpre_start - _vpre_low) / _vpre_start * 100
                    _vpre_rec = (_vpre_cur - _vpre_low) / _vpre_low * 100
                    is_v_shape_early = _vpre_drop >= 7 and _vpre_rec >= 6
        # 宽 V（30根）：大跌后强势反转，起点取低点前最高价
        is_wide_v_early = False
        wide_v_drop_early = 0.0
        if not is_v_shape_early:
            _wvpre_closes = [self._safe_float(row.get("close")) for row in history_rows[-30:]]
            _wvpre_closes = [c for c in _wvpre_closes if c is not None]
            if len(_wvpre_closes) >= 15:
                _wvpre_search = _wvpre_closes[:-5]
                _wvpre_low = min(_wvpre_search)
                _wvpre_idx = _wvpre_search.index(_wvpre_low)
                if _wvpre_idx >= 3:
                    _wvpre_peak = max(_wvpre_closes[: _wvpre_idx + 1])
                    _wvpre_cur = _wvpre_closes[-1]
                    if _wvpre_peak > 0 and _wvpre_low > 0:
                        wide_v_drop_early = (_wvpre_peak - _wvpre_low) / _wvpre_peak * 100
                        _wvpre_rec = (_wvpre_cur - _wvpre_low) / _wvpre_low * 100
                        is_wide_v_early = wide_v_drop_early >= 10 and _wvpre_rec >= 10

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

        # 标准多头排列：价格 > MA20 > MA60，均线斜率向上
        _std_bull = (
            ma20 is not None and ma60 is not None
            and price >= ma20 >= ma60
            and ma_slope_20 > 0 and ma_slope_60 >= 0
        )
        # 强势突破状态：价格高于 MA20 与 MA60，但两条均线可能尚未完成金叉
        # （大幅拉升后 MA60 会滞后，MA20 与 MA60 短期可能纠缠）
        _breakout_bull = (
            ma20 is not None and ma60 is not None
            and price >= ma20 and price >= ma60
            and ma_slope_20 > 0
            and not (ma20 >= ma60)  # MA 排列尚未稳固，否则由标准多头处理
        )
        if _std_bull or _breakout_bull:
            score = 0.63
            hits = [
                "价格位于 MA20 和 MA60 之上",
                "中期均线仍在上行",
            ]
            if _breakout_bull:
                score = 0.60  # 均线尚未完全整理，置信度稍降
                hits = [
                    "价格已站上 MA20 与 MA60，但两线尚未完成金叉排列",
                    "MA20 斜率向上，趋势方向偏多",
                ]
                if is_wide_v_early:
                    # 30日内存在大幅回调后反弹结构（宽 V），"延续"标签具误导性
                    # 压低分数，让 V形修复 优先排首位
                    score = 0.48
                    hits.append(f"注意：30日内峰谷跌幅达 {wide_v_drop_early:.1f}%，趋势曾显著中断")
            if close_quality >= 0.65 and latest_change > 0:
                score += 0.08
                hits.append("收盘位置较好，趋势延续性更强")
            if feature_snapshot.retrace_ready:
                score += 0.06
                hits.append("价格回到趋势均线附近，存在回踩确认语义")
                name = "回踩确认"
                phase = "回踩后待确认"
                summary = "趋势没坏，关键看均线附近的承接和次日确认。"
            elif _breakout_bull:
                name = "上升趋势延续"
                phase = "均线整理中"
                summary = "价格已站上所有主要均线，MA 排列正在完善，整体方向偏多。"
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

        if (
            flag_pole_high is not None
            and flag_face_low is not None
            and not flag_large_struct_broken
            and feature_snapshot.ma_alignment != "均线压制"
        ):
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
            and latest_change >= 0
            and (
                close_quality >= 0.5
                or center_shift >= 2
                or volume_pattern in {"明显放量", "温和放量"}
            )
        ):
            # 右底固定为最近的波段低点，向左扫描最佳匹配左底
            # 优先选：① 间隔最长（结构更宏观）② 价格差最小（两底更对称）
            _sb = swing_low_points[-1]   # 右底：始终取最近的波段低点
            best_db_pair = None
            best_db_neck = None
            best_db_gap = 0.0
            for _i in range(len(swing_low_points) - 1):
                _sa = swing_low_points[_i]
                _gap = _sb["index"] - _sa["index"]
                if _gap < 10:
                    continue
                _price_diff_pct = abs(_sa["price"] - _sb["price"]) / max(_sa["price"], 0.01)
                if _price_diff_pct > 0.10:   # 允许 10%，兼容右底略低的不对称双底
                    continue
                # 计算两底之间的颈线（两底之间最高点）
                _mid_neck = self._neckline_point_between(
                    history_rows, _sa["index"], _sb["index"], mode="double_bottom"
                )
                if _mid_neck is None:
                    continue
                if _mid_neck["price"] <= max(_sa["price"], _sb["price"]):
                    continue
                # 用间隔长度 * (1 - 价格差比率) 作为优先级，选择最完整的双底
                _score_key = _gap * (1 - _price_diff_pct)
                if _score_key > best_db_gap:
                    best_db_gap = _score_key
                    best_db_pair = (_sa, _sb)
                    best_db_neck = _mid_neck

            if best_db_pair is not None and best_db_neck is not None:
                sl_a, sl_b = best_db_pair
                sl_time_gap = sl_b["index"] - sl_a["index"]
                _nk = best_db_neck["price"]
                _above_neckline = price >= _nk * 1.01
                # 价格在颈线以上（双底突破确认）时允许"区间高位"
                _range_ok = (
                    feature_snapshot.range60_position != "区间高位"
                    or _above_neckline
                )
                if _range_ok:
                    score = 0.56
                    if center_shift >= 2:
                        score += 0.04
                    if volume_pattern in {"明显放量", "温和放量"}:
                        score += 0.03
                    if _above_neckline:
                        score += 0.05
                    _phase = "颈线突破后" if _above_neckline else "颈线附近修复"
                    _summary = (
                        "双底结构已完成，颈线有效突破后进入加速上攻阶段。"
                        if _above_neckline
                        else "两个低点接近，当前位置更像双底修复而不是单日反弹。"
                    )
                    _conflict = (
                        ["突破后如快速回落至颈线下方，双底结构会明显削弱"]
                        if _above_neckline
                        else ["颈线未确认前，仍可能只是弱修复反弹"]
                    )
                    candidates.append(
                        StockPatternCandidate(
                            name="双底修复",
                            score=min(score, 0.86),
                            confidence=self._score_confidence(score),
                            phase=_phase,
                            summary=_summary,
                            rule_hits=[
                                f"两个波段低点接近：{sl_a['price']:.2f}/{sl_b['price']:.2f}（间隔 {sl_time_gap} 根）",
                                f"两底之间颈线约 {_nk:.2f}，当前{'已突破颈线' if _above_neckline else '逼近颈线'}",
                                "收盘位置和修复动能不差",
                            ],
                            conflict_points=_conflict,
                        )
                    )

        # ── 窄窗口 V 形（15根）：捕捉快节奏短期 V 形 ──────────────────────────
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

        # ── 宽窗口 V 形（30根）：补充窄窗覆盖不到的大跌后强势反转 ──────────
        # 起点取低点之前的最高价，而非窗口第一根，以准确量化真实跌幅
        is_wide_v = False
        wide_v_drop_pct = 0.0
        wide_v_recovery_pct = 0.0
        if not is_v_shape:
            _wv_closes = [self._safe_float(row.get("close")) for row in history_rows[-30:]]
            _wv_closes = [c for c in _wv_closes if c is not None]
            if len(_wv_closes) >= 15:
                # 在前 25 根中找低点，保留至少 5 根回升空间
                _wv_search = _wv_closes[:-5]
                _wv_low = min(_wv_search)
                _wv_idx = _wv_search.index(_wv_low)
                # 低点前至少 3 根，才有足够的下跌过程
                if _wv_idx >= 3:
                    _wv_peak = max(_wv_closes[: _wv_idx + 1])
                    _wv_current = _wv_closes[-1]
                    if _wv_peak > 0 and _wv_low > 0:
                        wide_v_drop_pct = (_wv_peak - _wv_low) / _wv_peak * 100
                        wide_v_recovery_pct = (_wv_current - _wv_low) / _wv_low * 100
                        # 宽 V 要求跌幅更大（≥10%）、回升也要有力（≥10%）
                        is_wide_v = wide_v_drop_pct >= 10 and wide_v_recovery_pct >= 10

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
            is_wide_v
            and not is_v_shape
            and ma_slope_10 > 0
            and latest_change >= 0
            and close_quality >= 0.5
        ):
            score = 0.53
            if volume_pattern in {"明显放量", "温和放量"}:
                score += 0.06
            if center_shift >= 2:
                score += 0.04
            candidates.append(
                StockPatternCandidate(
                    name="V形修复",
                    score=min(score, 0.82),
                    confidence=self._score_confidence(score),
                    phase="大幅回调后强势反转",
                    summary="经历大幅回调后快速反转，V 形底部已现，修复能否延续是关键。",
                    rule_hits=[
                        f"30日内回调峰谷跌幅 {wide_v_drop_pct:.1f}%，随后回升 {wide_v_recovery_pct:.1f}%，大 V 形结构成立",
                        f"短期均线斜率转正，收盘质量 {close_quality:.2f}",
                        f"近 20 日重心变化 {center_shift:.2f}%",
                    ],
                    conflict_points=[
                        "大跌后的 V 形反转稳定性偏低，前期下跌压力位密集，需观察能否有效突破",
                        "V 形回升速度快但结构尚浅，不能把短期反弹速度等同于趋势反转",
                    ],
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

        # 规则全未命中但大结构仍偏多时：避免「大阳线旗杆 + 深幅整理」等落在规则缝隙里变成赤裸的未识别
        if not candidates:
            if (
                ma20 is not None
                and ma60 is not None
                and float(price) >= float(ma60) * 0.985
                and ma_slope_20 is not None
                and ma_slope_20 > -0.25
                and feature_snapshot.range20_position in {"区间中位", "区间低位"}
                and amplitude20 >= 8
            ):
                candidates.append(
                    StockPatternCandidate(
                        name="上升趋势延续",
                        score=0.52,
                        confidence=self._score_confidence(0.52),
                        phase="整理后再选方向",
                        summary="未命中细分旗形/平台等硬规则，但价仍在长期均线之上、更像趋势中的整理段。",
                        rule_hits=[
                            "核心形态规则未触发（常见于旗形阈值过严或 K 线冲高回落）",
                            f"当前 20 日区间位置：{feature_snapshot.range20_position}，收盘质量 {close_quality:.2f}",
                            f"MA20 斜率未明显走坏，价格相对 MA60 仍处 {float(price) / float(ma60) * 100:.1f}% 水位",
                        ],
                        conflict_points=[
                            "若有效跌破 MA60 或重心持续下移，需降级为观望",
                            "若放量突破前高并站稳，可再对照旗形中继规则复核",
                        ],
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
        confidence_str = primary.confidence or self._score_confidence(primary.score)
        action_advice = self._build_action_advice(primary.name, breakout_level, defense_level, confidence_str)
        return StockPatternResult(
            primary_pattern=primary.name,
            secondary_patterns=[item.name for item in candidates[1:]],
            confidence=confidence_str,
            pattern_phase=primary.phase or "待确认",
            pattern_summary=pattern_summary,
            pattern_rationale=rationale,
            execution_hint=execution_hint,
            risk_hint=risk_hint,
            action_advice=action_advice,
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
        channel_structure = (
            self._falling_channel_structure(history_rows)
            if pattern_result.primary_pattern == "下跌通道反抽"
            else None
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
        if pattern_result.primary_pattern == "下跌通道反抽" and channel_structure is not None:
            # 通道上下轨替换默认水平压力/支撑线
            price_lines = [
                StockPatternLine(
                    label="通道上轨",
                    line_type="pressure",
                    start_trade_date=channel_structure["upper_start_date"],
                    end_trade_date=channel_structure["upper_end_date"],
                    start_price=channel_structure["upper_start_price"],
                    end_price=channel_structure["upper_end_price"],
                ),
                StockPatternLine(
                    label="通道下轨",
                    line_type="support",
                    start_trade_date=channel_structure["lower_start_date"],
                    end_trade_date=channel_structure["lower_end_date"],
                    start_price=channel_structure["lower_start_price"],
                    end_price=channel_structure["lower_end_price"],
                ),
            ]
        if pattern_result.breakout_level is not None:
            breakout_exists = any(
                line.line_type == "pressure"
                and line.price is not None
                and abs(line.price - pattern_result.breakout_level) <= 0.01
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
                line.line_type == "support"
                and line.price is not None
                and abs(line.price - pattern_result.defense_level) <= 0.01
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
            pattern_result.primary_pattern == "旗形中继"
            and feature_snapshot.flag_face_high is not None
            and feature_snapshot.flag_face_low is not None
            and feature_snapshot.flag_pole_end_date is not None
            and candles
        ):
            flag_start_date = next(
                (c.trade_date for c in candles if c.trade_date >= feature_snapshot.flag_pole_end_date),
                None,
            )
            if flag_start_date:
                zones.append(
                    StockPatternZone(
                        label="旗面区",
                        zone_type="flag_face",
                        start_trade_date=flag_start_date,
                        end_trade_date=candles[-1].trade_date,
                        low_price=feature_snapshot.flag_face_low,
                        high_price=feature_snapshot.flag_face_high,
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
        merged.action_advice = str(llm_result.get("action_advice") or merged.action_advice)
        bias = str(llm_result.get("direction_bias") or "").strip()
        if bias in {"看多", "看空", "中性"}:
            merged.direction_bias = bias
        rationale = str(llm_result.get("direction_rationale") or "").strip()
        if rationale:
            merged.direction_rationale = rationale
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
            # 右底固定为最近波段低点，向左扫描最佳匹配左底
            _dsb = swing_low_points[-1]   # 右底：始终取最近的波段低点
            _best_ll, _best_rl, _best_nk_pt = None, None, None
            _best_db_key = 0.0
            for _di in range(len(swing_low_points) - 1):
                _dsa = swing_low_points[_di]
                _dgap = _dsb["index"] - _dsa["index"]
                if _dgap < 10:
                    continue
                _ddiff = abs(_dsa["price"] - _dsb["price"]) / max(_dsa["price"], 0.01)
                if _ddiff > 0.10:
                    continue
                _dnk = self._neckline_point_between(history_rows, _dsa["index"], _dsb["index"], mode="double_bottom")
                if _dnk is None or _dnk["price"] <= max(_dsa["price"], _dsb["price"]):
                    continue
                _dkey = _dgap * (1 - _ddiff)
                if _dkey > _best_db_key:
                    _best_db_key = _dkey
                    _best_ll, _best_rl, _best_nk_pt = _dsa, _dsb, _dnk
            if _best_ll and _best_rl:
                left_low, right_low = _best_ll, _best_rl
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
                if _best_nk_pt is not None:
                    annotations.append(
                        StockPatternAnnotation(
                            trade_date=_best_nk_pt["trade_date"],
                            price=_best_nk_pt["price"],
                            label="颈线",
                            annotation_type="neckline",
                        )
                    )
                    # 在颈线 → 右底之间找"右侧二次探底"（比右底还低的超跌点）
                    # _best_nk_pt 只含 trade_date/price，需按 trade_date 定位 index
                    _nk_idx = next(
                        (i for i, r in enumerate(history_rows)
                         if self._format_trade_date(str(r.get("trade_date") or ""))
                         == _best_nk_pt["trade_date"]),
                        None,
                    )
                    _retest_rows = (
                        history_rows[_nk_idx + 1 : right_low["index"]]
                        if _nk_idx is not None
                        else []
                    )
                    if _retest_rows:
                        _rt_row = min(
                            _retest_rows,
                            key=lambda r: self._safe_float(r.get("low")) or float("inf"),
                        )
                        _rt_price = self._safe_float(_rt_row.get("low"))
                        # 比右底低超过 1%，才值得单独标注
                        if _rt_price is not None and _rt_price < right_low["price"] * 0.99:
                            annotations.append(
                                StockPatternAnnotation(
                                    trade_date=self._format_trade_date(
                                        str(_rt_row.get("trade_date") or "")
                                    ),
                                    price=round(_rt_price, 2),
                                    label="二次探底",
                                    annotation_type="db_retest",
                                )
                            )
        elif pattern_name == "V形修复":
            # 从最近 30 根 K 线里找 V 形顶点和底部，用于前端连线示意
            rows_30 = history_rows[-30:]
            _vc_pairs = [
                (str(r.get("trade_date") or ""), self._safe_float(r.get("close")))
                for r in rows_30
            ]
            _vc_pairs = [(d, c) for d, c in _vc_pairs if d and c is not None]
            if len(_vc_pairs) >= 12:
                _vc_search = _vc_pairs[:-5]          # 前 25 根中找低点，留 5 根回升空间
                _vc_prices = [c for _, c in _vc_search]
                _vc_low_price = min(_vc_prices)
                _vc_low_idx = _vc_prices.index(_vc_low_price)
                _vc_low_date = self._format_trade_date(_vc_search[_vc_low_idx][0])
                if _vc_low_idx >= 3:
                    _vc_peak_price = max(_vc_prices[: _vc_low_idx + 1])
                    _vc_peak_idx = _vc_prices.index(_vc_peak_price)
                    _vc_peak_date = self._format_trade_date(_vc_search[_vc_peak_idx][0])
                    annotations.append(
                        StockPatternAnnotation(
                            trade_date=_vc_peak_date,
                            price=round(_vc_peak_price, 2),
                            label="V形顶",
                            annotation_type="v_peak",
                        )
                    )
                    annotations.append(
                        StockPatternAnnotation(
                            trade_date=_vc_low_date,
                            price=round(_vc_low_price, 2),
                            label="V形底",
                            annotation_type="v_low",
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
        elif pattern_name == "旗形中继":
            # 旗杆起点和旗杆顶点：供前端连线画旗杆
            _pole_start_date = feature_snapshot.flag_pole_start_date
            _pole_end_date = feature_snapshot.flag_pole_end_date
            _pole_start_price = feature_snapshot.flag_pole_start
            _pole_end_price = feature_snapshot.flag_pole_high
            if _pole_start_date and _pole_start_price is not None:
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=_pole_start_date,
                        price=round(_pole_start_price, 2),
                        label="旗杆起",
                        annotation_type="flag_pole_start",
                    )
                )
            if _pole_end_date and _pole_end_price is not None:
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=_pole_end_date,
                        price=round(_pole_end_price, 2),
                        label="旗杆顶",
                        annotation_type="flag_pole_top",
                    )
                )

        elif pattern_name == "下跌通道反抽":
            # 反抽低点：最近一个波段低点，供前端连线到当前收盘画反抽示意线
            _ch = self._falling_channel_structure(history_rows)
            if _ch and _ch.get("bounce_date") and _ch.get("bounce_price") is not None:
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=_ch["bounce_date"],
                        price=_ch["bounce_price"],
                        label="反抽低点",
                        annotation_type="channel_bounce",
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
        elif pattern_name == "上升趋势延续":
            ext_lows = self._swing_points(history_rows, mode="low", tail=15)
            chain = self._uptrend_swing_low_chain(ext_lows)
            labels = ("抬升低①", "抬升低②", "抬升低③")
            for idx, pt in enumerate(chain):
                annotations.append(
                    StockPatternAnnotation(
                        trade_date=pt["trade_date"],
                        price=pt["price"],
                        label=labels[idx] if idx < len(labels) else f"抬升低{idx + 1}",
                        annotation_type="uptrend_low",
                    )
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
            and pattern_name not in {"双底修复", "双顶风险", "上升趋势延续"}
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

    def _build_action_advice(
        self,
        pattern_name: str,
        breakout_level: Optional[float],
        defense_level: Optional[float],
        confidence: str = "",
    ) -> str:
        """规则层操作建议（LLM 启用时会被覆盖）。
        聚焦：操作方向 + 触发条件 + 止损/防守价位。
        """
        bl = f"{breakout_level:.2f}" if breakout_level is not None else "突破位"
        dl = f"{defense_level:.2f}" if defense_level is not None else "防守位"

        mapping: dict[str, str] = {
            "平台突破临界": (
                f"可在 {bl} 附近放量突破时轻仓介入，防守 {dl}；"
                f"若缩量假突破则不追，等回踩 {dl} 再看承接。"
            ),
            "回踩确认": (
                f"回踩 {dl} 附近有效承接可考虑加仓/介入，"
                f"跌破 {dl} 则止损离场。"
            ),
            "旗形中继": (
                f"旗面整理期间可轻仓持有；"
                f"放量突破 {bl} 后可加仓追进，止损设 {dl}。"
            ),
            "双底修复": (
                f"颈线 {bl} 放量突破可介入，目标参考旗杆高度；"
                f"防守 {dl}，破则止损。"
            ),
            "双顶风险": (
                f"当前不适合追多，建议轻仓或观望；"
                f"若跌破颈线 {dl} 则减仓止损。"
            ),
            "V形修复": (
                f"V 形低点 {dl} 不破可短线持有；"
                f"但 V 形稳定性偏低，{bl} 以下建议控制仓位。"
            ),
            "圆弧底修复": (
                f"弧顶突破 {bl} 才可加仓，破前轻仓观察；"
                f"防守 {dl}，破则止损。"
            ),
            "上升趋势延续": (
                f"多头趋势延续，回踩均线（{dl} 附近）可补仓；"
                f"跌破均线支撑且 {dl} 失守则减仓。"
            ),
            "平台整理": (
                f"区间整理期间观望为主，等待方向突破 {bl} 后再介入；"
                f"跌破 {dl} 则回避。"
            ),
            "箱体震荡": (
                f"箱体内高抛低吸为主；"
                f"放量突破 {bl} 可跟进，跌破 {dl} 则止损。"
            ),
            "三角收敛": (
                f"三角收敛等待方向选择；"
                f"突破上轨 {bl} 后可买入，跌破下轨 {dl} 则止损。"
            ),
            "假突破/突破失败": (
                f"当前形态偏弱，不建议追多；"
                f"{dl} 守住可观察是否修复，跌破则离场。"
            ),
            "下跌通道反抽": (
                f"反抽行情以观望为主，不建议介入；"
                f"站回 {bl} 且通道有效突破后再考虑。"
            ),
            "弱修复反弹": (
                f"弱反弹风险高，建议观望；"
                f"若持仓在 {dl} 失守时减仓。"
            ),
            "高位震荡/派发嫌疑": (
                f"高位派发风险较大，不建议追高；"
                f"已持仓关注 {dl} 是否失守，破则减仓。"
            ),
        }
        advice = mapping.get(pattern_name)
        if advice:
            return advice
        return (
            f"当前形态不明确，建议观望；"
            f"有意介入者需等 {bl} 有效突破，并以 {dl} 作为止损参考。"
        )

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

    def _swing_points(
        self,
        history_rows: List[Dict],
        *,
        mode: str,
        tail: Optional[int] = 5,
    ) -> List[Dict]:
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
        if tail is None:
            return points
        if tail <= 0:
            return []
        return points[-tail:]

    def _uptrend_swing_low_chain(self, swing_lows: List[Dict]) -> List[Dict]:
        """
        从波段低点序列中提取 2～3 个「依次抬高」的低点（时间越晚价格越高），
        用于「上升趋势延续」在 K 线图上的示意连线。
        """
        if not swing_lows:
            return []
        if len(swing_lows) == 1:
            return [swing_lows[-1]]
        # 从最右侧波段低点向左回溯：仅保留价格严格低于右侧点的更早低点，形成低点抬高链
        chain: List[Dict] = [swing_lows[-1]]
        for i in range(len(swing_lows) - 2, -1, -1):
            prev = swing_lows[i]
            if prev["price"] < chain[0]["price"] * 0.998:
                chain.insert(0, prev)
            if len(chain) >= 3:
                break
        if len(chain) < 2:
            return swing_lows[-2:]
        return chain

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
        # 双底颈线：右底固定为最近波段低点，向左扫描最佳匹配左底
        if len(swing_low_points) >= 2:
            _sb = swing_low_points[-1]   # 右底：始终取最近的波段低点
            best_neck = None
            best_key = 0.0
            for _i in range(len(swing_low_points) - 1):
                _sa = swing_low_points[_i]
                _gap = _sb["index"] - _sa["index"]
                if _gap < 10:
                    continue
                _diff_pct = abs(_sa["price"] - _sb["price"]) / max(_sa["price"], 0.01)
                if _diff_pct > 0.10:
                    continue
                _nk_pt = self._neckline_point_between(
                    history_rows, _sa["index"], _sb["index"], mode="double_bottom"
                )
                if _nk_pt is None or _nk_pt["price"] <= max(_sa["price"], _sb["price"]):
                    continue
                _key = _gap * (1 - _diff_pct)
                if _key > best_key:
                    best_key = _key
                    best_neck = _nk_pt
            if best_neck is not None:
                return best_neck["price"]
        # 双顶颈线：取最后两个高点之间最低点
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

    def _falling_channel_structure(self, history_rows: List[Dict]) -> Optional[Dict]:
        """检测下跌通道结构：找最近两个构成下降趋势的波段高点，构建通道上下轨并投影到当前。"""
        if len(history_rows) < 20:
            return None
        rows = history_rows[-80:]
        n = len(rows)
        swing_highs = self._swing_points(rows, mode="high")
        swing_lows  = self._swing_points(rows, mode="low")
        if len(swing_highs) < 2:
            return None

        # 找最近两个价格依次降低的波段高点
        sh2 = swing_highs[-1]
        sh1 = None
        for sh in reversed(swing_highs[:-1]):
            if sh["price"] > sh2["price"]:
                sh1 = sh
                break
        if sh1 is None:
            return None

        gap = sh2["index"] - sh1["index"]
        if gap <= 0:
            return None
        slope = (sh2["price"] - sh1["price"]) / gap  # 负斜率

        bars_to_end = (n - 1) - sh2["index"]
        upper_end_price = sh2["price"] + slope * bars_to_end

        # 下轨：与上轨平行，过 sh1 之后最低的波段低点
        lows_after_sh1 = [sl for sl in swing_lows if sl["index"] >= sh1["index"]]
        if not lows_after_sh1:
            return None
        lowest_sl = min(lows_after_sh1, key=lambda s: s["price"])
        upper_at_lowest = sh1["price"] + slope * (lowest_sl["index"] - sh1["index"])
        channel_width = upper_at_lowest - lowest_sl["price"]
        if channel_width <= 0:
            return None

        lower_start_price = sh1["price"] - channel_width
        lower_end_price   = upper_end_price - channel_width

        # 最近反抽低点（最新波段低点）
        recent_low = swing_lows[-1] if swing_lows else None
        current_date = self._format_trade_date(str(rows[-1].get("trade_date") or ""))
        return {
            "upper_start_date":  sh1["trade_date"],
            "upper_start_price": round(sh1["price"], 2),
            "upper_end_date":    current_date,
            "upper_end_price":   round(upper_end_price, 2),
            "lower_start_date":  sh1["trade_date"],
            "lower_start_price": round(lower_start_price, 2),
            "lower_end_date":    current_date,
            "lower_end_price":   round(lower_end_price, 2),
            "bounce_date":  recent_low["trade_date"] if recent_low else None,
            "bounce_price": round(recent_low["price"], 2) if recent_low else None,
        }

    def _flag_structure(self, history_rows: List[Dict]) -> Optional[Dict]:
        """检测旗形结构：旗杆（快速集中拉升）+ 旗面（缩幅、下倾整理）。

        核心约束（偏严以降低误报）：
        1. 旗杆顶点必须是波段高点（swing high），不接受任意 K 线
        2. 旗杆起点为旗杆顶之前的波段低点，间距 3～55 根
        3. 旗杆效率：短杆 ≥0.85%/根，长杆(≥40根) ≥0.65%/根
        4. 旗杆最小涨幅 14%
        5. 旗面仅用杆顶之后 K 线，至少 5 根；高低价与杆顶同用 OHLC，不用收盘混用
        6. 旗面高点整体下移、低点整体下移（略放宽以容忍噪声与深幅整理）
        7. 旗面最高价不明显突破杆顶（避免「顶横宽震」当旗形）
        8. 旗面回调相对旗杆涨幅：基础 48%，旗杆≥22%/28%/35% 时分别放宽至 54%/60%/68%；旗面振幅上限随旗杆放大略放宽
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

        swing_highs = self._swing_points(tail_rows, mode="high", tail=None)
        swing_lows = self._swing_points(tail_rows, mode="low", tail=None)

        best_result = None
        best_score = 0.0

        for sh in swing_highs:
            pole_end = sh["index"]
            pole_end_price = sh["price"]

            # 旗杆顶点需在 [5, n-5) 范围内，后面留足旗面空间
            if pole_end < 5 or pole_end >= n - 5:
                continue

            # 在旗杆顶点之前找效率最高的波段低点作为旗杆起点（距离 ≤ 55 根）
            pole_start_sl = None
            best_pole_efficiency = 0.0
            for sl in reversed(swing_lows):
                gap = pole_end - sl["index"]
                if gap < 3:
                    continue
                if gap > 55:
                    break
                _gain = (pole_end_price - sl["price"]) / max(sl["price"], 0.01) * 100
                if _gain < 14:
                    continue
                _efficiency = _gain / gap
                _eff_threshold = 0.65 if gap >= 40 else 0.85
                if _efficiency >= _eff_threshold and _efficiency > best_pole_efficiency:
                    best_pole_efficiency = _efficiency
                    pole_start_sl = sl
            if pole_start_sl is None:
                continue

            pole_start_price = pole_start_sl["price"]
            pole_bars = pole_end - pole_start_sl["index"]
            if pole_start_price <= 0 or pole_bars <= 0:
                continue

            pole_gain_pct = (pole_end_price - pole_start_price) / pole_start_price * 100

            if pole_gain_pct < 14:
                continue

            _pole_eff_min = 0.65 if pole_bars >= 40 else 0.85
            if pole_gain_pct / pole_bars < _pole_eff_min:
                continue

            # 旗面：杆顶日之后，直到收盘再次站上杆顶（略放宽）或序列末尾；不含杆顶日本身
            flag_face_end = n
            for j in range(pole_end + 1, n):
                if sc[j] >= pole_end_price * 1.005:
                    flag_face_end = j
                    break
            flag_rows = tail_rows[pole_end + 1 : flag_face_end]
            if len(flag_rows) < 5:
                continue
            highs_seg: List[float] = []
            lows_seg: List[float] = []
            for row in flag_rows:
                h = self._safe_float(row.get("high"))
                lo = self._safe_float(row.get("low"))
                if h is None or lo is None:
                    highs_seg = []
                    break
                highs_seg.append(h)
                lows_seg.append(lo)
            if len(highs_seg) < 5:
                continue

            flag_high = max(highs_seg)
            flag_low = min(lows_seg)

            # 旗面不应反复创出高于杆顶太多的上影（宽顶横盘误报）
            if flag_high > pole_end_price * 1.012:
                continue

            half = len(highs_seg) // 2
            if half < 2:
                continue
            h_first = max(highs_seg[:half])
            h_second = max(highs_seg[half:])
            l_first = min(lows_seg[:half])
            l_second = min(lows_seg[half:])
            # 略放宽：旗面上影噪声、深幅整理时两半段边界不必过严
            if h_first < h_second * 0.992:
                continue
            if l_second >= l_first * 0.998:
                continue

            pullback_pct = (pole_end_price - flag_low) / pole_end_price * 100
            _pullback_cap = 0.48
            if pole_gain_pct >= 35:
                _pullback_cap = 0.68
            elif pole_gain_pct >= 28:
                _pullback_cap = 0.60
            elif pole_gain_pct >= 22:
                _pullback_cap = 0.54
            if pullback_pct > pole_gain_pct * _pullback_cap:
                continue

            if current_price < pole_start_price * 0.97:
                continue

            flag_amplitude_pct = (flag_high - flag_low) / max(flag_low, 0.01) * 100
            _face_amp_cap = 0.65
            if pole_gain_pct >= 30:
                _face_amp_cap = 0.80
            if flag_amplitude_pct >= pole_gain_pct * _face_amp_cap:
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
                    "pole_end_date": sh["trade_date"],
                    "pole_start_date": pole_start_sl["trade_date"],
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
