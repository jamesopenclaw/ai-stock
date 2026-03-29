"""
三池页面完整快照数据模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class StockPoolSnapshot(Base):
    """按交易日和候选规模缓存完整三池结果。"""

    __tablename__ = "stock_pool_snapshots"
    __table_args__ = (
        UniqueConstraint("trade_date", "candidate_limit", "account_id", name="uq_stock_pool_snapshot_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, default="", index=True)
    candidate_limit = Column(Integer, nullable=False, default=100, index=True)
    resolved_trade_date = Column(String, default="")
    payload_json = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
