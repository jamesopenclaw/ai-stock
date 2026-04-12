"""
决策上下文测试
"""
from dataclasses import replace
import os
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    AccountInput,
    AccountPosition,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    StockInput,
)
from app.services.decision_context import (  # noqa: E402
    AccountDecisionContext,
    DecisionContextService,
    SharedDecisionContext,
)
from app.services.strategy_config import DEFAULT_STOCK_FILTER_STRATEGY  # noqa: E402


def test_enrich_holding_time_fields_uses_trade_date():
    """持有天数与可卖状态应按请求 trade_date 计算。"""
    service = DecisionContextService()
    holding = {
        "ts_code": "002463.SZ",
        "buy_date": "2026-03-18",
        "can_sell_today": False,
    }

    enriched = service._enrich_holding_time_fields(holding, "2026-03-23")

    assert enriched["holding_days"] == 5
    assert enriched["can_sell_today"] is True


def test_enrich_holding_time_fields_same_day_is_t1_locked():
    """买入当天持有天数为 0，且仍不可卖。"""
    service = DecisionContextService()
    holding = {
        "ts_code": "002463.SZ",
        "buy_date": "2026-03-23",
    }

    enriched = service._enrich_holding_time_fields(holding, "2026-03-23")

    assert enriched["holding_days"] == 0
    assert enriched["can_sell_today"] is False


@pytest.mark.asyncio
async def test_resolve_selection_trade_date_uses_sector_snapshot_lookup(monkeypatch):
    service = DecisionContextService()

    async def fake_resolve_snapshot_lookup_trade_date(_trade_date):
        return "2026-03-20"

    monkeypatch.setattr(
        "app.services.decision_context.resolve_snapshot_lookup_trade_date",
        fake_resolve_snapshot_lookup_trade_date,
    )

    assert await service._resolve_selection_trade_date("2026-03-24") == "2026-03-20"


@pytest.mark.asyncio
async def test_build_context_passes_market_env_to_sector_scan(monkeypatch):
    """构建上下文时，应先取市场环境并传给板块扫描。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=70,
        sentiment_score=82,
        overall_score=77,
    )
    captured = {}

    async def fake_holdings(_account_id=None, _trade_date=None):
        return []

    async def fake_account(_holdings, _account_id=None, _trade_date=None):
        return AccountInput(
            total_asset=100000,
            available_cash=100000,
            total_position_ratio=0.0,
            holding_count=0,
            today_new_buy_count=0,
        )

    monkeypatch.setattr(service, "get_holdings_from_db", fake_holdings)
    monkeypatch.setattr(
        service,
        "build_account_input_from_holdings",
        fake_account,
    )
    market_env_calls = []

    def fake_get_current_env(_trade_date):
        market_env_calls.append(_trade_date)
        return market_env

    monkeypatch.setattr(
        "app.services.decision_context.market_env_service.get_current_env",
        fake_get_current_env,
    )
    async def fake_get_sector_scan_snapshot(_trade_date):
        return None

    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_snapshot_service.get_snapshot",
        fake_get_sector_scan_snapshot,
    )
    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_service.scan",
        lambda trade_date, limit_output=False, market_env=None: (
            captured.update(
                {
                    "trade_date": trade_date,
                    "limit_output": limit_output,
                    "market_env": market_env,
                }
            )
            or {"ok": True}
        ),
    )
    monkeypatch.setattr(
        service,
        "get_candidate_stocks",
        lambda *_args, **_kwargs: ([], "2026-03-20"),
    )

    async def fake_resolve_selection_trade_date(_trade_date):
        return "2026-03-20"

    monkeypatch.setattr(
        service,
        "_resolve_selection_trade_date",
        fake_resolve_selection_trade_date,
    )

    context = await service.build_context("2026-03-23")

    assert captured["trade_date"] == "2026-03-20"
    assert captured["limit_output"] is False
    assert captured["market_env"] == market_env
    assert market_env_calls == ["2026-03-20", "2026-03-23"]
    assert context.market_env == market_env
    assert context.realtime_market_env == market_env
    assert context.resolved_stock_trade_date == "2026-03-20"
    assert context.sector_scan_trade_date is None
    assert context.sector_scan_resolved_trade_date is None
    assert context.shared_context.selection_trade_date == "2026-03-20"


@pytest.mark.asyncio
async def test_build_shared_context_does_not_load_account_state(monkeypatch):
    """共享上下文不应依赖持仓或账户信息。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=60,
        sentiment_score=58,
        overall_score=59,
    )

    async def should_not_load_holdings(*args, **kwargs):
        raise AssertionError("shared context should not load holdings")

    async def should_not_build_account(*args, **kwargs):
        raise AssertionError("shared context should not build account input")

    monkeypatch.setattr(service, "get_holdings_from_db", should_not_load_holdings)
    monkeypatch.setattr(service, "build_account_input_from_holdings", should_not_build_account)
    async def fake_resolve_selection_trade_date(_trade_date):
        return "2026-03-24"

    monkeypatch.setattr(
        service,
        "_resolve_selection_trade_date",
        fake_resolve_selection_trade_date,
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_env_service.get_current_env",
        lambda _trade_date: market_env,
    )

    async def fake_get_sector_scan_snapshot(_trade_date):
        return {"snapshot": True}

    monkeypatch.setattr(
        "app.services.decision_context.sector_scan_snapshot_service.get_snapshot",
        fake_get_sector_scan_snapshot,
    )
    monkeypatch.setattr(
        service,
        "get_candidate_stocks",
        lambda *_args, **_kwargs: (
            [
                StockInput(
                    ts_code="000001.SZ",
                    stock_name="平安银行",
                    sector_name="银行",
                    close=12.5,
                    change_pct=1.2,
                    turnover_rate=1.8,
                    amount=123456,
                    high=12.7,
                    low=12.2,
                    open=12.3,
                    pre_close=12.35,
                )
            ],
            "2026-03-24",
        ),
    )

    context = await service.build_shared_context("2026-03-24")

    assert context.trade_date == "2026-03-24"
    assert context.selection_trade_date == "2026-03-24"
    assert len(context.stocks) == 1


