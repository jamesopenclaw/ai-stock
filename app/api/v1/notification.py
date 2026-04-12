"""通知中心 API"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.security import AuthenticatedAccount, AuthenticatedUser, get_current_account, get_current_user
from app.models.schemas import (
    ApiResponse,
    NotificationCategory,
    NotificationPriority,
    NotificationReadRequest,
    NotificationSettingsPayload,
    NotificationSnoozeRequest,
    NotificationStatus,
    NotificationWecomTestRequest,
)
from app.services.notification_engine import notification_engine
from app.services.notification_service import notification_service

router = APIRouter()


def _enum_value(value):
    raw = getattr(value, "default", value)
    return getattr(raw, "value", raw)


def _current_trade_date() -> str:
    return datetime.now(ZoneInfo(settings.notification_timezone)).strftime("%Y-%m-%d")


async def _refresh_notifications(
    current_account: AuthenticatedAccount,
    current_user: Optional[AuthenticatedUser] = None,
) -> None:
    try:
        await notification_engine.refresh_account_events(
            current_account.id,
            user_id=getattr(current_user, "id", None),
            trade_date=_current_trade_date(),
            force=False,
        )
    except Exception:
        # 通知面板不能因为后台刷新失败而阻塞读取。
        return


@router.get("/notifications", response_model=ApiResponse)
async def list_notifications(
    status: Optional[NotificationStatus] = Query(None, description="状态筛选"),
    category: Optional[NotificationCategory] = Query(None, description="分类筛选"),
    priority: Optional[NotificationPriority] = Query(None, description="优先级筛选"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    await _refresh_notifications(current_account, current_user)
    result = await notification_service.list_events(
        current_account.id,
        status=_enum_value(status) if status else None,
        category=_enum_value(category) if category else None,
        priority=_enum_value(priority) if priority else None,
        limit=limit,
    )
    return ApiResponse(data=result.model_dump(mode="json"))


@router.get("/notifications/summary", response_model=ApiResponse)
async def get_notification_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    await _refresh_notifications(current_account, current_user)
    result = await notification_service.get_summary(current_account.id)
    return ApiResponse(data=result.model_dump(mode="json"))


@router.post("/notifications/{event_id}/read", response_model=ApiResponse)
async def mark_notification_read(
    event_id: str,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    success = await notification_service.mark_read(current_account.id, event_id)
    return ApiResponse(data={"success": success})


@router.post("/notifications/{event_id}/dismiss", response_model=ApiResponse)
async def dismiss_notification(
    event_id: str,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    success = await notification_service.dismiss(current_account.id, event_id)
    return ApiResponse(data={"success": success})


@router.post("/notifications/{event_id}/snooze", response_model=ApiResponse)
async def snooze_notification(
    event_id: str,
    request: NotificationSnoozeRequest,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    success = await notification_service.snooze(current_account.id, event_id, request.minutes)
    return ApiResponse(data={"success": success})


@router.post("/notifications/read-all", response_model=ApiResponse)
async def read_all_notifications(
    request: NotificationReadRequest,
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    updated = await notification_service.mark_all_read(
        current_account.id,
        ids=request.ids or None,
        status=_enum_value(request.status) if request.status else None,
        category=_enum_value(request.category) if request.category else None,
        priority=_enum_value(request.priority) if request.priority else None,
        exclude_priorities=[_enum_value(item) for item in (request.exclude_priorities or [])],
    )
    return ApiResponse(data={"updated": updated})


@router.get("/notifications/settings", response_model=ApiResponse)
async def get_notification_settings(
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    result = await notification_service.get_settings(
        current_account.id,
        user_id=current_user.id,
    )
    return ApiResponse(data=result.model_dump(mode="json"))


@router.put("/notifications/settings", response_model=ApiResponse)
async def update_notification_settings(
    payload: NotificationSettingsPayload,
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    result = await notification_service.update_settings(
        current_account.id,
        payload,
        user_id=current_user.id,
    )
    return ApiResponse(data=result.model_dump(mode="json"))


@router.post("/notifications/settings/test-wecom", response_model=ApiResponse)
async def test_notification_wecom(
    request: NotificationWecomTestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    success = await notification_service.send_wecom_test_message(
        current_account.id,
        account_name=current_account.account_name,
        user_id=current_user.id,
        webhook_url=request.webhook_url,
    )
    return ApiResponse(data={"success": bool(success)})
