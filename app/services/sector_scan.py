"""
板块扫描服务
"""
from typing import List, Dict, Optional
from loguru import logger
from datetime import datetime, timedelta

from app.data.tushare_client import is_sector_scan_board_eligible
from app.models.schemas import (
    MarketEnvOutput,
    MarketEnvTag,
    SectorOutput,
    SectorMainlineTag,
    SectorContinuityTag,
    SectorTradeabilityTag,
    SectorTierTag,
    SectorActionHint,
    SectorRotationTag,
    SectorDimensionScores,
    SectorLeaderStock,
    SectorTopStock,
    SectorScanResponse,
    LeaderSectorResponse,
    SectorTopStocksResponse,
)
from app.services.market_data_gateway import market_data_gateway


class SectorScanService:
    """板块扫描服务"""

    # 板块主线判定阈值（基于行业平均涨跌幅，比个股阈值低）
    # 行业平均 > 1.0% 在 A 股中已属强势，> 0.5% 即值得关注
    MAINLINE_CHANGE_THRESHOLD = 2.5   # 行业均值 >= 2.5% 视为主线
    SUB_MAINLINE_THRESHOLD = 1.5      # 行业均值 >= 1.5% 视为次主线
    FOLLOW_THRESHOLD = 0.5            # 行业均值 >= 0.5% 视为跟风
    INDUSTRY_ONLY_MAINLINE_THRESHOLD = 1.0   # 仅行业均值时，适度放宽阈值
    INDUSTRY_ONLY_SUB_MAINLINE_THRESHOLD = 0.6
    INDUSTRY_ONLY_FOLLOW_THRESHOLD = 0.2
    LIMITUP_INDUSTRY_MAINLINE_THRESHOLD = 1.8
    LIMITUP_INDUSTRY_SUB_MAINLINE_THRESHOLD = 0.9
    LIMITUP_INDUSTRY_FOLLOW_THRESHOLD = 0.3
    ATTACK_THRESHOLD_DELTA = -0.2
    DEFENSE_THRESHOLD_DELTA = 0.3

    # 连续性判定
    CONTINUITY_DAYS_STRONG = 3  # 连续 3 天以上强势
    CONTINUITY_DAYS_MODERATE = 2  # 连续 2 天

    def __init__(self):
        self.client = market_data_gateway

    def scan(
        self,
        trade_date: str,
        limit_output: bool = True,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> SectorScanResponse:
        """
        扫描当日板块

        Args:
            trade_date: 交易日

        Returns:
            板块扫描结果
        """
        compact_trade_date = trade_date.replace("-", "")
        resolved_trade_date = self.client._resolve_trade_date(compact_trade_date)

        # 获取板块数据
        sector_payload = self._get_sector_data(resolved_trade_date)
        resolved_trade_date = sector_payload.get("data_trade_date") or resolved_trade_date
        resolved_trade_date_fmt = (
            f"{resolved_trade_date[:4]}-{resolved_trade_date[4:6]}-{resolved_trade_date[6:8]}"
        )
        sector_data = sector_payload["rows"]
        sector_data_mode = sector_payload["sector_data_mode"]
        threshold_profile = self._resolve_threshold_profile(
            sector_data_mode,
            market_env,
        )

        # 排序并打分
        scored_sectors = self._score_sectors(
            sector_data,
            resolved_trade_date_fmt,
            data_mode=sector_data_mode,
            market_env=market_env,
        )

        # 分类输出
        mainline = []
        sub_mainline = []
        follow = []
        trash = []

        for sector in scored_sectors:
            if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
                mainline.append(sector)
            elif sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
                sub_mainline.append(sector)
            elif sector.sector_mainline_tag == SectorMainlineTag.FOLLOW:
                follow.append(sector)
            else:
                trash.append(sector)

        if limit_output:
            mainline = mainline[:5]
            sub_mainline = sub_mainline[:5]
            follow = follow[:10]
            trash = trash[:10]

        return SectorScanResponse(
            trade_date=trade_date,
            resolved_trade_date=resolved_trade_date_fmt,
            sector_data_mode=sector_data_mode,
            concept_data_status=sector_payload.get("concept_data_status"),
            concept_data_message=sector_payload.get("concept_data_message"),
            threshold_profile=threshold_profile,
            mainline_sectors=mainline,
            sub_mainline_sectors=sub_mainline,
            follow_sectors=follow,
            trash_sectors=trash,
            total_sectors=len(scored_sectors)
        )

    def limit_scan_result(
        self,
        scan_result: SectorScanResponse,
    ) -> SectorScanResponse:
        """将完整板块扫描结果裁剪为页面展示尺寸。"""
        return scan_result.model_copy(
            update={
                "mainline_sectors": list(scan_result.mainline_sectors[:5]),
                "sub_mainline_sectors": list(scan_result.sub_mainline_sectors[:5]),
                "follow_sectors": list(scan_result.follow_sectors[:10]),
                "trash_sectors": list(scan_result.trash_sectors[:10]),
            },
            deep=True,
        )

    def get_leader(
        self,
        trade_date: str,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> LeaderSectorResponse:
        """
        获取当日主线板块

        Args:
            trade_date: 交易日

        Returns:
            最重要的主线板块
        """
        scan_result = self.scan(
            trade_date,
            limit_output=False,
            market_env=market_env,
        )
        return self.build_leader_from_scan(trade_date, scan_result)

    def build_leader_from_scan(
        self,
        trade_date: str,
        scan_result: SectorScanResponse,
    ) -> LeaderSectorResponse:
        """基于已完成的板块扫描结果生成主线板块响应。"""

        if scan_result.mainline_sectors:
            leader = scan_result.mainline_sectors[0]
        elif scan_result.sub_mainline_sectors:
            leader = scan_result.sub_mainline_sectors[0]
        else:
            # 没有主线，返回第一个
            scan_result.mainline_sectors = scan_result.sub_mainline_sectors[:1] if scan_result.sub_mainline_sectors else []
            leader = scan_result.mainline_sectors[0] if scan_result.mainline_sectors else None

            if not leader:
                # 返回空的主线
                leader = SectorOutput(
                    sector_name="无明确主线",
                    sector_change_pct=0,
                    sector_strength_rank=999,
                    sector_mainline_tag=SectorMainlineTag.TRASH,
                    sector_continuity_tag=SectorContinuityTag.CAUTION,
                    sector_tradeability_tag=SectorTradeabilityTag.NOT_RECOMMENDED,
                    sector_comment="未识别到明确主线板块"
                )

        return LeaderSectorResponse(
            trade_date=trade_date,
            resolved_trade_date=scan_result.resolved_trade_date,
            sector_data_mode=scan_result.sector_data_mode,
            threshold_profile=scan_result.threshold_profile,
            concept_data_status=scan_result.concept_data_status,
            concept_data_message=scan_result.concept_data_message,
            sector=leader,
            leader_stocks=self._pick_leader_stocks(trade_date, leader),
        )

    def build_sector_top_stocks_from_scan(
        self,
        trade_date: str,
        scan_result: SectorScanResponse,
        sector_name: str,
        sector_source_type: Optional[str] = None,
        limit: int = 10,
    ) -> Optional[SectorTopStocksResponse]:
        """基于已完成的板块扫描结果生成板块 Top 股票响应。"""
        sector = self._find_sector_from_scan(
            scan_result,
            sector_name=sector_name,
            sector_source_type=sector_source_type,
        )
        if sector is None:
            return None

        top_stocks = self._pick_top_stocks(
            trade_date,
            sector,
            count=limit,
        )
        return SectorTopStocksResponse(
            trade_date=trade_date,
            resolved_trade_date=scan_result.resolved_trade_date,
            sector_data_mode=scan_result.sector_data_mode,
            threshold_profile=scan_result.threshold_profile,
            concept_data_status=scan_result.concept_data_status,
            concept_data_message=scan_result.concept_data_message,
            sector=sector,
            top_stocks=top_stocks,
            total=len(top_stocks),
        )

    def _find_sector_from_scan(
        self,
        scan_result: SectorScanResponse,
        sector_name: str,
        sector_source_type: Optional[str] = None,
    ) -> Optional[SectorOutput]:
        target_name = str(sector_name or "").strip()
        target_source = str(sector_source_type or "").strip()
        if not target_name:
            return None

        all_sectors = (
            list(scan_result.mainline_sectors or [])
            + list(scan_result.sub_mainline_sectors or [])
            + list(scan_result.follow_sectors or [])
            + list(scan_result.trash_sectors or [])
        )
        if target_source:
            for row in all_sectors:
                if row.sector_name == target_name and row.sector_source_type == target_source:
                    return row
        for row in all_sectors:
            if row.sector_name == target_name:
                return row
        return None

    def _build_top_stock_role_tag(self, index: int) -> str:
        if index == 0:
            return "龙头"
        if index == 1:
            return "中军"
        if index == 2:
            return "趋势核心"
        return "前排活跃"

    def _pick_top_stocks(
        self,
        trade_date: str,
        sector: SectorOutput,
        count: int = 10,
    ) -> List[SectorTopStock]:
        """为任意板块返回 Top 股票。"""
        compact_trade_date = trade_date.replace("-", "")
        try:
            if sector.sector_source_type == "concept":
                payload = self.client.get_expanded_stock_list_with_meta(
                    compact_trade_date,
                    top_gainers=max(150, count * 15),
                )
                rows = payload.get("rows") or []
                matched = [
                    row for row in rows
                    if str(row.get("sector_name") or "") == sector.sector_name
                    or sector.sector_name in (row.get("concept_names") or [])
                ]
                matched = [
                    row for row in matched
                    if is_sector_scan_board_eligible(row.get("ts_code") or "")
                ]
                matched.sort(
                    key=lambda row: (
                        "涨停入选" in str(row.get("candidate_source_tag") or ""),
                        float(row.get("amount") or 0),
                        float(row.get("change_pct") or 0),
                        float(row.get("turnover_rate") or 0),
                        float(row.get("vol_ratio") or 1),
                    ),
                    reverse=True,
                )
                return [
                    SectorTopStock(
                        rank=index + 1,
                        ts_code=str(row.get("ts_code") or ""),
                        stock_name=str(row.get("stock_name") or row.get("ts_code") or ""),
                        change_pct=round(float(row.get("change_pct") or 0), 2),
                        amount=round(float(row.get("amount") or 0), 2),
                        turnover_rate=round(float(row.get("turnover_rate") or 0), 2),
                        vol_ratio=round(float(row.get("vol_ratio") or 1), 2),
                        role_tag=self._build_top_stock_role_tag(index),
                        candidate_source_tag=row.get("candidate_source_tag"),
                        top_reason="题材辨识度高，且涨幅、成交额或活跃度居前",
                        quote_time=row.get("quote_time"),
                        data_source=row.get("data_source"),
                    )
                    for index, row in enumerate(matched[:count])
                    if row.get("ts_code")
                ]

            if sector.sector_source_type == "limitup_industry" and getattr(
                self.client,
                "pro",
                None,
            ):
                effective_trade_date = self.client._resolve_trade_date(compact_trade_date)
                df_up = self.client.pro.limit_list_d(
                    trade_date=effective_trade_date,
                    limit_type="U",
                )
                if df_up is not None and not df_up.empty:
                    work = df_up.copy()
                    work = work[
                        work["industry"].fillna("").astype(str).str.strip()
                        == sector.sector_name
                    ]
                    work = work[
                        work["ts_code"].fillna("").astype(str).map(is_sector_scan_board_eligible)
                    ]
                    if not work.empty:
                        work["pct_chg"] = work["pct_chg"].fillna(0)
                        work["amount"] = work["amount"].fillna(0)
                        work["turn_over"] = work["turn_over"].fillna(0)
                        work["open_times"] = work["open_times"].fillna(99)
                        work = work.sort_values(
                            ["open_times", "amount", "pct_chg", "turn_over"],
                            ascending=[True, False, False, False],
                        )
                        return [
                            SectorTopStock(
                                rank=index + 1,
                                ts_code=str(row.get("ts_code") or ""),
                                stock_name=str(row.get("name") or row.get("ts_code") or ""),
                                change_pct=round(float(row.get("pct_chg") or 0), 2),
                                amount=round(float(row.get("amount") or 0), 2),
                                turnover_rate=round(float(row.get("turn_over") or 0), 2),
                                vol_ratio=1.0,
                                role_tag=self._build_top_stock_role_tag(index),
                                candidate_source_tag="涨停前排",
                                top_reason="涨停行业前排，炸板次数更少且成交额更强",
                                data_source="limit_list_d",
                            )
                            for index, (_, row) in enumerate(work.head(count).iterrows())
                            if row.get("ts_code")
                        ]

            payload = self.client._fetch_recent_stock_daily_df(compact_trade_date)
            df = payload.get("df")
            if df is None or df.empty:
                return []

            stock_meta_map = self.client._get_stock_basic_snapshot_map()
            daily_basic_df = None
            daily_basic = getattr(getattr(self.client, "pro", None), "daily_basic", None)
            if callable(daily_basic):
                data_trade_date = str(payload.get("data_trade_date") or compact_trade_date)
                try:
                    daily_basic_df = daily_basic(
                        trade_date=data_trade_date,
                        fields="ts_code,turnover_rate,volume_ratio",
                    )
                except TypeError:
                    daily_basic_df = daily_basic(trade_date=data_trade_date)

            work = self.client._build_daily_stock_source_df(
                df,
                stock_meta_map,
                daily_basic_df=daily_basic_df,
            )
            if work is None or work.empty:
                return []

            work = work[work["industry"].fillna("") == sector.sector_name]
            work = work[work["ts_code"].fillna("").astype(str).map(is_sector_scan_board_eligible)]
            if work.empty:
                return []

            work["pct_change"] = work["pct_change"].fillna(0)
            work["amount"] = work["amount"].fillna(0)
            work["turnover_rate"] = work["turnover_rate"].fillna(0)
            work["volume_ratio"] = work["volume_ratio"].fillna(1.0)
            work = work.sort_values(
                ["pct_change", "amount", "turnover_rate", "volume_ratio"],
                ascending=False,
            )

            return [
                SectorTopStock(
                    rank=index + 1,
                    ts_code=str(row.get("ts_code") or ""),
                    stock_name=str(row.get("stock_name") or row.get("ts_code") or ""),
                    change_pct=round(float(row.get("pct_change") or 0), 2),
                    amount=round(float(row.get("amount") or 0), 2),
                    turnover_rate=round(float(row.get("turnover_rate") or 0), 2),
                    vol_ratio=round(float(row.get("volume_ratio") or 1), 2),
                    role_tag=self._build_top_stock_role_tag(index),
                    candidate_source_tag="行业前排",
                    top_reason="行业前排股，涨幅、成交额与换手表现居前",
                    data_source="daily",
                )
                for index, (_, row) in enumerate(work.head(count).iterrows())
                if row.get("ts_code")
            ]
        except Exception as e:
            logger.warning(f"获取板块 Top 股票失败: {e}")
            return []

    def _get_sector_data(self, trade_date: str) -> Dict[str, object]:
        """
        获取板块数据：优先走独立题材聚合；
        若题材不可用，则退回涨停行业聚合；最后再用申万行业均值补充。
        """
        try:
            compact = trade_date.replace("-", "")
            industry_meta = self.client.get_sector_data_with_meta(compact)
            actual_trade_date = str(industry_meta.get("data_trade_date") or compact)
            industry_rows = industry_meta.get("rows") or []
            concept_meta = self.client.get_concept_sectors_from_limitup_with_meta(actual_trade_date)
            concept_rows = concept_meta.get("rows") or []
            limitup_industry_meta = None
            limitup_industry_rows: List[Dict] = []
            if not concept_rows and concept_meta.get("status") != "ok":
                limitup_industry_meta = self.client.get_limitup_industry_sectors_with_meta(
                    actual_trade_date
                )
                limitup_industry_rows = limitup_industry_meta.get("rows") or []

            concept_rows = [{**r, "sector_source_type": "concept"} for r in concept_rows]
            limitup_industry_rows = [
                {**r, "sector_source_type": "limitup_industry"}
                for r in limitup_industry_rows
            ]
            industry_rows = [{**r, "sector_source_type": "industry"} for r in industry_rows]
            primary_rows = concept_rows or limitup_industry_rows
            seen_names = {r.get("sector_name", "") for r in primary_rows}
            merged: List[Dict] = list(primary_rows)
            for r in industry_rows:
                name = r.get("sector_name", "")
                if name and name not in seen_names:
                    merged.append(r)
                    seen_names.add(name)
            if not merged:
                if industry_meta.get("used_mock"):
                    return {
                        "rows": self.client._mock_sector_data(),
                        "sector_data_mode": "mock",
                        "concept_data_status": self._resolve_concept_status(
                            concept_meta, limitup_industry_meta
                        ),
                        "concept_data_message": self._resolve_concept_message(
                            concept_meta, limitup_industry_meta
                        ),
                        "data_trade_date": actual_trade_date,
                    }
                return {
                    "rows": [],
                    "sector_data_mode": "empty",
                    "concept_data_status": self._resolve_concept_status(
                        concept_meta, limitup_industry_meta
                    ),
                    "concept_data_message": self._resolve_concept_message(
                        concept_meta, limitup_industry_meta
                    ),
                    "data_trade_date": actual_trade_date,
                }
            if concept_rows:
                sector_data_mode = "hybrid"
            elif limitup_industry_rows:
                sector_data_mode = "limitup_industry_hybrid"
            else:
                sector_data_mode = "industry_only"
            return {
                "rows": merged,
                "sector_data_mode": sector_data_mode,
                "concept_data_status": self._resolve_concept_status(
                    concept_meta, limitup_industry_meta
                ),
                "concept_data_message": self._resolve_concept_message(
                    concept_meta, limitup_industry_meta
                ),
                "data_trade_date": actual_trade_date,
            }
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return {
                "rows": self.client._mock_sector_data(),
                "sector_data_mode": "mock",
                "concept_data_status": "error",
                "concept_data_message": f"板块扫描降级为 mock：{e}",
                "data_trade_date": compact,
            }

    def _resolve_concept_status(
        self,
        concept_meta: Dict[str, object],
        limitup_industry_meta: Optional[Dict[str, object]] = None,
    ) -> Optional[str]:
        """汇总题材/涨停行业聚合状态，供前端展示。"""
        if concept_meta.get("status") == "ok":
            return "ok"
        if limitup_industry_meta and limitup_industry_meta.get("status") == "ok":
            return "limitup_industry_ok"
        return str(concept_meta.get("status") or "")

    def _resolve_concept_message(
        self,
        concept_meta: Dict[str, object],
        limitup_industry_meta: Optional[Dict[str, object]] = None,
    ) -> Optional[str]:
        """汇总题材/涨停行业聚合说明，供前端展示。"""
        if concept_meta.get("status") == "ok":
            return str(concept_meta.get("message") or "")
        if limitup_industry_meta and limitup_industry_meta.get("status") == "ok":
            return "涨停列表未提供 theme 字段，已改为按涨停 industry 字段聚合，并用行业均值补充。"
        return str(concept_meta.get("message") or "")

    def _resolve_threshold_profile(
        self,
        data_mode: str,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> str:
        """根据口径与市场环境返回当前阈值档位。"""
        env_tag = market_env.market_env_tag if market_env else None
        if env_tag == MarketEnvTag.DEFENSE:
            return "defensive"
        if env_tag == MarketEnvTag.ATTACK and data_mode != "industry_only":
            return "attack"
        if data_mode == "industry_only":
            return "relaxed"
        return "strict"

    def _build_threshold_config(
        self,
        data_mode: str,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> Dict[str, float]:
        """按板块口径与市场环境生成主线判定阈值。"""
        if data_mode == "industry_only":
            config = {
                "mainline_threshold": self.INDUSTRY_ONLY_MAINLINE_THRESHOLD,
                "sub_mainline_threshold": self.INDUSTRY_ONLY_SUB_MAINLINE_THRESHOLD,
                "follow_threshold": self.INDUSTRY_ONLY_FOLLOW_THRESHOLD,
                "mainline_score": 65.0,
                "sub_mainline_score": 45.0,
            }
        elif data_mode == "limitup_industry_hybrid":
            config = {
                "mainline_threshold": self.LIMITUP_INDUSTRY_MAINLINE_THRESHOLD,
                "sub_mainline_threshold": self.LIMITUP_INDUSTRY_SUB_MAINLINE_THRESHOLD,
                "follow_threshold": self.LIMITUP_INDUSTRY_FOLLOW_THRESHOLD,
                "mainline_score": 65.0,
                "sub_mainline_score": 45.0,
            }
        else:
            config = {
                "mainline_threshold": self.MAINLINE_CHANGE_THRESHOLD,
                "sub_mainline_threshold": self.SUB_MAINLINE_THRESHOLD,
                "follow_threshold": self.FOLLOW_THRESHOLD,
                "mainline_score": 70.0,
                "sub_mainline_score": 50.0,
            }

        env_tag = market_env.market_env_tag if market_env else None
        if env_tag == MarketEnvTag.ATTACK:
            config["mainline_threshold"] = max(
                0.3,
                config["mainline_threshold"] + self.ATTACK_THRESHOLD_DELTA,
            )
            config["sub_mainline_threshold"] = max(
                0.2,
                config["sub_mainline_threshold"] + self.ATTACK_THRESHOLD_DELTA,
            )
            config["follow_threshold"] = max(
                0.0,
                config["follow_threshold"] + self.ATTACK_THRESHOLD_DELTA / 2,
            )
            config["mainline_score"] = max(55.0, config["mainline_score"] - 5)
            config["sub_mainline_score"] = max(40.0, config["sub_mainline_score"] - 5)
        elif env_tag == MarketEnvTag.DEFENSE:
            config["mainline_threshold"] += self.DEFENSE_THRESHOLD_DELTA
            config["sub_mainline_threshold"] += self.DEFENSE_THRESHOLD_DELTA / 2
            config["follow_threshold"] += self.DEFENSE_THRESHOLD_DELTA / 3
            config["mainline_score"] += 5
            config["sub_mainline_score"] += 5

        return config

    def _pick_leader_stocks(
        self,
        trade_date: str,
        sector: SectorOutput,
        count: int = 3,
    ) -> List[SectorLeaderStock]:
        """为主线板块挑选 1-3 只风向标个股。"""
        compact_trade_date = trade_date.replace("-", "")
        try:
            if sector.sector_source_type == "concept":
                payload = self.client.get_expanded_stock_list_with_meta(
                    compact_trade_date,
                    top_gainers=150,
                )
                rows = payload.get("rows") or []
                matched = [
                    row for row in rows
                    if str(row.get("sector_name") or "") == sector.sector_name
                ]
                matched = [
                    row for row in matched
                    if is_sector_scan_board_eligible(row.get("ts_code") or "")
                ]
                matched.sort(
                    key=lambda row: (
                        "涨停入选" in str(row.get("candidate_source_tag") or ""),
                        float(row.get("amount") or 0),
                        float(row.get("change_pct") or 0),
                    ),
                    reverse=True,
                )
                return [
                    SectorLeaderStock(
                        ts_code=str(row.get("ts_code") or ""),
                        stock_name=str(row.get("stock_name") or row.get("ts_code") or ""),
                        change_pct=round(float(row.get("change_pct") or 0), 2),
                        amount=round(float(row.get("amount") or 0), 2),
                        candidate_source_tag=row.get("candidate_source_tag"),
                        leader_reason="题材辨识度高，且在候选池中居前",
                        quote_time=row.get("quote_time"),
                        data_source=row.get("data_source"),
                    )
                    for row in matched[:count]
                    if row.get("ts_code")
                ]

            if sector.sector_source_type == "limitup_industry" and getattr(
                self.client,
                "pro",
                None,
            ):
                effective_trade_date = self.client._resolve_trade_date(
                    compact_trade_date,
                )
                df_up = self.client.pro.limit_list_d(
                    trade_date=effective_trade_date,
                    limit_type="U",
                )
                if df_up is not None and not df_up.empty:
                    work = df_up.copy()
                    work = work[
                        work["industry"].fillna("").astype(str).str.strip()
                        == sector.sector_name
                    ]
                    work = work[
                        work["ts_code"].fillna("").astype(str).map(is_sector_scan_board_eligible)
                    ]
                    if not work.empty:
                        work["pct_chg"] = work["pct_chg"].fillna(0)
                        work["amount"] = work["amount"].fillna(0)
                        work["open_times"] = work["open_times"].fillna(99)
                        work = work.sort_values(
                            ["open_times", "amount", "pct_chg"],
                            ascending=[True, False, False],
                        )
                        return [
                            SectorLeaderStock(
                                ts_code=str(row.get("ts_code") or ""),
                                stock_name=str(
                                    row.get("name") or row.get("ts_code") or ""
                                ),
                                change_pct=round(
                                    float(row.get("pct_chg") or 0),
                                    2,
                                ),
                                amount=round(float(row.get("amount") or 0), 2),
                                candidate_source_tag="涨停前排",
                                leader_reason="涨停行业前排，炸板次数更少且成交额居前",
                                data_source="limit_list_d",
                            )
                            for _, row in work.head(count).iterrows()
                            if row.get("ts_code")
                        ]

            payload = self.client._fetch_recent_stock_daily_df(compact_trade_date)
            df = payload.get("df")
            if df is None or df.empty:
                return []

            stock_meta_map = self.client._get_stock_basic_snapshot_map()
            daily_basic_df = None
            daily_basic = getattr(getattr(self.client, "pro", None), "daily_basic", None)
            if callable(daily_basic):
                data_trade_date = str(payload.get("data_trade_date") or compact_trade_date)
                try:
                    daily_basic_df = daily_basic(
                        trade_date=data_trade_date,
                        fields="ts_code,turnover_rate,volume_ratio",
                    )
                except TypeError:
                    daily_basic_df = daily_basic(trade_date=data_trade_date)

            work = self.client._build_daily_stock_source_df(
                df,
                stock_meta_map,
                daily_basic_df=daily_basic_df,
            )
            if work is None or work.empty:
                return []

            work = work[work["industry"].fillna("") == sector.sector_name]
            work = work[work["ts_code"].fillna("").astype(str).map(is_sector_scan_board_eligible)]
            if work.empty:
                return []

            work["pct_change"] = work["pct_change"].fillna(0)
            work["amount"] = work["amount"].fillna(0)
            work["turnover_rate"] = work["turnover_rate"].fillna(0)
            work = work.sort_values(
                ["pct_change", "amount", "turnover_rate"],
                ascending=False,
            )

            return [
                SectorLeaderStock(
                    ts_code=str(row.get("ts_code") or ""),
                    stock_name=str(row.get("stock_name") or row.get("ts_code") or ""),
                    change_pct=round(float(row.get("pct_change") or 0), 2),
                    amount=round(float(row.get("amount") or 0), 2),
                    candidate_source_tag="行业前排",
                    leader_reason="行业前排股，涨幅与成交额居前",
                    data_source="daily",
                )
                for _, row in work.head(count).iterrows()
                if row.get("ts_code")
            ]
        except Exception as e:
            logger.warning(f"挑选板块风向标失败: {e}")
            return []

    def _build_dynamic_sector_metrics(
        self,
        trade_date: Optional[str],
    ) -> Dict[tuple[str, str], Dict]:
        """基于当日个股快照补充板块动态联动指标。"""
        if not trade_date:
            return {}
        try:
            payload = self.client.get_expanded_stock_list_with_meta(
                trade_date.replace("-", ""),
                top_gainers=300,
            )
            rows = payload.get("rows") or []
        except Exception as exc:
            logger.warning(f"构建板块动态联动指标失败: {exc}")
            return {}

        metrics: Dict[tuple[str, str], Dict] = {}
        grouped: Dict[tuple[str, str], List[Dict]] = {}
        for row in rows:
            sector_name = str(row.get("sector_name") or "").strip()
            if not sector_name:
                continue
            key = (sector_name, "industry")
            grouped.setdefault(key, []).append(row)

        for key, items in grouped.items():
            sorted_rows = sorted(
                items,
                key=lambda row: (
                    float(row.get("change_pct") or 0),
                    float(row.get("amount") or 0),
                ),
                reverse=True,
            )
            front_count = sum(1 for row in items if float(row.get("change_pct") or 0) >= 5.0)
            follow_count = sum(1 for row in items if float(row.get("change_pct") or 0) >= 1.5)
            rebound_samples = 0
            rebound_hits = 0
            for row in items:
                close = float(row.get("close") or 0)
                open_price = float(row.get("open") or 0)
                avg_price = float(row.get("avg_price") or 0)
                if close <= 0 or open_price <= 0:
                    continue
                rebound_samples += 1
                if close >= open_price and (avg_price <= 0 or close >= avg_price):
                    rebound_hits += 1
            afternoon_rebound_strength = (
                round(rebound_hits / rebound_samples, 3) if rebound_samples > 0 else 0.0
            )

            leader_broken = False
            leader = sorted_rows[0] if sorted_rows else None
            if leader:
                leader_close = float(leader.get("close") or 0)
                leader_avg = float(leader.get("avg_price") or 0)
                leader_change = float(leader.get("change_pct") or 0)
                leader_broken = bool(
                    leader_close > 0 and (
                        (leader_avg > 0 and leader_close < leader_avg)
                        or leader_change < 0.5
                    )
                )

            metrics[key] = {
                "front_runner_count": front_count,
                "follow_runner_count": follow_count,
                "afternoon_rebound_strength": afternoon_rebound_strength,
                "leader_broken": leader_broken,
            }
        return metrics

    def _score_sectors(
        self,
        sectors: List[Dict],
        trade_date: Optional[str] = None,
        data_mode: str = "hybrid",
        market_env: Optional[MarketEnvOutput] = None,
    ) -> List[SectorOutput]:
        """
        对板块进行评分和分类

        Args:
            sectors: 原始板块数据

        Returns:
            评分后的板块列表
        """
        result = []
        ranked_sectors = self._rank_sectors_within_source(sectors)
        dynamic_metrics = self._build_dynamic_sector_metrics(trade_date)

        continuity_days_map = (
            self._build_continuity_days_map(trade_date, ranked_sectors)
            if trade_date else {}
        )

        source_totals: Dict[str, int] = {}
        source_ranks: Dict[str, int] = {}
        for sector in ranked_sectors:
            source_type = sector.get("sector_source_type") or "industry"
            source_totals[source_type] = source_totals.get(source_type, 0) + 1

        for sector in ranked_sectors:
            change_pct = sector.get("sector_change_pct", 0)
            source_type = sector.get("sector_source_type") or "industry"
            source_rank = source_ranks.get(source_type, 0)
            source_total = source_totals.get(source_type, len(ranked_sectors))
            source_ranks[source_type] = source_rank + 1

            # 计算基础评分
            strength_score = self._calculate_strength_score(change_pct, source_rank, source_total)

            # 确定主线标签
            mainline_tag = self._determine_mainline_tag(
                change_pct,
                strength_score,
                data_mode,
                market_env=market_env,
            )

            # 确定连续性标签（简化版，实际需要历史数据）
            continuity_days = continuity_days_map.get(
                (source_type, sector.get("sector_name", "")),
                0,
            )
            continuity_tag = self._determine_continuity_tag(strength_score, continuity_days)

            # 确定交易性标签
            tradeability_tag = self._determine_tradeability_tag(
                mainline_tag,
                continuity_tag,
                change_pct,
                market_env=market_env,
            )
            sector_dynamic = dynamic_metrics.get((sector.get("sector_name", "未知"), source_type), {})
            dimension_scores = self._calculate_dimension_scores(
                sector=sector,
                source_rank=source_rank,
                source_total=source_total,
                continuity_days=continuity_days,
                continuity_tag=continuity_tag,
                mainline_tag=mainline_tag,
                tradeability_tag=tradeability_tag,
                market_env=market_env,
            )
            rotation_tag, rotation_reason = self._determine_sector_rotation(
                sector=sector,
                mainline_tag=mainline_tag,
                continuity_days=continuity_days,
                dynamic_metrics=sector_dynamic,
            )
            sector_tier = self._determine_sector_tier(
                dimension_scores=dimension_scores,
                mainline_tag=mainline_tag,
            )
            action_hint = self._determine_action_hint(
                sector_tier=sector_tier,
                tradeability_tag=tradeability_tag,
                continuity_tag=continuity_tag,
                market_env=market_env,
                change_pct=change_pct,
            )

            reason_tags = self._build_sector_reason_tags(
                sector=sector,
                source_type=source_type,
                source_rank=source_rank,
                source_total=source_total,
                strength_score=strength_score,
                continuity_days=continuity_days,
                mainline_tag=mainline_tag,
                tradeability_tag=tradeability_tag,
                dimension_scores=dimension_scores,
                sector_tier=sector_tier,
                action_hint=action_hint,
                rotation_tag=rotation_tag,
                data_mode=data_mode,
            )

            # 生成板块简评
            comment = self._generate_sector_comment(
                mainline_tag, continuity_tag, tradeability_tag, change_pct, rotation_tag
            )

            output = SectorOutput(
                sector_name=sector.get("sector_name", "未知"),
                sector_source_type=source_type,
                sector_change_pct=change_pct,
                sector_score=round(strength_score, 1),
                sector_strength_rank=0,
                sector_mainline_tag=mainline_tag,
                sector_continuity_tag=continuity_tag,
                sector_tradeability_tag=tradeability_tag,
                sector_continuity_days=continuity_days,
                sector_turnover=sector.get("sector_turnover"),
                sector_stock_count=sector.get("stock_count"),
                sector_reason_tags=reason_tags,
                sector_comment=comment,
                sector_dimension_scores=dimension_scores,
                sector_tier=sector_tier,
                sector_action_hint=action_hint,
                sector_rotation_tag=rotation_tag,
                sector_rotation_reason=rotation_reason,
                sector_summary_reason=self._build_sector_summary_reason(
                    dimension_scores=dimension_scores,
                    sector_tier=sector_tier,
                    action_hint=action_hint,
                    rotation_tag=rotation_tag,
                ),
                sector_news_summary=sector.get("sector_news_summary"),
                sector_falsification=sector.get("sector_falsification"),
                front_runner_count=sector_dynamic.get("front_runner_count"),
                follow_runner_count=sector_dynamic.get("follow_runner_count"),
                afternoon_rebound_strength=sector_dynamic.get("afternoon_rebound_strength"),
                leader_broken=sector_dynamic.get("leader_broken"),
            )

            result.append(output)

        # 汇总榜单按涨幅优先，再看成交额与成分股数量
        result.sort(
            key=lambda x: (
                x.sector_change_pct,
                next(
                    (
                        float(s.get("sector_turnover", 0) or 0)
                        for s in ranked_sectors
                        if s.get("sector_name") == x.sector_name
                        and (s.get("sector_source_type") or "industry") == x.sector_source_type
                    ),
                    0.0,
                ),
            ),
            reverse=True,
        )

        # 重新编号
        for idx, sector in enumerate(result):
            sector.sector_strength_rank = idx + 1

        return result

    def _rank_sectors_within_source(self, sectors: List[Dict]) -> List[Dict]:
        """题材与行业分组排序，避免不同口径直接共享排名分。"""
        grouped: Dict[str, List[Dict]] = {}
        for sector in sectors:
            source_type = sector.get("sector_source_type") or "industry"
            grouped.setdefault(source_type, []).append(sector)

        ranked: List[Dict] = []
        for source_type in ["concept", "limitup_industry", "industry", "mock"]:
            rows = grouped.pop(source_type, [])
            rows.sort(
                key=lambda s: (
                    float(s.get("sector_change_pct", 0) or 0),
                    float(s.get("sector_turnover", 0) or 0),
                    int(s.get("stock_count", 0) or 0),
                ),
                reverse=True,
            )
            ranked.extend(rows)

        for rows in grouped.values():
            rows.sort(
                key=lambda s: (
                    float(s.get("sector_change_pct", 0) or 0),
                    float(s.get("sector_turnover", 0) or 0),
                    int(s.get("stock_count", 0) or 0),
                ),
                reverse=True,
            )
            ranked.extend(rows)

        return ranked

    def _calculate_strength_score(self, change_pct: float, rank: int, total: int) -> float:
        """
        计算板块强度评分 (0-100)

        Args:
            change_pct: 涨跌幅
            rank: 排名
            total: 总数
        """
        # 基础分：行业均值 -3% → 0 分，+3% → 100 分
        base_score = (change_pct + 3) / 6 * 100

        # 排名分：排名前 10% 加分
        if rank < total * 0.1:
            base_score += 20
        elif rank < total * 0.2:
            base_score += 10

        return max(0, min(100, base_score))

    def _determine_mainline_tag(
        self,
        change_pct: float,
        strength_score: float,
        data_mode: str = "hybrid",
        market_env: Optional[MarketEnvOutput] = None,
    ) -> SectorMainlineTag:
        """确定板块主线标签"""
        config = self._build_threshold_config(data_mode, market_env)
        mainline_threshold = config["mainline_threshold"]
        sub_mainline_threshold = config["sub_mainline_threshold"]
        follow_threshold = config["follow_threshold"]
        mainline_score = config["mainline_score"]
        sub_mainline_score = config["sub_mainline_score"]

        # 涨幅和强度都高才是主线
        if change_pct >= mainline_threshold and strength_score >= mainline_score:
            return SectorMainlineTag.MAINLINE
        elif change_pct >= sub_mainline_threshold and strength_score >= sub_mainline_score:
            return SectorMainlineTag.SUB_MAINLINE
        elif change_pct >= follow_threshold:
            return SectorMainlineTag.FOLLOW
        else:
            return SectorMainlineTag.TRASH

    def _determine_continuity_tag(self, strength_score: float, continuity_days: int) -> SectorContinuityTag:
        """确定板块连续性标签"""
        if continuity_days >= self.CONTINUITY_DAYS_STRONG:
            return SectorContinuityTag.SUSTAINABLE
        if continuity_days >= self.CONTINUITY_DAYS_MODERATE:
            return SectorContinuityTag.OBSERVABLE
        if continuity_days == 0:
            # 缺少历史连续性时，保守降级为可观察，不直接视为可持续
            if strength_score >= 60:
                return SectorContinuityTag.OBSERVABLE
            return SectorContinuityTag.CAUTION
        if strength_score >= 50:
            return SectorContinuityTag.OBSERVABLE
        return SectorContinuityTag.CAUTION

    def _build_continuity_days_map(self, trade_date: str, sectors: List[Dict]) -> Dict[tuple[str, str], int]:
        """计算板块连续活跃天数（按来源分别回看近5个唯一交易日）。"""
        continuity_map: Dict[tuple[str, str], int] = {}
        for sector in sectors:
            name = sector.get("sector_name", "")
            source_type = sector.get("sector_source_type") or "industry"
            if name:
                continuity_map[(source_type, name)] = 0
        if not continuity_map:
            return continuity_map

        lookback_dates = self._get_recent_effective_trade_dates(trade_date, count=5)
        industry_history: List[Dict[str, float]] = []
        concept_history: List[Dict[str, float]] = []
        limitup_industry_history: List[Dict[str, float]] = []
        for d in lookback_dates:
            try:
                industry_rows = self.client.get_sector_data(d)
                industry_history.append({
                    r.get("sector_name", ""): float(r.get("sector_change_pct", 0) or 0)
                    for r in industry_rows
                })
            except Exception:
                industry_history.append({})
            try:
                concept_rows = self.client.get_concept_sectors_from_limitup(d)
                concept_history.append({
                    r.get("sector_name", ""): float(r.get("sector_change_pct", 0) or 0)
                    for r in concept_rows
                })
            except Exception:
                concept_history.append({})
            try:
                limitup_industry_rows = self.client.get_limitup_industry_sectors(d)
                limitup_industry_history.append({
                    r.get("sector_name", ""): float(r.get("sector_change_pct", 0) or 0)
                    for r in limitup_industry_rows
                })
            except Exception:
                limitup_industry_history.append({})

        for source_type, name in list(continuity_map.keys()):
            count = 0
            if source_type == "concept":
                history = concept_history
            elif source_type == "limitup_industry":
                history = limitup_industry_history
            else:
                history = industry_history
            for day_map in history:
                if day_map.get(name, -999) > 0:
                    count += 1
                else:
                    break
            continuity_map[(source_type, name)] = count
        return continuity_map

    def _get_recent_effective_trade_dates(self, trade_date: str, count: int = 5) -> List[str]:
        """获取近若干个唯一交易日，避免周末回退导致同一天重复统计。"""
        dt = datetime.strptime(trade_date, "%Y-%m-%d")
        resolved_dates: List[str] = []
        seen = set()
        for i in range(0, 14):
            natural_day = (dt - timedelta(days=i)).strftime("%Y%m%d")
            effective_day = self.client._resolve_trade_date(natural_day)
            if effective_day in seen:
                continue
            seen.add(effective_day)
            resolved_dates.append(effective_day)
            if len(resolved_dates) >= count:
                break
        return resolved_dates

    def _determine_tradeability_tag(
        self,
        mainline_tag: SectorMainlineTag,
        continuity_tag: SectorContinuityTag,
        change_pct: float,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> SectorTradeabilityTag:
        """确定板块交易性标签"""
        env_tag = market_env.market_env_tag if market_env else None
        # 主线且可持续，可以交易
        if mainline_tag in [SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE]:
            if continuity_tag == SectorContinuityTag.SUSTAINABLE:
                return SectorTradeabilityTag.TRADABLE
            elif (
                continuity_tag == SectorContinuityTag.OBSERVABLE
                and env_tag == MarketEnvTag.ATTACK
                and mainline_tag == SectorMainlineTag.MAINLINE
                and change_pct <= 6.5
            ):
                return SectorTradeabilityTag.TRADABLE
            elif continuity_tag == SectorContinuityTag.OBSERVABLE:
                return SectorTradeabilityTag.CAUTION

        # 跟风板块谨慎
        if mainline_tag == SectorMainlineTag.FOLLOW:
            # 涨幅过大可能是末端
            if change_pct > 5 or env_tag == MarketEnvTag.DEFENSE:
                return SectorTradeabilityTag.NOT_RECOMMENDED
            return SectorTradeabilityTag.CAUTION

        # 杂毛不建议
        return SectorTradeabilityTag.NOT_RECOMMENDED

    def _turnover_score(self, turnover: float) -> float:
        """将成交额映射为 0-100 分。"""
        if turnover >= 500:
            return 100.0
        if turnover >= 300:
            return 85.0
        if turnover >= 150:
            return 70.0
        if turnover >= 50:
            return 55.0
        if turnover >= 20:
            return 40.0
        return 20.0

    def _calculate_dimension_scores(
        self,
        sector: Dict,
        source_rank: int,
        source_total: int,
        continuity_days: int,
        continuity_tag: SectorContinuityTag,
        mainline_tag: SectorMainlineTag,
        tradeability_tag: SectorTradeabilityTag,
        market_env: Optional[MarketEnvOutput] = None,
    ) -> SectorDimensionScores:
        """基于现有字段生成五维评分。"""
        stock_count = int(sector.get("stock_count", 0) or 0)
        turnover = float(sector.get("sector_turnover", 0) or 0)
        change_pct = float(sector.get("sector_change_pct", 0) or 0)
        percentile = 1.0
        if source_total > 1:
            percentile = 1 - (source_rank / max(source_total - 1, 1))

        linkage_score = min(
            100.0,
            min(stock_count, 10) / 10 * 55
            + percentile * 25
            + max(0.0, min(100.0, (change_pct + 1.0) / 4.5 * 100)) * 0.2,
        )
        capital_score = min(
            100.0,
            self._turnover_score(turnover) * 0.75 + percentile * 25,
        )

        continuity_score = 35.0
        if continuity_days >= self.CONTINUITY_DAYS_STRONG:
            continuity_score = 90.0
        elif continuity_days >= self.CONTINUITY_DAYS_MODERATE:
            continuity_score = 75.0
        elif continuity_days == 1:
            continuity_score = 55.0
        elif continuity_tag == SectorContinuityTag.OBSERVABLE:
            continuity_score = 45.0

        resilience_score = (
            continuity_score * 0.45
            + linkage_score * 0.3
            + capital_score * 0.25
        )
        if change_pct > 8:
            resilience_score -= 10
        if market_env and market_env.market_env_tag == MarketEnvTag.DEFENSE:
            resilience_score -= 5
        resilience_score = max(0.0, min(100.0, resilience_score))

        tradeability_score = {
            SectorTradeabilityTag.TRADABLE: 85.0,
            SectorTradeabilityTag.CAUTION: 60.0,
            SectorTradeabilityTag.NOT_RECOMMENDED: 25.0,
        }[tradeability_tag]
        if 2.0 <= change_pct <= 6.5:
            tradeability_score += 10
        if change_pct > 8:
            tradeability_score -= 15
        if mainline_tag == SectorMainlineTag.MAINLINE:
            tradeability_score += 5
        tradeability_score = max(0.0, min(100.0, tradeability_score))

        return SectorDimensionScores(
            linkage_score=round(linkage_score, 1),
            capital_score=round(capital_score, 1),
            continuity_score=round(continuity_score, 1),
            resilience_score=round(resilience_score, 1),
            tradeability_score=round(tradeability_score, 1),
        )

    def _determine_sector_tier(
        self,
        dimension_scores: SectorDimensionScores,
        mainline_tag: SectorMainlineTag,
    ) -> SectorTierTag:
        """将五维评分映射为 A/B/C。"""
        if (
            mainline_tag in [SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE]
            and dimension_scores.linkage_score >= 65
            and dimension_scores.capital_score >= 60
            and dimension_scores.continuity_score >= 55
            and dimension_scores.resilience_score >= 60
            and dimension_scores.tradeability_score >= 65
        ):
            return SectorTierTag.A

        avg_score = (
            dimension_scores.linkage_score
            + dimension_scores.capital_score
            + dimension_scores.continuity_score
            + dimension_scores.resilience_score
            + dimension_scores.tradeability_score
        ) / 5
        if mainline_tag != SectorMainlineTag.TRASH and avg_score >= 50:
            return SectorTierTag.B
        return SectorTierTag.C

    def _determine_action_hint(
        self,
        sector_tier: SectorTierTag,
        tradeability_tag: SectorTradeabilityTag,
        continuity_tag: SectorContinuityTag,
        market_env: Optional[MarketEnvOutput],
        change_pct: float,
    ) -> SectorActionHint:
        """根据分级与交易性映射为执行建议。"""
        if (
            sector_tier == SectorTierTag.A
            and tradeability_tag == SectorTradeabilityTag.TRADABLE
            and not (
                market_env
                and market_env.market_env_tag == MarketEnvTag.DEFENSE
                and continuity_tag != SectorContinuityTag.SUSTAINABLE
            )
            and change_pct <= 7.0
        ):
            return SectorActionHint.EXECUTABLE
        if sector_tier in [SectorTierTag.A, SectorTierTag.B]:
            return SectorActionHint.OBSERVE
        return SectorActionHint.AVOID

    def _determine_sector_rotation(
        self,
        sector: Dict,
        mainline_tag: SectorMainlineTag,
        continuity_days: int,
        dynamic_metrics: Optional[Dict],
    ) -> tuple[SectorRotationTag, str]:
        """识别方向是否强化、切换或衰减。"""
        dynamic_metrics = dynamic_metrics or {}
        rebound = float(dynamic_metrics.get("afternoon_rebound_strength") or 0.0)
        front_count = int(dynamic_metrics.get("front_runner_count") or 0)
        follow_count = int(dynamic_metrics.get("follow_runner_count") or 0)
        leader_broken = bool(dynamic_metrics.get("leader_broken"))
        change_pct = float(sector.get("sector_change_pct", 0) or 0.0)
        stock_count = int(sector.get("stock_count", 0) or 0)

        if leader_broken:
            return SectorRotationTag.WEAKENING, "前排龙头承接走弱，方向有衰减迹象。"
        if (
            continuity_days <= 2
            and mainline_tag in {SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE}
            and (rebound >= 0.55 or front_count >= 2 or change_pct >= 2.5)
        ):
            return SectorRotationTag.STRENGTHENING, "午后回流和前排扩散增强，方向处于强化阶段。"
        if (
            continuity_days <= 2
            and (rebound >= 0.35 or follow_count >= max(2, min(stock_count, 4)))
            and change_pct >= 1.0
        ):
            return SectorRotationTag.ROTATING, "联动开始扩散，方向处于切换确认阶段。"
        if continuity_days >= 4 and mainline_tag == SectorMainlineTag.MAINLINE:
            return SectorRotationTag.STABLE, "连续性和强度较稳定，仍是当前主线锚。"
        return SectorRotationTag.NEUTRAL, "方向暂无明确强化或衰减信号。"

    def _build_sector_summary_reason(
        self,
        dimension_scores: SectorDimensionScores,
        sector_tier: SectorTierTag,
        action_hint: SectorActionHint,
        rotation_tag: SectorRotationTag,
    ) -> str:
        """输出一句话主线总结，便于前端流程头部展示。"""
        reasons: List[str] = []
        if dimension_scores.linkage_score >= 65:
            reasons.append("联动强")
        elif dimension_scores.linkage_score >= 50:
            reasons.append("联动尚可")

        if dimension_scores.capital_score >= 65:
            reasons.append("资金承接强")
        elif dimension_scores.capital_score >= 50:
            reasons.append("资金介入中等")

        if dimension_scores.continuity_score >= 70:
            reasons.append("持续性较好")
        elif dimension_scores.continuity_score >= 50:
            reasons.append("延续性待确认")

        if dimension_scores.resilience_score >= 60:
            reasons.append("抗分化较强")

        if rotation_tag != SectorRotationTag.NEUTRAL:
            reasons.append(rotation_tag.value)

        reasons.append(f"{sector_tier.value}类")
        reasons.append(action_hint.value)
        return "，".join(reasons[:5])

    def _generate_sector_comment(
        self,
        mainline_tag: SectorMainlineTag,
        continuity_tag: SectorContinuityTag,
        tradeability_tag: SectorTradeabilityTag,
        change_pct: float,
        rotation_tag: SectorRotationTag,
    ) -> str:
        """生成板块简评"""
        comments = []

        # 主线定性
        if mainline_tag == SectorMainlineTag.MAINLINE:
            comments.append("主线板块")
        elif mainline_tag == SectorMainlineTag.SUB_MAINLINE:
            comments.append("次主线")
        elif mainline_tag == SectorMainlineTag.FOLLOW:
            comments.append("跟风板块")
        else:
            comments.append("弱势板块")

        # 连续性
        if continuity_tag == SectorContinuityTag.SUSTAINABLE:
            comments.append("具备持续性")
        elif continuity_tag == SectorContinuityTag.CAUTION:
            comments.append("注意末端风险")

        # 交易建议
        if tradeability_tag == SectorTradeabilityTag.TRADABLE:
            comments.append("可交易")
        elif tradeability_tag == SectorTradeabilityTag.CAUTION:
            comments.append("谨慎参与")
        else:
            comments.append("不建议")

        if rotation_tag != SectorRotationTag.NEUTRAL:
            comments.append(rotation_tag.value)

        return "，".join(comments)

    def _build_sector_reason_tags(
        self,
        sector: Dict,
        source_type: str,
        source_rank: int,
        source_total: int,
        strength_score: float,
        continuity_days: int,
        mainline_tag: SectorMainlineTag,
        tradeability_tag: SectorTradeabilityTag,
        dimension_scores: SectorDimensionScores,
        sector_tier: SectorTierTag,
        action_hint: SectorActionHint,
        rotation_tag: SectorRotationTag,
        data_mode: str,
    ) -> List[str]:
        """构建结构化解释标签，便于前端展示与复盘。"""
        tags: List[str] = []

        if source_type == "concept":
            tags.append("题材口径")
        elif source_type == "limitup_industry":
            tags.append("涨停行业口径")
        else:
            tags.append("行业口径")
        tags.append(f"涨幅{float(sector.get('sector_change_pct', 0) or 0):.2f}%")
        tags.append(f"评分{strength_score:.1f}")

        if source_total > 0:
            percentile = (source_rank + 1) / source_total
            if percentile <= 0.1:
                tags.append("组内前10%")
            elif percentile <= 0.2:
                tags.append("组内前20%")

        turnover = float(sector.get("sector_turnover", 0) or 0)
        if turnover >= 500:
            tags.append("高成交额")
        elif turnover >= 100:
            tags.append("中高成交额")

        stock_count = int(sector.get("stock_count", 0) or 0)
        if stock_count >= 8:
            tags.append("成分扩散较好")
        elif 0 < stock_count <= 2 and source_type == "concept":
            tags.append("题材集中度高")

        if continuity_days >= self.CONTINUITY_DAYS_STRONG:
            tags.append(f"连续{continuity_days}天活跃")
        elif continuity_days >= self.CONTINUITY_DAYS_MODERATE:
            tags.append(f"连续{continuity_days}天走强")
        elif continuity_days == 0:
            tags.append("连续性待确认")

        if data_mode == "industry_only":
            tags.append("行业兜底模式")

        if mainline_tag == SectorMainlineTag.MAINLINE:
            tags.append("主线候选")
        elif mainline_tag == SectorMainlineTag.SUB_MAINLINE:
            tags.append("次主线候选")

        if dimension_scores.linkage_score >= 65:
            tags.append("联动强")
        elif dimension_scores.linkage_score >= 50:
            tags.append("联动尚可")

        if dimension_scores.capital_score >= 65:
            tags.append("资金强")
        elif dimension_scores.capital_score >= 50:
            tags.append("资金中等")

        if tradeability_tag == SectorTradeabilityTag.TRADABLE:
            tags.append("可交易")
        elif tradeability_tag == SectorTradeabilityTag.CAUTION:
            tags.append("需确认")
        else:
            tags.append("暂不参与")

        if rotation_tag != SectorRotationTag.NEUTRAL:
            tags.append(rotation_tag.value)

        tags.append(f"{sector_tier.value}类")
        tags.append(action_hint.value)
        return tags


# 全局服务实例
sector_scan_service = SectorScanService()
