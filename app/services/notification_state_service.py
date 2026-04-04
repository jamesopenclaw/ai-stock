"""
通知状态快照服务
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.notification_state_snapshot import NotificationStateSnapshot


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass(frozen=True)
class NotificationStateInput:
    state_key: str
    current_value: str
    current_rank: int
    entity_type: str = "system"
    entity_code: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationStateChange:
    state_key: str
    previous_value: str
    previous_rank: int
    current_value: str
    current_rank: int
    entity_type: str
    entity_code: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


class NotificationStateService:
    """维护通知相关的状态快照。"""

    async def sync_states(
        self,
        account_id: str,
        *,
        state_type: str,
        trade_date: str,
        states: list[NotificationStateInput],
    ) -> dict[str, NotificationStateChange]:
        now = _utcnow()
        state_map = {item.state_key: item for item in states}

        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationStateSnapshot).where(
                    NotificationStateSnapshot.account_id == account_id,
                    NotificationStateSnapshot.state_type == state_type,
                )
            )
            existing_rows = {row.state_key: row for row in result.scalars().all()}
            changes: dict[str, NotificationStateChange] = {}

            for state_key, item in state_map.items():
                row = existing_rows.get(state_key)
                previous_value = "inactive"
                previous_rank = 0
                if row is None:
                    row = NotificationStateSnapshot(
                        id=uuid.uuid4().hex,
                        account_id=account_id,
                        state_type=state_type,
                        state_key=state_key,
                        created_at=now,
                    )
                    session.add(row)
                elif row.last_trade_date == trade_date:
                    previous_value = str(row.current_value or "inactive")
                    previous_rank = int(row.current_rank or 0)

                row.entity_type = item.entity_type
                row.entity_code = item.entity_code
                row.current_value = item.current_value
                row.current_rank = int(item.current_rank)
                row.last_trade_date = trade_date
                row.state_payload = dict(item.payload or {})
                row.updated_at = now

                changes[state_key] = NotificationStateChange(
                    state_key=state_key,
                    previous_value=previous_value,
                    previous_rank=previous_rank,
                    current_value=item.current_value,
                    current_rank=int(item.current_rank),
                    entity_type=item.entity_type,
                    entity_code=item.entity_code,
                    payload=dict(item.payload or {}),
                )

            missing_keys = set(existing_rows.keys()) - set(state_map.keys())
            for state_key in missing_keys:
                row = existing_rows[state_key]
                previous_value = "inactive"
                previous_rank = 0
                if row.last_trade_date == trade_date:
                    previous_value = str(row.current_value or "inactive")
                    previous_rank = int(row.current_rank or 0)

                row.current_value = "inactive"
                row.current_rank = 0
                row.last_trade_date = trade_date
                row.state_payload = {}
                row.updated_at = now

                changes[state_key] = NotificationStateChange(
                    state_key=state_key,
                    previous_value=previous_value,
                    previous_rank=previous_rank,
                    current_value="inactive",
                    current_rank=0,
                    entity_type=row.entity_type,
                    entity_code=row.entity_code,
                    payload={},
                )

            if changes:
                await session.commit()
            return changes


notification_state_service = NotificationStateService()
