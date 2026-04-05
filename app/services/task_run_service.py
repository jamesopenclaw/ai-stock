"""
任务运行记录服务
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import desc, select

from app.core.database import async_session_factory
from app.models.task_run import TaskRun

TERMINAL_STATUSES = {"success", "failed"}
IDEMPOTENT_STATUSES = {"queued", "running", "retrying", "success"}


def _build_result_summary(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(result, dict):
        return None

    report = result.get("report") or {}
    summary = report.get("summary") or {}
    market_env = report.get("market_env") or {}
    buy_analysis = report.get("buy_analysis") or {}
    sell_analysis = report.get("sell_analysis") or {}
    stock_pools = report.get("stock_pools") or {}

    sell_count = len(sell_analysis.get("sell_positions") or []) + len(sell_analysis.get("reduce_positions") or [])
    candidate_pool_count = (
        int(stock_pools.get("market_watch_count") or 0)
        + int(stock_pools.get("account_executable_count") or 0)
    )

    return {
        "pipeline": result.get("pipeline") or "",
        "today_action": summary.get("today_action") or "",
        "priority_action": summary.get("priority_action") or "",
        "market_env_tag": market_env.get("market_env_tag") or "",
        "market_comment": market_env.get("market_comment") or "",
        "available_buy_count": len(buy_analysis.get("available_buy_points") or []),
        "sell_signal_count": sell_count,
        "candidate_pool_count": candidate_pool_count,
    }


def _serialize_task_run(row: TaskRun) -> Dict[str, Any]:
    result = None
    if row.result_json:
        try:
            result = json.loads(row.result_json)
        except Exception:
            result = None
    return {
        "id": row.id,
        "mode": row.mode,
        "trade_date": row.trade_date,
        "trigger_source": row.trigger_source,
        "status": row.status,
        "attempt_count": int(row.attempt_count or 0),
        "max_attempts": int(row.max_attempts or 1),
        "duration_ms": float(row.duration_ms or 0.0),
        "result": result,
        "result_summary": _build_result_summary(result),
        "last_error": row.last_error or "",
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class TaskRunService:
    """任务运行记录与幂等控制。"""

    async def create_task_run(
        self,
        mode: str,
        trade_date: str,
        *,
        trigger_source: str = "manual",
        max_attempts: int = 1,
        force: bool = False,
    ) -> Dict[str, Any]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TaskRun)
                .where(TaskRun.mode == mode, TaskRun.trade_date == trade_date)
                .order_by(desc(TaskRun.created_at), desc(TaskRun.updated_at))
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest and latest.status in IDEMPOTENT_STATUSES and not force:
                return {
                    "created": False,
                    "run": _serialize_task_run(latest),
                    "reason": "already_finished" if latest.status == "success" else "already_running",
                }

            row = TaskRun(
                id=uuid.uuid4().hex,
                mode=mode,
                trade_date=trade_date,
                trigger_source=trigger_source,
                status="queued",
                attempt_count=0,
                max_attempts=max(1, int(max_attempts)),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return {"created": True, "run": _serialize_task_run(row), "reason": "created"}

    async def get_task_run(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TaskRun).where(TaskRun.id == task_id)
            )
            row = result.scalar_one_or_none()
            return _serialize_task_run(row) if row else None

    async def list_task_runs(self, limit: int = 20) -> list[Dict[str, Any]]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TaskRun)
                .order_by(desc(TaskRun.created_at), desc(TaskRun.updated_at))
                .limit(max(1, min(limit, 100)))
            )
            return [_serialize_task_run(row) for row in result.scalars().all()]

    async def mark_running(self, task_id: str, attempt_count: int) -> Optional[Dict[str, Any]]:
        return await self._update_task_run(
            task_id,
            status="running",
            attempt_count=attempt_count,
            started_at=datetime.utcnow(),
            finished_at=None,
            last_error="",
        )

    async def mark_retrying(self, task_id: str, attempt_count: int, error_message: str) -> Optional[Dict[str, Any]]:
        return await self._update_task_run(
            task_id,
            status="retrying",
            attempt_count=attempt_count,
            last_error=error_message,
            finished_at=None,
        )

    async def mark_success(self, task_id: str, result: Dict[str, Any], started_at: Optional[datetime]) -> Optional[Dict[str, Any]]:
        duration_ms = self._duration_ms(started_at)
        return await self._update_task_run(
            task_id,
            status="success",
            result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
            finished_at=datetime.utcnow(),
            duration_ms=duration_ms,
            last_error="",
        )

    async def mark_failed(
        self,
        task_id: str,
        error_message: str,
        started_at: Optional[datetime],
        attempt_count: int,
    ) -> Optional[Dict[str, Any]]:
        duration_ms = self._duration_ms(started_at)
        return await self._update_task_run(
            task_id,
            status="failed",
            attempt_count=attempt_count,
            last_error=error_message,
            finished_at=datetime.utcnow(),
            duration_ms=duration_ms,
        )

    async def _update_task_run(self, task_id: str, **updates) -> Optional[Dict[str, Any]]:
        async with async_session_factory() as session:
            result = await session.execute(select(TaskRun).where(TaskRun.id == task_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            for key, value in updates.items():
                setattr(row, key, value)
            row.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(row)
            return _serialize_task_run(row)

    @staticmethod
    def _duration_ms(started_at: Optional[datetime]) -> float:
        if started_at is None:
            return 0.0
        return max(0.0, (datetime.utcnow() - started_at).total_seconds() * 1000.0)


task_run_service = TaskRunService()
