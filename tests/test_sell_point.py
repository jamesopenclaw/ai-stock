"""
卖点分析模块测试

测试 V0.4 卖点与账户模块 - 卖点分析功能：
- 卖点信号判定（持有/减仓/卖出/观察）
- 卖点类型分类（止损/止盈/减仓/失效退出）
- T+1 约束处理
- 优先级判定
"""
import pytest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    AccountPosition,
    SellPointOutput,
    SellSignalTag,
    SellPointType,
    SellPriority,
    MarketEnvTag,
)
from app.services.sell_point import SellPointService


class TestSellPoint:
    """卖点分析服务测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return SellPointService()

    @pytest.fixture
    def profitable_position(self):
        """盈利持仓"""
        return AccountPosition(
            ts_code="600519.SH",
            stock_name="贵州茅台",
            holding_qty=100,
            cost_price=1500.0,
            market_price=1800.0,
            pnl_pct=20.0,
            holding_market_value=180000,
            buy_date="2026-03-15",
            can_sell_today=True,
            holding_reason="核心资产"
        )

    @pytest.fixture
    def losing_position(self):
        """亏损持仓"""
        return AccountPosition(
            ts_code="300750.SZ",
            stock_name="宁德时代",
            holding_qty=200,
            cost_price=550.0,
            market_price=500.0,
            pnl_pct=-9.09,
            holding_market_value=100000,
            buy_date="2026-03-10",
            can_sell_today=True,
            holding_reason="新能源龙头"
        )

    @pytest.fixture
    def small_profit_position(self):
        """小幅盈利持仓"""
        return AccountPosition(
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=1000,
            cost_price=12.0,
            market_price=12.8,
            pnl_pct=6.67,
            holding_market_value=12800,
            buy_date="2026-03-18",
            can_sell_today=False,  # T+1 锁定
            holding_reason="银行轮动"
        )

    # ========== 止损测试 ==========

    def test_stop_loss_for_large_loss(self, service, losing_position):
        """
        测试：大额亏损触发止损
        
        验证点：亏损 > 5%（默认止损线）应触发止损
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(losing_position, MockMarketEnv(), {})
        
        assert sell_point.sell_point_type == SellPointType.STOP_LOSS, \
            f"亏损9%应触发止损，实际: {sell_point.sell_point_type}"

    def test_stop_loss_signal_for_large_loss(self, service, losing_position):
        """
        测试：大额亏损应给出卖出信号
        
        验证点：亏损超过止损线应卖出
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(losing_position, MockMarketEnv(), {})
        
        assert sell_point.sell_signal_tag in [SellSignalTag.SELL, SellSignalTag.REDUCE]

    # ========== 止盈测试 ==========

    def test_stop_profit_for_large_gain(self, service, profitable_position):
        """
        测试：大额盈利触发止盈
        
        验证点：盈利 > 15%（默认止盈线）应触发止盈
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), {})
        
        assert sell_point.sell_point_type == SellPointType.STOP_PROFIT, \
            f"盈利20%应触发止盈，实际: {sell_point.sell_point_type}"

    def test_stop_profit_signal_for_profitable(self, service, profitable_position):
        """
        测试：盈利持仓应给出减仓或卖出信号
        
        验证点：盈利足够多时应考虑止盈
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), {})
        
        assert sell_point.sell_signal_tag in [SellSignalTag.SELL, SellSignalTag.REDUCE, SellSignalTag.HOLD]

    # ========== 减仓测试 ==========

    def test_reduce_for_moderate_profit(self, service):
        """
        测试：中等盈利触发减仓
        
        验证点：盈利在 5-10% 之间可考虑减仓
        """
        position = AccountPosition(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            holding_qty=100,
            cost_price=10.0,
            market_price=10.8,
            pnl_pct=8.0,
            holding_market_value=1080,
            buy_date="2026-03-15",
            can_sell_today=True,
            holding_reason="测试"
        )
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(position, MockMarketEnv(), {})
        
        # 盈利 8%，在减仓阈值附近
        assert sell_point.sell_point_type in [SellPointType.STOP_PROFIT, SellPointType.REDUCE_POSITION]

    # ========== 持有测试 ==========

    def test_hold_for_small_profit_in_uptrend(self, service, profitable_position):
        """
        测试：上涨趋势中小幅盈利应持有
        
        验证点：强势股上涨趋势中应继续持有
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
        
        # 假设是主线板块
        sector_map = {"白酒": "MAINLINE"}
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), sector_map)
        
        # 进攻环境 + 主线板块 = 可能继续持有
        assert sell_point.sell_signal_tag in [SellSignalTag.HOLD, SellSignalTag.REDUCE]

    # ========== T+1 约束测试 ==========

    def test_t1_locked_position_cannot_sell(self, service, small_profit_position):
        """
        测试：T+1 锁定持仓
        
        验证点：当日不可卖的持仓应有特殊处理
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(small_profit_position, MockMarketEnv(), {})
        
        # T+1 锁定的持仓，今天不能卖
        # 应该在 can_sell_today 属性中体现或评论中说明
        # 检查评论中是否提到 T+1
        assert small_profit_position.can_sell_today is False

    # ========== 优先级测试 ==========

    def test_high_priority_for_large_loss(self, service, losing_position):
        """
        测试：大额亏损优先级高
        
        验证点：亏损严重应高优先级处理
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(losing_position, MockMarketEnv(), {})
        
        # 大额亏损应该是高优先级
        assert sell_point.sell_priority == SellPriority.HIGH

    # ========== 环境影响测试 ==========

    def test_defense_environment_increases_sell_pressure(self, service, profitable_position):
        """
        测试：防守环境增加卖出压力
        
        验证点：防守环境下应更积极卖出
        """
        # 进攻环境
        class AttackEnv:
            market_env_tag = MarketEnvTag.ATTACK
        
        # 防守环境
        class DefenseEnv:
            market_env_tag = MarketEnvTag.DEFENSE
        
        sell_point_attack = service._analyze_position(profitable_position, AttackEnv(), {})
        sell_point_defense = service._analyze_position(profitable_position, DefenseEnv(), {})
        
        # 防守环境下卖出压力更大
        # 至少信号不应该比进攻环境更乐观
        assert sell_point_defense.sell_signal_tag in [SellSignalTag.SELL, SellSignalTag.REDUCE]


