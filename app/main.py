"""
轻舟版交易系统 - 主入口
"""
import asyncio
import uuid
from contextlib import suppress
from datetime import datetime, time
from time import monotonic
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from app.core.config import settings
from app.core.security import get_current_user, hash_password
from app.services.notification_engine import notification_engine
from app.services.ths_concept_sync_service import ths_concept_sync_service

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# 配置 CORS
origins = settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_notification_refresh_task: asyncio.Task | None = None

_MARKET_TIMEZONE = ZoneInfo(settings.notification_timezone)
_TRADING_WINDOWS = (
    (time(9, 25), time(11, 30)),
    (time(13, 0), time(15, 0)),
)


def _is_market_monitor_window(now: datetime | None = None) -> bool:
    if now is None:
        current = datetime.now(_MARKET_TIMEZONE)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=_MARKET_TIMEZONE)
    else:
        current = now.astimezone(_MARKET_TIMEZONE)
    if current.weekday() >= 5:
        return False
    current_time = current.time().replace(second=0, microsecond=0)
    return any(start <= current_time <= end for start, end in _TRADING_WINDOWS)


async def _notification_refresh_loop() -> None:
    """后台定时生成通知事件，避免请求路径同步重算。"""
    interval_seconds = max(10, int(settings.notification_refresh_interval_seconds))
    initial_delay_seconds = max(0, int(settings.notification_refresh_initial_delay_seconds))

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    while True:
        cycle_started_at = monotonic()
        try:
            if _is_market_monitor_window():
                refreshed_accounts = await notification_engine.refresh_active_accounts()
                logger.debug("通知后台刷新完成 accounts={}", refreshed_accounts)
            else:
                logger.debug("当前不在交易监控时段，跳过本轮通知刷新")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("通知后台刷新失败 error={}", exc)

        elapsed_seconds = monotonic() - cycle_started_at
        sleep_seconds = max(1.0, interval_seconds - elapsed_seconds)
        await asyncio.sleep(sleep_seconds)


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    settings.validate_runtime()
    logger.info(f"{settings.app_name} v{settings.app_version} 启动中...")

    # 仅初始化业务默认数据；表结构由 Alembic 管理
    try:
        from app.models.account_config import AccountConfig
        from app.models.trading_account import TradingAccount
        from app.models.user import User
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.services.trading_account_service import create_trading_account

        # 账户配置单例：无记录时用 .env 中的 QINGZHOU_TOTAL_ASSET 作为初始值
        async with async_session_factory() as session:
            r = await session.execute(
                select(AccountConfig).where(AccountConfig.id == 1)
            )
            if r.scalar_one_or_none() is None:
                session.add(
                    AccountConfig(
                        id=1,
                        total_asset=float(settings.qingzhou_total_asset),
                        llm_enabled=bool(settings.llm_enabled),
                        llm_provider=settings.llm_provider,
                        llm_base_url=settings.llm_base_url,
                        llm_api_key=settings.llm_api_key,
                        llm_model=settings.llm_model,
                        llm_timeout_seconds=float(settings.llm_timeout_seconds),
                        llm_temperature=float(settings.llm_temperature),
                        llm_max_input_items=int(settings.llm_max_input_items),
                    )
                )
                await session.commit()
                logger.info("已初始化 account_config 默认总资产")

            if settings.auth_enabled:
                user_result = await session.execute(
                    select(User).where(User.username == settings.auth_bootstrap_admin_username)
                )
                admin_user = user_result.scalar_one_or_none()
                if admin_user is None:
                    admin_user = User(
                        id=str(uuid.uuid4()),
                        username=settings.auth_bootstrap_admin_username,
                        password_hash=hash_password(settings.auth_bootstrap_admin_password),
                        display_name=settings.auth_bootstrap_admin_display_name,
                        role="admin",
                        status="active",
                    )
                    session.add(admin_user)
                    await session.commit()
                    await session.refresh(admin_user)
                    logger.info("已初始化默认管理员账号: {}", settings.auth_bootstrap_admin_username)

                if not admin_user.default_account_id:
                    account_result = await session.execute(
                        select(TradingAccount)
                        .where(TradingAccount.owner_user_id == admin_user.id)
                        .order_by(TradingAccount.created_at.asc())
                    )
                    account = account_result.scalars().first()
                    if account is None:
                        account = await create_trading_account(
                            "DEFAULT-001",
                            "默认账户",
                            owner_user_id=admin_user.id,
                        )
                        logger.info("已初始化默认交易账户: {}", account.account_code)

                    refresh_result = await session.execute(select(User).where(User.id == admin_user.id))
                    bound_admin = refresh_result.scalar_one_or_none()
                    if bound_admin:
                        bound_admin.default_account_id = account.id
                        await session.commit()
    except Exception as e:
        logger.warning(f"默认业务数据初始化失败，请先执行 Alembic 迁移: {e}")

    try:
        await ths_concept_sync_service.refresh_local_cache()
    except Exception as exc:
        logger.warning("加载本地 THS 概念缓存失败: {}", exc)

    global _notification_refresh_task
    if settings.notification_background_refresh_enabled and _notification_refresh_task is None:
        _notification_refresh_task = asyncio.create_task(_notification_refresh_loop())
        logger.info(
            "已启动通知后台刷新 interval={}s initial_delay={}s",
            settings.notification_refresh_interval_seconds,
            settings.notification_refresh_initial_delay_seconds,
        )


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    global _notification_refresh_task
    if _notification_refresh_task is not None:
        _notification_refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await _notification_refresh_task
        _notification_refresh_task = None
    logger.info("应用关闭...")


