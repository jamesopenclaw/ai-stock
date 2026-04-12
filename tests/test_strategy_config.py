"""
策略配置预设测试
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.strategy_config import (  # noqa: E402
    BALANCED_STOCK_FILTER_STRATEGY,
    LEFT_BIASED_STOCK_FILTER_STRATEGY,
    RIGHT_BIASED_STOCK_FILTER_STRATEGY,
    build_stock_filter_strategy,
)


def test_left_biased_strategy_is_more_permissive_than_balanced():
    assert LEFT_BIASED_STOCK_FILTER_STRATEGY.mainline_pullback_per_sector_limit > BALANCED_STOCK_FILTER_STRATEGY.mainline_pullback_per_sector_limit
    assert LEFT_BIASED_STOCK_FILTER_STRATEGY.mainline_low_suck_per_sector_limit > BALANCED_STOCK_FILTER_STRATEGY.mainline_low_suck_per_sector_limit
    assert LEFT_BIASED_STOCK_FILTER_STRATEGY.mainline_pullback_anchor_gap_max > BALANCED_STOCK_FILTER_STRATEGY.mainline_pullback_anchor_gap_max
    assert LEFT_BIASED_STOCK_FILTER_STRATEGY.mainline_low_suck_min_vol_ratio < BALANCED_STOCK_FILTER_STRATEGY.mainline_low_suck_min_vol_ratio


def test_right_biased_strategy_is_stricter_than_balanced():
    assert RIGHT_BIASED_STOCK_FILTER_STRATEGY.mainline_pullback_per_sector_limit < BALANCED_STOCK_FILTER_STRATEGY.mainline_pullback_per_sector_limit
    assert RIGHT_BIASED_STOCK_FILTER_STRATEGY.mainline_low_suck_per_sector_limit < BALANCED_STOCK_FILTER_STRATEGY.mainline_low_suck_per_sector_limit
    assert RIGHT_BIASED_STOCK_FILTER_STRATEGY.mainline_pullback_anchor_gap_max < BALANCED_STOCK_FILTER_STRATEGY.mainline_pullback_anchor_gap_max
    assert RIGHT_BIASED_STOCK_FILTER_STRATEGY.mainline_low_suck_min_vol_ratio > BALANCED_STOCK_FILTER_STRATEGY.mainline_low_suck_min_vol_ratio


def test_build_stock_filter_strategy_allows_named_style_with_overrides():
    strategy = build_stock_filter_strategy(
        "right",
        mainline_pullback_per_sector_limit=5,
    )

    assert strategy.mainline_pullback_per_sector_limit == 5
    assert strategy.mainline_low_suck_per_sector_limit == RIGHT_BIASED_STOCK_FILTER_STRATEGY.mainline_low_suck_per_sector_limit
