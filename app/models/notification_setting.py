"""
通知偏好模型
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.types import JSON

from app.core.database import Base


class NotificationSetting(Base):
    """账户通知偏好。"""

    __tablename__ = "notification_settings"

    id = Column(String(40), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    in_app_enabled = Column(Boolean, nullable=False, default=True)
    wecom_enabled = Column(Boolean, nullable=False, default=False)
    wecom_webhook_url = Column(String(500), nullable=False, default="")
    rules_json = Column(JSON, nullable=False, default=dict)
    quiet_windows = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_notification_settings_account_unique", "account_id", unique=True),
    )
