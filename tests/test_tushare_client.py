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
        self.daily_basic_calls = []
        self.index_daily_calls = []
        self.stock_basic_calls = []

    def stock_basic(self, ts_code=None, fields=None):
        self.stock_basic_calls.append((ts_code, fields))
        rows = [
            {"ts_code": "002025.SZ", "name": "航天电器", "industry": "元器件"},
            {"ts_code": "002475.SZ", "name": "立讯精密", "industry": "电子"},
        ]
        if ts_code:
            rows = [row for row in rows if row["ts_code"] == ts_code]
        return pd.DataFrame(rows)

    def daily(self, ts_code=None, start_date=None, end_date=None, trade_date=None):
        self.daily_calls.append((ts_code, start_date, end_date, trade_date))
        if trade_date == "20260320":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002025.SZ",
                        "trade_date": "20260320",
                        "close": 56.78,
                        "pct_chg": 1.23,
                        "vol": 120000,
                        "amount": 345678,
                        "high": 57.2,
                        "low": 55.8,
                        "open": 56.1,
                        "pre_close": 56.09,
                    },
                    {
                        "ts_code": "002475.SZ",
                        "trade_date": "20260320",
                        "close": 35.00,
                        "pct_chg": 6.50,
                        "vol": 320000,
                        "amount": 580000,
                        "high": 36.0,
                        "low": 33.5,
                        "open": 33.5,
                        "pre_close": 32.8,
                    },
                ]
            )
        if ts_code == "002025.SZ" and start_date == end_date == "20260320":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002025.SZ",
                        "trade_date": "20260320",
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

    def daily_basic(self, ts_code=None, trade_date=None, fields=None):
        self.daily_basic_calls.append((ts_code, trade_date, fields))
        if trade_date == "20260320":
            rows = [
                {
                    "ts_code": "002025.SZ",
                    "turnover_rate": 12.3,
                    "volume_ratio": 1.8,
                },
                {
                    "ts_code": "002475.SZ",
                    "turnover_rate": 18.0,
                    "volume_ratio": 3.0,
                },
            ]
            if ts_code:
                rows = [row for row in rows if row["ts_code"] == ts_code]
            return pd.DataFrame(rows)
        return pd.DataFrame()

    def index_daily(self, ts_code=None, start_date=None, end_date=None):
        self.index_daily_calls.append((ts_code, start_date, end_date))
        mapping = {
            "000001.SH": {"close": 3957.05, "pct_chg": 0.5, "vol": 102000000, "amount": 136000000000},
            "399001.SZ": {"close": 13866.20, "pct_chg": 0.8, "vol": 12200000000, "amount": 194000000000},
            "399006.SZ": {"close": 3352.10, "pct_chg": 1.2, "vol": 3390000000, "amount": 90300000000},
        }
        row = mapping.get(ts_code)
        if row and start_date == end_date == "20260320":
            payload = dict(row)
            payload["trade_date"] = "20260320"
            return pd.DataFrame([payload])
        return pd.DataFrame()


def test_get_stock_detail_uses_resolved_trade_date():
    """非交易日请求应先回退到最近交易日，并优先用 daily 取行情。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"
    client._recent_open_dates = lambda trade_date, count=5: ["20260320"]
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}

    detail = client.get_stock_detail("002025.SZ", "2026-03-22")

    assert client.pro.daily_calls == [("002025.SZ", "20260320", "20260320", None)]
    assert detail["ts_code"] == "002025.SZ"
    assert detail["stock_name"] == "航天电器"
    assert detail["sector_name"] == "元器件"
    assert detail["close"] == 56.78


class _FallbackDailyPro(_FakePro):
    def daily(self, ts_code=None, start_date=None, end_date=None, trade_date=None):
        self.daily_calls.append((ts_code, start_date, end_date, trade_date))
        if ts_code == "002025.SZ" and start_date == end_date == "20260320":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002025.SZ",
                        "trade_date": "20260320",
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


def test_get_stock_detail_falls_back_to_recent_daily_when_same_day_not_ready():
    """交易日当天无 daily 明细时，应回退到最近可用日线，而不是返回 0。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackDailyPro()
    client._resolve_trade_date = lambda d: "20260323"
    client._recent_open_dates = lambda trade_date, count=5: ["20260323", "20260320"]
    client._should_use_realtime_quote = lambda d: False
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}

    detail = client.get_stock_detail("002025.SZ", "2026-03-23")

    assert client.pro.daily_calls == [
        ("002025.SZ", "20260323", "20260323", None),
        ("002025.SZ", "20260320", "20260320", None),
    ]
    assert detail["close"] == 56.78
    assert detail["pre_close"] == 56.09


