"""
通知事件服务
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import desc, or_, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.notification_event import NotificationEvent
from app.models.notification_setting import NotificationSetting
from app.models.schemas import (
    NotificationActionTargetType,
    NotificationCategory,
    NotificationItem,
    NotificationListResponse,
    NotificationPriority,
    NotificationSettingsPayload,
    NotificationStatus,
    NotificationSummaryResponse,
)
from app.services.notify import notify_service


DEFAULT_NOTIFICATION_RULES = {
    "holding_to_sell": "high",
    "holding_to_reduce": "high",
    "candidate_to_executable": "medium",
    "candidate_near_trigger": "medium",
    "radar_candidate_near_execution": "medium",
    "market_env_downgraded": "high",
    "realtime_source_degraded": "info",
}
VALID_NOTIFICATION_PRIORITIES = {
    NotificationPriority.HIGH.value,
    NotificationPriority.MEDIUM.value,
    NotificationPriority.LOW.value,
    NotificationPriority.INFO.value,
}
DISABLED_NOTIFICATION_RULE_VALUES = {
    "off",
    "disabled",
    "mute",
    "none",
    "close",
    "closed",
    "关闭",
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _notification_now() -> datetime:
    return datetime.now(ZoneInfo(settings.notification_timezone))


def _serialize_notification_item(row: NotificationEvent) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        event_type=row.event_type,
        category=NotificationCategory(str(row.category)),
        priority=NotificationPriority(str(row.priority)),
        status=NotificationStatus(str(row.status)),
        title=row.title,
        message=row.message,
        action_label=row.action_label,
        action_target_type=NotificationActionTargetType(str(row.action_target_type)),
        action_target_payload=dict(row.action_target_payload or {}),
        entity_type=row.entity_type,
        entity_code=row.entity_code,
        trade_date=row.trade_date,
        data_source=row.data_source,
        created_at=row.created_at,
        updated_at=row.updated_at,
        read_at=row.read_at,
        snoozed_until=row.snoozed_until,
        resolved_at=row.resolved_at,
    )


class NotificationService:
    """通知事件增删改查。"""

    def normalize_rules(self, rules: Optional[Dict[str, Any]] = None) -> dict[str, str]:
        merged = dict(DEFAULT_NOTIFICATION_RULES)
        for event_type, raw_value in dict(rules or {}).items():
            normalized = self._normalize_rule_value(raw_value)
            if normalized is None:
                continue
            merged[str(event_type)] = normalized
        return merged

    def resolve_event_priority(
        self,
        rules: Optional[Dict[str, Any]],
        event_type: str,
        fallback_priority: str,
    ) -> Optional[str]:
        normalized_rules = self.normalize_rules(rules)
        normalized_fallback = self._normalize_rule_value(fallback_priority)
        if normalized_fallback == "off":
            normalized_fallback = None
        configured = normalized_rules.get(event_type)
        normalized_configured = self._normalize_rule_value(configured)
        if normalized_configured == "off":
            return None
        if normalized_configured in VALID_NOTIFICATION_PRIORITIES:
            return normalized_configured
        return normalized_fallback

    def _normalize_rule_value(self, value: Any) -> Optional[str]:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
        if raw in DISABLED_NOTIFICATION_RULE_VALUES:
            return "off"
        if raw in VALID_NOTIFICATION_PRIORITIES:
            return raw
        return None

    def normalize_quiet_windows(self, quiet_windows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, str]]:
        normalized_windows: list[dict[str, str]] = []
        for item in list(quiet_windows or []):
            if not isinstance(item, dict):
                continue
            start = self._normalize_hhmm(item.get("start"))
            end = self._normalize_hhmm(item.get("end"))
            if not start or not end or start == end:
                continue
            normalized_windows.append({"start": start, "end": end})
        return normalized_windows

    def get_active_quiet_window(
        self,
        quiet_windows: Optional[list[dict[str, Any]]] = None,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[dict[str, str]]:
        current = now or _notification_now()
        current_minutes = current.hour * 60 + current.minute
        for item in self.normalize_quiet_windows(quiet_windows):
            start_minutes = self._hhmm_to_minutes(item["start"])
            end_minutes = self._hhmm_to_minutes(item["end"])
            if start_minutes < end_minutes:
                if start_minutes <= current_minutes < end_minutes:
                    return item
                continue
            if current_minutes >= start_minutes or current_minutes < end_minutes:
                return item
        return None

    def _normalize_hhmm(self, value: Any) -> Optional[str]:
        raw = str(value or "").strip()
        if len(raw) != 5 or raw[2] != ":":
            return None
        hour_text, minute_text = raw.split(":", 1)
        if not hour_text.isdigit() or not minute_text.isdigit():
            return None
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    def _hhmm_to_minutes(self, value: str) -> int:
        hour_text, minute_text = value.split(":", 1)
        return int(hour_text) * 60 + int(minute_text)

    async def get_settings(
        self,
        account_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> NotificationSettingsPayload:
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationSetting).where(NotificationSetting.account_id == account_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = NotificationSetting(
                    id=uuid.uuid4().hex,
                    account_id=account_id,
                    user_id=user_id,
                    in_app_enabled=True,
                    wecom_enabled=False,
                    rules_json=dict(DEFAULT_NOTIFICATION_RULES),
                    quiet_windows=[],
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return NotificationSettingsPayload(
                in_app_enabled=bool(row.in_app_enabled),
                wecom_enabled=bool(row.wecom_enabled),
                rules=self.normalize_rules(row.rules_json),
                quiet_windows=self.normalize_quiet_windows(row.quiet_windows),
            )

    async def update_settings(
        self,
        account_id: str,
        payload: NotificationSettingsPayload,
        *,
        user_id: Optional[str] = None,
    ) -> NotificationSettingsPayload:
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationSetting).where(NotificationSetting.account_id == account_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = NotificationSetting(
                    id=uuid.uuid4().hex,
                    account_id=account_id,
                    user_id=user_id,
                    created_at=_utcnow(),
                )
                session.add(row)
            row.user_id = user_id or row.user_id
            row.in_app_enabled = bool(payload.in_app_enabled)
            row.wecom_enabled = bool(payload.wecom_enabled)
            row.rules_json = self.normalize_rules(payload.rules)
            row.quiet_windows = self.normalize_quiet_windows(payload.quiet_windows)
            row.updated_at = _utcnow()
            await session.commit()
            await session.refresh(row)
            normalized_payload = NotificationSettingsPayload(
                in_app_enabled=bool(row.in_app_enabled),
                wecom_enabled=bool(row.wecom_enabled),
                rules=self.normalize_rules(row.rules_json),
                quiet_windows=self.normalize_quiet_windows(row.quiet_windows),
            )
        await self.apply_settings_to_existing_events(account_id, normalized_payload.rules)
        return normalized_payload

    async def reactivate_expired_snoozed(self, account_id: str) -> None:
        now = _utcnow()
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationEvent).where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.status == NotificationStatus.SNOOZED.value,
                    NotificationEvent.snoozed_until.is_not(None),
                    NotificationEvent.snoozed_until <= now,
                )
            )
            rows = result.scalars().all()
            for row in rows:
                row.status = NotificationStatus.PENDING.value
                row.snoozed_until = None
                row.updated_at = now
            if rows:
                await session.commit()

    async def list_events(
        self,
        account_id: str,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> NotificationListResponse:
        await self.reactivate_expired_snoozed(account_id)
        settings = await self.get_settings(account_id)
        if not settings.in_app_enabled:
            return NotificationListResponse()

        async with async_session_factory() as session:
            stmt = select(NotificationEvent).where(NotificationEvent.account_id == account_id)
            if status:
                stmt = stmt.where(NotificationEvent.status == status)
            if category:
                stmt = stmt.where(NotificationEvent.category == category)
            if priority:
                stmt = stmt.where(NotificationEvent.priority == priority)

            if status == NotificationStatus.PENDING.value:
                stmt = stmt.where(
                    or_(
                        NotificationEvent.snoozed_until.is_(None),
                        NotificationEvent.snoozed_until <= _utcnow(),
                    )
                )

            stmt = stmt.order_by(desc(NotificationEvent.updated_at), desc(NotificationEvent.created_at)).limit(
                max(1, min(limit, 100))
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            unread_count, critical_count = await self._count_pending(session, account_id)
            return NotificationListResponse(
                items=[_serialize_notification_item(row) for row in rows],
                unread_count=unread_count,
                critical_count=critical_count,
                next_cursor=None,
            )

    async def get_summary(self, account_id: str, *, latest_limit: int = 3) -> NotificationSummaryResponse:
        await self.reactivate_expired_snoozed(account_id)
        settings = await self.get_settings(account_id)
        if not settings.in_app_enabled:
            return NotificationSummaryResponse()
        active_quiet_window = self.get_active_quiet_window(settings.quiet_windows)

        async with async_session_factory() as session:
            unread_count, critical_count = await self._count_pending(session, account_id)
            latest_result = await session.execute(
                select(NotificationEvent)
                .where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.status == NotificationStatus.PENDING.value,
                    or_(
                        NotificationEvent.snoozed_until.is_(None),
                        NotificationEvent.snoozed_until <= _utcnow(),
                    ),
                )
                .order_by(desc(NotificationEvent.updated_at), desc(NotificationEvent.created_at))
                .limit(max(1, min(latest_limit, 10)))
            )
            return NotificationSummaryResponse(
                unread_count=unread_count,
                critical_count=critical_count,
                latest_items=[_serialize_notification_item(row) for row in latest_result.scalars().all()],
                quiet_window_active=bool(active_quiet_window),
                quiet_window_label=(
                    f"{active_quiet_window['start']}-{active_quiet_window['end']}"
                    if active_quiet_window
                    else None
                ),
            )

    async def mark_read(self, account_id: str, event_id: str) -> bool:
        return await self._update_status(
            account_id,
            event_id,
            NotificationStatus.READ.value,
            read_at=_utcnow(),
            snoozed_until=None,
        )

    async def dismiss(self, account_id: str, event_id: str) -> bool:
        return await self._update_status(
            account_id,
            event_id,
            NotificationStatus.DISMISSED.value,
            snoozed_until=None,
        )

    async def snooze(self, account_id: str, event_id: str, minutes: int) -> bool:
        return await self._update_status(
            account_id,
            event_id,
            NotificationStatus.SNOOZED.value,
            snoozed_until=_utcnow() + timedelta(minutes=max(5, minutes)),
        )

    async def mark_all_read(
        self,
        account_id: str,
        *,
        ids: Optional[Iterable[str]] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        exclude_priorities: Optional[Iterable[str]] = None,
    ) -> int:
        async with async_session_factory() as session:
            stmt = select(NotificationEvent).where(NotificationEvent.account_id == account_id)
            if ids:
                stmt = stmt.where(NotificationEvent.id.in_(list(ids)))
            else:
                stmt = stmt.where(NotificationEvent.status == NotificationStatus.PENDING.value)
                if status:
                    stmt = stmt.where(NotificationEvent.status == status)
                if category:
                    stmt = stmt.where(NotificationEvent.category == category)
                if priority:
                    stmt = stmt.where(NotificationEvent.priority == priority)
                if exclude_priorities:
                    stmt = stmt.where(NotificationEvent.priority.not_in(list(exclude_priorities)))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            now = _utcnow()
            for row in rows:
                row.status = NotificationStatus.READ.value
                row.read_at = now
                row.snoozed_until = None
                row.updated_at = now
            if rows:
                await session.commit()
            return len(rows)

    async def upsert_event(
        self,
        account_id: str,
        *,
        user_id: Optional[str],
        event_type: str,
        category: str,
        priority: str,
        title: str,
        message: str,
        action_label: str,
        action_target_type: str,
        action_target_payload: Optional[Dict[str, Any]] = None,
        entity_type: str = "system",
        entity_code: Optional[str] = None,
        trade_date: str,
        data_source: Optional[str] = None,
        dedupe_key: str,
        trigger_value: Optional[Dict[str, Any]] = None,
    ) -> Optional[NotificationItem]:
        settings = await self.get_settings(account_id, user_id=user_id)
        effective_priority = self.resolve_event_priority(settings.rules, event_type, priority)
        now = _utcnow()
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationEvent).where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.dedupe_key == dedupe_key,
                )
            )
            row = result.scalar_one_or_none()
            if effective_priority is None:
                if row is not None and row.status in {
                    NotificationStatus.PENDING.value,
                    NotificationStatus.READ.value,
                    NotificationStatus.SNOOZED.value,
                }:
                    row.status = NotificationStatus.RESOLVED.value
                    row.resolved_at = now
                    row.snoozed_until = None
                    row.updated_at = now
                    await session.commit()
                return None
            should_push_wecom = False
            if row is None:
                row = NotificationEvent(
                    id=uuid.uuid4().hex,
                    account_id=account_id,
                    user_id=user_id,
                    event_type=event_type,
                    category=category,
                    priority=effective_priority,
                    status=NotificationStatus.PENDING.value,
                    title=title,
                    message=message,
                    action_label=action_label,
                    action_target_type=action_target_type,
                    action_target_payload=dict(action_target_payload or {}),
                    entity_type=entity_type,
                    entity_code=entity_code,
                    trade_date=trade_date,
                    data_source=data_source,
                    dedupe_key=dedupe_key,
                    trigger_value=dict(trigger_value or {}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                should_push_wecom = True
            else:
                previous_status = row.status
                row.user_id = user_id or row.user_id
                row.event_type = event_type
                row.category = category
                row.priority = effective_priority
                row.title = title
                row.message = message
                row.action_label = action_label
                row.action_target_type = action_target_type
                row.action_target_payload = dict(action_target_payload or {})
                row.entity_type = entity_type
                row.entity_code = entity_code
                row.trade_date = trade_date
                row.data_source = data_source
                row.trigger_value = dict(trigger_value or {})
                row.updated_at = now
                row.resolved_at = None
                if previous_status == NotificationStatus.RESOLVED.value:
                    row.status = NotificationStatus.PENDING.value
                    row.read_at = None
                    row.snoozed_until = None
                    should_push_wecom = True
            await session.commit()
            await session.refresh(row)

        active_quiet_window = self.get_active_quiet_window(settings.quiet_windows)
        if (
            settings.wecom_enabled
            and should_push_wecom
            and effective_priority == NotificationPriority.HIGH.value
            and not active_quiet_window
        ):
            await notify_service.wecom.send_markdown(
                f"## 盘中提醒\n\n**{title}**\n\n{message}"
            )
        return _serialize_notification_item(row)

    async def apply_settings_to_existing_events(self, account_id: str, rules: Optional[Dict[str, Any]] = None) -> int:
        normalized_rules = self.normalize_rules(rules)
        managed_event_types = list(normalized_rules.keys())
        if not managed_event_types:
            return 0

        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationEvent).where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.event_type.in_(managed_event_types),
                    NotificationEvent.status.in_(
                        [
                            NotificationStatus.PENDING.value,
                            NotificationStatus.READ.value,
                            NotificationStatus.SNOOZED.value,
                        ]
                    ),
                )
            )
            rows = result.scalars().all()
            now = _utcnow()
            updated = 0
            for row in rows:
                effective_priority = self.resolve_event_priority(normalized_rules, row.event_type, row.priority)
                if effective_priority is None:
                    row.status = NotificationStatus.RESOLVED.value
                    row.resolved_at = now
                    row.snoozed_until = None
                    row.updated_at = now
                    updated += 1
                    continue
                if row.priority != effective_priority:
                    row.priority = effective_priority
                    row.updated_at = now
                    updated += 1
            if updated:
                await session.commit()
            return updated

    async def resolve_inactive_events(
        self,
        account_id: str,
        *,
        active_dedupe_keys: set[str],
        event_types: set[str],
    ) -> int:
        if not event_types:
            return 0
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationEvent).where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.event_type.in_(list(event_types)),
                    NotificationEvent.status.in_(
                        [
                            NotificationStatus.PENDING.value,
                            NotificationStatus.READ.value,
                            NotificationStatus.SNOOZED.value,
                        ]
                    ),
                )
            )
            rows = result.scalars().all()
            now = _utcnow()
            updated = 0
            for row in rows:
                if row.dedupe_key in active_dedupe_keys:
                    continue
                row.status = NotificationStatus.RESOLVED.value
                row.resolved_at = now
                row.snoozed_until = None
                row.updated_at = now
                updated += 1
            if updated:
                await session.commit()
            return updated

    async def _count_pending(self, session, account_id: str) -> tuple[int, int]:
        result = await session.execute(
            select(NotificationEvent).where(
                NotificationEvent.account_id == account_id,
                NotificationEvent.status == NotificationStatus.PENDING.value,
                or_(
                    NotificationEvent.snoozed_until.is_(None),
                    NotificationEvent.snoozed_until <= _utcnow(),
                ),
            )
        )
        rows = result.scalars().all()
        unread_count = len(rows)
        critical_count = sum(1 for row in rows if row.priority == NotificationPriority.HIGH.value)
        return unread_count, critical_count

    async def _update_status(self, account_id: str, event_id: str, status: str, **updates) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                select(NotificationEvent).where(
                    NotificationEvent.account_id == account_id,
                    NotificationEvent.id == event_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            row.status = status
            for key, value in updates.items():
                setattr(row, key, value)
            row.updated_at = _utcnow()
            await session.commit()
            return True


notification_service = NotificationService()
