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
    SectorContinuityTag,
    SectorMainlineTag,
    SectorOutput,
    SectorTradeabilityTag,
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
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
    candidates = [
        StockOutput(
            ts_code="000001.SZ",
            stock_name="平安银行",
            sector_name="银行",
            change_pct=2.3,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
        )
    ]
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
        market_watch_candidates=candidates,
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
        include_watch_candidates=True,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["mode"] == "radar"
    assert response.data["is_realtime"] is True
    assert response.data["resolved_trade_date"] == "2026-03-24"
    assert response.data["radar_generated_at"]
    assert response.data["market_watch_candidate_count"] == 1
    assert response.data["market_watch_candidates"][0]["ts_code"] == "000001.SZ"
    assert len(compute_calls) == 1


@pytest.mark.asyncio
async def test_get_stock_pools_radar_mode_passes_strategy_style(monkeypatch):
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
        strategy_style="right",
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["mode"] == "radar"
    assert response.data["strategy_style"] == "right"
    assert len(compute_calls) == 1
    assert compute_calls[0][1]["strategy_style"] == "right"


@pytest.mark.asyncio
async def test_compute_radar_stock_pools_result_prefers_today_sources(monkeypatch):
    account_context = type(
        "AccountContext",
        (),
        {
            "holdings_list": [],
            "holdings": [],
            "account": AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.1,
                holding_count=0,
                today_new_buy_count=0,
            ),
        },
    )()
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        index_score=60,
        sentiment_score=58,
        overall_score=59,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="可观察",
    )
    sector_scan = type(
        "SectorScan",
        (),
        {
            "resolved_trade_date": "2026-03-24",
            "theme_leaders": [],
            "industry_leaders": [],
            "mainline_sectors": [],
            "sub_mainline_sectors": [],
        },
    )()
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    async def fake_build_account_context(*args, **kwargs):
        return account_context

    scan_calls = []
    candidate_calls = []

    def fake_scan(*args, **kwargs):
        scan_calls.append(kwargs.get("prefer_today"))
        return sector_scan

    def fake_get_candidate_stocks(*args, **kwargs):
        candidate_calls.append(kwargs.get("prefer_today"))
        return [], "2026-03-24"

    monkeypatch.setattr(
        stock.decision_context_service,
        "build_account_context",
        fake_build_account_context,
    )
    monkeypatch.setattr(stock.market_env_service, "get_current_env", lambda *_args, **_kwargs: market_env)
    monkeypatch.setattr(stock.sector_scan_service, "scan", fake_scan)
    monkeypatch.setattr(
        stock.decision_context_service,
        "get_candidate_stocks",
        fake_get_candidate_stocks,
    )
    monkeypatch.setattr(stock.stock_filter_service, "filter_with_context", lambda *args, **kwargs: [])
    async def fake_get_review_bias_profile_safe(*args, **kwargs):
        return None

    monkeypatch.setattr(
        stock.review_snapshot_service,
        "get_review_bias_profile_safe",
        fake_get_review_bias_profile_safe,
    )
    monkeypatch.setattr(stock.stock_filter_service, "classify_pools", lambda *args, **kwargs: pools)
    monkeypatch.setattr(stock.sell_point_service, "analyze", lambda *args, **kwargs: None)
    monkeypatch.setattr(stock.stock_filter_service, "attach_sell_analysis", lambda stock_pools, sell_analysis: stock_pools)

    result = await stock._compute_radar_stock_pools_result("2026-03-24", 50)

    assert result.resolved_trade_date == "2026-03-24"
    assert result.sector_scan_resolved_trade_date == "2026-03-24"
    assert scan_calls == [True]
    assert candidate_calls == [True]