def test_get_stock_detail_overlays_realtime_quote_when_available():
    """当日盘中若实时行情可用，应覆盖详情中的价格字段。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260323"
    client._recent_open_dates = lambda trade_date, count=5: ["20260323", "20260320"]
    client._should_use_realtime_quote = lambda d: True
    client._intraday_volume_ratio_cache = {}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}
    client._fetch_realtime_quote_map = lambda codes: {
        "002025.SZ": {
            "close": 63.44,
            "change_pct": -0.17,
            "open": 63.70,
            "high": 64.10,
            "low": 63.22,
            "pre_close": 63.55,
            "volume": 2456000,
            "amount": 156000000,
            "avg_price": 63.52,
            "quote_time": "2026-03-23 09:35:51",
            "data_source": "realtime_sina",
        }
    }

    detail = client.get_stock_detail("002025.SZ", "2026-03-23")

    assert detail["close"] == 63.44
    assert detail["change_pct"] == -0.17
    assert detail["quote_time"] == "2026-03-23 09:35:51"
    assert detail["data_source"] == "realtime_sina"
    assert detail["intraday_volume_ratio"] is not None


def test_get_stock_quote_map_batches_daily_query_and_realtime_overlay():
    """批量行情应共用一次 daily/daily_basic 查询，并统一叠加实时覆盖。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"
    client._recent_open_dates = lambda trade_date, count=5: ["20260320"]
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}
    client._should_use_realtime_quote = lambda d: True
    client._fetch_realtime_quote_map = lambda codes: {
        "002025.SZ": {
            "close": 63.44,
            "change_pct": -0.17,
            "open": 63.70,
            "high": 64.10,
            "low": 63.22,
            "pre_close": 63.55,
            "volume": 2456000,
            "amount": 156000000,
            "avg_price": 63.52,
            "quote_time": "2026-03-23 09:35:51",
            "data_source": "realtime_sina",
        }
    }

    result = client.get_stock_quote_map(["002025.SZ", "002475.SZ"], "2026-03-23")

    assert client.pro.daily_calls == [(None, None, None, "20260320")]
    assert client.pro.daily_basic_calls == [(None, "20260320", "ts_code,turnover_rate,volume_ratio")]
    assert result["002025.SZ"]["close"] == 63.44
    assert result["002025.SZ"]["data_source"] == "realtime_sina"
    assert result["002475.SZ"]["close"] == 35.0


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

    def limit_list_d(self, trade_date=None, limit_type=None):
        return pd.DataFrame()


def test_get_expanded_stock_list_falls_back_to_recent_available_daily():
    """当天无 daily 个股数据时，应回退到最近有数据的交易日。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackStockListPro()
    client._resolve_trade_date = lambda d: "20260323"
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}

    payload = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)

    assert payload["data_trade_date"] == "20260320"
    assert payload["used_mock"] is False
    assert len(payload["rows"]) >= 1
    assert any(row["ts_code"] == "002475.SZ" for row in payload["rows"])


def test_get_expanded_stock_list_overlays_realtime_prices():
    """候选池应保留历史筛选口径，但价格展示优先盘中实时。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackStockListPro()
    client._resolve_trade_date = lambda d: "20260323"
    client._should_use_realtime_quote = lambda d: True
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}
    client._fetch_realtime_quote_map = lambda codes: {
        "002475.SZ": {
            "close": 36.12,
            "change_pct": 7.01,
            "open": 34.10,
            "high": 36.30,
            "low": 34.00,
            "pre_close": 33.75,
            "volume": 1860000,
            "amount": 67000000,
            "avg_price": 36.02,
            "quote_time": "2026-03-23 09:36:11",
            "data_source": "realtime_sina",
        }
    }

    payload = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)

    assert payload["data_trade_date"] == "20260320"
    target = next(row for row in payload["rows"] if row["ts_code"] == "002475.SZ")
    assert target["close"] == 36.12
    assert target["quote_time"] == "2026-03-23 09:36:11"
    assert target["data_source"] == "realtime_sina"


