"""
手动跟踪池 API 测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.models.schemas import (  # noqa: E402
    AccountInput,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    StockInput,
    StockOutput,
    StockContinuityTag,
    StockCoreTag,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
)


@pytest.mark.asyncio
async def test_get_manual_watch_returns_items(monkeypatch):
    entries = [("000001.SZ", __import__("datetime").datetime.utcnow())]

    async def fake_list(_account_id):
        return entries

    async def fake_build_view(trade_date, account_id, ents):
        assert trade_date == "2026-04-18"
        assert ents == entries
        return [{"ts_code": "000001.SZ", "stock_name": "平安银行", "candidate_source_tag": "手动跟踪"}]

    monkeypatch.setattr(stock, "manual_watch_list_codes", fake_list)
    monkeypatch.setattr(stock, "build_manual_watch_view", fake_build_view)

    resp = await stock.get_manual_watch(
        trade_date="2026-04-18",
        current_account=type("A", (), {"id": "acct-1"})(),
    )
    assert resp.code == 200
    assert resp.data["total"] == 1
    assert resp.data["items"][0]["ts_code"] == "000001.SZ"


@pytest.mark.asyncio
async def test_post_manual_watch_duplicate_returns_409(monkeypatch):
    from sqlalchemy.exc import IntegrityError

    def fake_build_input(_raw, _td, candidate_source_tag=""):
        return StockInput(
            ts_code="000001.SZ",
            stock_name="平安银行",
            sector_name="银行",
            close=10.0,
            change_pct=1.0,
            turnover_rate=1.0,
            amount=1.0,
            high=10.0,
            low=10.0,
            open=10.0,
            pre_close=9.9,
            candidate_source_tag=candidate_source_tag or "",
        )

    async def fake_add(_account_id, _raw):
        raise IntegrityError("stmt", {}, None)

    monkeypatch.setattr(stock.decision_context_service, "build_single_stock_input", fake_build_input)
    monkeypatch.setattr(stock, "manual_watch_add", fake_add)

    from app.models.schemas import ManualWatchAddRequest

    resp = await stock.post_manual_watch(
        body=ManualWatchAddRequest(ts_code="000001.SZ"),
        trade_date="2026-04-18",
        current_account=type("A", (), {"id": "acct-1"})(),
    )
    assert resp.code == 409


@pytest.mark.asyncio
async def test_delete_manual_watch_not_found(monkeypatch):
    async def fake_remove(_account_id, _raw):
        return 0

    monkeypatch.setattr(stock, "manual_watch_remove", fake_remove)

    resp = await stock.delete_manual_watch(
        ts_code="000001.SZ",
        current_account=type("A", (), {"id": "acct-1"})(),
    )
    assert resp.code == 404


@pytest.mark.asyncio
async def test_build_manual_watch_view_marks_not_in_pool(monkeypatch):
    from app.services import manual_watch_service as mws

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
                holding_count=0,
                today_new_buy_count=0,
            ),
            "market_env": MarketEnvOutput(
                trade_date="2026-04-18",
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

    async def fake_build_context(*args, **kwargs):
        return context

    def fake_build_input(ts_code, trade_date, candidate_source_tag=""):
        return StockInput(
            ts_code=ts_code,
            stock_name="测试",
            sector_name="板块",
            close=10.0,
            change_pct=1.0,
            turnover_rate=1.0,
            amount=1.0,
            high=10.0,
            low=10.0,
            open=10.0,
            pre_close=9.9,
            candidate_source_tag=candidate_source_tag or "",
        )

    def fake_filter_with_context(trade_date, stocks, **kwargs):
        return [
            StockOutput(
                ts_code=s.ts_code,
                stock_name=s.stock_name,
                sector_name=s.sector_name,
                change_pct=s.change_pct,
                stock_strength_tag=StockStrengthTag.STRONG,
                stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
                stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
                stock_core_tag=StockCoreTag.CORE,
                stock_pool_tag=StockPoolTag.MARKET_WATCH,
                candidate_source_tag=s.candidate_source_tag or "",
            )
            for s in stocks
        ]

    monkeypatch.setattr(mws.decision_context_service, "build_context", fake_build_context)
    monkeypatch.setattr(mws.decision_context_service, "build_single_stock_input", fake_build_input)
    monkeypatch.setattr(mws.stock_filter_service, "filter_with_context", fake_filter_with_context)

    from datetime import datetime

    rows = await mws.build_manual_watch_view(
        "2026-04-18",
        None,
        [("000001.SZ", datetime(2026, 4, 1, 8, 0, 0))],
    )
    assert rows[0]["stock_pool_tag"] == StockPoolTag.NOT_IN_POOL.value
    assert rows[0]["candidate_source_tag"] == "手动跟踪"
    assert rows[0]["manual_watch_added_at"]
