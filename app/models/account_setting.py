"""
账户设置模型
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class AccountSetting(Base):
    """每个交易账户自己的配置。"""

    __tablename__ = "account_settings"

    account_id = Column(String(36), ForeignKey("trading_accounts.id"), primary_key=True)
    total_asset = Column(Float, nullable=False, default=1_000_000.0)
    llm_enabled = Column(Boolean, nullable=False, default=False)
    llm_provider = Column(String(40), nullable=False, default="custom")
    llm_base_url = Column(String(255), nullable=False, default="")
    llm_api_key = Column(String(255), nullable=False, default="")
    llm_model = Column(String(120), nullable=False, default="")
    llm_timeout_seconds = Column(Float, nullable=False, default=60.0)
    llm_temperature = Column(Float, nullable=False, default=0.2)
    llm_max_input_items = Column(Integer, nullable=False, default=8)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
