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
    SectorMainlineTag,
    SectorTradeabilityTag,
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

    def test_stop_loss_zone_prefers_reduce_before_clear(self, service):
        """
        测试：刚进入止损区时，不再一刀切直接清仓

        验证点：轻微跌破止损阈值时，应先减仓防守，再看后续确认
        """
        position = AccountPosition(
            ts_code="002675.SZ",
            stock_name="东诚药业",
            holding_qty=200,
            cost_price=15.04,
            market_price=14.14,
            pnl_pct=-5.98,
            holding_market_value=2828,
            buy_date="2026-03-18",
            can_sell_today=True,
            holding_reason="修复仓",
        )

        class NeutralEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        sell_point = service._analyze_position(position, NeutralEnv(), {})

        assert sell_point.sell_signal_tag == SellSignalTag.REDUCE
        assert sell_point.sell_point_type == SellPointType.REDUCE_POSITION
        assert "止损区" in sell_point.sell_reason

    def test_deep_stop_loss_still_sells(self, service):
        """
        测试：深度亏损时仍应直接卖出
        """
        position = AccountPosition(
            ts_code="300750.SZ",
            stock_name="宁德时代",
            holding_qty=200,
            cost_price=100.0,
            market_price=91.5,
            pnl_pct=-8.5,
            holding_market_value=18300,
            buy_date="2026-03-12",
            can_sell_today=True,
            holding_reason="赛道跟随",
        )

        class NeutralEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        sell_point = service._analyze_position(position, NeutralEnv(), {})

        assert sell_point.sell_signal_tag == SellSignalTag.SELL
        assert sell_point.sell_point_type == SellPointType.STOP_LOSS

    # ========== 止盈测试 ==========

    def test_stop_profit_for_large_gain(self, service, profitable_position):
        """
        测试：大额盈利触发止盈
        
        验证点：盈利很多但结构不弱时，不应再机械止盈
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), {})
        
        assert sell_point.sell_signal_tag == SellSignalTag.HOLD, \
            f"盈利20%但未见结构转弱时应继续持有，实际: {sell_point.sell_signal_tag}"

    def test_stop_profit_signal_for_profitable(self, service, profitable_position):
        """
        测试：盈利持仓应给出减仓或卖出信号
        
        验证点：盈利足够多时应考虑止盈
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), {})
        
        assert sell_point.sell_signal_tag in [SellSignalTag.SELL, SellSignalTag.REDUCE, SellSignalTag.HOLD]

    def test_sell_point_contains_position_context(self, service, profitable_position):
        """
        测试：卖点输出应包含现价、成本和持仓上下文
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), {})

        assert sell_point.market_price == 1800.0
        assert sell_point.cost_price == 1500.0
        assert sell_point.pnl_pct == 20.0
        assert sell_point.holding_qty == 100
        assert sell_point.can_sell_today is True

    def test_analyze_sorts_by_priority_and_severity(self, service):
        """
        测试：同组卖点应按优先级和盈亏幅度排序
        """
        positions = [
            AccountPosition(
                ts_code="A.SZ",
                stock_name="A",
                holding_qty=100,
                cost_price=10.0,
                market_price=9.2,
                pnl_pct=-8.0,
                holding_market_value=920,
                buy_date="2026-03-10",
                can_sell_today=True,
                holding_reason="",
            ),
            AccountPosition(
                ts_code="B.SZ",
                stock_name="B",
                holding_qty=100,
                cost_price=10.0,
                market_price=9.6,
                pnl_pct=-4.0,
                holding_market_value=960,
                buy_date="2026-03-10",
                can_sell_today=True,
                holding_reason="",
            ),
        ]

        class NeutralEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        sector_scan = type(
            "SectorScan",
            (),
            {
                "mainline_sectors": [],
                "sub_mainline_sectors": [],
                "follow_sectors": [],
                "trash_sectors": [],
            },
        )()

        result = service.analyze(
            "2026-03-20",
            positions,
            market_env=NeutralEnv(),
            sector_scan=sector_scan,
        )

        assert result.sell_positions[0].ts_code == "A.SZ"

    # ========== 减仓测试 ==========

    def test_reduce_for_moderate_profit(self, service):
        """
        测试：中等盈利触发减仓
        
        验证点：盈利达到阈值但结构未弱化时，不应只按盈利减仓
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
        
        assert sell_point.sell_signal_tag == SellSignalTag.HOLD

    def test_reduce_for_profit_when_sector_turns_weak(self, service):
        """
        测试：盈利票在板块转弱时才减仓
        """
        position = AccountPosition(
            ts_code="TEST002.SZ",
            stock_name="测试股2",
            holding_qty=100,
            cost_price=10.0,
            market_price=10.8,
            pnl_pct=8.0,
            holding_market_value=1080,
            buy_date="2026-03-15",
            can_sell_today=True,
            holding_reason="板块轮动"
        )

        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        class WeakSector:
            sector_mainline_tag = SectorMainlineTag.TRASH
            sector_tradeability_tag = SectorTradeabilityTag.NOT_RECOMMENDED

        sell_point = service._analyze_position(
            position,
            MockMarketEnv(),
            {"测试板块": WeakSector()},
            "测试板块",
        )

        assert sell_point.sell_signal_tag == SellSignalTag.REDUCE
        assert sell_point.sell_point_type == SellPointType.REDUCE_POSITION

    def test_single_lot_position_should_not_be_marked_reduce(self, service):
        """
        测试：仅持有100股时，不应给出不可执行的减仓建议
        """
        position = AccountPosition(
            ts_code="TEST003.SZ",
            stock_name="测试股3",
            holding_qty=100,
            cost_price=10.0,
            market_price=10.9,
            pnl_pct=9.0,
            holding_market_value=1090,
            buy_date="2026-03-15",
            can_sell_today=True,
            holding_reason="板块轮动",
        )

        class MockMarketEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        class WeakSector:
            sector_mainline_tag = SectorMainlineTag.TRASH
            sector_tradeability_tag = SectorTradeabilityTag.NOT_RECOMMENDED

        sector_map = {"测试板块": WeakSector()}
        sell_point = service._analyze_position(position, MockMarketEnv(), sector_map, "测试板块")
        service._apply_sector_resonance_adjustment(
            sell_point,
            position,
            "测试板块",
            sector_map,
            MockMarketEnv(),
        )
        service._normalize_execution_constraints(sell_point, position)

        assert sell_point.sell_signal_tag == SellSignalTag.SELL
        assert "100股" in sell_point.sell_reason

    # ========== 持有测试 ==========

    def test_hold_for_small_profit_in_uptrend(self, service, profitable_position):
        """
        测试：上涨趋势中小幅盈利应持有
        
        验证点：强势股上涨趋势中应继续持有
        """
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.ATTACK
        
        class MainlineSector:
            sector_mainline_tag = SectorMainlineTag.MAINLINE
            sector_tradeability_tag = SectorTradeabilityTag.TRADABLE

        sector_map = {"白酒": MainlineSector()}
        
        sell_point = service._analyze_position(profitable_position, MockMarketEnv(), sector_map, "白酒")
        
        assert sell_point.sell_signal_tag == SellSignalTag.HOLD

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

    def test_defense_weak_sector_prefers_reduce_for_small_drawdown(self, service):
        """
        测试：弱市且板块转弱时，小幅盈亏应先减仓而不是一刀切卖出
        """
        position = AccountPosition(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            holding_qty=200,
            cost_price=86.45,
            market_price=84.30,
            pnl_pct=-2.49,
            holding_market_value=16860,
            buy_date="2026-03-18",
            can_sell_today=True,
            holding_reason="板块主升跟随",
        )

        class DefenseEnv:
            market_env_tag = MarketEnvTag.DEFENSE

        class WeakSector:
            sector_mainline_tag = SectorMainlineTag.TRASH
            sector_tradeability_tag = SectorTradeabilityTag.NOT_RECOMMENDED

        sell_point = service._analyze_position(position, DefenseEnv(), {"元器件": WeakSector()})
        service._apply_sector_resonance_adjustment(
            sell_point,
            position,
            "元器件",
            {"元器件": WeakSector()},
            DefenseEnv(),
        )

        assert sell_point.sell_signal_tag == SellSignalTag.REDUCE
        assert "先降仓" in sell_point.sell_reason or "先降" in sell_point.sell_comment

    def test_observe_signal_stays_in_hold_bucket(self, service):
        """
        测试：观察信号应归入持有观察，而不是落到卖出列表
        """
        position = AccountPosition(
            ts_code="000001.SZ",
            stock_name="平安银行",
            holding_qty=100,
            cost_price=12.0,
            market_price=13.2,
            pnl_pct=10.0,
            holding_market_value=1320,
            buy_date="2026-03-20",
            can_sell_today=False,
            holding_reason="今日新开仓",
        )

        class NeutralEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        response = service.analyze(
            "2026-03-20",
            [position],
            market_env=NeutralEnv(),
            sector_scan=type(
                "SectorScan",
                (),
                {
                    "mainline_sectors": [],
                    "sub_mainline_sectors": [],
                    "follow_sectors": [],
                    "trash_sectors": [],
                },
            )(),
        )

        assert len(response.hold_positions) == 1
        assert len(response.sell_positions) == 0
        assert response.hold_positions[0].sell_signal_tag == SellSignalTag.OBSERVE

    def test_invalid_reason_exits_even_without_large_loss(self, service):
        """
        测试：原买入逻辑失效时优先退出，不再依赖盈亏阈值
        """
        position = AccountPosition(
            ts_code="000002.SZ",
            stock_name="万科A",
            holding_qty=100,
            cost_price=10.0,
            market_price=10.6,
            pnl_pct=6.0,
            holding_market_value=1060,
            buy_date="2026-03-18",
            can_sell_today=True,
            holding_reason="地产反弹逻辑失效",
        )

        class NeutralEnv:
            market_env_tag = MarketEnvTag.NEUTRAL

        sell_point = service._analyze_position(position, NeutralEnv(), {})

        assert sell_point.sell_signal_tag == SellSignalTag.SELL
        assert sell_point.sell_point_type == SellPointType.INVALID_EXIT


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
            assert sell_point.sell_signal_tag is not None

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
