"""
账户配置（单例表 id=1）
"""
from datetime import datetime

from sqlalchemy import Column, Integer, Float, DateTime, Boolean, String

from app.core.database import Base


class AccountConfig(Base):
    """轻舟账户总资产等配置，仅一条记录"""

    __tablename__ = "account_config"

    id = Column(Integer, primary_key=True)  # 固定为 1
    total_asset = Column(Float, nullable=False, default=1_000_000.0)
    llm_enabled = Column(Boolean, nullable=False, default=False)
    llm_provider = Column(String(40), nullable=False, default="custom")
    llm_base_url = Column(String(255), nullable=False, default="")
    llm_api_key = Column(String(255), nullable=False, default="")
    llm_model = Column(String(120), nullable=False, default="")
    llm_timeout_seconds = Column(Float, nullable=False, default=12.0)
    llm_temperature = Column(Float, nullable=False, default=0.2)
    llm_max_input_items = Column(Integer, nullable=False, default=8)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
