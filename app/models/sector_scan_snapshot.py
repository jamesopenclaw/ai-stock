"""
板块扫描完整快照数据模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class SectorScanSnapshot(Base):
    """按交易日缓存完整板块扫描结果。"""

    __tablename__ = "sector_scan_snapshots"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_sector_scan_snapshot_trade_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String, nullable=False, index=True)
    resolved_trade_date = Column(String, default="")
    payload_json = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
