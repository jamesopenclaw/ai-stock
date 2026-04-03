"""
管理员 API 测试
"""
from types import SimpleNamespace

import pytest

from app.api.v1 import admin as admin_api


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.executed = []
        self.commit_called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        self.executed.append(stmt)
        sql = str(stmt)
        if "FROM users" in sql:
            return _FakeResult(self.user)
        return _FakeResult(None)

    async def commit(self):
        self.commit_called = True


@pytest.mark.asyncio
async def test_reset_user_password_updates_hash_and_revokes_sessions(monkeypatch):
    user = SimpleNamespace(id="user-1", password_hash="old-hash")
    session = _FakeSession(user)

    monkeypatch.setattr(admin_api, "async_session_factory", lambda: session)
    monkeypatch.setattr(admin_api, "hash_password", lambda password: f"hashed::{password}")

    response = await admin_api.reset_user_password(
        "user-1",
        admin_api.ResetUserPasswordRequest(password="new-password"),
    )

    assert response.code == 200
    assert response.data == {"success": True}
    assert user.password_hash == "hashed::new-password"
    assert session.commit_called is True
    assert len(session.executed) == 2
    assert "DELETE FROM user_sessions" in str(session.executed[1])
    assert "user_sessions.user_id" in str(session.executed[1])


@pytest.mark.asyncio
async def test_reset_user_password_returns_404_when_user_missing(monkeypatch):
    session = _FakeSession(None)

    monkeypatch.setattr(admin_api, "async_session_factory", lambda: session)

    response = await admin_api.reset_user_password(
        "missing-user",
        admin_api.ResetUserPasswordRequest(password="new-password"),
    )

    assert response.code == 404
    assert response.message == "用户不存在"
    assert session.commit_called is False
    assert len(session.executed) == 1