@pytest.mark.asyncio
async def test_get_stock_pools_returns_snapshot_market_env_and_mainline(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_env=MarketEnvOutput(
            trade_date="2026-03-24",
            market_env_tag=MarketEnvTag.NEUTRAL,
            market_env_profile="中性偏强",
            breakout_allowed=True,
            risk_level=RiskLevel.MEDIUM,
            market_comment="广度强于接力",
            market_headline="可以盯主线，但先等确认再上",
            market_subheadline="广度强于接力，综合分 62.7",
            trading_tempo_label="主线确认后参与",
            dominant_factor_label="广度强于接力",
            index_score=61.8,
            sentiment_score=63.3,
            overall_score=62.7,
        ),
        theme_leaders=[
            SectorOutput(
                sector_name="草甘膦",
                sector_source_type="concept",
                sector_change_pct=6.02,
                sector_score=100.0,
                sector_strength_rank=1,
                sector_mainline_tag=SectorMainlineTag.MAINLINE,
                sector_continuity_tag=SectorContinuityTag.OBSERVABLE,
                sector_tradeability_tag=SectorTradeabilityTag.CAUTION,
                sector_rotation_tag="强化中",
                sector_summary_reason="题材强度领先",
            )
        ],
        industry_leaders=[
            SectorOutput(
                sector_name="农化制品",
                sector_source_type="industry",
                sector_change_pct=3.8,
                sector_score=92.0,
                sector_strength_rank=2,
                sector_mainline_tag=SectorMainlineTag.MAINLINE,
                sector_continuity_tag=SectorContinuityTag.OBSERVABLE,
                sector_tradeability_tag=SectorTradeabilityTag.CAUTION,
                sector_rotation_tag="稳定主线",
                sector_summary_reason="行业承接较稳",
            )
        ],
        mainline_sectors=[
            SectorOutput(
                sector_name="草甘膦",
                sector_change_pct=6.02,
                sector_score=100.0,
                sector_strength_rank=1,
                sector_mainline_tag=SectorMainlineTag.MAINLINE,
                sector_continuity_tag=SectorContinuityTag.OBSERVABLE,
                sector_tradeability_tag=SectorTradeabilityTag.CAUTION,
                sector_rotation_tag="强化中",
                sector_summary_reason="联动尚可，资金承接强，强化中",
            )
        ],
        sub_mainline_sectors=[],
        market_watch_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    async def fake_get_snapshot(trade_date, candidate_limit):
        assert trade_date == "2026-03-24"
        assert candidate_limit == 100
        return cached_pools

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-24"

    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)
    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        refresh=False,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["market_env"]["market_env_profile"] == "中性偏强"
    assert response.data["market_env"]["market_headline"] == "可以盯主线，但先等确认再上"
    assert response.data["theme_leaders"][0]["sector_name"] == "草甘膦"
    assert response.data["theme_leaders"][0]["sector_source_type"] == "concept"
    assert response.data["industry_leaders"][0]["sector_name"] == "农化制品"
    assert response.data["industry_leaders"][0]["sector_source_type"] == "industry"
    assert response.data["mainline_sectors"][0]["sector_name"] == "草甘膦"
    assert response.data["mainline_sectors"][0]["sector_rotation_tag"] == "强化中"


@pytest.mark.asyncio
async def test_get_stock_pools_non_default_style_bypasses_snapshot(monkeypatch):
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )

    compute_calls = []

    async def fake_compute(*args, **kwargs):
        compute_calls.append((args, kwargs))
        return pools

    async def should_not_read_snapshot(*args, **kwargs):
        raise AssertionError("non-default style should bypass stable snapshots")

    monkeypatch.setattr(stock, "_compute_stock_pools_result", fake_compute)
    monkeypatch.setattr(
        stock.review_snapshot_service,
        "get_stock_pools_page_snapshot",
        should_not_read_snapshot,
    )

    response = await stock.get_stock_pools(
        trade_date="2026-03-24",
        limit=50,
        refresh=False,
        strategy_style="left",
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["mode"] == "stable"
    assert response.data["strategy_style"] == "left"
    assert response.data["snapshot_status_message"] == "当前使用非默认候选风格，已按实时规则直接计算，不读写稳定快照。"
    assert len(compute_calls) == 1
    assert compute_calls[0][1]["strategy_style"] == "left"


@pytest.mark.asyncio
async def test_get_stock_pools_prefers_saved_snapshot(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-23",
        sector_scan_trade_date="2026-03-23",
        sector_scan_resolved_trade_date="2026-03-23",
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
        snapshot_version=stock.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
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
