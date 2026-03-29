"""
账户 API 行情刷新测试
"""
import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import account


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
