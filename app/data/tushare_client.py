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


    def get_stock_list(self, trade_date: str, limit: int = 100) -> List[Dict]:
        """
        获取当日个股行情列表

        Args:
            trade_date: 交易日，格式 YYYYMMDD
            limit: 返回数量限制

        Returns:
            个股行情列表
        """
        if not self.token:
            return self._mock_stock_list()

        try:
            # 使用合法接口获取当日个股日线，再按涨跌幅排序截取
            df = self.pro.daily(trade_date=trade_date)
            if df.empty:
                return self._mock_stock_list()

            # 获取基础信息（名称、行业）
            basic_df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
            basic_map: Dict[str, Dict] = {}
            if not basic_df.empty:
                basic_map = {
                    row.get("ts_code"): {
                        "name": row.get("name", ""),
                        "industry": row.get("industry", "未知"),
                    }
                    for _, row in basic_df.iterrows()
                }

            # 获取当日换手率、量比等扩展指标（接口可能因权限不可用，失败时降级）
            daily_basic_map: Dict[str, Dict] = {}
            try:
                daily_basic_df = self.pro.daily_basic(
                    trade_date=trade_date,
                    fields="ts_code,turnover_rate,volume_ratio"
                )
                if not daily_basic_df.empty:
                    daily_basic_map = {
                        row.get("ts_code"): {
                            "turnover_rate": row.get("turnover_rate", 0),
                            "volume_ratio": row.get("volume_ratio", 1),
                        }
                        for _, row in daily_basic_df.iterrows()
                    }
            except Exception as basic_e:
                logger.warning(f"获取 daily_basic 失败，使用默认值: {basic_e}")

            # 按涨跌幅降序，保留前 N 条
            df = df.sort_values(by="pct_chg", ascending=False).head(limit)

            result = []
            for _, row in df.iterrows():
                ts_code = row.get("ts_code")
                stock_meta = basic_map.get(ts_code, {})
                daily_meta = daily_basic_map.get(ts_code, {})
                turnover_rate = daily_meta.get("turnover_rate", 0)
                volume_ratio = daily_meta.get("volume_ratio", 1)
                if turnover_rate is None or turnover_rate != turnover_rate:
                    turnover_rate = 0
                if volume_ratio is None or volume_ratio != volume_ratio:
                    volume_ratio = 1
                result.append({
                    "ts_code": ts_code,
                    "stock_name": stock_meta.get("name", ts_code),
                    "sector_name": stock_meta.get("industry", "未知"),
                    "close": float(row.get("close", 0)),
                    "change_pct": float(row.get("pct_chg", 0)),
                    "turnover_rate": float(turnover_rate),
                    "amount": float(row.get("amount", 0)),
                    "vol_ratio": float(volume_ratio),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "open": float(row.get("open", 0)),
                    "pre_close": float(row.get("pre_close", 0)),
                })

            return result
        except Exception as e:
            logger.error(f"获取个股列表失败: {e}")
            return self._mock_stock_list()

    def get_stock_detail(self, ts_code: str, trade_date: str) -> Dict:
        """
        获取个股详情

        Args:
            ts_code: 股票代码
            trade_date: 交易日

        Returns:
            个股详情
        """
        if not self.token:
            return self._mock_stock_detail(ts_code)

        try:
            # 获取股票基本信息（名称和行业）
            stock_info = self.pro.stock_basic(ts_code=ts_code)
            stock_name = ts_code
            industry = "未知"
            if not stock_info.empty:
                stock_name = stock_info.iloc[0].get("name", ts_code)
                industry = stock_info.iloc[0].get("industry", "未知")

            # 获取日线数据
            df = self.pro.daily(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
            if df.empty:
                return self._mock_stock_detail(ts_code)

            row = df.iloc[0]

            return {
                "ts_code": ts_code,
                "stock_name": stock_name,
                "sector_name": industry,
                "close": float(row.get("close", 0)),
                "change_pct": float(row.get("pct_chg", 0)),
                "turnover_rate": float(row.get("vol", 0)) / 10000,  # 简化
                "amount": float(row.get("amount", 0)),
                "vol_ratio": 1.5,  # 简化
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "open": float(row.get("open", 0)),
                "pre_close": float(row.get("pre_close", 0)),
            }
        except Exception as e:
            logger.error(f"获取个股详情失败: {e}")
            return self._mock_stock_detail(ts_code)

    # ========== Mock 数据 ==========

    def _mock_stock_list(self) -> List[Dict]:
        """模拟个股列表"""
        return [
            {"ts_code": "000001.SZ", "stock_name": "平安银行", "sector_name": "银行", "close": 12.5, "change_pct": 3.5, "turnover_rate": 8.5, "amount": 350000, "vol_ratio": 1.8, "high": 12.8, "low": 12.1, "open": 12.2, "pre_close": 12.1},
            {"ts_code": "000002.SZ", "stock_name": "万 科A", "sector_name": "房地产", "close": 8.2, "change_pct": 5.2, "turnover_rate": 15.0, "amount": 520000, "vol_ratio": 2.5, "high": 8.5, "low": 7.9, "open": 7.9, "pre_close": 7.8},
            {"ts_code": "600036.SH", "stock_name": "招商银行", "sector_name": "银行", "close": 35.0, "change_pct": 2.0, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.5, "high": 35.5, "low": 34.2, "open": 34.3, "pre_close": 34.3},
            {"ts_code": "600519.SH", "stock_name": "贵州茅台", "sector_name": "白酒", "close": 1850.0, "change_pct": 1.2, "turnover_rate": 0.8, "amount": 450000, "vol_ratio": 1.2, "high": 1860.0, "low": 1820.0, "open": 1825.0, "pre_close": 1828.0},
            {"ts_code": "300750.SZ", "stock_name": "宁德时代", "sector_name": "新能源汽车", "close": 185.0, "change_pct": 4.5, "turnover_rate": 12.0, "amount": 680000, "vol_ratio": 2.2, "high": 188.0, "low": 178.0, "open": 178.0, "pre_close": 177.0},
            {"ts_code": "002594.SZ", "stock_name": "比亚迪", "sector_name": "新能源汽车", "close": 265.0, "change_pct": 3.8, "turnover_rate": 6.5, "amount": 420000, "vol_ratio": 1.6, "high": 268.0, "low": 258.0, "open": 258.0, "pre_close": 255.0},
            {"ts_code": "000858.SZ", "stock_name": "五粮液", "sector_name": "白酒", "close": 168.0, "change_pct": 2.1, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.3, "high": 170.0, "low": 165.0, "open": 165.0, "pre_close": 164.5},
            {"ts_code": "600900.SH", "stock_name": "长江电力", "sector_name": "电力", "close": 23.5, "change_pct": 0.5, "turnover_rate": 1.2, "amount": 150000, "vol_ratio": 1.0, "high": 23.8, "low": 23.2, "open": 23.3, "pre_close": 23.4},
            {"ts_code": "601318.SH", "stock_name": "中国平安", "sector_name": "保险", "close": 48.5, "change_pct": 1.8, "turnover_rate": 2.5, "amount": 320000, "vol_ratio": 1.4, "high": 49.0, "low": 47.8, "open": 47.8, "pre_close": 47.6},
            {"ts_code": "000333.SZ", "stock_name": "美的集团", "sector_name": "家电", "close": 62.0, "change_pct": 2.5, "turnover_rate": 4.0, "amount": 250000, "vol_ratio": 1.5, "high": 63.0, "low": 61.0, "open": 61.0, "pre_close": 60.5},
            {"ts_code": "002475.SZ", "stock_name": "立讯精密", "sector_name": "电子", "close": 35.0, "change_pct": 6.5, "turnover_rate": 18.0, "amount": 580000, "vol_ratio": 3.0, "high": 36.0, "low": 33.5, "open": 33.5, "pre_close": 32.8},
        ]

    def _mock_stock_detail(self, ts_code: str) -> Dict:
        """模拟个股详情"""
        # 先尝试从 Tushare 获取
        try:
            stock_info = self.pro.stock_basic(ts_code=ts_code)
            if not stock_info.empty:
                stock_name = stock_info.iloc[0].get("name", ts_code)
                industry = stock_info.iloc[0].get("industry", "未知")
                return {
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "sector_name": industry,
                    "close": 0.0,
                    "change_pct": 0.0,
                    "turnover_rate": 0.0,
                    "amount": 0,
                    "vol_ratio": 1.0,
                    "high": 0.0,
                    "low": 0.0,
                    "open": 0.0,
                    "pre_close": 0.0,
                }
        except:
            pass
        
        # Tushare 不可用时，返回包含代码的默认数据（不再返回其他股票的数据）
        return {
            "ts_code": ts_code,
            "stock_name": ts_code,
            "sector_name": "未知",
            "close": 0.0,
            "change_pct": 0.0,
            "turnover_rate": 0.0,
            "amount": 0,
            "vol_ratio": 1.0,
            "high": 0.0,
            "low": 0.0,
            "open": 0.0,
            "pre_close": 0.0,
        }


# 全局客户端实例
tushare_client = TushareClient()
