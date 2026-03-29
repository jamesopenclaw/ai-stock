"""
认证 API 测试
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import auth
from app.core.security import AuthenticatedAccount, AuthenticatedUser, get_current_account, require_admin


@pytest.mark.asyncio
async def test_login_returns_401_for_invalid_credentials(monkeypatch):
    async def fake_authenticate_user(username, password):
        assert username == "demo"
        assert password == "bad-password"
        return None

    monkeypatch.setattr(auth, "authenticate_user", fake_authenticate_user)

    response = await auth.login(auth.LoginRequest(username="demo", password="bad-password"))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_tokens_for_valid_user(monkeypatch):
    fake_user = SimpleNamespace(
        id="user-1",
        username="admin",
        display_name="管理员",
        default_account_id="account-1",
        role="admin",
        status="active",
    )

    async def fake_authenticate_user(username, password):
        assert username == "admin"
        assert password == "good-password"
        return fake_user

    async def fake_create_refresh_session(user_id):
        assert user_id == "user-1"
        from datetime import datetime, timedelta, timezone

        return "refresh-token", datetime.now(timezone.utc) + timedelta(days=7)

    monkeypatch.setattr(auth, "authenticate_user", fake_authenticate_user)
    monkeypatch.setattr(auth, "create_access_token", lambda user: f"access-for-{user.id}")
    monkeypatch.setattr(auth, "create_refresh_session", fake_create_refresh_session)
    monkeypatch.setattr(
        auth,
        "get_user_default_account",
        lambda user_id, default_account_id=None: __import__("asyncio").sleep(
            0,
            result=SimpleNamespace(
                id="account-1",
                account_code="DEFAULT-001",
                account_name="默认账户",
                owner_user_id="user-1",
                status="active",
            ),
        ),
    )

    response = await auth.login(auth.LoginRequest(username="admin", password="good-password"))

    assert response.code == 200
    assert response.data["access_token"] == "access-for-user-1"
    assert response.data["refresh_token"] == "refresh-token"
    assert response.data["user"]["role"] == "admin"
    assert response.data["account"]["account_code"] == "DEFAULT-001"


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin_user():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(
            AuthenticatedUser(
                id="user-1",
                username="demo",
                display_name="演示用户",
                role="user",
                status="active",
            )
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_account_allows_admin_to_switch(monkeypatch):
    fake_account = SimpleNamespace(
        id="account-2",
        account_code="ACC002",
        account_name="演示账户",
        owner_user_id="user-2",
        status="active",
    )

    async def fake_load_account(account_id):
        assert account_id == "account-2"
        return fake_account

    monkeypatch.setattr("app.core.security._load_active_account_by_id", fake_load_account)

    account = await get_current_account(
        AuthenticatedUser(
            id="admin-1",
            username="admin",
            display_name="管理员",
            default_account_id="account-1",
            role="admin",
            status="active",
        ),
        requested_account_id="account-2",
    )

    assert account == AuthenticatedAccount(
        id="account-2",
        account_code="ACC002",
        account_name="演示账户",
        owner_user_id="user-2",
        status="active",
    )


@pytest.mark.asyncio
async def test_get_current_account_rejects_user_switching_other_account(monkeypatch):
    fake_account = SimpleNamespace(
        id="account-9",
        account_code="ACC009",
        account_name="别人的账户",
        owner_user_id="other-user",
        status="active",
    )

    async def fake_load_account(account_id):
        assert account_id == "account-9"
        return fake_account

    monkeypatch.setattr("app.core.security._load_active_account_by_id", fake_load_account)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_account(
            AuthenticatedUser(
                id="user-1",
                username="demo",
                display_name="演示用户",
                default_account_id="account-1",
                role="user",
                status="active",
            ),
            requested_account_id="account-9",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_me_returns_resolved_current_account():
    response = await auth.me(
        current_user=AuthenticatedUser(
            id="admin-1",
            username="admin",
            display_name="管理员",
            default_account_id="account-1",
            role="admin",
            status="active",
        ),
        current_account=AuthenticatedAccount(
            id="account-2",
            account_code="ACC002",
            account_name="演示账户",
            owner_user_id="user-2",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data["account"]["id"] == "account-2"
    assert response.data["account"]["account_code"] == "ACC002"
