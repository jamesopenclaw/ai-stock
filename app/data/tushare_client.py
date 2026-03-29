"""
Tushare 数据客户端
"""
import copy
import os
import time as time_module
from datetime import datetime, time
from zoneinfo import ZoneInfo
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

    SH_TZ = ZoneInfo("Asia/Shanghai")
    REALTIME_CHUNK_SIZE = 50
    REALTIME_SOURCE = "sina"
    REALTIME_MARKET_CACHE_TTL_SECONDS = 20
    REALTIME_VOLUME_RATIO_CACHE_TTL_SECONDS = 60
    REALTIME_MARKET_MIN_TOTAL = 3000
    STOCK_BASIC_CACHE_TTL_SECONDS = 6 * 60 * 60
    EXPANDED_STOCK_LIST_CACHE_TTL_SECONDS = 5 * 60

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.tushare_token
        if self.token:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            logger.info("Tushare 客户端初始化成功")
        else:
            logger.warning("Tushare token 未配置，部分功能可能不可用")
        self._realtime_market_cache = {
            "trade_date": "",
            "fetched_at": 0.0,
            "snapshot": None,
        }
        self._stock_basic_industry_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._stock_basic_snapshot_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._intraday_volume_ratio_cache = {}
        self._ths_concept_index_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._ths_member_by_stock_cache = {}
        self._expanded_stock_list_cache = {}

    def _now_sh(self) -> datetime:
        """获取上海时区当前时间。"""
        return datetime.now(self.SH_TZ)

    def _should_use_realtime_quote(self, trade_date: str) -> bool:
        """
        当前请求是否适合尝试盘中实时行情。

        仅在：
        - 已配置 token
        - 请求日期等于上海时区今天
        - 交易日工作日
        - 09:15 ~ 15:30
        时尝试实时覆盖。
        """
        if not self.token:
            return False

        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        now = self._now_sh()
        if compact_trade_date != now.strftime("%Y%m%d"):
            return False
        if now.weekday() >= 5:
            return False
        current_time = now.time()
        return time(9, 15) <= current_time <= time(15, 30)

    def get_last_completed_trade_date(self, trade_date: str) -> str:
        """
        获取最近一个“已完成”的交易日。

        用于需要稳定日线输出的场景：
        - 若请求的是今天且当前仍在盘中，则回退到上一交易日
        - 其他情况沿用最近开市日
        """
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        effective_trade_date = self._resolve_trade_date(compact_trade_date) if self.token else compact_trade_date

        if self._should_use_realtime_quote(compact_trade_date):
            recent_dates = self._recent_open_dates(effective_trade_date, count=2)
            if len(recent_dates) >= 2:
                return recent_dates[1]

        return effective_trade_date

    def _fetch_realtime_quote_map(self, ts_codes: List[str]) -> Dict[str, Dict]:
        """批量获取实时行情并转成按 ts_code 索引的映射。"""
        normalized_codes = []
        for code in ts_codes:
            normalized = normalize_ts_code(code)
            if normalized and normalized not in normalized_codes:
                normalized_codes.append(normalized)

        if not normalized_codes:
            return {}

        quote_map: Dict[str, Dict] = {}
        for idx in range(0, len(normalized_codes), self.REALTIME_CHUNK_SIZE):
            chunk = normalized_codes[idx: idx + self.REALTIME_CHUNK_SIZE]
            try:
                df = ts.realtime_quote(
                    ",".join(chunk),
                    src=self.REALTIME_SOURCE,
                )
            except Exception as e:
                logger.warning(f"实时行情拉取失败（{len(chunk)}只）: {e}")
                continue

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                ts_code = normalize_ts_code(str(row.get("TS_CODE") or "").strip())
                if not ts_code:
                    continue
                price = float(row.get("PRICE") or 0)
                volume = float(row.get("VOLUME") or 0)
                amount = float(row.get("AMOUNT") or 0)
                pre_close = float(row.get("PRE_CLOSE") or 0)
                change_pct = 0.0
                if pre_close:
                    change_pct = round((price - pre_close) / pre_close * 100, 2)
                date_raw = str(row.get("DATE") or "").strip()
                time_raw = str(row.get("TIME") or "").strip()
                quote_time = None
                if len(date_raw) == 8 and time_raw:
                    quote_time = (
                        f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]} {time_raw}"
                    )

                quote_map[ts_code] = {
                    "close": price,
                    "change_pct": change_pct,
                    "open": float(row.get("OPEN") or 0),
                    "high": float(row.get("HIGH") or 0),
                    "low": float(row.get("LOW") or 0),
                    "pre_close": pre_close,
                    "volume": volume,
                    "amount": amount,
                    "avg_price": self._infer_realtime_avg_price(price, amount, volume),
                    "trade_date": date_raw,
                    "quote_time": quote_time,
                    "data_source": f"realtime_{self.REALTIME_SOURCE}",
                }

        return quote_map

    def _apply_realtime_overlay_to_stocks(
        self,
        rows: List[Dict],
        trade_date: str,
    ) -> bool:
        """对个股列表做盘中价格覆盖，不改动日线评分口径字段。"""
        if not rows or not self._should_use_realtime_quote(trade_date):
            return False

        quote_map = self._fetch_realtime_quote_map([row.get("ts_code", "") for row in rows])
        if not quote_map:
            return False

        used_realtime = False
        for row in rows:
            realtime = quote_map.get(normalize_ts_code(row.get("ts_code", "")))
            if not realtime:
                row.setdefault("data_source", "daily_fallback")
                continue
            row["close"] = realtime["close"]
            row["change_pct"] = realtime["change_pct"]
            row["open"] = realtime["open"]
            row["high"] = realtime["high"]
            row["low"] = realtime["low"]
            row["pre_close"] = realtime["pre_close"]
            row["volume"] = realtime["volume"]
            row["amount"] = realtime["amount"]
            row["avg_price"] = realtime["avg_price"]
            row["quote_time"] = realtime["quote_time"]
            row["data_source"] = realtime["data_source"]
            used_realtime = True
        return used_realtime

    def _apply_realtime_overlay_to_indexes(
        self,
        rows: List[Dict],
        trade_date: str,
    ) -> bool:
        """对指数列表做盘中覆盖。"""
        if not rows or not self._should_use_realtime_quote(trade_date):
            return False

        quote_map = self._fetch_realtime_quote_map([row.get("ts_code", "") for row in rows])
        if not quote_map:
            return False

        used_realtime = False
        for row in rows:
            realtime = quote_map.get(normalize_ts_code(row.get("ts_code", "")))
            if not realtime:
                row.setdefault("data_source", "index_daily")
                continue
            row["close"] = realtime["close"]
            row["change_pct"] = realtime["change_pct"]
            row["volume"] = realtime["volume"]
            row["amount"] = realtime["amount"]
            row["trade_date"] = realtime["trade_date"] or row.get("trade_date")
            row["quote_time"] = realtime["quote_time"]
            row["data_source"] = realtime["data_source"]
            used_realtime = True
        return used_realtime

    def _fetch_realtime_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """获取盘中市场快照，短 TTL 缓存避免重复抓全市场。"""
        if not self._should_use_realtime_quote(trade_date):
            return None

        cache = getattr(self, "_realtime_market_cache", None) or {
            "trade_date": "",
            "fetched_at": 0.0,
            "snapshot": None,
        }
        now_ts = time_module.monotonic()
        if (
            cache.get("trade_date") == str(trade_date).replace("-", "")[:8]
            and now_ts - float(cache.get("fetched_at") or 0) < self.REALTIME_MARKET_CACHE_TTL_SECONDS
        ):
            return cache.get("snapshot") or None

        df = None
        used_source = None
        last_error = None
        for source in ("dc", "sina"):
            for _ in range(2):
                try:
                    df = ts.realtime_list(src=source, page_count=1 if source == "sina" else None)
                    if df is not None and not df.empty:
                        used_source = source
                        break
                except Exception as e:
                    last_error = e
            if df is not None and not df.empty:
                break
        if df is None or df.empty:
            if last_error:
                logger.warning(f"盘中市场快照拉取失败: {last_error}")
            self._realtime_market_cache = {
                "trade_date": str(trade_date).replace("-", "")[:8],
                "fetched_at": now_ts,
                "snapshot": False,
            }
            return None

        pct_series = df["PCT_CHANGE"].fillna(0)
        amount_series = df["AMOUNT"].fillna(0)
        up = int((pct_series > 0).sum())
        down = int((pct_series < 0).sum())
        flat = int((pct_series == 0).sum())
        total = len(df)
        if total < self.REALTIME_MARKET_MIN_TOTAL:
            logger.warning(
                f"盘中市场快照样本不足（{used_source or 'unknown'} 仅 {total} 条），回退日线口径"
            )
            self._realtime_market_cache = {
                "trade_date": str(trade_date).replace("-", "")[:8],
                "fetched_at": now_ts,
                "snapshot": False,
            }
            return None
        limit_stats = self._estimate_realtime_limit_stats(df)
        now = self._now_sh()
        quote_time = now.strftime("%Y-%m-%d %H:%M:%S")
        time_col = str(df.iloc[0].get("TIME") or "").strip() if "TIME" in df.columns and not df.empty else ""
        if time_col:
            quote_time = f"{now.strftime('%Y-%m-%d')} {time_col}"
        snapshot = {
            "market_turnover": round(float(amount_series.sum()) / 100000000, 2),
            "up_down_ratio": {
                "up": up,
                "down": down,
                "flat": flat,
                "total": total,
            },
            "limit_stats": limit_stats,
            "data_trade_date": now.strftime("%Y%m%d"),
            "quote_time": quote_time,
            "data_source": f"realtime_{used_source or 'unknown'}",
        }
        self._realtime_market_cache = {
            "trade_date": snapshot["data_trade_date"],
            "fetched_at": now_ts,
            "snapshot": snapshot,
        }
        return snapshot

    def _estimate_limit_pct(self, ts_code: str, stock_name: str = "") -> float:
        code = normalize_ts_code(ts_code)
        name = str(stock_name or "").upper()
        compact_name = name.replace("*", "").replace(" ", "")
        if "ST" in compact_name:
            return 5.0
        if code.endswith(".BJ"):
            return 30.0
        if code.startswith(("300", "301", "688")):
            return 20.0
        return 10.0

    def _is_near_price(self, actual: float, target: float) -> bool:
        if actual <= 0 or target <= 0:
            return False
        tolerance = max(0.01, target * 0.0015)
        return abs(actual - target) <= tolerance

    def _estimate_realtime_limit_stats(self, df) -> Dict[str, object]:
        """基于全市场实时表近似估算盘中涨跌停和炸板率。"""
        if df is None or getattr(df, "empty", True):
            return {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "broken_board_rate": 0.0,
                "estimated": True,
            }

        limit_up_count = 0
        limit_down_count = 0
        touched_limit_up_count = 0
        broken_board_count = 0

        for _, row in df.iterrows():
            ts_code = normalize_ts_code(str(row.get("TS_CODE") or "").strip())
            if not ts_code:
                continue
            stock_name = str(row.get("NAME") or "").strip()
            limit_pct = self._estimate_limit_pct(ts_code, stock_name)
            pre_close = float(row.get("CLOSE") or row.get("PRE_CLOSE") or 0)
            price = float(row.get("PRICE") or 0)
            high = float(row.get("HIGH") or 0)
            low = float(row.get("LOW") or 0)
            pct_change = float(row.get("PCT_CHANGE") or 0)
            if pre_close <= 0:
                continue

            upper_limit_price = round(pre_close * (1 + limit_pct / 100), 2)
            lower_limit_price = round(pre_close * (1 - limit_pct / 100), 2)
            near_upper = self._is_near_price(price, upper_limit_price) or pct_change >= limit_pct - 0.15
            near_lower = self._is_near_price(price, lower_limit_price) or pct_change <= -limit_pct + 0.15
            touched_upper = self._is_near_price(high, upper_limit_price)
            touched_lower = self._is_near_price(low, lower_limit_price)

            if near_upper:
                limit_up_count += 1
            if near_lower:
                limit_down_count += 1
            if touched_upper:
                touched_limit_up_count += 1
                if not near_upper:
                    broken_board_count += 1
            elif touched_lower and not near_lower:
                # 跌停打开不计入炸板，但保留这里作为未来扩展点
                pass

        broken_board_rate = 0.0
        if touched_limit_up_count > 0:
            broken_board_rate = round(broken_board_count / touched_limit_up_count * 100, 1)

        return {
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "broken_board_rate": broken_board_rate,
            "estimated": True,
            "touched_limit_up_count": touched_limit_up_count,
            "broken_board_count": broken_board_count,
        }

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
                open_days = sorted(str(d) for d in open_days)
                return open_days[:count]
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
        return self.get_index_quote_with_meta(trade_date).get("rows", [])

    def get_index_quote_with_meta(self, trade_date: str) -> Dict[str, object]:
        """获取主要指数行情，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "rows": self._mock_index_quote(trade_date),
                "data_trade_date": trade_date,
                "used_mock": True,
            }

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            # 上证指数、深成指、创业板
            index_codes = ["000001.SH", "399001.SZ", "399006.SZ"]
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                result = []
                for ts_code in index_codes:
                    df = self.pro.index_daily(
                        ts_code=ts_code,
                        start_date=data_trade_date,
                        end_date=data_trade_date
                    )
                    if df is None or df.empty:
                        continue
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
                        "trade_date": row["trade_date"],
                        "quote_time": None,
                        "data_source": "index_daily",
                    })
                if result:
                    used_realtime = self._apply_realtime_overlay_to_indexes(result, trade_date)
                    response_trade_date = trade_date if used_realtime else data_trade_date
                    if data_trade_date != effective_trade_date:
                        logger.info(
                            f"指数行情从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                        )
                    return {
                        "rows": result,
                        "data_trade_date": response_trade_date,
                        "used_mock": False,
                    }

            logger.warning(f"最近交易日均无指数行情（截至 {effective_trade_date}）")
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "used_mock": False,
            }
        except Exception as e:
            logger.error(f"获取指数行情失败: {e}")
            return {
                "rows": [],
                "data_trade_date": trade_date,
                "used_mock": False,
            }

    def get_limit_stats(self, trade_date: str) -> Dict:
        """
        获取涨跌停统计数据

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            涨跌停统计
        """
        return self.get_limit_stats_with_meta(trade_date).get("stats", {})

    def get_limit_stats_with_meta(self, trade_date: str) -> Dict[str, object]:
        """获取涨跌停统计，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "stats": self._mock_limit_stats(),
                "data_trade_date": trade_date,
                "used_mock": True,
            }

        try:
            snapshot = self._fetch_realtime_market_snapshot(trade_date)
            if snapshot and snapshot.get("limit_stats"):
                return {
                    "stats": snapshot["limit_stats"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot.get("quote_time"),
                    "data_source": snapshot.get("data_source"),
                }
            effective_trade_date = self._resolve_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df_up = self.pro.limit_list_d(
                    trade_date=data_trade_date,
                    limit_type='U',
                )
                df_down = self.pro.limit_list_d(
                    trade_date=data_trade_date,
                    limit_type='D',
                )
                limit_up_count = len(df_up) if df_up is not None else 0
                limit_down_count = len(df_down) if df_down is not None else 0

                broken_board_rate = 0.0
                if (
                    limit_up_count > 0
                    and df_up is not None
                    and "open_times" in df_up.columns
                ):
                    broken = len(df_up[df_up["open_times"] > 0])
                    broken_board_rate = round(broken / limit_up_count * 100, 1)

                if limit_up_count == 0 and limit_down_count == 0:
                    logger.warning(f"涨跌停列表为空（{data_trade_date}）")
                    continue

                if data_trade_date != effective_trade_date:
                    logger.info(
                        f"涨跌停统计从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                    )
                return {
                    "stats": {
                        "limit_up_count": limit_up_count,
                        "limit_down_count": limit_down_count,
                        "broken_board_rate": broken_board_rate,
                    },
                    "data_trade_date": data_trade_date,
                    "used_mock": False,
                }

            return {
                "stats": {
                    "limit_up_count": 0,
                    "limit_down_count": 0,
                    "broken_board_rate": 0.0,
                },
                "data_trade_date": effective_trade_date,
                "used_mock": False,
            }
        except Exception as e:
            logger.error(f"获取涨跌停统计失败: {e}")
            return {
                "stats": {
                    "limit_up_count": 0,
                    "limit_down_count": 0,
                    "broken_board_rate": 0.0,
                },
                "data_trade_date": trade_date,
                "used_mock": False,
            }

    def get_sector_data(self, trade_date: str) -> List[Dict]:
        """
        获取板块行情数据（按 daily + stock_basic 行业字段聚合）。

        Args:
            trade_date: 交易日，格式 YYYYMMDD

        Returns:
            板块行情列表（按平均涨跌幅降序）
        """
        return self.get_sector_data_with_meta(trade_date)["rows"]

    def _recent_open_dates(self, trade_date: str, count: int = 5) -> List[str]:
        """获取截至指定日期的最近若干开市日，按新到旧排序。"""
        if not self.token:
            return [trade_date]

        try:
            from datetime import datetime, timedelta

            end_dt = datetime.strptime(trade_date, "%Y%m%d")
            start_dt = end_dt - timedelta(days=20)
            cal_df = self.pro.trade_cal(
                exchange="SSE",
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=trade_date,
                fields="cal_date,is_open",
            )
            if cal_df is None or cal_df.empty:
                return [trade_date]
            open_days = cal_df[cal_df["is_open"] == 1]["cal_date"].tolist()
            open_days = sorted((str(day) for day in open_days), reverse=True)
            return open_days[:count] or [trade_date]
        except Exception as e:
            logger.warning(f"获取最近交易日序列失败: {e}")
            return [trade_date]

    def _get_stock_basic_snapshot_map(self) -> Dict[str, Dict[str, str]]:
        """获取股票基础映射，并做进程内缓存。"""
        if not self.token:
            return {}

        cache = getattr(self, "_stock_basic_snapshot_cache", None)
        now_ts = time_module.time()
        if (
            cache
            and cache.get("mapping")
            and now_ts - float(cache.get("fetched_at") or 0)
            < self.STOCK_BASIC_CACHE_TTL_SECONDS
        ):
            return dict(cache["mapping"])

        try:
            try:
                df = self.pro.stock_basic(fields="ts_code,name,industry")
            except TypeError:
                df = self.pro.stock_basic()

            if df is None or df.empty:
                return dict(cache.get("mapping") or {}) if cache else {}

            mapping: Dict[str, Dict[str, str]] = {}
            for _, row in df.iterrows():
                ts_code = normalize_ts_code(str(row.get("ts_code") or "").strip())
                stock_name = str(row.get("name") or ts_code).strip() or ts_code
                industry = str(row.get("industry") or "").strip()
                if ts_code:
                    mapping[ts_code] = {
                        "stock_name": stock_name,
                        "industry": industry,
                    }

            self._stock_basic_snapshot_cache = {
                "fetched_at": now_ts,
                "mapping": mapping,
            }
            return dict(mapping)
        except Exception as e:
            logger.warning(f"获取 stock_basic 基础映射失败: {e}")
            return dict(cache.get("mapping") or {}) if cache else {}

    def _get_stock_basic_industry_map(self) -> Dict[str, str]:
        """获取股票行业映射，并做进程内缓存。"""
        cache = getattr(self, "_stock_basic_industry_cache", None)
        now_ts = time_module.time()
        if (
            cache
            and cache.get("mapping")
            and now_ts - float(cache.get("fetched_at") or 0)
            < self.STOCK_BASIC_CACHE_TTL_SECONDS
        ):
            return dict(cache["mapping"])

        snapshot_map = self._get_stock_basic_snapshot_map()
        mapping = {
            ts_code: str(meta.get("industry") or "").strip()
            for ts_code, meta in snapshot_map.items()
            if str(meta.get("industry") or "").strip()
        }
        self._stock_basic_industry_cache = {
            "fetched_at": now_ts,
            "mapping": mapping,
        }
        return dict(mapping)

    def _build_daily_sector_source_df(self, df, industry_map: Dict[str, str]):
        """将 daily 行情与行业映射合并为板块聚合明细。"""
        if df is None or df.empty:
            return None

        work = df.copy()
        if "ts_code" not in work.columns or "pct_chg" not in work.columns:
            return None

        work["ts_code"] = work["ts_code"].astype(str).map(normalize_ts_code)
        work["industry"] = work["ts_code"].map(industry_map)
        work["pct_change"] = work["pct_chg"].fillna(0)
        work["amount"] = work.get("amount", 0)
        work["amount"] = work["amount"].fillna(0)
        work = work[work["industry"].notna() & (work["industry"] != "")]
        if work.empty:
            return None
        return work[["ts_code", "industry", "pct_change", "amount"]]

    def _build_daily_stock_source_df(
        self,
        daily_df,
        stock_meta_map: Dict[str, Dict[str, str]],
        daily_basic_df=None,
    ):
        """将 daily 行情与 stock_basic/daily_basic 合并为候选股明细。"""
        if daily_df is None or daily_df.empty:
            return None

        work = daily_df.copy()
        if "ts_code" not in work.columns or "pct_chg" not in work.columns:
            return None

        work["ts_code"] = work["ts_code"].astype(str).map(normalize_ts_code)
        work["stock_name"] = work["ts_code"].map(
            lambda code: str((stock_meta_map.get(code) or {}).get("stock_name") or code)
        )
        work["industry"] = work["ts_code"].map(
            lambda code: str((stock_meta_map.get(code) or {}).get("industry") or "").strip()
        )
        work["pct_change"] = work["pct_chg"].fillna(0)
        work["amount"] = work.get("amount", 0)
        work["amount"] = work["amount"].fillna(0)

        if daily_basic_df is not None and not daily_basic_df.empty:
            basic = daily_basic_df.copy()
            basic["ts_code"] = basic["ts_code"].astype(str).map(normalize_ts_code)
            if "turnover_rate" not in basic.columns:
                basic["turnover_rate"] = 0.0
            if "volume_ratio" not in basic.columns:
                basic["volume_ratio"] = 1.0
            basic = basic[["ts_code", "turnover_rate", "volume_ratio"]]
            work = work.merge(basic, on="ts_code", how="left")
        else:
            work["turnover_rate"] = 0.0
            work["volume_ratio"] = 1.0

        work["turnover_rate"] = work["turnover_rate"].fillna(0)
        work["volume_ratio"] = work["volume_ratio"].fillna(1.0)
        return work[
            [
                "ts_code",
                "stock_name",
                "industry",
                "close",
                "pct_change",
                "turnover_rate",
                "amount",
                "volume_ratio",
                "high",
                "low",
                "open",
                "pre_close",
            ]
        ]

    def _aggregate_sector_rows(
        self,
        df,
        amount_divisor: float = 10000,
    ) -> List[Dict]:
        """将行业明细聚合成板块列表。"""
        if df is None or df.empty:
            return []

        df = df.copy()
        df["pct_change"] = df["pct_change"].fillna(0)
        df["amount"] = df["amount"].fillna(0)
        df = df[df["industry"].notna() & (df["industry"] != "")]
        if df.empty:
            return []

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
                "sector_turnover": round(
                    float(row["sector_turnover"]) / amount_divisor,
                    2,
                ),
                "stock_count": int(row["stock_count"]),
            })
        return sectors

    def get_sector_data_with_meta(self, trade_date: str) -> Dict[str, object]:
        """获取行业板块，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "rows": self._mock_sector_data(),
                "data_trade_date": trade_date,
                "used_mock": True,
            }

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)
            industry_map = self._get_stock_basic_industry_map()
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df = self.pro.daily(trade_date=data_trade_date)
                source_df = self._build_daily_sector_source_df(df, industry_map)
                sectors = self._aggregate_sector_rows(
                    source_df,
                    amount_divisor=100000,
                )
                if not sectors:
                    logger.warning(f"daily 行业板块数据为空（{data_trade_date}）")
                    continue

                if data_trade_date != effective_trade_date:
                    logger.info(
                        f"板块数据从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                    )

                logger.info(
                    f"板块数据（{data_trade_date}）: {len(sectors)} 个行业"
                )
                return {
                    "rows": sectors,
                    "data_trade_date": data_trade_date,
                    "used_mock": False,
                }

            logger.warning(f"最近交易日均无板块数据（截至 {effective_trade_date}）")
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "used_mock": False,
            }
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return {
                "rows": [],
                "data_trade_date": trade_date,
                "used_mock": False,
            }

    def get_market_turnover(self, trade_date: str) -> float:
        """
        获取两市成交额

        Args:
            trade_date: 交易日

        Returns:
            成交额(亿元)
        """
        return float(self.get_market_turnover_with_meta(trade_date).get("market_turnover") or 0.0)

    def get_market_turnover_with_meta(self, trade_date: str) -> Dict[str, object]:
        """获取两市成交额，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "market_turnover": 12000.0,
                "data_trade_date": trade_date,
                "used_mock": True,
                "quote_time": None,
                "data_source": "mock",
            }

        try:
            snapshot = self._fetch_realtime_market_snapshot(trade_date)
            if snapshot:
                return {
                    "market_turnover": snapshot["market_turnover"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot["quote_time"],
                    "data_source": snapshot["data_source"],
                }
            effective_trade_date = self._resolve_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                sh_df = self.pro.index_daily(
                    ts_code="000001.SH",
                    start_date=data_trade_date,
                    end_date=data_trade_date
                )
                sz_df = self.pro.index_daily(
                    ts_code="399001.SZ",
                    start_date=data_trade_date,
                    end_date=data_trade_date
                )
                total = 0.0
                if sh_df is not None and not sh_df.empty:
                    total += float(sh_df.iloc[0]["amount"])
                if sz_df is not None and not sz_df.empty:
                    total += float(sz_df.iloc[0]["amount"])
                if total > 0:
                    if data_trade_date != effective_trade_date:
                        logger.info(
                            f"市场成交额从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                        )
                    return {
                        "market_turnover": total / 100000,
                        "data_trade_date": data_trade_date,
                        "used_mock": False,
                        "quote_time": None,
                        "data_source": "index_daily",
                    }
            return {
                "market_turnover": 12000.0,
                "data_trade_date": effective_trade_date,
                "used_mock": False,
                "quote_time": None,
                "data_source": "index_daily",
            }
        except Exception as e:
            logger.error(f"获取成交额失败: {e}")
            return {
                "market_turnover": 12000.0,
                "data_trade_date": trade_date,
                "used_mock": False,
                "quote_time": None,
                "data_source": "index_daily",
            }

    def get_up_down_ratio(self, trade_date: str) -> Dict:
        """
        获取涨跌家数对比（基于 daily 的 pct_chg 字段）

        Args:
            trade_date: 交易日

        Returns:
            涨跌家数 {"up": int, "down": int, "flat": int, "total": int}
        """
        return self.get_up_down_ratio_with_meta(trade_date).get("up_down_ratio", {})

    def get_up_down_ratio_with_meta(self, trade_date: str) -> Dict[str, object]:
        """获取涨跌家数，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "up_down_ratio": {"up": 0, "down": 0, "flat": 0, "total": 0},
                "data_trade_date": trade_date,
                "used_mock": True,
                "quote_time": None,
                "data_source": "mock",
            }

        try:
            snapshot = self._fetch_realtime_market_snapshot(trade_date)
            if snapshot:
                return {
                    "up_down_ratio": snapshot["up_down_ratio"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot["quote_time"],
                    "data_source": snapshot["data_source"],
                }
            effective_trade_date = self._resolve_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df = self.pro.daily(trade_date=data_trade_date)
                if df is None or df.empty:
                    logger.warning(f"daily 无数据（{data_trade_date}）")
                    continue

                df["pct_chg"] = df["pct_chg"].fillna(0)
                up = int((df["pct_chg"] > 0).sum())
                down = int((df["pct_chg"] < 0).sum())
                flat = int((df["pct_chg"] == 0).sum())
                total = len(df)
                if data_trade_date != effective_trade_date:
                    logger.info(
                        f"涨跌家数从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                    )
                logger.info(f"涨跌家数（{data_trade_date}）: 涨{up} 跌{down} 平{flat}")
                return {
                    "up_down_ratio": {"up": up, "down": down, "flat": flat, "total": total},
                    "data_trade_date": data_trade_date,
                    "used_mock": False,
                    "quote_time": None,
                    "data_source": "daily",
                }
            return {
                "up_down_ratio": {"up": 0, "down": 0, "flat": 0, "total": 0},
                "data_trade_date": effective_trade_date,
                "used_mock": False,
                "quote_time": None,
                "data_source": "daily",
            }
        except Exception as e:
            logger.error(f"获取涨跌家数失败: {e}")
            return {
                "up_down_ratio": {"up": 0, "down": 0, "flat": 0, "total": 0},
                "data_trade_date": trade_date,
                "used_mock": False,
                "quote_time": None,
                "data_source": "daily",
            }

    def _aggregate_limitup_rows(
        self,
        df,
        label_col: str,
        default_label: str,
    ) -> List[Dict]:
        """按指定字段聚合涨停列表，产出统一板块结构。"""
        if df is None or df.empty:
            return []

        work = df.copy()
        work["_label"] = work[label_col].fillna("").astype(str).str.strip()
        work.loc[work["_label"] == "", "_label"] = default_label

        pct_col = "pct_chg" if "pct_chg" in work.columns else None
        if not pct_col:
            return []

        work[pct_col] = work[pct_col].fillna(0)

        if "amount" in work.columns:
            grouped = (
                work.groupby("_label", as_index=False)
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
                work.groupby("_label", as_index=False)
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
                "sector_name": str(row["_label"]),
                "sector_code": "",
                "sector_change_pct": round(float(row["sector_change_pct"]), 2),
                "sector_turnover": round(float(row["sector_turnover"]), 2),
                "stock_count": int(row["stock_count"]),
            })
        return sectors

    def _get_ths_concept_index_map(self) -> Dict[str, Dict[str, str]]:
        """获取同花顺题材指数映射，并做进程内缓存。"""
        cache = getattr(self, "_ths_concept_index_cache", None)
        now_ts = time_module.time()
        if (
            cache
            and cache.get("mapping")
            and now_ts - float(cache.get("fetched_at") or 0)
            < self.STOCK_BASIC_CACHE_TTL_SECONDS
        ):
            return dict(cache["mapping"])

        mapping: Dict[str, Dict[str, str]] = {}
        ths_index = getattr(self.pro, "ths_index", None)
        if not callable(ths_index):
            return {}
        for ths_type in ("N", "TH"):
            try:
                df = ths_index(exchange="A", type=ths_type)
            except TypeError:
                df = ths_index(type=ths_type)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code") or "").strip()
                name = str(row.get("name") or "").strip()
                if not ts_code or not name:
                    continue
                mapping[ts_code] = {
                    "name": name,
                    "type": str(row.get("type") or ths_type).strip() or ths_type,
                }

        if mapping:
            self._ths_concept_index_cache = {
                "fetched_at": now_ts,
                "mapping": mapping,
            }
        return dict(mapping)

    def _get_ths_concept_codes_for_stock(self, ts_code: str) -> List[str]:
        """获取单只股票所属的同花顺题材代码，并做进程内缓存。"""
        normalized = normalize_ts_code(ts_code)
        if not normalized:
            return []

        cache = getattr(self, "_ths_member_by_stock_cache", None)
        if cache is None:
            cache = {}
            self._ths_member_by_stock_cache = cache

        now_ts = time_module.time()
        cached = cache.get(normalized)
        if cached and now_ts - float(cached.get("fetched_at") or 0) < self.STOCK_BASIC_CACHE_TTL_SECONDS:
            return list(cached.get("codes") or [])

        ths_member = getattr(self.pro, "ths_member", None)
        if not callable(ths_member):
            cache[normalized] = {
                "fetched_at": now_ts,
                "codes": [],
            }
            return []

        df = ths_member(con_code=normalized)
        codes: List[str] = []
        if df is not None and not df.empty:
            work = df.copy()
            if "is_new" in work.columns:
                work = work[work["is_new"].fillna("Y").astype(str).str.upper() == "Y"]
            for code in work.get("ts_code", []):
                concept_code = str(code or "").strip()
                if concept_code and concept_code not in codes:
                    codes.append(concept_code)

        cache[normalized] = {
            "fetched_at": now_ts,
            "codes": codes,
        }
        return list(codes)

    def _get_ths_concept_names_for_stock(self, ts_code: str) -> List[str]:
        """获取单只股票所属的同花顺题材名称。"""
        concept_index_map = self._get_ths_concept_index_map()
        if not concept_index_map:
            return []

        names: List[str] = []
        for code in self._get_ths_concept_codes_for_stock(ts_code):
            name = str((concept_index_map.get(code) or {}).get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _get_concept_sectors_from_ths_with_meta(self, trade_date: str) -> Dict[str, object]:
        """
        基于同花顺题材成分与题材指数行情构建题材聚合。

        逻辑：
        - 用 limit_list_d 识别当日涨停股
        - 用 ths_member(con_code=ts_code) 找到涨停股所属题材
        - 用 ths_daily(trade_date=...) 提取题材指数涨跌幅
        - 成交额与扩散度仍按涨停股聚合
        """
        try:
            limitup_df = self.pro.limit_list_d(
                trade_date=trade_date,
                limit_type="U",
            )
            if limitup_df is None or limitup_df.empty:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "empty",
                    "message": "涨停列表为空，暂无可聚合题材",
                }
            if "pct_chg" not in limitup_df.columns:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "missing_pct_chg",
                    "message": "涨停列表缺少 pct_chg 字段，无法计算题材强度",
                }

            concept_index_map = self._get_ths_concept_index_map()
            if not concept_index_map:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "ths_unavailable",
                    "message": "同花顺题材索引不可用，无法构建题材聚合",
                }

            work = limitup_df.copy()
            work["ts_code"] = work["ts_code"].astype(str).map(normalize_ts_code)
            work["pct_chg"] = work["pct_chg"].fillna(0)
            if "amount" not in work.columns:
                work["amount"] = 0.0
            work["amount"] = work["amount"].fillna(0)

            grouped: Dict[str, Dict[str, object]] = {}
            matched_stock_count = 0
            for _, row in work.iterrows():
                stock_code = str(row.get("ts_code") or "").strip()
                if not stock_code:
                    continue
                concept_codes = [
                    code
                    for code in self._get_ths_concept_codes_for_stock(stock_code)
                    if code in concept_index_map
                ]
                if not concept_codes:
                    continue
                matched_stock_count += 1
                for concept_code in concept_codes:
                    bucket = grouped.setdefault(
                        concept_code,
                        {
                            "sector_name": concept_index_map[concept_code]["name"],
                            "sector_code": concept_code,
                            "stock_codes": set(),
                            "pct_values": [],
                            "amount_sum": 0.0,
                        },
                    )
                    bucket["stock_codes"].add(stock_code)
                    bucket["pct_values"].append(float(row.get("pct_chg") or 0))
                    bucket["amount_sum"] = float(bucket["amount_sum"]) + float(row.get("amount") or 0)

            if not grouped:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "ths_no_members",
                    "message": "涨停股未匹配到可用的同花顺题材成分",
                }

            concept_quote_map: Dict[str, Dict[str, float]] = {}
            try:
                quote_df = self.pro.ths_daily(trade_date=trade_date)
                if quote_df is not None and not quote_df.empty and "ts_code" in quote_df.columns:
                    quote_df = quote_df.copy()
                    quote_df["ts_code"] = quote_df["ts_code"].astype(str).str.strip()
                    quote_df = quote_df[quote_df["ts_code"].isin(grouped.keys())]
                    for _, row in quote_df.iterrows():
                        concept_quote_map[str(row.get("ts_code") or "").strip()] = {
                            "pct_change": float(row.get("pct_change") or 0),
                        }
            except Exception as e:
                logger.warning(f"获取同花顺题材指数行情失败，将回退到涨停股均值: {e}")

            sectors: List[Dict] = []
            for concept_code, bucket in grouped.items():
                stock_codes = bucket["stock_codes"]
                pct_values = bucket["pct_values"]
                quote = concept_quote_map.get(concept_code) or {}
                change_pct = quote.get("pct_change")
                if change_pct is None:
                    change_pct = (
                        sum(float(v) for v in pct_values) / len(pct_values)
                        if pct_values else 0.0
                    )
                sectors.append({
                    "sector_name": str(bucket["sector_name"]),
                    "sector_code": concept_code,
                    "sector_change_pct": round(float(change_pct), 2),
                    "sector_turnover": round(float(bucket["amount_sum"]) / 10000, 2),
                    "stock_count": len(stock_codes),
                })

            sectors.sort(
                key=lambda row: (
                    int(row.get("stock_count", 0) or 0),
                    float(row.get("sector_change_pct", 0) or 0),
                ),
                reverse=True,
            )
            logger.info(
                f"题材板块（{trade_date}，THS题材聚合）: {len(sectors)} 个题材，命中 {matched_stock_count} 只涨停股"
            )
            return {
                "rows": sectors,
                "data_trade_date": trade_date,
                "status": "ok",
                "message": f"同花顺题材聚合成功，共 {len(sectors)} 个题材",
            }
        except Exception as e:
            logger.warning(f"同花顺题材聚合失败: {e}")
            return {
                "rows": [],
                "data_trade_date": trade_date,
                "status": "ths_error",
                "message": f"同花顺题材聚合异常: {e}",
            }

    def _get_concept_sectors_from_limitup_theme_with_meta(self, trade_date: str) -> Dict[str, object]:
        """按涨停板附带的 theme 字段聚合题材概念板块。"""
        try:
            df = self.pro.limit_list_d(
                trade_date=trade_date,
                limit_type="U",
            )
            if df is None or df.empty:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "empty",
                    "message": "涨停列表为空，暂无可聚合题材",
                }
            if "theme" not in df.columns:
                logger.warning(
                    f"limit_list_d 无 theme 列（{trade_date}），题材板块为空"
                )
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "missing_theme",
                    "message": "涨停列表未提供 theme 字段，无法按题材聚合",
                }

            sectors = self._aggregate_limitup_rows(
                df,
                label_col="theme",
                default_label="其他题材",
            )
            if not sectors:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "missing_pct_chg",
                    "message": "涨停列表缺少 pct_chg 字段，无法计算题材涨跌幅",
                }

            logger.info(
                f"题材板块（{trade_date}，涨停 theme 聚合）: {len(sectors)} 个"
            )
            return {
                "rows": sectors,
                "data_trade_date": trade_date,
                "status": "ok",
                "message": f"涨停题材聚合成功，共 {len(sectors)} 个题材",
            }
        except Exception as e:
            logger.warning(f"涨停 theme 题材聚合失败: {e}")
            return {
                "rows": [],
                "data_trade_date": trade_date,
                "status": "theme_error",
                "message": f"涨停 theme 题材聚合异常: {e}",
            }

    def get_concept_sectors_from_limitup_with_meta(self, trade_date: str) -> Dict[str, object]:
        """
        获取题材概念板块，并返回可追踪状态。

        status:
        - ok: 成功聚合出题材
        - no_token: 未配置 token
        - empty: 接口有响应但当日无涨停数据
        - missing_theme: 降级到旧 theme 口径时，返回字段不含 theme
        - missing_pct_chg: 返回字段缺少涨跌幅
        - ths_unavailable/ths_no_members/ths_error: 同花顺题材链路不可用
        """
        effective_trade_date = self._resolve_trade_date(trade_date) if self.token else trade_date
        if not self.token:
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "status": "no_token",
                "message": "未配置 Tushare Token，无法获取题材聚合数据",
            }

        ths_meta = self._get_concept_sectors_from_ths_with_meta(effective_trade_date)
        if ths_meta.get("rows"):
            return ths_meta

        theme_meta = self._get_concept_sectors_from_limitup_theme_with_meta(effective_trade_date)
        if theme_meta.get("rows"):
            return theme_meta

        if (
            ths_meta.get("status") not in {"empty", "missing_pct_chg"}
            and theme_meta.get("status") == "missing_theme"
        ):
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "status": str(ths_meta.get("status") or "missing_theme"),
                "message": (
                    f"{ths_meta.get('message') or '题材聚合不可用'}；"
                    "涨停列表也未提供 theme 字段，无法按题材聚合"
                ),
            }
        if ths_meta.get("status") in {"empty", "missing_pct_chg"}:
            return ths_meta
        return theme_meta

    def get_limitup_industry_sectors_with_meta(self, trade_date: str) -> Dict[str, object]:
        """按涨停列表的 industry 字段聚合行业热度，并返回可追踪状态。"""
        effective_trade_date = self._resolve_trade_date(trade_date) if self.token else trade_date
        if not self.token:
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "status": "no_token",
                "message": "未配置 Tushare Token，无法获取涨停行业聚合数据",
            }

        try:
            df = self.pro.limit_list_d(
                trade_date=effective_trade_date,
                limit_type="U",
            )
            if df is None or df.empty:
                return {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "status": "empty",
                    "message": "涨停列表为空，暂无可聚合行业",
                }
            if "industry" not in df.columns:
                return {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "status": "missing_industry",
                    "message": "涨停列表未提供 industry 字段，无法按行业聚合",
                }

            sectors = self._aggregate_limitup_rows(
                df,
                label_col="industry",
                default_label="其他行业",
            )
            if not sectors:
                return {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "status": "missing_pct_chg",
                    "message": "涨停列表缺少 pct_chg 字段，无法计算行业涨跌幅",
                }

            logger.info(
                f"涨停行业（{effective_trade_date}，涨停聚合）: {len(sectors)} 个"
            )
            return {
                "rows": sectors,
                "data_trade_date": effective_trade_date,
                "status": "ok",
                "message": f"涨停行业聚合成功，共 {len(sectors)} 个行业",
            }
        except Exception as e:
            logger.error(f"获取涨停行业板块失败: {e}")
            return {
                "rows": [],
                "data_trade_date": effective_trade_date,
                "status": "error",
                "message": f"涨停行业聚合调用异常: {e}",
            }

    def get_limitup_industry_sectors(self, trade_date: str) -> List[Dict]:
        """按涨停列表的 industry 字段聚合行业热度。"""
        return self.get_limitup_industry_sectors_with_meta(trade_date).get("rows", [])

    def get_concept_sectors_from_limitup(self, trade_date: str) -> List[Dict]:
        """
        按涨停板 limit_list_d 的 theme 字段聚合题材概念板块（与 get_sector_data 返回结构一致）。
        """
        return self.get_concept_sectors_from_limitup_with_meta(trade_date).get("rows", [])

    def _stock_row_to_stock_dict(
        self,
        row,
        sector_name: Optional[str] = None,
        concept_names: Optional[List[str]] = None,
        candidate_source_tag: str = "",
    ) -> Dict:
        """将统一行情行转为个股行情 dict。"""
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
            "quote_time": None,
            "data_source": "daily",
            "concept_names": list(concept_names or []),
        }

    def _limit_up_row_to_stock_dict(self, lr, candidate_source_tag: str = "涨停入选") -> Dict:
        """涨停榜行转个股行情（题材覆盖缺少日线明细时兜底）。"""
        tc = str(lr.get("ts_code", "")).strip()
        theme = lr.get("theme")
        theme_s = (
            str(theme).strip() if theme is not None and str(theme).strip() else "其他题材"
        )
        concept_names = self._get_ths_concept_names_for_stock(tc)
        if theme_s != "其他题材" and theme_s not in concept_names:
            concept_names.append(theme_s)
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
            "quote_time": None,
            "data_source": "daily",
            "concept_names": concept_names,
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
            {"ts_code": "000001.SH", "name": "上证指数", "close": 3420.0, "change_pct": 0.5, "volume": 350000000, "amount": 380000000000, "trade_date": trade_date, "quote_time": None, "data_source": "mock"},
            {"ts_code": "399001.SZ", "name": "深证成指", "close": 11500.0, "change_pct": 0.8, "volume": 450000000, "amount": 520000000000, "trade_date": trade_date, "quote_time": None, "data_source": "mock"},
            {"ts_code": "399006.SZ", "name": "创业板指", "close": 2400.0, "change_pct": 1.2, "volume": 180000000, "amount": 200000000000, "trade_date": trade_date, "quote_time": None, "data_source": "mock"},
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
        """获取当日个股行情列表。"""
        return self.get_stock_list_with_meta(trade_date, limit).get("rows", [])

    def _fetch_recent_stock_daily_df(self, trade_date: str) -> Dict[str, object]:
        """获取最近一个有 daily 个股数据的交易日明细。"""
        if not self.token:
            return {"df": None, "data_trade_date": trade_date, "used_mock": True}

        effective_trade_date = self._resolve_trade_date(trade_date)
        for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
            df = self.pro.daily(trade_date=data_trade_date)
            if df is None or df.empty:
                logger.warning(f"daily 个股数据为空（{data_trade_date}）")
                continue
            if data_trade_date != effective_trade_date:
                logger.info(
                    f"个股行情从 {effective_trade_date} 回退到最近有数据交易日 {data_trade_date}"
                )
            return {"df": df, "data_trade_date": data_trade_date, "used_mock": False}

        return {"df": None, "data_trade_date": effective_trade_date, "used_mock": False}

    def get_stock_list_with_meta(self, trade_date: str, limit: int = 100) -> Dict[str, object]:
        """获取个股行情列表，并返回实际使用的数据交易日。"""
        if not self.token:
            return {
                "rows": self._mock_stock_list(),
                "data_trade_date": trade_date,
                "used_mock": True,
            }

        try:
            payload = self._fetch_recent_stock_daily_df(trade_date)
            df = payload.get("df")
            effective_trade_date = str(payload.get("data_trade_date") or trade_date)
            if df is None or df.empty:
                return {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "used_mock": False,
                }

            stock_meta_map = self._get_stock_basic_snapshot_map()
            daily_basic_df = None
            daily_basic = getattr(self.pro, "daily_basic", None)
            if callable(daily_basic):
                try:
                    daily_basic_df = daily_basic(
                        trade_date=effective_trade_date,
                        fields="ts_code,turnover_rate,volume_ratio",
                    )
                except TypeError:
                    daily_basic_df = daily_basic(trade_date=effective_trade_date)

            source_df = self._build_daily_stock_source_df(
                df,
                stock_meta_map,
                daily_basic_df=daily_basic_df,
            )
            if source_df is None or source_df.empty:
                return {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "used_mock": False,
                }

            source_df = source_df.sort_values("pct_change", ascending=False).head(limit)

            result = []
            for _, row in source_df.iterrows():
                concept_names = self._get_ths_concept_names_for_stock(str(row["ts_code"]))
                result.append({
                    "ts_code": str(row["ts_code"]),
                    "stock_name": str(row.get("stock_name", row["ts_code"])),
                    "sector_name": str(row.get("industry", "未知")) or "未知",
                    "close": float(row.get("close") or 0),
                    "change_pct": float(row.get("pct_change") or 0),
                    "turnover_rate": float(row.get("turnover_rate") or 0),
                    "amount": float(row.get("amount") or 0),
                    "vol_ratio": float(row.get("volume_ratio") or 1),
                    "high": float(row.get("high") or 0),
                    "low": float(row.get("low") or 0),
                    "open": float(row.get("open") or 0),
                    "pre_close": float(row.get("pre_close") or 0),
                    "quote_time": None,
                    "data_source": "daily",
                    "concept_names": concept_names,
                })

            self._apply_realtime_overlay_to_stocks(result, trade_date)

            logger.info(
                f"个股列表（{payload.get('data_trade_date')}）: 共 {len(result)} 只"
            )
            return {
                "rows": result,
                "data_trade_date": effective_trade_date,
                "used_mock": False,
            }
        except Exception as e:
            logger.error(f"获取个股列表失败: {e}")
            return {
                "rows": [],
                "data_trade_date": trade_date,
                "used_mock": False,
            }

    def get_expanded_stock_list(
        self,
        trade_date: str,
        top_gainers: int = 100,
        vol_ratio_min: float = 2.5,
        pct_floor: float = -5.0,
    ) -> List[Dict]:
        """
        扩展候选池：合并三源后按 ts_code 去重。
        - A: daily 涨幅前 top_gainers
        - B: 当日全部涨停股（sector_name 用 limit_list_d.theme）
        - C: daily_basic 量比异动 vol_ratio >= vol_ratio_min 且 pct_change > pct_floor

        无 token 时回退为 _mock_stock_list。
        """
        return self.get_expanded_stock_list_with_meta(
            trade_date,
            top_gainers=top_gainers,
            vol_ratio_min=vol_ratio_min,
            pct_floor=pct_floor,
        ).get("rows", [])

    def get_expanded_stock_list_with_meta(
        self,
        trade_date: str,
        top_gainers: int = 100,
        vol_ratio_min: float = 2.5,
        pct_floor: float = -5.0,
    ) -> Dict[str, object]:
        """扩展候选池，并返回实际使用的数据交易日。"""
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        cache_key = f"{compact_trade_date}:{int(top_gainers)}:{float(vol_ratio_min):.4f}:{float(pct_floor):.4f}"
        cached = self._get_cached_expanded_stock_list(cache_key)
        if cached is not None:
            return cached

        if not self.token:
            payload = {
                "rows": self._mock_stock_list(),
                "data_trade_date": trade_date,
                "used_mock": True,
            }
            self._cache_expanded_stock_list(cache_key, payload, compact_trade_date, str(trade_date))
            return payload

        try:
            payload = self._fetch_recent_stock_daily_df(compact_trade_date)
            df = payload.get("df")
            effective_trade_date = str(payload.get("data_trade_date") or compact_trade_date)
            if df is None or df.empty:
                logger.warning(
                    f"扩展候选池无可用个股数据（截至 {effective_trade_date}）"
                )
                result = {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "used_mock": False,
                }
                self._cache_expanded_stock_list(cache_key, result, compact_trade_date, effective_trade_date)
                return result

            stock_meta_map = self._get_stock_basic_snapshot_map()
            daily_basic_df = None
            daily_basic = getattr(self.pro, "daily_basic", None)
            if callable(daily_basic):
                try:
                    daily_basic_df = daily_basic(
                        trade_date=effective_trade_date,
                        fields="ts_code,turnover_rate,volume_ratio",
                    )
                except TypeError:
                    daily_basic_df = daily_basic(trade_date=effective_trade_date)

            source_df = self._build_daily_stock_source_df(
                df,
                stock_meta_map,
                daily_basic_df=daily_basic_df,
            )
            if source_df is None or source_df.empty:
                logger.warning(
                    f"扩展候选池无可用个股数据（截至 {effective_trade_date}）"
                )
                result = {
                    "rows": [],
                    "data_trade_date": effective_trade_date,
                    "used_mock": False,
                }
                self._cache_expanded_stock_list(cache_key, result, compact_trade_date, effective_trade_date)
                return result

            by_code = source_df.set_index("ts_code", drop=False)
            merged: Dict[str, Dict] = {}

            # C: 量比异动（先放入，优先级最低）
            mask_c = (source_df["volume_ratio"] >= vol_ratio_min) & (
                source_df["pct_change"] > pct_floor
            )
            for _, row in source_df.loc[mask_c].iterrows():
                tc = str(row["ts_code"])
                concept_names = self._get_ths_concept_names_for_stock(tc)
                merged[tc] = {
                    "ts_code": tc,
                    "stock_name": str(row.get("stock_name", tc) or tc),
                    "sector_name": str(row.get("industry", "未知") or "未知"),
                    "close": float(row.get("close") or 0),
                    "change_pct": float(row.get("pct_change") or 0),
                    "turnover_rate": float(row.get("turnover_rate") or 0),
                    "amount": float(row.get("amount") or 0),
                    "vol_ratio": float(row.get("volume_ratio") or 1),
                    "high": float(row.get("high") or 0),
                    "low": float(row.get("low") or 0),
                    "open": float(row.get("open") or 0),
                    "pre_close": float(row.get("pre_close") or 0),
                    "candidate_source_tag": "量比异动",
                    "quote_time": None,
                    "data_source": "daily",
                    "concept_names": concept_names,
                }

            # A: 涨幅前列
            top_n = max(1, min(top_gainers, 300))
            top_df = source_df.sort_values("pct_change", ascending=False).head(top_n)
            for _, row in top_df.iterrows():
                tc = str(row["ts_code"])
                concept_names = self._get_ths_concept_names_for_stock(tc)
                if tc in merged:
                    if concept_names:
                        merged[tc]["concept_names"] = list(dict.fromkeys(
                            list(merged[tc].get("concept_names") or []) + concept_names
                        ))
                    merged[tc] = self._append_candidate_source(merged[tc], "涨幅前列")
                else:
                    merged[tc] = {
                        "ts_code": tc,
                        "stock_name": str(row.get("stock_name", tc) or tc),
                        "sector_name": str(row.get("industry", "未知") or "未知"),
                        "close": float(row.get("close") or 0),
                        "change_pct": float(row.get("pct_change") or 0),
                        "turnover_rate": float(row.get("turnover_rate") or 0),
                        "amount": float(row.get("amount") or 0),
                        "vol_ratio": float(row.get("volume_ratio") or 1),
                        "high": float(row.get("high") or 0),
                        "low": float(row.get("low") or 0),
                        "open": float(row.get("open") or 0),
                        "pre_close": float(row.get("pre_close") or 0),
                        "candidate_source_tag": "涨幅前列",
                        "quote_time": None,
                        "data_source": "daily",
                        "concept_names": concept_names,
                    }

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
                        concept_names = self._get_ths_concept_names_for_stock(tc)
                        if theme_s != "其他题材" and theme_s not in concept_names:
                            concept_names.append(theme_s)
                        if tc in merged:
                            merged[tc]["sector_name"] = theme_s
                            if concept_names:
                                merged[tc]["concept_names"] = list(dict.fromkeys(
                                    list(merged[tc].get("concept_names") or []) + concept_names
                                ))
                            merged[tc] = self._append_candidate_source(merged[tc], "涨停入选")
                        else:
                            merged[tc] = {
                                "ts_code": tc,
                                "stock_name": str(row.get("stock_name", tc) or tc),
                                "sector_name": theme_s,
                                "close": float(row.get("close") or 0),
                                "change_pct": float(row.get("pct_change") or 0),
                                "turnover_rate": float(row.get("turnover_rate") or 0),
                                "amount": float(row.get("amount") or 0),
                                "vol_ratio": float(row.get("volume_ratio") or 1),
                                "high": float(row.get("high") or 0),
                                "low": float(row.get("low") or 0),
                                "open": float(row.get("open") or 0),
                                "pre_close": float(row.get("pre_close") or 0),
                                "candidate_source_tag": "涨停入选",
                                "quote_time": None,
                                "data_source": "daily",
                                "concept_names": concept_names,
                            }
                    else:
                        merged[tc] = self._limit_up_row_to_stock_dict(lr, candidate_source_tag="涨停入选")

            result = list(merged.values())
            result.sort(key=lambda x: x["change_pct"], reverse=True)
            self._apply_realtime_overlay_to_stocks(result, trade_date)
            logger.info(
                f"扩展个股候选（{effective_trade_date}）: 共 {len(result)} 只 "
                f"(涨幅前{top_n}+涨停+量比≥{vol_ratio_min})"
            )
            response = {
                "rows": result,
                "data_trade_date": effective_trade_date,
                "used_mock": False,
            }
            self._cache_expanded_stock_list(cache_key, response, compact_trade_date, effective_trade_date)
            return copy.deepcopy(response)
        except Exception as e:
            logger.error(f"获取扩展个股列表失败: {e}")
            result = {
                "rows": [],
                "data_trade_date": compact_trade_date,
                "used_mock": False,
            }
            self._cache_expanded_stock_list(cache_key, result, compact_trade_date, compact_trade_date)
            return result

    def _get_cached_expanded_stock_list(self, cache_key: str) -> Optional[Dict[str, object]]:
        cache = getattr(self, "_expanded_stock_list_cache", None)
        if cache is None:
            cache = {}
            self._expanded_stock_list_cache = cache
        cached = cache.get(cache_key)
        if not cached:
            return None
        if time_module.time() - float(cached.get("fetched_at") or 0) > float(cached.get("ttl") or 0):
            cache.pop(cache_key, None)
            return None
        return copy.deepcopy(cached.get("payload") or {})

    def _cache_expanded_stock_list(
        self,
        cache_key: str,
        payload: Dict[str, object],
        request_trade_date: str,
        resolved_trade_date: str,
    ) -> None:
        cache = getattr(self, "_expanded_stock_list_cache", None)
        if cache is None:
            cache = {}
            self._expanded_stock_list_cache = cache
        ttl = (
            self.REALTIME_VOLUME_RATIO_CACHE_TTL_SECONDS
            if self._should_use_realtime_quote(request_trade_date)
            else self.EXPANDED_STOCK_LIST_CACHE_TTL_SECONDS
        )
        entry = {
            "fetched_at": time_module.time(),
            "ttl": ttl,
            "payload": copy.deepcopy(payload),
        }
        cache[cache_key] = entry
        compact_resolved_trade_date = str(resolved_trade_date).replace("-", "").strip()[:8]
        alias_key = cache_key.replace(f"{request_trade_date}:", f"{compact_resolved_trade_date}:")
        cache[alias_key] = entry

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
        detail = self._mock_stock_detail(ts_code)

        if not self.token:
            return self._overlay_realtime_detail(detail, trade_date)

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)

            stock_meta = (self._get_stock_basic_snapshot_map().get(ts_code) or {})
            if stock_meta:
                detail["stock_name"] = str(
                    stock_meta.get("stock_name") or detail["stock_name"] or ts_code
                )
                detail["sector_name"] = str(
                    stock_meta.get("industry") or detail["sector_name"] or "未知"
                )
            detail["concept_names"] = self._get_ths_concept_names_for_stock(ts_code)

            daily_basic = getattr(self.pro, "daily_basic", None)

            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df = self.pro.daily(
                    ts_code=ts_code,
                    start_date=data_trade_date,
                    end_date=data_trade_date,
                )
                if df is None or df.empty:
                    continue

                row = df.iloc[0]
                turnover_rate = float(row.get("vol", 0)) / 10000
                vol_ratio = 1.5
                if callable(daily_basic):
                    try:
                        basic_df = daily_basic(
                            ts_code=ts_code,
                            trade_date=data_trade_date,
                            fields="ts_code,turnover_rate,volume_ratio",
                        )
                    except TypeError:
                        basic_df = daily_basic(
                            ts_code=ts_code,
                            trade_date=data_trade_date,
                        )
                    if basic_df is not None and not basic_df.empty:
                        basic_row = basic_df.iloc[0]
                        turnover_rate = float(
                            basic_row.get("turnover_rate") or turnover_rate
                        )
                        vol_ratio = float(
                            basic_row.get("volume_ratio") or vol_ratio
                        )

                detail.update(
                    {
                        "close": float(row.get("close", 0)),
                        "change_pct": float(row.get("pct_chg", 0)),
                        "turnover_rate": turnover_rate,
                        "amount": float(row.get("amount", 0)),
                        "vol_ratio": vol_ratio,
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "open": float(row.get("open", 0)),
                        "pre_close": float(row.get("pre_close", 0)),
                        "data_source": "daily",
                    }
                )
                return self._overlay_realtime_detail(detail, trade_date)

            return self._overlay_realtime_detail(detail, trade_date)
        except Exception as e:
            logger.error(f"获取个股详情失败: {e}")
            return self._overlay_realtime_detail(detail, trade_date)

    def get_stock_quote_map(self, ts_codes: List[str], trade_date: str) -> Dict[str, Dict]:
        """批量获取个股行情详情，供持仓页等需要快速刷新现价的场景使用。"""
        normalized_codes = []
        for code in ts_codes:
            normalized = normalize_ts_code(code)
            if normalized and normalized not in normalized_codes:
                normalized_codes.append(normalized)

        if not normalized_codes:
            return {}

        compact_trade_date = str(trade_date).replace("-", "").strip()

        if not self.token:
            result = {
                code: self._overlay_realtime_detail(self._mock_stock_detail(code), compact_trade_date)
                for code in normalized_codes
            }
            return result

        try:
            payload = self._fetch_recent_stock_daily_df(compact_trade_date)
            daily_df = payload.get("df")
            effective_trade_date = str(payload.get("data_trade_date") or compact_trade_date)
            stock_meta_map = self._get_stock_basic_snapshot_map()

            daily_basic_df = None
            daily_basic = getattr(self.pro, "daily_basic", None)
            if callable(daily_basic):
                try:
                    daily_basic_df = daily_basic(
                        trade_date=effective_trade_date,
                        fields="ts_code,turnover_rate,volume_ratio",
                    )
                except TypeError:
                    daily_basic_df = daily_basic(trade_date=effective_trade_date)

            source_df = self._build_daily_stock_source_df(
                daily_df,
                stock_meta_map,
                daily_basic_df=daily_basic_df,
            )
            source_map: Dict[str, Dict] = {}
            if source_df is not None and not source_df.empty:
                filtered_df = source_df[source_df["ts_code"].isin(normalized_codes)]
                for _, row in filtered_df.iterrows():
                    source_map[str(row["ts_code"])] = {
                        "ts_code": str(row["ts_code"]),
                        "stock_name": str(row.get("stock_name") or row["ts_code"]),
                        "sector_name": str(row.get("industry") or "未知") or "未知",
                        "close": float(row.get("close") or 0),
                        "change_pct": float(row.get("pct_change") or 0),
                        "turnover_rate": float(row.get("turnover_rate") or 0),
                        "amount": float(row.get("amount") or 0),
                        "vol_ratio": float(row.get("volume_ratio") or 1),
                        "high": float(row.get("high") or 0),
                        "low": float(row.get("low") or 0),
                        "open": float(row.get("open") or 0),
                        "pre_close": float(row.get("pre_close") or 0),
                        "quote_time": None,
                        "data_source": "daily",
                    }

            for code in normalized_codes:
                if code in source_map:
                    continue
                stock_meta = stock_meta_map.get(code) or {}
                source_map[code] = {
                    **self._mock_stock_detail(code),
                    "stock_name": str(stock_meta.get("stock_name") or code),
                    "sector_name": str(stock_meta.get("industry") or "未知") or "未知",
                    "data_source": "daily_fallback",
                }

            rows = list(source_map.values())
            self._apply_realtime_overlay_to_stocks(rows, compact_trade_date)
            return {
                normalize_ts_code(row.get("ts_code", "")): row
                for row in rows
                if normalize_ts_code(row.get("ts_code", ""))
            }
        except Exception as e:
            logger.error(f"批量获取个股行情失败: {e}")
            return {
                code: self.get_stock_detail(code, compact_trade_date)
                for code in normalized_codes
            }

    def _overlay_realtime_detail(self, detail: Dict, trade_date: str) -> Dict:
        """对单只股票详情做盘中价格覆盖。"""
        if not detail:
            return detail
        if not self._should_use_realtime_quote(trade_date):
            detail.setdefault("data_source", "daily_fallback")
            return detail

        quote_map = self._fetch_realtime_quote_map([detail.get("ts_code", "")])
        realtime = quote_map.get(normalize_ts_code(detail.get("ts_code", "")))
        if not realtime:
            detail.setdefault("data_source", "daily_fallback")
            return detail

        intraday_volume_ratio = self._infer_intraday_volume_ratio(
            detail.get("ts_code", ""),
            trade_date,
            float(realtime.get("close") or 0),
            float(realtime.get("amount") or 0),
            float(realtime.get("volume") or 0),
            realtime.get("quote_time"),
        )

        detail.update(
            {
                "close": realtime["close"],
                "change_pct": realtime["change_pct"],
                "open": realtime["open"],
                "high": realtime["high"],
                "low": realtime["low"],
                "pre_close": realtime["pre_close"],
                "volume": realtime["volume"],
                "amount": realtime["amount"],
                "avg_price": realtime["avg_price"],
                "intraday_volume_ratio": intraday_volume_ratio,
                "quote_time": realtime["quote_time"],
                "data_source": realtime["data_source"],
            }
        )
        return detail

    def _infer_realtime_avg_price(
        self,
        price: float,
        amount: float,
        volume: float,
    ) -> Optional[float]:
        """从实时成交额/成交量推断盘中均价，兼容股/手两种量纲。"""
        if price <= 0 or amount <= 0 or volume <= 0:
            return None

        candidates = []
        raw_avg = amount / volume
        hand_avg = amount / (volume * 100)
        for candidate in (raw_avg, hand_avg):
            if candidate <= 0:
                continue
            deviation = abs(candidate - price) / price
            if deviation <= 0.35:
                candidates.append((deviation, candidate))

        if not candidates:
            return None
        return round(min(candidates, key=lambda item: item[0])[1], 2)

    def _normalize_realtime_volume_to_daily_unit(
        self,
        price: float,
        amount: float,
        volume: float,
    ) -> Optional[float]:
        """将实时成交量尽量归一到日线 vol 的“手”口径。"""
        if price <= 0 or amount <= 0 or volume <= 0:
            return None

        raw_avg = amount / volume
        hand_avg = amount / (volume * 100)
        raw_deviation = abs(raw_avg - price) / price
        hand_deviation = abs(hand_avg - price) / price
        if raw_deviation <= hand_deviation:
            return volume / 100
        return volume

    def _intraday_elapsed_ratio(
        self,
        quote_time: Optional[str],
        trade_date: str,
    ) -> Optional[float]:
        """估算 A 股当日盘中已完成的成交时间比例。"""
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        if not compact_trade_date:
            return None

        timestamp = None
        if quote_time:
            try:
                timestamp = datetime.strptime(quote_time, "%Y-%m-%d %H:%M:%S")
                timestamp = timestamp.replace(tzinfo=self.SH_TZ)
            except Exception:
                timestamp = None
        if timestamp is None:
            now = self._now_sh()
            if compact_trade_date != now.strftime("%Y%m%d"):
                return None
            timestamp = now

        minutes = timestamp.hour * 60 + timestamp.minute
        morning_open = 9 * 60 + 30
        morning_close = 11 * 60 + 30
        afternoon_open = 13 * 60
        afternoon_close = 15 * 60

        if minutes < morning_open:
            return None
        if minutes <= morning_close:
            elapsed = minutes - morning_open
        elif minutes < afternoon_open:
            elapsed = 120
        elif minutes <= afternoon_close:
            elapsed = 120 + (minutes - afternoon_open)
        else:
            elapsed = 240

        if elapsed <= 0:
            return None
        return min(max(elapsed / 240, 0.0), 1.0)

    def _recent_average_daily_volume(
        self,
        ts_code: str,
        trade_date: str,
        lookback: int = 5,
    ) -> Optional[float]:
        """获取近若干已完成交易日的平均成交量（手）。"""
        cache = getattr(self, "_intraday_volume_ratio_cache", None)
        if cache is None:
            cache = {}
            self._intraday_volume_ratio_cache = cache

        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        cache_key = f"{normalize_ts_code(ts_code)}:{compact_trade_date}:{lookback}"
        cached = cache.get(cache_key)
        ttl = getattr(self, "REALTIME_VOLUME_RATIO_CACHE_TTL_SECONDS", 60)
        now_ts = time_module.time()
        if cached and now_ts - cached["fetched_at"] <= ttl:
            return cached["value"]

        if not getattr(self, "token", None) or not getattr(self, "pro", None):
            return None

        try:
            effective_trade_date = self._resolve_trade_date(compact_trade_date)
            open_dates = self._recent_open_dates(effective_trade_date, count=lookback + 1)
            query_dates = open_dates[1:] if len(open_dates) > 1 else open_dates
            if not query_dates:
                return None

            df = self.pro.daily(
                ts_code=normalize_ts_code(ts_code),
                start_date=query_dates[-1],
                end_date=query_dates[0],
            )
            if df is None or df.empty or "vol" not in df.columns:
                return None

            work = df.copy()
            if "trade_date" in work.columns:
                work["trade_date"] = work["trade_date"].astype(str)
                work = work[work["trade_date"].isin(query_dates)]

            volumes = [
                float(value)
                for value in work.get("vol", [])
                if float(value or 0) > 0
            ]
            if not volumes:
                return None

            value = round(sum(volumes[:lookback]) / min(len(volumes), lookback), 2)
            cache[cache_key] = {"fetched_at": now_ts, "value": value}
            return value
        except Exception as e:
            logger.debug(f"计算近端日均量失败 {ts_code}: {e}")
            return None

    def _infer_intraday_volume_ratio(
        self,
        ts_code: str,
        trade_date: str,
        price: float,
        amount: float,
        volume: float,
        quote_time: Optional[str],
    ) -> Optional[float]:
        """基于实时成交量与近端均量，估算盘中实时相对放量。"""
        normalized_volume = self._normalize_realtime_volume_to_daily_unit(price, amount, volume)
        if normalized_volume is None:
            return None

        elapsed_ratio = self._intraday_elapsed_ratio(quote_time, trade_date)
        if elapsed_ratio is None or elapsed_ratio <= 0:
            return None

        avg_daily_volume = self._recent_average_daily_volume(ts_code, trade_date)
        if avg_daily_volume is None or avg_daily_volume <= 0:
            return None

        expected_volume = avg_daily_volume * elapsed_ratio
        if expected_volume <= 0:
            return None

        return round(normalized_volume / expected_volume, 2)

    # ========== Mock 数据 ==========

    def _mock_stock_list(self) -> List[Dict]:
        """模拟个股列表"""
        return [
            {"ts_code": "000001.SZ", "stock_name": "平安银行", "sector_name": "银行", "close": 12.5, "change_pct": 3.5, "turnover_rate": 8.5, "amount": 350000, "vol_ratio": 1.8, "high": 12.8, "low": 12.1, "open": 12.2, "pre_close": 12.1, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "000002.SZ", "stock_name": "万 科A", "sector_name": "房地产", "close": 8.2, "change_pct": 5.2, "turnover_rate": 15.0, "amount": 520000, "vol_ratio": 2.5, "high": 8.5, "low": 7.9, "open": 7.9, "pre_close": 7.8, "candidate_source_tag": "涨幅前列/量比异动", "quote_time": None, "data_source": "mock"},
            {"ts_code": "600036.SH", "stock_name": "招商银行", "sector_name": "银行", "close": 35.0, "change_pct": 2.0, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.5, "high": 35.5, "low": 34.2, "open": 34.3, "pre_close": 34.3, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "600519.SH", "stock_name": "贵州茅台", "sector_name": "白酒", "close": 1850.0, "change_pct": 1.2, "turnover_rate": 0.8, "amount": 450000, "vol_ratio": 1.2, "high": 1860.0, "low": 1820.0, "open": 1825.0, "pre_close": 1828.0, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "300750.SZ", "stock_name": "宁德时代", "sector_name": "新能源汽车", "close": 185.0, "change_pct": 4.5, "turnover_rate": 12.0, "amount": 680000, "vol_ratio": 2.2, "high": 188.0, "low": 178.0, "open": 178.0, "pre_close": 177.0, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "002594.SZ", "stock_name": "比亚迪", "sector_name": "新能源汽车", "close": 265.0, "change_pct": 3.8, "turnover_rate": 6.5, "amount": 420000, "vol_ratio": 1.6, "high": 268.0, "low": 258.0, "open": 258.0, "pre_close": 255.0, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "000858.SZ", "stock_name": "五粮液", "sector_name": "白酒", "close": 168.0, "change_pct": 2.1, "turnover_rate": 3.5, "amount": 280000, "vol_ratio": 1.3, "high": 170.0, "low": 165.0, "open": 165.0, "pre_close": 164.5, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "600900.SH", "stock_name": "长江电力", "sector_name": "电力", "close": 23.5, "change_pct": 0.5, "turnover_rate": 1.2, "amount": 150000, "vol_ratio": 1.0, "high": 23.8, "low": 23.2, "open": 23.3, "pre_close": 23.4, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "601318.SH", "stock_name": "中国平安", "sector_name": "保险", "close": 48.5, "change_pct": 1.8, "turnover_rate": 2.5, "amount": 320000, "vol_ratio": 1.4, "high": 49.0, "low": 47.8, "open": 47.8, "pre_close": 47.6, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "000333.SZ", "stock_name": "美的集团", "sector_name": "家电", "close": 62.0, "change_pct": 2.5, "turnover_rate": 4.0, "amount": 250000, "vol_ratio": 1.5, "high": 63.0, "low": 61.0, "open": 61.0, "pre_close": 60.5, "candidate_source_tag": "涨幅前列", "quote_time": None, "data_source": "mock"},
            {"ts_code": "002475.SZ", "stock_name": "立讯精密", "sector_name": "电子", "close": 35.0, "change_pct": 6.5, "turnover_rate": 18.0, "amount": 580000, "vol_ratio": 3.0, "high": 36.0, "low": 33.5, "open": 33.5, "pre_close": 32.8, "candidate_source_tag": "涨幅前列/量比异动", "quote_time": None, "data_source": "mock"},
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
                    "quote_time": None,
                    "data_source": "mock",
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
            "quote_time": None,
            "data_source": "mock",
        }


# 全局客户端实例
tushare_client = TushareClient()
