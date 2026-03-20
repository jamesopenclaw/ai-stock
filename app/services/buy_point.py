"""
买点分析服务
"""
from typing import List, Dict, Optional
from loguru import logger

from app.models.schemas import (
    StockInput,
    StockOutput,
    BuyPointOutput,
    BuyPointRequest,
    BuyPointResponse,
    BuyPointType,
    BuySignalTag,
    MarketEnvTag,
    RiskLevel,
    SectorMainlineTag,
    SectorTradeabilityTag,
    StockPoolTag,
    StockStrengthTag,
)
from app.services.market_env import market_env_service
from app.services.sector_scan import sector_scan_service
from app.services.stock_filter import stock_filter_service


class BuyPointService:
    """买点分析服务"""

    def __init__(self):
        self.market_env_service = market_env_service
        self.sector_scan_service = sector_scan_service
        self.stock_filter_service = stock_filter_service

    def analyze(self, trade_date: str, stocks: List[StockInput]) -> BuyPointResponse:
        """
        买点分析

        Args:
            trade_date: 交易日
            stocks: 候选个股列表

        Returns:
            买点分析结果
        """
        # 获取市场环境
        market_env = self.market_env_service.get_current_env(trade_date)

        # 筛选评分
        scored_stocks = self.stock_filter_service.filter(trade_date, stocks)

        # 分析每个股票的买点
        available = []   # 可买
        observe = []    # 观察
        not_buy = []    # 不买

        for stock in scored_stocks:
            buy_point = self._analyze_stock_buy_point(stock, market_env)

            if buy_point.buy_signal_tag == BuySignalTag.CAN_BUY:
                available.append(buy_point)
            elif buy_point.buy_signal_tag == BuySignalTag.OBSERVE:
                observe.append(buy_point)
            else:
                not_buy.append(buy_point)

        return BuyPointResponse(
            trade_date=trade_date,
            market_env_tag=market_env.market_env_tag,
            available_buy_points=available[:10],   # 最多10只
            observe_buy_points=observe[:10],       # 最多10只
            not_buy_points=not_buy[:10],           # 最多10只
            total_count=len(scored_stocks)
        )

    def _analyze_stock_buy_point(self, stock: StockOutput, market_env) -> BuyPointOutput:
        """
        分析单个股票的买点

        Args:
            stock: 评分后的个股
            market_env: 市场环境

        Returns:
            买点分析结果
        """
        # 判断买点类型
        buy_type = self._determine_buy_type(stock, market_env)

        # 判断是否可买
        signal_tag = self._determine_buy_signal(stock, market_env, buy_type)

        # 生成触发/确认/失效条件
        trigger_cond = self._generate_trigger_cond(stock, buy_type)
        confirm_cond = self._generate_confirm_cond(stock, buy_type)
        invalid_cond = self._generate_invalid_cond(stock, buy_type)

        # 评估风险等级
        risk_level = self._assess_risk(stock, market_env, buy_type)

        # 评估账户适合度
        account_fit = self._assess_account_fit(stock, market_env)

        # 生成买点简评
        comment = self._generate_buy_comment(stock, buy_type, signal_tag)

        return BuyPointOutput(
            ts_code=stock.ts_code,
            stock_name=stock.stock_name,
            buy_signal_tag=signal_tag,
            buy_point_type=buy_type,
            buy_trigger_cond=trigger_cond,
            buy_confirm_cond=confirm_cond,
            buy_invalid_cond=invalid_cond,
            buy_risk_level=risk_level,
            buy_account_fit=account_fit,
            buy_comment=comment
        )

    def _determine_buy_type(self, stock: StockOutput, market_env) -> BuyPointType:
        """确定买点类型"""
        # 强势股 -> 突破
        if stock.stock_strength_tag == StockStrengthTag.STRONG:
            if stock.change_pct >= 5:  # 涨幅较大，突破概率高
                return BuyPointType.BREAKTHROUGH
            else:
                return BuyPointType.RETRACE_SUPPORT

        # 中等强度 -> 回踩承接
        if stock.stock_strength_tag == StockStrengthTag.MEDIUM:
            return BuyPointType.RETRACE_SUPPORT

        # 弱势 -> 修复转强（需要更多条件）
        return BuyPointType.REPAIR_STRENGTHEN

    def _determine_buy_signal(
        self,
        stock: StockOutput,
        market_env,
        buy_type: BuyPointType
    ) -> BuySignalTag:
        """确定买点信号"""
        # 市场环境过滤
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            # 防守环境，大部分股票不建议买
            if stock.stock_core_tag.value == "核心" and stock.stock_strength_tag == StockStrengthTag.STRONG:
                return BuySignalTag.OBSERVE
            return BuySignalTag.NOT_BUY

        # 交易性标签过滤
        if stock.stock_tradeability_tag.value == "不建议":
            return BuySignalTag.NOT_BUY

        if stock.stock_tradeability_tag.value == "谨慎":
            return BuySignalTag.OBSERVE

        # 核心强势股 -> 可买
        if stock.stock_core_tag.value == "核心" and stock.stock_strength_tag == StockStrengthTag.STRONG:
            return BuySignalTag.CAN_BUY

        # 其他 -> 观察
        return BuySignalTag.OBSERVE

    def _generate_trigger_cond(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        """生成触发条件"""
        if buy_type == BuyPointType.BREAKTHROUGH:
            return f"价格突破 {stock.change_pct + 1:.1f}% 关键位时触发"
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            return f"回踩至今日开盘价附近企稳时触发"
        else:
            return f"出现分时反转信号、量能配合时触发"

    def _generate_confirm_cond(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        """生成确认条件"""
        conds = []

        # 都需要量能配合
        conds.append("成交量放大至前一交易日1.2倍以上")

        if buy_type == BuyPointType.BREAKTHROUGH:
            conds.append("突破后不回落到关键位下方")
            conds.append("有板块或指数共振")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            conds.append("在支撑位收出止跌K线")
            conds.append("分时走势企稳")
        else:
            conds.append("出现明显反转信号")
            conds.append("板块整体回暖")

        return "；".join(conds)

    def _generate_invalid_cond(self, stock: StockOutput, buy_type: BuyPointType) -> str:
        """生成失效条件"""
        conds = []

        # 通用失效条件
        conds.append(f"收盘跌破今日最低价，视为突破失败")
        conds.append(f"次日开盘跌破今日收盘价3%以上")

        if buy_type == BuyPointType.BREAKTHROUGH:
            conds.append("炸板（涨停被打开）")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            conds.append("跌破支撑位2%以上无法收回")

        # 个股特定失效
        if stock.stock_falsification_cond:
            conds.append(stock.stock_falsification_cond)

        return "；".join(conds[:3])  # 最多3条

    def _assess_risk(self, stock: StockOutput, market_env, buy_type: BuyPointType) -> RiskLevel:
        """评估风险等级"""
        # 市场风险
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return RiskLevel.HIGH
        elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            return RiskLevel.MEDIUM

        # 买点类型风险
        if buy_type == BuyPointType.BREAKTHROUGH:
            # 突破本身风险较高
            if market_env.market_env_tag == MarketEnvTag.ATTACK:
                return RiskLevel.MEDIUM
            return RiskLevel.HIGH
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.MEDIUM

    def _assess_account_fit(self, stock: StockOutput, market_env) -> str:
        """评估账户适合度"""
        # 防守环境
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            return "不适合"

        # 核心强势股
        if stock.stock_core_tag == StockCoreTag.CORE and stock.stock_strength_tag == StockStrengthTag.STRONG:
            # 还要看仓位
            if market_env.market_env_tag == MarketEnvTag.ATTACK:
                return "适合"
            return "一般"

        # 普通股票
        return "一般"

    def _generate_buy_comment(
        self,
        stock: StockOutput,
        buy_type: BuyPointType,
        signal_tag: BuySignalTag
    ) -> str:
        """生成买点简评"""
        comments = []

        # 买点类型
        if buy_type == BuyPointType.BREAKTHROUGH:
            comments.append("突破型买点")
        elif buy_type == BuyPointType.RETRACE_SUPPORT:
            comments.append("回踩承接型")
        elif buy_type == BuyPointType.REPAIR_STRENGTHEN:
            comments.append("修复转强型")
        else:
            comments.append("低吸型")

        # 信号
        if signal_tag == BuySignalTag.CAN_BUY:
            comments.append("可执行")
        elif signal_tag == BuySignalTag.OBSERVE:
            comments.append("需观察")
        else:
            comments.append("不建议")

        # 风险提示
        if stock.stock_continuity_tag.value == "末端谨慎":
            comments.append("注意末端风险")

        return "，".join(comments)


# 全局服务实例
buy_point_service = BuyPointService()
