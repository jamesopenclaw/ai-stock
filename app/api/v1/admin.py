"""
管理员 API
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password, require_admin
from app.models.account_setting import AccountSetting
from app.models.schemas import ApiResponse
from app.models.trading_account import TradingAccount
from app.models.user import User
from app.services.trading_account_service import create_trading_account, serialize_account


router = APIRouter()


class CreateUserRequest(BaseModel):
    """创建用户请求。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=64)
    role: str = Field("user", pattern="^(admin|user)$")
    status: str = Field("active", pattern="^(active|disabled)$")
    default_account_id: Optional[str] = None


class UpdateUserRequest(BaseModel):
    """更新用户请求。"""

    display_name: Optional[str] = Field(None, min_length=1, max_length=64)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")
    default_account_id: Optional[str] = None


class CreateAccountRequest(BaseModel):
    """创建账户请求。"""

    account_code: str = Field(..., min_length=1, max_length=64)
    account_name: str = Field(..., min_length=1, max_length=64)
    available_cash: Optional[float] = Field(None, ge=0)
    owner_user_id: Optional[str] = None
    status: str = Field("active", pattern="^(active|disabled)$")


class UpdateAccountRequest(BaseModel):
    """更新账户请求。"""

    account_name: Optional[str] = Field(None, min_length=1, max_length=64)
    available_cash: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")


class BindAccountRequest(BaseModel):
    """绑定账户请求。"""

    user_id: Optional[str] = None
    set_default: bool = True


