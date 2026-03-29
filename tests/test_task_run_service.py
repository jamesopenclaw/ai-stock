"""
任务运行记录服务测试
"""
from datetime import datetime

from app.models.task_run import TaskRun
from app.services.task_run_service import _serialize_task_run


def test_serialize_task_run_includes_result_summary():
    row = TaskRun(
        id="task-1",
        mode="daily",
        trade_date="2026-03-28",
        trigger_source="manual",
        status="success",
        attempt_count=1,
        max_attempts=2,
        duration_ms=1200,
        result_json='{"pipeline":"daily","report":{"summary":{"today_action":"可适度出手","priority_action":"先看核心票"},"market_env":{"market_env_tag":"进攻","market_comment":"题材扩散"},"buy_analysis":{"available_buy_points":[{"ts_code":"300024.SZ"},{"ts_code":"300025.SZ"}]},"sell_analysis":{"sell_positions":[{"ts_code":"600001.SH"}],"reduce_positions":[]},"stock_pools":{"market_watch_count":3,"trend_recognition_count":2,"account_executable_count":1}}}',
        last_error="",
        created_at=datetime(2026, 3, 28, 10, 0, 0),
        updated_at=datetime(2026, 3, 28, 10, 2, 0),
    )

    payload = _serialize_task_run(row)

    assert payload["result_summary"] == {
        "pipeline": "daily",
        "today_action": "可适度出手",
        "priority_action": "先看核心票",
        "market_env_tag": "进攻",
        "market_comment": "题材扩散",
        "available_buy_count": 2,
        "sell_signal_count": 1,
        "candidate_pool_count": 6,
    }
