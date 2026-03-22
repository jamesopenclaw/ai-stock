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

    def stock_basic(self, ts_code=None):
        return pd.DataFrame([{"name": "航天电器", "industry": "元器件"}])

    def daily(self, ts_code=None, start_date=None, end_date=None):
        self.daily_calls.append((ts_code, start_date, end_date))
        if start_date == "20260320" and end_date == "20260320":
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
    """非交易日请求应先回退到最近交易日，再取个股详情。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"

    detail = client.get_stock_detail("002025.SZ", "2026-03-22")

    assert client.pro.daily_calls == [("002025.SZ", "20260320", "20260320")]
    assert detail["ts_code"] == "002025.SZ"
    assert detail["stock_name"] == "航天电器"
    assert detail["sector_name"] == "元器件"
    assert detail["close"] == 56.78