def test_get_expanded_stock_list_with_meta_uses_cache_for_same_request():
    """同一交易日同一参数的扩展候选池请求应命中缓存，避免重复查 daily/daily_basic/limit_list。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackStockListPro()
    client._resolve_trade_date = lambda d: "20260323"
    client._should_use_realtime_quote = lambda d: False
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}
    client._expanded_stock_list_cache = {}

    first = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)
    second = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)

    assert first["data_trade_date"] == "20260320"
    assert second["data_trade_date"] == "20260320"
    assert len(client.pro.daily_calls) == 2
    assert len(client.pro.daily_basic_calls) == 1
    assert len(client.pro.trade_cal_calls) == 1


def test_get_expanded_stock_list_with_meta_reuses_resolved_trade_date_cache():
    """非交易日请求回退后，应复用已缓存的实际交易日结果。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FallbackStockListPro()
    client._resolve_trade_date = lambda d: "20260323"
    client._should_use_realtime_quote = lambda d: False
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}
    client._expanded_stock_list_cache = {}

    from_non_trading_day = client.get_expanded_stock_list_with_meta("20260323", top_gainers=20)
    from_resolved_day = client.get_expanded_stock_list_with_meta("20260320", top_gainers=20)

    assert from_non_trading_day["data_trade_date"] == "20260320"
    assert from_resolved_day["data_trade_date"] == "20260320"
    assert len(client.pro.daily_basic_calls) == 1
    assert len(client.pro.trade_cal_calls) == 1


def test_get_stock_list_with_meta_uses_daily_and_daily_basic():
    """个股列表应改为 daily + daily_basic + stock_basic。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"
    client._recent_open_dates = lambda trade_date, count=5: ["20260320"]
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}
    client._stock_basic_snapshot_cache = {"fetched_at": 0.0, "mapping": {}}

    payload = client.get_stock_list_with_meta("20260320", limit=10)

    assert payload["data_trade_date"] == "20260320"
    assert payload["used_mock"] is False
    assert client.pro.daily_calls[-1][3] == "20260320"
    assert client.pro.daily_basic_calls[-1][1] == "20260320"
    assert client.pro.stock_basic_calls
    first = payload["rows"][0]
    assert first["stock_name"] in {"立讯精密", "航天电器"}
    assert first["sector_name"] in {"电子", "元器件"}


def test_get_concept_sectors_from_limitup_with_meta_prefers_ths_concepts():
    """limit_list_d 无 theme 字段时，应优先走 THS 题材链路恢复题材聚合。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client._resolve_trade_date = lambda d: "20260323"
    client._ths_concept_index_cache = {"fetched_at": 0.0, "mapping": {}}
    client._ths_member_by_stock_cache = {}

    class _ThsConceptPro:
        def limit_list_d(self, trade_date=None, limit_type=None):
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260323",
                        "ts_code": "000703.SZ",
                        "name": "恒逸石化",
                        "pct_chg": 10.04,
                        "amount": 715730592.0,
                    },
                    {
                        "trade_date": "20260323",
                        "ts_code": "001258.SZ",
                        "name": "立新能源",
                        "pct_chg": 10.05,
                        "amount": 903245120.0,
                    }
                ]
            )

        def ths_index(self, exchange=None, type=None):
            return pd.DataFrame(
                [
                    {"ts_code": "885531.TI", "name": "绿色电力", "type": "N"},
                    {"ts_code": "885555.TI", "name": "石化概念", "type": "N"},
                ]
            )

        def ths_member(self, ts_code=None, con_code=None):
            if con_code == "000703.SZ":
                return pd.DataFrame([{"ts_code": "885555.TI", "con_code": "000703.SZ", "is_new": "Y"}])
            if con_code == "001258.SZ":
                return pd.DataFrame([{"ts_code": "885531.TI", "con_code": "001258.SZ", "is_new": "Y"}])
            return pd.DataFrame()

        def ths_daily(self, ts_code=None, trade_date=None, start_date=None, end_date=None):
            return pd.DataFrame(
                [
                    {"ts_code": "885531.TI", "trade_date": "20260323", "pct_change": 3.26},
                    {"ts_code": "885555.TI", "trade_date": "20260323", "pct_change": 2.18},
                ]
            )

    client.pro = _ThsConceptPro()

    payload = client.get_concept_sectors_from_limitup_with_meta("20260323")

    assert payload["status"] == "ok"
    assert payload["data_trade_date"] == "20260323"
    assert payload["rows"][0]["sector_name"] == "绿色电力"
    assert payload["rows"][0]["sector_change_pct"] == 3.26


