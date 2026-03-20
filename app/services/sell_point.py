"""
卖点分析服务
"""
from typing import List, Dict
from loguru import logger

from app.models.schemas import (
    AccountPosition,
    SellPointOutput,
    SellPointResponse,
    SellSignalTag,
    SellPointType,
    SellPriority,
    MarketEnvTag,
    SectorMainlineTag,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service


class SellPointService:
    """卖点分析服务"""

    # 止损阈值
    STOP_LOSS_PCT = -5.0  # 亏损超过5%止损
    STOP_LOSS_PCT_STRICT = -3.0  # 严格止损

    # 止盈阈值
    STOP_PROFIT_PCT = 15.0  # 盈利超过15%考虑止盈
    STOP_PROFIT_PCT_TIGHT = 10.0  # 10%可部分止盈

    # 减仓阈值
    REDUCE_PCT = 8.0  # 盈利超过8%可减仓

    def __init__(self):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service

    def analyze(
        self,
        trade_date: str,
        holdings: List[AccountPosition]
    ) -> SellPointResponse:
        """
        卖点分析

        Args:
            trade_date: 交易日
            holdings: 持仓列表

        Returns:
            卖点分析结果
        """
        # 获取市场环境和板块
        market_env = self.market_env_service.get_current_env(trade_date)
        sector_scan = self.sector_scan_service.scan(trade_date)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 分析每个持仓
        hold = []     # 持有观察
        reduce_pos = []  # 建议减仓
        sell = []     # 建议卖出

        for position in holdings:
            sell_point = self._analyze_position(position, market_env, sector_map)

            if sell_point.sell_signal_tag == SellSignalTag.HOLD:
                hold.append(sell_point)
            elif sell_point.sell_signal_tag == SellSignalTag.REDUCE:
                reduce_pos.append(sell_point)
            else:
                sell.append(sell_point)

        return SellPointResponse(
            trade_date=trade_date,
            hold_positions=hold,
            reduce_positions=reduce_pos,
            sell_positions=sell,
            total_count=len(holdings)
        )

    def _build_sector_map(self, sector_scan) -> Dict:
        """构建板块映射"""
        sector_map = {}

        for s in sector_scan.mainline_sectors:
            sector_map[s.sector_name] = s
        for s in sector_scan.sub_mainline_sectors:
            sector_map[s.sector_name] = s

        return sector_map

    def _analyze_position(
        self,
        position: AccountPosition,
        market_env,
        sector_map: Dict
    ) -> SellPointOutput:
        """
        分析单个持仓的卖点

        Args:
            position: 持仓
            market_env: 市场环境
            sector_map: 板块映射

        Returns:
            卖点分析结果
        """
        pnl_pct = position.pnl_pct
        can_sell = position.can_sell_today

        # 判断卖点类型和信号
        sell_type, signal_tag, priority, reason, trigger, comment = self._determine_sell(
            pnl_pct, can_sell, market_env
        )

        return SellPointOutput(
            ts_code=position.ts_code,
            stock_name=position.stock_name,
            sell_signal_tag=signal_tag,
            sell_point_type=sell_type,
            sell_trigger_cond=trigger,
            sell_reason=reason,
            sell_priority=priority,
            sell_comment=comment
        )

    def _determine_sell(
        self,
        pnl_pct: float,
        can_sell: bool,
        market_env
    ) -> tuple:
        """确定卖点"""
        # 1. 止损判断（优先）
        if pnl_pct <= self.STOP_LOSS_PCT:
            # 严重亏损 -> 止损
            return (
                SellPointType.STOP_LOSS,
                SellSignalTag.SELL,
                SellPriority.HIGH,
                f"亏损{pnl_pct:.1f}%，触发止损",
                f"收盘跌破成本价{abs(pnl_pct) + 2:.1f}%无法收回",
                f"止损出局，亏损{pnl_pct:.1f}%"
            )

        # 2. 市场环境恶化 -> 卖出
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            if pnl_pct < 0:
                return (
                    SellPointType.INVALID_EXIT,
                    SellSignalTag.SELL,
                    SellPriority.HIGH,
                    "市场转弱，亏损持仓应优先处理",
                    "次日开盘卖出",
                    "市场防守，亏损票优先离场"
                )

        # 3. 止盈判断
        if pnl_pct >= self.STOP_PROFIT_PCT:
            # 盈利较高，考虑止盈
            if market_env.market_env_tag == MarketEnvTag.DEFENSE:
                return (
                    SellPointType.STOP_PROFIT,
                    SellSignalTag.SELL,
                    SellPriority.HIGH,
                    f"盈利{pnl_pct:.1f}%，市场转弱应止盈",
                    "收盘前卖出",
                    f"保护盈利，市场转弱"
                )
            elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
                return (
                    SellPointType.STOP_PROFIT,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"盈利{pnl_pct:.1f}%，可部分止盈",
                    "卖出一半仓位",
                    "中性市场，部分止盈"
                )

        # 4. 减仓判断
        if pnl_pct >= self.REDUCE_PCT:
            if not can_sell:
                # T+1 不能卖，观察
                return (
                    SellPointType.INVALID_EXIT,
                    SellSignalTag.OBSERVE,
                    SellPriority.LOW,
                    f"盈利{pnl_pct:.1f}%，但T+1锁定",
                    "次日观察是否企稳",
                    "T+1，次日处理"
                )
            return (
                SellPointType.REDUCE_POSITION,
                SellSignalTag.REDUCE,
                SellPriority.MEDIUM,
                f"盈利{pnl_pct:.1f}%，可减仓锁定部分利润",
                "卖出一半仓位",
                "部分止盈"
            )

        # 5. T+1 约束处理
        if not can_sell:
            return (
                SellPointType.INVALID_EXIT,
                SellSignalTag.OBSERVE,
                SellPriority.LOW,
                "T+1锁定，今日无法卖出",
                "次日根据情况处理",
                "持有观察"
            )

        # 6. 持有观察
        if pnl_pct > 0:
            return (
                SellPointType.INVALID_EXIT,
                SellSignalTag.HOLD,
                SellPriority.LOW,
                "盈利中，继续持有",
                "持有观察",
                "趋势未坏，持有"
            )
        else:
            # 小幅亏损
            if market_env.market_env_tag == MarketEnvTag.ATTACK:
                return (
                    SellPointType.INVALID_EXIT,
                    SellSignalTag.HOLD,
                    SellPriority.LOW,
                    "小幅亏损，市场强势可继续持有",
                    "持有等待反弹",
                    "市场进攻持有"
                )
            else:
                return (
                    SellPointType.STOP_LOSS,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"亏损{pnl_pct:.1f}%，市场转弱应减仓",
                    "卖出三分之一",
                    "控制亏损"
                )


# 全局服务实例
sell_point_service = SellPointService()
