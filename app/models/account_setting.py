"""
账户设置模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String

from app.core.database import Base


class AccountSetting(Base):
    """每个交易账户自己的配置。"""

    __tablename__ = "account_settings"

    account_id = Column(String(36), ForeignKey("trading_accounts.id"), primary_key=True)
    total_asset = Column(Float, nullable=False, default=1_000_000.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
