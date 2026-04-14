"""通知后台刷新运行时。"""
from __future__ import annotations

import asyncio
from datetime import datetime, time
from time import monotonic
from zoneinfo import ZoneInfo

from loguru import logger

from app.core.config import settings
from app.services.notification_engine import notification_engine

_MARKET_TIMEZONE = ZoneInfo(settings.notification_timezone)
_TRADING_WINDOWS = (
    (time(9, 25), time(11, 30)),
    (time(13, 0), time(15, 0)),
)


def is_market_monitor_window(now: datetime | None = None) -> bool:
    """仅在交易日的盘中窗口内执行通知刷新。"""
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


async def notification_refresh_loop() -> None:
    """后台定时生成通知事件，避免请求路径同步重算。"""
    interval_seconds = max(10, int(settings.notification_refresh_interval_seconds))
    initial_delay_seconds = max(0, int(settings.notification_refresh_initial_delay_seconds))

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    while True:
        cycle_started_at = monotonic()
        try:
            if is_market_monitor_window():
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
