"""
轻舟版交易系统 - 配置文件
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 应用信息
    app_name: str = "轻舟版交易系统"
    app_version: str = "0.1.0"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"

    # 数据库
    database_url: str = "postgresql+asyncpg://aistock:aistock123@localhost:5432/aistock"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Tushare
    tushare_token: str = ""

    # 轻舟账户配置 (手工维护)
    qingzhou_total_asset: float = 1000000
    qingzhou_available_cash: float = 500000
    qingzhou_total_position_ratio: float = 0.5

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # 企业微信机器人
    wecom_webhook_url: str = ""
    notify_enabled: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
