"""
LLM 解释结果缓存模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class LlmCacheEntry(Base):
    """LLM 页面解释缓存。"""

    __tablename__ = "llm_cache_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene = Column(String(60), nullable=False, index=True, default="")
    cache_key = Column(String(64), nullable=False, unique=True, index=True, default="")
    trade_date = Column(String(20), nullable=False, index=True, default="")
    provider = Column(String(40), nullable=False, default="")
    model = Column(String(120), nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="")
    response_json = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
