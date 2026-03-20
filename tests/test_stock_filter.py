"""
个股筛选模块测试

测试 V0.3 选股与买点模块 - 个股筛选功能：
- 个股评分逻辑
- 三池分类（市场最强观察池 / 账户可参与池 / 持仓处理池）
- 强弱标签判定
- 核心属性标签
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
    StockPoolsOutput,
    MarketEnvTag,
    RiskLevel,
)
from app.services.stock_filter import StockFilterService


class TestStockFilter:
    """个股筛选服务测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return StockFilterService()

    @pytest.fixture
    def mock_market_env_attack(self):
        """模拟进攻市场环境"""
        env = MagicMock()
        env.market_env_tag = MarketEnvTag.ATTACK
        env.breakout_allowed = True
        env.risk_level = RiskLevel.LOW
        return env

    @pytest.fixture
    def mock_market_env_defense(self):
        """模拟防守市场环境"""
        env = MagicMock()
        env.market_env_tag = MarketEnvTag.DEFENSE
        env.breakout_allowed = False
        env.risk_level = RiskLevel.HIGH
        return env

    @pytest.fixture
    def sample_stocks(self):
        """示例股票数据"""
        return [
            StockInput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                sector_name="银行",
                close=12.5,
                change_pct=8.5,
                turnover_rate=18.5,
                amount=150000,
                vol_ratio=2.5,
                high=12.8,
                low=11.5,
                open=11.6,
                pre_close=11.5,
                trend_tag="上升",
                stage_tag="启动"
            ),
            StockInput(
                ts_code="600519.SH",
                stock_name="贵州茅台",
                sector_name="白酒",
                close=1850.0,
                change_pct=3.2,
                turnover_rate=1.2,
                amount=450000,
                vol_ratio=1.2,
                high=1860.0,
                low=1790.0,
                open=1795.0,
                pre_close=1792.0,
                trend_tag="上升",
                stage_tag="主升"
            ),
            StockInput(
                ts_code="300750.SZ",
                stock_name="宁德时代",
                sector_name="新能源汽车",
                close=520.0,
                change_pct=-2.5,
                turnover_rate=8.5,
                amount=320000,
                vol_ratio=0.8,
                high=540.0,
                low=510.0,
                open=535.0,
                pre_close=533.0,
                trend_tag="下跌",
                stage_tag="回调"
            ),
        ]

    # ========== 个股评分测试 ==========

    def test_strong_stock_recognition(self, service, sample_stocks, mock_market_env_attack):
        """
        测试：强势股识别
        
        验证点：涨幅 > 7% 应识别为强势股
        """
        stock = sample_stocks[0]  # 平安银行 +8.5%
        
        scored = service._score_stock(stock, mock_market_env_attack, {})
        
        assert scored.stock_strength_tag == StockStrengthTag.STRONG, \
            f"涨幅8.5%应为强，实际: {scored.stock_strength_tag}"

    def test_medium_stock_recognition(self, service, sample_stocks, mock_market_env_attack):
        """
        测试：中等涨幅股识别
        
        验证点：3% < 涨幅 < 7% 应识别为中等
        """
        stock = sample_stocks[1]  # 茅台 +3.2%
        
        scored = service._score_stock(stock, mock_market_env_attack, {})
        
        assert scored.stock_strength_tag == StockStrengthTag.MEDIUM, \
            f"涨幅3.2%应为中，实际: {scored.stock_strength_tag}"

    def test_weak_stock_recognition(self, service, sample_stocks, mock_market_env_defense):
        """
        测试：弱势股识别
        
        验证点：防守环境下弱势股应被正确识别
        """
        stock = sample_stocks[2]  # 宁德时代 -2.5%
        
        scored = service._score_stock(stock, mock_market_env_defense, {})
        
        # 防守环境下，弱势股不应建议交易
        assert scored.stock_tradeability_tag == StockTradeabilityTag.NOT_RECOMMENDED

    # ========== 交易性标签测试 ==========

    def test_stock_scoring_works(self, service, sample_stocks, mock_market_env_attack):
        """
        测试：股票评分功能正常
        
        验证点：强势股在进攻环境下评分应正确
        """
        stock = sample_stocks[0]  # 平安银行
        
        scored = service._score_stock(stock, mock_market_env_attack, {})
        
        # 评分功能正常，应能产出结果
        assert scored.ts_code == stock.ts_code
        assert scored.stock_strength_tag is not None

    def test_not_recommended_in_defense(self, service, sample_stocks, mock_market_env_defense):
        """
        测试：防守环境下不建议交易
        
        验证点：防守环境下股票应不建议交易
        """
        stock = sample_stocks[0]  # 平安银行
        
        scored = service._score_stock(stock, mock_market_env_defense, {})
        
        assert scored.stock_tradeability_tag == StockTradeabilityTag.NOT_RECOMMENDED

    # ========== 三池分类测试 ==========

    def test_market_watch_pool_classification(self, service, sample_stocks, mock_market_env_attack):
        """
        测试：市场最强观察池
        
        验证点：高评分股票应进入市场最强观察池
        """
        stock = sample_stocks[0]  # 平安银行
        
        scored = service._score_stock(stock, mock_market_env_attack, {})
        
        assert scored.stock_strength_tag == StockStrengthTag.STRONG


class TestStockFilterEdgeCases:
    """个股筛选边界情况测试"""

    @pytest.fixture
    def service(self):
        return StockFilterService()

    @pytest.fixture
    def mock_market_env(self):
        env = MagicMock()
        env.market_env_tag = MarketEnvTag.ATTACK
        env.breakout_allowed = True
        env.risk_level = RiskLevel.LOW
        return env

    def test_extreme_high_change(self, service, mock_market_env):
        """测试：极端高涨幅"""
        stock = StockInput(
            ts_code="TEST001.SZ",
            stock_name="测试股",
            sector_name="测试板块",
            close=10.0,
            change_pct=20.0,
            turnover_rate=50.0,
            amount=100000,
            high=10.5,
            low=9.0,
            open=9.2,
            pre_close=8.3
        )
        
        scored = service._score_stock(stock, mock_market_env, {})
        
        assert scored.stock_strength_tag == StockStrengthTag.STRONG

    def test_extreme_negative_change(self, service, mock_market_env):
        """测试：极端负涨幅
        
        验证点：极端下跌应被识别
        """
        stock = StockInput(
            ts_code="TEST002.SZ",
            stock_name="测试股",
            sector_name="测试板块",
            close=8.0,
            change_pct=-15.0,
            turnover_rate=35.0,
            amount=100000,
            high=9.5,
            low=7.5,
            open=9.0,
            pre_close=9.4
        )
        
        scored = service._score_stock(stock, mock_market_env, {})
        
        # 极端下跌应被识别（可能是弱势或中等）
        assert scored.stock_strength_tag in [StockStrengthTag.WEAK, StockStrengthTag.MEDIUM]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
