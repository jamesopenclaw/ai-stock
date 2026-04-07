"""
市场环境模块测试

测试 V0.2 市场环境判定功能：
- 市场环境判定（进攻/中性/防守）
- breakout_allowed 判定
- risk_level 判定
- API 响应格式
"""
import pytest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    MarketEnvInput,
    MarketEnvTag,
    RiskLevel
)
from app.services.market_env import MarketEnvService


class TestMarketEnv:
    """市场环境分析服务测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return MarketEnvService()

    def test_get_current_env_uses_last_completed_trade_date_before_realtime_window(self, service, monkeypatch):
        """
        测试：盘前分析应直接使用最近已完成交易日，而不是先请求今天再回退
        """
        class StubGateway:
            def __init__(self):
                self.requested_dates = []

            def now_trade_date(self):
                return "2026-03-31"

            def should_use_realtime_quote(self, trade_date):
                return False

            def should_use_market_snapshot(self, trade_date):
                return False

            def get_last_completed_trade_date(self, trade_date):
                assert trade_date == "20260331"
                return "20260330"

            def get_index_quote_with_meta(self, trade_date):
                self.requested_dates.append(("index", trade_date))
                return {
                    "rows": [
                        {"change_pct": 1.0},
                        {"change_pct": 0.8},
                        {"change_pct": 0.6},
                    ],
                    "data_trade_date": "20260330",
                }

            def get_limit_stats_with_meta(self, trade_date):
                self.requested_dates.append(("limit", trade_date))
                return {
                    "stats": {"limit_up_count": 50, "limit_down_count": 5, "broken_board_rate": 10.0},
                    "data_trade_date": "20260330",
                }

            def get_market_turnover_with_meta(self, trade_date):
                self.requested_dates.append(("turnover", trade_date))
                return {"market_turnover": 12000, "data_trade_date": "20260330"}

            def get_up_down_ratio_with_meta(self, trade_date):
                self.requested_dates.append(("updown", trade_date))
                return {"up_down_ratio": {"up": 2500, "down": 1500}, "data_trade_date": "20260330"}

        gateway = StubGateway()
        monkeypatch.setattr(service, "client", gateway)

        result = service.get_current_env("2026-03-31")

        assert result.trade_date == "2026-03-30"
        assert gateway.requested_dates == [
            ("index", "20260330"),
            ("limit", "20260330"),
            ("turnover", "20260330"),
            ("updown", "20260330"),
        ]

    def test_get_current_env_uses_today_snapshot_window_after_close(self, service, monkeypatch):
        class StubGateway:
            def __init__(self):
                self.requested_dates = []

            def now_trade_date(self):
                return "2026-04-07"

            def should_use_realtime_quote(self, trade_date):
                return False

            def should_use_market_snapshot(self, trade_date):
                return True

            def get_last_completed_trade_date(self, trade_date):
                return "20260403"

            def get_index_quote_with_meta(self, trade_date):
                self.requested_dates.append(("index", trade_date))
                return {
                    "rows": [
                        {"change_pct": 0.26},
                        {"change_pct": 0.36},
                        {"change_pct": 0.36},
                    ],
                    "data_trade_date": "20260407",
                }

            def get_limit_stats_with_meta(self, trade_date):
                self.requested_dates.append(("limit", trade_date))
                return {
                    "stats": {"limit_up_count": 101, "limit_down_count": 18, "broken_board_rate": 36.9},
                    "data_trade_date": "20260407",
                }

            def get_market_turnover_with_meta(self, trade_date):
                self.requested_dates.append(("turnover", trade_date))
                return {"market_turnover": 16000, "data_trade_date": "20260407"}

            def get_up_down_ratio_with_meta(self, trade_date):
                self.requested_dates.append(("updown", trade_date))
                return {
                    "up_down_ratio": {"up": 800, "down": 5200, "flat": 100, "total": 6100},
                    "data_trade_date": "20260407",
                }

        gateway = StubGateway()
        monkeypatch.setattr(service, "client", gateway)

        result = service.get_current_env("2026-04-07")

        assert result.trade_date == "2026-04-07"
        assert gateway.requested_dates == [
            ("index", "20260407"),
            ("limit", "20260407"),
            ("turnover", "20260407"),
            ("updown", "20260407"),
        ]

    # ========== 市场环境判定测试 ==========

    def test_market_env_attack_with_strong_index(self, service):
        """
        测试：市场环境判定-进攻（指数共振上涨）
        
        验证点：当日均大幅上涨，overall_score >= 70，应判定为"进攻"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=2.5,  # 上证 +2.5%
            index_sz=2.8,  # 深成 +2.8%
            index_cyb=3.0,  # 创业板 +3.0%
            up_down_ratio={"up": 3500, "down": 1000},
            limit_up_count=80,
            limit_down_count=2,
            broken_board_rate=8.0,
            market_turnover=15000,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.ATTACK, \
            f"预期: 进攻, 实际: {result.market_env_tag}"
        assert result.overall_score >= 70, \
            f"预期综合评分 >= 70, 实际: {result.overall_score}"

    def test_market_env_attack_with_high_limit_ups(self, service):
        """
        测试：市场环境判定-进攻（涨停家数多）
        
        验证点：涨停数 > 50，overall_score >= 70，应判定为"进攻"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.8,
            index_sz=1.0,
            index_cyb=1.2,
            up_down_ratio={"up": 2500, "down": 1500},
            limit_up_count=60,
            limit_down_count=5,
            broken_board_rate=12.0,
            market_turnover=12000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.ATTACK, \
            f"预期: 进攻, 实际: {result.market_env_tag}"

    def test_market_env_defense_with_all_drop(self, service):
        """
        测试：市场环境判定-防守（指数普跌）
        
        验证点：三大指数均下跌，应判定为"防守"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-1.5,
            index_sz=-2.0,
            index_cyb=-2.5,
            up_down_ratio={"up": 800, "down": 3000},
            limit_up_count=10,
            limit_down_count=30,
            broken_board_rate=40.0,
            market_turnover=7000,
            risk_appetite_tag="保守"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.DEFENSE, \
            f"预期: 防守, 实际: {result.market_env_tag}"
        assert result.overall_score < 40, \
            f"预期综合评分 < 40, 实际: {result.overall_score}"

    def test_market_env_defense_with_high_limit_downs(self, service):
        """
        测试：市场环境判定-防守（跌停家数多）
        
        验证点：跌停数 > 20，应判定为"防守"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-0.5,
            index_sz=-0.8,
            index_cyb=-1.0,
            up_down_ratio={"up": 1200, "down": 2500},
            limit_up_count=20,
            limit_down_count=25,
            broken_board_rate=35.0,
            market_turnover=8000,
            risk_appetite_tag="保守"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.DEFENSE, \
            f"预期: 防守, 实际: {result.market_env_tag}"

    def test_market_env_neutral_with_mixed_index(self, service):
        """
        测试：市场环境判定-中性（分化明显）
        
        验证点：指数分化，应判定为"中性"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.8,   # 上证涨
            index_sz=-0.3,  # 深成跌
            index_cyb=-1.0,  # 创业板跌
            up_down_ratio={"up": 1500, "down": 2000},
            limit_up_count=30,
            limit_down_count=10,
            broken_board_rate=20.0,
            market_turnover=10000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.NEUTRAL, \
            f"预期: 中性, 实际: {result.market_env_tag}"
        assert 40 <= result.overall_score < 70, \
            f"预期综合评分在 [40, 70), 实际: {result.overall_score}"

    # ========== breakout_allowed 测试 ==========

    def test_breakout_allowed_true_in_attack(self, service):
        """
        测试：breakout_allowed - 进攻时为 true
        
        验证点：进攻环境下，breakout_allowed 应为 true
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=2.0,
            index_sz=2.2,
            index_cyb=2.5,
            up_down_ratio={"up": 3000, "down": 1200},
            limit_up_count=55,
            limit_down_count=3,
            broken_board_rate=10.0,
            market_turnover=14000,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        assert result.breakout_allowed is True, \
            f"进攻环境下 breakout_allowed 应为 True, 实际: {result.breakout_allowed}"

    def test_breakout_allowed_false_in_defense(self, service):
        """
        测试：breakout_allowed - 防守时为 false
        
        验证点：防守环境下，breakout_allowed 应为 false
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-1.2,
            index_sz=-1.8,
            index_cyb=-2.0,
            up_down_ratio={"up": 900, "down": 2800},
            limit_up_count=8,
            limit_down_count=25,
            broken_board_rate=38.0,
            market_turnover=6500,
            risk_appetite_tag="保守"
        )

        result = service.analyze(market_data)

        assert result.breakout_allowed is False, \
            f"防守环境下 breakout_allowed 应为 False, 实际: {result.breakout_allowed}"

    def test_breakout_allowed_false_in_neutral_with_high_broken_board(self, service):
        """
        测试：breakout_allowed - 中性但炸板率高时为 false
        
        验证点：中性环境 + 炸板率 > 25%，breakout_allowed 应为 false
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.6,
            index_sz=0.4,
            index_cyb=0.3,
            up_down_ratio={"up": 1800, "down": 1800},
            limit_up_count=35,
            limit_down_count=8,
            broken_board_rate=30.0,  # 炸板率高
            market_turnover=9000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.NEUTRAL, \
            f"预期: 中性, 实际: {result.market_env_tag}"
        assert result.breakout_allowed is False, \
            f"中性+高炸板率时 breakout_allowed 应为 False, 实际: {result.breakout_allowed}"

    def test_sentiment_score_balances_breadth_and_speculation(self, service):
        """
        测试：广度较强但接力偏弱时，情绪分不应被单项指标压到过低

        验证点：应识别为中性，且评论明确提示“广度尚可、接力承压”
        """
        market_data = MarketEnvInput(
            trade_date="2026-04-07",
            index_sh=0.03,
            index_sz=-0.20,
            index_cyb=-0.46,
            up_down_ratio={"up": 3645, "down": 1781},
            limit_up_count=70,
            limit_down_count=17,
            broken_board_rate=37.5,
            market_turnover=11000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.NEUTRAL
        assert 45 <= result.sentiment_score <= 55, \
            f"情绪分应落在中性偏谨慎区间, 实际: {result.sentiment_score}"
        assert result.market_env_profile == "中性偏谨慎"
        assert result.market_headline == "可以盯盘，但优先低吸和回踩确认"
        assert result.trading_tempo_label == "观望低吸"
        assert result.dominant_factor_label == "广度强于接力"
        assert "接力" in result.market_comment
        assert ("广度" in result.market_comment or "多数个股" in result.market_comment)

    def test_sentiment_score_is_smooth_near_limit_up_boundary(self, service):
        """
        测试：涨停家数临界点附近应平滑，不应出现明显跳变
        """
        base_kwargs = dict(
            trade_date="2026-04-07",
            index_sh=0.2,
            index_sz=0.1,
            index_cyb=0.0,
            up_down_ratio={"up": 2400, "down": 1600},
            limit_down_count=6,
            broken_board_rate=16.0,
            market_turnover=12000,
            risk_appetite_tag="中性"
        )

        result_50 = service.analyze(MarketEnvInput(limit_up_count=50, **base_kwargs))
        result_51 = service.analyze(MarketEnvInput(limit_up_count=51, **base_kwargs))

        assert abs(result_51.sentiment_score - result_50.sentiment_score) < 1.0, \
            "涨停家数 +1 不应造成情绪分明显跳变"

    # ========== risk_level 测试 ==========

    def test_risk_level_low_in_attack(self, service):
        """
        测试：risk_level - 进攻时为低
        
        验证点：overall_score >= 70，risk_level 应为"低"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=2.5,
            index_sz=2.8,
            index_cyb=3.0,
            up_down_ratio={"up": 3500, "down": 800},
            limit_up_count=75,
            limit_down_count=2,
            broken_board_rate=7.0,
            market_turnover=16000,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        assert result.risk_level == RiskLevel.LOW, \
            f"进攻环境下 risk_level 应为低, 实际: {result.risk_level}"

    def test_risk_level_medium_in_neutral(self, service):
        """
        测试：risk_level - 中性时为中
        
        验证点：40 <= overall_score < 70，risk_level 应为"中"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.3,
            index_sz=0.5,
            index_cyb=0.2,
            up_down_ratio={"up": 1600, "down": 1900},
            limit_up_count=25,
            limit_down_count=12,
            broken_board_rate=18.0,
            market_turnover=9500,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.risk_level == RiskLevel.MEDIUM, \
            f"中性环境下 risk_level 应为中, 实际: {result.risk_level}"

    def test_risk_level_high_in_defense(self, service):
        """
        测试：risk_level - 防守时为高
        
        验证点：overall_score < 40，risk_level 应为"高"
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-2.0,
            index_sz=-2.5,
            index_cyb=-3.0,
            up_down_ratio={"up": 500, "down": 3500},
            limit_up_count=5,
            limit_down_count=40,
            broken_board_rate=50.0,
            market_turnover=5000,
            risk_appetite_tag="保守"
        )

        result = service.analyze(market_data)

        assert result.risk_level == RiskLevel.HIGH, \
            f"防守环境下 risk_level 应为高, 实际: {result.risk_level}"

    # ========== 边界条件测试 ==========

    def test_boundary_score_70_is_attack(self, service):
        """
        测试：边界条件 - score = 70 应为进攻
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=2.0,
            index_sz=2.0,
            index_cyb=2.0,
            up_down_ratio={"up": 2500, "down": 1500},
            limit_up_count=50,
            limit_down_count=5,
            broken_board_rate=10.0,
            market_turnover=12000,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.ATTACK, \
            f"score=70 应为进攻, 实际: {result.market_env_tag}"
        assert result.risk_level == RiskLevel.LOW

    def test_boundary_score_40_is_neutral(self, service):
        """
        测试：边界条件 - score = 40 应为中性
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.0,
            index_sz=0.0,
            index_cyb=0.0,
            up_down_ratio={"up": 1500, "down": 1500},
            limit_up_count=20,
            limit_down_count=10,
            broken_board_rate=20.0,
            market_turnover=8000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.NEUTRAL, \
            f"score=40 应为中性, 实际: {result.market_env_tag}"
        assert result.risk_level == RiskLevel.MEDIUM

    def test_edge_case_high_broken_board_rate(self, service):
        """
        测试：边界条件 - 极高炸板率
        
        验证点：炸板率极高（60%）时，会在市场评论中提示风险
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=1.5,
            index_sz=1.8,
            index_cyb=2.0,
            up_down_ratio={"up": 2800, "down": 1000},
            limit_up_count=80,
            limit_down_count=3,
            broken_board_rate=60.0,  # 极高炸板率
            market_turnover=13000,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        # 炸板率极高会在评论中提示
        assert "炸板率偏高" in result.market_comment or "炸板率" in result.market_comment, \
            f"极高炸板率应在评论中提示风险, 实际评论: {result.market_comment}"

    # ========== 评分详情测试 ==========

    def test_index_resonance_bonus(self, service):
        """
        测试：指数共振加分
        """
        # 三个指数同涨
        market_data_same = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=1.0,
            index_sz=1.0,
            index_cyb=1.0,
            up_down_ratio={"up": 2000, "down": 1500},
            limit_up_count=30,
            limit_down_count=5,
            broken_board_rate=15.0,
            market_turnover=10000,
            risk_appetite_tag="中性"
        )
        result_same = service.analyze(market_data_same)

        # 三个指数不同向
        market_data_diff = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=1.0,
            index_sz=-1.0,
            index_cyb=-1.0,
            up_down_ratio={"up": 1500, "down": 2000},
            limit_up_count=30,
            limit_down_count=5,
            broken_board_rate=15.0,
            market_turnover=10000,
            risk_appetite_tag="中性"
        )
        result_diff = service.analyze(market_data_diff)

        # 同向应该有更高的指数评分
        assert result_same.index_score > result_diff.index_score, \
            "指数共振应有更高的评分"

    def test_index_resonance_downside_is_penalty(self, service):
        """
        测试：同向下跌应扣分，而不是因为共振被抬高
        """
        market_data_same_down = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-1.2,
            index_sz=-1.4,
            index_cyb=-1.6,
            up_down_ratio={"up": 1600, "down": 1800},
            limit_up_count=28,
            limit_down_count=8,
            broken_board_rate=16.0,
            market_turnover=9500,
            risk_appetite_tag="中性"
        )
        market_data_mixed = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-1.2,
            index_sz=0.2,
            index_cyb=0.1,
            up_down_ratio={"up": 1600, "down": 1800},
            limit_up_count=28,
            limit_down_count=8,
            broken_board_rate=16.0,
            market_turnover=9500,
            risk_appetite_tag="中性"
        )

        result_same_down = service.analyze(market_data_same_down)
        result_mixed = service.analyze(market_data_mixed)

        assert result_same_down.index_score < result_mixed.index_score, \
            "同向下跌应降低指数评分"

    def test_neutral_breakout_requires_positive_breadth(self, service):
        """
        测试：中性环境下，若涨跌家数不占优，则不允许突破型交易
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=0.5,
            index_sz=0.4,
            index_cyb=0.2,
            up_down_ratio={"up": 1700, "down": 2000},
            limit_up_count=32,
            limit_down_count=9,
            broken_board_rate=18.0,
            market_turnover=11000,
            risk_appetite_tag="中性"
        )

        result = service.analyze(market_data)

        assert result.market_env_tag == MarketEnvTag.NEUTRAL
        assert result.breakout_allowed is False, "中性环境下涨跌家数不占优时不应追突破"

    def test_sentiment_quality_matters_more_than_raw_turnover(self, service):
        """
        测试：高成交额不能抵消明显走弱的情绪结构
        """
        weak_quality = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-0.4,
            index_sz=-0.6,
            index_cyb=-0.8,
            up_down_ratio={"up": 1200, "down": 2800},
            limit_up_count=18,
            limit_down_count=24,
            broken_board_rate=38.0,
            market_turnover=19000,
            risk_appetite_tag="中性"
        )
        healthy_quality = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-0.4,
            index_sz=-0.6,
            index_cyb=-0.8,
            up_down_ratio={"up": 2600, "down": 1400},
            limit_up_count=52,
            limit_down_count=4,
            broken_board_rate=9.0,
            market_turnover=12000,
            risk_appetite_tag="中性"
        )

        weak_result = service.analyze(weak_quality)
        healthy_result = service.analyze(healthy_quality)

        assert weak_result.sentiment_score < healthy_result.sentiment_score, \
            "高成交额不应盖过明显走弱的情绪质量"

    def test_market_comment_contains_actionable_reason_and_hint_in_defense(self, service):
        """
        测试：防守环境评语应同时包含原因和操作提示
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=-1.1,
            index_sz=-1.5,
            index_cyb=-1.8,
            up_down_ratio={"up": 900, "down": 2600},
            limit_up_count=12,
            limit_down_count=22,
            broken_board_rate=34.0,
            market_turnover=6800,
            risk_appetite_tag="保守"
        )

        result = service.analyze(market_data)

        assert "市场偏防守" in result.market_comment
        assert ("跌停" in result.market_comment or "涨跌家数比" in result.market_comment)
        assert ("控制仓位" in result.market_comment or "先收缩仓位" in result.market_comment)

    def test_market_comment_contains_breakout_guidance_in_attack(self, service):
        """
        测试：进攻环境评语应给出突破型操作提示
        """
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=1.8,
            index_sz=2.0,
            index_cyb=2.3,
            up_down_ratio={"up": 3200, "down": 1200},
            limit_up_count=68,
            limit_down_count=3,
            broken_board_rate=11.0,
            market_turnover=14500,
            risk_appetite_tag="积极"
        )

        result = service.analyze(market_data)

        assert "市场偏进攻" in result.market_comment
        assert ("涨停" in result.market_comment or "赚钱效应" in result.market_comment)
        assert "允许做强势突破" in result.market_comment

    def test_get_current_env_uses_cache_for_same_trade_date(self, service, monkeypatch):
        calls = {
            "index": 0,
            "limit": 0,
            "turnover": 0,
            "up_down": 0,
        }

        monkeypatch.setattr(service.client, "now_trade_date", lambda: "2026-03-29")
        monkeypatch.setattr(service.client, "should_use_realtime_quote", lambda _trade_date: False)

        def fake_index(_trade_date):
            calls["index"] += 1
            return {
                "rows": [
                    {"change_pct": 1.2},
                    {"change_pct": 1.0},
                    {"change_pct": 0.8},
                ],
                "data_trade_date": "20260327",
            }

        def fake_limit(_trade_date):
            calls["limit"] += 1
            return {
                "stats": {"limit_up_count": 45, "limit_down_count": 4, "broken_board_rate": 12.0},
                "data_trade_date": "20260327",
            }

        def fake_turnover(_trade_date):
            calls["turnover"] += 1
            return {
                "market_turnover": 12345,
                "data_trade_date": "20260327",
            }

        def fake_up_down(_trade_date):
            calls["up_down"] += 1
            return {
                "up_down_ratio": {"up": 3200, "down": 1200},
                "data_trade_date": "20260327",
            }

        monkeypatch.setattr(service.client, "get_index_quote_with_meta", fake_index)
        monkeypatch.setattr(service.client, "get_limit_stats_with_meta", fake_limit)
        monkeypatch.setattr(service.client, "get_market_turnover_with_meta", fake_turnover)
        monkeypatch.setattr(service.client, "get_up_down_ratio_with_meta", fake_up_down)

        first = service.get_current_env("2026-03-29")
        second = service.get_current_env("2026-03-29")

        assert first.trade_date == "2026-03-27"
        assert second.trade_date == "2026-03-27"
        assert calls == {
            "index": 1,
            "limit": 1,
            "turnover": 1,
            "up_down": 1,
        }

    def test_get_current_env_reuses_resolved_trade_date_cache(self, service, monkeypatch):
        calls = {
            "index": 0,
            "limit": 0,
            "turnover": 0,
            "up_down": 0,
        }

        monkeypatch.setattr(service.client, "now_trade_date", lambda: "2026-03-29")
        monkeypatch.setattr(service.client, "should_use_realtime_quote", lambda _trade_date: False)

        def fake_index(_trade_date):
            calls["index"] += 1
            return {
                "rows": [
                    {"change_pct": 0.5},
                    {"change_pct": 0.3},
                    {"change_pct": 0.2},
                ],
                "data_trade_date": "20260327",
            }

        def fake_limit(_trade_date):
            calls["limit"] += 1
            return {
                "stats": {"limit_up_count": 28, "limit_down_count": 9, "broken_board_rate": 18.0},
                "data_trade_date": "20260327",
            }

        def fake_turnover(_trade_date):
            calls["turnover"] += 1
            return {
                "market_turnover": 9800,
                "data_trade_date": "20260327",
            }

        def fake_up_down(_trade_date):
            calls["up_down"] += 1
            return {
                "up_down_ratio": {"up": 2100, "down": 1700},
                "data_trade_date": "20260327",
            }

        monkeypatch.setattr(service.client, "get_index_quote_with_meta", fake_index)
        monkeypatch.setattr(service.client, "get_limit_stats_with_meta", fake_limit)
        monkeypatch.setattr(service.client, "get_market_turnover_with_meta", fake_turnover)
        monkeypatch.setattr(service.client, "get_up_down_ratio_with_meta", fake_up_down)

        from_non_trading_day = service.get_current_env("2026-03-29")
        from_resolved_trade_day = service.get_current_env("2026-03-27")

        assert from_non_trading_day.trade_date == "2026-03-27"
        assert from_resolved_trade_day.trade_date == "2026-03-27"
        assert calls == {
            "index": 1,
            "limit": 1,
            "turnover": 1,
            "up_down": 1,
        }


class TestMarketEnvAPI:
    """市场环境 API 测试（模拟 API 响应格式）"""

    def test_api_response_format(self):
        """测试 API 响应格式"""
        from app.models.schemas import ApiResponse
        
        # 模拟 API 响应结构
        market_data = MarketEnvInput(
            trade_date="2026-03-19",
            index_sh=2.0,
            index_sz=2.2,
            index_cyb=2.5,
            up_down_ratio={"up": 3000, "down": 1200},
            limit_up_count=55,
            limit_down_count=3,
            broken_board_rate=10.0,
            market_turnover=14000,
            risk_appetite_tag="积极"
        )
        
        service = MarketEnvService()
        result = service.analyze(market_data)
        
        # 构建 API 响应数据
        api_data = {
            "trade_date": result.trade_date,
            "market_env_tag": result.market_env_tag.value,
            "breakout_allowed": result.breakout_allowed,
            "risk_level": result.risk_level.value,
            "market_comment": result.market_comment,
            "index_score": result.index_score,
            "sentiment_score": result.sentiment_score,
            "overall_score": result.overall_score
        }
        
        # 验证必要字段
        assert "trade_date" in api_data
        assert "market_env_tag" in api_data
        assert "breakout_allowed" in api_data
        assert "risk_level" in api_data
        assert "market_comment" in api_data
        assert "index_score" in api_data
        assert "sentiment_score" in api_data
        assert "overall_score" in api_data
        
        # 验证字段类型
        assert isinstance(api_data["trade_date"], str)
        assert api_data["market_env_tag"] in ["进攻", "中性", "防守"]
        assert isinstance(api_data["breakout_allowed"], bool)
        assert api_data["risk_level"] in ["低", "中", "高"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
