"""
卖点分析服务
"""
from typing import List, Dict

from app.models.schemas import (
    AccountPosition,
    SellPointOutput,
    SellPointResponse,
    SellSignalTag,
    SellPointType,
    SellPriority,
    MarketEnvTag,
    SectorMainlineTag,
    SectorTradeabilityTag,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.market_data_gateway import market_data_gateway
from app.services.strategy_config import (
    DEFAULT_SELL_POINT_STRATEGY,
    SellPointStrategyConfig,
)


class SellPointService:
    """卖点分析服务"""

    def __init__(self, strategy: SellPointStrategyConfig | None = None):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service
        self.strategy = strategy or DEFAULT_SELL_POINT_STRATEGY
        self.STOP_LOSS_PCT = self.strategy.stop_loss_pct
        self.STOP_LOSS_PCT_STRICT = self.strategy.stop_loss_pct_strict
        self.STOP_PROFIT_PCT = self.strategy.stop_profit_pct
        self.STOP_PROFIT_PCT_TIGHT = self.strategy.stop_profit_pct_tight
        self.REDUCE_PCT = self.strategy.reduce_pct

    def analyze(
        self,
        trade_date: str,
        holdings: List[AccountPosition],
        market_env=None,
        sector_scan=None,
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
        market_env = market_env or self.market_env_service.get_current_env(trade_date)
        sector_scan = sector_scan or self.sector_scan_service.scan(trade_date, limit_output=False)

        # 构建板块映射
        sector_map = self._build_sector_map(sector_scan)

        # 分析每个持仓
        hold = []     # 持有观察
        reduce_pos = []  # 建议减仓
        sell = []     # 建议卖出

        for position in holdings:
            sector_name = self._resolve_position_sector(position.ts_code, trade_date)
            sell_point = self._analyze_position(position, market_env, sector_map, sector_name)
            # 叠加板块共振判断：若个股所属板块不在主线/次主线，提升离场优先级
            self._apply_sector_resonance_adjustment(sell_point, position, sector_name, sector_map, market_env)
            self._normalize_execution_constraints(sell_point, position)

            if sell_point.sell_signal_tag in [SellSignalTag.HOLD, SellSignalTag.OBSERVE]:
                hold.append(sell_point)
            elif sell_point.sell_signal_tag == SellSignalTag.REDUCE:
                reduce_pos.append(sell_point)
            else:
                sell.append(sell_point)

        sell = self._sort_sell_points(sell)
        reduce_pos = self._sort_sell_points(reduce_pos)
        hold = self._sort_sell_points(hold)

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

        for group in [
            sector_scan.mainline_sectors,
            sector_scan.sub_mainline_sectors,
            sector_scan.follow_sectors,
            sector_scan.trash_sectors,
        ]:
            for s in group:
                sector_map[s.sector_name] = s

        return sector_map

    def _analyze_position(
        self,
        position: AccountPosition,
        market_env,
        sector_map: Dict,
        sector_name: str = "",
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
        sell_type, signal_tag, priority, reason, trigger, comment, reduce_reason_code = self._determine_sell(
            position, pnl_pct, can_sell, market_env, sector_map, sector_name
        )

        return SellPointOutput(
            ts_code=position.ts_code,
            stock_name=position.stock_name,
            market_price=position.market_price,
            quote_time=position.quote_time,
            data_source=position.data_source,
            cost_price=position.cost_price,
            pnl_pct=position.pnl_pct,
            holding_qty=position.holding_qty,
            holding_days=position.holding_days,
            can_sell_today=position.can_sell_today,
            sell_signal_tag=signal_tag,
            sell_point_type=sell_type,
            sell_trigger_cond=trigger,
            sell_reason=reason,
            reduce_reason_code=reduce_reason_code,
            sell_priority=priority,
            sell_comment=comment
        )

    def _resolve_position_sector(self, ts_code: str, trade_date: str) -> str:
        """获取持仓所属板块名称。"""
        try:
            detail = market_data_gateway.get_stock_detail(ts_code, trade_date)
            return detail.get("sector_name", "")
        except Exception:
            return ""

    def _sort_sell_points(self, points: List[SellPointOutput]) -> List[SellPointOutput]:
        """按优先级和盈亏幅度排序，便于页面直接展示处理顺序。"""
        priority_order = {
            SellPriority.HIGH: 0,
            SellPriority.MEDIUM: 1,
            SellPriority.LOW: 2,
        }

        def sort_key(point: SellPointOutput):
            pnl = point.pnl_pct if point.pnl_pct is not None else 0.0
            severity = abs(pnl)
            return (
                priority_order.get(point.sell_priority, 99),
                -severity,
                point.ts_code,
            )

        return sorted(points, key=sort_key)

    def _can_partially_reduce(self, holding_qty: int | None) -> bool:
        """A 股按 100 股一手交易，至少 200 股才存在明确的部分减仓空间。"""
        return bool(holding_qty and holding_qty >= 200)

    def _normalize_execution_constraints(
        self,
        sell_point: SellPointOutput,
        position: AccountPosition,
    ) -> None:
        """将不可执行的减仓建议修正为可执行动作。"""
        if sell_point.sell_signal_tag != SellSignalTag.REDUCE:
            return

        if self._can_partially_reduce(position.holding_qty):
            return

        sell_point.sell_signal_tag = SellSignalTag.SELL
        if sell_point.sell_point_type == SellPointType.REDUCE_POSITION:
            sell_point.sell_point_type = (
                SellPointType.STOP_PROFIT if (position.pnl_pct or 0) > 0 else SellPointType.STOP_LOSS
            )
        if sell_point.sell_priority == SellPriority.MEDIUM:
            sell_point.sell_priority = SellPriority.HIGH
        sell_point.sell_reason = f"{sell_point.sell_reason}；当前仅有{position.holding_qty or 0}股，无法按一手部分减仓"
        sell_point.sell_trigger_cond = "满足原触发条件时一次卖出"
        sell_point.sell_comment = "A股最小交易单位为100股，这笔仓位没有可执行的部分减仓空间"
        sell_point.reduce_reason_code = None

    def _apply_sector_resonance_adjustment(
        self,
        sell_point: SellPointOutput,
        position: AccountPosition,
        sector_name: str,
        sector_map: Dict,
        market_env
    ) -> None:
        """根据板块共振与原始持仓理由修正卖点建议。"""
        if not position.can_sell_today:
            return

        reason_text = position.holding_reason or ""
        reason_invalid = any(tag in reason_text for tag in ["失效", "证伪", "逻辑坏了", "不成立"])
        sector = sector_map.get(sector_name) if sector_name else None
        sector_known = sector is not None
        sector_supportive = bool(
            sector
            and sector.sector_mainline_tag in {
                SectorMainlineTag.MAINLINE,
                SectorMainlineTag.SUB_MAINLINE,
                SectorMainlineTag.FOLLOW,
            }
            and sector.sector_tradeability_tag != SectorTradeabilityTag.NOT_RECOMMENDED
        )
        sector_weak = bool(
            sector
            and (
                sector.sector_mainline_tag == SectorMainlineTag.TRASH
                or sector.sector_tradeability_tag == SectorTradeabilityTag.NOT_RECOMMENDED
            )
        )
        dynamic_supportive = bool(
            sector
            and (
                int(getattr(sector, "front_runner_count", 0) or 0) >= 2
                or int(getattr(sector, "follow_runner_count", 0) or 0) >= 4
                or float(getattr(sector, "afternoon_rebound_strength", 0) or 0) >= 0.55
            )
            and not bool(getattr(sector, "leader_broken", False))
        )
        dynamic_weak = bool(
            sector
            and bool(getattr(sector, "leader_broken", False))
            and int(getattr(sector, "front_runner_count", 0) or 0) <= 0
            and float(getattr(sector, "afternoon_rebound_strength", 0) or 0) < 0.35
        )
        sector_supportive = sector_supportive or dynamic_supportive
        sector_weak = sector_weak or dynamic_weak

        # 原买入逻辑失效时优先退出，这是最强约束。
        if reason_invalid:
            sell_point.sell_signal_tag = SellSignalTag.SELL
            sell_point.sell_point_type = SellPointType.INVALID_EXIT
            sell_point.sell_priority = SellPriority.HIGH
            sell_point.sell_reason = "原买入理由已经失效，优先退出"
            sell_point.sell_trigger_cond = "下一次反弹不能转强时卖出"
            sell_point.sell_comment = "这类票不再适合继续拿"
            sell_point.reduce_reason_code = None
            return

        # 已经明确触发止损/止盈卖出的，不再被板块规则覆盖。
        if sell_point.sell_signal_tag == SellSignalTag.SELL:
            return

        # 防守环境下，板块转弱以“先减仓”为默认动作，不再一刀切全卖。
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            if sector_weak:
                if position.pnl_pct <= self.STOP_LOSS_PCT_STRICT:
                    sell_point.sell_signal_tag = SellSignalTag.SELL
                    sell_point.sell_point_type = SellPointType.STOP_LOSS
                    sell_point.sell_priority = SellPriority.HIGH
                    sell_point.sell_reason = "市场偏弱，板块也没有支撑，亏损已接近止损线"
                    sell_point.sell_trigger_cond = "反弹无力时先退出"
                    sell_point.sell_comment = "弱市里不要硬扛弱板块"
                    sell_point.reduce_reason_code = None
                else:
                    sell_point.sell_signal_tag = SellSignalTag.REDUCE
                    sell_point.sell_point_type = SellPointType.REDUCE_POSITION
                    sell_point.sell_priority = SellPriority.MEDIUM
                    sell_point.reduce_reason_code = "env_weak"
                    if position.pnl_pct > 0:
                        sell_point.sell_reason = "市场偏弱，这只票所在板块也不强，先落一部分利润"
                        sell_point.sell_trigger_cond = "冲高不能放量续强时减仓"
                        sell_point.sell_comment = "先把仓位降下来，等更清晰的信号"
                    else:
                        sell_point.sell_reason = "市场偏弱，这只票所在板块也不强，先降仓控制回撤"
                        sell_point.sell_trigger_cond = "反弹无力或跌破日内支撑时减仓"
                        sell_point.sell_comment = "先降风险，不必一口气清仓"
                return

            if not sector_known and sell_point.sell_signal_tag == SellSignalTag.HOLD:
                sell_point.sell_signal_tag = SellSignalTag.REDUCE if position.pnl_pct > 0 else SellSignalTag.HOLD
                sell_point.sell_point_type = SellPointType.REDUCE_POSITION if position.pnl_pct > 0 else SellPointType.INVALID_EXIT
                sell_point.sell_priority = SellPriority.MEDIUM if position.pnl_pct > 0 else SellPriority.LOW
                sell_point.reduce_reason_code = "rebound_exit" if position.pnl_pct > 0 else None
                sell_point.sell_reason = (
                    "当前没找到明确板块共振，先收缩仓位等待确认"
                    if position.pnl_pct > 0
                    else "当前没找到明确板块共振，先观察，不急着加仓"
                )
                sell_point.sell_trigger_cond = (
                    "冲高无量时先减一部分"
                    if position.pnl_pct > 0
                    else "若继续走弱再处理"
                )
                sell_point.sell_comment = "板块线索不清时，动作先保守一些"
                return

        # 中性环境下，板块转弱则先降仓；仅缺少映射则保持观察。
        if market_env.market_env_tag == MarketEnvTag.NEUTRAL and sector_weak:
            if sell_point.sell_signal_tag == SellSignalTag.HOLD:
                sell_point.sell_signal_tag = SellSignalTag.REDUCE
                sell_point.sell_point_type = SellPointType.REDUCE_POSITION
                sell_point.sell_priority = SellPriority.MEDIUM
                sell_point.reduce_reason_code = "env_weak"
                sell_point.sell_reason = "板块走弱了，先降一点仓位更稳妥"
                sell_point.sell_trigger_cond = "日内反弹无量时减仓"
                sell_point.sell_comment = "先降风险敞口，等板块重新转强"

    def _decision(
        self,
        sell_type: SellPointType,
        signal_tag: SellSignalTag,
        priority: SellPriority,
        reason: str,
        trigger: str,
        comment: str,
        reduce_reason_code: str | None = None,
    ) -> tuple:
        return (
            sell_type,
            signal_tag,
            priority,
            reason,
            trigger,
            comment,
            reduce_reason_code,
        )

    def _determine_sell(
        self,
        position: AccountPosition,
        pnl_pct: float,
        can_sell: bool,
        market_env,
        sector_map: Dict,
        sector_name: str = "",
    ) -> tuple:
        """确定卖点"""
        reason_text = position.holding_reason or ""
        reason_invalid = any(tag in reason_text for tag in ["失效", "证伪", "逻辑坏了", "不成立"])
        reason_strong = any(tag in reason_text for tag in ["主升", "主线", "龙头", "核心", "趋势", "突破"])
        reason_tactical = any(tag in reason_text for tag in ["套利", "反弹", "轮动", "低吸", "博弈"])
        sector = sector_map.get(sector_name) if sector_name else None
        sector_supportive = bool(
            sector
            and sector.sector_mainline_tag in {
                SectorMainlineTag.MAINLINE,
                SectorMainlineTag.SUB_MAINLINE,
                SectorMainlineTag.FOLLOW,
            }
            and sector.sector_tradeability_tag != SectorTradeabilityTag.NOT_RECOMMENDED
        )
        sector_weak = bool(
            sector
            and (
                sector.sector_mainline_tag == SectorMainlineTag.TRASH
                or sector.sector_tradeability_tag == SectorTradeabilityTag.NOT_RECOMMENDED
            )
        )
        dynamic_supportive = bool(
            sector
            and (
                int(getattr(sector, "front_runner_count", 0) or 0) >= 2
                or int(getattr(sector, "follow_runner_count", 0) or 0) >= 4
                or float(getattr(sector, "afternoon_rebound_strength", 0) or 0) >= 0.55
            )
            and not bool(getattr(sector, "leader_broken", False))
        )
        dynamic_weak = bool(
            sector
            and bool(getattr(sector, "leader_broken", False))
            and int(getattr(sector, "front_runner_count", 0) or 0) <= 0
            and float(getattr(sector, "afternoon_rebound_strength", 0) or 0) < 0.35
        )
        sector_supportive = sector_supportive or dynamic_supportive
        sector_weak = sector_weak or dynamic_weak
        structure_strong = (
            market_env.market_env_tag == MarketEnvTag.ATTACK
            and (sector_supportive or reason_strong)
            and not sector_weak
        )
        structure_weak = (
            sector_weak
            or (market_env.market_env_tag == MarketEnvTag.DEFENSE and not sector_supportive)
        )
        if reason_tactical and market_env.market_env_tag == MarketEnvTag.DEFENSE:
            structure_weak = True

        # 0. 原始逻辑失效优先退出
        if reason_invalid:
            return self._decision(
                SellPointType.INVALID_EXIT,
                SellSignalTag.SELL,
                SellPriority.HIGH,
                "原买入理由已经失效，优先退出",
                "下一次反弹不能转强时卖出",
                "买入逻辑被证伪，不再适合继续拿",
            )

        # 1. 止损判断（优先）
        if pnl_pct <= self.STOP_LOSS_PCT:
            # 严重亏损 -> 止损
            return self._decision(
                SellPointType.STOP_LOSS,
                SellSignalTag.SELL,
                SellPriority.HIGH,
                f"亏损{pnl_pct:.1f}%，触发止损",
                f"收盘跌破成本价{abs(pnl_pct) + 2:.1f}%无法收回",
                f"止损出局，亏损{pnl_pct:.1f}%"
            )

        # 2. T+1 约束处理
        if not can_sell:
            if pnl_pct >= self.STOP_PROFIT_PCT and structure_weak:
                return self._decision(
                    SellPointType.REDUCE_POSITION,
                    SellSignalTag.OBSERVE,
                    SellPriority.MEDIUM,
                    f"盈利{pnl_pct:.1f}%，但T+1锁定，明天优先处理",
                    "次日若冲高不能续强则先减仓",
                    "今天动不了，先把减仓计划定好",
                    "protect_profit" if pnl_pct > 0 else "structure_loose",
                )
            return self._decision(
                SellPointType.INVALID_EXIT,
                SellSignalTag.OBSERVE,
                SellPriority.LOW,
                "T+1锁定，今日无法卖出",
                "次日根据结构强弱处理",
                "今日先观察，明天再执行",
            )

        # 3. 市场环境恶化且结构偏弱 -> 先减仓
        if market_env.market_env_tag == MarketEnvTag.DEFENSE and pnl_pct < 0:
            if pnl_pct <= self.STOP_LOSS_PCT_STRICT or structure_weak:
                return self._decision(
                    SellPointType.REDUCE_POSITION,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"市场偏弱，当前亏损{abs(pnl_pct):.1f}%，先减仓控制风险",
                    "反弹无力时先减一部分",
                    "弱市先降仓，不必急着一次卖完",
                    "env_weak",
                )

        # 4. 结构走弱后的止盈/减仓
        if pnl_pct >= self.STOP_PROFIT_PCT:
            if structure_weak and market_env.market_env_tag == MarketEnvTag.DEFENSE and not sector_supportive:
                return self._decision(
                    SellPointType.STOP_PROFIT,
                    SellSignalTag.SELL,
                    SellPriority.HIGH,
                    f"盈利{pnl_pct:.1f}%，市场转弱应止盈",
                    "收盘前卖出",
                    "保护盈利，市场转弱"
                )
            if structure_weak:
                return self._decision(
                    SellPointType.STOP_PROFIT,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"盈利{pnl_pct:.1f}%，但结构性价比在下降，先落一部分利润",
                    "冲高不能续强时先减仓",
                    "先把利润装进口袋，保留继续走强的仓位",
                    "env_weak" if market_env.market_env_tag == MarketEnvTag.DEFENSE else "protect_profit",
                )

        # 5. 减仓判断：不再只按盈利阈值，需叠加结构走弱
        if pnl_pct >= self.REDUCE_PCT:
            if structure_weak:
                return self._decision(
                    SellPointType.REDUCE_POSITION,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"盈利{pnl_pct:.1f}%，结构边际走弱，适合减仓锁定部分利润",
                    "反弹到压力位不能放量续强时减仓",
                    "先降一点仓位，避免利润回撤",
                    "structure_loose",
                )

        # 6. 持有观察或保护利润
        if pnl_pct > 0:
            if structure_strong:
                return self._decision(
                    SellPointType.INVALID_EXIT,
                    SellSignalTag.HOLD,
                    SellPriority.LOW,
                    f"盈利{pnl_pct:.1f}%，趋势与板块仍有支撑，继续持有",
                    "跌破关键承接前继续持有",
                    "结构没坏，不急着因为浮盈就减仓"
                )
            if (
                pnl_pct >= self.STOP_PROFIT_PCT_TIGHT
                and market_env.market_env_tag != MarketEnvTag.ATTACK
                and not sector_supportive
                and not reason_strong
            ):
                return self._decision(
                    SellPointType.REDUCE_POSITION,
                    SellSignalTag.REDUCE,
                    SellPriority.MEDIUM,
                    f"盈利{pnl_pct:.1f}%，先上移保护位并减一部分更稳妥",
                    "冲高回落或跌破日内承接时减仓",
                    "环境一般时，先锁一部分利润",
                    "protect_profit",
                )
            return self._decision(
                SellPointType.INVALID_EXIT,
                SellSignalTag.HOLD,
                SellPriority.LOW,
                "盈利中，继续持有观察",
                "不破支撑先持有",
                "先看趋势是否延续"
            )

        # 7. 小幅亏损处理
        if market_env.market_env_tag == MarketEnvTag.ATTACK and not structure_weak:
            return self._decision(
                SellPointType.INVALID_EXIT,
                SellSignalTag.HOLD,
                SellPriority.LOW,
                "小幅亏损，但市场和结构仍可接受，继续观察",
                "守住关键支撑可继续持有",
                "这是正常波动，不急着机械处理"
            )
        if sector_supportive and pnl_pct > self.STOP_LOSS_PCT_STRICT:
            return self._decision(
                SellPointType.INVALID_EXIT,
                SellSignalTag.OBSERVE,
                SellPriority.LOW,
                f"亏损{pnl_pct:.1f}%，但板块仍有支撑，先观察承接",
                "跌破关键支撑再减仓",
                "先区分正常分歧还是走弱确认"
            )
        return self._decision(
            SellPointType.REDUCE_POSITION,
            SellSignalTag.REDUCE,
            SellPriority.MEDIUM,
            f"亏损{pnl_pct:.1f}%，结构没有明显优势，先减仓控制回撤",
            "反弹无力或跌破支撑时减仓",
            "先把风险敞口降下来",
            "structure_loose",
        )


# 全局服务实例
sell_point_service = SellPointService()
