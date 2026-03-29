"""
交易账户相关服务
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.account_setting import AccountSetting
from app.models.trading_account import TradingAccount
from app.models.user import User


def serialize_account(account: Optional[TradingAccount]) -> Optional[dict]:
    """输出前端可消费的账户公开信息。"""
    if not account:
        return None
    return {
        "id": account.id,
        "account_code": account.account_code,
        "account_name": account.account_name,
        "owner_user_id": account.owner_user_id,
        "status": account.status,
    }


async def get_user_default_account(user_id: str, default_account_id: Optional[str] = None) -> Optional[TradingAccount]:
    """读取用户当前默认账户。"""
    async with async_session_factory() as session:
        if default_account_id:
            result = await session.execute(
                select(TradingAccount).where(
                    TradingAccount.id == default_account_id,
                    TradingAccount.status == "active",
                )
            )
            account = result.scalar_one_or_none()
            if account:
                return account

        result = await session.execute(
            select(TradingAccount)
            .where(
                TradingAccount.owner_user_id == user_id,
                TradingAccount.status == "active",
            )
            .order_by(TradingAccount.created_at.asc())
        )
        return result.scalars().first()


async def ensure_account_setting(account_id: str) -> None:
    """确保账户设置存在。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountSetting).where(AccountSetting.account_id == account_id)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return

        session.add(
            AccountSetting(
                account_id=account_id,
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


async def create_trading_account(
    account_code: str,
    account_name: str,
    *,
    owner_user_id: Optional[str] = None,
    status: str = "active",
) -> TradingAccount:
    """创建交易账户及对应账户设置。"""
    async with async_session_factory() as session:
        account = TradingAccount(
            id=str(uuid.uuid4()),
            account_code=account_code,
            account_name=account_name,
            owner_user_id=owner_user_id,
            status=status,
        )
        session.add(account)
        await session.flush()
        session.add(
            AccountSetting(
                account_id=account.id,
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

        if owner_user_id:
            user_result = await session.execute(select(User).where(User.id == owner_user_id))
            user = user_result.scalar_one_or_none()
            if user and not user.default_account_id:
                user.default_account_id = account.id

        await session.commit()
        await session.refresh(account)
        return account