def test_get_concept_sectors_from_limitup_with_meta_falls_back_to_theme_when_ths_unavailable():
    """THS 题材链路不可用时，应回退到旧 theme 聚合。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client._resolve_trade_date = lambda d: "20260323"
    client._ths_concept_index_cache = {"fetched_at": 0.0, "mapping": {}}
    client._ths_member_by_stock_cache = {}

    class _ThemeFallbackPro:
        def limit_list_d(self, trade_date=None, limit_type=None):
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260323",
                        "ts_code": "000703.SZ",
                        "theme": "石化",
                        "name": "恒逸石化",
                        "pct_chg": 10.04,
                        "amount": 715730592.0,
                    },
                    {
                        "trade_date": "20260323",
                        "ts_code": "001258.SZ",
                        "theme": "绿色电力",
                        "name": "立新能源",
                        "pct_chg": 10.05,
                        "amount": 903245120.0,
                    },
                ]
            )

        def ths_index(self, exchange=None, type=None):
            raise RuntimeError("no ths permission")

    client.pro = _ThemeFallbackPro()

    payload = client.get_concept_sectors_from_limitup_with_meta("20260323")

    assert payload["status"] == "ok"
    assert payload["data_trade_date"] == "20260323"
    assert {row["sector_name"] for row in payload["rows"]} == {"石化", "绿色电力"}


def test_get_limitup_industry_sectors_with_meta_uses_industry_field():
    """theme 缺失时，应可按 limit_list_d.industry 聚合涨停行业。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client._resolve_trade_date = lambda d: "20260323"

    class _LimitUpIndustryPro:
        def limit_list_d(self, trade_date=None, limit_type=None):
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260323",
                        "ts_code": "000703.SZ",
                        "industry": "炼化及贸",
                        "name": "恒逸石化",
                        "pct_chg": 10.04,
                        "amount": 715730592.0,
                    },
                    {
                        "trade_date": "20260323",
                        "ts_code": "001258.SZ",
                        "industry": "电力",
                        "name": "立新能源",
                        "pct_chg": 10.05,
                        "amount": 903245120.0,
                    },
                    {
                        "trade_date": "20260323",
                        "ts_code": "002543.SZ",
                        "industry": "电力",
                        "name": "万和电气",
                        "pct_chg": 10.01,
                        "amount": 605000000.0,
                    },
                ]
            )

    client.pro = _LimitUpIndustryPro()

    payload = client.get_limitup_industry_sectors_with_meta("20260323")

    assert payload["status"] == "ok"
    assert payload["data_trade_date"] == "20260323"
    assert len(payload["rows"]) == 2
    power = next(row for row in payload["rows"] if row["sector_name"] == "电力")
    assert power["stock_count"] == 2


def test_get_sector_data_with_meta_uses_daily_and_stock_basic():
    """行业板块扫描应改为 daily + stock_basic 聚合。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260320"
    client._recent_open_dates = lambda trade_date, count=5: ["20260320"]
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}

    payload = client.get_sector_data_with_meta("20260320")

    assert payload["data_trade_date"] == "20260320"
    assert payload["used_mock"] is False
    assert client.pro.stock_basic_calls
    assert client.pro.daily_calls[-1][3] == "20260320"
    sectors = payload["rows"]
    assert len(sectors) == 2
    electronic = next(row for row in sectors if row["sector_name"] == "电子")
    assert electronic["stock_count"] == 1
    assert electronic["sector_change_pct"] == 6.5


def test_get_sector_data_with_meta_falls_back_to_recent_daily_trade_date():
    """当日 daily 无数据时，应回退到最近有数据的交易日。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260323"
    client._recent_open_dates = lambda trade_date, count=5: ["20260323", "20260320"]
    client._stock_basic_industry_cache = {"fetched_at": 0.0, "mapping": {}}

    payload = client.get_sector_data_with_meta("20260323")

    assert payload["data_trade_date"] == "20260320"
    assert len(payload["rows"]) == 2


