"""
板块扫描服务
"""
from typing import List, Dict, Optional
from loguru import logger
from datetime import datetime, timedelta

from app.models.schemas import (
    SectorOutput,
    SectorMainlineTag,
    SectorContinuityTag,
    SectorTradeabilityTag,
    SectorScanResponse,
    LeaderSectorResponse
)
from app.data.tushare_client import tushare_client


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

    # 连续性判定
    CONTINUITY_DAYS_STRONG = 3  # 连续 3 天以上强势
    CONTINUITY_DAYS_MODERATE = 2  # 连续 2 天

    def __init__(self):
        self.client = tushare_client

    def scan(self, trade_date: str, limit_output: bool = True) -> SectorScanResponse:
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
        threshold_profile = "relaxed" if sector_data_mode == "industry_only" else "strict"

        # 排序并打分
        scored_sectors = self._score_sectors(
            sector_data,
            resolved_trade_date_fmt,
            data_mode=sector_data_mode,
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
            threshold_profile=threshold_profile,
            mainline_sectors=mainline,
            sub_mainline_sectors=sub_mainline,
            follow_sectors=follow,
            trash_sectors=trash,
            total_sectors=len(scored_sectors)
        )

    def get_leader(self, trade_date: str) -> LeaderSectorResponse:
        """
        获取当日主线板块

        Args:
            trade_date: 交易日

        Returns:
            最重要的主线板块
        """
        scan_result = self.scan(trade_date, limit_output=False)

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
            sector=leader
        )

    def _get_sector_data(self, trade_date: str) -> Dict[str, object]:
        """
        获取板块数据：题材概念（涨停 theme 聚合）优先，申万行业均值补充，按 sector_name 去重。
        """
        try:
            compact = trade_date.replace("-", "")
            industry_meta = self.client.get_sector_data_with_meta(compact)
            actual_trade_date = str(industry_meta.get("data_trade_date") or compact)
            industry_rows = industry_meta.get("rows") or []
            concept_rows = self.client.get_concept_sectors_from_limitup(actual_trade_date)
            concept_rows = [{**r, "sector_source_type": "concept"} for r in concept_rows]
            industry_rows = [{**r, "sector_source_type": "industry"} for r in industry_rows]
            seen_names = {r.get("sector_name", "") for r in concept_rows}
            merged: List[Dict] = list(concept_rows)
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
                        "data_trade_date": actual_trade_date,
                    }
                return {
                    "rows": [],
                    "sector_data_mode": "empty",
                    "data_trade_date": actual_trade_date,
                }
            return {
                "rows": merged,
                "sector_data_mode": "hybrid" if concept_rows else "industry_only",
                "data_trade_date": actual_trade_date,
            }
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return {
                "rows": self.client._mock_sector_data(),
                "sector_data_mode": "mock",
                "data_trade_date": compact,
            }

    def _score_sectors(
        self,
        sectors: List[Dict],
        trade_date: Optional[str] = None,
        data_mode: str = "hybrid",
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
            mainline_tag = self._determine_mainline_tag(change_pct, strength_score, data_mode)

            # 确定连续性标签（简化版，实际需要历史数据）
            continuity_days = continuity_days_map.get(
                (source_type, sector.get("sector_name", "")),
                0,
            )
            continuity_tag = self._determine_continuity_tag(strength_score, continuity_days)

            # 确定交易性标签
            tradeability_tag = self._determine_tradeability_tag(
                mainline_tag, continuity_tag, change_pct
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
                data_mode=data_mode,
            )

            # 生成板块简评
            comment = self._generate_sector_comment(
                mainline_tag, continuity_tag, tradeability_tag, change_pct
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
                sector_news_summary=sector.get("sector_news_summary"),
                sector_falsification=sector.get("sector_falsification")
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
        for source_type in ["concept", "industry", "mock"]:
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
    ) -> SectorMainlineTag:
        """确定板块主线标签"""
        if data_mode == "industry_only":
            mainline_threshold = self.INDUSTRY_ONLY_MAINLINE_THRESHOLD
            sub_mainline_threshold = self.INDUSTRY_ONLY_SUB_MAINLINE_THRESHOLD
            follow_threshold = self.INDUSTRY_ONLY_FOLLOW_THRESHOLD
        else:
            mainline_threshold = self.MAINLINE_CHANGE_THRESHOLD
            sub_mainline_threshold = self.SUB_MAINLINE_THRESHOLD
            follow_threshold = self.FOLLOW_THRESHOLD

        # 涨幅和强度都高才是主线
        if change_pct >= mainline_threshold and strength_score >= 70:
            return SectorMainlineTag.MAINLINE
        elif change_pct >= sub_mainline_threshold and strength_score >= 50:
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

        for source_type, name in list(continuity_map.keys()):
            count = 0
            history = concept_history if source_type == "concept" else industry_history
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
        change_pct: float
    ) -> SectorTradeabilityTag:
        """确定板块交易性标签"""
        # 主线且可持续，可以交易
        if mainline_tag in [SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE]:
            if continuity_tag == SectorContinuityTag.SUSTAINABLE:
                return SectorTradeabilityTag.TRADABLE
            elif continuity_tag == SectorContinuityTag.OBSERVABLE:
                return SectorTradeabilityTag.CAUTION

        # 跟风板块谨慎
        if mainline_tag == SectorMainlineTag.FOLLOW:
            # 涨幅过大可能是末端
            if change_pct > 5:
                return SectorTradeabilityTag.NOT_RECOMMENDED
            return SectorTradeabilityTag.CAUTION

        # 杂毛不建议
        return SectorTradeabilityTag.NOT_RECOMMENDED

    def _generate_sector_comment(
        self,
        mainline_tag: SectorMainlineTag,
        continuity_tag: SectorContinuityTag,
        tradeability_tag: SectorTradeabilityTag,
        change_pct: float
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
        data_mode: str,
    ) -> List[str]:
        """构建结构化解释标签，便于前端展示与复盘。"""
        tags: List[str] = []

        tags.append("题材口径" if source_type == "concept" else "行业口径")
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

        if tradeability_tag == SectorTradeabilityTag.TRADABLE:
            tags.append("可交易")
        elif tradeability_tag == SectorTradeabilityTag.CAUTION:
            tags.append("需确认")
        else:
            tags.append("暂不参与")

        return tags


# 全局服务实例
sector_scan_service = SectorScanService()
