"""
决策 API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import decision  # noqa: E402
from app.core.security import AuthenticatedAccount  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AccountInput,
    AccountPosition,
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

    bundle = type(
        "Bundle",
        (),
        {
            "context": context,
            "scored_stocks": scored,
            "stock_pools": pools,
            "review_bias_profile": {"exact": {}, "bucket": {}},
        },
    )()

    async def fake_build_candidate_analysis(*args, **kwargs):
        return bundle

    def fake_analyze(*args, **kwargs):
        return buy_result

    snapshot_calls = []
    page_snapshot_calls = []

    async def fake_save_snapshot(trade_date, stock_pools=None, buy_analysis=None, **kwargs):
        snapshot_calls.append(
            {
                "trade_date": trade_date,
                "stock_pools": stock_pools,
                "buy_analysis": buy_analysis,
            }
        )
        return 2

    async def fake_save_page_snapshot(trade_date, candidate_limit, stock_pools, **kwargs):
        page_snapshot_calls.append(
            {
                "trade_date": trade_date,
                "candidate_limit": candidate_limit,
                "stock_pools": stock_pools,
            }
        )
        return 1

    async def fake_get_page_snapshot(*args, **kwargs):
        return None

    async def fake_get_review_bias_profile(*args, **kwargs):
        return {"exact": {}, "bucket": {}}

    monkeypatch.setattr(decision.decision_flow_service, "build_candidate_analysis", fake_build_candidate_analysis)
    monkeypatch.setattr(decision.buy_point_service, "analyze", fake_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_page_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "get_review_bias_profile_safe", fake_get_review_bias_profile)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "save_stock_pools_page_snapshot_safe", fake_save_page_snapshot)
    async def fake_resolve_snapshot_lookup_trade_date(trade_date):
        return trade_date

    monkeypatch.setattr(
        decision,
        "resolve_snapshot_lookup_trade_date",
        fake_resolve_snapshot_lookup_trade_date,
    )

    response = await decision.analyze_buy_point(trade_date="2026-03-24", limit=20)

    assert response.code == 200
    assert response.data["total_count"] == 1
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["trade_date"] == "2026-03-24"
    assert snapshot_calls[0]["stock_pools"] is pools
    assert snapshot_calls[0]["buy_analysis"] is buy_result
    assert len(page_snapshot_calls) == 1
    assert page_snapshot_calls[0]["candidate_limit"] == 100


@pytest.mark.asyncio
async def test_buy_point_prefers_cached_stock_pools_snapshot(monkeypatch):
    cached_pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=decision.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[
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
        ],
        trend_recognition_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=1,
    )
    account_context = type(
        "AccountContext",
        (),
        {
            "account": AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            )
        },
    )()
    buy_result = BuyPointResponse(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        available_buy_points=[],
        observe_buy_points=[],
        not_buy_points=[],
        total_count=1,
    )

    async def should_not_build_candidate_analysis(*args, **kwargs):
        raise AssertionError("buy-point should reuse cached stock pools")

    async def fake_get_page_snapshot(*args, **kwargs):
        return cached_pools

    async def fake_build_account_context(*args, **kwargs):
        return account_context

    async def fake_get_review_bias_profile(*args, **kwargs):
        return {"exact": {}, "bucket": {}}

    saved_snapshots = []

    async def fake_save_snapshot(trade_date, stock_pools=None, buy_analysis=None, **kwargs):
        saved_snapshots.append(
            {
                "trade_date": trade_date,
                "stock_pools": stock_pools,
                "buy_analysis": buy_analysis,
            }
        )
        return 1

    def fake_analyze(*args, **kwargs):
        assert kwargs["stock_pools"] is cached_pools
        assert len(kwargs["scored_stocks"]) == 1
        return buy_result

    monkeypatch.setattr(
        decision.decision_flow_service,
        "build_candidate_analysis",
        should_not_build_candidate_analysis,
    )
    monkeypatch.setattr(decision.decision_context_service, "build_account_context", fake_build_account_context)
    monkeypatch.setattr(decision.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_page_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "get_review_bias_profile_safe", fake_get_review_bias_profile)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)
    monkeypatch.setattr(decision.buy_point_service, "analyze", fake_analyze)
    monkeypatch.setattr(decision.market_env_service, "get_current_env", lambda trade_date: object())
    async def fake_resolve_snapshot_lookup_trade_date(trade_date):
        return trade_date

    monkeypatch.setattr(
        decision,
        "resolve_snapshot_lookup_trade_date",
        fake_resolve_snapshot_lookup_trade_date,
    )

    response = await decision.analyze_buy_point(trade_date="2026-03-24", limit=20)

    assert response.code == 200
    assert response.data["total_count"] == 1
    assert saved_snapshots == [
        {
            "trade_date": "2026-03-24",
            "stock_pools": None,
            "buy_analysis": buy_result,
        }
    ]


@pytest.mark.asyncio
async def test_decision_summary_uses_lightweight_account_context(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        index_score=55,
        sentiment_score=52,
        overall_score=53,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性市",
    )
    account = AccountInput(
        total_asset=100000,
        available_cash=50000,
        total_position_ratio=0.2,
        holding_count=1,
        today_new_buy_count=0,
    )
    holdings = [
        AccountPosition(
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=12.0,
            market_price=12.5,
            pnl_pct=4.1,
            holding_market_value=1250.0,
            buy_date="2026-03-20",
            can_sell_today=True,
        )
    ]
    account_context = type(
        "AccountContext",
        (),
        {
            "account": account,
            "holdings": holdings,
        },
    )()

    async def should_not_build_candidate_analysis(*args, **kwargs):
        raise AssertionError("summary should not build candidate analysis")

    async def fake_build_account_context(trade_date, account_id=None):
        assert trade_date == "2026-03-24"
        assert account_id is None
        return account_context

    monkeypatch.setattr(
        decision.decision_flow_service,
        "build_candidate_analysis",
        should_not_build_candidate_analysis,
    )
    monkeypatch.setattr(
        decision.decision_context_service,
        "build_account_context",
        fake_build_account_context,
    )
    monkeypatch.setattr(
        decision.market_env_service,
        "get_current_env",
        lambda trade_date: market_env,
    )

    response = await decision.get_decision_summary(trade_date="2026-03-24")

    assert response.code == 200
    assert response.data["market_env_tag"] == "中性"
    assert response.data["priority_action"] == "保持现有仓位"


@pytest.mark.asyncio
async def test_review_stats_uses_current_account_scope(monkeypatch):
    captured = {}

    async def fake_get_review_stats(limit_days=10, refresh_outcomes=False, account_id=None):
        captured["limit_days"] = limit_days
        captured["refresh_outcomes"] = refresh_outcomes
        captured["account_id"] = account_id
        return {
            "trade_dates": ["2026-03-24"],
            "snapshot_count": 1,
            "bucket_stats": [],
            "stats_mode": "buy",
            "pending_outcome_count": 0,
            "pending_1d_count": 0,
            "pending_3d_count": 0,
            "pending_5d_count": 0,
            "refreshed_outcome_count": 0,
            "refresh_in_progress": False,
        }

    monkeypatch.setattr(decision.review_snapshot_service, "get_review_stats", fake_get_review_stats)

    response = await decision.get_review_stats(
        limit_days=12,
        refresh_outcomes=True,
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    assert captured == {
        "limit_days": 12,
        "refresh_outcomes": True,
        "account_id": "acct-001",
    }
