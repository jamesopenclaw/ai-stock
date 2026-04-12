"""
通知服务测试
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models.notification_event import NotificationEvent
from app.models.schemas import NotificationSettingsPayload
from app.services.notification_service import notification_service


class _FakeResult:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _SummarySession:
    def __init__(self, rows):
        self.rows = list(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeResult(rows=self.rows)


class _FakeSession:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        if self.rows:
            rows = list(self.rows)
            compiled = _stmt.compile()
            params = compiled.params
            exclude_priorities = []
            for key, value in params.items():
                if key.startswith("priority_") and isinstance(value, (list, tuple, set)):
                    exclude_priorities.extend([str(item) for item in value])
            if exclude_priorities:
                rows = [row for row in rows if str(getattr(row, "priority", "")) not in set(exclude_priorities)]
            return _FakeResult(rows=rows)
        return _FakeResult(row=self.row)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_upsert_event_skips_disabled_rule_and_resolves_existing(monkeypatch):
    now = datetime.utcnow()
    row = NotificationEvent(
        id="evt-001",
        account_id="acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        status="pending",
        title="旧提醒",
        message="旧提醒",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    session = _FakeSession(row=row)

    async def fake_get_settings(account_id, *, user_id=None):
        return NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001",
            rules={"holding_to_sell": "off"},
            quiet_windows=[],
        )

    async def fake_send_markdown(message, *, webhook_url=None):
        raise AssertionError("disabled event should not push wecom")

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)
    monkeypatch.setattr(notification_service, "get_settings", fake_get_settings)
    monkeypatch.setattr("app.services.notification_service.notify_service.wecom.send_markdown", fake_send_markdown)

    result = await notification_service.upsert_event(
        "acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        title="沪电股份转为建议卖出",
        message="盘中优先退出",
        action_label="看卖点详解",
        action_target_type="sell_analysis",
        action_target_payload={"route": "/sell"},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        trigger_value={"sell_signal_tag": "卖出"},
    )

    assert result is None
    assert row.status == "resolved"
    assert row.resolved_at is not None
    assert session.commits == 1


@pytest.mark.asyncio
async def test_upsert_event_applies_rule_priority_override(monkeypatch):
    session = _FakeSession()

    async def fake_get_settings(account_id, *, user_id=None):
        return NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001",
            rules={"candidate_to_executable": "low"},
            quiet_windows=[],
        )

    async def fake_send_markdown(message, *, webhook_url=None):
        raise AssertionError("low priority event should not push wecom")

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)
    monkeypatch.setattr(notification_service, "get_settings", fake_get_settings)
    monkeypatch.setattr("app.services.notification_service.notify_service.wecom.send_markdown", fake_send_markdown)

    result = await notification_service.upsert_event(
        "acct-001",
        user_id="user-001",
        event_type="candidate_to_executable",
        category="candidate",
        priority="medium",
        title="特锐德进入可执行名单",
        message="当前已进入账户可参与池",
        action_label="看买点详解",
        action_target_type="buy_analysis",
        action_target_payload={"route": "/buy"},
        entity_type="stock",
        entity_code="300001.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:candidate_to_executable:300001.SZ:2026-04-04",
        trigger_value={"buy_signal_tag": "可买"},
    )

    assert result is not None
    assert result.priority.value == "low"
    assert len(session.added) == 1
    assert session.added[0].priority == "low"


@pytest.mark.asyncio
async def test_apply_settings_to_existing_events_updates_priorities_and_resolves(monkeypatch):
    now = datetime.utcnow()
    sell_row = NotificationEvent(
        id="evt-sell",
        account_id="acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        status="pending",
        title="卖出提醒",
        message="卖出提醒",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    candidate_row = NotificationEvent(
        id="evt-candidate",
        account_id="acct-001",
        user_id="user-001",
        event_type="candidate_near_trigger",
        category="candidate",
        priority="medium",
        status="read",
        title="候选提醒",
        message="候选提醒",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="300001.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:candidate_near_trigger:300001.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    session = _FakeSession(rows=[sell_row, candidate_row])

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)

    updated = await notification_service.apply_settings_to_existing_events(
        "acct-001",
        {"holding_to_sell": "off", "candidate_near_trigger": "low"},
    )

    assert updated == 2
    assert sell_row.status == "resolved"
    assert sell_row.resolved_at is not None
    assert candidate_row.priority == "low"
    assert session.commits == 1


def test_get_active_quiet_window_handles_normal_and_cross_day_windows():
    daytime = notification_service.get_active_quiet_window(
        [{"start": "11:30", "end": "13:00"}],
        now=datetime(2026, 4, 4, 11, 45),
    )
    overnight = notification_service.get_active_quiet_window(
        [{"start": "22:00", "end": "09:30"}],
        now=datetime(2026, 4, 4, 8, 15),
    )
    outside = notification_service.get_active_quiet_window(
        [{"start": "11:30", "end": "13:00"}],
        now=datetime(2026, 4, 4, 14, 0),
    )

    assert daytime == {"start": "11:30", "end": "13:00"}
    assert overnight == {"start": "22:00", "end": "09:30"}
    assert outside is None


@pytest.mark.asyncio
async def test_upsert_event_suppresses_wecom_inside_quiet_window(monkeypatch):
    session = _FakeSession()
    send_calls = []

    async def fake_get_settings(account_id, *, user_id=None):
        return NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001",
            rules={"holding_to_sell": "high"},
            quiet_windows=[{"start": "11:30", "end": "13:00"}],
        )

    async def fake_send_markdown(message, *, webhook_url=None):
        send_calls.append((message, webhook_url))

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)
    monkeypatch.setattr(notification_service, "get_settings", fake_get_settings)
    monkeypatch.setattr(
        notification_service,
        "get_active_quiet_window",
        lambda quiet_windows, now=None: {"start": "11:30", "end": "13:00"},
    )
    monkeypatch.setattr("app.services.notification_service.notify_service.wecom.send_markdown", fake_send_markdown)

    result = await notification_service.upsert_event(
        "acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        title="沪电股份转为建议卖出",
        message="盘中优先退出",
        action_label="看卖点详解",
        action_target_type="sell_analysis",
        action_target_payload={"route": "/sell"},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        trigger_value={"sell_signal_tag": "卖出"},
    )

    assert result is not None
    assert send_calls == []


@pytest.mark.asyncio
async def test_get_summary_marks_quiet_window_active(monkeypatch):
    now = datetime.utcnow()
    row = NotificationEvent(
        id="evt-summary",
        account_id="acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        status="pending",
        title="卖出提醒",
        message="盘中优先退出",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    session = _SummarySession([row])

    async def fake_get_settings(account_id, *, user_id=None):
        return NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001",
            rules={"holding_to_sell": "high"},
            quiet_windows=[{"start": "11:30", "end": "13:00"}],
        )

    async def fake_reactivate(account_id):
        return None

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)
    monkeypatch.setattr(notification_service, "get_settings", fake_get_settings)
    monkeypatch.setattr(notification_service, "reactivate_expired_snoozed", fake_reactivate)
    monkeypatch.setattr(
        notification_service,
        "get_active_quiet_window",
        lambda quiet_windows, now=None: {"start": "11:30", "end": "13:00"},
    )

    summary = await notification_service.get_summary("acct-001")

    assert summary.unread_count == 1
    assert summary.critical_count == 1
    assert len(summary.latest_items) == 1
    assert summary.quiet_window_active is True
    assert summary.quiet_window_label == "11:30-13:00"


@pytest.mark.asyncio
async def test_mark_all_read_excludes_high_priority(monkeypatch):
    now = datetime.utcnow()
    high_row = NotificationEvent(
        id="evt-high",
        account_id="acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        status="pending",
        title="高优先级提醒",
        message="高优先级提醒",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    low_row = NotificationEvent(
        id="evt-low",
        account_id="acct-001",
        user_id="user-001",
        event_type="candidate_to_executable",
        category="candidate",
        priority="low",
        status="pending",
        title="低优先级提醒",
        message="低优先级提醒",
        action_label="查看",
        action_target_type="route",
        action_target_payload={},
        entity_type="stock",
        entity_code="300001.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:candidate_to_executable:300001.SZ:2026-04-04",
        created_at=now,
        updated_at=now,
    )
    session = _FakeSession(rows=[high_row, low_row])

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)

    updated = await notification_service.mark_all_read(
        "acct-001",
        exclude_priorities=["high"],
    )

    assert updated == 1
    assert high_row.status == "pending"
    assert low_row.status == "read"


@pytest.mark.asyncio
async def test_upsert_event_pushes_account_specific_wecom_webhook(monkeypatch):
    session = _FakeSession()
    send_calls = []

    async def fake_get_settings(account_id, *, user_id=None):
        return NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-xyz",
            rules={"holding_to_sell": "high"},
            quiet_windows=[],
        )

    async def fake_send_markdown(message, *, webhook_url=None):
        send_calls.append({"message": message, "webhook_url": webhook_url})
        return True

    monkeypatch.setattr("app.services.notification_service.async_session_factory", lambda: session)
    monkeypatch.setattr(notification_service, "get_settings", fake_get_settings)
    monkeypatch.setattr(
        notification_service,
        "get_active_quiet_window",
        lambda quiet_windows, now=None: None,
    )
    monkeypatch.setattr("app.services.notification_service.notify_service.wecom.send_markdown", fake_send_markdown)

    result = await notification_service.upsert_event(
        "acct-001",
        user_id="user-001",
        event_type="holding_to_sell",
        category="holding",
        priority="high",
        title="沪电股份转为建议卖出",
        message="盘中优先退出",
        action_label="看卖点详解",
        action_target_type="sell_analysis",
        action_target_payload={"route": "/sell"},
        entity_type="stock",
        entity_code="002463.SZ",
        trade_date="2026-04-04",
        dedupe_key="acct-001:holding_to_sell:002463.SZ:2026-04-04",
        trigger_value={"sell_signal_tag": "卖出"},
    )

    assert result is not None
    assert send_calls == [
        {
            "message": "## 盘中提醒\n\n**沪电股份转为建议卖出**\n\n盘中优先退出",
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-xyz",
        }
    ]


def test_notification_settings_payload_requires_webhook_when_wecom_enabled():
    with pytest.raises(ValidationError):
        NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=True,
            wecom_webhook_url="",
            rules={},
            quiet_windows=[],
        )


def test_notification_settings_payload_rejects_invalid_wecom_webhook():
    with pytest.raises(ValidationError):
        NotificationSettingsPayload(
            in_app_enabled=True,
            wecom_enabled=False,
            wecom_webhook_url="https://example.com/webhook",
            rules={},
            quiet_windows=[],
        )


@pytest.mark.asyncio
async def test_send_wecom_test_message_uses_explicit_webhook(monkeypatch):
    send_calls = []

    async def fake_send_markdown(message, *, webhook_url=None):
        send_calls.append({"message": message, "webhook_url": webhook_url})
        return True

    monkeypatch.setattr("app.services.notification_service.notify_service.wecom.send_markdown", fake_send_markdown)

    success = await notification_service.send_wecom_test_message(
        "acct-001",
        account_name="测试账户",
        user_id="user-001",
        webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-test",
    )

    assert success is True
    assert send_calls[0]["webhook_url"] == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-test"
    assert "测试账户" in send_calls[0]["message"]