@app.get("/")
async def root():
    """根路由"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.get(f"{settings.api_v1_prefix}/ping")
async def api_ping():
    """API 前缀下的轻量预热端点。"""
    return {"status": "ok"}


# 导入并注册路由
from app.api.v1 import account, auth, decision, market, notification, sector, stock, task
from app.api.v1 import admin as admin_api
from app.api.v1 import system as system_api

app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["认证"])
app.include_router(admin_api.router, prefix=f"{settings.api_v1_prefix}/admin", tags=["管理员"])
app.include_router(market.router, prefix=settings.api_v1_prefix, tags=["市场环境"], dependencies=[Depends(get_current_user)])
app.include_router(sector.router, prefix=settings.api_v1_prefix, tags=["板块扫描"], dependencies=[Depends(get_current_user)])
app.include_router(stock.router, prefix=settings.api_v1_prefix, tags=["个股筛选"], dependencies=[Depends(get_current_user)])
app.include_router(decision.router, prefix=settings.api_v1_prefix, tags=["决策分析"], dependencies=[Depends(get_current_user)])
app.include_router(account.router, prefix=settings.api_v1_prefix, tags=["账户适配"], dependencies=[Depends(get_current_user)])
app.include_router(task.router, prefix=settings.api_v1_prefix, tags=["任务管理"], dependencies=[Depends(get_current_user)])
app.include_router(system_api.router, prefix=settings.api_v1_prefix, tags=["系统设置"], dependencies=[Depends(get_current_user)])
app.include_router(notification.router, prefix=settings.api_v1_prefix, tags=["通知"], dependencies=[Depends(get_current_user)])

# 兼容前端按业务分组的路径：/api/v1/market/* /api/v1/decision/* 等
app.include_router(market.router, prefix=f"{settings.api_v1_prefix}/market", tags=["市场环境"], dependencies=[Depends(get_current_user)])
app.include_router(sector.router, prefix=f"{settings.api_v1_prefix}/sector", tags=["板块扫描"], dependencies=[Depends(get_current_user)])
app.include_router(stock.router, prefix=f"{settings.api_v1_prefix}/stock", tags=["个股筛选"], dependencies=[Depends(get_current_user)])
app.include_router(decision.router, prefix=f"{settings.api_v1_prefix}/decision", tags=["决策分析"], dependencies=[Depends(get_current_user)])
app.include_router(account.router, prefix=f"{settings.api_v1_prefix}/account", tags=["账户适配"], dependencies=[Depends(get_current_user)])
app.include_router(task.router, prefix=f"{settings.api_v1_prefix}/task", tags=["任务管理"], dependencies=[Depends(get_current_user)])
app.include_router(system_api.router, prefix=f"{settings.api_v1_prefix}/system", tags=["系统设置"], dependencies=[Depends(get_current_user)])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
