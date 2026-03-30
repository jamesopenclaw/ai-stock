"""
认证 API
"""
from datetime import datetime, timezone
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import (
    authenticate_user,
    create_access_token,
    create_refresh_session,
    get_current_user,
    get_current_account,
    revoke_refresh_session,
    rotate_refresh_session,
    serialize_user,
)
from app.models.schemas import ApiResponse
from app.services.trading_account_service import get_user_default_account, serialize_account
from app.core.security import AuthenticatedAccount


router = APIRouter()


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """刷新令牌请求。"""

    refresh_token: str = Field(..., min_length=16)


class LogoutRequest(BaseModel):
    """登出请求。"""

    refresh_token: str = Field(..., min_length=16)


async def _build_auth_payload(user, access_token: str, refresh_token: str, refresh_expires_at) -> dict:
    started = time.perf_counter()
    refresh_expires_in = max(
        int((refresh_expires_at - datetime.now(timezone.utc)).total_seconds()),
        0,
    )
    account = await get_user_default_account(user.id, getattr(user, "default_account_id", None))
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= 500:
        logger.warning("auth.build_payload user_id={} account_lookup_ms={:.1f}", user.id, elapsed_ms)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(settings.auth_access_token_expire_minutes * 60),
        "refresh_token": refresh_token,
        "refresh_expires_in": refresh_expires_in,
        "user": serialize_user(user),
        "account": serialize_account(account),
    }


@router.post("/login", response_model=ApiResponse)
async def login(request: LoginRequest) -> ApiResponse:
    """用户名密码登录。"""
    started = time.perf_counter()
    user = await authenticate_user(request.username, request.password)
    if not user:
        logger.info("auth.login username={} result=unauthorized total_ms={:.1f}", request.username, (time.perf_counter() - started) * 1000)
        return JSONResponse(
            status_code=401,
            content=ApiResponse(code=401, message="用户名或密码错误").model_dump(),
        )

    access_token = create_access_token(user)
    refresh_token, refresh_expires_at = await create_refresh_session(user.id)
    response = ApiResponse(
        data=await _build_auth_payload(user, access_token, refresh_token, refresh_expires_at)
    )
    total_ms = (time.perf_counter() - started) * 1000
    log_fn = logger.warning if total_ms >= 2000 else logger.info
    log_fn("auth.login username={} user_id={} result=ok total_ms={:.1f}", request.username, user.id, total_ms)
    return response


@router.post("/refresh", response_model=ApiResponse)
async def refresh_token(request: RefreshRequest) -> ApiResponse:
    """刷新 access token，并轮换 refresh token。"""
    started = time.perf_counter()
    rotated = await rotate_refresh_session(request.refresh_token)
    if not rotated:
        logger.info("auth.refresh result=invalid total_ms={:.1f}", (time.perf_counter() - started) * 1000)
        return JSONResponse(
            status_code=401,
            content=ApiResponse(code=401, message="刷新令牌无效或已过期").model_dump(),
        )

    user, new_refresh_token, refresh_expires_at = rotated
    access_token = create_access_token(user)
    response = ApiResponse(
        data=await _build_auth_payload(user, access_token, new_refresh_token, refresh_expires_at)
    )
    total_ms = (time.perf_counter() - started) * 1000
    log_fn = logger.warning if total_ms >= 2000 else logger.info
    log_fn("auth.refresh user_id={} result=ok total_ms={:.1f}", user.id, total_ms)
    return response


@router.post("/logout", response_model=ApiResponse)
async def logout(request: LogoutRequest) -> ApiResponse:
    """注销当前 refresh session。"""
    started = time.perf_counter()
    await revoke_refresh_session(request.refresh_token)
    logger.info("auth.logout result=ok total_ms={:.1f}", (time.perf_counter() - started) * 1000)
    return ApiResponse(data={"success": True})


@router.get("/me", response_model=ApiResponse)
async def me(
    current_user=Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    """获取当前登录用户。"""
    started = time.perf_counter()
    response = ApiResponse(
        data={
            "user": serialize_user(current_user),
            "account": serialize_account(current_account),
        }
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= 200:
        logger.warning("auth.me user_id={} account_id={} total_ms={:.1f}", current_user.id, current_account.id, elapsed_ms)
    return response