def test_get_index_quote_with_meta_overlays_realtime_indexes():
    """指数接口在盘中应优先覆盖为实时行情。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._resolve_trade_date = lambda d: "20260323"
    client._recent_open_dates = lambda trade_date, count=5: ["20260320"]
    client._should_use_realtime_quote = lambda d: True
    client._fetch_realtime_quote_map = lambda codes: {
        "000001.SH": {
            "close": 3877.14,
            "change_pct": -2.02,
            "volume": 102353059,
            "amount": 136938090378,
            "trade_date": "20260323",
            "quote_time": "2026-03-23 09:35:50",
            "data_source": "realtime_sina",
        },
        "399001.SZ": {
            "close": 13559.04,
            "change_pct": -2.22,
            "volume": 12254472145,
            "amount": 194550361155.41,
            "trade_date": "20260323",
            "quote_time": "2026-03-23 09:35:48",
            "data_source": "realtime_sina",
        },
        "399006.SZ": {
            "close": 3294.22,
            "change_pct": -1.73,
            "volume": 3397634188,
            "amount": 90332019817.8,
            "trade_date": "20260323",
            "quote_time": "2026-03-23 09:35:48",
            "data_source": "realtime_sina",
        },
    }

    payload = client.get_index_quote_with_meta("20260323")

    assert payload["data_trade_date"] == "20260323"
    assert payload["rows"][0]["close"] == 3877.14
    assert payload["rows"][0]["data_source"] == "realtime_sina"


def test_get_market_turnover_with_meta_uses_realtime_snapshot():
    """交易时段应优先使用盘中市场快照计算成交额。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._fetch_realtime_market_snapshot = lambda trade_date: {
        "market_turnover": 3487.65,
        "up_down_ratio": {"up": 1200, "down": 3400, "flat": 80, "total": 4680},
        "data_trade_date": "20260323",
        "quote_time": "2026-03-23 09:58:00",
        "data_source": "realtime_dc",
    }

    payload = client.get_market_turnover_with_meta("20260323")

    assert payload["market_turnover"] == 3487.65
    assert payload["data_trade_date"] == "20260323"
    assert payload["quote_time"] == "2026-03-23 09:58:00"
    assert payload["data_source"] == "realtime_dc"


def test_get_up_down_ratio_with_meta_uses_realtime_snapshot():
    """交易时段应优先使用盘中市场快照计算涨跌家数。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._fetch_realtime_market_snapshot = lambda trade_date: {
        "market_turnover": 3487.65,
        "up_down_ratio": {"up": 1200, "down": 3400, "flat": 80, "total": 4680},
        "data_trade_date": "20260323",
        "quote_time": "2026-03-23 09:58:00",
        "data_source": "realtime_dc",
    }

    payload = client.get_up_down_ratio_with_meta("20260323")

    assert payload["up_down_ratio"]["up"] == 1200
    assert payload["up_down_ratio"]["down"] == 3400
    assert payload["quote_time"] == "2026-03-23 09:58:00"
    assert payload["data_source"] == "realtime_dc"


def test_get_limit_stats_with_meta_uses_realtime_snapshot():
    """交易时段应优先使用盘中快照近似涨跌停统计。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._fetch_realtime_market_snapshot = lambda trade_date: {
        "market_turnover": 3487.65,
        "up_down_ratio": {"up": 1200, "down": 3400, "flat": 80, "total": 4680},
        "limit_stats": {
            "limit_up_count": 36,
            "limit_down_count": 5,
            "broken_board_rate": 18.2,
            "estimated": True,
        },
        "data_trade_date": "20260323",
        "quote_time": "2026-03-23 09:58:00",
        "data_source": "realtime_dc",
    }

    payload = client.get_limit_stats_with_meta("20260323")

    assert payload["stats"]["limit_up_count"] == 36
    assert payload["stats"]["limit_down_count"] == 5
    assert payload["stats"]["broken_board_rate"] == 18.2
    assert payload["data_trade_date"] == "20260323"
    assert payload["data_source"] == "realtime_dc"


