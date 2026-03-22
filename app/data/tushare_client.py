"""
Tushare 数据客户端
"""
import os
import tushare as ts
from typing import Optional, List, Dict
from loguru import logger
from app.core.config import settings


def normalize_ts_code(ts_code: str) -> str:
    """
    将 6 位数字或带交易所后缀的代码规范为 Tushare 所需的 ts_code。
    未带后缀时：6 开头 -> .SH；43/83/87/88 开头 -> .BJ；其余 -> .SZ。
    """
    ts_code = ts_code.strip().upper()
    if not ts_code:
        return ts_code
    if ts_code.endswith((".SH", ".SZ", ".BJ")):
        return ts_code
    if len(ts_code) == 6 and ts_code.isdigit():
        if ts_code.startswith("6"):
            return f"{ts_code}.SH"
        if ts_code.startswith(("43", "83", "87", "88")):
            return f"{ts_code}.BJ"
        return f"{ts_code}.SZ"
    return ts_code


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

    def _resolve_trade_date(self, trade_date: str) -> str:
        """
        将输入日期解析为最近一个开市日（含当天）。
        通过查询前 14 天日历，找到最近一个 is_open=1 的日期，
        避免依赖 pretrade_date（高级权限字段）。
        """
        if not self.token:
            return trade_date

        try:
            from datetime import datetime, timedelta
            end_dt = datetime.strptime(trade_date, "%Y%m%d")
            start_dt = end_dt - timedelta(days=14)
            cal_df = self.pro.trade_cal(
                exchange="SSE",
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=trade_date,
                fields="cal_date,is_open"
            )
            if not cal_df.empty:
                open_days = cal_df[cal_df["is_open"] == 1]["cal_date"]
                if not open_days.empty:
                    # Tushare 返回降序（最新在前），取 iloc[0] 拿最近开市日
                    resolved = str(open_days.iloc[0])
                    if resolved != trade_date:
                        logger.info(
                            f"非交易日 {trade_date}，回退到最近交易日 {resolved}"
                        )
                    return resolved
        except Exception as e:
            logger.warning(
                f"解析交易日失败，使用原始日期 {trade_date}: {e}"
            )

        return trade_date

    def get_next_trade_date(self, trade_date: str) -> str:
        """
        获取指定日期之后最近一个开市日。
        无 token 时退化为原日期后一天。
        """
        if not self.token:
            from datetime import datetime, timedelta
            dt = datetime.strptime(trade_date, "%Y%m%d") + timedelta(days=1)
            return dt.strftime("%Y%m%d")

        try:
            from datetime import datetime, timedelta

            start_dt = datetime.strptime(trade_date, "%Y%m%d") + timedelta(days=1)
            end_dt = start_dt + timedelta(days=14)
            cal_df = self.pro.trade_cal(
                exchange="SSE",
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
                fields="cal_date,is_open",
            )
            if not cal_df.empty:
                open_days = cal_df[cal_df["is_open"] == 1]["cal_date"]
                if not open_days.empty:
                    return str(open_days.iloc[-1] if False else open_days.iloc[0])
        except Exception as e:
            logger.warning(f"获取下一交易日失败，退回自然日: {e}")

        from datetime import datetime, timedelta
        dt = datetime.strptime(trade_date, "%Y%m%d") + timedelta(days=1)
        return dt.strftime("%Y%m%d")

    def get_future_trade_dates(self, trade_date: str, count: int = 5) -> List[str]:
        """
        获取指定日期之后未来若干个开市日。
        无 token 时退化为连续自然日。
        """
        if count <= 0:
            return []

        if not self.token:
            from datetime import datetime, timedelta
            start = datetime.strptime(trade_date, "%Y%m%d")
            return [
                (start + timedelta(days=i)).strftime("%Y%m%d")
                for i in range(1, count + 1)
            ]

        try:
            from datetime import datetime, timedelta

            start_dt = datetime.strptime(trade_date, "%Y%m%d") + timedelta(days=1)
            end_dt = start_dt + timedelta(days=20)
            cal_df = self.pro.trade_cal(
                exchange="SSE",
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
                fields="cal_date,is_open",
            )
            if not cal_df.empty:
                open_days = cal_df[cal_df["is_open"] == 1]["cal_date"].tolist()
                return [str(d) for d in open_days[:count]]
        except Exception as e:
            logger.warning(f"获取未来交易日失败，退回自然日: {e}")

        from datetime import datetime, timedelta
        start = datetime.strptime(trade_date, "%Y%m%d")
        return [
            (start + timedelta(days=i)).strftime("%Y%m%d")
            for i in range(1, count + 1)
        ]

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
            effective_trade_date = self._resolve_trade_date(trade_date)
            # 上证指数、深成指、创业板
            index_codes = ["000001.SH", "399001.SZ", "399006.SZ"]
            result = []

            for ts_code in index_codes:
                df = self.pro.index_daily(
                    ts_code=ts_code,
                    start_date=effective_trade_date,
                    end_date=effective_trade_date
                )
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

            if not result:
                logger.warning(
                    f"指数行情无数据（{effective_trade_date}），使用模拟数据"
                )
                return self._mock_index_quote(trade_date)
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
            effective_trade_date = self._resolve_trade_date(trade_date)
            # Tushare v1.4+ 改名为 limit_list_d，旧 limit_list 接口已不返回数据
            df_up = self.pro.limit_list_d(
                trade_date=effective_trade_date,
                limit_type='U',
            )
            df_down = self.pro.limit_list_d(
                trade_date=effective_trade_date,
                limit_type='D',
            )
            limit_up_count = len(df_up) if df_up is not None else 0
            limit_down_count = len(df_down) if df_down is not None else 0

            # 炸板率：open_times > 0 表示当天曾打开过（炸板），占涨停总数的比例
            broken_board_rate = 0.0
            if (
                limit_up_count > 0
                and df_up is not None
                and "open_times" in df_up.columns
            ):
                broken = len(df_up[df_up["open_times"] > 0])
                broken_board_rate = round(broken / limit_up_count * 100, 1)

            if limit_up_count == 0 and limit_down_count == 0:
                logger.warning(
                    f"涨跌停列表为空（{effective_trade_date}），"
                    "请确认 Tushare 权限与交易日是否正确"
                )

            return {
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "broken_board_rate": broken_board_rate,
            }
        except Exception as e:
            logger.error(f"获取涨跌停统计失败: {e}")
            return {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "broken_board_rate": 0.0,
            }

    def get_sector_data(self, trade_date: str) -> List[Dict]:
        """
        获取板块行情数据（按 bak_daily 行业字段聚合，覆盖全市场5000+股票）

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            板块行情列表（按平均涨跌幅降序）
        """
        if not self.token:
            return self._mock_sector_data()

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            df = self.pro.bak_daily(
                trade_date=effective_trade_date,
                fields="ts_code,industry,pct_change,amount"
            )
            if df is None or df.empty:
                logger.warning(f"bak_daily 板块数据为空（{effective_trade_date}）")
                return self._mock_sector_data()

            df["pct_change"] = df["pct_change"].fillna(0)
            df["amount"] = df["amount"].fillna(0)
            df = df[df["industry"].notna() & (df["industry"] != "")]

            grouped = (
                df.groupby("industry")
                .agg(
                    sector_change_pct=("pct_change", "mean"),
                    sector_turnover=("amount", "sum"),
                    stock_count=("ts_code", "count"),
                )
                .reset_index()
                .sort_values("sector_change_pct", ascending=False)
            )

            sectors = []
            for _, row in grouped.iterrows():
                sectors.append({
                    "sector_name": str(row["industry"]),
                    "sector_code": "",
                    "sector_change_pct": round(float(row["sector_change_pct"]), 2),
                    # amount 单位万元 → 亿元
                    "sector_turnover": round(float(row["sector_turnover"]) / 10000, 2),
                    "stock_count": int(row["stock_count"]),
                })

            logger.info(
                f"板块数据（{effective_trade_date}）: {len(sectors)} 个行业"
            )
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
            effective_trade_date = self._resolve_trade_date(trade_date)
            # 用指数日线接口获取上证+深成指成交额（amount 为千元，/100000 → 亿元）
            sh_df = self.pro.index_daily(
                ts_code="000001.SH",
                start_date=effective_trade_date,
                end_date=effective_trade_date
            )
            sz_df = self.pro.index_daily(
                ts_code="399001.SZ",
                start_date=effective_trade_date,
                end_date=effective_trade_date
            )
            total = 0.0
            if not sh_df.empty:
                total += float(sh_df.iloc[0]["amount"])
            if not sz_df.empty:
                total += float(sz_df.iloc[0]["amount"])
            if total > 0:
                return total / 100000  # 千元 → 亿元
            return 12000.0
        except Exception as e:
            logger.error(f"获取成交额失败: {e}")
            return 12000.0

    def get_up_down_ratio(self, trade_date: str) -> Dict:
        """
        获取涨跌家数对比（基于 bak_daily 的 pct_change 字段）

        Args:
            trade_date: 交易日

        Returns:
            涨跌家数 {"up": int, "down": int, "flat": int, "total": int}
        """
        if not self.token:
            return {"up": 0, "down": 0, "flat": 0, "total": 0}

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            df = self.pro.bak_daily(
                trade_date=effective_trade_date,
                fields="ts_code,pct_change"
            )
            if df is None or df.empty:
                logger.warning(f"bak_daily 无数据（{effective_trade_date}）")
                return {"up": 0, "down": 0, "flat": 0, "total": 0}

            df["pct_change"] = df["pct_change"].fillna(0)
            up = int((df["pct_change"] > 0).sum())
            down = int((df["pct_change"] < 0).sum())
            flat = int((df["pct_change"] == 0).sum())
            total = len(df)
            logger.info(f"涨跌家数（{effective_trade_date}）: 涨{up} 跌{down} 平{flat}")
            return {"up": up, "down": down, "flat": flat, "total": total}
        except Exception as e:
            logger.error(f"获取涨跌家数失败: {e}")
            return {"up": 0, "down": 0, "flat": 0, "total": 0}

    def get_concept_sectors_from_limitup(self, trade_date: str) -> List[Dict]:
        """
        按涨停板 limit_list_d 的 theme 字段聚合题材概念板块（与 get_sector_data 返回结构一致）。

        无 token 或接口无 theme 列时返回空列表，由行业板块补充。
        """
        if not self.token:
            return []

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            df = self.pro.limit_list_d(
                trade_date=effective_trade_date,
                limit_type="U",
            )
            if df is None or df.empty:
                return []
            if "theme" not in df.columns:
                logger.warning(
                    f"limit_list_d 无 theme 列（{effective_trade_date}），题材板块为空"
                )
                return []

            work = df.copy()
            work["_theme"] = (
                work["theme"].fillna("").astype(str).str.strip()
            )
            work.loc[work["_theme"] == "", "_theme"] = "其他题材"

            pct_col = "pct_chg" if "pct_chg" in work.columns else None
            if not pct_col:
                return []

            work[pct_col] = work[pct_col].fillna(0)

            if "amount" in work.columns:
                grouped = (
                    work.groupby("_theme", as_index=False)
                    .agg(
                        sector_change_pct=(pct_col, "mean"),
                        stock_count=("ts_code", "count"),
                        _amt_sum=("amount", "sum"),
                    )
                )
                grouped["sector_turnover"] = grouped["_amt_sum"].fillna(0) / 10000
                grouped = grouped.drop(columns=["_amt_sum"])
            else:
                grouped = (
                    work.groupby("_theme", as_index=False)
                    .agg(
                        sector_change_pct=(pct_col, "mean"),
                        stock_count=("ts_code", "count"),
                    )
                )
                grouped["sector_turnover"] = 0.0

            grouped = grouped.sort_values("stock_count", ascending=False)

            sectors: List[Dict] = []
            for _, row in grouped.iterrows():
                sectors.append({
                    "sector_name": str(row["_theme"]),
                    "sector_code": "",
                    "sector_change_pct": round(float(row["sector_change_pct"]), 2),
                    "sector_turnover": round(float(row["sector_turnover"]), 2),
                    "stock_count": int(row["stock_count"]),
                })

            logger.info(
                f"题材板块（{effective_trade_date}，涨停聚合）: {len(sectors)} 个"
            )
            return sectors
        except Exception as e:
            logger.error(f"获取题材概念板块失败: {e}")
            return []

    def _bak_row_to_stock_dict(
        self,
        row,
        sector_name: Optional[str] = None,
        candidate_source_tag: str = "",
    ) -> Dict:
        """将 bak_daily 一行转为个股行情 dict。"""
        ind = row.get("industry", "未知")
        if sector_name is not None:
            sn = sector_name
        else:
            sn = str(ind) if ind is not None and str(ind).strip() else "未知"
        return {
            "ts_code": str(row["ts_code"]),
            "stock_name": str(row.get("name", row["ts_code"])),
            "sector_name": sn,
            "close": float(row.get("close") or 0),
            "change_pct": float(row.get("pct_change") or 0),
            "turnover_rate": float(row.get("turn_over") or 0),
            "amount": float(row.get("amount") or 0),
            "vol_ratio": float(row.get("vol_ratio") or 1),
            "high": float(row.get("high") or 0),
            "low": float(row.get("low") or 0),
            "open": float(row.get("open") or 0),
            "pre_close": float(row.get("pre_close") or 0),
            "candidate_source_tag": candidate_source_tag,
        }

    def _limit_up_row_to_stock_dict(self, lr, candidate_source_tag: str = "涨停入选") -> Dict:
        """涨停榜行转个股行情（bak_daily 缺省时兜底）。"""
        tc = str(lr.get("ts_code", "")).strip()
        theme = lr.get("theme")
        theme_s = (
            str(theme).strip() if theme is not None and str(theme).strip() else "其他题材"
        )
        pct = float(lr.get("pct_chg") or lr.get("pct_change") or 0)
        tr = lr.get("turnover_ratio")
        turnover_rate = float(tr) if tr is not None else 0.0
        return {
            "ts_code": tc,
            "stock_name": str(lr.get("name", tc) or tc),
            "sector_name": theme_s,
            "close": float(lr.get("close") or 0),
            "change_pct": pct,
            "turnover_rate": turnover_rate,
            "amount": float(lr.get("amount") or lr.get("fd_amount") or 0),
            "vol_ratio": 1.0,
            "high": float(lr.get("high") or lr.get("close") or 0),
            "low": float(lr.get("low") or lr.get("close") or 0),
            "open": float(lr.get("open") or lr.get("close") or 0),
            "pre_close": float(lr.get("pre_close") or 0),
            "candidate_source_tag": candidate_source_tag,
        }

    def _append_candidate_source(self, record: Dict, source_tag: str) -> Dict:
        """追加候选来源标签并去重。"""
        if not source_tag:
            return record
        current = str(record.get("candidate_source_tag") or "").strip()
        parts = [p for p in current.split("/") if p]
        if source_tag not in parts:
            parts.append(source_tag)
        record["candidate_source_tag"] = "/".join(parts)
        return record

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
        获取当日个股行情列表（基于 bak_daily，一次调用包含名称/行业/涨跌幅/换手率/量比）

        Args:
            trade_date: 交易日，格式 YYYYMMDD
            limit: 按涨跌幅降序截取数量

        Returns:
            个股行情列表
        """
        if not self.token:
            return self._mock_stock_list()

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            df = self.pro.bak_daily(
                trade_date=effective_trade_date,
                fields=(
                    "ts_code,name,industry,pct_change,close,open,high,low,"
                    "pre_close,vol,amount,turn_over,vol_ratio"
                ),
            )
            if df is None or df.empty:
                logger.warning(f"bak_daily 个股数据为空（{effective_trade_date}）")
                return self._mock_stock_list()

            # 清洗
            df["pct_change"] = df["pct_change"].fillna(0)
            df["turn_over"] = df["turn_over"].fillna(0)
            df["vol_ratio"] = df["vol_ratio"].fillna(1)

            # 按涨跌幅降序，截取前 limit 条
            df = df.sort_values("pct_change", ascending=False).head(limit)

            result = []
            for _, row in df.iterrows():
                result.append({
                    "ts_code": str(row["ts_code"]),
                    "stock_name": str(row.get("name", row["ts_code"])),
                    "sector_name": str(row.get("industry", "未知")) or "未知",
                    "close": float(row.get("close") or 0),
                    "change_pct": float(row.get("pct_change") or 0),
                    "turnover_rate": float(row.get("turn_over") or 0),
                    "amount": float(row.get("amount") or 0),
                    "vol_ratio": float(row.get("vol_ratio") or 1),
                    "high": float(row.get("high") or 0),
                    "low": float(row.get("low") or 0),
                    "open": float(row.get("open") or 0),
                    "pre_close": float(row.get("pre_close") or 0),
                })

            logger.info(
                f"个股列表（{effective_trade_date}）: 共 {len(result)} 只"
            )
            return result
        except Exception as e:
            logger.error(f"获取个股列表失败: {e}")
            return self._mock_stock_list()

    def get_expanded_stock_list(
        self,
        trade_date: str,
        top_gainers: int = 100,
        vol_ratio_min: float = 2.5,
        pct_floor: float = -5.0,
    ) -> List[Dict]:
        """
        扩展候选池：合并三源后按 ts_code 去重。
        - A: bak_daily 涨幅前 top_gainers
        - B: 当日全部涨停股（sector_name 用 limit_list_d.theme）
        - C: 量比异动 vol_ratio >= vol_ratio_min 且 pct_change > pct_floor

        无 token 时回退为 _mock_stock_list。
        """
        if not self.token:
            return self._mock_stock_list()

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            df = self.pro.bak_daily(
                trade_date=effective_trade_date,
                fields=(
                    "ts_code,name,industry,pct_change,close,open,high,low,"
                    "pre_close,vol,amount,turn_over,vol_ratio"
                ),
            )
            if df is None or df.empty:
                logger.warning(
                    f"bak_daily 个股数据为空（{effective_trade_date}），"
                    "扩展候选池回退 mock"
                )
                return self._mock_stock_list()

            df["pct_change"] = df["pct_change"].fillna(0)
            df["turn_over"] = df["turn_over"].fillna(0)
            df["vol_ratio"] = df["vol_ratio"].fillna(1)

            by_code = df.set_index("ts_code", drop=False)
            merged: Dict[str, Dict] = {}

            # C: 量比异动（先放入，优先级最低）
            mask_c = (df["vol_ratio"] >= vol_ratio_min) & (
                df["pct_change"] > pct_floor
            )
            for _, row in df.loc[mask_c].iterrows():
                tc = str(row["ts_code"])
                merged[tc] = self._bak_row_to_stock_dict(row, candidate_source_tag="量比异动")

            # A: 涨幅前列
            top_n = max(1, min(top_gainers, 300))
            top_df = df.sort_values("pct_change", ascending=False).head(top_n)
            for _, row in top_df.iterrows():
                tc = str(row["ts_code"])
                if tc in merged:
                    merged[tc] = self._append_candidate_source(merged[tc], "涨幅前列")
                else:
                    merged[tc] = self._bak_row_to_stock_dict(row, candidate_source_tag="涨幅前列")

            # B: 涨停全量，题材覆盖 sector_name
            df_up = self.pro.limit_list_d(
                trade_date=effective_trade_date,
                limit_type="U",
            )
            if df_up is not None and not df_up.empty:
                for _, lr in df_up.iterrows():
                    tc = str(lr.get("ts_code", "")).strip()
                    if not tc:
                        continue
                    theme = lr.get("theme")
                    theme_s = (
                        str(theme).strip()
                        if theme is not None and str(theme).strip()
                        else "其他题材"
                    )
                    if tc in by_code.index:
                        row = by_code.loc[tc]
                        if getattr(row, "ndim", 1) == 2:
                            row = row.iloc[0]
                        if tc in merged:
                            merged[tc] = self._bak_row_to_stock_dict(
                                row, sector_name=theme_s, candidate_source_tag=merged[tc].get("candidate_source_tag", "")
                            )
                            merged[tc] = self._append_candidate_source(merged[tc], "涨停入选")
                        else:
                            merged[tc] = self._bak_row_to_stock_dict(
                                row, sector_name=theme_s, candidate_source_tag="涨停入选"
                            )
                    else:
                        merged[tc] = self._limit_up_row_to_stock_dict(lr, candidate_source_tag="涨停入选")

            result = list(merged.values())
            result.sort(key=lambda x: x["change_pct"], reverse=True)
            logger.info(
                f"扩展个股候选（{effective_trade_date}）: 共 {len(result)} 只 "
                f"(涨幅前{top_n}+涨停+量比≥{vol_ratio_min})"
            )
            return result
        except Exception as e:
            logger.error(f"获取扩展个股列表失败: {e}")
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
        ts_code = normalize_ts_code(ts_code)
        trade_date = str(trade_date).replace("-", "").strip()

        if not self.token:
            return self._mock_stock_detail(ts_code)

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)

            # 获取股票基本信息（名称和行业）
            stock_info = self.pro.stock_basic(ts_code=ts_code)
            stock_name = ts_code
            industry = "未知"
            if not stock_info.empty:
                stock_name = stock_info.iloc[0].get("name", ts_code)
                industry = stock_info.iloc[0].get("industry", "未知")

            # 获取日线数据
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=effective_trade_date,
                end_date=effective_trade_date,
            )
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
            {"ts_code": "000001.SZ", "stock_name": "平安银行", "sector_name": "银行", "close": 12.5, "change_pct": 3.5, "turnover_rate": 8.5, "amount": 350000, "vol_ratio": 1.8, "high": 12.8, "low": 12.1, "open": 12.2, "pre_close": 12.1, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "000002.SZ", "stock_name": "万 科A", "sector_name": "房地产", "close": 8.2, "change_pct": 5.2, "turnover_rate": 15.0, "amount": 520000, "vol_ratio": 2.5, "high": 8.5, "low": 7.9, "open": 7.9, "pre_close": 7.8, "candidate_source_tag": "涨幅前列/量比异动"},
            {"ts_code": "600036.SH", "stock_name": "招商银行", "sector_name": "银行", "close": 35.0, "change_pct": 2.0, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.5, "high": 35.5, "low": 34.2, "open": 34.3, "pre_close": 34.3, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "600519.SH", "stock_name": "贵州茅台", "sector_name": "白酒", "close": 1850.0, "change_pct": 1.2, "turnover_rate": 0.8, "amount": 450000, "vol_ratio": 1.2, "high": 1860.0, "low": 1820.0, "open": 1825.0, "pre_close": 1828.0, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "300750.SZ", "stock_name": "宁德时代", "sector_name": "新能源汽车", "close": 185.0, "change_pct": 4.5, "turnover_rate": 12.0, "amount": 680000, "vol_ratio": 2.2, "high": 188.0, "low": 178.0, "open": 178.0, "pre_close": 177.0, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "002594.SZ", "stock_name": "比亚迪", "sector_name": "新能源汽车", "close": 265.0, "change_pct": 3.8, "turnover_rate": 6.5, "amount": 420000, "vol_ratio": 1.6, "high": 268.0, "low": 258.0, "open": 258.0, "pre_close": 255.0, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "000858.SZ", "stock_name": "五粮液", "sector_name": "白酒", "close": 168.0, "change_pct": 2.1, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.3, "high": 170.0, "low": 165.0, "open": 165.0, "pre_close": 164.5, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "600900.SH", "stock_name": "长江电力", "sector_name": "电力", "close": 23.5, "change_pct": 0.5, "turnover_rate": 1.2, "amount": 150000, "vol_ratio": 1.0, "high": 23.8, "low": 23.2, "open": 23.3, "pre_close": 23.4, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "601318.SH", "stock_name": "中国平安", "sector_name": "保险", "close": 48.5, "change_pct": 1.8, "turnover_rate": 2.5, "amount": 320000, "vol_ratio": 1.4, "high": 49.0, "low": 47.8, "open": 47.8, "pre_close": 47.6, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "000333.SZ", "stock_name": "美的集团", "sector_name": "家电", "close": 62.0, "change_pct": 2.5, "turnover_rate": 4.0, "amount": 250000, "vol_ratio": 1.5, "high": 63.0, "low": 61.0, "open": 61.0, "pre_close": 60.5, "candidate_source_tag": "涨幅前列"},
            {"ts_code": "002475.SZ", "stock_name": "立讯精密", "sector_name": "电子", "close": 35.0, "change_pct": 6.5, "turnover_rate": 18.0, "amount": 580000, "vol_ratio": 3.0, "high": 36.0, "low": 33.5, "open": 33.5, "pre_close": 32.8, "candidate_source_tag": "涨幅前列/量比异动"},
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
