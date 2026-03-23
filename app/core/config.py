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

    # 轻舟账户：首次启动写入 DB 的默认总资产（元），之后由账户管理页维护
    qingzhou_total_asset: float = 1000000

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # 企业微信机器人
    wecom_webhook_url: str = ""
    notify_enabled: bool = True

    # LLM 辅助层
    llm_enabled: bool = False
    llm_provider: str = "custom"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 12.0
    llm_temperature: float = 0.2
    llm_max_input_items: int = 8

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
