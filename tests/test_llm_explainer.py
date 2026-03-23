"""
LLM 解释增强测试
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (
    LlmPoolsSummary,
    LlmSellSummary,
    MarketEnvTag,
    SellPointOutput,
    SellPointResponse,
    SellPointType,
    SellPriority,
    SellSignalTag,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockPoolsOutput,
    StockStrengthTag,
    StockTradeabilityTag,
)
from app.services.llm_explainer import LlmExplainerService


class TestLlmExplainer:
    @pytest.fixture
    def service(self):
        return LlmExplainerService()

    @pytest.fixture
    def sample_stock_pools(self):
        stock = StockOutput(
            ts_code="000539.SZ",
            stock_name="粤电力A",
            sector_name="电力",
            change_pct=4.5,
            close=6.06,
            stock_score=88.0,
            candidate_source_tag="涨幅前列",
            candidate_bucket_tag="趋势回踩",
            stock_strength_tag=StockStrengthTag.MEDIUM,
            stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
            stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
            stock_core_tag=StockCoreTag.CORE,
            stock_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE,
            stock_comment="强势回踩，可继续观察承接",
            stock_falsification_cond="跌破支撑位则结构转弱",
        )
        return StockPoolsOutput(
            trade_date="2026-03-20",
            market_watch_pool=[],
            account_executable_pool=[stock],
            holding_process_pool=[],
            total_count=1,
        )

    @pytest.fixture
    def sample_sell_response(self):
        point = SellPointOutput(
            ts_code="601012.SH",
            stock_name="隆基绿能",
            market_price=18.99,
            cost_price=18.49,
            pnl_pct=2.7,
            holding_qty=800,
            holding_days=3,
            can_sell_today=True,
            sell_signal_tag=SellSignalTag.REDUCE,
            sell_point_type=SellPointType.REDUCE_POSITION,
            sell_trigger_cond="冲高不能放量续强时减仓",
            sell_reason="市场偏弱，这只票所在板块也不强，先落一部分利润",
            sell_priority=SellPriority.MEDIUM,
            sell_comment="先把仓位降下来，等更清晰的信号",
        )
        return SellPointResponse(
            trade_date="2026-03-20",
            hold_positions=[],
            reduce_positions=[point],
            sell_positions=[],
            total_count=1,
        )

    def test_apply_pool_summary_only_adds_human_notes(self, service, sample_stock_pools):
        summary = LlmPoolsSummary.model_validate(
            {
                "page_summary": "今天先看账户可参与池。",
                "top_focus_summary": "这只票可以继续盯，但别把可参与当成直接追价。",
                "pool_empty_reason": "",
                "stock_notes": [
                    {
                        "ts_code": "000539.SZ",
                        "plain_note": "这只票通过了账户准入，但还要等买点确认。",
                        "risk_note": "如果承接转弱，就不要勉强试错。",
                    }
                ],
            }
        )

        service.apply_pool_summary(sample_stock_pools, summary)
        stock = sample_stock_pools.account_executable_pool[0]

        assert stock.llm_plain_note == "这只票通过了账户准入，但还要等买点确认。"
        assert stock.llm_risk_note == "如果承接转弱，就不要勉强试错。"
        assert stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE
        assert stock.stock_tradeability_tag == StockTradeabilityTag.TRADABLE

    def test_apply_sell_summary_only_adds_human_notes(self, service, sample_sell_response):
        summary = LlmSellSummary.model_validate(
            {
                "page_summary": "先处理需要减仓的持仓。",
                "action_summary": "先把风险降下来，再看结构是否修复。",
                "notes": [
                    {
                        "ts_code": "601012.SH",
                        "action_sentence": "先减一部分，把仓位降下来。",
                        "trigger_sentence": "盘中冲高但量跟不上时就动手。",
                        "risk_sentence": "如果继续拖着不动，弱市里回撤会放大。",
                    }
                ],
            }
        )

        service.apply_sell_summary(sample_sell_response, summary)
        point = sample_sell_response.reduce_positions[0]

        assert point.llm_action_sentence == "先减一部分，把仓位降下来。"
        assert point.llm_trigger_sentence == "盘中冲高但量跟不上时就动手。"
        assert point.llm_risk_sentence == "如果继续拖着不动，弱市里回撤会放大。"
        assert point.sell_signal_tag == SellSignalTag.REDUCE
        assert point.sell_priority == SellPriority.MEDIUM

    def test_summarize_stock_pools_returns_none_when_llm_disabled(self, service, sample_stock_pools):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        result = asyncio.run(service.summarize_stock_pools(sample_stock_pools, MockMarketEnv()))
        assert result is None

    def test_summarize_stock_pools_returns_disabled_status_when_llm_disabled(self, service, sample_stock_pools):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        summary, status = asyncio.run(service.summarize_stock_pools_with_status(sample_stock_pools, MockMarketEnv()))
        assert summary is None
        assert status.enabled is False
        assert status.success is False
        assert status.status == "disabled"
