"""
决策 API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import decision  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AccountInput,
    BuyPointOutput,
    BuyPointResponse,
    BuyPointType,
    BuySignalTag,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    StockContinuityTag,
    StockCoreTag,
    StockInput,
    StockOutput,
    StockPoolTag,
    StockPoolsOutput,
    StockStrengthTag,
    StockTradeabilityTag,
)


@pytest.mark.asyncio
async def test_buy_point_page_saves_review_snapshot(monkeypatch):
    context = type(
        "Context",
        (),
        {
            "stocks": [
                StockInput(
                    ts_code="000001.SZ",
                    stock_name="平安银行",
                    sector_name="银行",
                    close=12.5,
                    change_pct=2.3,
                    turnover_rate=1.8,
                    amount=123456,
                    high=12.6,
                    low=12.1,
                    open=12.2,
                    pre_close=12.22,
                )
            ],
            "holdings_list": [],
            "holdings": [],
            "account": AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
            "market_env": MarketEnvOutput(
                trade_date="2026-03-24",
                market_env_tag=MarketEnvTag.NEUTRAL,
                index_score=55,
                sentiment_score=52,
                overall_score=53,
                breakout_allowed=True,
                risk_level=RiskLevel.MEDIUM,
                market_comment="中性市",
            ),
            "sector_scan": None,
        },
    )()

    scored = [
        StockOutput(
            ts_code="000001.SZ",
            stock_name="平安银行",
            sector_name="银行",
            change_pct=2.3,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
        )
    ]
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-23",
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=scored,
        holding_process_pool=[],
        total_count=1,
    )
    buy_result = BuyPointResponse(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        available_buy_points=[
            BuyPointOutput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                buy_signal_tag=BuySignalTag.CAN_BUY,
                buy_point_type=BuyPointType.RETRACE_SUPPORT,
                buy_trigger_cond="回踩确认",
                buy_confirm_cond="量价配合",
                buy_invalid_cond="跌破失效",
                buy_risk_level=RiskLevel.MEDIUM,
                buy_account_fit="适合",
                buy_comment="测试",
            )
        ],
        observe_buy_points=[],
        not_buy_points=[],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    def fake_filter_with_context(*args, **kwargs):
        return scored

    def fake_classify_pools(*args, **kwargs):
        return pools

    def fake_analyze(*args, **kwargs):
        return buy_result

    snapshot_calls = []

    async def fake_save_snapshot(trade_date, stock_pools=None, buy_analysis=None):
        snapshot_calls.append(
            {
                "trade_date": trade_date,
                "stock_pools": stock_pools,
                "buy_analysis": buy_analysis,
            }
        )
        return 2

    monkeypatch.setattr(decision.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(decision.stock_filter_service, "filter_with_context", fake_filter_with_context)
    monkeypatch.setattr(decision.stock_filter_service, "classify_pools", fake_classify_pools)
    monkeypatch.setattr(decision.buy_point_service, "analyze", fake_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot", fake_save_snapshot)

    response = await decision.analyze_buy_point(trade_date="2026-03-24", limit=20)

    assert response.code == 200
    assert response.data["total_count"] == 1
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["trade_date"] == "2026-03-24"
    assert snapshot_calls[0]["stock_pools"] is pools
    assert snapshot_calls[0]["buy_analysis"] is buy_result
