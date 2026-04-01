"""
FastAPI 路由集成测试
"""
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.main import app, settings
from app.api.v1 import account, decision, stock
from app.core.config import Settings
from app.models.schemas import (
    AccountInput,
    ApiResponse,
    BuyPointOutput,
    BuyPointResponse,
    BuyPointType,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    SellPointResponse,
    StockOutput,
    StockPoolsOutput,
    StockPoolTag,
    StockStrengthTag,
    StockContinuityTag,
    StockTradeabilityTag,
    StockCoreTag,
)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeResult(self._row)

    async def commit(self):
        return None


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(Settings, "validate_runtime", lambda _self: None)
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: _FakeSession(SimpleNamespace(id=1)),
    )
    transport = httpx.ASGITransport(app=app)
    await app.router.startup()
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    await app.router.shutdown()
    monkeypatch.setattr(settings, "auth_enabled", True)


@pytest.mark.asyncio
async def test_root_and_health_routes(client):
    root = await client.get("/")
    assert root.status_code == 200
    assert root.json()["status"] == "running"

    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_account_config_route_via_testclient(client, monkeypatch):
    async def fake_get_config(account_id=None):
        return {
            "available_cash": 500000.0,
            "updated_at": None,
        }

    monkeypatch.setattr(account, "get_account_config_from_db", fake_get_config)

    response = await client.get("/api/v1/account/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["available_cash"] == 500000.0


@pytest.mark.asyncio
async def test_account_overview_route_via_testclient(client, monkeypatch):
    async def fake_build_overview(_current_account):
        return {
            "profile": {
                "account_id": "account-1",
                "account_name": "默认账户",
                "total_asset": 500000.0,
                "available_cash": 320000.0,
                "market_value": 180000.0,
                "total_position_ratio": 0.36,
                "holding_count": 2,
                "t1_locked_count": 1,
                "can_trade": True,
                "action": "控制仓位",
                "priority": "观察为主",
            },
            "status": {
                "account_id": "account-1",
                "account_name": "默认账户",
                "can_trade": True,
                "action": "控制仓位",
                "priority": "观察为主",
                "position_ratio": 0.36,
                "available_cash": 320000.0,
                "holding_count": 2,
            },
            "positions": [
                {
                    "ts_code": "000001.SZ",
                    "stock_name": "平安银行",
                    "holding_qty": 100,
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(account, "build_account_overview_payload", fake_build_overview)

    response = await client.get("/api/v1/account/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["profile"]["account_name"] == "默认账户"
    assert payload["data"]["positions"][0]["ts_code"] == "000001.SZ"


@pytest.mark.asyncio
async def test_account_overview_route_uses_short_ttl_cache(monkeypatch):
    calls = {"overview": 0}

    async def fake_build_overview(_current_account):
        calls["overview"] += 1
        return {
            "profile": {
                "account_id": "account-1",
                "account_name": "默认账户",
                "total_asset": 500000.0,
                "available_cash": 320000.0,
                "market_value": 180000.0,
                "total_position_ratio": 0.36,
                "holding_count": 2,
                "t1_locked_count": 1,
                "can_trade": True,
                "action": "控制仓位",
                "priority": "观察为主",
            },
            "status": {
                "account_id": "account-1",
                "account_name": "默认账户",
                "can_trade": True,
                "action": "控制仓位",
                "priority": "观察为主",
                "position_ratio": 0.36,
                "available_cash": 320000.0,
                "holding_count": 2,
            },
            "positions": [],
            "total": 0,
        }

    monkeypatch.setattr(account, "_account_overview_cache", {})
    monkeypatch.setattr(account, "build_account_overview_payload", fake_build_overview)

    current_account = SimpleNamespace(
        id="account-1",
        account_name="默认账户",
    )
    first = await account.get_overview(current_account=current_account)
    second = await account.get_overview(current_account=current_account)

    assert first.code == 200
    assert second.code == 200
    assert calls["overview"] == 1


@pytest.mark.asyncio
async def test_sell_point_route_uses_lightweight_context_path(monkeypatch):
    async def fail_build_context(*args, **kwargs):
        raise AssertionError("sell-point route should not build full decision context")

    async def fake_get_holdings(_account_id=None, _trade_date=None):
        return []

    async def fake_get_snapshot(_trade_date):
        return {"cached": True}

    def fake_market_env(_trade_date):
        return MarketEnvOutput(
            trade_date="2026-03-28",
            market_env_tag=MarketEnvTag.ATTACK,
            breakout_allowed=True,
            risk_level=RiskLevel.LOW,
            market_comment="进攻环境",
            index_score=80,
            sentiment_score=75,
            overall_score=77,
        )

    def fake_sell_analyze(*args, **kwargs):
        return SellPointResponse(
            trade_date="2026-03-28",
            hold_positions=[],
            reduce_positions=[],
            sell_positions=[],
            total_count=0,
        )

    async def fake_save_snapshot(*args, **kwargs):
        return 0

    monkeypatch.setattr(decision.decision_context_service, "build_context", fail_build_context)
    monkeypatch.setattr(decision.decision_context_service, "get_holdings_from_db", fake_get_holdings)
    monkeypatch.setattr(decision.sector_scan_snapshot_service, "get_snapshot", fake_get_snapshot)
    monkeypatch.setattr(decision.market_env_service, "get_current_env", fake_market_env)
    monkeypatch.setattr(decision.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)

    response = await decision.analyze_sell_point(
        trade_date="2026-03-28",
        refresh=False,
        include_llm=False,
        current_account=SimpleNamespace(id="account-1"),
    )

    assert isinstance(response, ApiResponse)
    assert response.code == 200
    assert response.data["total_count"] == 0


@pytest.mark.asyncio
async def test_sell_point_route_uses_short_ttl_cache(monkeypatch):
    calls = {"holdings": 0, "analyze": 0}

    async def fake_get_holdings(_account_id=None, _trade_date=None):
        calls["holdings"] += 1
        return []

    async def fake_get_snapshot(_trade_date):
        return {"cached": True}

    def fake_market_env(_trade_date):
        return MarketEnvOutput(
            trade_date="2026-03-28",
            market_env_tag=MarketEnvTag.ATTACK,
            breakout_allowed=True,
            risk_level=RiskLevel.LOW,
            market_comment="进攻环境",
            index_score=80,
            sentiment_score=75,
            overall_score=77,
        )

    def fake_sell_analyze(*args, **kwargs):
        calls["analyze"] += 1
        return SellPointResponse(
            trade_date="2026-03-28",
            hold_positions=[],
            reduce_positions=[],
            sell_positions=[],
            total_count=0,
        )

    async def fake_save_snapshot(*args, **kwargs):
        return 0

    monkeypatch.setattr(decision, "_sell_point_page_cache", {})
    monkeypatch.setattr(decision.decision_context_service, "get_holdings_from_db", fake_get_holdings)
    monkeypatch.setattr(decision.sector_scan_snapshot_service, "get_snapshot", fake_get_snapshot)
    monkeypatch.setattr(decision.market_env_service, "get_current_env", fake_market_env)
    monkeypatch.setattr(decision.sell_point_service, "analyze", fake_sell_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)

    current_account = SimpleNamespace(id="account-1")
    first = await decision.analyze_sell_point(
        trade_date="2026-03-28",
        refresh=False,
        force_llm_refresh=False,
        include_llm=False,
        current_account=current_account,
    )
    second = await decision.analyze_sell_point(
        trade_date="2026-03-28",
        refresh=False,
        force_llm_refresh=False,
        include_llm=False,
        current_account=current_account,
    )

    assert first.code == 200
    assert second.code == 200
    assert calls == {"holdings": 1, "analyze": 1}


@pytest.mark.asyncio
async def test_buy_point_route_via_testclient(client, monkeypatch):
    bundle = SimpleNamespace(
        context=SimpleNamespace(
            stocks=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=80000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
                t1_locked_positions=[],
            ),
            market_env=MarketEnvOutput(
                trade_date="2026-03-28",
                market_env_tag=MarketEnvTag.ATTACK,
                breakout_allowed=True,
                risk_level=RiskLevel.LOW,
                market_comment="进攻环境",
                index_score=80,
                sentiment_score=75,
                overall_score=77,
            ),
            sector_scan=None,
        ),
        scored_stocks=[],
        stock_pools=StockPoolsOutput(
            trade_date="2026-03-28",
            market_watch_pool=[],
            trend_recognition_pool=[],
            account_executable_pool=[],
            holding_process_pool=[],
            total_count=0,
        ),
        review_bias_profile={"exact": {}, "bucket": {}},
    )

    async def fake_build_candidate_analysis(*args, **kwargs):
        return bundle

    async def fake_get_page_snapshot(*args, **kwargs):
        return None

    async def fake_get_review_bias_profile(*args, **kwargs):
        return {"exact": {}, "bucket": {}}

    def fake_buy_analyze(*args, **kwargs):
        return BuyPointResponse(
            trade_date="2026-03-28",
            market_env_tag=MarketEnvTag.ATTACK,
            available_buy_points=[
                BuyPointOutput(
                    ts_code="000001.SZ",
                    stock_name="平安银行",
                    buy_signal_tag="可买",
                    buy_point_type=BuyPointType.RETRACE_SUPPORT,
                    buy_trigger_cond="回踩确认",
                    buy_confirm_cond="量价配合",
                    buy_invalid_cond="跌破失效",
                    buy_risk_level=RiskLevel.MEDIUM,
                    buy_account_fit="适合",
                    buy_comment="测试买点",
                )
            ],
            observe_buy_points=[],
            not_buy_points=[],
            total_count=1,
        )

    async def fake_save_snapshot(*args, **kwargs):
        return 1

    async def fake_save_page_snapshot(*args, **kwargs):
        return 1

    monkeypatch.setattr(decision.decision_flow_service, "build_candidate_analysis", fake_build_candidate_analysis)
    monkeypatch.setattr(decision.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_page_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "get_review_bias_profile_safe", fake_get_review_bias_profile)
    monkeypatch.setattr(decision.buy_point_service, "analyze", fake_buy_analyze)
    monkeypatch.setattr(decision.review_snapshot_service, "save_analysis_snapshot_safe", fake_save_snapshot)
    monkeypatch.setattr(decision.review_snapshot_service, "save_stock_pools_page_snapshot_safe", fake_save_page_snapshot)
    async def fake_resolve_snapshot_lookup_trade_date(trade_date):
        return trade_date

    monkeypatch.setattr(
        decision,
        "resolve_snapshot_lookup_trade_date",
        fake_resolve_snapshot_lookup_trade_date,
    )

    response = await client.get("/api/v1/decision/buy-point", params={"trade_date": "2026-03-28", "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["total_count"] == 1
    assert payload["data"]["available_buy_points"][0]["ts_code"] == "000001.SZ"


@pytest.mark.asyncio
async def test_stock_pools_route_uses_cached_snapshot_via_testclient(client, monkeypatch):
    cached = StockPoolsOutput(
        trade_date="2026-03-28",
        resolved_trade_date="2026-03-27",
        sector_scan_trade_date="2026-03-27",
        sector_scan_resolved_trade_date="2026-03-27",
        snapshot_version=3,
        market_watch_pool=[
            StockOutput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                sector_name="银行",
                change_pct=3.2,
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

    async def fake_resolve_lookup_trade_date(_trade_date):
        return "2026-03-27"

    async def fake_get_snapshot(trade_date, candidate_limit):
        assert trade_date == "2026-03-28"
        assert candidate_limit == 100
        return cached

    monkeypatch.setattr(stock, "resolve_snapshot_lookup_trade_date", fake_resolve_lookup_trade_date)
    monkeypatch.setattr(stock.review_snapshot_service, "get_stock_pools_page_snapshot", fake_get_snapshot)

    response = await client.get("/api/v1/stock/pools", params={"trade_date": "2026-03-28", "limit": 50})

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["resolved_trade_date"] == "2026-03-27"
    assert payload["data"]["llm_status"]["status"] == "disabled"
    assert payload["data"]["market_watch_pool"][0]["ts_code"] == "000001.SZ"
