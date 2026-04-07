"""
账户适配服务
"""
from typing import List
from loguru import logger

from app.models.schemas import (
    AccountInput,
    AccountOutput,
    AccountProfile,
    AccountPosition,
    MarketEnvTag,
)
from app.services.market_env import market_env_service


class AccountAdapterService:
    """账户适配服务"""

    # 仓位阈值
    POSITION_HIGH = 0.8   # 高仓位
    POSITION_MEDIUM = 0.6  # 中仓位
    POSITION_LOW = 0.4    # 低仓位
    AVAILABLE_CASH_MIN = 5000  # 最低可用资金

    # 持仓数量阈值
    HOLDING_COUNT_HIGH = 5  # 持仓过多
    HOLDING_COUNT_MEDIUM = 3  # 持仓适中

    # 当日新开仓阈值
    NEW_BUY_COUNT_LIMIT = 3  # 当日新开仓限制

    def __init__(self):
        self.market_env_service = market_env_service

    def adapt(
        self,
        trade_date: str,
        account: AccountInput,
        holdings: List[AccountPosition] = None,
        market_env=None,
    ) -> AccountOutput:
        """
        账户适配分析

        Args:
            trade_date: 交易日
            account: 账户信息
            holdings: 当前持仓列表

        Returns:
            账户适配结果
        """
        holdings = holdings or []

        # 获取市场环境
        market_env = market_env or self.market_env_service.get_current_env(trade_date)

        # 计算各项指标
        position_ratio = account.total_position_ratio
        holding_count = account.holding_count
        available_cash = account.available_cash
        total_asset = account.total_asset

        # 判断仓位压力
        position_pressure = self._judge_position_pressure(position_ratio, holding_count)

        # 判断是否允许新开仓
        new_allowed, action_tag = self._judge_new_position(
            position_ratio, holding_count, market_env, account.today_new_buy_count
        )

        # 确定优先动作
        priority_action = self._determine_priority_action(
            position_ratio, holding_count, market_env, holdings
        )

        # 生成说明
        comment = self._generate_comment(
            action_tag, position_pressure, priority_action, market_env
        )

        return AccountOutput(
            account_action_tag=action_tag,
            position_pressure_tag=position_pressure,
            new_position_allowed=new_allowed,
            priority_action=priority_action,
            account_comment=comment
        )

    def get_profile(
        self,
        account: AccountInput,
        holdings: List[AccountPosition] = None
    ) -> AccountProfile:
        """
        获取账户概况

        Args:
            account: 账户信息
            holdings: 持仓列表

        Returns:
            账户概况
        """
        holdings = holdings or []

        # 计算持仓市值
        market_value = sum(h.holding_market_value for h in holdings)

        # 计算T+1锁定数量
        t1_locked = sum(1 for h in holdings if not h.can_sell_today)

        return AccountProfile(
            total_asset=account.total_asset,
            available_cash=account.available_cash,
            total_position_ratio=account.total_position_ratio,
            holding_count=account.holding_count,
            today_new_buy_count=account.today_new_buy_count,
            t1_locked_count=t1_locked,
            market_value=market_value
        )

    def _judge_position_pressure(
        self,
        position_ratio: float,
        holding_count: int
    ) -> str:
        """判断仓位压力"""
        if position_ratio >= self.POSITION_HIGH or holding_count >= self.HOLDING_COUNT_HIGH:
            return "高"
        elif position_ratio >= self.POSITION_MEDIUM or holding_count >= self.HOLDING_COUNT_MEDIUM:
            return "中"
        else:
            return "低"

    def _judge_new_position(
        self,
        position_ratio: float,
        holding_count: int,
        market_env,
        today_new_buy_count: int
    ) -> tuple:
        """判断是否允许新开仓"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")

        # 市场环境判断
        if market_env.market_env_tag == MarketEnvTag.DEFENSE:
            # 防守环境，不允许新开仓
            return (False, "不执行")
        if market_profile == "弱中性":
            return (False, "谨慎执行")

        # 仓位判断
        if position_ratio >= self.POSITION_HIGH:
            return (False, "不执行")

        # 持仓数量判断
        if holding_count >= self.HOLDING_COUNT_HIGH:
            return (False, "不执行")

        # 当日新开仓判断
        if today_new_buy_count >= self.NEW_BUY_COUNT_LIMIT:
            return (False, "谨慎执行")

        # 仓位适中
        if position_ratio >= self.POSITION_MEDIUM:
            return (False, "谨慎执行")

        if market_profile == "中性偏谨慎":
            return (True, "谨慎执行")

        return (True, "可执行")

    def _determine_priority_action(
        self,
        position_ratio: float,
        holding_count: int,
        market_env,
        holdings: List[AccountPosition]
    ) -> str:
        """确定优先动作"""
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")
        # 1. 有亏损持仓优先处理
        for h in holdings:
            if h.pnl_pct < -3:
                return "先处理亏损持仓"

        # 2. 有弱势持仓优先处理
        for h in holdings:
            if h.pnl_pct < 0 and market_env.market_env_tag == MarketEnvTag.DEFENSE:
                return "先处理弱势持仓"

        # 3. 仓位重优先减仓
        if position_ratio >= self.POSITION_HIGH:
            return "优先减仓"

        # 4. 持仓多优先清理
        if holding_count >= self.HOLDING_COUNT_HIGH:
            return "清理低效持仓"

        # 5. 市场进攻可开新仓
        if market_env.market_env_tag == MarketEnvTag.ATTACK:
            return "可适度开新仓"
        if market_profile == "中性偏强":
            return "等主线确认后开新仓"
        if market_profile in {"中性偏谨慎", "弱中性"}:
            return "只做低吸或回踩确认"

        # 6. 默认观察
        return "保持现有仓位"

    def _generate_comment(
        self,
        action_tag: str,
        position_pressure: str,
        priority_action: str,
        market_env
    ) -> str:
        """生成说明"""
        comments = []
        market_profile = str(getattr(market_env, "market_env_profile", "") or "")

        # 仓位压力
        if position_pressure == "高":
            comments.append("仓位较高")
        elif position_pressure == "中":
            comments.append("仓位适中")
        else:
            comments.append("仓位较轻")

        # 市场环境
        if market_env.market_env_tag == MarketEnvTag.ATTACK:
            comments.append("市场进攻，可积极")
        elif market_env.market_env_tag == MarketEnvTag.NEUTRAL:
            if market_profile == "中性偏强":
                comments.append("市场中性偏强，可等主线确认")
            elif market_profile == "中性偏谨慎":
                comments.append("市场中性偏谨慎，优先低吸确认")
            elif market_profile == "弱中性":
                comments.append("市场弱中性，尽量少追价")
            else:
                comments.append("市场中性，谨慎")
        else:
            comments.append("市场防守，控制")

        # 操作建议
        comments.append(priority_action)

        return "，".join(comments)


# 全局服务实例
account_adapter_service = AccountAdapterService()
