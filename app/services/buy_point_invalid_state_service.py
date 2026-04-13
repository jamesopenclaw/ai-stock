"""
买点失效观察状态服务
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger
from redis import Redis

from app.core.config import settings


class BuyPointInvalidStateService:
    """记录盘中首次跌破失效价的时间，优先走 Redis，失败时回退到进程内存。"""

    def __init__(self) -> None:
        self._client: Optional[Redis] = None
        self._client_ready = False
        self._memory_state: dict[str, str] = {}
        self._ttl_seconds = 15 * 60

    def _get_client(self) -> Optional[Redis]:
        if self._client_ready:
            return self._client
        self._client_ready = True
        try:
            self._client = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:
            logger.warning(f"初始化买点失效观察 Redis 失败，回退内存态: {exc}")
            self._client = None
        return self._client

    def get_first_breach_time(self, state_key: str) -> Optional[str]:
        if not state_key:
            return None
        client = self._get_client()
        if client is not None:
            try:
                value = client.get(state_key)
                if value:
                    return str(value)
            except Exception as exc:
                logger.warning(f"读取买点失效观察 Redis 失败，回退内存态: {exc}")
        return self._memory_state.get(state_key)

    def mark_first_breach_time(self, state_key: str, quote_time: datetime) -> None:
        if not state_key:
            return
        value = quote_time.strftime("%Y-%m-%d %H:%M:%S")
        client = self._get_client()
        if client is not None:
            try:
                client.setex(state_key, self._ttl_seconds, value)
            except Exception as exc:
                logger.warning(f"写入买点失效观察 Redis 失败，回退内存态: {exc}")
        self._memory_state[state_key] = value

    def clear_breach_time(self, state_key: str) -> None:
        if not state_key:
            return
        client = self._get_client()
        if client is not None:
            try:
                client.delete(state_key)
            except Exception as exc:
                logger.warning(f"删除买点失效观察 Redis 失败，回退内存态: {exc}")
        self._memory_state.pop(state_key, None)


buy_point_invalid_state_service = BuyPointInvalidStateService()
