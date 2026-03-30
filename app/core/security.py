"""
认证与权限控制
"""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.trading_account import TradingAccount
from app.models.user import User
from app.models.user_session import UserSession


pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,
)

ACCESS_TOKEN_TYPE = "access"


class AuthenticatedUser(BaseModel):
    """当前认证用户上下文。"""

    id: str
    username: str
    display_name: str
    default_account_id: Optional[str] = None
    role: str
    status: str


class AuthenticatedAccount(BaseModel):
    """当前认证账户上下文。"""

    id: str
    account_code: str
    account_name: str
    owner_user_id: Optional[str] = None
    status: str = "active"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _auth_disabled_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id="auth-disabled",
        username="auth-disabled",
        display_name="Auth Disabled",
        default_account_id=None,
        role="admin",
        status="active",
    )


def _auth_disabled_account() -> AuthenticatedAccount:
    return AuthenticatedAccount(
        id="auth-disabled-account",
        account_code="AUTH-DISABLED",
        account_name="Auth Disabled Account",
        owner_user_id=None,
        status="active",
    )


def hash_password(password: str) -> str:
    """生成密码哈希。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验密码。"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """对 refresh token 做不可逆哈希。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User) -> str:
    """生成访问令牌。"""
    expires_at = _utcnow() + timedelta(minutes=settings.auth_access_token_expire_minutes)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "type": ACCESS_TOKEN_TYPE,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token() -> str:
    """生成 refresh token 原文。"""
    return secrets.token_urlsafe(48)


def serialize_user(user: User | AuthenticatedUser) -> dict:
    """输出前端可消费的用户公开信息。"""
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "default_account_id": getattr(user, "default_account_id", None),
        "role": user.role,
        "status": user.status,
    }


async def authenticate_user(username: str, password: str) -> Optional[User]:
    """校验用户名密码。"""
    started = time.perf_counter()
    async with async_session_factory() as session:
        query_started = time.perf_counter()
        result = await session.execute(
            select(User).where(User.username == username.strip())
        )
        user = result.scalar_one_or_none()
        query_ms = (time.perf_counter() - query_started) * 1000

        if not user or user.status != "active":
            logger.info("auth.authenticate_user username={} result=not_found query_ms={:.1f} total_ms={:.1f}", username, query_ms, (time.perf_counter() - started) * 1000)
            return None
        verify_started = time.perf_counter()
        if not verify_password(password, user.password_hash):
            logger.info(
                "auth.authenticate_user username={} result=bad_password query_ms={:.1f} verify_ms={:.1f} total_ms={:.1f}",
                username,
                query_ms,
                (time.perf_counter() - verify_started) * 1000,
                (time.perf_counter() - started) * 1000,
            )
            return None

        commit_started = time.perf_counter()
        user.last_login_at = datetime.utcnow()
        await session.commit()
        total_ms = (time.perf_counter() - started) * 1000
        commit_ms = (time.perf_counter() - commit_started) * 1000
        verify_ms = (commit_started - verify_started) * 1000
        log_fn = logger.warning if total_ms >= 2000 else logger.info
        log_fn(
            "auth.authenticate_user username={} result=ok query_ms={:.1f} verify_ms={:.1f} commit_ms={:.1f} total_ms={:.1f}",
            username,
            query_ms,
            verify_ms,
            commit_ms,
            total_ms,
        )
        return user


async def create_refresh_session(user_id: str) -> tuple[str, datetime]:
    """创建 refresh session，并返回原始 token 和过期时间。"""
    started = time.perf_counter()
    raw_token = create_refresh_token()
    expires_at = _utcnow() + timedelta(days=settings.auth_refresh_token_expire_days)

    async with async_session_factory() as session:
        session.add(
            UserSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=hash_token(raw_token),
                expires_at=expires_at,
                revoked_at=None,
            )
        )
        await session.commit()

    elapsed_ms = (time.perf_counter() - started) * 1000
    log_fn = logger.warning if elapsed_ms >= 1000 else logger.info
    log_fn("auth.create_refresh_session user_id={} elapsed_ms={:.1f}", user_id, elapsed_ms)
    return raw_token, expires_at


