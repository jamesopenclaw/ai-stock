"""
三池 API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AccountInput,
    LlmCallStatus,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    StockContinuityTag,
    StockCoreTag,
    StockInput,
    StockOutput,
    StockPoolsOutput,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
)


@pytest.mark.asyncio
async def test_get_stock_pools_skips_live_llm_when_not_forced(monkeypatch):
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
            "resolved_stock_trade_date": "2026-03-23",
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

    async def fake_build_context(*args, **kwargs):
        return context

    def fake_filter_with_context(*args, **kwargs):
        return scored

    def fake_classify_pools(*args, **kwargs):
        return pools

    def fake_sell_analyze(*args, **kwargs):
        return None

    def fake_attach_sell_analysis(stock_pools, sell_analysis):
        return stock_pools

    snapshot_calls = []

    async def fake_save_snapshot(trade_date, stock_pools=None, buy_analysis=None):
        snapshot_calls.append(
            {
                "trade_date": trade_date,
                "stock_pools": stock_pools,
                "buy_analysis": buy_analysis,
            }
        )
        return 1

    async def fake_summarize(*args, **kwargs):
        assert kwargs["force_refresh"] is False
        assert kwargs["allow_live_request"] is False
        return None, LlmCallStatus(
            enabled=True,
            success=False,
            status="cache_miss",
            message="LLM 摘要未命中缓存，已跳过实时生成以保证页面响应",
        )

    monkeypatch.setattr(stock.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(stock.stock_filter_service, "filter_with_context", fake_filter_with_context)
    monkeypatch.setattr(stock.stock_filter_service, "classify_pools", fake_classify_pools)
    monkeypatch.setattr(stock.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(stock.stock_filter_service, "attach_sell_analysis", fake_attach_sell_analysis)
    monkeypatch.setattr(stock.review_snapshot_service, "save_analysis_snapshot", fake_save_snapshot)
    monkeypatch.setattr(stock.llm_explainer_service, "summarize_stock_pools_with_status", fake_summarize)

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["resolved_trade_date"] == "2026-03-23"
    assert response.data["llm_summary"] is None
    assert response.data["llm_status"]["status"] == "cache_miss"
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["trade_date"] == "2026-03-24"
    assert snapshot_calls[0]["stock_pools"] is pools
    assert snapshot_calls[0]["buy_analysis"] is None
