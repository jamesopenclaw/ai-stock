"""
个股筛选模块测试

测试 V0.3 选股与买点模块 - 个股筛选功能：
- 个股评分逻辑
- 三池分类（市场最强观察池 / 趋势辨识度观察池 / 账户可参与池 / 持仓处理池）
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
    StockRoleTag,
    DayStrengthTag,
    StructureStateTag,
    NextTradeabilityTag,
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

    def test_mainline_leader_with_poor_entry_stays_in_market_watch_only(self, service, mock_market_env_attack):
        """
        测试：主线龙头但买点差，只进市场最强观察池，不进账户可参与池
        """
        leader_stock = StockInput(
            ts_code="002100.SZ",
            stock_name="天花龙头",
            sector_name="机器人",
            close=18.2,
            change_pct=9.8,
            turnover_rate=19.0,
            amount=180000,
            vol_ratio=2.8,
            high=18.5,
            low=16.3,
            open=16.6,
            pre_close=16.58,
            stage_tag="加速",
            candidate_source_tag="涨停入选/涨幅前列",
        )
        sector = SectorOutput(
            sector_name="机器人",
            sector_source_type="concept",
            sector_change_pct=3.6,
            sector_score=95.0,
            sector_strength_rank=1,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=3,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [leader_stock],
            holdings=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=80000,
                total_position_ratio=0.2,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.market_watch_pool) == 1
        assert len(pools.account_executable_pool) == 0
        watched = pools.market_watch_pool[0]
        assert watched.stock_pool_tag == StockPoolTag.MARKET_WATCH
        assert watched.day_strength_tag == DayStrengthTag.LIMIT_STRONG
        assert watched.next_tradeability_tag == NextTradeabilityTag.CHASE_ONLY
        assert "账户可参与池" in " ".join(watched.not_other_pools)

    def test_trend_structure_stock_can_enter_trend_and_account_pools(self, service, mock_market_env_attack):
        """
        测试：主线前排但存在舒服回踩确认位时，可同时进入趋势池与账户池
        """
        trend_stock = StockInput(
            ts_code="002200.SZ",
            stock_name="趋势核心",
            sector_name="算力",
            close=25.5,
            change_pct=5.4,
            turnover_rate=9.5,
            amount=180000,
            vol_ratio=1.6,
            high=26.2,
            low=23.4,
            open=24.7,
            pre_close=24.19,
            stage_tag="回调",
            candidate_source_tag="涨幅前列",
        )
        sector = SectorOutput(
            sector_name="算力",
            sector_source_type="concept",
            sector_change_pct=2.8,
            sector_score=90.0,
            sector_strength_rank=2,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=4,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [trend_stock],
            holdings=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=85000,
                total_position_ratio=0.15,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.market_watch_pool) == 1
        assert len(pools.trend_recognition_pool) == 1
        assert len(pools.account_executable_pool) == 1
        trend_item = pools.trend_recognition_pool[0]
        account_item = pools.account_executable_pool[0]
        assert trend_item.structure_state_tag == StructureStateTag.DIVERGENCE
        assert trend_item.stock_role_tag == StockRoleTag.FRONT
        assert account_item.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE
        assert "可参与池" in (account_item.why_this_pool or "")

    def test_tradable_breakthrough_stock_can_enter_account_pool(self, service, mock_market_env_attack):
        """
        测试：交易性为可交易的突破票，应允许进入账户可参与池
        """
        breakout_stock = StockInput(
            ts_code="002201.SZ",
            stock_name="强势确认",
            sector_name="算力",
            close=26.1,
            change_pct=6.2,
            turnover_rate=16.2,
            amount=210000,
            vol_ratio=1.8,
            high=26.5,
            low=24.9,
            open=25.0,
            pre_close=24.58,
            stage_tag="主升",
            candidate_source_tag="涨幅前列",
        )
        sector = SectorOutput(
            sector_name="算力",
            sector_source_type="concept",
            sector_change_pct=2.8,
            sector_score=90.0,
            sector_strength_rank=2,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=4,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [breakout_stock],
            holdings=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=85000,
                total_position_ratio=0.15,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.market_watch_pool) == 1
        assert len(pools.account_executable_pool) == 1
        assert "突破确认机会" in (pools.account_executable_pool[0].pool_entry_reason or "")

    def test_medium_retrace_stock_can_enter_account_pool(self, service, mock_market_env_attack):
        """
        测试：中等强度但存在明确回踩确认位的票，应允许进入账户可参与池
        """
        retrace_stock = StockInput(
            ts_code="002202.SZ",
            stock_name="回踩确认",
            sector_name="算力",
            close=18.6,
            change_pct=4.2,
            turnover_rate=7.8,
            amount=160000,
            vol_ratio=1.5,
            high=18.9,
            low=17.9,
            open=18.0,
            pre_close=17.85,
            stage_tag="回调",
            candidate_source_tag="涨幅前列",
        )
        sector = SectorOutput(
            sector_name="算力",
            sector_source_type="concept",
            sector_change_pct=2.8,
            sector_score=90.0,
            sector_strength_rank=2,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=4,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [retrace_stock],
            holdings=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=85000,
                total_position_ratio=0.15,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        assert len(pools.account_executable_pool) == 1
        assert "回踩确认位" in (pools.account_executable_pool[0].pool_entry_reason or "")

    def test_visible_account_pool_keeps_comfortable_entries(self, service):
        """
        测试：账户可参与池展示前 10 只时，应保留部分回踩/低吸类型，避免被突破票全部挤掉
        """
        def make_output(idx, next_tag):
            return StockOutput(
                ts_code=f"000{idx:03d}.SZ",
                stock_name=f"测试{idx}",
                sector_name="算力",
                change_pct=5.0,
                stock_strength_tag=StockStrengthTag.STRONG,
                stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
                stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
                stock_core_tag=StockCoreTag.CORE,
                stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
                next_tradeability_tag=next_tag,
            )

        items = [make_output(i, NextTradeabilityTag.BREAKTHROUGH) for i in range(8)]
        items += [make_output(100 + i, NextTradeabilityTag.RETRACE_CONFIRM) for i in range(3)]

        visible = service._select_visible_account_executable(items, limit=10)

        comfortable_count = sum(
            1 for stock in visible
            if stock.next_tradeability_tag in {NextTradeabilityTag.RETRACE_CONFIRM, NextTradeabilityTag.LOW_SUCK}
        )
        breakthrough_count = sum(
            1 for stock in visible
            if stock.next_tradeability_tag == NextTradeabilityTag.BREAKTHROUGH
        )
        assert len(visible) == 10
        assert comfortable_count >= 3
        assert breakthrough_count >= 3

    def test_visible_account_pool_prioritizes_account_entry_score(self, service):
        """
        测试：账户可参与池应优先按执行分排序，而不是继续按综合分排。
        """
        breakthrough = StockOutput(
            ts_code="000001.SZ",
            stock_name="突破票",
            sector_name="算力",
            change_pct=6.8,
            stock_score=95.0,
            account_entry_score=79.0,
            stock_strength_tag=StockStrengthTag.STRONG,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.BREAKTHROUGH,
        )
        retrace = StockOutput(
            ts_code="000002.SZ",
            stock_name="回踩票",
            sector_name="算力",
            change_pct=3.4,
            stock_score=88.0,
            account_entry_score=96.0,
            stock_strength_tag=StockStrengthTag.MEDIUM,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.CAUTION,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            next_tradeability_tag=NextTradeabilityTag.RETRACE_CONFIRM,
        )

        visible = service._select_visible_account_executable([breakthrough, retrace], limit=10)

        assert [stock.ts_code for stock in visible] == ["000002.SZ", "000001.SZ"]

    def test_follow_stock_stays_out_of_formal_pools(self, service, mock_market_env_attack):
        """
        测试：后排跟风/杂毛不进入正式池
        """
        follower = StockInput(
            ts_code="300555.SZ",
            stock_name="后排补涨",
            sector_name="普通题材",
            close=11.2,
            change_pct=3.3,
            turnover_rate=5.2,
            amount=60000,
            vol_ratio=1.1,
            high=11.9,
            low=10.8,
            open=10.9,
            pre_close=10.84,
            stage_tag="震荡",
            candidate_source_tag="涨幅前列",
        )
        sector = SectorOutput(
            sector_name="普通题材",
            sector_source_type="industry",
            sector_change_pct=0.9,
            sector_score=58.0,
            sector_strength_rank=9,
            sector_mainline_tag=SectorMainlineTag.FOLLOW,
            sector_continuity_tag=SectorContinuityTag.OBSERVABLE,
            sector_tradeability_tag=SectorTradeabilityTag.CAUTION,
            sector_continuity_days=1,
            sector_comment="跟风",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [follower],
            holdings=[],
            account=None,
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[],
                sub_mainline_sectors=[],
                follow_sectors=[sector],
                trash_sectors=[],
            ),
        )

        assert len(pools.market_watch_pool) == 0
        assert len(pools.trend_recognition_pool) == 0
        assert len(pools.account_executable_pool) == 0

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
            + len(pools.trend_recognition_pool)
            + len(pools.account_executable_pool)
            + len(pools.holding_process_pool)
        )
        assert pools.total_count == visible_count

    def test_stock_output_contains_profile_and_pool_explanations(self, service, mock_market_env_attack):
        """
        测试：输出应包含五项画像和池间解释字段
        """
        stock = StockInput(
            ts_code="002201.SZ",
            stock_name="结构说明票",
            sector_name="芯片",
            close=31.4,
            change_pct=6.1,
            turnover_rate=10.0,
            amount=150000,
            vol_ratio=1.8,
            high=32.0,
            low=29.7,
            open=30.4,
            pre_close=29.6,
            stage_tag="回调",
            candidate_source_tag="涨幅前列",
        )
        sector = SectorOutput(
            sector_name="芯片",
            sector_source_type="concept",
            sector_change_pct=2.5,
            sector_score=88.0,
            sector_strength_rank=2,
            sector_mainline_tag=SectorMainlineTag.MAINLINE,
            sector_continuity_tag=SectorContinuityTag.SUSTAINABLE,
            sector_tradeability_tag=SectorTradeabilityTag.TRADABLE,
            sector_continuity_days=3,
            sector_comment="主线",
        )

        pools = service.classify_pools(
            "2026-03-20",
            [stock],
            holdings=[],
            account=AccountInput(
                total_asset=100000,
                available_cash=90000,
                total_position_ratio=0.1,
                holding_count=1,
                today_new_buy_count=0,
            ),
            market_env=mock_market_env_attack,
            sector_scan=MagicMock(
                mainline_sectors=[sector],
                sub_mainline_sectors=[],
                follow_sectors=[],
                trash_sectors=[],
            ),
        )

        output = pools.account_executable_pool[0]
        assert output.sector_profile_tag is not None
        assert output.stock_role_tag is not None
        assert output.day_strength_tag is not None
        assert output.structure_state_tag is not None
        assert output.next_tradeability_tag is not None
        assert output.why_this_pool
        assert isinstance(output.not_other_pools, list)
        assert output.pool_decision_summary

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
