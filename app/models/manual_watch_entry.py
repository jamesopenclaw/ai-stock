"""
手动跟踪股票池（按交易账户维度）
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, UniqueConstraint

from app.core.database import Base


class ManualWatchEntry(Base):
    """用户在三池页维护的自选跟踪代码，不参与自动三池分类。"""

    __tablename__ = "manual_watch_entries"
    __table_args__ = (UniqueConstraint("account_id", "ts_code", name="uq_manual_watch_account_ts_code"),)

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
