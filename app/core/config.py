"""
轻舟版交易系统 - 配置文件
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # 应用信息
    app_name: str = "轻舟版交易系统"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "dev-secret-key-change-in-production"

    # 认证
    auth_enabled: bool = True
    auth_access_token_expire_minutes: int = 30
    auth_refresh_token_expire_days: int = 14
    auth_bootstrap_admin_username: str = "admin"
    auth_bootstrap_admin_password: str = "admin123456"
    auth_bootstrap_admin_display_name: str = "系统管理员"

    # 数据库
    database_url: str = "postgresql+asyncpg://aistock:aistock123@localhost:5488/aistock"

    # Redis
    redis_url: str = "redis://localhost:6388/0"

    # Tushare
    tushare_token: str = ""

    # 轻舟账户：首次启动写入 DB 的默认总资产（元），之后由账户管理页维护
    qingzhou_total_asset: float = 1000000

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:3088,http://localhost:8000"

    # 企业微信机器人
    wecom_webhook_url: str = ""
    notify_enabled: bool = False

    # LLM 辅助层
    llm_enabled: bool = False
    llm_provider: str = "custom"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 60.0
    # 个股体检输出 JSON 较大，实际 HTTP 等待时间取 max(账户超时, 本值)
    llm_stock_checkup_min_timeout_seconds: float = 45.0
    llm_temperature: float = 0.2
    llm_max_input_items: int = 8

    def validate_runtime(self) -> None:
        """校验高风险运行配置。"""
        if not self.debug and self.secret_key == "dev-secret-key-change-in-production":
            raise ValueError("生产模式必须显式设置 SECRET_KEY")
        if self.notify_enabled and not self.wecom_webhook_url.strip():
            raise ValueError("启用通知时必须提供 WECOM_WEBHOOK_URL")
        if self.llm_enabled and not self.llm_api_key.strip():
            raise ValueError("启用 LLM 时必须提供 LLM_API_KEY")
        if self.llm_enabled and not self.llm_model.strip():
            raise ValueError("启用 LLM 时必须提供 LLM_MODEL")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
