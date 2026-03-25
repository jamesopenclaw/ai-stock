"""
单股卖点 SOP API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.models.schemas import (  # noqa: E402
    SellPointSopAccountContext,
    SellPointSopBasicInfo,
    SellPointSopDailyJudgement,
    SellPointSopExecution,
    SellPointSopIntradayJudgement,
    SellPointSopOrderPlan,
    SellPointSopResponse,
)


@pytest.mark.asyncio
async def test_get_stock_sell_analysis_returns_response(monkeypatch):
    sample = SellPointSopResponse(
        trade_date="2026-03-23",
        resolved_trade_date="2026-03-23",
        stock_found_in_holdings=True,
        basic_info=SellPointSopBasicInfo(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            market_env_tag="中性",
            sell_signal_tag="减仓",
            sell_point_type="减仓",
        ),
        account_context=SellPointSopAccountContext(
            position_status="中仓",
            pnl_status="厚利",
            role="进攻仓",
            priority="中，需要尽快处理",
            context_summary="中仓厚利进攻仓",
        ),
        daily_judgement=SellPointSopDailyJudgement(
            current_stage="中继",
            sell_signal="跌破5日线",
            sell_point_level="C",
            reason="结构开始松动",
        ),
        intraday_judgement=SellPointSopIntradayJudgement(
            price_vs_avg_line="均价线关系 [需确认]",
            intraday_structure="冲高回落",
            volume_quality="放量回落 = 派发（量比 1.8）",
            conclusion="减",
            note="先收风险。",
        ),
        order_plan=SellPointSopOrderPlan(
            proactive_take_profit_price="33.50-33.70",
            rebound_sell_price="33.00-33.20",
            break_stop_price="32.40",
            observe_level="32.90",
            take_profit_condition="冲高先兑现",
            rebound_condition="反抽无力先减",
            stop_condition="跌破止损位处理",
            hold_condition="守住观察位继续看",
        ),
        execution=SellPointSopExecution(
            action="减",
            partial_plan="分批处理",
            key_level="33.50-33.70",
            reason="先保护利润。",
        ),
    )

    async def fake_analyze(*args, **kwargs):
        return sample

    monkeypatch.setattr(stock.sell_point_sop_service, "analyze", fake_analyze)

    response = await stock.get_stock_sell_analysis(
        "002463.SZ",
        trade_date="2026-03-23",
    )

    assert response.code == 200
    assert response.data["basic_info"]["stock_name"] == "沪电股份"
    assert response.data["daily_judgement"]["sell_point_level"] == "C"
    assert response.data["execution"]["action"] == "减"

