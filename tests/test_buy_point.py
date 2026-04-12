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
    NextTradeabilityTag,
    RiskLevel,
    MarketEnvTag,
    StockPoolsOutput,
    AccountInput,
    SectorOutput,
    SectorMainlineTag,
    SectorContinuityTag,
    SectorTradeabilityTag,
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
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
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

    def test_market_watch_stock_only_observe(self, service, strong_stock):
        """
        测试：市场观察池股票不应直接给出可买
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.stock_pool_tag = StockPoolTag.MARKET_WATCH
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())

        assert buy_point.buy_signal_tag == BuySignalTag.OBSERVE

    def test_defense_account_executable_stock_can_trial_buy(self, service, strong_stock):
        """
        测试：防守环境下，明确放入账户可参与池的最强核心股可给轻仓试错信号
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            breakout_allowed = False
            risk_level = RiskLevel.HIGH

        strong_stock.stock_tradeability_tag = StockTradeabilityTag.NOT_RECOMMENDED
        strong_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE
        strong_stock.pool_entry_reason = "防守日仅保留最强核心股试错"
        buy_point = service._analyze_stock_buy_point(
            strong_stock,
            MockMarketEnv(),
            AccountInput(
                total_asset=100000,
                available_cash=80000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
        )

        assert buy_point.buy_signal_tag == BuySignalTag.CAN_BUY
        assert buy_point.buy_account_fit == "一般"
        assert "防守试错" in buy_point.buy_comment

    def test_weak_neutral_profile_blocks_regular_new_position(self, service, strong_stock):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
            market_env_profile = "弱中性"
            breakout_allowed = False
            risk_level = RiskLevel.MEDIUM

        strong_stock.stock_pool_tag = StockPoolTag.MARKET_WATCH
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())

        assert buy_point.buy_signal_tag == BuySignalTag.NOT_BUY

    def test_neutral_cautious_profile_reduces_order_pct(self, service, strong_stock):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
            market_env_profile = "中性偏谨慎"
            breakout_allowed = False
            risk_level = RiskLevel.MEDIUM

        pct = service._resolve_recommended_order_pct(strong_stock, MockMarketEnv())
        risk = service._assess_risk(strong_stock, MockMarketEnv(), BuyPointType.RETRACE_SUPPORT)

        assert pct == 0.12
        assert risk == RiskLevel.MEDIUM

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

    def test_breakthrough_trigger_condition_uses_price_level(self, service, strong_stock):
        """
        测试：突破型触发条件应使用价格位，不应误写成涨跌幅关键位
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.change_pct = 6.0
        strong_stock.close = 7.85
        strong_stock.pre_close = 7.20
        strong_stock.open = 7.30
        strong_stock.high = 7.92
        strong_stock.low = 7.22

        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())

        assert "触发价" in buy_point.buy_trigger_cond
        assert "当日高点" in buy_point.buy_trigger_cond
        assert "%" not in buy_point.buy_trigger_cond

    def test_breakthrough_context_downgraded_to_retrace_keeps_display_context(self, service):
        """
        测试：原始突破语境被降成回踩时，展示层应明确写成“突破后回踩”
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
            market_env_profile = "中性偏谨慎"
            breakout_allowed = False
            risk_level = RiskLevel.MEDIUM

        stock = StockOutput(
            ts_code="300781.SZ",
            stock_name="因赛集团",
            sector_name="快手概念",
            change_pct=8.47,
            close=37.15,
            pre_close=34.25,
            open=35.16,
            high=37.29,
            low=34.33,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.OBSERVABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.BREAKTHROUGH,
            stock_comment="已过确认位，当前位置不宜直接追高",
        )

        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT
        assert buy_point.buy_display_type == "突破后回踩"
        assert buy_point.buy_execution_context == "突破确认"

    def test_core_breakthrough_candidate_keeps_breakthrough_type_in_neutral(self, service):
        """
        测试：高质量突破候选在中性环境里，不应被一律压回回踩承接
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
            breakout_allowed = True
            risk_level = RiskLevel.MEDIUM

        stock = StockOutput(
            ts_code="300024.SZ",
            stock_name="机器人先锋",
            sector_name="机器人",
            change_pct=8.2,
            close=33.2,
            pre_close=30.68,
            open=31.1,
            high=33.4,
            low=30.9,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.BREAKTHROUGH,
            stock_falsification_cond="跌回前高下方",
            stock_comment="强确认",
        )

        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.BREAKTHROUGH

    def test_retrace_support_conditions_use_stock_specific_price_levels(self, service, medium_stock):
        """
        测试：回踩承接型条件应带个股自己的价格锚点，而不是通用模板句
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.open = 1550.0
        medium_stock.close = 1562.0
        medium_stock.pre_close = 1541.0
        medium_stock.low = 1538.0
        medium_stock.high = 1568.0
        medium_stock.avg_price = 1551.6
        medium_stock.stock_tradeability_tag = StockTradeabilityTag.TRADABLE
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE

        buy_point = service._analyze_stock_buy_point(medium_stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT
        assert "日内均价 1551.60" in buy_point.buy_trigger_cond
        assert "日内均价 1551.60" in buy_point.buy_confirm_cond
        assert "失效价" in buy_point.buy_confirm_cond

    def test_breakthrough_context_retrace_uses_execution_reference_in_conditions(self, service):
        """
        测试：原始突破语境被降成回踩时，触发/确认文案应优先围绕执行位，而不是统一回踩开盘价
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
            breakout_allowed = False
            risk_level = RiskLevel.MEDIUM

        stock = StockOutput(
            ts_code="600166.SH",
            stock_name="福田汽车",
            sector_name="汽车",
            change_pct=7.74,
            close=3.34,
            pre_close=3.10,
            open=3.12,
            high=3.39,
            low=3.06,
            avg_price=3.21,
            execution_reference_price=3.40,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.OBSERVABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.BREAKTHROUGH,
        )

        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT
        assert buy_point.buy_trigger_price == 3.40
        assert "执行位 3.40" in buy_point.buy_trigger_cond
        assert "执行位 3.40" in buy_point.buy_confirm_cond

    def test_extended_strong_stock_prefers_retrace_support(self, service, strong_stock):
        """
        测试：涨幅过大的强票不应默认继续追突破
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.change_pct = 8.5
        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT

    def test_account_executable_medium_stock_can_buy_on_retrace(self, service, medium_stock):
        """
        测试：账户可参与池中的中强可交易票，也可作为回踩承接型可买对象
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.stock_tradeability_tag = StockTradeabilityTag.TRADABLE
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE

        buy_point = service._analyze_stock_buy_point(
            medium_stock,
            MockMarketEnv(),
            AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
        )

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT
        assert buy_point.buy_signal_tag == BuySignalTag.CAN_BUY

    def test_medium_breakthrough_candidate_keeps_breakthrough_type(self, service):
        """
        测试：中强度但已明确进入突破确认语境的票，不应再被一律压成回踩承接
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        stock = StockOutput(
            ts_code="002371.SZ",
            stock_name="北方华创",
            sector_name="半导体设备",
            change_pct=5.2,
            close=88.2,
            pre_close=83.84,
            open=84.6,
            high=88.5,
            low=84.2,
            stock_strength_tag=StockStrengthTag.MEDIUM,
            stock_continuity_tag=StockContinuityTag.OBSERVABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.FOLLOW,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.BREAKTHROUGH,
            stock_falsification_cond="跌回启动平台",
            stock_comment="突破确认中",
        )

        buy_point = service._analyze_stock_buy_point(stock, MockMarketEnv())

        assert buy_point.buy_point_type == BuyPointType.BREAKTHROUGH

    def test_attack_env_ranks_breakthrough_ahead_of_retrace(self, service):
        """
        测试：进攻环境下，排序应优先显示突破型，而不是默认回踩型排在最前
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        breakthrough = BuyPointOutput(
            ts_code="000001.SZ",
            stock_name="A",
            sector_name="测试",
            candidate_source_tag="",
            candidate_bucket_tag="",
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE.value,
            pool_entry_reason="",
            account_entry_mode="",
            hard_filter_failed_rules=[],
            hard_filter_failed_count=0,
            hard_filter_pass_count=0,
            hard_filter_summary="",
            buy_signal_tag=BuySignalTag.CAN_BUY,
            buy_point_type=BuyPointType.BREAKTHROUGH,
            buy_trigger_cond="",
            buy_confirm_cond="",
            buy_invalid_cond="",
            buy_current_price=10.0,
            buy_current_change_pct=5.0,
            buy_quote_time=None,
            buy_data_source=None,
            buy_trigger_price=10.1,
            buy_invalid_price=9.8,
            buy_trigger_gap_pct=-0.8,
            buy_invalid_gap_pct=-2.0,
            buy_required_volume_ratio=1.2,
            buy_requires_sector_resonance=True,
            buy_risk_level=RiskLevel.MEDIUM,
            buy_account_fit="适合",
            buy_comment="",
        )
        retrace = breakthrough.model_copy(update={
            "ts_code": "000002.SZ",
            "stock_name": "B",
            "buy_point_type": BuyPointType.RETRACE_SUPPORT,
        })

        ranked = sorted(
            [retrace, breakthrough],
            key=lambda point: service._buy_point_rank_key(point, MockMarketEnv()),
            reverse=True,
        )

        assert ranked[0].buy_point_type == BuyPointType.BREAKTHROUGH

    def test_bucket_priority_prefers_strong_confirm_over_retrace_and_premove(self, service):
        breakthrough = BuyPointOutput(
            ts_code="000001.SZ",
            stock_name="A",
            sector_name="测试",
            candidate_source_tag="",
            candidate_bucket_tag="强势确认",
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE.value,
            pool_entry_reason="",
            account_entry_mode="",
            hard_filter_failed_rules=[],
            hard_filter_failed_count=0,
            hard_filter_pass_count=0,
            hard_filter_summary="",
            buy_signal_tag=BuySignalTag.OBSERVE,
            buy_point_type=BuyPointType.BREAKTHROUGH,
            buy_trigger_cond="",
            buy_confirm_cond="",
            buy_invalid_cond="",
            buy_current_price=10.0,
            buy_current_change_pct=4.0,
            buy_quote_time=None,
            buy_data_source=None,
            buy_trigger_price=10.1,
            buy_invalid_price=9.8,
            buy_trigger_gap_pct=-0.8,
            buy_invalid_gap_pct=-2.0,
            buy_required_volume_ratio=1.2,
            buy_requires_sector_resonance=True,
            buy_risk_level=RiskLevel.MEDIUM,
            buy_account_fit="适合",
            buy_comment="",
            review_bias_score=0.0,
        )
        retrace = breakthrough.model_copy(update={
            "ts_code": "000002.SZ",
            "candidate_bucket_tag": "趋势回踩",
            "buy_point_type": BuyPointType.RETRACE_SUPPORT,
        })
        premove = breakthrough.model_copy(update={
            "ts_code": "000003.SZ",
            "candidate_bucket_tag": "异动预备",
            "buy_point_type": BuyPointType.LOW_SUCK,
        })

        ranked = sorted(
            [retrace, premove, breakthrough],
            key=lambda point: service._buy_point_rank_key(point, None),
            reverse=True,
        )

        assert [item.candidate_bucket_tag for item in ranked] == ["强势确认", "趋势回踩", "异动预备"]

    def test_account_executable_buy_point_includes_recommended_order_sizing(self, service, strong_stock):
        """
        测试：可买列表会返回基于账户资金测算的建议股数
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.close = 21.35
        strong_stock.pre_close = 20.77
        strong_stock.open = 20.9
        strong_stock.high = 21.5
        strong_stock.low = 20.8
        strong_stock.account_entry_mode = "standard"
        account = AccountInput(
            total_asset=100000,
            available_cash=50000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        )

        buy_point = service._analyze_stock_buy_point(
            strong_stock,
            MockMarketEnv(),
            account,
        )
        buy_point = service._apply_recommended_order_sizing(
            buy_point,
            strong_stock,
            MockMarketEnv(),
            account,
        )

        assert buy_point.account_entry_mode == "standard"
        assert buy_point.recommended_order_pct == 0.2
        assert buy_point.recommended_shares == 900
        assert buy_point.recommended_lots == 9
        assert buy_point.recommended_order_amount == 19215.0

    def test_account_executable_caution_stock_can_buy_on_comfortable_retrace(self, service, medium_stock):
        """
        测试：账户可参与池中的谨慎票，只要是舒服回踩位，也应进入可买
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.stock_tradeability_tag = StockTradeabilityTag.CAUTION
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE

        buy_point = service._analyze_stock_buy_point(
            medium_stock,
            MockMarketEnv(),
            AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
        )

        assert buy_point.buy_point_type == BuyPointType.RETRACE_SUPPORT
        assert buy_point.buy_signal_tag == BuySignalTag.CAN_BUY

    def test_far_from_trigger_available_point_downgrades_to_observe(self, service, medium_stock):
        """
        测试：回踩型可买票若现价离触发位过远，应降回观察列表
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.stock_tradeability_tag = StockTradeabilityTag.TRADABLE
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE
        medium_stock.open = 100.0
        medium_stock.close = 103.0
        medium_stock.pre_close = 99.6
        medium_stock.high = 103.6
        medium_stock.low = 99.8

        response = service.analyze(
            "2026-04-06",
            stocks=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.1,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=MockMarketEnv(),
            scored_stocks=[medium_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-04-06",
                market_watch_pool=[],
                account_executable_pool=[medium_stock],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        assert response.available_buy_points == []
        assert len(response.observe_buy_points) == 1
        assert response.observe_buy_points[0].buy_signal_tag == BuySignalTag.OBSERVE
        assert "现价离执行位仍偏远" in response.observe_buy_points[0].buy_comment

    def test_near_trigger_available_point_stays_in_available(self, service, medium_stock):
        """
        测试：回踩型可买票若现价已接近触发位，应继续留在可买列表
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.stock_tradeability_tag = StockTradeabilityTag.TRADABLE
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE
        medium_stock.open = 100.0
        medium_stock.close = 101.0
        medium_stock.pre_close = 99.6
        medium_stock.high = 101.4
        medium_stock.low = 99.8

        response = service.analyze(
            "2026-04-06",
            stocks=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.1,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=MockMarketEnv(),
            scored_stocks=[medium_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-04-06",
                market_watch_pool=[],
                account_executable_pool=[medium_stock],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        assert len(response.available_buy_points) == 1
        assert response.observe_buy_points == []
        assert response.available_buy_points[0].buy_signal_tag == BuySignalTag.CAN_BUY

    def test_buy_point_contains_current_price_and_gap(self, service, strong_stock):
        """
        测试：买点输出应包含最新价及与关键价位的距离
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.close = 12.5
        strong_stock.pre_close = 11.5
        strong_stock.open = 11.6
        strong_stock.high = 12.8
        strong_stock.low = 11.5

        buy_point = service._analyze_stock_buy_point(strong_stock, MockMarketEnv())

        assert buy_point.buy_current_price == 12.5
        assert buy_point.buy_current_change_pct == 8.5
        assert buy_point.buy_trigger_gap_pct is not None
        assert buy_point.buy_invalid_gap_pct is not None

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

    def test_analyze_skips_holding_process_pool(self, service, strong_stock):
        """
        测试：持仓处理池股票不应出现在买点列表中
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.stock_pool_tag = StockPoolTag.HOLDING_PROCESS
        response = service.analyze(
            "2026-03-20",
            stocks=[],
            account=None,
            market_env=MockMarketEnv(),
            scored_stocks=[strong_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-03-20",
                market_watch_pool=[],
                account_executable_pool=[],
                holding_process_pool=[strong_stock],
                total_count=1,
            ),
        )

        assert response.total_count == 0
        assert response.available_buy_points == []
        assert response.observe_buy_points == []
        assert response.not_buy_points == []

    def test_available_buy_points_only_come_from_account_executable_pool(self, service, strong_stock):
        """
        测试：可买列表必须只来自账户可参与池
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.change_pct = 6.0
        strong_stock.stock_pool_tag = StockPoolTag.MARKET_WATCH

        response = service.analyze(
            "2026-03-20",
            stocks=[],
            market_env=MockMarketEnv(),
            scored_stocks=[strong_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-03-20",
                market_watch_pool=[strong_stock],
                account_executable_pool=[],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        assert response.available_buy_points == []
        assert len(response.observe_buy_points) == 1
        assert response.observe_buy_points[0].stock_pool_tag == StockPoolTag.MARKET_WATCH.value

    def test_buy_point_output_keeps_pool_source_fields(self, service, medium_stock):
        """
        测试：买点结果应保留来源池与入池原因，方便页面联动展示
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        medium_stock.stock_tradeability_tag = StockTradeabilityTag.TRADABLE
        medium_stock.stock_pool_tag = StockPoolTag.ACCOUNT_EXECUTABLE
        medium_stock.pool_entry_reason = "账户允许参与，优先看回踩承接"

        buy_point = service._analyze_stock_buy_point(
            medium_stock,
            MockMarketEnv(),
            AccountInput(
                total_asset=100000,
                available_cash=50000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
        )

        assert buy_point.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE.value
        assert buy_point.pool_entry_reason == "账户允许参与，优先看回踩承接"

    def test_analyze_overlays_realtime_display_quote(self, service, strong_stock, monkeypatch):
        """
        测试：盘中买点列表展示价应走实时行情，不受稳定三池日线口径影响
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.close = 12.5
        strong_stock.pre_close = 11.5
        strong_stock.open = 11.6
        strong_stock.high = 12.8
        strong_stock.low = 11.5
        strong_stock.quote_time = "2026-03-23 15:00:00"
        strong_stock.data_source = "daily"

        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._should_use_realtime_quote",
            lambda trade_date: True,
        )
        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._fetch_realtime_stock_quote_map",
            lambda ts_codes: {
                "000001.SZ": {
                    "close": 12.88,
                    "change_pct": 11.13,
                    "quote_time": "2026-03-24 10:31:00",
                    "data_source": "realtime_dc",
                }
            },
        )

        response = service.analyze(
            "2026-03-24",
            stocks=[],
            market_env=MockMarketEnv(),
            scored_stocks=[strong_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-03-24",
                market_watch_pool=[],
                account_executable_pool=[strong_stock],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        assert response.total_count == 1
        assert response.available_buy_points == []
        buy_point = response.observe_buy_points[0]
        assert buy_point.buy_current_price == 12.88
        assert buy_point.buy_current_change_pct == 11.13
        assert buy_point.buy_quote_time == "2026-03-24 10:31:00"
        assert buy_point.buy_data_source == "realtime_dc"
        assert buy_point.buy_trigger_gap_pct is not None
        assert buy_point.buy_invalid_gap_pct is not None
        assert buy_point.buy_signal_tag == BuySignalTag.OBSERVE

    def test_analyze_syncs_execution_reference_from_account_pool(self, service, strong_stock, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.close = 12.5
        strong_stock.pre_close = 11.5
        strong_stock.open = 11.6
        strong_stock.high = 12.8
        strong_stock.low = 11.5
        strong_stock.execution_reference_price = None
        strong_stock.execution_reference_gap_pct = None
        strong_stock.execution_proximity_tag = None

        pool_stock = strong_stock.model_copy(deep=True)
        pool_stock.execution_reference_price = 12.10
        pool_stock.execution_reference_gap_pct = -3.2
        pool_stock.execution_proximity_tag = "待回踩"
        pool_stock.execution_proximity_note = "当前价距离确认区仍远。"

        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._should_use_realtime_quote",
            lambda trade_date: True,
        )
        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._fetch_realtime_stock_quote_map",
            lambda ts_codes: {
                "000001.SZ": {
                    "close": 12.88,
                    "change_pct": 11.13,
                    "quote_time": "2026-03-24 10:31:00",
                    "data_source": "realtime_dc",
                }
            },
        )

        response = service.analyze(
            "2026-03-24",
            stocks=[],
            market_env=MockMarketEnv(),
            scored_stocks=[strong_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-03-24",
                market_watch_pool=[],
                account_executable_pool=[pool_stock],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        buy_point = response.observe_buy_points[0]
        assert buy_point.execution_reference_price == 12.10
        assert buy_point.execution_proximity_tag == "待回踩"
        assert buy_point.execution_reference_gap_pct == -6.06

    def test_analyze_syncs_execution_reference_from_market_watch_pool(self, service, strong_stock, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        strong_stock.close = 68.3
        strong_stock.pre_close = 62.0
        strong_stock.open = 62.5
        strong_stock.high = 69.0
        strong_stock.low = 61.8
        strong_stock.execution_reference_price = None
        strong_stock.execution_reference_gap_pct = None
        strong_stock.execution_proximity_tag = None

        pool_stock = strong_stock.model_copy(deep=True)
        pool_stock.execution_reference_price = 68.465
        pool_stock.execution_reference_gap_pct = 0.24
        pool_stock.execution_proximity_tag = "接近执行位"
        pool_stock.execution_proximity_note = "回踩确认区已接近。"

        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._should_use_realtime_quote",
            lambda trade_date: True,
        )
        monkeypatch.setattr(
            "app.services.buy_point.tushare_client._fetch_realtime_stock_quote_map",
            lambda ts_codes: {
                "000001.SZ": {
                    "close": 68.30,
                    "change_pct": 10.16,
                    "quote_time": "2026-04-12 10:31:00",
                    "data_source": "realtime_dc",
                }
            },
        )

        response = service.analyze(
            "2026-04-12",
            stocks=[],
            market_env=MockMarketEnv(),
            scored_stocks=[strong_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-04-12",
                market_watch_pool=[pool_stock],
                account_executable_pool=[],
                holding_process_pool=[],
                total_count=1,
            ),
        )

        buy_point = response.observe_buy_points[0]
        assert buy_point.stock_pool_tag == StockPoolTag.MARKET_WATCH.value
        assert buy_point.execution_reference_price == 68.465
        assert buy_point.execution_proximity_tag == "接近执行位"
        assert buy_point.execution_reference_gap_pct == 0.24

    def test_analyze_attaches_dual_mainline_direction_context(self, service):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
            breakout_allowed = True
            risk_level = RiskLevel.LOW

        theme_stock = StockOutput(
            ts_code="002031.SZ",
            stock_name="巨轮智能",
            sector_name="通用设备",
            concept_names=["机器人"],
            change_pct=7.2,
            close=10.2,
            open=9.7,
            high=10.4,
            low=9.6,
            pre_close=9.51,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
        )
        industry_stock = StockOutput(
            ts_code="001896.SZ",
            stock_name="豫能控股",
            sector_name="电力",
            change_pct=7.2,
            close=7.5,
            open=7.1,
            high=7.6,
            low=7.0,
            pre_close=6.99,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
        )
        theme_leader = SectorOutput(
            sector_name="机器人",
            sector_source_type="concept",
            sector_change_pct=6.4,
            sector_score=99.0,
            sector_strength_rank=1,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=3,
        )
        industry_leader = SectorOutput(
            sector_name="电力",
            sector_source_type="industry",
            sector_change_pct=4.1,
            sector_score=93.0,
            sector_strength_rank=2,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=4,
        )

        response = service.analyze(
            "2026-04-09",
            stocks=[],
            market_env=MockMarketEnv(),
            scored_stocks=[industry_stock, theme_stock],
            stock_pools=StockPoolsOutput(
                trade_date="2026-04-09",
                theme_leaders=[theme_leader],
                industry_leaders=[industry_leader],
                market_watch_pool=[],
                account_executable_pool=[industry_stock, theme_stock],
                holding_process_pool=[],
                total_count=2,
            ),
        )

        assert response.theme_leaders[0].sector_name == "机器人"
        assert response.industry_leaders[0].sector_name == "电力"
        assert response.available_buy_points[0].direction_match_role == "theme"
        assert response.available_buy_points[0].direction_match_name == "机器人"
        assert response.available_buy_points[0].direction_match_source_type == "concept"
        assert response.available_buy_points[1].direction_match_role == "industry"
        assert response.available_buy_points[1].direction_match_name == "电力"


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
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
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
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
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
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
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
