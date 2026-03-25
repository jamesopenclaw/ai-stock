"""
系统相关 API
"""
from typing import Optional

from fastapi import APIRouter, Query

from app.models.schemas import ApiResponse
from app.services.llm_call_log_service import llm_call_log_service

router = APIRouter()


@router.get("/llm/logs", response_model=ApiResponse)
async def get_llm_call_logs(
    limit: int = Query(100, ge=1, le=500, description="返回数量"),
    scene: Optional[str] = Query(None, description="调用场景"),
    status: Optional[str] = Query(None, description="调用状态"),
    success: Optional[bool] = Query(None, description="是否成功"),
) -> ApiResponse:
    logs = await llm_call_log_service.list_logs(
        limit=limit,
        scene=scene,
        status=status,
        success=success,
    )
    return ApiResponse(
        data={
            "logs": logs,
            "total": len(logs),
        }
    )
