"""
Tushare 数据客户端
"""
import asyncio
import copy
import json
import os
import re
import threading
import time as time_module
from datetime import datetime, time
from zoneinfo import ZoneInfo
import httpx
import requests
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


def is_sector_scan_board_eligible(ts_code: str) -> bool:
    """
    板块扫描仅纳入主板/创业板/科创板，即保留 SH/SZ，排除北交所 .BJ。
    """
    normalized = normalize_ts_code(str(ts_code or "").strip())
    if not normalized:
        return False
    return not normalized.endswith(".BJ")


class TushareClient:
    """Tushare API 客户端"""

    SH_TZ = ZoneInfo("Asia/Shanghai")
    REALTIME_SESSION_START = time(9, 15)
    REALTIME_SESSION_END = time(15, 0)
    EOD_DATA_READY_TIME = time(19, 0)
    REALTIME_CHUNK_SIZE = 50
    REALTIME_SOURCE = "sina"
    REALTIME_MARKET_CACHE_TTL_SECONDS = 20
    REALTIME_MARKET_STALE_TTL_SECONDS = 180
    REALTIME_MARKET_FAILURE_COOLDOWN_SECONDS = 60
    REALTIME_VOLUME_RATIO_CACHE_TTL_SECONDS = 60
    REALTIME_MARKET_MIN_TOTAL = 3000
    REALTIME_CANDIDATE_MIN_TOTAL = 80
    REALTIME_AGGREGATE_TIMEOUT_SECONDS = 5.0
    HOT_SECTOR_CACHE_TTL_SECONDS = 30
    STOCK_DETAIL_INTRADAY_CACHE_TTL_SECONDS = 20
    STOCK_DETAIL_HISTORY_CACHE_TTL_SECONDS = 6 * 60 * 60
    STOCK_DETAIL_QUOTA_COOLDOWN_SECONDS = 15 * 60
    STOCK_BASIC_CACHE_TTL_SECONDS = 6 * 60 * 60
    EXPANDED_STOCK_LIST_CACHE_TTL_SECONDS = 5 * 60
    TRADE_DATE_RESOLUTION_CACHE_TTL_SECONDS = 6 * 60 * 60
    RECENT_OPEN_DATES_CACHE_TTL_SECONDS = 6 * 60 * 60
    DAILY_API_INTRADAY_CACHE_TTL_SECONDS = 60
    DAILY_API_HISTORY_CACHE_TTL_SECONDS = 6 * 60 * 60
    LOCAL_THS_SNAPSHOT_RELOAD_COOLDOWN_SECONDS = 30

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
        self._realtime_market_state_cache = {
            "trade_date": "",
            "fetched_at": 0.0,
            "snapshot": None,
        }
        self._realtime_market_source_cooldowns = {}
        self._realtime_market_fetch_lock = threading.Lock()
        self._recent_open_dates_lock = threading.Lock()
        self._sina_hot_sector_cache = {
            "cache_key": "",
            "fetched_at": 0.0,
            "snapshot": None,
        }
        self._stock_basic_industry_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._stock_detail_cache = {}
        self._stock_detail_quota_state = {
            "limited_until": 0.0,
            "message": "",
        }
        self._stock_basic_snapshot_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._intraday_volume_ratio_cache = {}
        self._recent_open_dates_cache = {}
        self._ths_concept_index_cache = {
            "fetched_at": 0.0,
            "mapping": {},
        }
        self._ths_member_by_stock_cache = {}
        self._local_ths_concept_snapshot = {
            "loaded": False,
            "loaded_at": 0.0,
            "sync_trade_date": "",
            "index_map": {},
            "stock_to_codes": {},
        }
        self._local_ths_concept_snapshot_lock = threading.Lock()
        self._expanded_stock_list_cache = {}
        self._trade_date_resolution_cache = {}
        self._daily_api_cache = {}
        self._daily_basic_api_cache = {}
        self._index_daily_api_cache = {}
        self._realtime_quote_cache = {}

    def _now_sh(self) -> datetime:
        """获取上海时区当前时间。"""
        return datetime.now(self.SH_TZ)

    def _should_use_realtime_quote(self, trade_date: str) -> bool:
        """
        当前请求是否适合尝试个股实时/收盘快照行情。

        仅在：
        - 已配置 token
        - 请求日期等于上海时区今天
        - 交易日工作日
        - 09:15 ~ 19:00
        时尝试实时覆盖；15:00 后优先拿收盘快照，19:00 后切回稳定日线。
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
        return self.REALTIME_SESSION_START <= current_time < self.EOD_DATA_READY_TIME

    def _should_use_market_snapshot(self, trade_date: str) -> bool:
        """
        当前请求是否适合尝试市场状态快照。

        用于市场环境页这类聚合指标：
        - 09:15 ~ 15:00：盘中实时
        - 15:00 ~ 19:00：收盘后快照
        - 19:00 之后：改走稳定日线
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
        return self.REALTIME_SESSION_START <= current_time < self.EOD_DATA_READY_TIME

    def get_last_completed_trade_date(self, trade_date: str) -> str:
        """
        获取最近一个“已完成”的交易日。

        用于需要稳定日线输出的场景：
        - 若请求的是今天且当前尚未到日线稳定时间，则回退到上一交易日
        - 其他情况沿用最近开市日
        """
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        effective_trade_date = self._resolve_trade_date(compact_trade_date) if self.token else compact_trade_date

        now = self._now_sh()
        if (
            compact_trade_date == now.strftime("%Y%m%d")
            and now.weekday() < 5
            and now.time() < self.EOD_DATA_READY_TIME
        ):
            recent_dates = self._recent_open_dates(effective_trade_date, count=2)
            if len(recent_dates) >= 2:
                return recent_dates[1]

        return effective_trade_date

    def _fetch_realtime_stock_quote_map(self, ts_codes: List[str]) -> Dict[str, Dict]:
        """个股实时行情统一走 realtime_quote。"""
        return self._fetch_realtime_quote_map(ts_codes)

    def _empty_realtime_market_state(
        self,
        trade_date: str,
        *,
        status: str,
        data_source: str,
        quote_time: Optional[str] = None,
        stale_from_quote_time: Optional[str] = None,
        market_turnover: Optional[float] = None,
        up_down_ratio: Optional[Dict[str, int]] = None,
        limit_stats: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        compact_trade_date = str(trade_date).replace("-", "")[:8]
        return {
            "market_turnover": market_turnover,
            "up_down_ratio": up_down_ratio or {"up": 0, "down": 0, "flat": 0, "total": 0},
            "limit_stats": limit_stats or {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "broken_board_rate": 0.0,
            },
            "data_trade_date": compact_trade_date,
            "quote_time": quote_time,
            "data_source": data_source,
            "status": status,
            "is_stale": status == "stale",
            "stale_from_quote_time": stale_from_quote_time,
        }

    def _build_realtime_market_state(
        self,
        trade_date: str,
        *,
        market_turnover: float,
        up_down_ratio: Dict[str, int],
        limit_stats: Dict[str, object],
        quote_time: Optional[str],
        data_source: str,
        status: str = "live",
        stale_from_quote_time: Optional[str] = None,
    ) -> Dict[str, object]:
        state = self._empty_realtime_market_state(
            trade_date,
            status=status,
            data_source=data_source,
            quote_time=quote_time,
            stale_from_quote_time=stale_from_quote_time,
            market_turnover=market_turnover,
            up_down_ratio=up_down_ratio,
            limit_stats=limit_stats,
        )
        state["is_stale"] = status == "stale"
        return state

    def _iter_realtime_sources(self, primary: Optional[str] = None) -> List[str]:
        """返回实时源尝试顺序，优先主源，不重复。"""
        base = str(primary or self.REALTIME_SOURCE or "sina").strip().lower() or "sina"
        sources = [base]
        for candidate in ("dc", "sina"):
            if candidate not in sources:
                sources.append(candidate)
        return sources

    def _is_realtime_source_in_cooldown(self, source_key: str) -> bool:
        cooldowns = getattr(self, "_realtime_market_source_cooldowns", None) or {}
        until_ts = float(cooldowns.get(source_key) or 0.0)
        return until_ts > time_module.monotonic()

    def _mark_realtime_source_failure(self, source_key: str) -> None:
        cooldowns = getattr(self, "_realtime_market_source_cooldowns", None)
        if cooldowns is None:
            cooldowns = {}
            self._realtime_market_source_cooldowns = cooldowns
        cooldowns[source_key] = time_module.monotonic() + self.REALTIME_MARKET_FAILURE_COOLDOWN_SECONDS

    def _clear_realtime_source_failure(self, source_key: str) -> None:
        cooldowns = getattr(self, "_realtime_market_source_cooldowns", None) or {}
        cooldowns.pop(source_key, None)

    def _normalize_public_aggregate_row(self, row: Dict[str, object]) -> Optional[Dict[str, object]]:
        code = str(row.get("f12") or "").strip()
        ts_code = normalize_ts_code(code)
        if not ts_code or ts_code.endswith(".BJ"):
            return None

        def as_float(value):
            try:
                if value in ("-", None, ""):
                    return 0.0
                return float(value)
            except Exception:
                return 0.0

        return {
            "TS_CODE": ts_code,
            "NAME": str(row.get("f14") or "").strip(),
            "PRICE": as_float(row.get("f2")),
            "PCT_CHANGE": as_float(row.get("f3")),
            "VOLUME": as_float(row.get("f5")),
            "AMOUNT": as_float(row.get("f6")),
            "TURNOVER_RATE": as_float(row.get("f8")),
            "HIGH": as_float(row.get("f15")),
            "LOW": as_float(row.get("f16")),
            "OPEN": as_float(row.get("f17")),
            "CLOSE": as_float(row.get("f18")),
        }

    def _extract_cls_limit_stats_from_html(self, html: str) -> Optional[Dict[str, object]]:
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html or "",
            re.S,
        )
        if not match:
            return None

        try:
            payload = json.loads(match.group(1))
        except Exception:
            return None

        page_props = (((payload or {}).get("props") or {}).get("initialProps") or {}).get("pageProps") or {}
        quote_limit = page_props.get("quoteLimit") or {}
        brief = str(quote_limit.get("brief") or "").strip()
        if not brief:
            return None

        limit_up_match = re.search(r"涨停数量为\s*(\d+)\s*家", brief)
        limit_down_match = re.search(r"跌停数量为\s*(\d+)\s*家", brief)
        broken_board_match = re.search(r"炸板率\s*(\d+(?:\.\d+)?)\s*%", brief)

        if not any((limit_up_match, limit_down_match, broken_board_match)):
            return None

        return {
            "limit_up_count": int(limit_up_match.group(1)) if limit_up_match else None,
            "limit_down_count": int(limit_down_match.group(1)) if limit_down_match else None,
            "broken_board_rate": float(broken_board_match.group(1)) if broken_board_match else None,
            "estimated": False,
        }

    def _parse_jsonp_payload(self, text: str) -> Optional[Dict[str, object]]:
        body = str(text or "").strip()
        if not body:
            return None
        body = re.sub(r"^/\*.*?\*/", "", body, flags=re.S).strip()
        match = re.search(r"^[^(]+\((.*)\)\s*;?\s*$", body, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    def _parse_sina_up_down_distribution(self, text: str) -> Optional[Dict[str, int]]:
        match = re.search(r'var\s+hq_str_zdp_updown="([^"]+)"', text or "")
        if not match:
            return None

        parts = [item.strip() for item in match.group(1).split(",")]
        if len(parts) < 13:
            return None

        try:
            buckets = [int(float(item or 0)) for item in parts[2:-1]]
        except Exception:
            return None

        if len(buckets) != 11:
            return None

        up = sum(buckets[:5])
        flat = buckets[5]
        down = sum(buckets[6:])
        return {
            "up": up,
            "down": down,
            "flat": flat,
            "total": up + flat + down,
        }

    def _normalize_sina_symbol(self, symbol: str) -> Optional[str]:
        raw = str(symbol or "").strip().lower()
        if not raw:
            return None
        if raw.startswith(("sh", "sz", "bj")) and raw[2:].isdigit():
            return normalize_ts_code(f"{raw[2:]}.{raw[:2].upper()}")
        normalized = normalize_ts_code(raw.upper())
        return normalized or None

    def _normalize_sina_plate_item(self, row: Dict[str, object], source_type: str) -> Optional[Dict[str, object]]:
        sector_name = str(row.get("category_cn") or "").strip()
        if not sector_name:
            return None
        try:
            sector_change_pct = round(float(row.get("percent") or 0.0), 2)
        except Exception:
            sector_change_pct = 0.0
        try:
            stock_count = int(float(row.get("sym_count") or 0))
        except Exception:
            stock_count = 0
        quote_time = str(row.get("time") or "").strip() or None
        return {
            "sector_id": str(row.get("id") or "").strip() or None,
            "sector_name": sector_name,
            "sector_source_type": source_type,
            "sector_change_pct": sector_change_pct,
            "leader_stock_name": str(row.get("lead_cname") or "").strip() or None,
            "leader_stock_ts_code": self._normalize_sina_symbol(row.get("lead_shares")),
            "stock_count": stock_count,
            "quote_time": quote_time,
            "data_source": "sina_hot_sector",
        }

    def _fetch_sina_plate_list(
        self,
        session: requests.Session,
        plate: str,
        *,
        limit: int = 5,
    ) -> List[Dict[str, object]]:
        response = session.get(
            "https://gu.sina.cn/hq/api/openapi.php/StockV2Service.getPlateList",
            params={
                "num": str(limit),
                "page": "1",
                "sort": "percent",
                "asc": "0",
                "dpc": "1",
                "plate": plate,
            },
            timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        rows = (((payload or {}).get("result") or {}).get("data") or {}).get("data") or []
        return rows if isinstance(rows, list) else []

    def get_sina_hot_sector_boards(
        self,
        trade_date: str,
        *,
        limit: int = 5,
        refresh: bool = False,
    ) -> Dict[str, object]:
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        display_trade_date = (
            f"{compact_trade_date[:4]}-{compact_trade_date[4:6]}-{compact_trade_date[6:8]}"
            if len(compact_trade_date) == 8
            else str(trade_date)
        )
        cache_key = f"{display_trade_date}:{int(limit)}"
        cache = getattr(self, "_sina_hot_sector_cache", None)
        if cache is None:
            cache = {"cache_key": "", "fetched_at": 0.0, "snapshot": None}
            self._sina_hot_sector_cache = cache

        if (
            not refresh
            and cache.get("cache_key") == cache_key
            and time_module.monotonic() - float(cache.get("fetched_at") or 0.0) <= self.HOT_SECTOR_CACHE_TTL_SECONDS
            and cache.get("snapshot")
        ):
            return copy.deepcopy(cache["snapshot"])

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.sina.cn/#/index/index",
        })

        plate_mapping = (
            ("all", "leader", "leader_boards"),
            ("sw2", "industry", "industry_boards"),
            ("chgn", "concept", "concept_boards"),
        )
        payload: Dict[str, object] = {
            "trade_date": display_trade_date,
            "resolved_trade_date": display_trade_date,
            "data_source": "sina_hot_sector",
            "leader_boards": [],
            "industry_boards": [],
            "concept_boards": [],
        }
        quote_times: List[str] = []

        for plate, source_type, target_key in plate_mapping:
            try:
                rows = self._fetch_sina_plate_list(session, plate, limit=limit)
            except Exception as e:
                logger.warning(f"新浪热门板块拉取失败（plate={plate}）: {e}")
                rows = []

            normalized_rows = []
            for row in rows:
                normalized = self._normalize_sina_plate_item(row, source_type)
                if normalized:
                    normalized_rows.append(normalized)
                    if normalized.get("quote_time"):
                        quote_times.append(str(normalized["quote_time"]))
            payload[target_key] = normalized_rows

        if quote_times:
            latest_quote_time = max(quote_times)
            payload["resolved_trade_date"] = latest_quote_time[:10]

        cache["cache_key"] = cache_key
        cache["fetched_at"] = time_module.monotonic()
        cache["snapshot"] = copy.deepcopy(payload)
        return payload

    def _fetch_sina_market_overview_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """通过新浪行情中心页面背后的开放接口获取市场概览。"""
        if self._is_realtime_source_in_cooldown("sina_overview"):
            return None

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.sina.cn/#/index/index",
        }
        session = requests.Session()
        session.headers.update(headers)

        try:
            rise_fall_resp = session.get(
                "https://gu.sina.cn/cn/api/openapi.php/CN_ZhendapanService.getRiseFall?type=1&callback=cb",
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
            )
            rise_fall_resp.raise_for_status()
            rise_fall_payload = self._parse_jsonp_payload(rise_fall_resp.text) or {}
            rise_fall_rows = (((rise_fall_payload.get("result") or {}).get("data") or {}).get("rise_fall")) or []
            rise_fall_latest = rise_fall_rows[0] if rise_fall_rows else {}

            amount_resp = session.get(
                "https://gu.sina.cn/hq/api/openapi.php/ZhenMinAmtService.getTodayDataForGraph?&callback=cb",
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
            )
            amount_resp.raise_for_status()
            amount_payload = self._parse_jsonp_payload(amount_resp.text) or {}
            latest_amount = ((((amount_payload.get("result") or {}).get("data") or {}).get("latest_data")) or {})

            updown_resp = session.get(
                "https://hq.sinajs.cn/list=zdp_updown",
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
            )
            updown_resp.raise_for_status()
            up_down_ratio = self._parse_sina_up_down_distribution(updown_resp.text)
        except Exception as e:
            self._mark_realtime_source_failure("sina_overview")
            logger.warning(f"新浪市场概览接口拉取失败: {e}")
            return None

        if not rise_fall_latest or not latest_amount or not up_down_ratio:
            self._mark_realtime_source_failure("sina_overview")
            logger.warning("新浪市场概览接口返回不完整，转入其他实时源")
            return None

        def as_float(value):
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        limit_up_count = int(float(rise_fall_latest.get("rise") or 0))
        limit_down_count = int(float(rise_fall_latest.get("fall") or 0))
        broken_board_count = int(float(rise_fall_latest.get("zhaban") or 0))
        denominator = limit_up_count + broken_board_count
        broken_board_rate = round(broken_board_count / denominator * 100, 2) if denominator > 0 else 0.0
        market_turnover = round((as_float(latest_amount.get("sh_amount")) + as_float(latest_amount.get("sz_amount"))) / 100000000, 2)
        ticktime = str(latest_amount.get("ticktime") or rise_fall_latest.get("tradetime") or "").strip()
        quote_date = str(latest_amount.get("opendate") or rise_fall_latest.get("day") or "").strip()
        quote_time = None
        if quote_date and ticktime:
            quote_time = f"{quote_date} {ticktime}"

        self._clear_realtime_source_failure("sina_overview")
        return self._build_realtime_market_state(
            trade_date,
            market_turnover=market_turnover,
            up_down_ratio=up_down_ratio,
            limit_stats={
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "broken_board_rate": broken_board_rate,
                "estimated": False,
            },
            quote_time=quote_time,
            data_source="realtime_sina_overview",
            status="live",
        )

    def _stock_detail_cache_ttl(self, trade_date: str) -> int:
        return (
            self.STOCK_DETAIL_INTRADAY_CACHE_TTL_SECONDS
            if self._should_use_realtime_quote(trade_date)
            else self.STOCK_DETAIL_HISTORY_CACHE_TTL_SECONDS
        )

    def _log_tushare_api_call(
        self,
        api_name: str,
        *,
        trade_date: Optional[str] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> None:
        compact_trade_date = str(trade_date or "").replace("-", "").strip()[:8] or "-"
        extra = extra or {}
        extra_parts = [
            f"{key}={value}"
            for key, value in extra.items()
            if value not in (None, "", [])
        ]
        extra_text = f" {' '.join(extra_parts)}" if extra_parts else ""
        logger.info(
            "Tushare 调用 api={} trade_date=<yellow>【{}】</yellow>{}",
            api_name,
            compact_trade_date,
            extra_text,
        )

    def _call_pro_trade_cal(
        self,
        *,
        exchange: str,
        start_date: str,
        end_date: str,
        fields: str,
    ):
        self._log_tushare_api_call(
            "pro.trade_cal",
            trade_date=end_date,
            extra={"exchange": exchange, "start_date": start_date, "end_date": end_date},
        )
        return self.pro.trade_cal(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            fields=fields,
        )

    def _call_pro_stock_basic(
        self,
        *,
        ts_code: Optional[str] = None,
        fields: Optional[str] = None,
    ):
        self._log_tushare_api_call(
            "pro.stock_basic",
            extra={"ts_code": normalize_ts_code(ts_code or ""), "fields": fields},
        )
        if fields is None:
            return self.pro.stock_basic(ts_code=ts_code)
        return self.pro.stock_basic(ts_code=ts_code, fields=fields)

    def _call_pro_limit_list_d(
        self,
        *,
        trade_date: str,
        limit_type: str,
    ):
        self._log_tushare_api_call(
            "pro.limit_list_d",
            trade_date=trade_date,
            extra={"limit_type": limit_type},
        )
        return self.pro.limit_list_d(
            trade_date=trade_date,
            limit_type=limit_type,
        )

    def _call_pro_ths_index(self, **kwargs):
        self._log_tushare_api_call("pro.ths_index", extra=kwargs)
        return self.pro.ths_index(**kwargs)

    def _call_pro_ths_member(
        self,
        *,
        ts_code: Optional[str] = None,
        con_code: Optional[str] = None,
    ):
        normalized_ts_code = str(ts_code or "").strip()
        normalized_con_code = normalize_ts_code(con_code or "")
        self._log_tushare_api_call(
            "pro.ths_member",
            extra={"ts_code": normalized_ts_code, "con_code": normalized_con_code},
        )
        kwargs = {}
        if normalized_ts_code:
            kwargs["ts_code"] = normalized_ts_code
        if normalized_con_code:
            kwargs["con_code"] = normalized_con_code
        return self.pro.ths_member(**kwargs)

    def _call_pro_ths_daily(self, *, trade_date: str):
        self._log_tushare_api_call("pro.ths_daily", trade_date=trade_date)
        return self.pro.ths_daily(trade_date=trade_date)

    def load_local_ths_concept_snapshot(
        self,
        *,
        index_map: Dict[str, Dict[str, str]],
        stock_to_codes: Dict[str, List[str]],
        sync_trade_date: str = "",
        loaded: bool = True,
    ) -> None:
        """装载数据库中的 THS 概念映射，供同步调用链直接读取。"""
        self._local_ths_concept_snapshot = {
            "loaded": bool(loaded),
            "loaded_at": time_module.time(),
            "sync_trade_date": str(sync_trade_date or "").replace("-", "").strip(),
            "index_map": copy.deepcopy(index_map or {}),
            "stock_to_codes": copy.deepcopy(stock_to_codes or {}),
        }

    def _run_coroutine_sync(self, coroutine):
        """在同步调用链中安全执行异步数据库查询。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        payload: Dict[str, object] = {}

        def _runner() -> None:
            try:
                payload["result"] = asyncio.run(coroutine)
            except Exception as exc:  # pragma: no cover - 线程分支由集成路径覆盖
                payload["error"] = exc

        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join()
        if "error" in payload:
            raise payload["error"]  # type: ignore[misc]
        return payload.get("result")

    async def _load_local_ths_concept_snapshot_from_db_async(self) -> Optional[Dict[str, object]]:
        """从数据库读取当前激活的 THS 概念快照。"""
        from collections import defaultdict

        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.ths_concept_index import ThsConceptIndex
        from app.models.ths_concept_member import ThsConceptMember
        from app.models.ths_concept_sync_state import ThsConceptSyncState

        async with async_session_factory() as session:
            state_result = await session.execute(
                select(ThsConceptSyncState).where(ThsConceptSyncState.sync_key == "ths_concept")
            )
            state = state_result.scalar_one_or_none()
            active_trade_date = str(getattr(state, "active_trade_date", "") or "").strip()
            if not active_trade_date:
                return None

            index_result = await session.execute(
                select(ThsConceptIndex).where(ThsConceptIndex.sync_trade_date == active_trade_date)
            )
            member_result = await session.execute(
                select(ThsConceptMember).where(ThsConceptMember.sync_trade_date == active_trade_date)
            )
            index_rows = index_result.scalars().all()
            member_rows = member_result.scalars().all()

        index_map: Dict[str, Dict[str, str]] = {}
        stock_to_codes: Dict[str, List[str]] = defaultdict(list)
        for row in index_rows:
            concept_code = str(row.ts_code or "").strip()
            if not concept_code:
                continue
            index_map[concept_code] = {
                "name": str(row.concept_name or "").strip(),
                "type": str(row.ths_type or "").strip(),
            }
        for row in member_rows:
            stock_code = normalize_ts_code(str(row.stock_code or "").strip())
            concept_code = str(row.concept_code or "").strip()
            if not stock_code or not concept_code:
                continue
            if concept_code not in stock_to_codes[stock_code]:
                stock_to_codes[stock_code].append(concept_code)

        if not index_map:
            return None
        return {
            "sync_trade_date": active_trade_date,
            "index_map": index_map,
            "stock_to_codes": dict(stock_to_codes),
        }

    def _ensure_local_ths_concept_snapshot_loaded(self) -> bool:
        """未装载时尝试从数据库懒加载本地 THS 概念快照。"""
        local_snapshot = getattr(self, "_local_ths_concept_snapshot", None) or {}
        if local_snapshot.get("loaded"):
            return True

        now_ts = time_module.time()
        if (
            now_ts - float(local_snapshot.get("loaded_at") or 0)
            < self.LOCAL_THS_SNAPSHOT_RELOAD_COOLDOWN_SECONDS
        ):
            return False

        lock = getattr(self, "_local_ths_concept_snapshot_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._local_ths_concept_snapshot_lock = lock

        with lock:
            local_snapshot = getattr(self, "_local_ths_concept_snapshot", None) or {}
            if local_snapshot.get("loaded"):
                return True
            if (
                now_ts - float(local_snapshot.get("loaded_at") or 0)
                < self.LOCAL_THS_SNAPSHOT_RELOAD_COOLDOWN_SECONDS
            ):
                return False

            try:
                snapshot = self._run_coroutine_sync(self._load_local_ths_concept_snapshot_from_db_async())
            except Exception as exc:
                logger.warning("懒加载本地 THS 概念快照失败: {}", exc)
                self.load_local_ths_concept_snapshot(
                    index_map={},
                    stock_to_codes={},
                    sync_trade_date="",
                    loaded=False,
                )
                return False

            if not snapshot:
                self.load_local_ths_concept_snapshot(
                    index_map={},
                    stock_to_codes={},
                    sync_trade_date="",
                    loaded=False,
                )
                return False

            index_map = snapshot.get("index_map") or {}
            stock_to_codes = snapshot.get("stock_to_codes") or {}
            sync_trade_date = str(snapshot.get("sync_trade_date") or "").strip()
            self.load_local_ths_concept_snapshot(
                index_map=index_map,
                stock_to_codes=stock_to_codes,
                sync_trade_date=sync_trade_date,
                loaded=bool(index_map),
            )
            logger.info(
                "已懒加载本地 THS 概念快照 concepts={} stocks={} trade_date={}",
                len(index_map),
                len(stock_to_codes),
                sync_trade_date or "-",
            )
            return bool(index_map)

    def fetch_remote_ths_concept_snapshot(self, trade_date: str) -> Dict[str, object]:
        """从 Tushare 全量抓取 THS 概念定义与成分。"""
        compact_trade_date = str(trade_date or "").replace("-", "").strip()[:8]
        if not compact_trade_date:
            compact_trade_date = self._now_sh().strftime("%Y%m%d")
        concept_rows = self.fetch_remote_ths_concept_index_rows()
        member_rows = self.fetch_remote_ths_concept_member_rows(
            [str(row.get("ts_code") or "").strip() for row in concept_rows]
        )
        return {
            "sync_trade_date": compact_trade_date,
            "concept_rows": concept_rows,
            "member_rows": member_rows,
        }

    def fetch_remote_ths_concept_index_rows(self) -> List[Dict[str, str]]:
        """抓取 THS 概念定义列表。"""
        if not getattr(self, "pro", None):
            raise RuntimeError("Tushare 客户端未初始化，无法同步 THS 概念")
        concept_rows: List[Dict[str, str]] = []
        seen_concepts = set()
        for ths_type in ("N", "TH"):
            try:
                df = self._call_pro_ths_index(exchange="A", type=ths_type)
            except TypeError:
                df = self._call_pro_ths_index(type=ths_type)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                concept_code = str(row.get("ts_code") or "").strip()
                concept_name = str(row.get("name") or "").strip()
                if not concept_code or not concept_name or concept_code in seen_concepts:
                    continue
                seen_concepts.add(concept_code)
                concept_rows.append(
                    {
                        "ts_code": concept_code,
                        "concept_name": concept_name,
                        "ths_type": str(row.get("type") or ths_type).strip() or ths_type,
                        "exchange": str(row.get("exchange") or "A").strip() or "A",
                    }
                )
        return concept_rows

    def fetch_remote_ths_concept_member_rows(self, concept_codes: List[str]) -> List[Dict[str, str]]:
        """按概念代码列表抓取 THS 概念成分。"""
        if not getattr(self, "pro", None):
            raise RuntimeError("Tushare 客户端未初始化，无法同步 THS 概念")
        member_rows: List[Dict[str, str]] = []
        seen_members = set()
        for concept_code in concept_codes:
            normalized_concept_code = str(concept_code or "").strip()
            if not normalized_concept_code:
                continue
            try:
                df = self._call_pro_ths_member(ts_code=normalized_concept_code)
            except TypeError:
                continue
            if df is None or df.empty:
                continue
            work = df.copy()
            if "is_new" in work.columns:
                work = work[work["is_new"].fillna("Y").astype(str).str.upper() == "Y"]
            for _, row in work.iterrows():
                stock_code = normalize_ts_code(str(row.get("con_code") or "").strip())
                if not stock_code:
                    continue
                member_key = (normalized_concept_code, stock_code)
                if member_key in seen_members:
                    continue
                seen_members.add(member_key)
                member_rows.append(
                    {
                        "concept_code": normalized_concept_code,
                        "stock_code": stock_code,
                        "stock_name": str(row.get("con_name") or row.get("name") or "").strip(),
                    }
                )
        return member_rows

    def _call_ts_realtime_quote(self, ts_code: str, *, src: Optional[str] = None):
        trade_date = self._now_sh().strftime("%Y%m%d")
        self._log_tushare_api_call(
            "ts.realtime_quote",
            trade_date=trade_date,
            extra={"src": src, "codes": ts_code},
        )
        return ts.realtime_quote(ts_code, src=src)

    def _call_ts_realtime_list(self, *, src: str, page_count: Optional[int] = None):
        trade_date = self._now_sh().strftime("%Y%m%d")
        self._log_tushare_api_call(
            "ts.realtime_list",
            trade_date=trade_date,
            extra={"src": src, "page_count": page_count},
        )
        return ts.realtime_list(src=src, page_count=page_count)

    def _tabular_api_cache_ttl(self, trade_date: str) -> int:
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        if self._should_use_market_snapshot(compact_trade_date) or self._should_use_realtime_quote(compact_trade_date):
            return self.DAILY_API_INTRADAY_CACHE_TTL_SECONDS
        return self.DAILY_API_HISTORY_CACHE_TTL_SECONDS

    def _get_cached_tabular_api_payload(self, cache_name: str, cache_key: str):
        cache = getattr(self, cache_name, None)
        if cache is None:
            cache = {}
            setattr(self, cache_name, cache)
        entry = cache.get(cache_key)
        if not entry:
            return None
        ttl = float(entry.get("ttl") or 0.0)
        if ttl <= 0 or time_module.monotonic() - float(entry.get("fetched_at") or 0.0) > ttl:
            cache.pop(cache_key, None)
            return None
        payload = entry.get("payload")
        return copy.deepcopy(payload)

    def _cache_tabular_api_payload(
        self,
        cache_name: str,
        cache_key: str,
        payload,
        *,
        trade_date: str,
    ):
        cache = getattr(self, cache_name, None)
        if cache is None:
            cache = {}
            setattr(self, cache_name, cache)
        cache[cache_key] = {
            "fetched_at": time_module.monotonic(),
            "ttl": self._tabular_api_cache_ttl(trade_date),
            "payload": copy.deepcopy(payload),
        }
        return copy.deepcopy(payload)

    def _cached_pro_daily(
        self,
        *,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trade_date: Optional[str] = None,
    ):
        cache_trade_date = trade_date or end_date or start_date or ""
        cache_key = f"{normalize_ts_code(ts_code or '')}:{start_date or ''}:{end_date or ''}:{trade_date or ''}"
        cached = self._get_cached_tabular_api_payload("_daily_api_cache", cache_key)
        if cached is not None:
            return cached
        self._log_tushare_api_call(
            "pro.daily",
            trade_date=cache_trade_date,
            extra={"ts_code": normalize_ts_code(ts_code or ""), "start_date": start_date, "end_date": end_date},
        )
        df = self.pro.daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            trade_date=trade_date,
        )
        return self._cache_tabular_api_payload(
            "_daily_api_cache",
            cache_key,
            df,
            trade_date=cache_trade_date,
        )

    def _cached_pro_daily_basic(
        self,
        *,
        ts_code: Optional[str] = None,
        trade_date: Optional[str] = None,
        fields: Optional[str] = None,
    ):
        cache_trade_date = trade_date or ""
        cache_key = f"{normalize_ts_code(ts_code or '')}:{trade_date or ''}:{fields or ''}"
        cached = self._get_cached_tabular_api_payload("_daily_basic_api_cache", cache_key)
        if cached is not None:
            return cached
        daily_basic = getattr(self.pro, "daily_basic", None)
        if not callable(daily_basic):
            return None
        self._log_tushare_api_call(
            "pro.daily_basic",
            trade_date=cache_trade_date,
            extra={"ts_code": normalize_ts_code(ts_code or ""), "fields": fields},
        )
        try:
            df = daily_basic(
                ts_code=ts_code,
                trade_date=trade_date,
                fields=fields,
            )
        except TypeError:
            df = daily_basic(
                ts_code=ts_code,
                trade_date=trade_date,
            )
        return self._cache_tabular_api_payload(
            "_daily_basic_api_cache",
            cache_key,
            df,
            trade_date=cache_trade_date,
        )

    def _cached_pro_index_daily(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ):
        cache_key = f"{normalize_ts_code(ts_code)}:{start_date}:{end_date}"
        cached = self._get_cached_tabular_api_payload("_index_daily_api_cache", cache_key)
        if cached is not None:
            return cached
        self._log_tushare_api_call(
            "pro.index_daily",
            trade_date=end_date,
            extra={"ts_code": normalize_ts_code(ts_code), "start_date": start_date, "end_date": end_date},
        )
        df = self.pro.index_daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        return self._cache_tabular_api_payload(
            "_index_daily_api_cache",
            cache_key,
            df,
            trade_date=end_date,
        )

    def _get_cached_stock_detail(self, ts_code: str, trade_date: str) -> Optional[Dict]:
        cache = getattr(self, "_stock_detail_cache", None)
        if cache is None:
            cache = {}
            self._stock_detail_cache = cache
        cache_key = f"{normalize_ts_code(ts_code)}:{str(trade_date).replace('-', '').strip()[:8]}"
        entry = cache.get(cache_key)
        if not entry:
            return None
        ttl = float(entry.get("ttl") or 0.0)
        if ttl <= 0 or time_module.monotonic() - float(entry.get("fetched_at") or 0.0) > ttl:
            cache.pop(cache_key, None)
            return None
        return copy.deepcopy(entry.get("detail"))

    def _cache_stock_detail(
        self,
        ts_code: str,
        request_trade_date: str,
        detail: Dict,
        *,
        resolved_trade_date: Optional[str] = None,
    ) -> Dict:
        cache = getattr(self, "_stock_detail_cache", None)
        if cache is None:
            cache = {}
            self._stock_detail_cache = cache

        compact_request_trade_date = str(request_trade_date).replace("-", "").strip()[:8]
        ttl = self._stock_detail_cache_ttl(compact_request_trade_date)
        payload = copy.deepcopy(detail)
        entry = {
            "fetched_at": time_module.monotonic(),
            "ttl": ttl,
            "detail": payload,
        }
        cache[f"{normalize_ts_code(ts_code)}:{compact_request_trade_date}"] = entry
        compact_resolved_trade_date = str(resolved_trade_date or "").replace("-", "").strip()[:8]
        if compact_resolved_trade_date and compact_resolved_trade_date != compact_request_trade_date:
            cache[f"{normalize_ts_code(ts_code)}:{compact_resolved_trade_date}"] = entry
        return copy.deepcopy(payload)

    def _is_tushare_quota_error(self, exc: Exception) -> bool:
        message = str(exc or "")
        return "每天最多访问该接口10000次" in message or "doc_id=108" in message

    def _build_data_error_meta(self, exc: Exception) -> Dict[str, str]:
        message = str(exc or "").strip()
        if "每分钟最多访问该接口500次" in message:
            return {
                "data_status": "rate_limited",
                "data_message": "候选链路触发 Tushare 分钟频控，当前结果可能不完整。",
            }
        if self._is_tushare_quota_error(exc):
            return {
                "data_status": "quota_limited",
                "data_message": "候选链路触发 Tushare 配额限制，当前结果可能不完整。",
            }
        return {
            "data_status": "error",
            "data_message": f"候选链路异常：{message or '未知错误'}",
        }

    def _is_stock_detail_quota_limited(self) -> bool:
        state = getattr(self, "_stock_detail_quota_state", None) or {}
        return time_module.monotonic() < float(state.get("limited_until") or 0.0)

    def _mark_stock_detail_quota_limited(self, exc: Exception) -> None:
        state = getattr(self, "_stock_detail_quota_state", None)
        if state is None:
            state = {"limited_until": 0.0, "message": ""}
            self._stock_detail_quota_state = state
        state["limited_until"] = time_module.monotonic() + self.STOCK_DETAIL_QUOTA_COOLDOWN_SECONDS
        state["message"] = str(exc or "")

    def _clear_stock_detail_quota_limited(self) -> None:
        state = getattr(self, "_stock_detail_quota_state", None)
        if state is None:
            return
        state["limited_until"] = 0.0
        state["message"] = ""

    def _empty_stock_detail(
        self,
        ts_code: str,
        *,
        stock_name: Optional[str] = None,
        sector_name: Optional[str] = None,
        data_source: str = "lightweight_fallback",
    ) -> Dict:
        normalized_code = normalize_ts_code(ts_code)
        return {
            "ts_code": normalized_code,
            "stock_name": str(stock_name or normalized_code),
            "sector_name": str(sector_name or "未知") or "未知",
            "close": 0.0,
            "change_pct": 0.0,
            "turnover_rate": 0.0,
            "amount": 0,
            "vol_ratio": 1.0,
            "high": 0.0,
            "low": 0.0,
            "open": 0.0,
            "pre_close": 0.0,
            "volume": None,
            "avg_price": None,
            "intraday_volume_ratio": None,
            "quote_time": None,
            "data_source": data_source,
            "concept_names": [],
        }

    def _build_lightweight_stock_detail(
        self,
        ts_code: str,
        trade_date: str,
        *,
        stock_meta_map: Optional[Dict[str, Dict[str, str]]] = None,
        data_source: str = "lightweight_fallback",
    ) -> Dict:
        normalized_code = normalize_ts_code(ts_code)
        meta_map = stock_meta_map if stock_meta_map is not None else (self._get_stock_basic_snapshot_map() or {})
        stock_meta = meta_map.get(normalized_code) or {}
        detail = self._empty_stock_detail(
            normalized_code,
            stock_name=str(stock_meta.get("stock_name") or normalized_code),
            sector_name=str(stock_meta.get("industry") or "未知") or "未知",
            data_source=data_source,
        )
        return self._overlay_realtime_detail_with_options(
            detail,
            trade_date,
            allow_intraday_volume_ratio=False,
        )

    def _fetch_public_page_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """通过公开网页首屏埋点补充盘中涨跌停统计。"""
        if self._is_realtime_source_in_cooldown("page_cls"):
            return None

        try:
            response = httpx.get(
                "https://www.cls.cn/",
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except Exception as e:
            self._mark_realtime_source_failure("page_cls")
            logger.warning(f"公开网页抓取失败（cls.cn）: {e}")
            return None

        limit_stats = self._extract_cls_limit_stats_from_html(response.text)
        if not limit_stats:
            self._mark_realtime_source_failure("page_cls")
            logger.info("公开网页抓取未解析到有效涨跌停统计（cls.cn）")
            return None

        self._clear_realtime_source_failure("page_cls")
        return {
            "data_trade_date": str(trade_date).replace("-", "")[:8],
            "quote_time": self._now_sh().strftime("%Y-%m-%d %H:%M:%S"),
            "data_source": "realtime_page_cls",
            "status": "live",
            "is_stale": False,
            "stale_from_quote_time": None,
            "limit_stats": limit_stats,
        }

    def _parse_ths_industry_rows(self, html: str) -> List[List[str]]:
        from html import unescape

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.S)
        parsed_rows: List[List[str]] = []
        for row in rows[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            values = []
            for cell in cells:
                text = re.sub(r"<[^>]+>", " ", cell)
                text = unescape(re.sub(r"\s+", " ", text)).strip()
                values.append(text)
            if len(values) >= 8:
                parsed_rows.append(values)
        return parsed_rows

    def _fetch_public_industry_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """通过同花顺行业分页页汇总涨跌家数和成交额。"""
        if self._is_realtime_source_in_cooldown("page_ths_industry"):
            return None

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        page_count = 1
        first_page_html = ""
        total_turnover = 0.0
        total_up = 0
        total_down = 0

        for page in range(1, 11):
            url = (
                "https://q.10jqka.com.cn/thshy/index/"
                f"field/199112/order/desc/page/{page}/ajax/1/"
            )
            try:
                response = session.get(url, timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS)
                response.raise_for_status()
            except Exception as e:
                self._mark_realtime_source_failure("page_ths_industry")
                logger.warning(f"公开网页抓取失败（10jqka thshy page={page}）: {e}")
                return None

            html = response.text or ""
            if "<table class=\"m-table m-pager-table\">" not in html:
                self._mark_realtime_source_failure("page_ths_industry")
                logger.warning(f"公开网页抓取未返回有效行业表（10jqka thshy page={page}）")
                return None

            if page == 1:
                first_page_html = html
                page_info_match = re.search(r"<span class=\"page_info\">(\d+)/(\d+)</span>", html)
                if page_info_match:
                    try:
                        page_count = max(1, min(10, int(page_info_match.group(2))))
                    except Exception:
                        page_count = 1

            for values in self._parse_ths_industry_rows(html):
                try:
                    total_turnover += float(values[4] or 0)
                    total_up += int(values[6] or 0)
                    total_down += int(values[7] or 0)
                except Exception:
                    continue

            if page >= page_count:
                break

        if not first_page_html or total_turnover <= 0 or (total_up + total_down) <= 0:
            self._mark_realtime_source_failure("page_ths_industry")
            logger.warning("公开网页抓取样本不足（10jqka thshy），无法汇总市场状态")
            return None

        self._clear_realtime_source_failure("page_ths_industry")
        return self._build_realtime_market_state(
            trade_date,
            market_turnover=round(total_turnover, 2),
            up_down_ratio={
                "up": total_up,
                "down": total_down,
                "flat": 0,
                "total": total_up + total_down,
            },
            limit_stats={
                "limit_up_count": 0,
                "limit_down_count": 0,
                "broken_board_rate": 0.0,
                "estimated": True,
            },
            quote_time=self._now_sh().strftime("%Y-%m-%d %H:%M:%S"),
            data_source="realtime_page_ths_industry",
            status="live",
        )

    def _apply_page_limit_stats_overlay(
        self,
        snapshot: Optional[Dict[str, object]],
        page_snapshot: Optional[Dict[str, object]],
    ) -> Optional[Dict[str, object]]:
        if not snapshot or not page_snapshot:
            return snapshot

        page_limit_stats = page_snapshot.get("limit_stats") or {}
        if not page_limit_stats:
            return snapshot

        merged = copy.deepcopy(snapshot)
        base_limit_stats = copy.deepcopy((merged.get("limit_stats") or {}))
        for field in ("limit_up_count", "limit_down_count", "broken_board_rate", "estimated"):
            if page_limit_stats.get(field) is not None:
                base_limit_stats[field] = page_limit_stats[field]
        merged["limit_stats"] = base_limit_stats
        return merged

    def _fetch_public_aggregate_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """通过公开聚合接口获取全市场实时状态。"""
        if self._is_realtime_source_in_cooldown("aggregate_em"):
            return None

        params = {
            "pn": "1",
            "pz": "12000",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f6,f12,f14,f15,f16,f17,f18",
        }

        try:
            response = httpx.get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                params=params,
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            payload = response.json()
            diff = (((payload or {}).get("data") or {}).get("diff")) or []
        except Exception as e:
            self._mark_realtime_source_failure("aggregate_em")
            logger.warning(f"公开聚合接口拉取失败: {e}")
            return None

        rows = []
        for raw in diff:
            normalized = self._normalize_public_aggregate_row(raw)
            if normalized:
                rows.append(normalized)

        if len(rows) < self.REALTIME_MARKET_MIN_TOTAL:
            self._mark_realtime_source_failure("aggregate_em")
            logger.warning(f"公开聚合接口样本不足（仅 {len(rows)} 条），转入兜底实时源")
            return None

        self._clear_realtime_source_failure("aggregate_em")
        now = self._now_sh()
        import pandas as pd
        df = pd.DataFrame(rows)
        pct_series = df["PCT_CHANGE"].fillna(0)
        amount_series = df["AMOUNT"].fillna(0)
        return self._build_realtime_market_state(
            trade_date,
            market_turnover=round(float(amount_series.sum()) / 100000000, 2),
            up_down_ratio={
                "up": int((pct_series > 0).sum()),
                "down": int((pct_series < 0).sum()),
                "flat": int((pct_series == 0).sum()),
                "total": int(len(df)),
            },
            limit_stats=self._estimate_realtime_limit_stats(df),
            quote_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            data_source="realtime_em",
            status="live",
        )

    def _fetch_public_aggregate_stock_rows(self, trade_date: str) -> Optional[Dict[str, object]]:
        """通过东财公开聚合接口获取全市场实时个股行级数据。"""
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        if not self._should_use_market_snapshot(compact_trade_date):
            return None
        if self._is_realtime_source_in_cooldown("aggregate_em"):
            return None

        params = {
            "pn": "1",
            "pz": "12000",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f5,f6,f8,f12,f14,f15,f16,f17,f18",
        }

        try:
            response = httpx.get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                params=params,
                timeout=self.REALTIME_AGGREGATE_TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            payload = response.json()
            diff = (((payload or {}).get("data") or {}).get("diff")) or []
        except Exception as e:
            self._mark_realtime_source_failure("aggregate_em")
            logger.warning(f"公开实时候选拉取失败: {e}")
            return None

        rows = []
        for raw in diff:
            normalized = self._normalize_public_aggregate_row(raw)
            if normalized:
                rows.append(normalized)

        if len(rows) < self.REALTIME_CANDIDATE_MIN_TOTAL:
            self._mark_realtime_source_failure("aggregate_em")
            logger.warning(f"公开实时候选样本不足（仅 {len(rows)} 条），转入日线候选兜底")
            return None

        self._clear_realtime_source_failure("aggregate_em")
        return {
            "rows": rows,
            "data_trade_date": compact_trade_date,
            "quote_time": self._now_sh().strftime("%Y-%m-%d %H:%M:%S"),
            "data_source": "realtime_em",
        }

    def _fetch_realtime_quote_map(self, ts_codes: List[str]) -> Dict[str, Dict]:
        """批量获取实时行情并转成按 ts_code 索引的映射。"""
        normalized_codes = []
        for code in ts_codes:
            normalized = normalize_ts_code(code)
            if normalized and normalized not in normalized_codes:
                normalized_codes.append(normalized)

        if not normalized_codes:
            return {}

        cache = getattr(self, "_realtime_quote_cache", None)
        if cache is None:
            cache = {}
            self._realtime_quote_cache = cache

        cache_key = ",".join(normalized_codes)
        cached = cache.get(cache_key)
        now_ts = time_module.monotonic()
        if cached and now_ts - float(cached.get("fetched_at") or 0.0) <= self.REALTIME_MARKET_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached.get("payload") or {})

        quote_map: Dict[str, Dict] = {}
        for idx in range(0, len(normalized_codes), self.REALTIME_CHUNK_SIZE):
            chunk = normalized_codes[idx: idx + self.REALTIME_CHUNK_SIZE]
            df = None
            used_source = None
            last_error = None
            for source in self._iter_realtime_sources():
                try:
                    df = self._call_ts_realtime_quote(
                        ",".join(chunk),
                        src=source,
                    )
                    if df is not None and not df.empty:
                        used_source = source
                        break
                except Exception as e:
                    last_error = e
                    continue

            if df is None or df.empty:
                if last_error:
                    logger.warning(f"实时行情拉取失败（{len(chunk)}只）: {last_error}")
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
                    "data_source": f"realtime_{used_source or self.REALTIME_SOURCE}",
                }

        cache[cache_key] = {
            "fetched_at": now_ts,
            "payload": copy.deepcopy(quote_map),
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

        quote_map = self._fetch_realtime_stock_quote_map([row.get("ts_code", "") for row in rows])
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
        """对指数列表做快照覆盖，兼容盘中与收盘后快照窗口。"""
        if not rows or not self._should_use_market_snapshot(trade_date):
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

    def _fetch_tushare_realtime_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """现有 Tushare 实时全市场扫描链路，作为最后兜底。"""
        if not self._should_use_realtime_quote(trade_date):
            return None
        if self._is_realtime_source_in_cooldown("tushare_scan"):
            return None

        cache = getattr(self, "_realtime_market_cache", None) or {
            "trade_date": "",
            "fetched_at": 0.0,
            "snapshot": None,
        }
        now_ts = time_module.monotonic()
        df = None
        used_source = None
        last_error = None
        insufficient_sources = []
        for source in self._iter_realtime_sources():
            source_sample_total = None
            for _ in range(2):
                try:
                    df = self._call_ts_realtime_list(
                        src=source,
                        page_count=1 if source == "sina" else None,
                    )
                    if df is not None and not df.empty:
                        total = len(df)
                        if total >= self.REALTIME_MARKET_MIN_TOTAL:
                            used_source = source
                            break
                        source_sample_total = total
                        df = None
                except Exception as e:
                    last_error = e
            if source_sample_total is not None:
                insufficient_sources.append((source, source_sample_total))
                logger.warning(
                    f"盘中市场快照样本不足（{source} 仅 {source_sample_total} 条），切换备用源重试"
                )
            if df is not None and not df.empty:
                break
        if df is None or df.empty:
            self._mark_realtime_source_failure("tushare_scan")
            if last_error:
                logger.warning(f"盘中市场快照拉取失败: {last_error}")
            elif insufficient_sources:
                source_text = " / ".join(f"{source}:{total}" for source, total in insufficient_sources)
                logger.warning(f"盘中市场快照样本仍不足（{source_text}），回退日线口径")
            self._realtime_market_cache = {
                "trade_date": str(trade_date).replace("-", "")[:8],
                "fetched_at": now_ts,
                "snapshot": False,
            }
            return None

        self._clear_realtime_source_failure("tushare_scan")
        pct_series = df["PCT_CHANGE"].fillna(0)
        amount_series = df["AMOUNT"].fillna(0)
        up = int((pct_series > 0).sum())
        down = int((pct_series < 0).sum())
        flat = int((pct_series == 0).sum())
        total = len(df)
        limit_stats = self._estimate_realtime_limit_stats(df)
        now = self._now_sh()
        quote_time = now.strftime("%Y-%m-%d %H:%M:%S")
        time_col = str(df.iloc[0].get("TIME") or "").strip() if "TIME" in df.columns and not df.empty else ""
        if time_col:
            quote_time = f"{now.strftime('%Y-%m-%d')} {time_col}"
        snapshot = self._build_realtime_market_state(
            trade_date,
            market_turnover=round(float(amount_series.sum()) / 100000000, 2),
            up_down_ratio={
                "up": up,
                "down": down,
                "flat": flat,
                "total": total,
            },
            limit_stats=limit_stats,
            quote_time=quote_time,
            data_source=f"realtime_{used_source or 'unknown'}",
            status="live",
        )
        self._realtime_market_cache = {
            "trade_date": snapshot["data_trade_date"],
            "fetched_at": now_ts,
            "snapshot": snapshot,
        }
        return snapshot

    def _fetch_realtime_market_snapshot(self, trade_date: str) -> Optional[Dict[str, object]]:
        """获取实时市场状态：新浪接口优先，网页/缓存次之，Tushare 扫描兜底。"""
        if not (
            self._should_use_market_snapshot(trade_date)
            or self._should_use_realtime_quote(trade_date)
        ):
            return None

        lock = getattr(self, "_realtime_market_fetch_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._realtime_market_fetch_lock = lock

        with lock:
            compact_trade_date = str(trade_date).replace("-", "")[:8]
            now_ts = time_module.monotonic()
            state_cache = getattr(self, "_realtime_market_state_cache", None) or {
                "trade_date": "",
                "fetched_at": 0.0,
                "snapshot": None,
            }

            cached_snapshot = None
            cached_age = None
            if state_cache.get("trade_date") == compact_trade_date:
                cached_snapshot = state_cache.get("snapshot") or None
                cached_age = now_ts - float(state_cache.get("fetched_at") or 0)
                if cached_snapshot and cached_age is not None:
                    if (
                        cached_snapshot.get("status") == "unavailable"
                        and cached_age < self.REALTIME_MARKET_FAILURE_COOLDOWN_SECONDS
                    ):
                        return copy.deepcopy(cached_snapshot)
                    if cached_age < self.REALTIME_MARKET_CACHE_TTL_SECONDS:
                        return cached_snapshot

            page_snapshot = self._fetch_public_page_market_snapshot(trade_date)

            sina_overview_snapshot = self._fetch_sina_market_overview_snapshot(trade_date)
            if sina_overview_snapshot:
                sina_overview_snapshot = self._apply_page_limit_stats_overlay(
                    sina_overview_snapshot,
                    page_snapshot,
                )
                self._realtime_market_state_cache = {
                    "trade_date": sina_overview_snapshot["data_trade_date"],
                    "fetched_at": now_ts,
                    "snapshot": sina_overview_snapshot,
                }
                return sina_overview_snapshot

            industry_snapshot = self._fetch_public_industry_market_snapshot(trade_date)
            if industry_snapshot:
                industry_snapshot = self._apply_page_limit_stats_overlay(
                    industry_snapshot,
                    page_snapshot,
                )
                logger.warning("实时市场状态主源失败，已切换到同花顺行业页汇总兜底")
                self._realtime_market_state_cache = {
                    "trade_date": industry_snapshot["data_trade_date"],
                    "fetched_at": now_ts,
                    "snapshot": industry_snapshot,
                }
                return industry_snapshot

            if cached_snapshot and cached_age is not None and cached_age < self.REALTIME_MARKET_STALE_TTL_SECONDS:
                stale_quote_time = cached_snapshot.get("quote_time")
                stale_snapshot = copy.deepcopy(cached_snapshot)
                stale_snapshot["status"] = "stale"
                stale_snapshot["is_stale"] = True
                stale_snapshot["stale_from_quote_time"] = stale_quote_time
                stale_snapshot["data_source"] = "realtime_cache"
                logger.warning(
                    "实时市场状态主源失败，已切换到最近成功缓存: stale_from={}",
                    stale_quote_time or "-",
                )
                return stale_snapshot

            legacy_snapshot = self._fetch_tushare_realtime_market_snapshot(trade_date)
            if legacy_snapshot:
                legacy_snapshot = self._apply_page_limit_stats_overlay(
                    legacy_snapshot,
                    page_snapshot,
                )
                logger.warning("实时市场状态主源失败，已切换到 Tushare 全市场扫描兜底")
                self._realtime_market_state_cache = {
                    "trade_date": legacy_snapshot["data_trade_date"],
                    "fetched_at": now_ts,
                    "snapshot": legacy_snapshot,
                }
                return legacy_snapshot

            unavailable_snapshot = self._empty_realtime_market_state(
                trade_date,
                status="unavailable",
                data_source="unavailable",
                stale_from_quote_time=cached_snapshot.get("quote_time") if cached_snapshot else None,
            )
            self._realtime_market_state_cache = {
                "trade_date": unavailable_snapshot["data_trade_date"],
                "fetched_at": now_ts,
                "snapshot": unavailable_snapshot,
            }
            return unavailable_snapshot

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

        cache = getattr(self, "_trade_date_resolution_cache", None)
        if cache is None:
            cache = {}
            self._trade_date_resolution_cache = cache
        cached = cache.get(trade_date)
        now_ts = time_module.monotonic()
        if cached and now_ts - float(cached.get("fetched_at") or 0) < self.TRADE_DATE_RESOLUTION_CACHE_TTL_SECONDS:
            return str(cached.get("resolved_trade_date") or trade_date)

        try:
            from datetime import datetime, timedelta
            end_dt = datetime.strptime(trade_date, "%Y%m%d")
            start_dt = end_dt - timedelta(days=14)
            cal_df = self._call_pro_trade_cal(
                exchange="SSE",
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=trade_date,
                fields="cal_date,is_open",
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
                    cache[trade_date] = {
                        "fetched_at": now_ts,
                        "resolved_trade_date": resolved,
                    }
                    return resolved
        except Exception as e:
            logger.warning(
                f"解析交易日失败，使用原始日期 {trade_date}: {e}"
            )

        cache[trade_date] = {
            "fetched_at": now_ts,
            "resolved_trade_date": trade_date,
        }
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
            cal_df = self._call_pro_trade_cal(
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
            cal_df = self._call_pro_trade_cal(
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

    def _resolve_eod_fallback_start_trade_date(self, trade_date: str) -> str:
        """
        获取日线类回退的起始交易日。

        当天日线未稳定前，不再先打当天 daily/index_daily/limit_list_d，
        而是直接从最近已完成交易日开始。
        """
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        now = self._now_sh()
        if (
            compact_trade_date == now.strftime("%Y%m%d")
            and now.weekday() < 5
            and now.time() < self.EOD_DATA_READY_TIME
        ):
            return self.get_last_completed_trade_date(trade_date)
        return self._resolve_trade_date(trade_date)

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
            effective_trade_date = self._resolve_eod_fallback_start_trade_date(trade_date)
            # 上证指数、深成指、创业板
            index_codes = ["000001.SH", "399001.SZ", "399006.SZ"]
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                result = []
                for ts_code in index_codes:
                    df = self._cached_pro_index_daily(
                        ts_code=ts_code,
                        start_date=data_trade_date,
                        end_date=data_trade_date,
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
            snapshot_status = snapshot.get("status", "live") if snapshot else None
            if snapshot and snapshot_status in {"live", "stale"} and snapshot.get("limit_stats"):
                return {
                    "stats": snapshot["limit_stats"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot.get("quote_time"),
                    "data_source": snapshot.get("data_source"),
                    "status": snapshot_status,
                    "is_stale": snapshot.get("is_stale", False),
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            page_snapshot = None
            if self._should_use_market_snapshot(trade_date):
                page_snapshot = self._fetch_public_page_market_snapshot(trade_date)
            if page_snapshot and page_snapshot.get("limit_stats"):
                return {
                    "stats": page_snapshot["limit_stats"],
                    "data_trade_date": page_snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": page_snapshot.get("quote_time"),
                    "data_source": page_snapshot.get("data_source"),
                    "status": page_snapshot.get("status", "live"),
                    "is_stale": page_snapshot.get("is_stale", False),
                    "stale_from_quote_time": page_snapshot.get("stale_from_quote_time"),
                }
            if snapshot and snapshot_status == "unavailable":
                return {
                    "stats": {
                        "limit_up_count": 0,
                        "limit_down_count": 0,
                        "broken_board_rate": 0.0,
                    },
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": None,
                    "data_source": snapshot.get("data_source"),
                    "status": "unavailable",
                    "is_stale": False,
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            effective_trade_date = self._resolve_eod_fallback_start_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df_up = self._call_pro_limit_list_d(
                    trade_date=data_trade_date,
                    limit_type='U',
                )
                df_down = self._call_pro_limit_list_d(
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

        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        cache = getattr(self, "_recent_open_dates_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_recent_open_dates_cache", cache)
        ttl = float(getattr(self, "RECENT_OPEN_DATES_CACHE_TTL_SECONDS", 0) or 0)
        now_ts = time_module.monotonic()
        cached = cache.get(compact_trade_date)
        if (
            cached
            and ttl > 0
            and now_ts - float(cached.get("fetched_at") or 0.0) <= ttl
        ):
            open_days = list(cached.get("open_days") or [])
            return open_days[:count] or [compact_trade_date]

        lock = getattr(self, "_recent_open_dates_lock", None)
        if lock is None:
            lock = threading.Lock()
            setattr(self, "_recent_open_dates_lock", lock)

        try:
            from datetime import datetime, timedelta

            with lock:
                cached = cache.get(compact_trade_date)
                now_ts = time_module.monotonic()
                if (
                    cached
                    and ttl > 0
                    and now_ts - float(cached.get("fetched_at") or 0.0) <= ttl
                ):
                    open_days = list(cached.get("open_days") or [])
                    return open_days[:count] or [compact_trade_date]

                end_dt = datetime.strptime(compact_trade_date, "%Y%m%d")
                start_dt = end_dt - timedelta(days=20)
                cal_df = self._call_pro_trade_cal(
                    exchange="SSE",
                    start_date=start_dt.strftime("%Y%m%d"),
                    end_date=compact_trade_date,
                    fields="cal_date,is_open",
                )
            if cal_df is None or cal_df.empty:
                return [compact_trade_date]
            open_days = cal_df[cal_df["is_open"] == 1]["cal_date"].tolist()
            open_days = sorted((str(day) for day in open_days), reverse=True)
            cache[compact_trade_date] = {
                "fetched_at": time_module.monotonic(),
                "open_days": list(open_days),
            }
            return open_days[:count] or [compact_trade_date]
        except Exception as e:
            logger.warning(f"获取最近交易日序列失败: {e}")
            return [compact_trade_date]

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
                df = self._call_pro_stock_basic(fields="ts_code,name,industry")
            except TypeError:
                df = self._call_pro_stock_basic()

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
        work = work[work["ts_code"].map(is_sector_scan_board_eligible)]
        if work.empty:
            return None
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

    def get_sector_data_with_meta(
        self,
        trade_date: str,
        *,
        prefer_today: bool = False,
    ) -> Dict[str, object]:
        """获取行业板块，并返回实际使用的数据日期。"""
        if not self.token:
            return {
                "rows": self._mock_sector_data(),
                "data_trade_date": trade_date,
                "used_mock": True,
        }

        try:
            effective_trade_date = (
                self._resolve_trade_date(trade_date)
                if prefer_today
                else self._resolve_eod_fallback_start_trade_date(trade_date)
            )
            industry_map = self._get_stock_basic_industry_map()
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df = self._cached_pro_daily(trade_date=data_trade_date)
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
            snapshot_status = snapshot.get("status", "live") if snapshot else None
            if snapshot and snapshot_status in {"live", "stale"}:
                return {
                    "market_turnover": snapshot["market_turnover"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot["quote_time"],
                    "data_source": snapshot["data_source"],
                    "status": snapshot_status,
                    "is_stale": snapshot.get("is_stale", False),
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            if snapshot and snapshot_status == "unavailable":
                return {
                    "market_turnover": None,
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": None,
                    "data_source": snapshot["data_source"],
                    "status": "unavailable",
                    "is_stale": False,
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            effective_trade_date = self._resolve_eod_fallback_start_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                sh_df = self._cached_pro_index_daily(
                    ts_code="000001.SH",
                    start_date=data_trade_date,
                    end_date=data_trade_date,
                )
                sz_df = self._cached_pro_index_daily(
                    ts_code="399001.SZ",
                    start_date=data_trade_date,
                    end_date=data_trade_date,
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
            snapshot_status = snapshot.get("status", "live") if snapshot else None
            if snapshot and snapshot_status in {"live", "stale"}:
                return {
                    "up_down_ratio": snapshot["up_down_ratio"],
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": snapshot["quote_time"],
                    "data_source": snapshot["data_source"],
                    "status": snapshot_status,
                    "is_stale": snapshot.get("is_stale", False),
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            if snapshot and snapshot_status == "unavailable":
                return {
                    "up_down_ratio": {"up": 0, "down": 0, "flat": 0, "total": 0},
                    "data_trade_date": snapshot["data_trade_date"],
                    "used_mock": False,
                    "quote_time": None,
                    "data_source": snapshot["data_source"],
                    "status": "unavailable",
                    "is_stale": False,
                    "stale_from_quote_time": snapshot.get("stale_from_quote_time"),
                }
            effective_trade_date = self._resolve_eod_fallback_start_trade_date(trade_date)
            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                df = self._cached_pro_daily(trade_date=data_trade_date)
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
        if "ts_code" in work.columns:
            work["ts_code"] = work["ts_code"].astype(str).map(normalize_ts_code)
            work = work[work["ts_code"].map(is_sector_scan_board_eligible)]
            if work.empty:
                return []
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
        self._ensure_local_ths_concept_snapshot_loaded()
        local_snapshot = getattr(self, "_local_ths_concept_snapshot", None) or {}
        if local_snapshot.get("loaded") and local_snapshot.get("index_map"):
            return dict(local_snapshot.get("index_map") or {})

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
                df = self._call_pro_ths_index(exchange="A", type=ths_type)
            except TypeError:
                df = self._call_pro_ths_index(type=ths_type)
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

        self._ensure_local_ths_concept_snapshot_loaded()
        local_snapshot = getattr(self, "_local_ths_concept_snapshot", None) or {}
        if local_snapshot.get("loaded"):
            return list((local_snapshot.get("stock_to_codes") or {}).get(normalized) or [])

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

        df = self._call_pro_ths_member(con_code=normalized)
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
            limitup_df = self._call_pro_limit_list_d(
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
            work = work[work["ts_code"].map(is_sector_scan_board_eligible)]
            if work.empty:
                return {
                    "rows": [],
                    "data_trade_date": trade_date,
                    "status": "empty",
                    "message": "涨停列表仅包含非板块扫描市场股票",
                }
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
                quote_df = self._call_pro_ths_daily(trade_date=trade_date)
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
            df = self._call_pro_limit_list_d(
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

    def get_concept_sectors_from_limitup_with_meta(
        self,
        trade_date: str,
        *,
        prefer_today: bool = False,
    ) -> Dict[str, object]:
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

    def get_limitup_industry_sectors_with_meta(
        self,
        trade_date: str,
        *,
        prefer_today: bool = False,
    ) -> Dict[str, object]:
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
            df = self._call_pro_limit_list_d(
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

    def _is_realtime_limit_candidate(self, ts_code: str, change_pct: float) -> bool:
        normalized = normalize_ts_code(ts_code)
        if not normalized:
            return False
        code = normalized.split(".")[0]
        threshold = 19.0 if code.startswith(("300", "301", "688")) else 9.5
        return float(change_pct or 0) >= threshold

    def _build_realtime_stock_dict_from_public_row(
        self,
        row: Dict[str, object],
        stock_meta_map: Dict[str, Dict[str, str]],
        *,
        trade_date: str,
        quote_time: Optional[str],
        candidate_source_tag: str = "",
    ) -> Dict:
        ts_code = str(row.get("TS_CODE") or "").strip()
        meta = stock_meta_map.get(ts_code) or {}
        stock_name = str(meta.get("stock_name") or row.get("NAME") or ts_code).strip() or ts_code
        sector_name = str(meta.get("industry") or "").strip() or "未知"
        price = float(row.get("PRICE") or 0)
        amount = float(row.get("AMOUNT") or 0)
        volume = float(row.get("VOLUME") or 0)
        intraday_volume_ratio = None
        return {
            "ts_code": ts_code,
            "stock_name": stock_name,
            "sector_name": sector_name,
            "close": price,
            "change_pct": float(row.get("PCT_CHANGE") or 0),
            "turnover_rate": float(row.get("TURNOVER_RATE") or 0),
            "amount": amount,
            "vol_ratio": intraday_volume_ratio,
            "high": float(row.get("HIGH") or price),
            "low": float(row.get("LOW") or price),
            "open": float(row.get("OPEN") or price),
            "pre_close": float(row.get("CLOSE") or 0),
            "candidate_source_tag": candidate_source_tag,
            "volume": volume,
            "avg_price": self._infer_realtime_avg_price(price, amount, volume),
            "intraday_volume_ratio": intraday_volume_ratio,
            "quote_time": quote_time,
            "data_source": "realtime_em",
            "concept_names": [],
        }

    def _build_realtime_stock_candidates_from_public_aggregate(
        self,
        trade_date: str,
        *,
        top_gainers: int,
        pct_floor: float,
    ) -> Optional[Dict[str, object]]:
        payload = self._fetch_public_aggregate_stock_rows(trade_date)
        if not payload:
            return None

        rows = payload.get("rows") or []
        if not rows:
            return None

        stock_meta_map = self._get_stock_basic_snapshot_map()
        quote_time = payload.get("quote_time")
        merged: Dict[str, Dict] = {}

        eligible_rows = [
            row for row in rows
            if is_sector_scan_board_eligible(str(row.get("TS_CODE") or "").strip())
            and float(row.get("PRICE") or 0) > 0
            and float(row.get("CLOSE") or 0) > 0
        ]
        if not eligible_rows:
            return None

        top_n = max(1, min(top_gainers, 300))
        top_rows = sorted(
            eligible_rows,
            key=lambda item: float(item.get("PCT_CHANGE") or 0),
            reverse=True,
        )[:top_n]
        for row in top_rows:
            ts_code = str(row.get("TS_CODE") or "").strip()
            merged[ts_code] = self._build_realtime_stock_dict_from_public_row(
                row,
                stock_meta_map,
                trade_date=trade_date,
                quote_time=quote_time,
                candidate_source_tag="涨幅前列",
            )

        anomaly_rows = sorted(
            eligible_rows,
            key=lambda item: (
                float(item.get("AMOUNT") or 0),
                float(item.get("PCT_CHANGE") or 0),
            ),
            reverse=True,
        )[: min(120, max(top_n, 40))]
        for row in anomaly_rows:
            ts_code = str(row.get("TS_CODE") or "").strip()
            intraday_volume_ratio = None
            turnover_rate = float(row.get("TURNOVER_RATE") or 0)
            realtime_anomaly = (
                intraday_volume_ratio is not None and intraday_volume_ratio >= 2.5
            ) or (
                intraday_volume_ratio is None
                and turnover_rate >= 10
                and float(row.get("PCT_CHANGE") or 0) > pct_floor
                and float(row.get("AMOUNT") or 0) >= 50000000
            )
            if realtime_anomaly:
                if ts_code in merged:
                    merged[ts_code]["intraday_volume_ratio"] = intraday_volume_ratio
                    merged[ts_code]["vol_ratio"] = intraday_volume_ratio
                    merged[ts_code] = self._append_candidate_source(merged[ts_code], "量比异动")
                else:
                    record = self._build_realtime_stock_dict_from_public_row(
                        row,
                        stock_meta_map,
                        trade_date=trade_date,
                        quote_time=quote_time,
                        candidate_source_tag="量比异动",
                    )
                    merged[ts_code] = record

            if self._is_realtime_limit_candidate(ts_code, float(row.get("PCT_CHANGE") or 0)):
                if ts_code in merged:
                    merged[ts_code] = self._append_candidate_source(merged[ts_code], "涨停入选")
                else:
                    merged[ts_code] = self._build_realtime_stock_dict_from_public_row(
                        row,
                        stock_meta_map,
                        trade_date=trade_date,
                        quote_time=quote_time,
                        candidate_source_tag="涨停入选",
                    )

        result = list(merged.values())
        result.sort(key=lambda x: x["change_pct"], reverse=True)
        return {
            "rows": result,
            "data_trade_date": payload.get("data_trade_date"),
            "used_mock": False,
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

    def _fetch_recent_stock_daily_df(
        self,
        trade_date: str,
        *,
        prefer_today: bool = False,
    ) -> Dict[str, object]:
        """获取最近一个有 daily 个股数据的交易日明细。"""
        if not self.token:
            return {"df": None, "data_trade_date": trade_date, "used_mock": True}

        effective_trade_date = (
            self._resolve_trade_date(trade_date)
            if prefer_today
            else self.get_last_completed_trade_date(trade_date)
        )
        for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
            df = self._cached_pro_daily(trade_date=data_trade_date)
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
            daily_basic_df = self._cached_pro_daily_basic(
                trade_date=effective_trade_date,
                fields="ts_code,turnover_rate,volume_ratio",
            )

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
        prefer_today: bool = False,
    ) -> Dict[str, object]:
        """扩展候选池，并返回实际使用的数据交易日。"""
        compact_trade_date = str(trade_date).replace("-", "").strip()[:8]
        mode_tag = "prefer_today" if prefer_today else "stable"
        cache_key = (
            f"{compact_trade_date}:{int(top_gainers)}:{float(vol_ratio_min):.4f}:"
            f"{float(pct_floor):.4f}:{mode_tag}"
        )
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
            if prefer_today:
                realtime_payload = self._build_realtime_stock_candidates_from_public_aggregate(
                    compact_trade_date,
                    top_gainers=top_gainers,
                    pct_floor=pct_floor,
                )
                if realtime_payload and realtime_payload.get("rows"):
                    self._cache_expanded_stock_list(
                        cache_key,
                        realtime_payload,
                        compact_trade_date,
                        str(realtime_payload.get("data_trade_date") or compact_trade_date),
                    )
                    logger.info(
                        f"扩展个股候选（{realtime_payload.get('data_trade_date')}）: 共 "
                        f"{len(realtime_payload.get('rows') or [])} 只 "
                        f"(公开实时候选优先, 涨幅前{max(1, min(top_gainers, 300))}+近似涨停+量比异动)"
                    )
                    return copy.deepcopy(realtime_payload)

            payload = self._fetch_recent_stock_daily_df(
                compact_trade_date,
                prefer_today=prefer_today,
            )
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
            df_up = self._call_pro_limit_list_d(
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
                "data_status": (
                    "fallback"
                    if prefer_today and effective_trade_date != compact_trade_date
                    else "ok"
                ),
                "data_message": (
                    f"当日实时候选源暂不可用，候选股已回退到 {effective_trade_date[:4]}-{effective_trade_date[4:6]}-{effective_trade_date[6:8]}。"
                    if prefer_today and effective_trade_date != compact_trade_date
                    else ""
                ),
            }
            self._cache_expanded_stock_list(cache_key, response, compact_trade_date, effective_trade_date)
            return copy.deepcopy(response)
        except Exception as e:
            logger.error(f"获取扩展个股列表失败: {e}")
            error_meta = self._build_data_error_meta(e)
            result = {
                "rows": [],
                "data_trade_date": compact_trade_date,
                "used_mock": False,
                **error_meta,
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
        cached_detail = self._get_cached_stock_detail(ts_code, trade_date)
        if cached_detail is not None:
            return cached_detail

        stock_meta_map = self._get_stock_basic_snapshot_map() if self.token else {}
        detail = self._build_lightweight_stock_detail(
            ts_code,
            trade_date,
            stock_meta_map=stock_meta_map,
        )

        if not self.token:
            return self._cache_stock_detail(
                ts_code,
                trade_date,
                detail,
                resolved_trade_date=trade_date,
            )

        if self._is_stock_detail_quota_limited():
            return self._cache_stock_detail(
                ts_code,
                trade_date,
                detail,
                resolved_trade_date=trade_date,
            )

        try:
            effective_trade_date = self._resolve_trade_date(trade_date)

            stock_meta = (stock_meta_map.get(ts_code) or {})
            if stock_meta:
                detail["stock_name"] = str(
                    stock_meta.get("stock_name") or detail["stock_name"] or ts_code
                )
                detail["sector_name"] = str(
                    stock_meta.get("industry") or detail["sector_name"] or "未知"
                )
            try:
                detail["concept_names"] = self._get_ths_concept_names_for_stock(ts_code)
            except Exception as e:
                if self._is_tushare_quota_error(e):
                    self._mark_stock_detail_quota_limited(e)
                logger.debug(f"个股题材补全失败 {ts_code}: {e}")
                detail["concept_names"] = []

            daily_basic = getattr(self.pro, "daily_basic", None)

            for data_trade_date in self._recent_open_dates(effective_trade_date, count=5):
                try:
                    df = self._cached_pro_daily(
                        ts_code=ts_code,
                        start_date=data_trade_date,
                        end_date=data_trade_date,
                    )
                except Exception as e:
                    if self._is_tushare_quota_error(e):
                        self._mark_stock_detail_quota_limited(e)
                        return self._cache_stock_detail(
                            ts_code,
                            trade_date,
                            detail,
                            resolved_trade_date=trade_date,
                        )
                    raise
                if df is None or df.empty:
                    continue

                row = df.iloc[0]
                turnover_rate = float(row.get("vol", 0)) / 10000
                vol_ratio = 1.5
                if callable(daily_basic):
                    try:
                        basic_df = self._cached_pro_daily_basic(
                            ts_code=ts_code,
                            trade_date=data_trade_date,
                            fields="ts_code,turnover_rate,volume_ratio",
                        )
                    except Exception as e:
                        if self._is_tushare_quota_error(e):
                            self._mark_stock_detail_quota_limited(e)
                            return self._cache_stock_detail(
                                ts_code,
                                trade_date,
                                self._overlay_realtime_detail_with_options(
                                    detail,
                                    trade_date,
                                    allow_intraday_volume_ratio=False,
                                ),
                                resolved_trade_date=data_trade_date,
                            )
                        raise
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
                self._clear_stock_detail_quota_limited()
                return self._cache_stock_detail(
                    ts_code,
                    trade_date,
                    self._overlay_realtime_detail(detail, trade_date),
                    resolved_trade_date=data_trade_date,
                )

            return self._cache_stock_detail(
                ts_code,
                trade_date,
                self._overlay_realtime_detail(detail, trade_date),
                resolved_trade_date=effective_trade_date,
            )
        except Exception as e:
            if self._is_tushare_quota_error(e):
                self._mark_stock_detail_quota_limited(e)
            logger.error(f"获取个股详情失败: {e}")
            return self._cache_stock_detail(
                ts_code,
                trade_date,
                detail,
                resolved_trade_date=trade_date,
            )

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
            daily_basic_df = self._cached_pro_daily_basic(
                trade_date=effective_trade_date,
                fields="ts_code,turnover_rate,volume_ratio",
            )

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
        return self._overlay_realtime_detail_with_options(
            detail,
            trade_date,
            allow_intraday_volume_ratio=True,
        )

    def _overlay_realtime_detail_with_options(
        self,
        detail: Dict,
        trade_date: str,
        *,
        allow_intraday_volume_ratio: bool = True,
    ) -> Dict:
        """对单只股票详情做盘中价格覆盖。"""
        if not detail:
            return detail
        if not self._should_use_realtime_quote(trade_date):
            detail.setdefault("data_source", "daily_fallback")
            return detail

        quote_map = self._fetch_realtime_stock_quote_map([detail.get("ts_code", "")])
        realtime = quote_map.get(normalize_ts_code(detail.get("ts_code", "")))
        if not realtime:
            detail.setdefault("data_source", "daily_fallback")
            return detail

        intraday_volume_ratio = None
        if allow_intraday_volume_ratio:
            try:
                intraday_volume_ratio = self._infer_intraday_volume_ratio(
                    detail.get("ts_code", ""),
                    trade_date,
                    float(realtime.get("close") or 0),
                    float(realtime.get("amount") or 0),
                    float(realtime.get("volume") or 0),
                    realtime.get("quote_time"),
                )
            except Exception as e:
                logger.debug(f"实时详情量比推断失败 {detail.get('ts_code')}: {e}")

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

            self._log_tushare_api_call(
                "pro.daily",
                trade_date=query_dates[0],
                extra={
                    "ts_code": normalize_ts_code(ts_code),
                    "start_date": query_dates[-1],
                    "end_date": query_dates[0],
                },
            )
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
            stock_info = self._call_pro_stock_basic(ts_code=ts_code)
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
