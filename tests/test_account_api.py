"""
账户 API 行情刷新测试
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import account
from app.models.account_setting import AccountSetting
from app.services.portfolio_service import portfolio_service


def test_refresh_holdings_price_uses_batch_quote_chain(monkeypatch):
    """账户页持仓刷新应优先复用批量行情链路。"""

    def fake_get_stock_quote_map(ts_codes, trade_date):
        assert ts_codes == ["601012.SH", "002463.SZ"]
        assert trade_date
        return {
            "601012.SH": {
                "ts_code": "601012.SH",
                "stock_name": "隆基绿能",
                "close": 19.18,
                "pre_close": 18.90,
                "quote_time": "2026-03-23 14:32:10",
                "data_source": "realtime_sina",
            },
            "002463.SZ": {
                "ts_code": "002463.SZ",
                "stock_name": "沪电股份",
                "close": 84.30,
                "pre_close": 85.10,
                "quote_time": "2026-03-23 14:32:11",
                "data_source": "realtime_sina",
            },
        }

    monkeypatch.setattr(account.tushare_client, "get_stock_quote_map", fake_get_stock_quote_map)

    holdings = [
        {
            "ts_code": "601012.SH",
            "stock_name": "隆基绿能",
            "holding_qty": 800,
            "cost_price": 18.49,
            "market_price": 0.0,
            "holding_market_value": 0.0,
            "pnl_pct": -100.0,
        },
        {
            "ts_code": "002463.SZ",
            "stock_name": "沪电股份",
            "holding_qty": 200,
            "cost_price": 86.45,
            "market_price": 84.30,
            "holding_market_value": 16860.0,
            "pnl_pct": -2.49,
        },
    ]

    account.refresh_holdings_price(holdings)

    assert holdings[0]["market_price"] == 19.18
    assert holdings[0]["pre_close"] == 18.90
    assert holdings[0]["holding_market_value"] == 15344.0
    assert holdings[0]["quote_time"] == "2026-03-23 14:32:10"
    assert holdings[0]["data_source"] == "realtime_sina"
    assert holdings[0]["pnl_pct"] == 3.73


def test_refresh_holdings_price_keeps_existing_when_detail_missing(monkeypatch):
    """个股详情拿不到有效价格时，不应把已有持仓价格覆盖成 0。"""

    monkeypatch.setattr(
        account.tushare_client,
        "get_stock_quote_map",
        lambda ts_codes, trade_date: {
            "002025.SZ": {
                "ts_code": "002025.SZ",
                "stock_name": "测试股票",
                "close": 0.0,
                "pre_close": 0.0,
                "quote_time": None,
                "data_source": "daily_fallback",
            }
        },
    )

    holdings = [
        {
            "ts_code": "002025.SZ",
            "stock_name": "航天电器",
            "holding_qty": 100,
            "cost_price": 63.55,
            "market_price": 63.44,
            "holding_market_value": 6344.0,
            "pnl_pct": -0.17,
        }
    ]

    account.refresh_holdings_price(holdings)

    assert holdings[0]["market_price"] == 63.44
    assert holdings[0]["holding_market_value"] == 6344.0
    assert holdings[0]["pnl_pct"] == -0.17


@pytest.mark.asyncio
async def test_build_account_overview_payload_enriches_pnl_amounts(monkeypatch):
    async def fake_get_holdings(_account_id):
        return [
            {
                "id": "h1",
                "ts_code": "601012.SH",
                "stock_name": "隆基绿能",
                "holding_qty": 800,
                "cost_price": 18.49,
                "market_price": 18.52,
                "pre_close": 18.40,
                "pnl_pct": 0.16,
                "holding_market_value": 14816.0,
                "buy_date": "2026-02-24",
                "can_sell_today": True,
                "holding_reason": "测试",
            }
        ]

    async def fake_build_account_input(_holdings, _account_id):
        return account.AccountInput(
            total_asset=100000.0,
            available_cash=85184.0,
            total_position_ratio=0.1482,
            holding_count=1,
            today_new_buy_count=0,
            t1_locked_positions=[],
        )

    monkeypatch.setattr(account, "get_holdings_from_db", fake_get_holdings)
    monkeypatch.setattr(account, "build_account_input", fake_build_account_input)
    monkeypatch.setattr(
        account.account_adapter_service,
        "get_profile",
        lambda _account, _holdings: account.AccountProfile(
            total_asset=100000.0,
            available_cash=85184.0,
            total_position_ratio=0.1482,
            holding_count=1,
            today_new_buy_count=0,
            t1_locked_count=0,
            market_value=14816.0,
        ),
    )
    monkeypatch.setattr(
        account.account_adapter_service,
        "adapt",
        lambda *_args, **_kwargs: SimpleNamespace(
            new_position_allowed=True,
            account_action_tag="可执行",
            priority_action="保持现有仓位",
        ),
    )

    payload = await account.build_account_overview_payload(
        SimpleNamespace(id="account-1", account_name="默认账户")
    )

    assert payload["profile"]["total_pnl_amount"] == 24.0
    assert payload["profile"]["today_pnl_amount"] == 96.0
    assert payload["positions"][0]["pnl_amount"] == 24.0
    assert payload["positions"][0]["today_pnl_amount"] == 96.0


@pytest.mark.asyncio
async def test_build_account_input_uses_available_cash_and_auto_computes_total_asset(monkeypatch):
    async def fake_get_account_available_cash(account_id=None):
        return 20000.0

    monkeypatch.setattr(
        "app.services.portfolio_service.get_account_available_cash",
        fake_get_account_available_cash,
    )

    account_input = await portfolio_service.build_account_input_from_holdings(
        [
            {
                "holding_market_value": 30000.0,
                "holding_qty": 100,
                "market_price": 300.0,
                "buy_date": "2026-03-20",
            }
        ],
        account_id="account-1",
        trade_date="2026-03-23",
    )

    assert account_input.available_cash == 20000.0
    assert account_input.total_asset == 50000.0
    assert account_input.total_position_ratio == 0.6


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _PositionSession:
    def __init__(self, *, holding=None, setting=None):
        self.holding = holding
        self.setting = setting

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is account.Holding:
            return _FakeResult(self.holding)
        if entity is account.AccountSetting:
            return _FakeResult(self.setting)
        raise AssertionError(f"unexpected entity: {entity}")

    def add(self, row):
        if isinstance(row, account.Holding):
            self.holding = row
            return
        if isinstance(row, account.AccountSetting):
            self.setting = row
            return
        raise AssertionError(f"unexpected add: {type(row)}")

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _row):
        return None

    async def delete(self, row):
        assert row is self.holding
        self.holding = None


def test_classify_position_change_distinguishes_add_reduce_and_close():
    holding = account.Holding(
        id="h1",
        account_id="account-1",
        ts_code="000001.SZ",
        stock_name="平安银行",
        holding_qty=100,
        cost_price=10.0,
        market_price=12.0,
        pnl_pct=20.0,
        holding_market_value=1200.0,
        buy_date="2026-04-01",
        can_sell_today=True,
        holding_reason="测试",
    )

    assert account._classify_position_change(holding, {"holding_reason": "新理由"}) == ("update", 0.0)
    assert account._classify_position_change(holding, {"holding_qty": 150}) == ("add", -500.0)
    assert account._classify_position_change(holding, {"cost_price": 9.5}) == ("update", 0.0)
    assert account._classify_position_change(holding, {"holding_qty": 60}) == ("reduce", 480.0)
    assert account._classify_position_change(holding, {"holding_qty": 0}) == ("close", 1200.0)
    assert account._classify_position_change(holding, {"holding_qty": 200, "cost_price": 11.0}) == ("add", -1200.0)


@pytest.mark.asyncio
async def test_add_position_auto_decreases_available_cash(monkeypatch):
    session = _PositionSession(
        setting=AccountSetting(
            account_id="account-1",
            available_cash=10000.0,
            total_asset=10000.0,
        )
    )

    monkeypatch.setattr(account, "async_session_factory", lambda: session)
    monkeypatch.setattr(account, "normalize_ts_code", lambda _code: "000001.SZ")
    monkeypatch.setattr(account, "get_stock_name", lambda _code: __import__("asyncio").sleep(0, result="平安银行"))
    monkeypatch.setattr(
        account.tushare_client,
        "get_stock_detail",
        lambda *_args, **_kwargs: {"close": 10.2, "stock_name": "平安银行"},
    )
    monkeypatch.setattr(account, "_invalidate_account_overview_cache", lambda _account_id: None)

    response = await account.add_position(
        account.AddPositionRequest(
            ts_code="000001",
            holding_qty=100,
            cost_price=10.0,
            buy_date="2026-04-01",
            holding_reason="测试建仓",
        ),
        current_account=SimpleNamespace(id="account-1"),
    )

    assert response.code == 200
    assert session.setting.available_cash == 9000.0
    assert session.holding is not None
    assert session.holding.ts_code == "000001.SZ"


@pytest.mark.asyncio
async def test_update_position_auto_adjusts_available_cash(monkeypatch):
    session = _PositionSession(
        holding=account.Holding(
            id="h1",
            account_id="account-1",
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=10.0,
            market_price=12.0,
            pnl_pct=20.0,
            holding_market_value=1200.0,
            buy_date="2026-04-01",
            can_sell_today=True,
            holding_reason="测试",
        ),
        setting=AccountSetting(
            account_id="account-1",
            available_cash=9000.0,
            total_asset=10000.0,
        ),
    )

    monkeypatch.setattr(account, "async_session_factory", lambda: session)
    monkeypatch.setattr(account, "normalize_ts_code", lambda code: code)
    monkeypatch.setattr(account, "refresh_holdings_price", lambda _holdings: None)
    monkeypatch.setattr(account, "enrich_holdings", lambda _holdings: None)
    monkeypatch.setattr(account, "_invalidate_account_overview_cache", lambda _account_id: None)

    response = await account.update_position(
        "000001.SZ",
        account.UpdatePositionRequest(holding_qty=150, cost_price=10.0),
        current_account=SimpleNamespace(id="account-1"),
    )

    assert response.code == 200
    assert session.setting.available_cash == 8500.0
    assert session.holding.holding_qty == 150


@pytest.mark.asyncio
async def test_update_position_reduce_uses_market_price_to_increase_available_cash(monkeypatch):
    session = _PositionSession(
        holding=account.Holding(
            id="h1",
            account_id="account-1",
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=10.0,
            market_price=12.0,
            pnl_pct=20.0,
            holding_market_value=1200.0,
            buy_date="2026-04-01",
            can_sell_today=True,
            holding_reason="测试",
        ),
        setting=AccountSetting(
            account_id="account-1",
            available_cash=9000.0,
            total_asset=10000.0,
        ),
    )

    monkeypatch.setattr(account, "async_session_factory", lambda: session)
    monkeypatch.setattr(account, "normalize_ts_code", lambda code: code)
    monkeypatch.setattr(account, "refresh_holdings_price", lambda _holdings: None)
    monkeypatch.setattr(account, "enrich_holdings", lambda _holdings: None)
    monkeypatch.setattr(account, "_invalidate_account_overview_cache", lambda _account_id: None)

    response = await account.update_position(
        "000001.SZ",
        account.UpdatePositionRequest(holding_qty=60, cost_price=10.0),
        current_account=SimpleNamespace(id="account-1"),
    )

    assert response.code == 200
    assert response.data["operation"] == "reduce"
    assert session.setting.available_cash == 9480.0
    assert session.holding.holding_qty == 60


@pytest.mark.asyncio
async def test_update_position_zero_qty_is_close(monkeypatch):
    session = _PositionSession(
        holding=account.Holding(
            id="h1",
            account_id="account-1",
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=10.0,
            market_price=12.0,
            pnl_pct=20.0,
            holding_market_value=1200.0,
            buy_date="2026-04-01",
            can_sell_today=True,
            holding_reason="测试",
        ),
        setting=AccountSetting(
            account_id="account-1",
            available_cash=8800.0,
            total_asset=10000.0,
        ),
    )

    monkeypatch.setattr(account, "async_session_factory", lambda: session)
    monkeypatch.setattr(account, "normalize_ts_code", lambda code: code)
    monkeypatch.setattr(account, "_invalidate_account_overview_cache", lambda _account_id: None)

    response = await account.update_position(
        "000001.SZ",
        account.UpdatePositionRequest(holding_qty=0),
        current_account=SimpleNamespace(id="account-1"),
    )

    assert response.code == 200
    assert response.data["operation"] == "close"
    assert session.setting.available_cash == 10000.0
    assert session.holding is None


@pytest.mark.asyncio
async def test_delete_position_auto_increases_available_cash(monkeypatch):
    session = _PositionSession(
        holding=account.Holding(
            id="h1",
            account_id="account-1",
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=10.0,
            market_price=12.0,
            pnl_pct=20.0,
            holding_market_value=1200.0,
            buy_date="2026-04-01",
            can_sell_today=True,
            holding_reason="测试",
        ),
        setting=AccountSetting(
            account_id="account-1",
            available_cash=8800.0,
            total_asset=10000.0,
        ),
    )

    monkeypatch.setattr(account, "async_session_factory", lambda: session)
    monkeypatch.setattr(account, "refresh_holdings_price", lambda _holdings: None)
    monkeypatch.setattr(account, "_invalidate_account_overview_cache", lambda _account_id: None)

    response = await account.delete_position(
        "h1",
        current_account=SimpleNamespace(id="account-1"),
    )

    assert response.code == 200
    assert response.data["operation"] == "close"
    assert session.setting.available_cash == 10000.0
    assert session.holding is None
