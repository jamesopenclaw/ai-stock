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
    SellPointOutput,
    SellPointResponse,
    SellPointType,
    SellPriority,
    SellSignalTag,
    StockContinuityTag,
    StockCoreTag,
    StockInput,
    StockOutput,
    StockPoolTag,
    StockPoolsOutput,
    StockStrengthTag,
    StockTradeabilityTag,
    SectorOutput,
    SectorMainlineTag,
    SectorContinuityTag,
    SectorTradeabilityTag,
)


def test_rewrite_hold_trigger_for_current_price_when_already_above_level():
    point = SellPointOutput(
        ts_code="301123.SZ",
        stock_name="奕东电子",
        market_price=66.67,
        cost_price=52.47,
        pnl_pct=27.06,
        holding_qty=100,
        holding_days=2,
        can_sell_today=True,
        sell_signal_tag=SellSignalTag.HOLD,
        sell_point_type=SellPointType.INVALID_EXIT,
        sell_trigger_cond="原始条件",
        sell_reason="继续观察",
        sell_priority=SellPriority.LOW,
        sell_comment="",
    )

    text = decision._rewrite_hold_trigger_for_current_price(
        point,
        "只有重新站回 59.90 上方并稳住，才值得继续看。",
    )

    assert text == "当前已经站在 59.90 上方，接下来重点看能否继续稳在 59.90 上方。"


