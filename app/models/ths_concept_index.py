"""
同花顺概念指数本地缓存模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String

from app.core.database import Base


class ThsConceptIndex(Base):
    """同花顺概念指数定义。"""

    __tablename__ = "ths_concept_index"

    ts_code = Column(String(20), primary_key=True)
    concept_name = Column(String(120), nullable=False, default="")
    ths_type = Column(String(10), nullable=False, default="")
    exchange = Column(String(10), nullable=False, default="A")
    sync_trade_date = Column(String(20), nullable=False, default="")
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
