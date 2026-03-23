from types import SimpleNamespace

import pytest

from app.services import account_config_service


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _GoodSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeResult(self._row)


class _BrokenSession:
    async def __aenter__(self):
        raise ConnectionError("db down")

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_get_llm_runtime_config_uses_last_good_cache_on_db_error(monkeypatch):
    row = SimpleNamespace(
        llm_enabled=True,
        llm_provider="volcengine",
        llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
        llm_api_key="secret-key",
        llm_model="ep-demo",
        llm_timeout_seconds=15.0,
        llm_temperature=0.3,
        llm_max_input_items=6,
    )

    monkeypatch.setattr(account_config_service, "_last_good_llm_runtime_config", None)
    monkeypatch.setattr(account_config_service, "async_session_factory", lambda: _GoodSession(row))

    runtime = await account_config_service.get_llm_runtime_config()
    assert runtime["enabled"] is True
    assert runtime["provider"] == "volcengine"
    assert runtime["model"] == "ep-demo"
    assert runtime["api_key"] == "secret-key"

    monkeypatch.setattr(account_config_service, "async_session_factory", lambda: _BrokenSession())
    cached_runtime = await account_config_service.get_llm_runtime_config()

    assert cached_runtime == runtime
