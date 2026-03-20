"""
个股筛选服务
"""
from typing import List, Dict, Optional
from loguru import logger

from app.models.schemas import (
    StockInput,
    StockOutput,
    StockStrengthTag,
    StockContinuityTag,
    StockTradeabilityTag,
    StockCoreTag,
    StockPoolTag,
    StockPoolsOutput,
    SectorMainlineTag,
    SectorTradeabilityTag,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service


class StockFilterService:
    """个股筛选服务"""

    # 涨跌幅阈值
    STRONG_CHANGE_THRESHOLD = 7.0   # 涨幅 > 7% 为强势
    MEDIUM_CHANGE_THRESHOLD = 3.0  # 涨幅 > 3% 为中等

    # 换手率阈值
    HIGH_TURNOVER = 15.0   # 高换手
    MEDIUM_TURNOVER = 8.0  # 中等换手

    def __init__(self):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service

    def filter(self, trade_date: str, stocks: List[StockInput]) -> List[StockOutput]:
        """
        个股筛选

        Args:
            trade_date: 交易日
            stocks: 个股列表

        Returns:
            筛选后的个股列表
        """
        # 获取市场环境和板块数据
        market_env = self.market_env_service.get_current_env(trade_date)
        sector_scan = self.sector_scan_service.scan(trade_date)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 筛选评分
        result = []
        for stock in stocks:
            output = self._score_stock(stock, market_env, sector_map)
            result.append(output)

        # 按涨幅排序
        result.sort(key=lambda x: x.change_pct, reverse=True)

        return result

    def classify_pools(
        self,
        trade_date: str,
        stocks: List[StockInput],
        holdings: List[Dict] = None
    ) -> StockPoolsOutput:
        """
        三池分类

        Args:
            trade_date: 交易日
            stocks: 候选个股列表
            holdings: 当前持仓列表

        Returns:
            三池分类结果
        """
        # 筛选评分
        scored_stocks = self.filter(trade_date, stocks)

        # 获取市场环境和板块
        market_env = self.market_env_service.get_current_env(trade_date)
        sector_scan = self.sector_scan_service.scan(trade_date)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 三池分类
        market_watch = []    # 市场最强观察池
        account_executable = []  # 账户可参与池
        holding_process = []  # 持仓处理池

        # 持仓代码集合
        holding_codes = set(h.get("ts_code") for h in (holdings or []))

        for stock in scored_stocks:
            # 分类到对应池
            if stock.ts_code in holding_codes:
                # 持仓处理池
                stock.stock_pool_tag = StockPoolTag.HOLDING_PROCESS
                holding_process.append(stock)
            elif stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE:
                # 可交易 -> 账户可参与池
                stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE
                account_executable.append(stock)
            else:
                # 市场最强观察池（不管能否交易，都放入观察）
                stock.stock_pool_tag = StockPoolTag.MARKET_WATCH
                market_watch.append(stock)

        return StockPoolsOutput(
            trade_date=trade_date,
            market_watch_pool=market_watch[:20],   # 最多20只
            account_executable_pool=account_executable[:10],  # 最多10只
            holding_process_pool=holding_process,  # 全部持仓
            total_count=len(scored_stocks)
        )

    def _build_sector_map(self, sector_scan) -> Dict:
        """构建板块映射"""
        sector_map = {}

        # 主线板块
        for s in sector_scan.mainline_sectors:
            sector_map[s.sector_name] = s

        # 次主线
        for s in sector_scan.sub_mainline_sectors:
            sector_map[s.sector_name] = s

        # 跟风
        for s in sector_scan.follow_sectors:
            sector_map[s.sector_name] = s

        return sector_map

    def _score_stock(
        self,
        stock: StockInput,
        market_env,
        sector_map: Dict
    ) -> StockOutput:
        """
        评分个股

        Args:
            stock: 个股数据
            market_env: 市场环境
            sector_map: 板块映射

        Returns:
            评分后的个股
        """
        # 获取所属板块
        sector = sector_map.get(stock.sector_name)

        # 计算强度评分
        strength_score = self._calculate_strength_score(stock, sector)

        # 确定强弱标签
        strength_tag = self._determine_strength_tag(stock.change_pct, strength_score)

        # 确定连续性标签
        continuity_tag = self._determine_continuity_tag(strength_score, stock)

        # 确定核心属性
        core_tag = self._determine_core_tag(stock, sector, strength_score)

        # 确定交易性标签
        tradeability_tag = self._determine_tradeability_tag(
            strength_tag, continuity_tag, core_tag, market_env
        )

        # 确定池标签（暂不赋值，由 classify_pools 处理）
        pool_tag = StockPoolTag.MARKET_WATCH

        # 生成证伪条件
        falsification = self._generate_falsification(stock, sector, core_tag)

        # 生成简评
        comment = self._generate_stock_comment(
            strength_tag, continuity_tag, tradeability_tag, sector
        )

        return StockOutput(
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            sector_name=stock.sector_name,
            change_pct=stock.change_pct,
            stock_strength_tag=strength_tag,
            stock_continuity_tag=continuity_tag,
            stock_tradeability_tag=tradeability_tag,
            stock_core_tag=core_tag,
            stock_pool_tag=pool_tag,
            stock_falsification_cond=falsification,
            stock_comment=comment
        )

    def _calculate_strength_score(self, stock: StockInput, sector) -> float:
        """计算强度评分 (0-100)"""
        score = 50  # 基础分

        # 涨跌幅得分
        if stock.change_pct >= self.STRONG_CHANGE_THRESHOLD:
            score += 30
        elif stock.change_pct >= self.MEDIUM_CHANGE_THRESHOLD:
            score += 15
        elif stock.change_pct > 0:
            score += 5
        else:
            score -= 10

        # 换手率得分
        if stock.turnover_rate >= self.HIGH_TURNOVER:
            score += 10
        elif stock.turnover_rate >= self.MEDIUM_TURNOVER:
            score += 5

        # 量比得分
        if stock.vol_ratio:
            if stock.vol_ratio >= 2:
                score += 10
            elif stock.vol_ratio >= 1.5:
                score += 5
            elif stock.vol_ratio < 0.5:
                score -= 10

        # 板块加分
        if sector:
            if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
                score += 20
            elif sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
                score += 10
            elif sector.sector_mainline_tag == SectorMainlineTag.FOLLOW:
                score += 5

        return max(0, min(100, score))

    def _determine_strength_tag(self, change_pct: float, strength_score: float) -> StockStrengthTag:
        """确定强弱标签"""
        if change_pct >= self.STRONG_CHANGE_THRESHOLD or strength_score >= 70:
            return StockStrengthTag.STRONG
        elif change_pct >= 0 or strength_score >= 40:
            return StockStrengthTag.MEDIUM
        else:
            return StockStrengthTag.WEAK

    def _determine_continuity_tag(self, strength_score: float, stock: StockInput) -> StockContinuityTag:
        """确定连续性标签"""
        # 简化判断：高位放量可能末端
        if stock.change_pct >= 9 and stock.turnover_rate >= 25:
            return StockContinuityTag.CAUTION

        if strength_score >= 70:
            return StockContinuityTag.SUSTAINABLE
        elif strength_score >= 40:
            return StockContinuityTag.OBSERVABLE
        else:
            return StockContinuityTag.CAUTION

    def _determine_core_tag(
        self,
        stock: StockInput,
        sector,
        strength_score: float
    ) -> StockCoreTag:
        """确定核心属性"""
        # 有板块支撑且强度高 -> 核心
        if sector and strength_score >= 60:
            if sector.sector_mainline_tag in [SectorMainlineTag.MAINLINE, SectorMainlineTag.SUB_MAINLINE]:
                return StockCoreTag.CORE

        # 有板块支撑但强度一般 -> 跟随
        if sector:
            return StockCoreTag.FOLLOW

        # 无板块支撑 -> 杂毛
        return StockCoreTag.TRASH

    def _determine_tradeability_tag(
        self,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        core_tag: StockCoreTag,
        market_env
    ) -> StockTradeabilityTag:
        """确定交易性标签"""
        from app.models.schemas import MarketEnvTag

        # 弱市不交易
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 末端谨慎
        if continuity_tag == StockContinuityTag.CAUTION:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 杂毛不建议
        if core_tag == StockCoreTag.TRASH:
            return StockTradeabilityTag.NOT_RECOMMENDED

        # 核心且持续 -> 可交易
        if core_tag == StockCoreTag.CORE and strength_tag == StockStrengthTag.STRONG:
            return StockTradeabilityTag.TRADABLE

        # 中等强度 -> 谨慎
        if strength_tag == StockStrengthTag.MEDIUM:
            return StockTradeabilityTag.CAUTION

        return StockTradeabilityTag.CAUTION

    def _generate_falsification(self, stock: StockInput, sector, core_tag: StockCoreTag) -> str:
        """生成证伪条件"""
        conds = []

        # 跌破关键位
        if stock.change_pct > 5:
            conds.append(f"收盘跌破今日涨幅的50%")

        # 板块走弱
        if sector:
            if sector.sector_tradeability_tag == SectorTradeabilityTag.NOT_RECOMMENDED:
                conds.append("板块转为不建议交易")

        # 杂毛
        if core_tag == StockCoreTag.TRASH:
            conds.append("无板块支撑，走势孤立")

        # 放量滞涨
        if stock.vol_ratio and stock.vol_ratio > 3 and stock.change_pct < 3:
            conds.append("放量滞涨")

        return "；".join(conds) if conds else "跌破5日均线"

    def _generate_stock_comment(
        self,
        strength_tag: StockStrengthTag,
        continuity_tag: StockContinuityTag,
        tradeability_tag: StockTradeabilityTag,
        sector
    ) -> str:
        """生成个股简评"""
        comments = []

        # 强度
        if strength_tag == StockStrengthTag.STRONG:
            comments.append("强势股")
        elif strength_tag == StockStrengthTag.MEDIUM:
            comments.append("中性")
        else:
            comments.append("弱势")

        # 板块
        if sector:
            if sector.sector_mainline_tag == SectorMainlineTag.MAINLINE:
                comments.append("主线")
            elif sector.sector_mainline_tag == SectorMainlineTag.SUB_MAINLINE:
                comments.append("次主线")

        # 连续性
        if continuity_tag == StockContinuityTag.CAUTION:
            comments.append("注意末端")

        # 交易建议
        if tradeability_tag == StockTradeabilityTag.TRADABLE:
            comments.append("可交易")
        elif tradeability_tag == StockTradeabilityTag.CAUTION:
            comments.append("谨慎")
        else:
            comments.append("不建议")

        return "，".join(comments)


# 全局服务实例
stock_filter_service = StockFilterService()
