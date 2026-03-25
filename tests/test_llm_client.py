# flake8: noqa: E501
import asyncio

from app.services.llm_client import llm_client


class _Recorder:
    def __init__(self):
        self.calls = []

    async def record_call(self, **kwargs):
        self.calls.append(kwargs)


def test_chat_json_with_status_records_disabled_call(monkeypatch):
    async def fake_runtime():
        return {
            "enabled": False,
            "provider": "volcengine",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "",
            "model": "ep-demo",
            "timeout_seconds": 12,
            "temperature": 0.2,
            "max_input_items": 8,
        }

    recorder = _Recorder()
    monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
    monkeypatch.setattr("app.services.llm_client.llm_call_log_service", recorder)

    data, status = asyncio.run(
        llm_client.chat_json_with_status(
            "system",
            {"trade_date": "2026-03-23"},
            scene="stock_pools",
            trade_date="2026-03-23",
        )
    )

    assert data is None
    assert status.status == "disabled"
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["scene"] == "stock_pools"
    assert recorder.calls[0]["trade_date"] == "2026-03-23"


def test_chat_json_with_status_appends_request_label_to_message(monkeypatch):
    async def fake_runtime():
        return {
            "enabled": False,
            "provider": "volcengine",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "",
            "model": "ep-demo",
            "timeout_seconds": 12,
            "temperature": 0.2,
            "max_input_items": 8,
        }

    recorder = _Recorder()
    monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
    monkeypatch.setattr("app.services.llm_client.llm_call_log_service", recorder)

    _data, status = asyncio.run(
        llm_client.chat_json_with_status(
            "system",
            {"trade_date": "2026-03-23"},
            scene="stock_checkup",
            trade_date="2026-03-23",
            request_label="stock_checkup_compact_retry",
        )
    )

    assert status.status == "disabled"
    assert "[stock_checkup_compact_retry]" in status.message
    assert "[stock_checkup_compact_retry]" in recorder.calls[0]["status"].message