def test_resolve_sell_trigger_for_display_prefers_priority_exit():
    order_plan = type(
        "OrderPlan",
        (),
        {
            "priority_exit_condition": "能直接在 65.10-65.40 一带处理，就优先直接退出；不要把最后失效线当成第一卖点。",
            "rebound_condition": "弱反抽到 64.80-65.00 一带但站不稳，优先借反抽退出。",
            "stop_condition": "跌破 59.42 且 3-5 分钟无法收回，就按结构失效处理。",
        },
    )()

    text = decision._resolve_sell_trigger_for_display(order_plan, "原始条件")

    assert text == "能直接在 65.10-65.40 一带处理，就优先直接退出；不要把最后失效线当成第一卖点。"


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
        account_executable_pool=scored,
        holding_process_pool=[],
        total_count=1,
    )
    buy_result = BuyPointResponse(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        theme_leaders=[
            SectorOutput(
                sector_name="草甘膦",
                sector_source_type="concept",
                sector_change_pct=6.0,
                sector_score=98.0,
                sector_strength_rank=1,
                sector_mainline_tag=SectorMainlineTag.MAINLINE,
                sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
                sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
                sector_continuity_days=3,
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
                sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
                sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
                sector_continuity_days=4,
            )
        ],
        available_buy_points=[
            BuyPointOutput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                direction_match_name="草甘膦",
                direction_match_source_type="concept",
                direction_match_role="theme",
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
    assert response.data["theme_leaders"][0]["sector_name"] == "草甘膦"
    assert response.data["industry_leaders"][0]["sector_name"] == "农化制品"
    assert response.data["available_buy_points"][0]["direction_match_role"] == "theme"
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
    monkeypatch.setattr(
        decision.market_env_service,
        "get_current_env",
        lambda trade_date: type("Env", (), {"market_env_tag": MarketEnvTag.NEUTRAL})(),
    )
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
async def test_buy_point_refresh_bypasses_cached_stock_pools_snapshot(monkeypatch):
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=decision.STOCK_POOLS_SNAPSHOT_VERSION,
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
            "account": AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
            "market_env": type(
                "Env",
                (),
                {"market_env_tag": MarketEnvTag.NEUTRAL},
            )(),
            "sector_scan": None,
        },
    )()
    bundle = type(
        "Bundle",
        (),
        {
            "context": context,
            "scored_stocks": [],
            "stock_pools": pools,
            "review_bias_profile": {"exact": {}, "bucket": {}},
        },
    )()
    buy_result = BuyPointResponse(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        available_buy_points=[],
        observe_buy_points=[],
        not_buy_points=[],
        total_count=0,
    )
    build_calls = []

    async def fake_build_candidate_analysis(*args, **kwargs):
        build_calls.append(kwargs)
        return bundle

    async def fake_get_page_snapshot(*args, **kwargs):
        raise AssertionError("refresh should skip buy-point stock pools cache lookup")

    async def fake_get_review_bias_profile(*args, **kwargs):
        return {"exact": {}, "bucket": {}}

    async def fake_save_snapshot(*args, **kwargs):
        return 1

    async def fake_save_page_snapshot(*args, **kwargs):
        return 1

    async def fake_resolve_snapshot_lookup_trade_date(trade_date):
        return trade_date

    monkeypatch.setattr(decision.decision_flow_service, "build_candidate_analysis", fake_build_candidate_analysis)
    monkeypatch.setattr(decision.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_page_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "get_review_bias_profile_safe", fake_get_review_bias_profile)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "save_stock_pools_page_snapshot_safe", fake_save_page_snapshot)
    monkeypatch.setattr(decision.buy_point_service, "analyze", lambda *args, **kwargs: buy_result)
    monkeypatch.setattr(decision, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await decision.analyze_buy_point(trade_date="2026-03-24", limit=20, refresh=True)

    assert response.code == 200
    assert build_calls


@pytest.mark.asyncio
async def test_buy_point_non_default_style_bypasses_default_snapshots(monkeypatch):
    context = type(
        "Context",
        (),
        {
            "stocks": [],
            "account": AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
            "market_env": type(
                "Env",
                (),
                {
                    "market_env_tag": MarketEnvTag.NEUTRAL,
                    "market_env_profile": "偏左侧测试",
                    "market_headline": "",
                    "market_subheadline": "",
                    "trading_tempo_label": "",
                },
            )(),
            "sector_scan": None,
        },
    )()
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        resolved_trade_date="2026-03-24",
        sector_scan_trade_date="2026-03-24",
        sector_scan_resolved_trade_date="2026-03-24",
        snapshot_version=decision.STOCK_POOLS_SNAPSHOT_VERSION,
        market_watch_pool=[],
        account_executable_pool=[],
        holding_process_pool=[],
        total_count=0,
    )
    buy_result = BuyPointResponse(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        available_buy_points=[],
        observe_buy_points=[],
        not_buy_points=[],
        total_count=0,
    )
    compute_calls = []
    save_calls = []

    async def fake_compute(*args, **kwargs):
        compute_calls.append((args, kwargs))
        return {
            "context": context,
            "scored_stocks": [],
            "stock_pools": pools,
            "review_bias_profile": {"exact": {}, "bucket": {}},
        }

    async def should_not_read_snapshot(*args, **kwargs):
        raise AssertionError("non-default style should bypass default stock-pools snapshot")

    async def fake_save_snapshot(*args, **kwargs):
        save_calls.append(("analysis", args, kwargs))
        return 1

    async def fake_save_page_snapshot(*args, **kwargs):
        save_calls.append(("page", args, kwargs))
        return 1

    monkeypatch.setattr(decision, "_compute_buy_point_bundle", fake_compute)
    monkeypatch.setattr(
        decision.review_snapshot_service,
        "get_stock_pools_page_snapshot",
        should_not_read_snapshot,
    )
    monkeypatch.setattr(
        decision.review_snapshot_service,
        "save_analysis_snapshot_safe",
        fake_save_snapshot,
    )
    monkeypatch.setattr(
        decision.review_snapshot_service,
        "save_stock_pools_page_snapshot_safe",
        fake_save_page_snapshot,
    )
    monkeypatch.setattr(decision.buy_point_service, "analyze", lambda *args, **kwargs: buy_result)

    response = await decision.analyze_buy_point(
        trade_date="2026-03-24",
        limit=20,
        strategy_style="left",
    )

    assert response.code == 200
    assert response.data["strategy_style"] == "left"
    assert len(compute_calls) == 1
    assert compute_calls[0][1]["strategy_style"] == "left"
    assert save_calls == []


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
async def test_sell_point_marks_add_signal_from_buy_sop(monkeypatch):
    holdings = [
        {
            "ts_code": "002463.SZ",
            "stock_name": "沪电股份",
            "holding_qty": 200,
            "cost_price": 30.0,
            "market_price": 30.6,
            "pnl_pct": 2.0,
            "holding_market_value": 6120.0,
            "buy_date": "2026-03-20",
            "can_sell_today": True,
        },
        {
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "holding_qty": 100,
            "cost_price": 12.0,
            "market_price": 12.06,
            "pnl_pct": 0.5,
            "holding_market_value": 1206.0,
            "buy_date": "2026-03-20",
            "can_sell_today": True,
        },
    ]

    sell_result = SellPointResponse(
        trade_date="2026-03-24",
        hold_positions=[
            SellPointOutput(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                market_price=30.6,
                cost_price=30.0,
                pnl_pct=2.0,
                holding_qty=200,
                holding_days=4,
                can_sell_today=True,
                sell_signal_tag=SellSignalTag.HOLD,
                sell_point_type=SellPointType.REDUCE_POSITION,
                sell_trigger_cond="跌破支撑再处理",
                sell_reason="趋势未坏",
                sell_priority=SellPriority.LOW,
                sell_comment="继续观察",
            ),
            SellPointOutput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                market_price=12.06,
                cost_price=12.0,
                pnl_pct=0.5,
                holding_qty=100,
                holding_days=4,
                can_sell_today=True,
                sell_signal_tag=SellSignalTag.HOLD,
                sell_point_type=SellPointType.REDUCE_POSITION,
                sell_trigger_cond="跌破支撑再处理",
                sell_reason="趋势未坏",
                sell_priority=SellPriority.LOW,
                sell_comment="继续观察",
            ),
        ],
        reduce_positions=[],
        sell_positions=[],
        total_count=2,
    )

    async def fake_get_holdings_from_db(account_id, trade_date):
        assert account_id == "acct-001"
        assert trade_date == "2026-03-24"
        return holdings

    async def fake_get_snapshot(trade_date):
        return type(
            "SectorScan",
            (),
            {
                "mainline_sectors": [],
                "sub_mainline_sectors": [],
                "follow_sectors": [],
                "trash_sectors": [],
            },
        )()

    async def fake_buy_sop_analyze(ts_code, trade_date, account_id=None):
        assert trade_date == "2026-03-24"
        assert account_id == "acct-001"
        if ts_code == "002463.SZ":
            return type(
                "BuySop",
                (),
                {
                    "account_context": type("Ctx", (), {"current_use": "加仓"})(),
                    "add_position_decision": type("Add", (), {"decision": "可加", "reason": "回踩确认已较明确，底仓也有利润垫。"})(),
                    "basic_info": type("Basic", (), {"buy_signal_tag": "可买"})(),
                    "position_advice": type("Pos", (), {"suggestion": "轻仓试错", "reason": "当前是加仓语境，只能等更强确认后用试错仓处理。"})(),
                    "execution": type("Exec", (), {"action": "买", "reason": "日线通过，分时也出现了相对明确的转强/承接信号。"})(),
                },
            )()
        return type(
            "BuySop",
            (),
            {
                "account_context": type("Ctx", (), {"current_use": "加仓"})(),
                "add_position_decision": type("Add", (), {"decision": "仅可小加", "reason": "结构还不错，但只适合小步推进。"})(),
                "basic_info": type("Basic", (), {"buy_signal_tag": "观察"})(),
                "position_advice": type("Pos", (), {"suggestion": "轻仓试错", "reason": "分时确认还没到位。"})(),
                "execution": type("Exec", (), {"action": "等", "reason": "日线可以继续看，但分时确认还没到位，先按计划等触发。"})(),
            },
        )()

    async def fake_resolve_snapshot_lookup_trade_date(trade_date):
        return trade_date

    saved_snapshots = []

    async def fake_save_snapshot(trade_date, add_position_analysis=None, **kwargs):
        saved_snapshots.append(
            {
                "trade_date": trade_date,
                "add_position_analysis": add_position_analysis,
                "kwargs": kwargs,
            }
        )
        return len(add_position_analysis or [])

    monkeypatch.setattr(decision.decision_context_service, "get_holdings_from_db", fake_get_holdings_from_db)
    monkeypatch.setattr(
        decision.market_env_service,
        "get_current_env",
        lambda trade_date: type("Env", (), {"market_env_tag": MarketEnvTag.NEUTRAL})(),
    )
    monkeypatch.setattr(decision.sector_scan_snapshot_service, "get_snapshot", fake_get_snapshot)
    monkeypatch.setattr(decision.sell_point_service, "analyze", lambda *args, **kwargs: sell_result)
    monkeypatch.setattr(decision.buy_point_sop_service, "analyze", fake_buy_sop_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)
    monkeypatch.setattr(decision, "resolve_snapshot_lookup_trade_date", fake_resolve_snapshot_lookup_trade_date)

    response = await decision.analyze_sell_point(
        trade_date="2026-03-24",
        include_llm=False,
        current_account=AuthenticatedAccount(
            id="acct-001",
            account_code="ACC001",
            account_name="测试账户",
            owner_user_id="user-001",
            status="active",
        ),
    )

    assert response.code == 200
    hold_positions = response.data["hold_positions"]
    assert hold_positions[0]["add_signal_tag"] == "建议加仓"
    assert hold_positions[1]["add_signal_tag"] == "仅可小加"
    assert saved_snapshots == [
        {
            "trade_date": "2026-03-24",
            "add_position_analysis": [
                {
                    "ts_code": "002463.SZ",
                    "stock_name": "沪电股份",
                    "candidate_source_tag": "",
                    "candidate_bucket_tag": "",
                    "buy_signal_tag": "可买",
                    "buy_point_type": "",
                    "stock_score": 0,
                    "base_price": 30.6,
                    "trade_mode": "加仓",
                    "add_position_decision": "可加",
                    "add_position_score_total": 0,
                    "add_position_scene": "",
                },
                {
                    "ts_code": "000001.SZ",
                    "stock_name": "平安银行",
                    "candidate_source_tag": "",
                    "candidate_bucket_tag": "",
                    "buy_signal_tag": "观察",
                    "buy_point_type": "",
                    "stock_score": 0,
                    "base_price": 12.06,
                    "trade_mode": "加仓",
                    "add_position_decision": "仅可小加",
                    "add_position_score_total": 0,
                    "add_position_scene": "",
                },
            ],
            "kwargs": {
                "account_id": "acct-001",
            },
        }
    ]


@pytest.mark.asyncio
async def test_review_stats_uses_current_account_scope(monkeypatch):
    captured = {}
    ensure_called = {"value": False}

    async def fake_get_review_stats(limit_days=10, refresh_outcomes=False, account_id=None):
        captured["limit_days"] = limit_days
        captured["refresh_outcomes"] = refresh_outcomes
        captured["account_id"] = account_id
        return {
            "trade_dates": ["2026-03-24"],
            "snapshot_count": 1,
            "bucket_stats": [],
            "stats_mode": "buy",
            "pending_outcome_count": 3,
            "pending_1d_count": 0,
            "pending_3d_count": 0,
            "pending_5d_count": 0,
            "refreshed_outcome_count": 0,
            "refresh_in_progress": False,
        }

    monkeypatch.setattr(decision.review_snapshot_service, "get_review_stats", fake_get_review_stats)
    monkeypatch.setattr(
        decision.review_snapshot_service,
        "ensure_background_refresh",
        lambda limit_days=20: ensure_called.__setitem__("value", True),
    )

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
    assert ensure_called["value"] is False
