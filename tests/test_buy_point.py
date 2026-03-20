"""
买点分析模块测试

测试 V0.3 选股与买点模块 - 买点分析功能：
- 买点信号判定（可买/观察/不买）
- 买点类型判定（突破/回踩承接/修复转强）
- 触发/确认/失效条件
- 风险等级评估
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    StockInput,
    StockOutput,
    StockStrengthTag,
    StockContinuityTag,
    StockTradeabilityTag,
    StockCoreTag,
    StockPoolTag,
    BuyPointOutput,
    BuyPointType,
    BuySignalTag,
    RiskLevel,
    MarketEnvTag,
)
from app.services.buy_point import BuyPointService


class TestBuyPoint:
    """买点分析服务测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return BuyPointService()

    @pytest.fixture
    def strong_stock(self):
        """强势股（可用于买点分析）"""
        return StockOutput(
            ts_code="000001.SZ",
            stock_name="平安银行",
            sector_name="银行",
            change_pct=8.5,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
            stock_falsification_cond="跌破MA5",
            stock_comment="强势股，可关注"
        )

    @pytest.fixture
    def medium_stock(self):
        """中等股票"""
        return StockOutput(
            ts_code="600519.SH",
            stock_name="贵州茅台",
            sector_name="白酒",
            change_pct=3.2,
            stock_strength_tag=StockStrengthTag.MEDIUM,
            stock_continuity_tag=StockContinuityTag.OBSERVABLE,
            stock_tradeability_tag=StockTradeabilityTag.CAUTION,
            stock_core_tag=StockCoreTag.FOLLOW,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            stock_falsification_cond="跌破10日均线",
            stock_comment="观望为主"
        )

    @pytest.fixture
    def weak_stock(self):
        """弱势股"""
        return StockOutput(
            ts_code="300750.SZ",
            stock_name="宁德时代",
            sector_name="新能源汽车",
            change_pct=-2.5,
            stock_strength_tag=StockStrengthTag.WEAK,
            stock_continuity_tag=StockContinuityTag.CAUTION,
            stock_tradeability_tag=StockTradeabilityTag.NOT_RECOMMENDED,
            stock_core_tag=StockCoreTag.TRASH,
            stock_pool_tag=StockPoolTag.NOT_IN_POOL,
            stock_falsification_cond="板块走弱",
            stock_comment="不建议参与"
        )

    # ========== 买点信号测试 ==========

    def test_buy_signal_for_strong_stock(self, service, strong_stock):
        """
        测试：强势股应有买点信号
        
        验证点：强势股应返回可买或观察信号
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())
        
        assert buy_point.buy_signal_tag in [BuySignalTag.CAN_BUY, BuySignalTag.OBSERVE], \
            f"强势股应有点买点信号，实际: {buy_point.buy_signal_tag}"

    def test_not_buy_signal_for_weak_stock(self, service, weak_stock):
        """
        测试：弱势股不应有点
        
        验证点：弱势股应返回不买信号
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            breakout_allowed = False
            risk_level = RiskLevel.HIGH
        
        buy_point = service._analyze_stock_buy_point(weak_stock, MockMarketEnv())
        
        assert buy_point.buy_signal_tag == BuySignalTag.NOT_BUY, \
            f"弱势股应返回不买信号，实际: {buy_point.buy_signal_tag}"

    # ========== 条件字段测试 ==========

    def test_trigger_condition_exists(self, service, strong_stock):
        """
        测试：触发条件存在
        
        验证点：买点输出必须包含触发条件
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())
        
        assert buy_point.buy_trigger_cond is not None
        assert len(buy_point.buy_trigger_cond) > 0

    def test_confirm_condition_exists(self, service, strong_stock):
        """
        测试：确认条件存在
        
        验证点：买点输出必须包含确认条件
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())
        
        assert buy_point.buy_confirm_cond is not None
        assert len(buy_point.buy_confirm_cond) > 0

    def test_invalid_condition_exists(self, service, strong_stock):
        """
        测试：失效条件存在
        
        验证点：买点输出必须包含失效条件（PRD 核心要求）
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())
        
        assert buy_point.buy_invalid_cond is not None
        assert len(buy_point.buy_invalid_cond) > 0

    # ========== 风险等级测试 ==========

    def test_low_risk_for_strong_stock_in_attack(self, service, strong_stock):
        """
        测试：低风险
        
        验证点：强势股在进攻环境应有较低风险
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())
        
        # 强势股在进攻环境风险不应为高
        assert buy_point.buy_risk_level != RiskLevel.HIGH


class TestBuyPointPRDRequirements:
    """PRD 验收要求测试"""

    @pytest.fixture
    def service(self):
        return BuyPointService()

    def test_must_have_trigger_condition(self, service):
        """
        PRD 要求：买点必须包含触发条件
        """
        stock = StockOutput(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            sector_name="测试板块",
            change_pct=5.0,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
            stock_falsification_cond="跌破MA5",
            stock_comment=""
        )
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())
        
        assert buy_point.buy_trigger_cond is not None
        assert len(buy_point.buy_trigger_cond) > 0

    def test_must_have_invalid_condition(self, service):
        """
        PRD 要求：买点必须包含失效条件（核心要求）
        
        "无失效条件的买点，不得进入可执行建议"
        """
        stock = StockOutput(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            sector_name="测试板块",
            change_pct=5.0,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
            stock_falsification_cond="跌破MA5",
            stock_comment=""
        )
        
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())
        
        assert buy_point.buy_invalid_cond is not None
        assert len(buy_point.buy_invalid_cond) > 0

    def test_must_reference_market_environment(self, service):
        """
        PRD 要求：买点必须引用市场环境结果
        
        "后续买点分析必须引用该模块输出结果，禁止各模块独立定义环境"
        """
        stock = StockOutput(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            sector_name="测试板块",
            change_pct=5.0,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
            stock_falsification_cond="",
            stock_comment=""
        )
        
        # 进攻环境
        class AttackEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        # 防守环境
        class DefenseEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            breakout_allowed = False
            risk_level = RiskLevel.HIGH
        
        buy_point_attack = service._analyze_stock_buy_point(stock, AttackEnv())
        buy_point_defense = service._analyze_stock_buy_point(stock, DefenseEnv())
        
        # 不同环境应产生不同的买点信号
        assert buy_point_attack.buy_signal_tag != buy_point_defense.buy_signal_tag


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
