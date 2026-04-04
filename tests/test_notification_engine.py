"""
通知引擎测试
"""
from types import SimpleNamespace

import pytest

from app.models.schemas import BuySignalTag, MarketEnvTag, SellSignalTag, StockPoolTag
from app.services.notification_engine import NotificationEngine


@pytest.mark.asyncio
async def test_refresh_active_accounts_refreshes_each_active_account(monkeypatch):
    engine = NotificationEngine()
    captured = []

    async def fake_list_active_accounts():
        return [
            ("acct-001", "user-001"),
            ("acct-002", None),
        ]

    async def fake_refresh(account_id, *, user_id=None, trade_date=None, force=False):
        captured.append(
            {
                "account_id": account_id,
                "user_id": user_id,
                "trade_date": trade_date,
                "force": force,
            }
        )

    monkeypatch.setattr(engine, "list_active_accounts", fake_list_active_accounts)
    monkeypatch.setattr(engine, "refresh_account_events", fake_refresh)

    refreshed = await engine.refresh_active_accounts(
        trade_date="2026-04-04",
        force=True,
    )

    assert refreshed == 2
    assert captured == [
        {
            "account_id": "acct-001",
            "user_id": "user-001",
            "trade_date": "2026-04-04",
            "force": True,
        },
        {
            "account_id": "acct-002",
            "user_id": None,
            "trade_date": "2026-04-04",
            "force": True,
        },
    ]


def _build_bundle():
    return SimpleNamespace(
        context=SimpleNamespace(
            market_env=SimpleNamespace(market_env_tag=MarketEnvTag.DEFENSE),
        ),
        buy_analysis=SimpleNamespace(
            available_buy_points=[
                SimpleNamespace(
                    ts_code="300001.SZ",
                    stock_name="特锐德",
                    stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE.value,
                    buy_trigger_gap_pct=1.6,
                    buy_comment="进入观察后的可执行名单",
                    buy_data_source="realtime_demo",
                    buy_signal_tag=BuySignalTag.CAN_BUY,
                )
            ],
        ),
        sell_analysis=SimpleNamespace(
            hold_positions=[],
            reduce_positions=[
                SimpleNamespace(
                    ts_code="002463.SZ",
                    stock_name="沪电股份",
                    sell_signal_tag=SellSignalTag.REDUCE,
                    sell_reason="分时走弱",
                    sell_trigger_cond="跌破承接位",
                    data_source="realtime_demo",
                )
            ],
            sell_positions=[],
        ),
    )


@pytest.mark.asyncio
async def test_refresh_account_events_only_emits_on_transition(monkeypatch):
    engine = NotificationEngine()
    emitted = []
    resolved = {}

    async def fake_build_full_decision(*args, **kwargs):
        return _build_bundle()

    async def fake_sync_states(account_id, *, state_type, trade_date, states):
        assert account_id == "acct-001"
        assert trade_date == "2026-04-04"
        if state_type == engine.STATE_TYPE_MARKET:
            return {
                engine.MARKET_STATE_KEY: SimpleNamespace(previous_rank=1, current_rank=2, current_value="防守"),
            }
        if state_type == engine.STATE_TYPE_HOLDING:
            return {
                "holding:002463.SZ": SimpleNamespace(previous_rank=0, current_rank=1, current_value="减仓"),
            }
        if state_type == engine.STATE_TYPE_CANDIDATE:
            return {
                "candidate:300001.SZ": SimpleNamespace(previous_rank=0, current_rank=1, current_value="executable"),
            }
        return {
            engine.REALTIME_STATE_KEY: SimpleNamespace(previous_rank=0, current_rank=0, current_value="healthy"),
        }

    async def fake_upsert_event(account_id, **kwargs):
        emitted.append({"account_id": account_id, "event_type": kwargs["event_type"]})
        return None

    async def fake_resolve(account_id, *, active_dedupe_keys, event_types):
        resolved["account_id"] = account_id
        resolved["active_dedupe_keys"] = active_dedupe_keys
        resolved["event_types"] = event_types
        return 0

    monkeypatch.setattr("app.services.notification_engine.decision_flow_service.build_full_decision", fake_build_full_decision)
    monkeypatch.setattr("app.services.notification_engine.notification_state_service.sync_states", fake_sync_states)
    monkeypatch.setattr("app.services.notification_engine.notification_service.upsert_event", fake_upsert_event)
    monkeypatch.setattr("app.services.notification_engine.notification_service.resolve_inactive_events", fake_resolve)
    monkeypatch.setattr("app.services.notification_engine.market_data_gateway.should_use_realtime_quote", lambda trade_date: False)

    await engine.refresh_account_events("acct-001", user_id="user-001", trade_date="2026-04-04", force=True)

    assert emitted == [
        {"account_id": "acct-001", "event_type": "market_env_downgraded"},
        {"account_id": "acct-001", "event_type": "holding_to_reduce"},
        {"account_id": "acct-001", "event_type": "candidate_to_executable"},
    ]
    assert resolved["account_id"] == "acct-001"
    assert resolved["active_dedupe_keys"] == {
        "acct-001:market_env_downgraded:market:2026-04-04",
        "acct-001:holding_to_reduce:002463.SZ:2026-04-04",
        "acct-001:candidate_to_executable:300001.SZ:2026-04-04",
    }


@pytest.mark.asyncio
async def test_refresh_account_events_does_not_reemit_stable_state(monkeypatch):
    engine = NotificationEngine()
    emitted = []
    resolved = {}

    async def fake_build_full_decision(*args, **kwargs):
        return _build_bundle()

    async def fake_sync_states(account_id, *, state_type, trade_date, states):
        if state_type == engine.STATE_TYPE_MARKET:
            return {
                engine.MARKET_STATE_KEY: SimpleNamespace(previous_rank=2, current_rank=2, current_value="防守"),
            }
        if state_type == engine.STATE_TYPE_HOLDING:
            return {
                "holding:002463.SZ": SimpleNamespace(previous_rank=1, current_rank=1, current_value="减仓"),
            }
        if state_type == engine.STATE_TYPE_CANDIDATE:
            return {
                "candidate:300001.SZ": SimpleNamespace(previous_rank=1, current_rank=1, current_value="executable"),
            }
        return {
            engine.REALTIME_STATE_KEY: SimpleNamespace(previous_rank=0, current_rank=0, current_value="healthy"),
        }

    async def fake_upsert_event(account_id, **kwargs):
        emitted.append(kwargs["event_type"])
        return None

    async def fake_resolve(account_id, *, active_dedupe_keys, event_types):
        resolved["active_dedupe_keys"] = active_dedupe_keys
        return 0

    monkeypatch.setattr("app.services.notification_engine.decision_flow_service.build_full_decision", fake_build_full_decision)
    monkeypatch.setattr("app.services.notification_engine.notification_state_service.sync_states", fake_sync_states)
    monkeypatch.setattr("app.services.notification_engine.notification_service.upsert_event", fake_upsert_event)
    monkeypatch.setattr("app.services.notification_engine.notification_service.resolve_inactive_events", fake_resolve)
    monkeypatch.setattr("app.services.notification_engine.market_data_gateway.should_use_realtime_quote", lambda trade_date: False)

    await engine.refresh_account_events("acct-001", user_id="user-001", trade_date="2026-04-04", force=True)

    assert emitted == []
    assert resolved["active_dedupe_keys"] == {
        "acct-001:market_env_downgraded:market:2026-04-04",
        "acct-001:holding_to_reduce:002463.SZ:2026-04-04",
        "acct-001:candidate_to_executable:300001.SZ:2026-04-04",
    }
