"""
认证与权限集成测试
"""
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.main import app, settings
from app.core.config import Settings
from app.core.security import AuthenticatedAccount, AuthenticatedUser, get_current_account, get_current_user


@pytest_asyncio.fixture
async def secured_client(monkeypatch):
    monkeypatch.setattr(Settings, "validate_runtime", lambda _self: None)
    monkeypatch.setattr(settings, "auth_enabled", True)
    transport = httpx.ASGITransport(app=app)
    await app.router.startup()
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        await app.router.shutdown()


@pytest.mark.asyncio
async def test_task_status_route_rejects_normal_user(secured_client):
    async def fake_current_user():
        return AuthenticatedUser(
            id="user-001",
            username="hehq",
            display_name="贺老师",
            default_account_id="acct-001",
            role="user",
            status="active",
        )

    app.dependency_overrides[get_current_user] = fake_current_user

    response = await secured_client.get("/api/v1/task/status")

    assert response.status_code == 403
    assert response.json()["detail"] == "当前用户无管理员权限"


@pytest.mark.asyncio
async def test_account_profile_route_rejects_normal_user_switching_other_account(secured_client, monkeypatch):
    async def fake_current_user():
        return AuthenticatedUser(
            id="user-001",
            username="hehq",
            display_name="贺老师",
            default_account_id="acct-001",
            role="user",
            status="active",
        )

    async def fake_load_active_account_by_id(account_id):
        assert account_id == "acct-999"
        return SimpleNamespace(
            id="acct-999",
            account_code="OTHER-999",
            account_name="别人的账户",
            owner_user_id="user-002",
            status="active",
        )

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr("app.core.security._load_active_account_by_id", fake_load_active_account_by_id)

    response = await secured_client.get(
        "/api/v1/account/profile",
        headers={"X-Account-Id": "acct-999"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前用户无权访问该交易账户"


@pytest.mark.asyncio
async def test_llm_logs_route_scopes_normal_user_to_current_account(secured_client, monkeypatch):
    captured = {}

    async def fake_current_user():
        return AuthenticatedUser(
            id="user-001",
            username="hehq",
            display_name="贺老师",
            default_account_id="acct-001",
            role="user",
            status="active",
        )

    async def fake_current_account():
        return AuthenticatedAccount(
            id="acct-001",
            account_code="HEHQ-001",
            account_name="贺老师的账户",
            owner_user_id="user-001",
            status="active",
        )

    async def fake_list_logs(limit=100, scene=None, status=None, success=None, account_id=None):
        captured["limit"] = limit
        captured["scene"] = scene
        captured["status"] = status
        captured["success"] = success
        captured["account_id"] = account_id
        return [{"id": "log-1", "account_id": account_id}]

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_current_account] = fake_current_account
    monkeypatch.setattr("app.api.v1.system.llm_call_log_service.list_logs", fake_list_logs)

    response = await secured_client.get(
        "/api/v1/system/llm/logs",
        params={"limit": 20, "scene": "sell_point", "status": "success", "success": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 1
    assert captured == {
        "limit": 20,
        "scene": "sell_point",
        "status": "success",
        "success": True,
        "account_id": "acct-001",
    }


@pytest.mark.asyncio
async def test_llm_daily_stats_route_scopes_normal_user_to_current_account(secured_client, monkeypatch):
    captured = {}

    async def fake_current_user():
        return AuthenticatedUser(
            id="user-001",
            username="hehq",
            display_name="贺老师",
            default_account_id="acct-001",
            role="user",
            status="active",
        )

    async def fake_current_account():
        return AuthenticatedAccount(
            id="acct-001",
            account_code="HEHQ-001",
            account_name="贺老师的账户",
            owner_user_id="user-001",
            status="active",
        )

    async def fake_get_daily_stats(days=7, scene=None, status=None, success=None, account_id=None):
        captured["days"] = days
        captured["scene"] = scene
        captured["status"] = status
        captured["success"] = success
        captured["account_id"] = account_id
        return {
            "days": days,
            "daily": [],
            "summary": {"total_tokens_estimated": 0},
            "start_date": "2026-03-24",
            "end_date": "2026-03-30",
            "token_estimate_rule": "ceil(chars / 4)",
        }

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_current_account] = fake_current_account
    monkeypatch.setattr("app.api.v1.system.llm_call_log_service.get_daily_stats", fake_get_daily_stats)

    response = await secured_client.get(
        "/api/v1/system/llm/logs/daily-stats",
        params={"days": 14, "scene": "stock_checkup", "status": "success", "success": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["days"] == 14
    assert captured == {
        "days": 14,
        "scene": "stock_checkup",
        "status": "success",
        "success": True,
        "account_id": "acct-001",
    }
