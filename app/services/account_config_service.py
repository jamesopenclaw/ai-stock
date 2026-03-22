"""
账户配置读写（PostgreSQL account_config 表）
"""
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.account_config import AccountConfig

SINGLETON_ID = 1


async def get_total_asset() -> float:
    """读取配置中的总资产（元）；无记录时回退到 settings.qingzhou_total_asset。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return float(row.total_asset)
        return float(settings.qingzhou_total_asset)


async def get_config() -> Dict[str, Any]:
    """返回当前账户配置（用于 GET /account/config）。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        if row is None:
            default = float(settings.qingzhou_total_asset)
            return {
                "total_asset": default,
                "updated_at": None,
            }
        return {
            "total_asset": float(row.total_asset),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


async def update_total_asset(total_asset: float) -> Dict[str, Any]:
    """更新总资产（元）。"""
    if total_asset <= 0:
        raise ValueError("总资产必须大于 0")

    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountConfig).where(AccountConfig.id == SINGLETON_ID)
        )
        row = result.scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = AccountConfig(id=SINGLETON_ID, total_asset=total_asset, updated_at=now)
            session.add(row)
        else:
            row.total_asset = total_asset
            row.updated_at = now
        await session.commit()
        await session.refresh(row)
        return {
            "total_asset": float(row.total_asset),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
