"""
轻舟版交易系统 - 主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from app.core.config import settings

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


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    settings.validate_runtime()
    logger.info(f"{settings.app_name} v{settings.app_version} 启动中...")

    # 仅初始化业务默认数据；表结构由 Alembic 管理
    try:
        from app.models.account_config import AccountConfig
        from sqlalchemy import select
        from app.core.database import async_session_factory

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
    except Exception as e:
        logger.warning(f"默认业务数据初始化失败，请先执行 Alembic 迁移: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
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


# 导入并注册路由
from app.api.v1 import market, sector, stock, decision, account, task
from app.api.v1 import system as system_api

app.include_router(market.router, prefix=settings.api_v1_prefix, tags=["市场环境"])
app.include_router(sector.router, prefix=settings.api_v1_prefix, tags=["板块扫描"])
app.include_router(stock.router, prefix=settings.api_v1_prefix, tags=["个股筛选"])
app.include_router(decision.router, prefix=settings.api_v1_prefix, tags=["决策分析"])
app.include_router(account.router, prefix=settings.api_v1_prefix, tags=["账户适配"])
app.include_router(task.router, prefix=settings.api_v1_prefix, tags=["任务管理"])
app.include_router(system_api.router, prefix=settings.api_v1_prefix, tags=["系统设置"])

# 兼容前端按业务分组的路径：/api/v1/market/* /api/v1/decision/* 等
app.include_router(market.router, prefix=f"{settings.api_v1_prefix}/market", tags=["市场环境"])
app.include_router(sector.router, prefix=f"{settings.api_v1_prefix}/sector", tags=["板块扫描"])
app.include_router(stock.router, prefix=f"{settings.api_v1_prefix}/stock", tags=["个股筛选"])
app.include_router(decision.router, prefix=f"{settings.api_v1_prefix}/decision", tags=["决策分析"])
app.include_router(account.router, prefix=f"{settings.api_v1_prefix}/account", tags=["账户适配"])
app.include_router(task.router, prefix=f"{settings.api_v1_prefix}/task", tags=["任务管理"])
app.include_router(system_api.router, prefix=f"{settings.api_v1_prefix}/system", tags=["系统设置"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
