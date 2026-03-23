"""
Tushare 客户端测试
"""
import os
import sys

import pandas as pd


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.tushare_client import TushareClient


class _FakePro:
    def __init__(self):
        self.daily_calls = []
        self.bak_daily_calls = []

    def stock_basic(self, ts_code=None):
        return pd.DataFrame([{"name": "航天电器", "industry": "元器件"}])

    def bak_daily(self, trade_date=None, fields=None):
        self.bak_daily_calls.append((trade_date, fields))
        if trade_date == "20260320":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002025.SZ",
                        "name": "航天电器",
                        "industry": "元器件",
                        "pct_change": 1.23,
                        "close": 56.78,
                        "open": 56.1,
                        "high": 57.2,
                        "low": 55.8,
                        "pre_close": 56.09,
                        "turn_over": 12.3,
                        "amount": 345678,
                        "vol_ratio": 1.8,
                    }
                ]
            )
        return pd.DataFrame()

    def daily(self, ts_code=None, start_date=None, end_date=None):
        self.daily_calls.append((ts_code, start_date, end_date))
        if (start_date, end_date) in {
            ("20260310", "20260320"),
            ("20260313", "20260323"),
        }:
            return pd.DataFrame(
                [
                    {
                        "close": 56.78,
                        "pct_chg": 1.23,
                        "vol": 120000,
                        "amount": 345678,
                        "high": 57.2,
                        "low": 55.8,
                        "open": 56.1,
                        "pre_close": 56.09,
                    }
                ]
            )
        return pd.DataFrame()


def test_get_stock_detail_uses_resolved_trade_date():
    """非交易日请求应先回退到最近交易日，并优先用 bak_daily 取行情。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"

    detail = client.get_stock_detail("002025.SZ", "2026-03-22")

    assert client.pro.bak_daily_calls
    assert client.pro.daily_calls == []
    assert detail["ts_code"] == "002025.SZ"
    assert detail["stock_name"] == "航天电器"
    assert detail["sector_name"] == "元器件"
    assert detail["close"] == 56.78


class _FallbackDailyPro(_FakePro):
    def bak_daily(self, trade_date=None, fields=None):
        self.bak_daily_calls.append((trade_date, fields))
        return pd.DataFrame()


def test_get_stock_detail_falls_back_to_recent_daily_when_same_day_not_ready():
    """交易日当天无 bak_daily 明细时，应回退到最近可用日线，而不是返回 0。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackDailyPro()
    client._resolve_trade_date = lambda d: "20260323"

    detail = client.get_stock_detail("002025.SZ", "2026-03-23")

    assert client.pro.bak_daily_calls
    assert client.pro.daily_calls == [("002025.SZ", "20260313", "20260323")]
    assert detail["close"] == 56.78
    assert detail["pre_close"] == 56.09


class _FallbackStockListPro(_FakePro):
    def __init__(self):
        super().__init__()
        self.trade_cal_calls = []

    def trade_cal(self, exchange=None, start_date=None, end_date=None, fields=None):
        self.trade_cal_calls.append((exchange, start_date, end_date, fields))
        return pd.DataFrame(
            [
                {"cal_date": "20260323", "is_open": 1},
                {"cal_date": "20260320", "is_open": 1},
                {"cal_date": "20260319", "is_open": 1},
            ]
        )

    def bak_daily(self, trade_date=None, fields=None):
        self.bak_daily_calls.append((trade_date, fields))
        if trade_date == "20260320":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002475.SZ",
                        "name": "立讯精密",
                        "industry": "电子",
                        "pct_change": 6.5,
                        "close": 35.0,
                        "open": 33.5,
                        "high": 36.0,
                        "low": 33.5,
                        "pre_close": 32.8,
                        "turn_over": 18.0,
                        "amount": 580000,
                        "vol_ratio": 3.0,
                    }
                ]
            )
        return pd.DataFrame()

    def limit_list_d(self, trade_date=None, limit_type=None):
        return pd.DataFrame()


def test_get_expanded_stock_list_falls_back_to_recent_available_bak_daily():
    """当天无 bak_daily 个股数据时，应回退到最近有数据的交易日，而不是用 mock 股票。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackStockListPro()
    client._resolve_trade_date = lambda d: "20260323"

    payload = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)

    assert payload["data_trade_date"] == "20260320"
    assert payload["used_mock"] is False
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["ts_code"] == "002475.SZ"