def test_compose_context_merges_holdings_only_when_requested(monkeypatch):
    """完整上下文只在显式要求时把持仓并回候选池。"""
    service = DecisionContextService()
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=True,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=60,
        sentiment_score=58,
        overall_score=59,
    )
    shared_stock = StockInput(
        ts_code="000001.SZ",
        stock_name="平安银行",
        sector_name="银行",
        close=12.5,
        change_pct=1.2,
        turnover_rate=1.8,
        amount=123456,
        high=12.7,
        low=12.2,
        open=12.3,
        pre_close=12.35,
    )
    merged_stock = StockInput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="PCB",
        close=30.5,
        change_pct=0.5,
        turnover_rate=2.1,
        amount=234567,
        high=31.0,
        low=30.1,
        open=30.3,
        pre_close=30.35,
    )
    shared_context = SharedDecisionContext(
        trade_date="2026-03-24",
        selection_trade_date="2026-03-24",
        resolved_stock_trade_date="2026-03-24",
        sector_scan_trade_date=None,
        sector_scan_resolved_trade_date=None,
        market_env=market_env,
        realtime_market_env=market_env,
        sector_scan={"snapshot": True},
        stocks=[shared_stock],
    )
    account_context = AccountDecisionContext(
        trade_date="2026-03-24",
        account_id="account-1",
        holdings_list=[{"ts_code": "002463.SZ"}],
        holdings=[
            AccountPosition(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                holding_qty=100,
                cost_price=30.0,
                market_price=30.5,
                pnl_pct=1.67,
                holding_market_value=3050.0,
                buy_date="2026-03-20",
                can_sell_today=True,
            )
        ],
        account=AccountInput(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )

    monkeypatch.setattr(
        "app.services.decision_context.merge_holdings_into_candidate_stocks",
        lambda trade_date, stocks, holdings: [*stocks, merged_stock],
    )

    original_merge = service.compose_context(shared_context, account_context, include_holdings=False)
    merged = service.compose_context(shared_context, account_context, include_holdings=True)

    assert [stock.ts_code for stock in original_merge.stocks] == ["000001.SZ"]
    assert [stock.ts_code for stock in merged.stocks] == ["000001.SZ", "002463.SZ"]
    assert [stock.ts_code for stock in original_merge.shared_context.stocks] == ["000001.SZ"]
    assert merged.shared_context.stocks == [shared_stock]


def test_build_mainline_pullback_candidates_recalls_concept_pullback(monkeypatch):
    """主线题材里未上榜但处于舒服回踩位的票，应被补进候选。"""
    service = DecisionContextService()
    sector_scan = SimpleNamespace(
        theme_leaders=[SimpleNamespace(sector_name="机器人", sector_source_type="concept")],
        industry_leaders=[],
        mainline_sectors=[],
        sub_mainline_sectors=[],
    )
    source_df = pd.DataFrame(
        [
            {
                "ts_code": "002779.SZ",
                "stock_name": "中坚科技",
                "industry": "专用设备",
                    "close": 20.10,
                    "pct_change": 1.6,
                    "turnover_rate": 8.2,
                    "amount": 156000,
                    "volume_ratio": 1.6,
                    "high": 20.22,
                    "low": 19.70,
                    "open": 20.00,
                "pre_close": 19.78,
                "avg_price": 20.03,
                "volume": 100000,
            }
        ]
    )

    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.fetch_recent_stock_daily_df",
        lambda *_args, **_kwargs: {"df": object(), "data_trade_date": "20260324"},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.get_stock_basic_snapshot_map",
        lambda: {},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.build_daily_stock_source_df",
        lambda *_args, **_kwargs: source_df,
    )
    monkeypatch.setattr(
        "app.services.decision_context.tushare_client._get_ths_concept_names_for_stock",
        lambda ts_code: ["机器人"] if ts_code == "002779.SZ" else [],
    )

    candidates = service._build_mainline_pullback_candidates(
        "2026-03-24",
        sector_scan,
        [],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.ts_code == "002779.SZ"
    assert candidate.sector_name == "机器人"
    assert candidate.candidate_source_tag == service.MAINLINE_PULLBACK_SOURCE_TAG


def test_get_candidate_stocks_merges_duplicate_mainline_recall_source(monkeypatch):
    """主线补充命中已存在候选时，应追加来源标签而不是重复插入。"""
    service = DecisionContextService()
    base_payload = {
        "rows": [
            {
                "ts_code": "002463.SZ",
                "stock_name": "沪电股份",
                "sector_name": "PCB",
                "close": 30.5,
                "change_pct": 3.2,
                "turnover_rate": 6.1,
                "amount": 120000,
                "vol_ratio": 1.8,
                "high": 31.0,
                "low": 30.1,
                "open": 30.2,
                "pre_close": 29.55,
                "candidate_source_tag": "涨幅前列",
                "concept_names": ["算力"],
            }
        ],
        "data_trade_date": "20260324",
        "data_status": "ok",
        "data_message": "",
    }

    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.get_expanded_stock_list_with_meta",
        lambda *_args, **_kwargs: base_payload,
    )
    monkeypatch.setattr(
        service,
        "_build_mainline_pullback_candidates",
        lambda *_args, **_kwargs: [
            StockInput(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                sector_name="高速铜缆",
                close=30.5,
                change_pct=3.2,
                turnover_rate=6.1,
                amount=120000,
                vol_ratio=1.8,
                high=31.0,
                low=30.1,
                open=30.2,
                pre_close=29.55,
                candidate_source_tag=service.MAINLINE_PULLBACK_SOURCE_TAG,
                concept_names=["高速铜缆"],
            )
        ],
    )

    stocks, resolved_trade_date, data_status, data_message = service.get_candidate_stocks(
        "2026-03-24",
        top_gainers=100,
        sector_scan=SimpleNamespace(),
    )

    assert len(stocks) == 1
    assert stocks[0].candidate_source_tag == "涨幅前列/主线回踩补充"
    assert stocks[0].concept_names == ["算力", "高速铜缆"]
    assert resolved_trade_date == "2026-03-24"
    assert data_status == "ok"
    assert data_message == ""


