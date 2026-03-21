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
    logger.info(f"{settings.app_name} v{settings.app_version} 启动中...")
    
    # 初始化数据库表
    try:
        from app.core.database import engine
        from app.core.database import Base
        from app.models.holding import Holding
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化失败: {e}")


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

app.include_router(market.router, prefix=settings.api_v1_prefix, tags=["市场环境"])
app.include_router(sector.router, prefix=settings.api_v1_prefix, tags=["板块扫描"])
app.include_router(stock.router, prefix=settings.api_v1_prefix, tags=["个股筛选"])
app.include_router(decision.router, prefix=settings.api_v1_prefix, tags=["决策分析"])
app.include_router(account.router, prefix=settings.api_v1_prefix, tags=["账户适配"])
app.include_router(task.router, prefix=settings.api_v1_prefix, tags=["任务管理"])

# 兼容前端按业务分组的路径：/api/v1/market/* /api/v1/decision/* 等
app.include_router(market.router, prefix=f"{settings.api_v1_prefix}/market", tags=["市场环境"])
app.include_router(sector.router, prefix=f"{settings.api_v1_prefix}/sector", tags=["板块扫描"])
app.include_router(stock.router, prefix=f"{settings.api_v1_prefix}/stock", tags=["个股筛选"])
app.include_router(decision.router, prefix=f"{settings.api_v1_prefix}/decision", tags=["决策分析"])
app.include_router(account.router, prefix=f"{settings.api_v1_prefix}/account", tags=["账户适配"])
app.include_router(task.router, prefix=f"{settings.api_v1_prefix}/task", tags=["任务管理"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
