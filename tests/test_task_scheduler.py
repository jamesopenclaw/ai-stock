"""
任务调度器测试
"""
import pytest

from app.tasks.scheduler import TaskScheduler


@pytest.mark.asyncio
async def test_execute_task_run_retries_then_succeeds(monkeypatch):
    scheduler = TaskScheduler()
    scheduler.RETRY_DELAY_SECONDS = 0

    run_state = {
        "id": "task-1",
        "mode": "sync",
        "trade_date": "2026-03-28",
        "status": "queued",
        "max_attempts": 2,
    }
    calls = []
    execution_count = {"value": 0}

    async def fake_get_task_run(task_id):
        assert task_id == "task-1"
        return dict(run_state)

    async def fake_mark_running(task_id, attempt_count):
        calls.append(("running", task_id, attempt_count))
        return None

    async def fake_mark_retrying(task_id, attempt_count, error_message):
        calls.append(("retrying", task_id, attempt_count, error_message))
        return None

    async def fake_mark_success(task_id, result, started_at):
        calls.append(("success", task_id, result["pipeline"]))
        return None

    async def fake_mark_failed(task_id, error_message, started_at, attempt_count):
        calls.append(("failed", task_id, attempt_count, error_message))
        return None

    async def fake_execute_mode(mode, trade_date):
        execution_count["value"] += 1
        if execution_count["value"] == 1:
            raise RuntimeError("temporary boom")
        return {"trade_date": trade_date, "pipeline": mode}

    monkeypatch.setattr("app.tasks.scheduler.task_run_service.get_task_run", fake_get_task_run)
    monkeypatch.setattr("app.tasks.scheduler.task_run_service.mark_running", fake_mark_running)
    monkeypatch.setattr("app.tasks.scheduler.task_run_service.mark_retrying", fake_mark_retrying)
    monkeypatch.setattr("app.tasks.scheduler.task_run_service.mark_success", fake_mark_success)
    monkeypatch.setattr("app.tasks.scheduler.task_run_service.mark_failed", fake_mark_failed)
    monkeypatch.setattr(scheduler, "_execute_mode", fake_execute_mode)

    result = await scheduler.execute_task_run("task-1")

    assert result["status"] == "success"
    assert execution_count["value"] == 2
    assert ("running", "task-1", 1) in calls
    assert ("retrying", "task-1", 1, "temporary boom") in calls
    assert ("running", "task-1", 2) in calls
    assert ("success", "task-1", "sync") in calls


@pytest.mark.asyncio
async def test_enqueue_task_returns_duplicate_when_existing_task_reused(monkeypatch):
    scheduler = TaskScheduler()

    async def fake_create_task_run(mode, trade_date, trigger_source="manual", max_attempts=1, force=False):
        assert mode == "daily"
        assert trade_date == "2026-03-28"
        assert max_attempts == scheduler.TASK_RETRY_LIMITS["daily"]
        return {
            "created": False,
            "reason": "already_running",
            "run": {
                "id": "task-existing",
                "mode": mode,
                "trade_date": trade_date,
                "status": "running",
            },
        }

    monkeypatch.setattr("app.tasks.scheduler.task_run_service.create_task_run", fake_create_task_run)

    result = await scheduler.enqueue_task("daily", "2026-03-28")

    assert result == {
        "created": False,
        "reason": "already_running",
        "task_id": "task-existing",
        "trade_date": "2026-03-28",
        "mode": "daily",
        "status": "running",
    }
