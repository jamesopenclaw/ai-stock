"""
交易账户数据模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base


class TradingAccount(Base):
    """交易账户。"""

    __tablename__ = "trading_accounts"

    id = Column(String(36), primary_key=True)
    account_code = Column(String(64), nullable=False, unique=True, index=True)
    account_name = Column(String(64), nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
