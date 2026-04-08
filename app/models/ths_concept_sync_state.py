"""
同花顺概念同步状态模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class ThsConceptSyncState(Base):
    """记录 THS 概念离线同步进度，支持分批与断点续跑。"""

    __tablename__ = "ths_concept_sync_states"

    sync_key = Column(String(40), primary_key=True)
    target_trade_date = Column(String(20), nullable=False, default="", index=True)
    active_trade_date = Column(String(20), nullable=False, default="", index=True)
    status = Column(String(20), nullable=False, default="idle", index=True)
    total_concepts = Column(Integer, nullable=False, default=0)
    processed_concepts = Column(Integer, nullable=False, default=0)
    next_cursor = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
