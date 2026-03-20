"""
定时任务 API
"""
from fastapi import APIRouter, BackgroundTasks
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from app.tasks.scheduler import scheduler

router = APIRouter()


class TaskRequest(BaseModel):
    """任务请求"""
    trade_date: Optional[str] = None
    mode: str = "daily"  # daily, sync, analyze, notify


class TaskResponse(BaseModel):
    """任务响应"""
    status: str
    message: str
    task_id: Optional[str] = None


@router.post("/trigger", response_model=TaskResponse)
async def trigger_task(
    request: TaskRequest,
    background_tasks: BackgroundTasks
):
    """
    手动触发定时任务

    - mode=daily: 完整流程（同步+分析+推送）
    - mode=sync: 仅同步数据
    - mode=analyze: 仅执行分析
    - mode=notify: 仅推送通知
    """
    trade_date = request.trade_date or datetime.now().strftime("%Y-%m-%d")

    task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def run_task():
        import asyncio
        from app.tasks.main import run_daily_task

        if request.mode == "daily":
            asyncio.run(run_daily_task(trade_date))
        elif request.mode == "sync":
            asyncio.run(scheduler.sync_data(trade_date))
        elif request.mode == "analyze":
            asyncio.run(scheduler.run_analysis(trade_date))
        elif request.mode == "notify":
            # 需要先有分析数据
            report_data = asyncio.run(scheduler.run_analysis(trade_date))
            asyncio.run(scheduler.notify_report(trade_date, report_data))

    # 后台执行任务
    background_tasks.add_task(run_task)

    return TaskResponse(
        status="started",
        message=f"任务已启动，模式: {request.mode}, 日期: {trade_date}",
        task_id=task_id
    )


@router.get("/status")
async def get_task_status():
    """获取任务状态（预留）"""
    return {
        "status": "ready",
        "message": "定时任务服务就绪"
    }
