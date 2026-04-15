"""
股票形态分析服务测试
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
    StructureStateTag,
)
from app.services.pattern_analysis import pattern_analysis_service  # noqa: E402


def _sample_target_input(**overrides):
    data = {
        "ts_code": "002463.SZ",
        "stock_name": "沪电股份",
        "sector_name": "元器件",
        "close": 10.22,
        "open": 10.05,
        "high": 10.28,
        "low": 9.98,
        "change_pct": 2.1,
        "turnover_rate": 6.8,
        "vol_ratio": 1.7,
        "quote_time": "2026-04-14 14:55:00",
        "data_source": "realtime_quote",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _sample_scored_stock(**overrides):
    data = {
        "ts_code": "002463.SZ",
        "stock_name": "沪电股份",
        "sector_name": "元器件",
        "change_pct": 2.1,
        "close": 10.22,
        "open": 10.05,
        "high": 10.28,
        "low": 9.98,
        "pre_close": 10.01,
        "vol_ratio": 1.7,
        "turnover_rate": 6.8,
        "stock_score": 89.0,
        "candidate_source_tag": "形态分析",
        "candidate_bucket_tag": "平台观察",
        "stock_strength_tag": StockStrengthTag.STRONG,
        "stock_continuity_tag": StockContinuityTag.SUSTAINABLE,
        "stock_tradeability_tag": StockTradeabilityTag.TRADABLE,
        "stock_core_tag": StockCoreTag.CORE,
        "stock_pool_tag": StockPoolTag.ACCOUNT_EXECUTABLE,
        "structure_state_tag": StructureStateTag.REPAIR,
        "stock_falsification_cond": "跌破平台下沿",
        "stock_comment": "平台整理后等待突破",
    }
    data.update(overrides)
    return StockOutput(**data)


def _platform_history():
    rows = []
    base = 8.9
    for index in range(80):
        close = round(base + 0.01 * index, 2) if index < 55 else round(10.05 + (index % 5) * 0.03, 2)
        high = round(close + 0.12, 2)
        low = round(close - 0.14, 2)
        rows.append(
            {
                "trade_date": f"202601{(index % 28) + 1:02d}",
                "open": round(close - 0.05, 2),
                "high": high,
                "low": low,
                "close": close,
                "vol": 100000 + index * 500,
            }
        )
    rows[-1].update({"close": 10.22, "high": 10.28, "low": 9.98, "open": 10.05, "trade_date": "20260414"})
    return rows


def _false_breakout_history():
    rows = []
    for index in range(80):
        if index < 60:
            close = round(9.5 + 0.015 * index, 2)
            high = round(close + 0.15, 2)
            low = round(close - 0.16, 2)
        else:
            step = index - 60
            close = round(10.48 + (step % 4) * 0.05, 2)
            high = round(min(10.86, close + 0.12), 2)
            low = round(close - 0.14, 2)
        rows.append(
            {
                "trade_date": f"202602{(index % 28) + 1:02d}",
                "open": round(close - 0.04, 2),
                "high": high,
                "low": low,
                "close": close,
                "vol": 120000 + index * 900,
            }
        )
    rows[-1].update({"open": 10.68, "high": 10.86, "low": 10.42, "close": 10.50, "vol": 260000, "trade_date": "20260414"})
    return rows


def _triangle_history():
    rows = []
    for index in range(80):
        if index < 55:
            close = round(10.2 + 0.02 * index, 2)
            high = round(close + 0.22, 2)
            low = round(close - 0.2, 2)
        else:
            step = index - 55
            high = round(12.2 - 0.03 * step, 2)
            low = round(10.45 + 0.025 * step, 2)
            close = round((high + low) / 2, 2)
        rows.append(
            {
                "trade_date": f"202603{(index % 28) + 1:02d}",
                "open": round(close - 0.03, 2),
                "high": high,
                "low": low,
                "close": close,
                "vol": 150000 - max(0, index - 55) * 1800,
            }
        )
    rows[-1].update({"open": 11.33, "high": 11.55, "low": 11.04, "close": 11.36, "vol": 98000, "trade_date": "20260414"})
    return rows


def _v_repair_history():
    """大跌后强势拉回；近 30/15 根内各有一段「中段低点」以匹配形态规则的索引约束。"""
    rows = []
    for index in range(80):
        if index < 38:
            close = round(14.2 - 0.15 * index, 2)
        elif index < 48:
            close = round(8.5 + 0.02 * (index - 38), 2)
        elif index < 62:
            close = round(8.7 + 0.12 * (index - 48), 2)
        elif index < 70:
            close = round(10.38 - 0.16 * (index - 62), 2)
        else:
            close = round(9.1 + 0.38 * (index - 70), 2)
        rows.append(
            {
                "trade_date": f"202604{(index % 28) + 1:02d}",
                "open": round(close - 0.06, 2),
                "high": round(close + 0.18, 2),
                "low": round(close - 0.15, 2),
                "close": close,
                "vol": 100000 + max(0, index - 58) * 4000,
            }
        )
    rows[-1].update({"open": 12.10, "high": 12.56, "low": 12.02, "close": 12.48, "vol": 280000, "trade_date": "20260414"})
    return rows


def _double_bottom_history():
    closes = [
        18.4, 18.1, 17.8, 17.3, 16.9, 16.2, 15.6, 15.1, 14.8, 14.6,
        14.9, 15.2, 15.5, 15.9, 16.2, 15.8, 15.4, 15.0, 14.7, 14.3,
        13.9, 14.2, 14.6, 15.0, 15.3, 15.6, 15.9, 16.1, 16.3, 16.5,
        16.7, 16.9, 17.1, 17.0, 16.8, 16.6, 16.4, 16.3, 16.2, 16.1,
        16.0, 15.9, 15.8, 15.7, 15.6, 15.5, 15.4, 15.3, 15.2, 15.1,
        15.0, 14.9, 14.8, 14.7, 14.6, 14.5, 14.4, 14.3, 14.2, 14.1,
        14.0, 14.1, 14.3, 14.6, 14.9, 15.2, 15.6, 16.0, 16.3, 16.7,
        16.9, 17.1, 17.2, 17.1, 17.0, 16.8, 16.6, 16.4, 16.2, 16.0,
    ]
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "trade_date": f"202605{(index % 28) + 1:02d}",
                "open": round(close - 0.08, 2),
                "high": round(close + 0.22, 2),
                "low": round(close - 0.18, 2),
                "close": round(close, 2),
                "vol": 100000 + (index % 9) * 9000,
            }
        )
    rows[-1].update({"trade_date": "20260414"})
    return rows


def test_feature_snapshot_extracts_platform_bounds():
    features = pattern_analysis_service._build_feature_snapshot(_sample_target_input(), _platform_history())

    assert features.sufficient_history is True
    assert features.platform_upper is not None
    assert features.platform_lower is not None
    assert features.platform_upper > features.platform_lower
    assert features.range20_position in {"区间高位", "区间中位", "区间低位"}


def test_pattern_candidates_include_platform_breakout_or_consolidation():
    features = pattern_analysis_service._build_feature_snapshot(_sample_target_input(), _platform_history())
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        _sample_target_input(),
        _sample_scored_stock(),
        _platform_history(),
    )

    assert candidates
    assert candidates[0].name in {"平台整理", "平台突破临界", "回踩确认", "上升趋势延续"}
    assert all(candidate.name for candidate in candidates)


def test_pattern_candidates_fall_back_when_history_insufficient():
    short_history = _platform_history()[:30]
    features = pattern_analysis_service._build_feature_snapshot(_sample_target_input(), short_history)
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        _sample_target_input(),
        _sample_scored_stock(),
        short_history,
    )

    assert features.sufficient_history is False
    assert candidates[0].name == "未识别明确形态"
    assert candidates[0].phase == "数据不足"


def test_rule_result_emits_key_levels_and_annotations():
    features = pattern_analysis_service._build_feature_snapshot(_sample_target_input(), _platform_history())
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        _sample_target_input(),
        _sample_scored_stock(),
        _platform_history(),
    )

    result = pattern_analysis_service._build_rule_result(
        features,
        candidates,
        _sample_target_input(),
        _sample_scored_stock(),
        _platform_history(),
    )

    assert result.primary_pattern
    assert result.defense_level is not None
    assert result.pressure_levels
    assert any(item.label in {"平台上沿", "平台下沿", "突破线", "防守线"} for item in result.key_annotations)


def test_pattern_candidates_include_false_breakout_signal():
    target_input = _sample_target_input(close=10.50, open=10.68, high=10.86, low=10.42, change_pct=0.6, vol_ratio=2.4)
    features = pattern_analysis_service._build_feature_snapshot(target_input, _false_breakout_history())
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        target_input,
        _sample_scored_stock(close=10.50, open=10.68, high=10.86, low=10.42, change_pct=0.6, vol_ratio=2.4),
        _false_breakout_history(),
    )

    assert any(candidate.name == "假突破/突破失败" for candidate in candidates)


def test_pattern_candidates_include_triangle_contraction():
    target_input = _sample_target_input(close=11.36, open=11.33, high=11.55, low=11.04, change_pct=0.9, vol_ratio=0.8)
    features = pattern_analysis_service._build_feature_snapshot(target_input, _triangle_history())
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        target_input,
        _sample_scored_stock(close=11.36, open=11.33, high=11.55, low=11.04, change_pct=0.9, vol_ratio=0.8),
        _triangle_history(),
    )

    assert any(candidate.name == "三角收敛" for candidate in candidates)

    result = pattern_analysis_service._build_rule_result(
        features,
        [candidate for candidate in candidates if candidate.name == "三角收敛"] or candidates,
        target_input,
        _sample_scored_stock(close=11.36, open=11.33, high=11.55, low=11.04, change_pct=0.9, vol_ratio=0.8),
        _triangle_history(),
    )
    labels = {item.label for item in result.key_annotations}
    assert {"左高点", "右高点", "左低点", "右低点"}.issubset(labels)
    assert result.pressure_levels[0] <= 11.6
    assert result.support_levels[0] >= 10.9


def test_pattern_candidates_include_v_shape_repair():
    target_input = _sample_target_input(close=12.48, open=12.10, high=12.56, low=12.02, change_pct=3.8, vol_ratio=2.1)
    features = pattern_analysis_service._build_feature_snapshot(target_input, _v_repair_history())
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        target_input,
        _sample_scored_stock(close=12.48, open=12.10, high=12.56, low=12.02, change_pct=3.8, vol_ratio=2.1),
        _v_repair_history(),
    )

    assert any(candidate.name == "V形修复" for candidate in candidates)


def test_double_bottom_uses_intervening_high_as_neckline_and_marks_wave_points():
    target_input = _sample_target_input(close=16.00, open=15.92, high=16.22, low=15.82, change_pct=3.1, vol_ratio=2.2)
    history = _double_bottom_history()
    features = pattern_analysis_service._build_feature_snapshot(target_input, history)
    candidates = pattern_analysis_service._build_pattern_candidates(
        features,
        target_input,
        _sample_scored_stock(close=16.00, open=15.92, high=16.22, low=15.82, change_pct=3.1, vol_ratio=2.2),
        history,
    )

    result = pattern_analysis_service._build_rule_result(
        features,
        [candidate for candidate in candidates if candidate.name == "双底修复"] or candidates,
        target_input,
        _sample_scored_stock(close=16.00, open=15.92, high=16.22, low=15.82, change_pct=3.1, vol_ratio=2.2),
        history,
    )

    labels = {item.label for item in result.key_annotations}

    assert features.neckline_level is not None
    assert result.breakout_level == features.neckline_level
    assert result.breakout_level > max(features.swing_lows[-2:])
    assert {"左底", "右底", "颈线"}.issubset(labels)


def test_uptrend_swing_low_chain_extracts_higher_lows():
    pts = [
        {"trade_date": "2026-01-01", "price": 8.0, "index": 0},
        {"trade_date": "2026-01-15", "price": 8.6, "index": 10},
        {"trade_date": "2026-02-01", "price": 9.1, "index": 20},
    ]
    chain = pattern_analysis_service._uptrend_swing_low_chain(pts)
    assert len(chain) >= 2
    assert chain[0]["price"] < chain[-1]["price"]
    assert {item["trade_date"] for item in chain}.issubset({p["trade_date"] for p in pts})