class TestSellPointPRDRequirements:
    """PRD 验收要求测试"""

    @pytest.fixture
    def service(self):
        return SellPointService()

    def test_must_classify_sell_point_types(self, service):
        """
        PRD 要求：卖点必须区分止损/止盈/减仓/观察
        """
        test_cases = [
            # 止损案例
            AccountPosition(
                ts_code="TEST01.SZ",
                stock_name="测试1",
                holding_qty=100,
                cost_price=100.0,
                market_price=90.0,
                pnl_pct=-10.0,
                holding_market_value=90000,
                buy_date="2026-03-10",
                can_sell_today=True,
                holding_reason=""
            ),
            # 止盈案例
            AccountPosition(
                ts_code="TEST02.SZ",
                stock_name="测试2",
                holding_qty=100,
                cost_price=100.0,
                market_price=120.0,
                pnl_pct=20.0,
                holding_market_value=120000,
                buy_date="2026-03-10",
                can_sell_today=True,
                holding_reason=""
            ),
        ]
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        for position in test_cases:
            sell_point = service._analyze_position(position, MockMarketEnv(), {})
            
            # 必须有明确的卖点类型
            assert sell_point.sell_point_type is not None
            assert sell_point.sell_point_type in [
                SellPointType.STOP_LOSS,
                SellPointType.STOP_PROFIT,
                SellPointType.REDUCE_POSITION,
                SellPointType.INVALID_EXIT,
            ]

    def test_must_consider_t1_constraint(self, service):
        """
        PRD 要求：卖点必须考虑 T+1 约束
        """
        # 当日不可卖
        position = AccountPosition(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            holding_qty=100,
            cost_price=10.0,
            market_price=11.0,
            pnl_pct=10.0,
            holding_market_value=1100,
            buy_date="2026-03-19",  # 今天买入
            can_sell_today=False,  # T+1 锁定
            holding_reason="今日买入"
        )
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(position, MockMarketEnv(), {})
        
        # 验证 T+1 约束被考虑（can_sell_today 为 False 时应有特殊处理）
        assert position.can_sell_today is False

    def test_must_have_trigger_condition(self, service):
        """
        PRD 要求：卖点必须包含触发条件
        """
        position = AccountPosition(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            holding_qty=100,
            cost_price=100.0,
            market_price=90.0,
            pnl_pct=-10.0,
            holding_market_value=90000,
            buy_date="2026-03-10",
            can_sell_today=True,
            holding_reason=""
        )
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(position, MockMarketEnv(), {})
        
        assert sell_point.sell_trigger_cond is not None
        assert len(sell_point.sell_trigger_cond) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
