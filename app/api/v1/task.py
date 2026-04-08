"""
定时任务 API
"""
import asyncio
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger

from app.core.security import AuthenticatedUser, require_admin
from app.tasks.scheduler import scheduler

router = APIRouter()


class TaskRequest(BaseModel):
    """任务请求"""
    trade_date: Optional[str] = None
    mode: str = "daily"  # daily, sync, analyze, notify, ths_sync
    force: bool = False


class TaskResponse(BaseModel):
    """任务响应"""
    status: str
    message: str
    task_id: Optional[str] = None


@router.post("/trigger", response_model=TaskResponse)
async def trigger_task(
    request: TaskRequest,
    background_tasks: BackgroundTasks = None,
    current_user: AuthenticatedUser = Depends(require_admin),
):
    """
    手动触发定时任务

    - mode=daily: 完整流程（同步+分析+推送）
    - mode=sync: 仅同步数据
    - mode=analyze: 仅执行分析
    - mode=notify: 仅推送通知
    - mode=ths_sync: 收盘后同步同花顺概念成分到本地库
    """
    trade_date = request.trade_date or datetime.now().strftime("%Y-%m-%d")

    task_result = await scheduler.enqueue_task(
        request.mode,
        trade_date,
        trigger_source="manual",
        force=bool(request.force),
    )

    if task_result["created"]:
        task_id = task_result["task_id"]

        async def run_task():
            try:
                await scheduler.execute_task_run(task_id)
            except Exception as exc:
                logger.exception(f"后台任务执行失败: task_id={task_id} error={exc}")

        asyncio.create_task(run_task())
        status = "started"
        message = f"任务已启动，模式: {request.mode}, 日期: {trade_date}"
    else:
        status = "duplicate"
        if task_result["reason"] == "already_finished":
            message = f"相同任务已执行成功，直接复用结果，模式: {request.mode}, 日期: {trade_date}"
        else:
            message = f"相同任务正在执行，未重复启动，模式: {request.mode}, 日期: {trade_date}"

    return TaskResponse(
        status=status,
        message=message,
        task_id=task_result["task_id"]
    )


@router.get("/status")
async def get_task_status(
    task_id: Optional[str] = None,
    limit: int = 20,
    current_user: AuthenticatedUser = Depends(require_admin),
):
    """获取任务状态。"""
    return await scheduler.get_task_status(task_id=task_id, limit=limit)
