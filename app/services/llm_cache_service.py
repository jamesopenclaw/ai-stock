"""
LLM 解释缓存服务
"""
import json
from typing import Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.llm_cache_entry import LlmCacheEntry


class LlmCacheService:
    """按场景与输入签名缓存 LLM 解释结果。"""

    async def get_cache(self, *, cache_key: str) -> Optional[Dict]:
        if not cache_key:
            return None
        try:
            async with async_session_factory() as session:
                row = (
                    await session.execute(
                        select(LlmCacheEntry).where(LlmCacheEntry.cache_key == cache_key)
                    )
                ).scalar_one_or_none()
            if not row or not row.response_json:
                return None
            return json.loads(row.response_json)
        except Exception as exc:
            logger.warning(f"读取 LLM 缓存失败: {exc}")
            return None

    async def upsert_cache(
        self,
        *,
        scene: str,
        cache_key: str,
        trade_date: str,
        provider: str,
        model: str,
        payload: Dict,
        response: Dict,
    ) -> None:
        if not cache_key:
            return
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            response_json = json.dumps(response, ensure_ascii=False, sort_keys=True)
            async with async_session_factory() as session:
                row = (
                    await session.execute(
                        select(LlmCacheEntry).where(LlmCacheEntry.cache_key == cache_key)
                    )
                ).scalar_one_or_none()
                if row is None:
                    session.add(
                        LlmCacheEntry(
                            scene=scene or "",
                            cache_key=cache_key,
                            trade_date=trade_date or "",
                            provider=provider or "",
                            model=model or "",
                            payload_json=payload_json,
                            response_json=response_json,
                        )
                    )
                else:
                    row.scene = scene or row.scene
                    row.trade_date = trade_date or row.trade_date
                    row.provider = provider or row.provider
                    row.model = model or row.model
                    row.payload_json = payload_json
                    row.response_json = response_json
                await session.commit()
        except Exception as exc:
            logger.warning(f"写入 LLM 缓存失败: {exc}")


llm_cache_service = LlmCacheService()
