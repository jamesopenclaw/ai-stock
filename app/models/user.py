"""
用户数据模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String

from app.core.database import Base


class User(Base):
    """登录用户。"""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(64), nullable=False, default="")
    default_account_id = Column(String(36), nullable=True, index=True)
    role = Column(String(20), nullable=False, default="user", index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