def _serialize_user(user: User, account_lookup: dict[str, TradingAccount]) -> dict:
    default_account = account_lookup.get(user.default_account_id or "")
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "default_account_id": user.default_account_id,
        "default_account_name": default_account.account_name if default_account else None,
        "role": user.role,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("/users", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def list_users() -> ApiResponse:
    """管理员查看用户列表。"""
    async with async_session_factory() as session:
        users_result = await session.execute(select(User).order_by(User.created_at.asc()))
        users = users_result.scalars().all()
        account_result = await session.execute(select(TradingAccount))
        accounts = account_result.scalars().all()

    account_lookup = {account.id: account for account in accounts}
    return ApiResponse(
        data={
            "users": [_serialize_user(user, account_lookup) for user in users],
            "total": len(users),
        }
    )


@router.post("/users", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def create_user(request: CreateUserRequest) -> ApiResponse:
    """管理员创建用户。"""
    async with async_session_factory() as session:
        existing = await session.execute(select(User).where(User.username == request.username.strip()))
        if existing.scalar_one_or_none():
            return ApiResponse(code=400, message="用户名已存在")

        if request.default_account_id:
            account_result = await session.execute(
                select(TradingAccount).where(TradingAccount.id == request.default_account_id)
            )
            if account_result.scalar_one_or_none() is None:
                return ApiResponse(code=400, message="默认账户不存在")

        user = User(
            id=str(uuid.uuid4()),
            username=request.username.strip(),
            password_hash=hash_password(request.password),
            display_name=request.display_name.strip(),
            default_account_id=request.default_account_id,
            role=request.role,
            status=request.status,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return ApiResponse(data={"user": _serialize_user(user, {})})


@router.put("/users/{user_id}", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def update_user(user_id: str, request: UpdateUserRequest) -> ApiResponse:
    """管理员更新用户。"""
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return ApiResponse(code=404, message="用户不存在")

        payload = request.model_dump(exclude_unset=True)
        default_account_id = payload.get("default_account_id")
        if "default_account_id" in payload and default_account_id:
            account_result = await session.execute(
                select(TradingAccount).where(TradingAccount.id == default_account_id)
            )
            if account_result.scalar_one_or_none() is None:
                return ApiResponse(code=400, message="默认账户不存在")

        for key, value in payload.items():
            setattr(user, key, value)

        await session.commit()
        await session.refresh(user)

        account_result = await session.execute(select(TradingAccount))
        accounts = account_result.scalars().all()

    account_lookup = {account.id: account for account in accounts}
    return ApiResponse(data={"user": _serialize_user(user, account_lookup)})


@router.get("/accounts", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def list_accounts() -> ApiResponse:
    """管理员查看交易账户列表。"""
    async with async_session_factory() as session:
        account_result = await session.execute(
            select(TradingAccount).order_by(TradingAccount.created_at.asc())
        )
        accounts = account_result.scalars().all()
        setting_result = await session.execute(select(AccountSetting))
        settings = setting_result.scalars().all()

        user_result = await session.execute(select(User))
        users = user_result.scalars().all()

    user_lookup = {user.id: user for user in users}
    setting_lookup = {row.account_id: row for row in settings}
    return ApiResponse(
        data={
            "accounts": [
                {
                    **serialize_account(account),
                    "available_cash": (
                        float(setting_lookup[account.id].available_cash)
                        if setting_lookup.get(account.id) and setting_lookup[account.id].available_cash is not None
                        else (
                            float(setting_lookup[account.id].total_asset)
                            if setting_lookup.get(account.id)
                            else None
                        )
                    ),
                    "owner_username": user_lookup.get(account.owner_user_id).username
                    if user_lookup.get(account.owner_user_id)
                    else None,
                    "owner_display_name": user_lookup.get(account.owner_user_id).display_name
                    if user_lookup.get(account.owner_user_id)
                    else None,
                }
                for account in accounts
            ],
            "total": len(accounts),
        }
    )


@router.post("/accounts", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def create_account(request: CreateAccountRequest) -> ApiResponse:
    """管理员创建交易账户。"""
    async with async_session_factory() as session:
        existing = await session.execute(
            select(TradingAccount).where(TradingAccount.account_code == request.account_code.strip())
        )
        if existing.scalar_one_or_none():
            return ApiResponse(code=400, message="账户编码已存在")
        if request.owner_user_id:
            user_result = await session.execute(select(User).where(User.id == request.owner_user_id))
            if user_result.scalar_one_or_none() is None:
                return ApiResponse(code=400, message="归属用户不存在")

    account = await create_trading_account(
        request.account_code.strip(),
        request.account_name.strip(),
        owner_user_id=request.owner_user_id,
        status=request.status,
    )
    if request.available_cash is not None:
        from app.services.account_config_service import update_available_cash

        await update_available_cash(float(request.available_cash), account_id=account.id)
    return ApiResponse(data={"account": serialize_account(account)})


@router.put("/accounts/{account_id}", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def update_account(account_id: str, request: UpdateAccountRequest) -> ApiResponse:
    """管理员更新交易账户。"""
    async with async_session_factory() as session:
        result = await session.execute(select(TradingAccount).where(TradingAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            return ApiResponse(code=404, message="交易账户不存在")

        payload = request.model_dump(exclude_unset=True)
        available_cash = payload.pop("available_cash", None)
        for key, value in payload.items():
            setattr(account, key, value)

        await session.commit()
        await session.refresh(account)

    if available_cash is not None:
        from app.services.account_config_service import update_available_cash

        await update_available_cash(float(available_cash), account_id=account_id)

    return ApiResponse(data={"account": serialize_account(account)})


@router.post("/accounts/{account_id}/bind-user", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def bind_account_user(account_id: str, request: BindAccountRequest) -> ApiResponse:
    """管理员绑定账户到用户。"""
    async with async_session_factory() as session:
        account_result = await session.execute(select(TradingAccount).where(TradingAccount.id == account_id))
        account = account_result.scalar_one_or_none()
        if not account:
            return ApiResponse(code=404, message="交易账户不存在")

        previous_owner_id = account.owner_user_id
        user = None
        if request.user_id:
            user_result = await session.execute(select(User).where(User.id == request.user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                return ApiResponse(code=404, message="用户不存在")

        account.owner_user_id = user.id if user else None
        if user and (request.set_default or not user.default_account_id):
            user.default_account_id = account.id
        if previous_owner_id and previous_owner_id != request.user_id:
            previous_user_result = await session.execute(select(User).where(User.id == previous_owner_id))
            previous_user = previous_user_result.scalar_one_or_none()
            if previous_user and previous_user.default_account_id == account.id:
                previous_user.default_account_id = None
        await session.commit()
        await session.refresh(account)

    return ApiResponse(
        data={
            "account": serialize_account(account),
            "user_id": request.user_id,
            "set_default": request.set_default,
        }
    )
