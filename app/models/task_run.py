"""
任务运行记录模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class TaskRun(Base):
    """任务执行记录。"""

    __tablename__ = "task_runs"

    id = Column(String(40), primary_key=True)
    mode = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(20), nullable=False, index=True)
    trigger_source = Column(String(20), nullable=False, default="manual")
    status = Column(String(20), nullable=False, index=True, default="queued")
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=1)
    duration_ms = Column(Float, nullable=False, default=0.0)
    result_json = Column(Text, nullable=False, default="")
    last_error = Column(Text, nullable=False, default="")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
