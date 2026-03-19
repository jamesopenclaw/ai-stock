"""
板块扫描服务
"""
from typing import List, Dict, Optional
from loguru import logger

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

    # 板块主线判定阈值
    MAINLINE_CHANGE_THRESHOLD = 2.5  # 涨幅 > 2.5% 可能是主线
    SUB_MAINLINE_THRESHOLD = 1.5      # 涨幅 > 1.5% 可能是次主线
    FOLLOW_THRESHOLD = 0.5            # 涨幅 > 0.5% 可能是跟风

    # 连续性判定
    CONTINUITY_DAYS_STRONG = 3  # 连续 3 天以上强势
    CONTINUITY_DAYS_MODERATE = 2  # 连续 2 天

    def __init__(self):
        self.client = tushare_client

    def scan(self, trade_date: str) -> SectorScanResponse:
        """
        扫描当日板块

        Args:
            trade_date: 交易日

        Returns:
            板块扫描结果
        """
        # 获取板块数据
        sector_data = self._get_sector_data(trade_date)

        # 排序并打分
        scored_sectors = self._score_sectors(sector_data)

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

        return SectorScanResponse(
            trade_date=trade_date,
            mainline_sectors=mainline[:5],  # 最多 5 个主线
            sub_mainline_sectors=sub_mainline[:5],  # 最多 5 个次主线
            follow_sectors=follow[:10],  # 最多 10 个跟风
            trash_sectors=trash[:10],  # 最多 10 个杂毛
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
        scan_result = self.scan(trade_date)

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
            sector=leader
        )

    def _get_sector_data(self, trade_date: str) -> List[Dict]:
        """获取板块数据"""
        try:
            return self.client.get_sector_data(trade_date.replace("-", ""))
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return self.client._mock_sector_data()

    def _score_sectors(self, sectors: List[Dict]) -> List[SectorOutput]:
        """
        对板块进行评分和分类

        Args:
            sectors: 原始板块数据

        Returns:
            评分后的板块列表
        """
        result = []

        for idx, sector in enumerate(sectors):
            change_pct = sector.get("sector_change_pct", 0)

            # 计算基础评分
            strength_score = self._calculate_strength_score(change_pct, idx, len(sectors))

            # 确定主线标签
            mainline_tag = self._determine_mainline_tag(change_pct, strength_score)

            # 确定连续性标签（简化版，实际需要历史数据）
            continuity_tag = self._determine_continuity_tag(strength_score)

            # 确定交易性标签
            tradeability_tag = self._determine_tradeability_tag(
                mainline_tag, continuity_tag, change_pct
            )

            # 生成板块简评
            comment = self._generate_sector_comment(
                mainline_tag, continuity_tag, tradeability_tag, change_pct
            )

            output = SectorOutput(
                sector_name=sector.get("sector_name", "未知"),
                sector_change_pct=change_pct,
                sector_strength_rank=idx + 1,
                sector_mainline_tag=mainline_tag,
                sector_continuity_tag=continuity_tag,
                sector_tradeability_tag=tradeability_tag,
                sector_continuity_days=continuity_tag.value if continuity_tag == SectorContinuityTag.SUSTAINABLE else 0,
                sector_comment=comment,
                sector_news_summary=sector.get("sector_news_summary"),
                sector_falsification=sector.get("sector_falsification")
            )

            result.append(output)

        # 按强度排序
        result.sort(key=lambda x: x.sector_change_pct, reverse=True)

        # 重新编号
        for idx, sector in enumerate(result):
            sector.sector_strength_rank = idx + 1

        return result

    def _calculate_strength_score(self, change_pct: float, rank: int, total: int) -> float:
        """
        计算板块强度评分 (0-100)

        Args:
            change_pct: 涨跌幅
            rank: 排名
            total: 总数
        """
        # 基础分：涨幅得分
        base_score = (change_pct + 5) * 10  # -5% -> 0, 5% -> 100

        # 排名分：排名前 10% 加分
        if rank < total * 0.1:
            base_score += 20
        elif rank < total * 0.2:
            base_score += 10

        return max(0, min(100, base_score))

    def _determine_mainline_tag(self, change_pct: float, strength_score: float) -> SectorMainlineTag:
        """确定板块主线标签"""
        # 涨幅和强度都高才是主线
        if change_pct >= self.MAINLINE_CHANGE_THRESHOLD and strength_score >= 70:
            return SectorMainlineTag.MAINLINE
        elif change_pct >= self.SUB_MAINLINE_THRESHOLD and strength_score >= 50:
            return SectorMainlineTag.SUB_MAINLINE
        elif change_pct >= self.FOLLOW_THRESHOLD:
            return SectorMainlineTag.FOLLOW
        else:
            return SectorMainlineTag.TRASH

    def _determine_continuity_tag(self, strength_score: float) -> SectorContinuityTag:
        """确定板块连续性标签"""
        # 简化：强度高认为可持续
        if strength_score >= 80:
            return SectorContinuityTag.SUSTAINABLE
        elif strength_score >= 50:
            return SectorContinuityTag.OBSERVABLE
        else:
            return SectorContinuityTag.CAUTION

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


# 全局服务实例
sector_scan_service = SectorScanService()
