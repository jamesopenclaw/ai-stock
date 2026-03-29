"""
任务 API 测试
"""
import pytest

from app.api.v1 import task


class _FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


@pytest.mark.asyncio
async def test_trigger_task_adds_background_job_for_new_run(monkeypatch):
    background_tasks = _FakeBackgroundTasks()
    create_task_calls = []

    async def fake_enqueue_task(mode, trade_date, trigger_source="manual", force=False):
        assert mode == "daily"
        assert trade_date == "2026-03-28"
        assert trigger_source == "manual"
        assert force is False
        return {
            "created": True,
            "reason": "created",
            "task_id": "task-123",
            "trade_date": trade_date,
            "mode": mode,
            "status": "queued",
        }

    async def fake_execute_task_run(task_id):
        assert task_id == "task-123"
        return {"status": "success"}

    def fake_create_task(coro):
        create_task_calls.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(task.scheduler, "enqueue_task", fake_enqueue_task)
    monkeypatch.setattr(task.scheduler, "execute_task_run", fake_execute_task_run)
    monkeypatch.setattr(task.asyncio, "create_task", fake_create_task)

    response = await task.trigger_task(
        task.TaskRequest(trade_date="2026-03-28", mode="daily"),
        background_tasks,
    )

    assert response.status == "started"
    assert response.task_id == "task-123"
    assert len(create_task_calls) == 1
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_trigger_task_returns_duplicate_without_background_job(monkeypatch):
    background_tasks = _FakeBackgroundTasks()

    async def fake_enqueue_task(mode, trade_date, trigger_source="manual", force=False):
        return {
            "created": False,
            "reason": "already_finished",
            "task_id": "task-123",
            "trade_date": trade_date,
            "mode": mode,
            "status": "success",
        }

    monkeypatch.setattr(task.scheduler, "enqueue_task", fake_enqueue_task)

    response = await task.trigger_task(
        task.TaskRequest(trade_date="2026-03-28", mode="daily"),
        background_tasks,
    )

    assert response.status == "duplicate"
    assert response.task_id == "task-123"
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_get_task_status_delegates_to_scheduler(monkeypatch):
    async def fake_get_status(task_id=None, limit=20):
        assert task_id == "task-1"
        assert limit == 5
        return {"status": "ok", "task": {"id": "task-1"}}

    monkeypatch.setattr(task.scheduler, "get_task_status", fake_get_status)

    response = await task.get_task_status(task_id="task-1", limit=5)

    assert response == {"status": "ok", "task": {"id": "task-1"}}
