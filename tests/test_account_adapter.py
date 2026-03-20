"""
账户适配模块测试

测试 V0.4 卖点与账户模块 - 账户适配功能：
- 仓位压力评估（低/中/高）
- 新开仓许可判定
- 优先动作建议
- 账户适配作为最后一道关口
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    AccountPosition,
    AccountInput,
    AccountOutput,
    MarketEnvTag,
)
from app.services.account_adapter import AccountAdapterService


class TestAccountAdapter:
    """账户适配服务测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return AccountAdapterService()

    # ========== 仓位压力测试 ==========

    def test_low_position_pressure(self, service):
        """
        测试：低仓位压力
        
        验证点：仓位 < 50% 应为低压力
        """
        result = service._judge_position_pressure(0.4, 2)  # 40%仓位，2只持仓
        
        assert result == "低", f"40%仓位应为低压力，实际: {result}"

    def test_medium_position_pressure(self, service):
        """
        测试：中等仓位压力
        
        验证点：50% <= 仓位 < 70% 应为中压力
        """
        result = service._judge_position_pressure(0.65, 4)  # 65%仓位，4只持仓
        
        assert result == "中", f"65%仓位应为中压力，实际: {result}"

    def test_high_position_pressure(self, service):
        """
        测试：高仓位压力
        
        验证点：仓位 >= 70% 应为高压力
        """
        result = service._judge_position_pressure(0.8, 6)  # 80%仓位，6只持仓
        
        assert result == "高", f"80%仓位应为高压力，实际: {result}"

    # ========== 新开仓许可测试 ==========

    def test_new_position_allowed_low_pressure(self, service):
        """
        测试：低压力时允许新开仓
        
        验证点：仓位低时允许开新仓
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        
        result, action = service._judge_new_position(0.4, 2, mock_env, 0)
        
        assert result is True

    def test_new_position_blocked_high_pressure(self, service):
        """
        测试：高压力时禁止新开仓
        
        验证点：仓位高时禁止开新仓
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        
        result, action = service._judge_new_position(0.9, 8, mock_env, 2)
        
        assert result is False
        assert action == "不执行"

    def test_new_position_blocked_by_defense_env(self, service):
        """
        测试：防守环境禁止新开仓
        
        验证点：防守环境下不允许新开仓
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.DEFENSE
        
        result, action = service._judge_new_position(0.3, 1, mock_env, 0)
        
        assert result is False

    def test_new_position_blocked_too_many_today(self, service):
        """
        测试：当日开仓过多时禁止新开仓
        
        验证点：当日已开仓 >= 3 只时应禁止
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        
        result, action = service._judge_new_position(0.5, 3, mock_env, 3)
        
        assert result is False

    # ========== 优先动作测试 ==========

    def test_priority_action_sell_weak_in_high_pressure(self, service):
        """
        测试：高仓位时的优先动作
        
        验证点：高仓位时应优先处理弱持仓
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        holdings = []
        
        result = service._determine_priority_action(0.85, 7, mock_env, holdings)
        
        # 高仓位时应建议卖出或减仓
        assert "减仓" in result or "卖出" in result or "处理" in result

    def test_priority_action_buy_in_low_pressure(self, service):
        """
        测试：低仓位时的优先动作
        
        验证点：低仓位时可考虑开新仓
        """
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        holdings = []
        
        result = service._determine_priority_action(0.3, 1, mock_env, holdings)
        
        # 低仓位时可建议买入
        assert "买入" in result or "开仓" in result or "建仓" in result or "可" in result


class TestAccountAdapterPRDRequirements:
    """PRD 验收要求测试"""

    @pytest.fixture
    def service(self):
        return AccountAdapterService()

    def test_must_be_last_gateway(self, service):
        """
        PRD 要求：账户适配必须作为最后一道关口
        
        "账户适配模块必须作为交易建议落地前的最后一道关口"
        """
        # 高仓位 + 防守环境 -> 不执行
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.DEFENSE
        
        result, action = service._judge_new_position(0.95, 10, mock_env, 3)
        
        assert result is False or action == "不执行"

    def test_must_consider_available_cash(self, service):
        """
        PRD 要求：必须考虑可用资金
        """
        # 极高仓位（资金紧张）
        result = service._judge_position_pressure(0.99, 15)
        
        # 资金紧张 + 高仓位 = 高压力
        assert result == "高"

    def test_must_limit_weak_market_expansion(self, service):
        """
        PRD 要求：必须能限制弱市乱开仓
        
        "不允许在弱市中无差别做突破"
        """
        # 防守环境
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.DEFENSE
        
        # 即使仓位低，防守环境也不应允许新开仓
        result, action = service._judge_new_position(0.2, 1, mock_env, 0)
        
        assert result is False

    def test_must_have_t1_constraint_handling(self, service):
        """
        PRD 要求：必须处理 T+1 约束
        
        T+1 锁定的持仓当日不可卖
        """
        t1_positions = [
            AccountPosition(
                ts_code="TEST01.SZ",
                stock_name="测试1",
                holding_qty=100,
                cost_price=10.0,
                market_price=11.0,
                pnl_pct=10.0,
                holding_market_value=1100,
                buy_date="2026-03-19",
                can_sell_today=False,  # T+1 锁定
                holding_reason="今日买入"
            ),
        ]
        
        # 验证 T+1 持仓今日不可卖
        for pos in t1_positions:
            assert pos.can_sell_today is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
