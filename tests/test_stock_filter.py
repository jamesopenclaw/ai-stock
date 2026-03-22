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
    SellPointOutput,
    SellPointResponse,
    SellSignalTag,
    SellPointType,
    SellPriority,
    AccountInput,
    SectorOutput,
    SectorMainlineTag,
    SectorContinuityTag,
    SectorTradeabilityTag,
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

    def test_low_liquidity_stock_filtered_out(self, service, mock_market_env_attack):
        """
        测试：低流动性候选应在预过滤阶段剔除
        """
        illiquid = StockInput(
            ts_code="300001.SZ",
            stock_name="低流动性",
            sector_name="测试板块",
            close=6.5,
            change_pct=6.0,
            turnover_rate=12.0,
            amount=12000,
            vol_ratio=2.8,
            high=6.6,
            low=6.1,
            open=6.2,
            pre_close=6.1,
        )

        filtered = service.filter_with_context(
            "2026-03-20",
            [illiquid],
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert filtered == []

    def test_weak_not_recommended_stock_not_in_watch_pool(self, service, mock_market_env_attack):
        """
        测试：弱且不建议交易的股票不应挤占观察池
        """
        weak = StockInput(
            ts_code="300002.SZ",
            stock_name="弱票",
            sector_name="未知",
            close=8.0,
            change_pct=-1.5,
            turnover_rate=2.0,
            amount=50000,
            vol_ratio=0.6,
            high=8.2,
            low=7.9,
            open=8.1,
            pre_close=8.12,
        )

        pools = service.classify_pools(
            "2026-03-20",
            [weak],
            holdings=[],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.market_watch_pool) == 0

    def test_holding_code_normalized_into_holding_pool(self, service, mock_market_env_attack):
        """
        测试：持仓代码格式不一致时，仍应正确进入持仓处理池
        """
        held_stock = StockInput(
            ts_code="000001.SZ",
            stock_name="平安银行",
            sector_name="银行",
            close=12.5,
            change_pct=5.2,
            turnover_rate=12.0,
            amount=120000,
            vol_ratio=2.2,
            high=12.8,
            low=12.0,
            open=12.1,
            pre_close=11.9,
        )

        pools = service.classify_pools(
            "2026-03-20",
            [held_stock],
            holdings=[{"ts_code": "000001"}],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.holding_process_pool) == 1
        assert pools.holding_process_pool[0].ts_code == "000001.SZ"

    def test_defense_day_allows_only_top_core_trial_in_account_pool(self, service, mock_market_env_defense):
        """
        测试：防守环境下仅极少数最强核心股可进入账户可参与池
        """
        strong_core = StockInput(
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
            candidate_source_tag="涨幅前列/量比异动",
        )
        account = AccountInput(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        )
        sector = SectorOutput(
            sector_name="银行",
            sector_source_type="industry",
            sector_change_pct=1.8,
            sector_score=92.0,
            sector_strength_rank=1,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=3,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [strong_core],
            holdings=[],
            account=account,
            market_env=mock_market_env_defense,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.account_executable_pool) == 1
        account_stock = pools.account_executable_pool[0]
        assert account_stock.pool_entry_reason == "防守日仅保留最强核心股试错"
        assert "轻仓试错" in (account_stock.position_hint or "")

    def test_defense_trial_allows_medium_position_and_three_holdings(self, service, mock_market_env_defense):
        """
        测试：防守试错不应因 3 只持仓或中低仓位被机械拦截
        """
        strong_core = StockInput(
            ts_code="000539.SZ",
            stock_name="粤电力Ａ",
            sector_name="火力发电",
            close=7.8,
            change_pct=7.2,
            turnover_rate=16.0,
            amount=220000,
            vol_ratio=2.2,
            high=7.9,
            low=7.2,
            open=7.25,
            pre_close=7.28,
            candidate_source_tag="涨幅前列/量比异动",
        )
        account = AccountInput(
            total_asset=100000,
            available_cash=52000,
            total_position_ratio=0.48,
            holding_count=3,
            today_new_buy_count=0,
        )
        sector = SectorOutput(
            sector_name="火力发电",
            sector_source_type="industry",
            sector_change_pct=1.15,
            sector_score=90.0,
            sector_strength_rank=1,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=3,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [strong_core],
            holdings=[],
            account=account,
            market_env=mock_market_env_defense,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.account_executable_pool) == 1

    def test_low_liquidity_holding_still_in_holding_pool(self, service, mock_market_env_attack):
        """
        测试：即使持仓股票不满足预过滤，也必须进入持仓处理池
        """
        held_stock = StockInput(
            ts_code="300003.SZ",
            stock_name="持仓低流动性",
            sector_name="测试板块",
            close=6.2,
            change_pct=-0.8,
            turnover_rate=1.5,
            amount=12000,
            vol_ratio=0.7,
            high=6.3,
            low=6.0,
            open=6.15,
            pre_close=6.25,
        )

        scored = service.filter_with_context(
            "2026-03-20",
            [held_stock],
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert scored == []

        pools = service.classify_pools(
            "2026-03-20",
            [held_stock],
            holdings=[{"ts_code": "300003.SZ"}],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
            scored_stocks=scored,
        )

        assert len(pools.holding_process_pool) == 1
        assert pools.holding_process_pool[0].stock_pool_tag == StockPoolTag.HOLDING_PROCESS

    def test_total_count_matches_visible_pool_size(self, service, sample_stocks, mock_market_env_attack):
        """
        测试：total_count 应与实际返回池子数量一致
        """
        pools = service.classify_pools(
            "2026-03-20",
            sample_stocks,
            holdings=[],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        visible_count = (
            len(pools.market_watch_pool)
            + len(pools.account_executable_pool)
            + len(pools.holding_process_pool)
        )
        assert pools.total_count == visible_count

    def test_holding_pool_contains_position_context(self, service, mock_market_env_attack):
        """
        测试：持仓处理池应包含持仓本身的上下文字段
        """
        held_stock = StockInput(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            close=28.5,
            change_pct=1.2,
            turnover_rate=6.0,
            amount=180000,
            vol_ratio=1.4,
            high=29.1,
            low=27.8,
            open=28.0,
            pre_close=28.16,
        )

        holding = {
            "ts_code": "002463.SZ",
            "holding_qty": 1200,
            "cost_price": 26.3,
            "holding_market_value": 34200,
            "pnl_pct": 8.37,
            "buy_date": "2026-03-18",
            "can_sell_today": True,
            "holding_reason": "板块主升跟随",
            "holding_days": 2,
        }

        pools = service.classify_pools(
            "2026-03-20",
            [held_stock],
            holdings=[holding],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        enriched = pools.holding_process_pool[0]
        assert enriched.holding_qty == 1200
        assert enriched.cost_price == 26.3
        assert enriched.pnl_pct == 8.37
        assert enriched.can_sell_today is True
        assert enriched.holding_reason == "板块主升跟随"
        assert enriched.holding_days == 2

    def test_attach_sell_analysis_enriches_holding_pool(self, service, mock_market_env_attack):
        """
        测试：持仓处理池应直接带上卖点动作建议
        """
        held_stock = StockInput(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            close=28.5,
            change_pct=1.2,
            turnover_rate=6.0,
            amount=180000,
            vol_ratio=1.4,
            high=29.1,
            low=27.8,
            open=28.0,
            pre_close=28.16,
        )
        holding = {
            "ts_code": "002463.SZ",
            "holding_qty": 1200,
            "cost_price": 26.3,
            "holding_market_value": 34200,
            "pnl_pct": 8.37,
            "buy_date": "2026-03-18",
            "can_sell_today": True,
            "holding_reason": "板块主升跟随",
            "holding_days": 2,
        }

        pools = service.classify_pools(
            "2026-03-20",
            [held_stock],
            holdings=[holding],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )
        sell_analysis = SellPointResponse(
            trade_date="2026-03-20",
            hold_positions=[],
            reduce_positions=[
                SellPointOutput(
                    ts_code="002463.SZ",
                    stock_name="沪电股份",
                    sell_signal_tag=SellSignalTag.REDUCE,
                    sell_point_type=SellPointType.REDUCE_POSITION,
                    sell_trigger_cond="卖出一半仓位",
                    sell_reason="盈利较多，先锁定利润",
                    sell_priority=SellPriority.MEDIUM,
                    sell_comment="部分止盈",
                )
            ],
            sell_positions=[],
            total_count=1,
        )

        enriched = service.attach_sell_analysis(pools, sell_analysis).holding_process_pool[0]
        assert enriched.sell_signal_tag == "减仓"
        assert enriched.sell_point_type == "减仓"
        assert enriched.sell_trigger_cond == "卖出一半仓位"
        assert enriched.sell_reason == "盈利较多，先锁定利润"
        assert enriched.sell_priority == "中"
        assert enriched.sell_comment == "部分止盈"


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
