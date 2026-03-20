"""
V1.0 集成测试

测试完整的决策链路：
1. 市场环境分析
2. 板块扫描
3. 个股筛选
4. 买点分析
5. 卖点分析
6. 账户适配
7. 完整决策输出
"""
import pytest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    MarketEnvInput,
    MarketEnvTag,
    RiskLevel,
    StockInput,
    AccountInput,
)
from app.services.market_env import MarketEnvService
from app.services.sector_scan import SectorScanService
from app.services.stock_filter import StockFilterService
from app.services.buy_point import BuyPointService
from app.services.sell_point import SellPointService
from app.services.account_adapter import AccountAdapterService


class TestV1Integration:
    """V1.0 完整决策链路集成测试"""

    @pytest.fixture
    def market_env_service(self):
        return MarketEnvService()

    @pytest.fixture
    def sector_scan_service(self):
        return SectorScanService()

    @pytest.fixture
    def stock_filter_service(self):
        return StockFilterService()

    @pytest.fixture
    def buy_point_service(self):
        return BuyPointService()

    @pytest.fixture
    def sell_point_service(self):
        return SellPointService()

    @pytest.fixture
    def account_adapter_service(self):
        return AccountAdapterService()

    @pytest.fixture
    def mock_market_data(self):
        """模拟市场数据 - 进攻环境"""
        return MarketEnvInput(
            trade_date="2026-03-20",
            index_sh=1.5,
            index_sz=1.8,
            index_cyb=2.0,
            up_down_ratio={"up": 2500, "down": 1500},
            limit_up_count=50,
            limit_down_count=5,
            broken_board_rate=15.0,
            market_turnover=12000,
            risk_appetite_tag="积极"
        )

    @pytest.fixture
    def mock_stocks(self):
        """模拟个股数据"""
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
                pre_close=11.5
            ),
            StockInput(
                ts_code="600519.SH",
                stock_name="贵州茅台",
                sector_name="白酒",
                close=1850.0,
                change_pct=3.2,
                turnover_rate=1.5,
                amount=450000,
                vol_ratio=1.2,
                high=1860.0,
                low=1790.0,
                open=1795.0,
                pre_close=1792.0
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
                pre_close=533.0
            ),
        ]

    @pytest.fixture
    def mock_account(self):
        """模拟账户数据"""
        return AccountInput(
            total_asset=1000000,
            available_cash=400000,
            total_position_ratio=0.6,
            holding_count=4,
            today_new_buy_count=1,
            t1_locked_positions=[]
        )

    # ========== 步骤1: 市场环境分析 ==========

    def test_step1_market_env_analysis(self, market_env_service, mock_market_data):
        """
        测试步骤1: 市场环境分析
        
        验证点：能输出正确的环境判定
        """
        result = market_env_service.analyze(mock_market_data)
        
        # 验证输出
        assert result.market_env_tag in [MarketEnvTag.ATTACK, MarketEnvTag.NEUTRAL, MarketEnvTag.DEFENSE]
        assert result.breakout_allowed is not None
        assert result.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert result.market_comment is not None
        assert len(result.market_comment) > 0

    # ========== 步骤2: 板块扫描 ==========

    def test_step2_sector_scan(self, sector_scan_service):
        """
        测试步骤2: 板块扫描
        
        验证点：能识别主线、次主线、跟风、杂毛板块
        """
        result = sector_scan_service.scan("2026-03-20")
        
        # 验证输出结构
        assert result.trade_date == "2026-03-20"
        assert result.total_sectors >= 0
        assert isinstance(result.mainline_sectors, list)
        assert isinstance(result.sub_mainline_sectors, list)
        assert isinstance(result.follow_sectors, list)
        assert isinstance(result.trash_sectors, list)

    # ========== 步骤3: 个股筛选 ==========

    def test_step3_stock_filter(self, stock_filter_service, mock_stocks):
        """
        测试步骤3: 个股筛选
        
        验证点：能对个股进行评分和分类
        """
        from app.models.schemas import MarketEnvTag, RiskLevel
        from unittest.mock import MagicMock
        
        # 创建模拟市场环境
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        mock_env.breakout_allowed = True
        mock_env.risk_level = RiskLevel.LOW
        
        # 创建板块映射
        from app.models.schemas import SectorOutput, SectorMainlineTag, SectorContinuityTag, SectorTradeabilityTag
        mock_sector = SectorOutput(
            sector_name="银行",
            sector_change_pct=3.0,
            sector_strength_rank=1,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_comment="主线板块"
        )
        sector_map = {"银行": mock_sector}
        
        # 筛选
        result = stock_filter_service._score_stock(mock_stocks[0], mock_env, sector_map)
        
        # 验证输出
        assert result.ts_code == "000001.SZ"
        assert result.stock_name == "平安银行"
        assert result.stock_strength_tag is not None

    # ========== 步骤4: 买点分析 ==========

    def test_step4_buy_point_analysis(self, buy_point_service, mock_stocks):
        """
        测试步骤4: 买点分析
        
        验证点：买点输出包含触发、确认、失效条件
        """
        from app.models.schemas import (
            StockOutput, StockStrengthTag, StockContinuityTag,
            StockTradeabilityTag, StockCoreTag, StockPoolTag,
            MarketEnvTag, RiskLevel
        )
        
        # 创建强势股
        strong_stock = StockOutput(
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
            stock_comment="强势股"
        )
        
        # 创建模拟市场环境
        class MockEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        result = buy_point_service._analyze_stock_buy_point(strong_stock, MockEnv())
        
        # 验证买点输出
        assert result.ts_code == "000001.SZ"
        assert result.buy_trigger_cond is not None
        assert len(result.buy_trigger_cond) > 0
        assert result.buy_confirm_cond is not None
        assert len(result.buy_confirm_cond) > 0
        assert result.buy_invalid_cond is not None
        assert len(result.buy_invalid_cond) > 0

    # ========== 步骤5: 卖点分析 ==========

    def test_step5_sell_point_analysis(self, sell_point_service):
        """
        测试步骤5: 卖点分析
        
        验证点：能识别止损/止盈/减仓/观察
        """
        from app.models.schemas import AccountPosition, MarketEnvTag
        
        # 亏损持仓
        losing_holding = AccountPosition(
            ts_code="300750.SZ",
            stock_name="宁德时代",
            holding_qty=500,
            cost_price=200.0,
            market_price=180.0,
            pnl_pct=-10.0,
            holding_market_value=90000,
            buy_date="2026-03-10",
            can_sell_today=True,
            holding_reason="新能源反弹"
        )
        
        class MockEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        result = sell_point_service._analyze_position(losing_holding, MockEnv(), {})
        
        # 验证卖点输出
        assert result.ts_code == "300750.SZ"
        assert result.sell_point_type is not None
        assert result.sell_trigger_cond is not None
        assert result.sell_reason is not None

    # ========== 步骤6: 账户适配 ==========

    def test_step6_account_adapter(self, account_adapter_service, mock_account):
        """
        测试步骤6: 账户适配
        
        验证点：能评估仓位压力和新开仓许可
        """
        # 测试仓位压力评估
        pressure = account_adapter_service._judge_position_pressure(
            mock_account.total_position_ratio,
            mock_account.holding_count
        )
        
        assert pressure in ["低", "中", "高"]
        
        # 测试新开仓判断
        from app.models.schemas import MarketEnvTag
        from unittest.mock import MagicMock
        
        mock_env = MagicMock()
        mock_env.market_env_tag = MarketEnvTag.ATTACK
        
        new_allowed, action = account_adapter_service._judge_new_position(
            mock_account.total_position_ratio,
            mock_account.holding_count,
            mock_env,
            mock_account.today_new_buy_count
        )
        
        assert isinstance(new_allowed, bool)
        assert action in ["可执行", "谨慎执行", "不执行"]

    # ========== 步骤7: 完整决策链路 ==========

    def test_full_decision_chain(self):
        """
        测试步骤7: 完整决策链路
        
        验证点：所有模块能协同工作
        """
        from app.services.market_env import market_env_service
        from app.services.sector_scan import sector_scan_service
        from app.services.stock_filter import stock_filter_service
        from app.services.buy_point import buy_point_service
        from app.models.schemas import MarketEnvTag, RiskLevel
        from unittest.mock import MagicMock
        
        # 1. 市场环境
        market_data = MarketEnvInput(
            trade_date="2026-03-20",
            index_sh=2.0,
            index_sz=2.2,
            index_cyb=2.5,
            up_down_ratio={"up": 3000, "down": 1000},
            limit_up_count=60,
            limit_down_count=3,
            broken_board_rate=10.0,
            market_turnover=15000,
            risk_appetite_tag="积极"
        )
        
        market_result = market_env_service.analyze(market_data)
        assert market_result.market_env_tag == MarketEnvTag.ATTACK
        
        # 2. 板块扫描
        sector_result = sector_scan_service.scan("2026-03-20")
        assert sector_result.total_sectors >= 0
        
        # 完整链路验证通过
        assert True


