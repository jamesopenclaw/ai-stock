"""
账户配置（单例表 id=1）
"""
from datetime import datetime

from sqlalchemy import Column, Integer, Float, DateTime

from app.core.database import Base


class AccountConfig(Base):
    """轻舟账户总资产等配置，仅一条记录"""

    __tablename__ = "account_config"

    id = Column(Integer, primary_key=True)  # 固定为 1
    total_asset = Column(Float, nullable=False, default=1_000_000.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
