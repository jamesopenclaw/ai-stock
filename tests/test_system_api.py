"""
系统 API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import system  # noqa: E402
from app.core.security import AuthenticatedAccount, AuthenticatedUser  # noqa: E402


@pytest.mark.asyncio
async def test_llm_logs_for_normal_user_are_scoped_to_current_account(monkeypatch):
    captured = {}

    async def fake_list_logs(limit=100, scene=None, status=None, success=None, account_id=None):
        captured["limit"] = limit
        captured["scene"] = scene
        captured["status"] = status
        captured["success"] = success
        captured["account_id"] = account_id
        return []

    monkeypatch.setattr(system.llm_call_log_service, "list_logs", fake_list_logs)

    response = await system.get_llm_call_logs(
        limit=20,
        scene="sell_point",
        status="success",
        success=True,
        current_user=AuthenticatedUser(
            id="user-001",
            username="user1",
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
    assert captured == {
        "limit": 20,
        "scene": "sell_point",
        "status": "success",
        "success": True,
        "account_id": "acct-001",
    }


@pytest.mark.asyncio
async def test_llm_logs_for_admin_can_read_all_accounts(monkeypatch):
    captured = {}

    async def fake_list_logs(limit=100, scene=None, status=None, success=None, account_id=None):
        captured["account_id"] = account_id
        return [{"id": "log-1", "account_id": "acct-002"}]

    monkeypatch.setattr(system.llm_call_log_service, "list_logs", fake_list_logs)

    response = await system.get_llm_call_logs(
        current_user=AuthenticatedUser(
            id="admin-001",
            username="admin",
            display_name="管理员",
            default_account_id="acct-admin",
            role="admin",
            status="active",
        ),
        current_account=AuthenticatedAccount(
            id="acct-admin",
            account_code="ADMIN",
            account_name="管理员账户",
            owner_user_id="admin-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data["total"] == 1
    assert captured["account_id"] is None
