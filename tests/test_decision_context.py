"""
决策上下文测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    AccountInput,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
)
from app.services.decision_context import DecisionContextService  # noqa: E402


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


@pytest.mark.asyncio
async def test_resolve_selection_trade_date_uses_sector_snapshot_lookup(monkeypatch):
    service = DecisionContextService()

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-20"

    monkeypatch.setattr(
        "app.services.decision_context.resolve_snapshot_lookup_trade_date",
        fake_resolve_snapshot_lookup_trade_date,
    )

    assert await service._resolve_selection_trade_date("2026-03-24") == "2026-03-20"


@pytest.mark.asyncio
async def test_build_context_passes_market_env_to_sector_scan(monkeypatch):
    """构建上下文时，应先取市场环境并传给板块扫描。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=70,
        sentiment_score=82,
        overall_score=77,
    )
    captured = {}

    async def fake_holdings(_trade_date=None):
        return []

    async def fake_account(_holdings, _trade_date=None):
        return AccountInput(
            total_asset=100000,
            available_cash=100000,
            total_position_ratio=0.0,
            holding_count=0,
            today_new_buy_count=0,
        )

    monkeypatch.setattr(service, "get_holdings_from_db", fake_holdings)
    monkeypatch.setattr(
        service,
        "build_account_input_from_holdings",
        fake_account,
    )
    market_env_calls = []

    def fake_get_current_env(_trade_date):
        market_env_calls.append(_trade_date)
        return market_env

    monkeypatch.setattr(
        "app.services.decision_context.market_env_service.get_current_env",
        fake_get_current_env,
    )
    async def fake_get_sector_scan_snapshot(_trade_date):
        return None

    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_snapshot_service.get_snapshot",
        fake_get_sector_scan_snapshot,
    )
    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_service.scan",
        lambda trade_date, limit_output=False, market_env=None: (
            captured.update(
                {
                    "trade_date": trade_date,
                    "limit_output": limit_output,
                    "market_env": market_env,
                }
            )
            or {"ok": True}
        ),
    )
    monkeypatch.setattr(
        service,
        "get_candidate_stocks",
        lambda *_args, **_kwargs: ([], "2026-03-20"),
    )

    async def fake_resolve_selection_trade_date(_trade_date):
        return "2026-03-20"

    monkeypatch.setattr(
        service,
        "_resolve_selection_trade_date",
        fake_resolve_selection_trade_date,
    )

    context = await service.build_context("2026-03-23")

    assert captured["trade_date"] == "2026-03-20"
    assert captured["limit_output"] is False
    assert captured["market_env"] == market_env
    assert market_env_calls == ["2026-03-20", "2026-03-23"]
    assert context.market_env == market_env
    assert context.realtime_market_env == market_env
    assert context.resolved_stock_trade_date == "2026-03-20"
    assert context.sector_scan_trade_date is None
    assert context.sector_scan_resolved_trade_date is None
