"""
决策上下文测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    AccountInput,
    AccountPosition,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    StockInput,
)
from app.services.decision_context import (  # noqa: E402
    AccountDecisionContext,
    DecisionContextService,
    SharedDecisionContext,
)


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

    async def fake_holdings(_account_id=None, _trade_date=None):
        return []

    async def fake_account(_holdings, _account_id=None, _trade_date=None):
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
    assert context.shared_context.selection_trade_date == "2026-03-20"


@pytest.mark.asyncio
async def test_build_shared_context_does_not_load_account_state(monkeypatch):
    """共享上下文不应依赖持仓或账户信息。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=60,
        sentiment_score=58,
        overall_score=59,
    )

    async def should_not_load_holdings(*args, **kwargs):
        raise AssertionError("shared context should not load holdings")

    async def should_not_build_account(*args, **kwargs):
        raise AssertionError("shared context should not build account input")

    monkeypatch.setattr(service, "get_holdings_from_db", should_not_load_holdings)
    monkeypatch.setattr(service, "build_account_input_from_holdings", should_not_build_account)
    async def fake_resolve_selection_trade_date(_trade_date):
        return "2026-03-24"

    monkeypatch.setattr(
        service,
        "_resolve_selection_trade_date",
        fake_resolve_selection_trade_date,
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_env_service.get_current_env",
        lambda _trade_date: market_env,
    )

    async def fake_get_sector_scan_snapshot(_trade_date):
        return {"snapshot": True}

    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_snapshot_service.get_snapshot",
        fake_get_sector_scan_snapshot,
    )
    monkeypatch.setattr(
        service,
        "get_candidate_stocks",
        lambda *_args, **_kwargs: (
            [
                StockInput(
                    ts_code="000001.SZ",
                    stock_name="平安银行",
                    sector_name="银行",
                    close=12.5,
                    change_pct=1.2,
                    turnover_rate=1.8,
                    amount=123456,
                    high=12.7,
                    low=12.2,
                    open=12.3,
                    pre_close=12.35,
                )
            ],
            "2026-03-24",
        ),
    )

    context = await service.build_shared_context("2026-03-24")

    assert context.trade_date == "2026-03-24"
    assert context.selection_trade_date == "2026-03-24"
    assert len(context.stocks) == 1


def test_compose_context_merges_holdings_only_when_requested(monkeypatch):
    """完整上下文只在显式要求时把持仓并回候选池。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=60,
        sentiment_score=58,
        overall_score=59,
    )
    shared_stock = StockInput(
        ts_code="000001.SZ",
        stock_name="平安银行",
        sector_name="银行",
        close=12.5,
        change_pct=1.2,
        turnover_rate=1.8,
        amount=123456,
        high=12.7,
        low=12.2,
        open=12.3,
        pre_close=12.35,
    )
    merged_stock = StockInput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="PCB",
        close=30.5,
        change_pct=0.5,
        turnover_rate=2.1,
        amount=234567,
        high=31.0,
        low=30.1,
        open=30.3,
        pre_close=30.35,
    )
    shared_context = SharedDecisionContext(
        trade_date="2026-03-24",
        selection_trade_date="2026-03-24",
        resolved_stock_trade_date="2026-03-24",
        sector_scan_trade_date=None,
        sector_scan_resolved_trade_date=None,
        market_env=market_env,
        realtime_market_env=market_env,
        sector_scan={"snapshot": True},
        stocks=[shared_stock],
    )
    account_context = AccountDecisionContext(
        trade_date="2026-03-24",
        account_id="account-1",
        holdings_list=[{"ts_code": "002463.SZ"}],
        holdings=[
            AccountPosition(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                holding_qty=100,
                cost_price=30.0,
                market_price=30.5,
                pnl_pct=1.67,
                holding_market_value=3050.0,
                buy_date="2026-03-20",
                can_sell_today=True,
            )
        ],
        account=AccountInput(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )

    monkeypatch.setattr(
        "app.services.decision_context.merge_holdings_into_candidate_stocks",
        lambda trade_date, stocks, holdings: [*stocks, merged_stock],
    )

    original_merge = service.compose_context(shared_context, account_context, include_holdings=False)
    merged = service.compose_context(shared_context, account_context, include_holdings=True)

    assert [stock.ts_code for stock in original_merge.stocks] == ["000001.SZ"]
    assert [stock.ts_code for stock in merged.stocks] == ["000001.SZ", "002463.SZ"]
    assert [stock.ts_code for stock in original_merge.shared_context.stocks] == ["000001.SZ"]
    assert merged.shared_context.stocks == [shared_stock]
