"""
LLM 调用记录模型
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class LlmCallLog(Base):
    """LLM 调用记录。"""

    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene = Column(String(60), nullable=False, index=True, default="")
    trade_date = Column(String(20), nullable=False, index=True, default="")
    provider = Column(String(40), nullable=False, default="")
    model = Column(String(120), nullable=False, default="")
    success = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String(40), nullable=False, default="", index=True)
    message = Column(Text, nullable=False, default="")
    request_chars = Column(Integer, nullable=False, default=0)
    response_chars = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
