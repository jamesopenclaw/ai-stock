"""系统相关 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.models.schemas import ApiResponse
from app.core.security import AuthenticatedAccount, AuthenticatedUser, get_current_account, get_current_user
from app.services.llm_call_log_service import llm_call_log_service
from app.services.account_config_service import get_config as get_platform_config, update_config as update_platform_config

router = APIRouter()


class SystemConfigUpdateRequest(BaseModel):
    llm_enabled: Optional[bool] = Field(None, description="是否启用 LLM 辅助层")
    llm_provider: Optional[str] = Field(None, description="LLM 供应商")
    llm_base_url: Optional[str] = Field(None, description="LLM Base URL")
    llm_api_key: Optional[str] = Field(None, description="LLM API Key，留空则保持不变")
    clear_llm_api_key: Optional[bool] = Field(None, description="是否清空已保存的 API Key")
    llm_model: Optional[str] = Field(None, description="LLM 模型名")
    llm_timeout_seconds: Optional[float] = Field(None, gt=0, description="LLM 超时秒数")
    llm_temperature: Optional[float] = Field(None, ge=0, le=2, description="LLM 温度")
    llm_max_input_items: Optional[int] = Field(None, ge=1, le=20, description="单次最大输入条数")


def _ensure_admin(current_user: AuthenticatedUser) -> None:
    if current_user.role != "admin":
        raise PermissionError("仅管理员可修改系统级模型配置")


@router.get("/config", response_model=ApiResponse)
async def get_system_config(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse:
    try:
        _ensure_admin(current_user)
        data = await get_platform_config()
        return ApiResponse(data=data)
    except PermissionError as e:
        return ApiResponse(code=403, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"获取系统配置失败：{str(e)}")


@router.put("/config", response_model=ApiResponse)
async def put_system_config(
    request: SystemConfigUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse:
    try:
        _ensure_admin(current_user)
        data = await update_platform_config(request.model_dump())
        return ApiResponse(data=data)
    except PermissionError as e:
        return ApiResponse(code=403, message=str(e))
    except ValueError as e:
        return ApiResponse(code=400, message=str(e))
    except Exception as e:
        return ApiResponse(code=500, message=f"更新系统配置失败：{str(e)}")


@router.get("/llm/logs", response_model=ApiResponse)
async def get_llm_call_logs(
    limit: int = Query(100, ge=1, le=500, description="返回数量"),
    scene: Optional[str] = Query(None, description="调用场景"),
    status: Optional[str] = Query(None, description="调用状态"),
    success: Optional[bool] = Query(None, description="是否成功"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    account_id = None if current_user.role == "admin" else current_account.id
    logs = await llm_call_log_service.list_logs(
        limit=limit,
        scene=scene,
        status=status,
        success=success,
        account_id=account_id,
    )
    return ApiResponse(
        data={
            "logs": logs,
            "total": len(logs),
        }
    )


@router.get("/llm/logs/daily-stats", response_model=ApiResponse)
async def get_llm_call_daily_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    scene: Optional[str] = Query(None, description="调用场景"),
    status: Optional[str] = Query(None, description="调用状态"),
    success: Optional[bool] = Query(None, description="是否成功"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_account: AuthenticatedAccount = Depends(get_current_account),
) -> ApiResponse:
    account_id = None if current_user.role == "admin" else current_account.id
    stats = await llm_call_log_service.get_daily_stats(
        days=days,
        scene=scene,
        status=status,
        success=success,
        account_id=account_id,
    )
    return ApiResponse(data=stats)
