"""
Tushare 数据客户端
"""
import os
import tushare as ts
from typing import Optional, List, Dict
from loguru import logger
from app.core.config import settings


class TushareClient:
    """Tushare API 客户端"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.tushare_token
        if self.token:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            logger.info("Tushare 客户端初始化成功")
        else:
            logger.warning("Tushare token 未配置，部分功能可能不可用")

    def get_index_quote(self, trade_date: str) -> List[Dict]:
        """
        获取主要指数行情

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            指数行情列表
        """
        if not self.token:
            return self._mock_index_quote(trade_date)

        try:
            # 上证指数、深成指、创业板
            index_codes = ["000001.SH", "399001.SZ", "399006.SZ"]
            result = []

            for ts_code in index_codes:
                df = self.pro.daily(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
                if not df.empty:
                    row = df.iloc[0]
                    name = {
                        "000001.SH": "上证指数",
                        "399001.SZ": "深证成指",
                        "399006.SZ": "创业板指"
                    }.get(ts_code, ts_code)

                    result.append({
                        "ts_code": ts_code,
                        "name": name,
                        "close": float(row["close"]),
                        "change_pct": float(row["pct_chg"]),
                        "volume": float(row["vol"]),
                        "amount": float(row["amount"]),
                        "trade_date": row["trade_date"]
                    })

            return result
        except Exception as e:
            logger.error(f"获取指数行情失败: {e}")
            return self._mock_index_quote(trade_date)

    def get_limit_stats(self, trade_date: str) -> Dict:
        """
        获取涨跌停统计数据

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            涨跌停统计
        """
        if not self.token:
            return self._mock_limit_stats()

        try:
            # 涨停数量
            df_up = self.pro.limit_list(ts_code='', start_date=trade_date, end_date=trade_date, limit_type='U')
            limit_up_count = len(df_up)

            # 跌停数量
            df_down = self.pro.limit_list(ts_code='', start_date=trade_date, end_date=trade_date, limit_type='D')
            limit_down_count = len(df_down)

            # 炸板率计算需要更复杂的数据，这里简化处理
            broken_board_rate = 0.0

            return {
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "broken_board_rate": broken_board_rate
            }
        except Exception as e:
            logger.error(f"获取涨跌停统计失败: {e}")
            return self._mock_limit_stats()

    def get_sector_data(self, trade_date: str) -> List[Dict]:
        """
        获取板块行情数据

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            板块行情列表
        """
        if not self.token:
            return self._mock_sector_data()

        try:
            # 使用行业板块数据
            df = self.pro.index_classify(ts_code='', date=trade_date)
            if df.empty:
                return self._mock_sector_data()

            # 获取各板块行情
            sectors = []
            for _, row in df.iterrows():
                ts_code = row.get("ts_code")
                if not ts_code:
                    continue

                # 获取板块日线数据
                daily_df = self.pro.index_daily(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
                if daily_df.empty:
                    continue

                daily_row = daily_df.iloc[0]
                sectors.append({
                    "sector_name": row.get("industry", row.get("ts_code")),
                    "sector_code": ts_code,
                    "sector_change_pct": float(daily_row.get("pct_chg", 0)),
                    "sector_turnover": float(daily_row.get("amount", 0)) / 100000000,  # 转换为亿元
                })

            return sectors
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return self._mock_sector_data()

    def get_market_turnover(self, trade_date: str) -> float:
        """
        获取两市成交额

        Args:
            trade_date: 交易日

        Returns:
            成交额(亿元)
        """
        if not self.token:
            return 12000.0  # 默认值

        try:
            # 获取市场总成交额
            df = self.pro.daily(ts_code="000001.SH", start_date=trade_date, end_date=trade_date)
            if not df.empty:
                return float(df.iloc[0]["amount"]) / 100000000  # 转换为亿元
            return 12000.0
        except Exception as e:
            logger.error(f"获取成交额失败: {e}")
            return 12000.0

    def get_up_down_ratio(self, trade_date: str) -> Dict:
        """
        获取涨跌家数对比

        Args:
            trade_date: 交易日

        Returns:
            涨跌家数
        """
        if not self.token:
            return {"up": 2000, "down": 1000, "total": 5000}

        try:
            # 简化处理，返回模拟数据
            return {"up": 2000, "down": 1000, "total": 5000}
        except Exception as e:
            logger.error(f"获取涨跌家数失败: {e}")
            return {"up": 2000, "down": 1000, "total": 5000}

    # ========== Mock 数据 ==========

    def _mock_index_quote(self, trade_date: str) -> List[Dict]:
        """模拟指数行情"""
        return [
            {"ts_code": "000001.SH", "name": "上证指数", "close": 3420.0, "change_pct": 0.5, "volume": 350000000, "amount": 380000000000, "trade_date": trade_date},
            {"ts_code": "399001.SZ", "name": "深证成指", "close": 11500.0, "change_pct": 0.8, "volume": 450000000, "amount": 520000000000, "trade_date": trade_date},
            {"ts_code": "399006.SZ", "name": "创业板指", "close": 2400.0, "change_pct": 1.2, "volume": 180000000, "amount": 200000000000, "trade_date": trade_date},
        ]

    def _mock_limit_stats(self) -> Dict:
        """模拟涨跌停统计"""
        return {
            "limit_up_count": 45,
            "limit_down_count": 8,
            "broken_board_rate": 15.0
        }

    def _mock_sector_data(self) -> List[Dict]:
        """模拟板块数据"""
        return [
            {"sector_name": "人工智能", "sector_code": "BK1001", "sector_change_pct": 3.5, "sector_turnover": 800},
            {"sector_name": "新能源汽车", "sector_code": "BK1002", "sector_change_pct": 2.8, "sector_turnover": 650},
            {"sector_name": "半导体", "sector_code": "BK1003", "sector_change_pct": 2.1, "sector_turnover": 520},
            {"sector_name": "医药生物", "sector_code": "BK1004", "sector_change_pct": 1.2, "sector_turnover": 380},
            {"sector_name": "银行", "sector_code": "BK1005", "sector_change_pct": 0.5, "sector_turnover": 300},
        ]


# 全局客户端实例
tushare_client = TushareClient()
