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
async def test_system_config_for_admin_reads_platform_singleton(monkeypatch):
    async def fake_get_config(account_id=None):
        assert account_id is None
        return {
            "llm_enabled": True,
            "llm_provider": "openai",
            "llm_base_url": "https://api.openai.com/v1",
            "llm_model": "gpt-5-mini",
            "llm_timeout_seconds": 18.0,
            "llm_temperature": 0.3,
            "llm_max_input_items": 6,
            "llm_has_api_key": True,
        }

    monkeypatch.setattr(system, "get_platform_config", fake_get_config)

    response = await system.get_system_config(
        current_user=AuthenticatedUser(
            id="admin-001",
            username="admin",
            display_name="管理员",
            default_account_id="acct-admin",
            role="admin",
            status="active",
        ),
    )

    assert response.code == 200
    assert response.data["llm_provider"] == "openai"


@pytest.mark.asyncio
async def test_system_config_for_non_admin_is_forbidden():
    response = await system.get_system_config(
        current_user=AuthenticatedUser(
            id="user-001",
            username="user1",
            display_name="普通用户",
            default_account_id="acct-001",
            role="user",
            status="active",
        ),
    )

    assert response.code == 403


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


@pytest.mark.asyncio
async def test_llm_daily_stats_for_normal_user_are_scoped_to_current_account(monkeypatch):
    captured = {}

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

    monkeypatch.setattr(system.llm_call_log_service, "get_daily_stats", fake_get_daily_stats)

    response = await system.get_llm_call_daily_stats(
        days=14,
        scene="stock_checkup",
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
        "days": 14,
        "scene": "stock_checkup",
        "status": "success",
        "success": True,
        "account_id": "acct-001",
    }
