"""独立通知刷新 worker。"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger

from app.core.config import settings
from app.runtime.notification_refresh import notification_refresh_loop
from app.services.ths_concept_sync_service import ths_concept_sync_service


logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)


async def main() -> None:
    """启动独立通知刷新进程。"""
    settings.validate_runtime()
    logger.info("通知刷新 worker 启动中...")

    try:
        await ths_concept_sync_service.refresh_local_cache()
    except Exception as exc:
        logger.warning("加载本地 THS 概念缓存失败: {}", exc)

    await notification_refresh_loop()


if __name__ == "__main__":
    asyncio.run(main())