def test_build_mainline_pullback_candidates_keeps_branch_quotas(monkeypatch):
    """同一主线方向应分别保留回踩/低吸配额，避免被单一分支占满。"""
    service = DecisionContextService()
    sector_scan = SimpleNamespace(
        theme_leaders=[SimpleNamespace(sector_name="算力", sector_source_type="concept")],
        industry_leaders=[],
        mainline_sectors=[],
        sub_mainline_sectors=[],
    )
    source_df = pd.DataFrame(
        [
            {
                "ts_code": "002001.SZ",
                "stock_name": "算力A",
                "industry": "电子",
                "close": 10.20,
                "pct_change": 1.3,
                "turnover_rate": 6.1,
                "amount": 120000,
                "volume_ratio": 1.4,
                "high": 10.28,
                "low": 10.00,
                "open": 10.12,
                "pre_close": 10.07,
                "avg_price": 10.16,
                "volume": 100000,
            },
            {
                "ts_code": "002002.SZ",
                "stock_name": "算力B",
                "industry": "电子",
                "close": 11.15,
                "pct_change": 1.9,
                "turnover_rate": 7.0,
                "amount": 118000,
                "volume_ratio": 1.5,
                "high": 11.24,
                "low": 10.92,
                "open": 11.02,
                "pre_close": 10.94,
                "avg_price": 11.08,
                "volume": 100000,
            },
            {
                "ts_code": "002003.SZ",
                "stock_name": "算力C",
                "industry": "电子",
                "close": 12.40,
                "pct_change": 2.2,
                "turnover_rate": 5.8,
                "amount": 116000,
                "volume_ratio": 1.3,
                "high": 12.52,
                "low": 12.15,
                "open": 12.26,
                "pre_close": 12.13,
                "avg_price": 12.32,
                "volume": 100000,
            },
            {
                "ts_code": "002004.SZ",
                "stock_name": "算力D",
                "industry": "电子",
                "close": 13.05,
                "pct_change": -2.2,
                "turnover_rate": 4.2,
                "amount": 110000,
                "volume_ratio": 1.2,
                "high": 13.10,
                "low": 12.88,
                "open": 12.94,
                "pre_close": 13.34,
                "avg_price": 12.96,
                "volume": 100000,
            },
            {
                "ts_code": "002005.SZ",
                "stock_name": "算力E",
                "industry": "电子",
                "close": 14.08,
                "pct_change": -0.3,
                "turnover_rate": 3.9,
                "amount": 108000,
                "volume_ratio": 1.1,
                "high": 14.11,
                "low": 13.95,
                "open": 14.00,
                "pre_close": 14.36,
                "avg_price": 14.02,
                "volume": 100000,
            },
            {
                "ts_code": "002006.SZ",
                "stock_name": "算力F",
                "industry": "电子",
                "close": 15.10,
                "pct_change": 0.2,
                "turnover_rate": 4.1,
                "amount": 106000,
                "volume_ratio": 1.0,
                "high": 15.14,
                "low": 14.98,
                "open": 15.02,
                "pre_close": 15.34,
                "avg_price": 15.03,
                "volume": 100000,
            },
        ]
    )

    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.fetch_recent_stock_daily_df",
        lambda *_args, **_kwargs: {"df": object(), "data_trade_date": "20260324"},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.get_stock_basic_snapshot_map",
        lambda: {},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.build_daily_stock_source_df",
        lambda *_args, **_kwargs: source_df,
    )
    monkeypatch.setattr(
        "app.services.decision_context.tushare_client._get_ths_concept_names_for_stock",
        lambda _ts_code: ["算力"],
    )

    candidates = service._build_mainline_pullback_candidates(
        "2026-03-24",
        sector_scan,
        [],
    )

    assert len(candidates) == (
        service.strategy.mainline_pullback_per_sector_limit
        + service.strategy.mainline_low_suck_per_sector_limit
    )
    assert sum(
        1 for item in candidates
        if item.candidate_source_tag == service.MAINLINE_PULLBACK_SOURCE_TAG
    ) == service.strategy.mainline_pullback_per_sector_limit
    assert sum(
        1 for item in candidates
        if item.candidate_source_tag == service.MAINLINE_LOW_SUCK_SOURCE_TAG
    ) == service.strategy.mainline_low_suck_per_sector_limit