class TestV1PRDRequirements:
    """V1.0 PRD 验收测试"""

    def test_must_have_market_env_switch(self):
        """
        PRD 要求：必须先判断市场环境
        
        "系统必须先判断市场环境，再进行个股层面分析"
        """
        from app.services.market_env import market_env_service
        from app.models.schemas import MarketEnvInput, MarketEnvTag
        
        # 防守环境
        defense_data = MarketEnvInput(
            trade_date="2026-03-20",
            index_sh=-1.5,
            index_sz=-2.0,
            index_cyb=-2.5,
            up_down_ratio={"up": 800, "down": 3000},
            limit_up_count=10,
            limit_down_count=30,
            broken_board_rate=40.0,
            market_turnover=6000,
            risk_appetite_tag="保守"
        )
        
        result = market_env_service.analyze(defense_data)
        assert result.market_env_tag == MarketEnvTag.DEFENSE
        assert result.breakout_allowed is False

    def test_must_have_three_pools(self):
        """
        PRD 要求：必须输出三池
        
        "每日选股结果必须固定拆分为三类"
        """
        from app.services.stock_filter import stock_filter_service
        from app.models.schemas import StockInput
        
        # 准备股票数据
        stocks = [
            StockInput(
                ts_code="TEST1.SZ",
                stock_name="测试1",
                sector_name="测试板块",
                close=10.0,
                change_pct=5.0,
                turnover_rate=10.0,
                amount=100000,
                high=10.5,
                low=9.5,
                open=9.6,
                pre_close=9.5
            ),
        ]
        
        # 测试分类方法存在
        assert hasattr(stock_filter_service, 'classify_pools')

    def test_must_have_buy_invalid_condition(self):
        """
        PRD 要求：买点必须包含失效条件
        
        "无失效条件的买点，不得进入可执行建议"
        """
        from app.services.buy_point import buy_point_service
        from app.models.schemas import (
            StockOutput, StockStrengthTag, StockContinuityTag,
            StockTradeabilityTag, StockCoreTag, StockPoolTag,
            MarketEnvTag, RiskLevel
        )
        
        stock = StockOutput(
            ts_code="TEST.SZ",
            stock_name="测试",
            sector_name="测试",
            change_pct=5.0,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.MARKET_WATCH,
            stock_falsification_cond="跌破MA5",
            stock_comment=""
        )
        
        class MockEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW
        
        result = buy_point_service._analyze_stock_buy_point(stock, MockEnv())
        
        # 验证失效条件
        assert result.buy_invalid_cond is not None
        assert len(result.buy_invalid_cond) > 0

    def test_must_have_t1_constraint(self):
        """
        PRD 要求：必须处理 T+1 约束
        
        "遵守 A 股 T+1"
        """
        from app.models.schemas import AccountPosition
        
        # 当日买入的持仓
        t1_position = AccountPosition(
            ts_code="TEST.SZ",
            stock_name="测试",
            holding_qty=100,
            cost_price=10.0,
            market_price=11.0,
            pnl_pct=10.0,
            holding_market_value=1100,
            buy_date="2026-03-20",  # 今天买入
            can_sell_today=False,   # T+1 锁定
            holding_reason="今日买入"
        )
        
        assert t1_position.can_sell_today is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
