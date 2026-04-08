"""
同花顺概念成分本地缓存模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base


class ThsConceptMember(Base):
    """同花顺概念成分映射。"""

    __tablename__ = "ths_concept_members"
    __table_args__ = (
        UniqueConstraint("concept_code", "stock_code", name="uq_ths_concept_member_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept_code = Column(String(20), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    stock_name = Column(String(120), nullable=False, default="")
    sync_trade_date = Column(String(20), nullable=False, default="", index=True)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
