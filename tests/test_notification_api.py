"""
通知 API 测试
"""
import pytest

from app.api.v1 import notification
from app.core.security import AuthenticatedAccount, AuthenticatedUser
from app.models.schemas import NotificationListResponse, NotificationSettingsPayload, NotificationSummaryResponse


@pytest.mark.asyncio
async def test_list_notifications_reads_scoped_events(monkeypatch):
    captured = {}

    async def fake_list_events(account_id, *, status=None, category=None, priority=None, limit=20):
        captured["list"] = {
            "account_id": account_id,
            "status": status,
            "category": category,
            "priority": priority,
            "limit": limit,
        }
        return NotificationListResponse()

    monkeypatch.setattr(notification.notification_service, "list_events", fake_list_events)

    response = await notification.list_notifications(
        limit=30,
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert captured == {
        "list": {
            "account_id": "acct-001",
            "status": None,
            "category": None,
            "priority": None,
            "limit": 30,
        },
    }


@pytest.mark.asyncio
async def test_list_notifications_passes_pending_status_when_explicit(monkeypatch):
    captured = {}

    async def fake_list_events(account_id, *, status=None, category=None, priority=None, limit=20):
        captured["list"] = {
            "account_id": account_id,
            "status": status,
            "category": category,
            "priority": priority,
            "limit": limit,
        }
        return NotificationListResponse()

    monkeypatch.setattr(notification.notification_service, "list_events", fake_list_events)

    response = await notification.list_notifications(
        status=notification.NotificationStatus.PENDING,
        limit=20,
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert captured["list"]["status"] == "pending"


@pytest.mark.asyncio
async def test_notification_summary_returns_service_payload(monkeypatch):
    async def fake_summary(account_id):
        assert account_id == "acct-001"
        return NotificationSummaryResponse(
            unread_count=3,
            critical_count=1,
            latest_items=[],
            quiet_window_active=False,
            quiet_window_label=None,
        )

    monkeypatch.setattr(notification.notification_service, "get_summary", fake_summary)

    response = await notification.get_notification_summary(
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data == {
        "unread_count": 3,
        "critical_count": 1,
        "latest_items": [],
        "quiet_window_active": False,
        "quiet_window_label": None,
    }


@pytest.mark.asyncio
async def test_update_notification_settings_delegates_to_service(monkeypatch):
    captured = {}

    async def fake_update(account_id, payload, *, user_id=None):
        captured["account_id"] = account_id
        captured["user_id"] = user_id
        captured["payload"] = payload
        return payload

    monkeypatch.setattr(notification.notification_service, "update_settings", fake_update)

    payload = NotificationSettingsPayload(
        in_app_enabled=True,
        wecom_enabled=True,
        wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acct-001",
        rules={"holding_to_sell": "high"},
        quiet_windows=[{"start": "11:35", "end": "12:55"}],
    )
    response = await notification.update_notification_settings(
        payload,
        current_user=AuthenticatedUser(
            id="user-001",
            username="user",
            display_name="普通用户",
            default_account_id="acct-001",
            role="user",
            status="active",
        ),
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert captured["account_id"] == "acct-001"
    assert captured["user_id"] == "user-001"
    assert captured["payload"] == payload


@pytest.mark.asyncio
async def test_read_all_notifications_passes_exclude_priorities(monkeypatch):
    captured = {}

    async def fake_mark_all_read(account_id, **kwargs):
        captured["account_id"] = account_id
        captured.update(kwargs)
        return 2

    monkeypatch.setattr(notification.notification_service, "mark_all_read", fake_mark_all_read)

    response = await notification.read_all_notifications(
        notification.NotificationReadRequest(exclude_priorities=["high"]),
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data == {"updated": 2}
    assert captured == {
        "account_id": "acct-001",
        "ids": None,
        "status": None,
        "category": None,
        "priority": None,
        "exclude_priorities": ["high"],
    }


@pytest.mark.asyncio
async def test_test_notification_wecom_delegates_to_service(monkeypatch):
    captured = {}

    async def fake_send_test(account_id, *, account_name, user_id=None, webhook_url=""):
        captured["account_id"] = account_id
        captured["account_name"] = account_name
        captured["user_id"] = user_id
        captured["webhook_url"] = webhook_url
        return True

    monkeypatch.setattr(notification.notification_service, "send_wecom_test_message", fake_send_test)

    response = await notification.test_notification_wecom(
        notification.NotificationWecomTestRequest(
            webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
        ),
        current_user=AuthenticatedUser(
            id="user-001",
            username="user",
            display_name="普通用户",
            default_account_id="acct-001",
            role="user",
            status="active",
        ),
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data == {"success": True}
    assert captured == {
        "account_id": "acct-001",
        "account_name": "测试账户",
        "user_id": "user-001",
        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key",
    }