async def rotate_refresh_session(refresh_token: str) -> Optional[tuple[User, str, datetime]]:
    """校验并轮换 refresh token。"""
    started = time.perf_counter()
    now = _utcnow()
    token_hash_value = hash_token(refresh_token)

    async with async_session_factory() as session:
        result = await session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == token_hash_value)
        )
        row = result.first()
        if not row:
            logger.info("auth.rotate_refresh_session result=not_found elapsed_ms={:.1f}", (time.perf_counter() - started) * 1000)
            return None

        session_row, user = row
        if (
            session_row.revoked_at is not None
            or session_row.expires_at is None
            or session_row.expires_at <= now
            or user.status != "active"
        ):
            logger.info("auth.rotate_refresh_session user_id={} result=invalid elapsed_ms={:.1f}", user.id, (time.perf_counter() - started) * 1000)
            return None

        session_row.revoked_at = now

        new_token = create_refresh_token()
        new_expires_at = now + timedelta(days=settings.auth_refresh_token_expire_days)
        session.add(
            UserSession(
                id=str(uuid.uuid4()),
                user_id=user.id,
                token_hash=hash_token(new_token),
                expires_at=new_expires_at,
                revoked_at=None,
            )
        )
        await session.commit()
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_fn = logger.warning if elapsed_ms >= 1000 else logger.info
        log_fn("auth.rotate_refresh_session user_id={} result=ok elapsed_ms={:.1f}", user.id, elapsed_ms)
        return user, new_token, new_expires_at


async def revoke_refresh_session(refresh_token: str) -> None:
    """注销 refresh token。"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.token_hash == hash_token(refresh_token))
        )
        session_row = result.scalar_one_or_none()
        if not session_row or session_row.revoked_at is not None:
            return

        session_row.revoked_at = _utcnow()
        await session.commit()


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> AuthenticatedUser:
    """从 access token 中解析当前用户。"""
    started = time.perf_counter()
    if not settings.auth_enabled:
        return _auth_disabled_user()

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已失效",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise credentials_error
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise credentials_error

    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= 500:
        logger.warning("auth.get_current_user user_id={} elapsed_ms={:.1f}", user.id, elapsed_ms)
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        default_account_id=user.default_account_id,
        role=user.role,
        status=user.status,
    )


async def require_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """要求当前用户为管理员。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户无管理员权限",
        )
    return current_user


async def _load_active_account_by_id(account_id: str) -> Optional[TradingAccount]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(TradingAccount).where(
                TradingAccount.id == account_id,
                TradingAccount.status == "active",
            )
        )
        return result.scalar_one_or_none()


async def get_current_account(
    current_user: AuthenticatedUser = Depends(get_current_user),
    requested_account_id: Optional[str] = Header(None, alias="X-Account-Id"),
) -> AuthenticatedAccount:
    """解析当前登录用户默认账户。"""
    started = time.perf_counter()
    if not settings.auth_enabled:
        return _auth_disabled_account()

    normalized_requested_account_id = str(requested_account_id or "").strip()
    if normalized_requested_account_id:
        account = await _load_active_account_by_id(normalized_requested_account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标交易账户不存在或已停用",
            )
        if current_user.role != "admin" and account.owner_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前用户无权访问该交易账户",
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= 500:
            logger.warning(
                "auth.get_current_account user_id={} source=requested account_id={} elapsed_ms={:.1f}",
                current_user.id,
                account.id,
                elapsed_ms,
            )
        return AuthenticatedAccount(
            id=account.id,
            account_code=account.account_code,
            account_name=account.account_name,
            owner_user_id=account.owner_user_id,
            status=account.status,
        )

    async with async_session_factory() as session:
        account = None
        if current_user.default_account_id:
            result = await session.execute(
                select(TradingAccount).where(
                    TradingAccount.id == current_user.default_account_id,
                    TradingAccount.status == "active",
                )
            )
            account = result.scalar_one_or_none()

        if account is None:
            result = await session.execute(
                select(TradingAccount)
                .where(
                    TradingAccount.owner_user_id == current_user.id,
                    TradingAccount.status == "active",
                )
                .order_by(TradingAccount.created_at.asc())
            )
            account = result.scalars().first()

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前用户未绑定可用交易账户",
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= 500:
        logger.warning(
            "auth.get_current_account user_id={} source=default account_id={} elapsed_ms={:.1f}",
            current_user.id,
            account.id,
            elapsed_ms,
        )
    return AuthenticatedAccount(
        id=account.id,
        account_code=account.account_code,
        account_name=account.account_name,
        owner_user_id=account.owner_user_id,
        status=account.status,
    )
