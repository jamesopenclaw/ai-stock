"""
板块扫描完整快照读写服务
"""
import json
import logging
from typing import Optional

from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.data.tushare_client import tushare_client
from app.models.schemas import SectorScanResponse
from app.models.sector_scan_snapshot import SectorScanSnapshot

logger = logging.getLogger(__name__)


def _format_trade_date(trade_date: str) -> str:
    compact = str(trade_date).replace("-", "").strip()[:8]
    if len(compact) != 8:
        return str(trade_date)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _today_trade_date() -> str:
    return tushare_client._now_sh().strftime("%Y-%m-%d")


def _previous_open_trade_date(trade_date: str) -> str:
    compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
    resolved_trade_date = tushare_client._resolve_trade_date(compact_trade_date)
    recent_dates = tushare_client._recent_open_dates(resolved_trade_date, count=2)
    if len(recent_dates) >= 2:
        return _format_trade_date(recent_dates[1])
    return _format_trade_date(resolved_trade_date)


class SectorScanSnapshotService:
    """按交易日缓存完整板块扫描结果。"""

    async def get_snapshot(self, trade_date: str) -> Optional[SectorScanResponse]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(SectorScanSnapshot).where(
                    SectorScanSnapshot.trade_date == trade_date,
                )
            )
            row = result.scalar_one_or_none()

        if not row or not row.payload_json:
            return None

        try:
            payload = json.loads(row.payload_json)
            if row.resolved_trade_date and not payload.get("resolved_trade_date"):
                payload["resolved_trade_date"] = row.resolved_trade_date
            return SectorScanResponse.model_validate(payload)
        except Exception as exc:
            logger.warning("板块扫描快照反序列化失败: %s", exc)
            return None

    async def save_snapshot(self, trade_date: str, scan_result: SectorScanResponse) -> int:
        payload_json = json.dumps(
            scan_result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )

        async with async_session_factory() as session:
            await session.execute(
                delete(SectorScanSnapshot).where(
                    SectorScanSnapshot.trade_date == trade_date,
                )
            )
            session.add(
                SectorScanSnapshot(
                    trade_date=trade_date,
                    resolved_trade_date=scan_result.resolved_trade_date or "",
                    payload_json=payload_json,
                )
            )
            await session.commit()

        return 1


sector_scan_snapshot_service = SectorScanSnapshotService()


async def resolve_snapshot_lookup_trade_date(trade_date: str) -> str:
    """
    默认读取板块结果时使用的稳定快照日：
    - 非今天：直接使用请求日
    - 今天且已有当天快照：使用今天
    - 否则优先使用最近已完成交易日
    - 若最近已完成交易日仍是今天，则回退到前一交易日
    """
    if trade_date != _today_trade_date():
        return trade_date

    today_snapshot = await sector_scan_snapshot_service.get_snapshot(trade_date)
    if today_snapshot:
        return trade_date

    last_completed_trade_date = _format_trade_date(
        tushare_client.get_last_completed_trade_date(trade_date)
    )
    if last_completed_trade_date != trade_date:
        return last_completed_trade_date

    return _previous_open_trade_date(trade_date)
