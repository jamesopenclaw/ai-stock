"""
交易账户服务测试
"""
from types import SimpleNamespace

import pytest

from app.models.account_setting import AccountSetting
from app.models.trading_account import TradingAccount
from app.services import trading_account_service


class _FakeScalarResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self):
        self.flush_called = False
        self.account_setting_added_after_flush = False
        self.added = []
        self.refreshed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, AccountSetting):
            self.account_setting_added_after_flush = self.flush_called

    async def flush(self):
        self.flush_called = True

    async def execute(self, _stmt):
        return _FakeScalarResult()

    async def commit(self):
        return None

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.mark.asyncio
async def test_create_trading_account_flushes_before_account_setting(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(trading_account_service, "async_session_factory", lambda: fake_session)

    account = await trading_account_service.create_trading_account(
        "ACC-TEST-001",
        "测试账户",
        owner_user_id="user-1",
    )

    assert isinstance(account, TradingAccount)
    assert fake_session.flush_called is True
    assert fake_session.account_setting_added_after_flush is True