def test_build_mainline_pullback_candidates_respects_custom_strategy(monkeypatch):
    """召回阈值与配额应跟随策略配置变化。"""
    strategy = replace(
        DEFAULT_STOCK_FILTER_STRATEGY,
        mainline_pullback_per_sector_limit=1,
        mainline_low_suck_per_sector_limit=1,
        mainline_pullback_change_min=0.0,
        mainline_pullback_change_max=1.0,
    )
    service = DecisionContextService(strategy=strategy)
    sector_scan = SimpleNamespace(
        theme_leaders=[SimpleNamespace(sector_name="机器人", sector_source_type="concept")],
        industry_leaders=[],
        mainline_sectors=[],
        sub_mainline_sectors=[],
    )
    source_df = pd.DataFrame(
        [
            {
                "ts_code": "002001.SZ",
                "stock_name": "机器人A",
                "industry": "专用设备",
                "close": 10.20,
                "pct_change": 1.3,
                "turnover_rate": 6.1,
                "amount": 120000,
                "volume_ratio": 1.4,
                "high": 10.28,
                "low": 10.00,
                "open": 10.12,
                "pre_close": 10.07,
                "avg_price": 10.16,
                "volume": 100000,
            },
            {
                "ts_code": "002002.SZ",
                "stock_name": "机器人B",
                "industry": "专用设备",
                "close": 11.05,
                "pct_change": -0.4,
                "turnover_rate": 4.0,
                "amount": 118000,
                "volume_ratio": 1.2,
                "high": 11.12,
                "low": 10.92,
                "open": 10.98,
                "pre_close": 11.09,
                "avg_price": 11.00,
                "volume": 100000,
            },
        ]
    )

    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.fetch_recent_stock_daily_df",
        lambda *_args, **_kwargs: {"df": object(), "data_trade_date": "20260324"},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.get_stock_basic_snapshot_map",
        lambda: {},
    )
    monkeypatch.setattr(
        "app.services.decision_context.market_data_gateway.build_daily_stock_source_df",
        lambda *_args, **_kwargs: source_df,
    )
    monkeypatch.setattr(
        "app.services.decision_context.tushare_client._get_ths_concept_names_for_stock",
        lambda _ts_code: ["机器人"],
    )

    candidates = service._build_mainline_pullback_candidates(
        "2026-03-24",
        sector_scan,
        [],
    )

    assert len(candidates) == 1
    assert candidates[0].candidate_source_tag == service.MAINLINE_LOW_SUCK_SOURCE_TAG