def test_get_up_down_ratio_with_meta_uses_daily_fallback():
    """非盘中场景应基于 daily.pct_chg 统计涨跌家数。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client.pro = _FakePro()
    client._fetch_realtime_market_snapshot = lambda trade_date: None
    client._resolve_trade_date = lambda d: "20260323"
    client._recent_open_dates = lambda trade_date, count=5: ["20260323", "20260320"]

    payload = client.get_up_down_ratio_with_meta("20260323")

    assert payload["data_trade_date"] == "20260320"
    assert payload["data_source"] == "daily"
    assert payload["up_down_ratio"] == {"up": 2, "down": 0, "flat": 0, "total": 2}


def test_fetch_realtime_market_snapshot_formats_sina_time():
    """新浪实时列表若样本不足，不应被当成全市场快照使用。"""
    client = TushareClient.__new__(TushareClient)
    client.token = "test-token"
    client._realtime_market_cache = {"trade_date": "", "fetched_at": 0.0, "snapshot": None}
    client._should_use_realtime_quote = lambda d: True
    client._now_sh = lambda: __import__("datetime").datetime(2026, 3, 23, 10, 7, 5)

    import tushare as ts

    original = ts.realtime_list
    try:
        ts.realtime_list = lambda src=None, page_count=None: pd.DataFrame(
            [
                {
                    "TS_CODE": "000001.SZ",
                    "PCT_CHANGE": 1.23,
                    "AMOUNT": 100000000.0,
                    "TIME": "10:07:00",
                },
                {
                    "TS_CODE": "000002.SZ",
                    "PCT_CHANGE": -0.56,
                    "AMOUNT": 200000000.0,
                    "TIME": "10:07:00",
                },
            ]
        ) if src == "sina" else (_ for _ in ()).throw(ConnectionError("dc down"))

        snapshot = client._fetch_realtime_market_snapshot("20260323")
    finally:
        ts.realtime_list = original

    assert snapshot is None


def test_estimate_realtime_limit_stats_handles_multi_board_rules():
    """实时涨跌停近似统计应兼容主板/创业板/北交所和炸板识别。"""
    client = TushareClient.__new__(TushareClient)

    df = pd.DataFrame(
        [
            {
                "TS_CODE": "600001.SH",
                "NAME": "测试主板",
                "PRICE": 11.0,
                "PCT_CHANGE": 10.0,
                "HIGH": 11.0,
                "LOW": 10.02,
                "OPEN": 10.05,
                "CLOSE": 10.0,
            },
            {
                "TS_CODE": "300001.SZ",
                "NAME": "测试创业板",
                "PRICE": 11.5,
                "PCT_CHANGE": 15.0,
                "HIGH": 12.0,
                "LOW": 10.1,
                "OPEN": 10.3,
                "CLOSE": 10.0,
            },
            {
                "TS_CODE": "830001.BJ",
                "NAME": "测试北交",
                "PRICE": 7.0,
                "PCT_CHANGE": -30.0,
                "HIGH": 9.2,
                "LOW": 7.0,
                "OPEN": 9.8,
                "CLOSE": 10.0,
            },
            {
                "TS_CODE": "600002.SH",
                "NAME": "ST测试",
                "PRICE": 10.5,
                "PCT_CHANGE": 5.0,
                "HIGH": 10.5,
                "LOW": 10.01,
                "OPEN": 10.02,
                "CLOSE": 10.0,
            },
        ]
    )

    stats = client._estimate_realtime_limit_stats(df)

    assert stats["limit_up_count"] == 2
    assert stats["limit_down_count"] == 1
    assert stats["touched_limit_up_count"] == 3
    assert stats["broken_board_count"] == 1
    assert stats["broken_board_rate"] == 33.3
