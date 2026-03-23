"""
决策上下文测试
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.decision_context import DecisionContextService


def test_enrich_holding_time_fields_uses_trade_date():
    """持有天数与可卖状态应按请求 trade_date 计算。"""
    service = DecisionContextService()
    holding = {
        "ts_code": "002463.SZ",
        "buy_date": "2026-03-18",
        "can_sell_today": False,
    }

    enriched = service._enrich_holding_time_fields(holding, "2026-03-23")

    assert enriched["holding_days"] == 5
    assert enriched["can_sell_today"] is True


def test_enrich_holding_time_fields_same_day_is_t1_locked():
    """买入当天持有天数为 0，且仍不可卖。"""
    service = DecisionContextService()
    holding = {
        "ts_code": "002463.SZ",
        "buy_date": "2026-03-23",
    }

    enriched = service._enrich_holding_time_fields(holding, "2026-03-23")

    assert enriched["holding_days"] == 0
    assert enriched["can_sell_today"] is False
