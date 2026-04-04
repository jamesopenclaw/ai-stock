"""
通知事件模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.types import JSON

from app.core.database import Base


class NotificationEvent(Base):
    """通知事件记录。"""

    __tablename__ = "notification_events"

    id = Column(String(40), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(60), nullable=False, index=True)
    category = Column(String(20), nullable=False, index=True)
    priority = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True, default="pending")
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False, default="")
    action_label = Column(String(60), nullable=False, default="查看")
    action_target_type = Column(String(30), nullable=False, default="route")
    action_target_payload = Column(JSON, nullable=False, default=dict)
    entity_type = Column(String(30), nullable=False, default="system")
    entity_code = Column(String(40), nullable=True, index=True)
    trade_date = Column(String(20), nullable=False, index=True)
    data_source = Column(String(40), nullable=True)
    dedupe_key = Column(String(160), nullable=False)
    trigger_value = Column(JSON, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    snoozed_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_notification_events_account_status_created", "account_id", "status", "created_at"),
        Index("ix_notification_events_account_priority_created", "account_id", "priority", "created_at"),
        Index("ix_notification_events_account_dedupe", "account_id", "dedupe_key", unique=True),
    )

