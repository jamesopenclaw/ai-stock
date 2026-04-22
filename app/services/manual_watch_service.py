"""
手动跟踪股票池：持久化与行情补全
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.models.manual_watch_entry import ManualWatchEntry
from app.models.schemas import StockPoolTag
from app.services.decision_context import decision_context_service
from app.services.market_data_gateway import market_data_gateway
from app.services.stock_filter import stock_filter_service


async def list_ts_codes(account_id: str) -> List[Tuple[str, datetime]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ManualWatchEntry.ts_code, ManualWatchEntry.created_at)
            .where(ManualWatchEntry.account_id == account_id)
            .order_by(ManualWatchEntry.created_at.asc())
        )
        return [(str(row[0]), row[1]) for row in result.all()]


async def add_ts_code(account_id: str, ts_code: str) -> None:
    normalized = market_data_gateway.normalize_ts_code(ts_code)
    row = ManualWatchEntry(
        id=str(uuid.uuid4()),
        account_id=account_id,
        ts_code=normalized,
        created_at=datetime.utcnow(),
    )
    async with async_session_factory() as session:
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise


async def remove_ts_code(account_id: str, ts_code: str) -> int:
    normalized = market_data_gateway.normalize_ts_code(ts_code)
    async with async_session_factory() as session:
        result = await session.execute(
            delete(ManualWatchEntry).where(
                ManualWatchEntry.account_id == account_id,
                ManualWatchEntry.ts_code == normalized,
            )
        )
        await session.commit()
        return int(result.rowcount or 0)


async def build_manual_watch_view(
    trade_date: str,
    account_id: Optional[str],
    entries: List[Tuple[str, datetime]],
) -> List[dict]:
    if not entries:
        return []
    ts_codes_ordered = [e[0] for e in entries]
    context = await decision_context_service.build_context(
        trade_date,
        top_gainers=120,
        include_holdings=True,
        account_id=account_id,
    )
    stocks = []
    for code in ts_codes_ordered:
        stocks.append(
            decision_context_service.build_single_stock_input(
                code,
                trade_date,
                candidate_source_tag="手动跟踪",
            )
        )
    scored = stock_filter_service.filter_with_context(
        trade_date,
        stocks,
        market_env=context.market_env,
        sector_scan=context.sector_scan,
        account=context.account,
        holdings=context.holdings_list,
    )
    by_code = {market_data_gateway.normalize_ts_code(s.ts_code): s for s in scored}
    items: List[dict] = []
    for (code, created_at) in entries:
        key = market_data_gateway.normalize_ts_code(code)
        stock = by_code.get(key)
        if not stock:
            continue
        adjusted = stock.model_copy(
            update={
                "stock_pool_tag": StockPoolTag.NOT_IN_POOL,
                "pool_entry_reason": "自选手动跟踪，未纳入自动三池分类结论。",
                "candidate_source_tag": "手动跟踪",
            }
        )
        row = adjusted.model_dump()
        if created_at is not None:
            row["manual_watch_added_at"] = created_at.isoformat()
        items.append(row)
    return items
