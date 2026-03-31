"""
复盘快照数据模型
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint

from app.core.database import Base


class ReviewSnapshot(Base):
    """每日候选/买点复盘快照。"""

    __tablename__ = "review_snapshots"
    __table_args__ = (
        UniqueConstraint("trade_date", "snapshot_type", "ts_code", "account_id", name="uq_review_snapshot_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True, default="")
    snapshot_type = Column(String, nullable=False, index=True)
    ts_code = Column(String, nullable=False, index=True)
    stock_name = Column(String, nullable=False)
    candidate_source_tag = Column(String, default="")
    candidate_bucket_tag = Column(String, default="")
    buy_signal_tag = Column(String, default="")
    buy_point_type = Column(String, default="")
    stock_pool_tag = Column(String, default="")
    stock_score = Column(Float, default=0.0)
    base_price = Column(Float, default=0.0)
    trade_mode = Column(String, default="")
    add_position_decision = Column(String, default="")
    add_position_score_total = Column(Integer, default=0)
    add_position_scene = Column(String, default="")
    return_1d = Column(Float, default=0.0)
    return_3d = Column(Float, default=0.0)
    return_5d = Column(Float, default=0.0)
    resolved_days = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
