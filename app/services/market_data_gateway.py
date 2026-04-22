"""
市场数据网关
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.data.tushare_client import normalize_ts_code, tushare_client


class MarketDataGateway:
    """统一封装 Tushare 行情读取入口，隔离服务层对底层客户端的直接依赖。"""

    def normalize_ts_code(self, ts_code: str) -> str:
        return normalize_ts_code(ts_code)

    def now_trade_date(self) -> str:
        return tushare_client._now_sh().strftime("%Y-%m-%d")

    def resolve_trade_date(self, trade_date: str) -> str:
        return tushare_client._resolve_trade_date(str(trade_date).replace("-", ""))

    def _resolve_trade_date(self, trade_date: str) -> str:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.resolve_trade_date(trade_date)

    def recent_open_dates(self, trade_date: str, count: int = 2) -> List[str]:
        compact = str(trade_date).replace("-", "")
        return tushare_client._recent_open_dates(compact, count=count)

    def _recent_open_dates(self, trade_date: str, count: int = 2) -> List[str]:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.recent_open_dates(trade_date, count=count)

    def get_last_completed_trade_date(self, trade_date: str) -> str:
        return tushare_client.get_last_completed_trade_date(trade_date)

    def get_future_trade_dates(self, trade_date: str, count: int = 5) -> List[str]:
        return tushare_client.get_future_trade_dates(trade_date, count=count)

    def get_stock_detail(self, ts_code: str, trade_date: str) -> Dict:
        return tushare_client.get_stock_detail(ts_code, str(trade_date).replace("-", ""))

    def get_stock_quote_map(self, ts_codes: List[str], trade_date: str) -> Dict[str, Dict]:
        return tushare_client.get_stock_quote_map(ts_codes, str(trade_date).replace("-", ""))

    def get_expanded_stock_list_with_meta(
        self,
        trade_date: str,
        *,
        top_gainers: int,
        prefer_today: bool = False,
    ) -> Dict:
        return tushare_client.get_expanded_stock_list_with_meta(
            str(trade_date).replace("-", ""),
            top_gainers=top_gainers,
            prefer_today=prefer_today,
        )

    def get_index_quote(self, trade_date: str) -> List[Dict]:
        return tushare_client.get_index_quote(str(trade_date).replace("-", ""))

    def get_index_quote_with_meta(self, trade_date: str) -> Dict:
        return tushare_client.get_index_quote_with_meta(str(trade_date).replace("-", ""))

    def get_limit_stats_with_meta(self, trade_date: str) -> Dict:
        return tushare_client.get_limit_stats_with_meta(str(trade_date).replace("-", ""))

    def get_market_turnover_with_meta(self, trade_date: str) -> Dict:
        return tushare_client.get_market_turnover_with_meta(str(trade_date).replace("-", ""))

    def get_up_down_ratio_with_meta(self, trade_date: str) -> Dict:
        return tushare_client.get_up_down_ratio_with_meta(str(trade_date).replace("-", ""))

    def get_sector_data(self, trade_date: str) -> List[Dict]:
        return tushare_client.get_sector_data(str(trade_date).replace("-", ""))

    def get_sector_data_with_meta(self, trade_date: str, *, prefer_today: bool = False) -> Dict:
        return tushare_client.get_sector_data_with_meta(
            str(trade_date).replace("-", ""),
            prefer_today=prefer_today,
        )

    def get_concept_sectors_from_limitup_with_meta(self, trade_date: str, *, prefer_today: bool = False) -> Dict:
        return tushare_client.get_concept_sectors_from_limitup_with_meta(
            str(trade_date).replace("-", ""),
            prefer_today=prefer_today,
        )

    def get_concept_sectors_from_limitup(self, trade_date: str) -> List[Dict]:
        payload = self.get_concept_sectors_from_limitup_with_meta(trade_date)
        return payload.get("rows") or []

    def get_limitup_industry_sectors_with_meta(self, trade_date: str, *, prefer_today: bool = False) -> Dict:
        return tushare_client.get_limitup_industry_sectors_with_meta(
            str(trade_date).replace("-", ""),
            prefer_today=prefer_today,
        )

    def get_sina_hot_sector_boards(
        self,
        trade_date: str,
        *,
        limit: int = 5,
        refresh: bool = False,
    ) -> Dict:
        return tushare_client.get_sina_hot_sector_boards(
            str(trade_date).replace("-", ""),
            limit=limit,
            refresh=refresh,
        )

    def should_use_realtime_quote(self, trade_date: str) -> bool:
        return tushare_client._should_use_realtime_quote(trade_date)

    def should_use_market_snapshot(self, trade_date: str) -> bool:
        return tushare_client._should_use_market_snapshot(trade_date)

    def _should_use_realtime_quote(self, trade_date: str) -> bool:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.should_use_realtime_quote(trade_date)

    def _should_use_market_snapshot(self, trade_date: str) -> bool:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.should_use_market_snapshot(trade_date)

    def fetch_realtime_quote_map(self, ts_codes: List[str]) -> Dict[str, Dict]:
        return tushare_client._fetch_realtime_quote_map(ts_codes)

    def _fetch_realtime_quote_map(self, ts_codes: List[str]) -> Dict[str, Dict]:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.fetch_realtime_quote_map(ts_codes)

    def fetch_recent_stock_daily_df(self, trade_date: str) -> Dict:
        return tushare_client._fetch_recent_stock_daily_df(str(trade_date).replace("-", ""))

    def _fetch_recent_stock_daily_df(self, trade_date: str) -> Dict:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.fetch_recent_stock_daily_df(trade_date)

    def get_stock_basic_snapshot_map(self) -> Dict:
        return tushare_client._get_stock_basic_snapshot_map()

    def _get_stock_basic_snapshot_map(self) -> Dict:
        """兼容旧服务与测试直接访问私有方法。"""
        return self.get_stock_basic_snapshot_map()

    def build_daily_stock_source_df(
        self,
        df,
        stock_meta_map,
        *,
        daily_basic_df=None,
    ):
        return tushare_client._build_daily_stock_source_df(
            df,
            stock_meta_map,
            daily_basic_df=daily_basic_df,
        )

    def _build_daily_stock_source_df(
        self,
        df,
        stock_meta_map,
        *,
        daily_basic_df=None,
    ):
        """兼容旧服务与测试直接访问私有方法。"""
        return self.build_daily_stock_source_df(
            df,
            stock_meta_map,
            daily_basic_df=daily_basic_df,
        )

    def get_daily_basic_df(
        self,
        *,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        fields: Optional[str] = None,
    ):
        return tushare_client._cached_pro_daily_basic(
            ts_code=normalize_ts_code(ts_code) if ts_code else None,
            trade_date=str(trade_date).replace("-", "") if trade_date else None,
            fields=fields,
        )

    @property
    def pro(self):
        return getattr(tushare_client, "pro", None)

    @property
    def token(self) -> str:
        return getattr(tushare_client, "token", "")


market_data_gateway = MarketDataGateway()
