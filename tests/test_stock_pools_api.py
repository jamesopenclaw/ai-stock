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
async def test_get_stock_pools_disables_llm_summary(monkeypatch):
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
            "sector_scan_trade_date": "2026-03-23",
            "sector_scan_resolved_trade_date": "2026-03-23",
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
        sector_scan_trade_date="2026-03-23",
        sector_scan_resolved_trade_date="2026-03-23",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=scored,
        holding_process_pool=[],
        total_count=1,
    )

    build_context_calls = []

    async def fake_build_context(*args, **kwargs):
        build_context_calls.append(True)
        return context

    async def fake_get_snapshot(*args, **kwargs):
        return None

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-23"

    def fake_filter_with_context(*args, **kwargs):
        return scored

    def fake_classify_pools(*args, **kwargs):
        return pools

    def fake_sell_analyze(*args, **kwargs):
        return None

    def fake_attach_sell_analysis(stock_pools, sell_analysis):
        return stock_pools

    snapshot_calls = []

    async def fake_save_snapshot(trade_date, stock_pools=None, buy_analysis=None, **kwargs):
        snapshot_calls.append(
            {
                "trade_date": trade_date,
                "stock_pools": stock_pools,
                "buy_analysis": buy_analysis,
            }
        )
        return 1

    full_snapshot_calls = []

    async def fake_save_page_snapshot(trade_date, candidate_limit, stock_pools, **kwargs):
        full_snapshot_calls.append(
            {
                "trade_date": trade_date,
                "candidate_limit": candidate_limit,
                "stock_pools": stock_pools,
            }
        )
        return 1

    monkeypatch.setattr(stock.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(stock.stock_filter_service, "filter_with_context", fake_filter_with_context)
    monkeypatch.setattr(stock.stock_filter_service, "classify_pools", fake_classify_pools)
    monkeypatch.setattr(stock.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(stock.stock_filter_service, "attach_sell_analysis", fake_attach_sell_analysis)
    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)
    monkeypatch.setattr(stock.review_snapshot_service, "save_analysis_snapshot", fake_save_snapshot)
    monkeypatch.setattr(stock.review_snapshot_service, "save_stock_pools_page_snapshot", fake_save_page_snapshot)
    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        refresh=False,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["resolved_trade_date"] == "2026-03-23"
    assert response.data["sector_scan_trade_date"] == "2026-03-23"
    assert response.data["sector_scan_resolved_trade_date"] == "2026-03-23"
    assert response.data["llm_summary"] is None
    assert response.data["llm_status"]["status"] == "disabled"
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["trade_date"] == "2026-03-24"
    assert snapshot_calls[0]["stock_pools"] is pools
    assert snapshot_calls[0]["buy_analysis"] is None
    assert len(full_snapshot_calls) == 1
    assert full_snapshot_calls[0]["trade_date"] == "2026-03-24"
    assert full_snapshot_calls[0]["candidate_limit"] == 100
    assert full_snapshot_calls[0]["stock_pools"] is pools


@pytest.mark.asyncio
async def test_get_stock_pools_radar_mode_returns_realtime_payload(monkeypatch):
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    compute_calls = []

    async def fake_compute(*args, **kwargs):
        compute_calls.append((args, kwargs))
        return pools

    monkeypatch.setattr(stock, "_compute_radar_stock_pools_result", fake_compute)

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        refresh=False,
        mode="radar",
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["mode"] == "radar"
    assert response.data["is_realtime"] is True
    assert response.data["resolved_trade_date"] == "2026-03-24"
    assert response.data["radar_generated_at"]
    assert len(compute_calls) == 1


@pytest.mark.asyncio
async def test_get_stock_pools_prefers_saved_snapshot(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-23",
        sector_scan_trade_date="2026-03-23",
        sector_scan_resolved_trade_date="2026-03-23",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    async def fake_get_snapshot(trade_date, candidate_limit):
        assert trade_date == "2026-03-24"
        assert candidate_limit == 100
        return cached_pools

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-23"

    async def should_not_build_context(*args, **kwargs):
        raise AssertionError("cache hit should skip recompute")

    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)
    monkeypatch.setattr(stock.decision_context_service, "build_context", should_not_build_context)
    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        refresh=False,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["trade_date"] == "2026-03-24"
    assert response.data["resolved_trade_date"] == "2026-03-23"
    assert response.data["sector_scan_trade_date"] == "2026-03-23"
    assert response.data["sector_scan_resolved_trade_date"] == "2026-03-23"
    assert response.data["total_count"] == 0
    assert response.data["llm_status"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_get_stock_pools_invalidates_cache_when_sector_scan_trade_date_changes(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-26",
        resolved_trade_date="2026-03-25",
        sector_scan_trade_date="2026-03-25",
        sector_scan_resolved_trade_date="2026-03-25",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    context = type(
        "Context",
        (),
        {
            "stocks": [],
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
                trade_date="2026-03-26",
                market_env_tag=MarketEnvTag.NEUTRAL,
                index_score=55,
                sentiment_score=52,
                overall_score=53,
                breakout_allowed=True,
                risk_level=RiskLevel.MEDIUM,
                market_comment="中性市",
            ),
            "sector_scan": type(
                "SectorScan",
                (),
                {
                    "trade_date": "2026-03-26",
                    "resolved_trade_date": "2026-03-26",
                },
            )(),
            "sector_scan_trade_date": "2026-03-26",
            "sector_scan_resolved_trade_date": "2026-03-26",
            "resolved_stock_trade_date": "2026-03-26",
        },
    )()

    recomputed = StockPoolsOutput(
        trade_date="2026-03-26",
        resolved_trade_date="2026-03-26",
        sector_scan_trade_date="2026-03-26",
        sector_scan_resolved_trade_date="2026-03-26",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    async def fake_get_snapshot(*args, **kwargs):
        return cached_pools

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-26"

    async def fake_build_context(*args, **kwargs):
        return context

    def fake_filter_with_context(*args, **kwargs):
        return []

    def fake_classify_pools(*args, **kwargs):
        return recomputed

    def fake_sell_analyze(*args, **kwargs):
        return None

    def fake_attach_sell_analysis(stock_pools, sell_analysis):
        return stock_pools

    async def fake_save_snapshot(*args, **kwargs):
        return 1

    async def fake_save_page_snapshot(*args, **kwargs):
        return 1

    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)
    monkeypatch.setattr(stock.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(stock.stock_filter_service, "filter_with_context", fake_filter_with_context)
    monkeypatch.setattr(stock.stock_filter_service, "classify_pools", fake_classify_pools)
    monkeypatch.setattr(stock.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(stock.stock_filter_service, "attach_sell_analysis", fake_attach_sell_analysis)
    monkeypatch.setattr(stock.review_snapshot_service, "save_analysis_snapshot", fake_save_snapshot)
    monkeypatch.setattr(stock.review_snapshot_service, "save_stock_pools_page_snapshot", fake_save_page_snapshot)
    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await stock.get_stock_pools(
        trade_date="2026-03-26",
        limit=50,
        refresh=False,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["trade_date"] == "2026-03-26"
    assert response.data["sector_scan_trade_date"] == "2026-03-26"


@pytest.mark.asyncio
async def test_get_stock_pools_invalidates_legacy_snapshot_without_version(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-26",
        resolved_trade_date="2026-03-25",
        sector_scan_trade_date="2026-03-25",
        sector_scan_resolved_trade_date="2026-03-25",
        snapshot_version=None,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    context = type(
        "Context",
        (),
        {
            "stocks": [],
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
                trade_date="2026-03-26",
                market_env_tag=MarketEnvTag.NEUTRAL,
                index_score=55,
                sentiment_score=52,
                overall_score=53,
                breakout_allowed=True,
                risk_level=RiskLevel.MEDIUM,
                market_comment="中性市",
            ),
            "sector_scan": type(
                "SectorScan",
                (),
                {
                    "trade_date": "2026-03-25",
                    "resolved_trade_date": "2026-03-25",
                },
            )(),
            "sector_scan_trade_date": "2026-03-25",
            "sector_scan_resolved_trade_date": "2026-03-25",
            "resolved_stock_trade_date": "2026-03-25",
        },
    )()

    recomputed = StockPoolsOutput(
        trade_date="2026-03-26",
        resolved_trade_date="2026-03-25",
        sector_scan_trade_date="2026-03-25",
        sector_scan_resolved_trade_date="2026-03-25",
        snapshot_version=3,
        market_watch_pool=[],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    async def fake_get_snapshot(*args, **kwargs):
        return cached_pools

    build_context_calls = []

    async def fake_build_context(*args, **kwargs):
        build_context_calls.append(True)
        return context

    def fake_filter_with_context(*args, **kwargs):
        return []

    def fake_classify_pools(*args, **kwargs):
        return recomputed

    def fake_sell_analyze(*args, **kwargs):
        return None

    def fake_attach_sell_analysis(stock_pools, sell_analysis):
        return stock_pools

    async def fake_save_snapshot(*args, **kwargs):
        return 1

    async def fake_save_page_snapshot(*args, **kwargs):
        return 1

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-25"

    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)
    monkeypatch.setattr(stock.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(stock.stock_filter_service, "filter_with_context", fake_filter_with_context)
    monkeypatch.setattr(stock.stock_filter_service, "classify_pools", fake_classify_pools)
    monkeypatch.setattr(stock.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(stock.stock_filter_service, "attach_sell_analysis", fake_attach_sell_analysis)
    monkeypatch.setattr(stock.review_snapshot_service, "save_analysis_snapshot", fake_save_snapshot)
    monkeypatch.setattr(stock.review_snapshot_service, "save_stock_pools_page_snapshot", fake_save_page_snapshot)
    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await stock.get_stock_pools(
        trade_date="2026-03-26",
        limit=50,
        refresh=False,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert build_context_calls == [True]
