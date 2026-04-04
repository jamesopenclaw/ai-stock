"""
通知状态快照模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.types import JSON

from app.core.database import Base


class NotificationStateSnapshot(Base):
    """记录每个通知对象最近一次状态，用于判定是否发生跃迁。"""

    __tablename__ = "notification_state_snapshots"

    id = Column(String(40), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    state_type = Column(String(40), nullable=False, index=True)
    state_key = Column(String(120), nullable=False)
    entity_type = Column(String(30), nullable=False, default="system")
    entity_code = Column(String(40), nullable=True, index=True)
    current_value = Column(String(40), nullable=False, default="inactive")
    current_rank = Column(Integer, nullable=False, default=0)
    last_trade_date = Column(String(20), nullable=False, index=True, default="")
    state_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_notification_state_snapshots_account_type", "account_id", "state_type"),
        Index("ix_notification_state_snapshots_account_key", "account_id", "state_key", unique=True),
    )
