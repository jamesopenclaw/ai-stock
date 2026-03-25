"""
单股买点 SOP API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BuyPointSopAccountContext,
    BuyPointSopBasicInfo,
    BuyPointSopDailyJudgement,
    BuyPointSopExecution,
    BuyPointSopIntradayJudgement,
    BuyPointSopOrderPlan,
    BuyPointSopPositionAdvice,
    BuyPointSopResponse,
)


@pytest.mark.asyncio
async def test_get_stock_buy_analysis_returns_response(monkeypatch):
    sample = BuyPointSopResponse(
        trade_date="2026-03-23",
        resolved_trade_date="2026-03-23",
        stock_found_in_candidates=True,
        basic_info=BuyPointSopBasicInfo(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            market_env_tag="进攻",
            buy_signal_tag="可买",
            buy_point_type="回踩承接",
        ),
        account_context=BuyPointSopAccountContext(
            position_status="轻仓（仓位 20%）",
            same_direction_exposure="暂无明显同方向重复暴露。",
            current_use="新开仓",
            market_suitability="市场允许主动试错，但仍要先等分时确认。",
            account_conclusion="轻仓新开仓，可试错",
        ),
        daily_judgement=BuyPointSopDailyJudgement(
            current_stage="启动",
            buy_signal="回踩承接，可买",
            buy_point_level="A",
            reason="结构偏强",
            risk_items=["分时确认仍需盯盘"],
            reference_levels=["MA5：27.50"],
        ),
        intraday_judgement=BuyPointSopIntradayJudgement(
            price_vs_avg_line="均价线关系 [需确认]",
            intraday_structure="回踩承接",
            volume_quality="温和放量（量比 1.8）",
            key_level_status="仍在支撑位 27.50 上方。",
            conclusion="买",
            note="盘中确认已到位。",
        ),
        order_plan=BuyPointSopOrderPlan(
            low_absorb_price="27.40-27.70",
            breakout_price="28.60",
            retrace_confirm_price="28.51-28.69",
            give_up_price="29.17",
            trigger_condition="回踩企稳再看",
            invalid_condition="跌破 MA10 放弃",
            above_no_chase="29.17",
            below_no_buy="27.20",
        ),
        position_advice=BuyPointSopPositionAdvice(
            suggestion="中仓参与",
            reason="环境和结构匹配",
            invalidation_level="27.20",
            invalidation_action="跌破失效位后直接放弃。",
        ),
        execution=BuyPointSopExecution(
            action="买",
            reason="日线和分时都过关。",
        ),
    )

    async def fake_analyze(*args, **kwargs):
        return sample

    monkeypatch.setattr(stock.buy_point_sop_service, "analyze", fake_analyze)

    response = await stock.get_stock_buy_analysis(
        "002463.SZ",
        trade_date="2026-03-23",
    )

    assert response.code == 200
    assert response.data["basic_info"]["stock_name"] == "沪电股份"
    assert response.data["daily_judgement"]["buy_point_level"] == "A"
    assert response.data["execution"]["action"] == "买"

