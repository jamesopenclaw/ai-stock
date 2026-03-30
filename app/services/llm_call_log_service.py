"""
LLM 调用记录服务
"""
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, select

from app.core.database import async_session_factory
from app.models.llm_call_log import LlmCallLog
from app.models.schemas import LlmCallStatus


class LlmCallLogService:
    """记录并查询 LLM 调用。"""

    def _normalize_account_id(self, account_id: Optional[str]) -> str:
        return str(account_id or "").strip()

    def _estimate_tokens(self, chars: int) -> int:
        normalized = max(0, int(chars or 0))
        if normalized <= 0:
            return 0
        return math.ceil(normalized / 4)

    async def record_call(
        self,
        *,
        scene: str,
        account_id: Optional[str] = None,
        trade_date: str = "",
        provider: str = "",
        model: str = "",
        status: LlmCallStatus,
        request_chars: int = 0,
        response_chars: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        try:
            normalized_account_id = self._normalize_account_id(account_id)
            async with async_session_factory() as session:
                session.add(
                    LlmCallLog(
                        scene=scene or "",
                        account_id=normalized_account_id,
                        trade_date=trade_date or "",
                        provider=provider or "",
                        model=model or "",
                        success=bool(status.success),
                        status=status.status or "",
                        message=status.message or "",
                        request_chars=max(0, int(request_chars or 0)),
                        response_chars=max(0, int(response_chars or 0)),
                        latency_ms=max(0.0, float(latency_ms or 0.0)),
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.warning(f"记录 LLM 调用失败: {exc}")

    async def list_logs(
        self,
        *,
        limit: int = 100,
        scene: Optional[str] = None,
        status: Optional[str] = None,
        success: Optional[bool] = None,
        account_id: Optional[str] = None,
    ) -> List[Dict]:
        async with async_session_factory() as session:
            stmt = select(LlmCallLog).order_by(desc(LlmCallLog.created_at)).limit(max(1, min(limit, 500)))
            normalized_account_id = self._normalize_account_id(account_id)
            if account_id is not None:
                stmt = stmt.where(LlmCallLog.account_id == normalized_account_id)
            if scene:
                stmt = stmt.where(LlmCallLog.scene == scene)
            if status:
                stmt = stmt.where(LlmCallLog.status == status)
            if success is not None:
                stmt = stmt.where(LlmCallLog.success == bool(success))
            rows = (await session.execute(stmt)).scalars().all()

        result = []
        for row in rows:
            result.append({
                "id": row.id,
                "scene": row.scene,
                "account_id": row.account_id,
                "trade_date": row.trade_date,
                "provider": row.provider,
                "model": row.model,
                "success": bool(row.success),
                "status": row.status,
                "message": row.message,
                "request_chars": row.request_chars,
                "response_chars": row.response_chars,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return result

    async def get_daily_stats(
        self,
        *,
        days: int = 7,
        scene: Optional[str] = None,
        status: Optional[str] = None,
        success: Optional[bool] = None,
        account_id: Optional[str] = None,
    ) -> Dict:
        normalized_days = max(1, min(days, 30))
        end_day = datetime.utcnow().date()
        start_day = end_day - timedelta(days=normalized_days - 1)
        start_at = datetime.combine(start_day, datetime.min.time())

        async with async_session_factory() as session:
            stmt = (
                select(LlmCallLog)
                .where(LlmCallLog.created_at >= start_at)
                .order_by(LlmCallLog.created_at.asc())
            )
            normalized_account_id = self._normalize_account_id(account_id)
            if account_id is not None:
                stmt = stmt.where(LlmCallLog.account_id == normalized_account_id)
            if scene:
                stmt = stmt.where(LlmCallLog.scene == scene)
            if status:
                stmt = stmt.where(LlmCallLog.status == status)
            if success is not None:
                stmt = stmt.where(LlmCallLog.success == bool(success))
            rows = (await session.execute(stmt)).scalars().all()

        day_buckets = {}
        for offset in range(normalized_days):
            current_day = start_day + timedelta(days=offset)
            day_key = current_day.isoformat()
            day_buckets[day_key] = {
                "date": day_key,
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "request_chars": 0,
                "response_chars": 0,
                "request_tokens_estimated": 0,
                "response_tokens_estimated": 0,
                "total_tokens_estimated": 0,
            }

        for row in rows:
            if not row.created_at:
                continue
            day_key = row.created_at.date().isoformat()
            bucket = day_buckets.get(day_key)
            if bucket is None:
                continue

            request_chars = max(0, int(row.request_chars or 0))
            response_chars = max(0, int(row.response_chars or 0))
            request_tokens = self._estimate_tokens(request_chars)
            response_tokens = self._estimate_tokens(response_chars)

            bucket["call_count"] += 1
            bucket["success_count"] += 1 if row.success else 0
            bucket["failure_count"] += 0 if row.success else 1
            bucket["request_chars"] += request_chars
            bucket["response_chars"] += response_chars
            bucket["request_tokens_estimated"] += request_tokens
            bucket["response_tokens_estimated"] += response_tokens
            bucket["total_tokens_estimated"] += request_tokens + response_tokens

        daily = list(day_buckets.values())
        total_calls = sum(item["call_count"] for item in daily)
        success_calls = sum(item["success_count"] for item in daily)
        failure_calls = sum(item["failure_count"] for item in daily)
        request_tokens_total = sum(item["request_tokens_estimated"] for item in daily)
        response_tokens_total = sum(item["response_tokens_estimated"] for item in daily)

        return {
            "days": normalized_days,
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "token_estimate_rule": "ceil(chars / 4)",
            "daily": daily,
            "summary": {
                "total_calls": total_calls,
                "success_calls": success_calls,
                "failure_calls": failure_calls,
                "success_rate": round((success_calls / total_calls) * 100, 2) if total_calls else 0.0,
                "request_tokens_estimated": request_tokens_total,
                "response_tokens_estimated": response_tokens_total,
                "total_tokens_estimated": request_tokens_total + response_tokens_total,
            },
        }


llm_call_log_service = LlmCallLogService()
