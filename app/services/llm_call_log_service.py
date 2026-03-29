"""
LLM 调用记录服务
"""
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


llm_call_log_service = LlmCallLogService()
