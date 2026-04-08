"""
同花顺概念板块本地同步服务
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from loguru import logger
from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.models.ths_concept_index import ThsConceptIndex
from app.models.ths_concept_member import ThsConceptMember
from app.models.ths_concept_sync_state import ThsConceptSyncState
from app.data.tushare_client import tushare_client


class ThsConceptSyncService:
    """将同花顺概念定义与成分同步到本地数据库，并刷新进程缓存。"""

    SYNC_KEY = "ths_concept"
    BATCH_SIZE = 80
    BATCH_SLEEP_SECONDS = 12.0

    async def refresh_local_cache(self) -> Dict[str, object]:
        """从数据库加载最新概念映射到进程内缓存。"""
        async with async_session_factory() as session:
            state = await self._get_or_create_state(session)
            active_trade_date = str(state.active_trade_date or "").strip()
            if not active_trade_date:
                tushare_client.load_local_ths_concept_snapshot(
                    index_map={},
                    stock_to_codes={},
                    sync_trade_date="",
                    loaded=False,
                )
                return {"concept_count": 0, "stock_count": 0, "sync_trade_date": ""}
            index_result = await session.execute(
                select(ThsConceptIndex).where(ThsConceptIndex.sync_trade_date == active_trade_date)
            )
            member_result = await session.execute(
                select(ThsConceptMember).where(ThsConceptMember.sync_trade_date == active_trade_date)
            )
            index_rows = index_result.scalars().all()
            member_rows = member_result.scalars().all()

        index_map: Dict[str, Dict[str, str]] = {}
        stock_to_codes: Dict[str, List[str]] = defaultdict(list)
        latest_sync_trade_date = ""

        for row in index_rows:
            index_map[row.ts_code] = {
                "name": row.concept_name,
                "type": row.ths_type,
            }
            if row.sync_trade_date and row.sync_trade_date > latest_sync_trade_date:
                latest_sync_trade_date = row.sync_trade_date

        for row in member_rows:
            if row.concept_code not in stock_to_codes[row.stock_code]:
                stock_to_codes[row.stock_code].append(row.concept_code)
            if row.sync_trade_date and row.sync_trade_date > latest_sync_trade_date:
                latest_sync_trade_date = row.sync_trade_date

        tushare_client.load_local_ths_concept_snapshot(
            index_map=index_map,
            stock_to_codes=dict(stock_to_codes),
            sync_trade_date=latest_sync_trade_date,
            loaded=bool(index_map),
        )

        logger.info(
            "已刷新本地 THS 概念缓存 concepts={} stocks={} trade_date={}",
            len(index_map),
            len(stock_to_codes),
            latest_sync_trade_date or "-",
        )
        return {
            "concept_count": len(index_map),
            "stock_count": len(stock_to_codes),
            "sync_trade_date": latest_sync_trade_date,
        }

    async def sync_from_tushare(self, trade_date: str) -> Dict[str, object]:
        """从 Tushare 分批同步同花顺概念定义与成分。"""
        sync_trade_date = str(trade_date or "").replace("-", "")
        concept_rows = tushare_client.fetch_remote_ths_concept_index_rows()
        if not concept_rows:
            raise RuntimeError("未拉取到 THS 概念定义，已终止本地同步")

        concept_rows = sorted(concept_rows, key=lambda row: str(row.get("ts_code") or ""))
        total_concepts = len(concept_rows)
        concept_codes = [str(row.get("ts_code") or "").strip() for row in concept_rows]
        now = datetime.utcnow()

        async with async_session_factory() as session:
            state = await self._get_or_create_state(session)
            reset_required = str(state.target_trade_date or "") != sync_trade_date
            if reset_required:
                state.target_trade_date = sync_trade_date
                state.status = "running"
                state.total_concepts = total_concepts
                state.processed_concepts = 0
                state.next_cursor = 0
                state.last_error = ""
                state.updated_at = now
                await session.execute(delete(ThsConceptMember).where(ThsConceptMember.sync_trade_date == sync_trade_date))
                await session.execute(delete(ThsConceptIndex).where(ThsConceptIndex.sync_trade_date == sync_trade_date))
                session.add_all(
                    [
                        ThsConceptIndex(
                            ts_code=str(row.get("ts_code") or "").strip(),
                            concept_name=str(row.get("concept_name") or "").strip(),
                            ths_type=str(row.get("ths_type") or "").strip(),
                            exchange=str(row.get("exchange") or "A").strip() or "A",
                            sync_trade_date=sync_trade_date,
                            synced_at=now,
                        )
                        for row in concept_rows
                        if str(row.get("ts_code") or "").strip()
                    ]
                )
            else:
                state.total_concepts = total_concepts
                if state.next_cursor > total_concepts:
                    state.next_cursor = total_concepts
                state.status = "running"
                state.last_error = ""
                state.updated_at = now
            await session.commit()
            start_cursor = int(state.next_cursor or 0)

        total_members = 0
        current_cursor = start_cursor
        batch_count = 0
        while current_cursor < total_concepts:
            batch_codes = concept_codes[current_cursor:current_cursor + self.BATCH_SIZE]
            member_rows = tushare_client.fetch_remote_ths_concept_member_rows(batch_codes)
            total_members += len(member_rows)
            batch_now = datetime.utcnow()
            async with async_session_factory() as session:
                await session.execute(
                    delete(ThsConceptMember).where(
                        ThsConceptMember.sync_trade_date == sync_trade_date,
                        ThsConceptMember.concept_code.in_(batch_codes),
                    )
                )
                session.add_all(
                    [
                        ThsConceptMember(
                            concept_code=str(row.get("concept_code") or "").strip(),
                            stock_code=str(row.get("stock_code") or "").strip(),
                            stock_name=str(row.get("stock_name") or "").strip(),
                            sync_trade_date=sync_trade_date,
                            synced_at=batch_now,
                        )
                        for row in member_rows
                        if str(row.get("concept_code") or "").strip()
                        and str(row.get("stock_code") or "").strip()
                    ]
                )
                state = await self._get_or_create_state(session)
                current_cursor += len(batch_codes)
                state.target_trade_date = sync_trade_date
                state.status = "running"
                state.total_concepts = total_concepts
                state.processed_concepts = current_cursor
                state.next_cursor = current_cursor
                state.last_error = ""
                state.updated_at = batch_now
                await session.commit()
            batch_count += 1
            if current_cursor < total_concepts:
                import asyncio
                await asyncio.sleep(self.BATCH_SLEEP_SECONDS)

        async with async_session_factory() as session:
            state = await self._get_or_create_state(session)
            state.target_trade_date = sync_trade_date
            state.active_trade_date = sync_trade_date
            state.status = "completed"
            state.total_concepts = total_concepts
            state.processed_concepts = total_concepts
            state.next_cursor = total_concepts
            state.last_error = ""
            state.updated_at = datetime.utcnow()
            await session.execute(delete(ThsConceptMember).where(ThsConceptMember.sync_trade_date != sync_trade_date))
            await session.execute(delete(ThsConceptIndex).where(ThsConceptIndex.sync_trade_date != sync_trade_date))
            await session.commit()

        cache_state = await self.refresh_local_cache()
        logger.info(
            "THS 概念同步完成 trade_date={} concepts={} members={} batches={}",
            sync_trade_date,
            total_concepts,
            total_members,
            batch_count,
        )
        return {
            "trade_date": sync_trade_date,
            "concept_count": total_concepts,
            "member_count": total_members,
            "batch_count": batch_count,
            "cache": cache_state,
        }

    async def mark_sync_failed(self, trade_date: str, error_message: str) -> None:
        async with async_session_factory() as session:
            state = await self._get_or_create_state(session)
            state.target_trade_date = str(trade_date or "").replace("-", "")
            state.status = "failed"
            state.last_error = str(error_message or "")
            state.updated_at = datetime.utcnow()
            await session.commit()

    async def _get_or_create_state(self, session) -> ThsConceptSyncState:
        result = await session.execute(
            select(ThsConceptSyncState).where(ThsConceptSyncState.sync_key == self.SYNC_KEY)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = ThsConceptSyncState(
            sync_key=self.SYNC_KEY,
            target_trade_date="",
            active_trade_date="",
            status="idle",
            total_concepts=0,
            processed_concepts=0,
            next_cursor=0,
            last_error="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        await session.flush()
        return row


ths_concept_sync_service = ThsConceptSyncService()
