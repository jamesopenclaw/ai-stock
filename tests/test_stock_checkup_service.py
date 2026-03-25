"""
个股全面体检服务测试
"""
# flake8: noqa: E501
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    LlmCallStatus,
    LlmStockCheckupReport,
    LlmStockCheckupSection,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    SellPointOutput,
    SellPointResponse,
    SellPointType,
    SellPriority,
    SellSignalTag,
    StockCheckupTarget,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockPoolsOutput,
    StockRoleTag,
    StockStrengthTag,
    StockTradeabilityTag,
    StructureStateTag,
    DayStrengthTag,
    NextTradeabilityTag,
)
from app.services.stock_checkup import stock_checkup_service  # noqa: E402


def _sample_stock(pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE):
    return StockOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        change_pct=6.2,
        close=28.5,
        open=27.8,
        high=29.1,
        low=27.4,
        pre_close=26.84,
        vol_ratio=1.9,
        turnover_rate=8.6,
        stock_score=91.0,
        candidate_source_tag="单股体检",
        candidate_bucket_tag="趋势回踩",
        stock_strength_tag=StockStrengthTag.STRONG,
        stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
        stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
        stock_core_tag=StockCoreTag.CORE,
        stock_pool_tag=pool_tag,
        sector_profile_tag="A类主线",
        stock_role_tag=StockRoleTag.FRONT,
        day_strength_tag=DayStrengthTag.TREND_STRONG,
        structure_state_tag=StructureStateTag.REPAIR,
        next_tradeability_tag=NextTradeabilityTag.RETRACE_CONFIRM,
        stock_falsification_cond="跌破20日线",
        stock_comment="强势修复，等待承接确认",
        pool_decision_summary="主线前排，修复中的趋势票",
    )


@pytest.mark.asyncio
async def test_checkup_builds_trading_response(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=80,
        sentiment_score=82,
        overall_score=81,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=28.5,
        open=27.8,
        high=29.1,
        low=27.4,
        pre_close=26.84,
        change_pct=6.2,
        turnover_rate=8.6,
        amount=180000,
        vol_ratio=1.9,
        quote_time="2026-03-23 14:35:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(
            mainline_sectors=[
                SimpleNamespace(
                    sector_name="元器件",
                    sector_mainline_tag=SimpleNamespace(value="主线"),
                    sector_continuity_tag=SimpleNamespace(value="可持续"),
                    sector_tradeability_tag=SimpleNamespace(value="可交易"),
                )
            ],
            sub_mainline_sectors=[],
            follow_sectors=[],
            trash_sectors=[],
        ),
        stocks=[target_input],
        holdings_list=[],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=70000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_stock()
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        account_executable_pool=[scored_stock],
        total_count=1,
    )
    llm_report = LlmStockCheckupReport(
        overall_summary="先看趋势修复是否继续。",
        llm_report_sections=[
            LlmStockCheckupSection(key="strategy", title="10）策略结论", content="这票更适合等承接确认。")
        ],
        key_risks=["跌破20日线"],
        one_line_conclusion="这票能看，但更适合等回踩承接。",
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.stock_checkup.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code: (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.sell_point_service.analyze",
        lambda *args, **kwargs: SellPointResponse(
            trade_date="2026-03-23",
            hold_positions=[],
            reduce_positions=[],
            sell_positions=[],
            total_count=0,
        ),
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.attach_sell_analysis",
        lambda stock_pools, sell_analysis: stock_pools,
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=SimpleNamespace(value="可买"),
            buy_point_type=SimpleNamespace(value="回踩承接"),
            buy_trigger_cond="回踩承接再看",
            buy_confirm_cond="量能确认",
            buy_invalid_cond="跌破支撑",
            buy_comment="适合等回踩承接",
        ),
    )
    monkeypatch.setattr(
        stock_checkup_service,
        "_load_history_payload",
        lambda *args, **kwargs: (
            [
                {"close": 25.0, "high": 25.5, "low": 24.8},
                {"close": 26.0, "high": 26.3, "low": 25.7},
                {"close": 27.2, "high": 27.6, "low": 26.8},
                {"close": 28.5, "high": 29.1, "low": 27.4},
            ]
            * 20,
            {"pe_ttm": 35.0, "pb": 4.2, "ps_ttm": 3.5, "total_mv": 3200000},
            "2026-03-23",
        ),
    )

    async def fake_llm(*args, **kwargs):
        return llm_report, LlmCallStatus(enabled=True, success=True, status="success", message="ok")

    monkeypatch.setattr(
        "app.services.stock_checkup.llm_explainer_service.explain_stock_checkup_with_status",
        fake_llm,
    )

    result = await stock_checkup_service.checkup(
        "002463.SZ",
        "2026-03-23",
        StockCheckupTarget.TRADING,
    )

    assert result.stock_found_in_candidates is True
    assert result.checkup_target == StockCheckupTarget.TRADING
    assert result.rule_snapshot.strategy.current_strategy == "观察"
    assert result.rule_snapshot.buy_view.buy_signal_tag == "可买"
    assert result.llm_report.one_line_conclusion == "这票能看，但更适合等回踩承接。"


@pytest.mark.asyncio
async def test_checkup_builds_holding_sell_view_when_stock_inserted(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.DEFENSE,
        breakout_allowed=False,
        risk_level=RiskLevel.HIGH,
        market_comment="防守环境",
        index_score=30,
        sentiment_score=28,
        overall_score=29,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=28.5,
        open=27.8,
        high=29.1,
        low=27.4,
        pre_close=26.84,
        change_pct=-2.1,
        turnover_rate=8.6,
        amount=180000,
        vol_ratio=1.1,
        quote_time=None,
        data_source="daily",
    )
    holding = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        holding_qty=1200,
        cost_price=30.2,
        market_price=28.5,
        pnl_pct=-5.63,
        holding_market_value=34200,
        buy_date="2026-03-20",
        can_sell_today=True,
        holding_reason="原逻辑失效",
        holding_days=3,
        quote_time=None,
        data_source="daily",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-20",
        market_env=market_env,
        sector_scan=SimpleNamespace(
            mainline_sectors=[],
            sub_mainline_sectors=[],
            follow_sectors=[],
            trash_sectors=[],
        ),
        stocks=[],
        holdings_list=[{"ts_code": "002463.SZ"}],
        holdings=[holding],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=50000,
            total_position_ratio=0.5,
            holding_count=2,
            today_new_buy_count=0,
        ),
    )
    holding_stock = _sample_stock(pool_tag=StockPoolTag.HOLDING_PROCESS)
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        holding_process_pool=[holding_stock],
        total_count=1,
    )
    sell_point = SellPointOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        market_price=28.5,
        cost_price=30.2,
        pnl_pct=-5.63,
        holding_qty=1200,
        holding_days=3,
        can_sell_today=True,
        sell_signal_tag=SellSignalTag.SELL,
        sell_point_type=SellPointType.STOP_LOSS,
        sell_trigger_cond="反弹无力时退出",
        sell_reason="亏损扩大，优先止损",
        sell_priority=SellPriority.HIGH,
        sell_comment="先控制风险",
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.stock_checkup.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code: ([target_input], False),
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [holding_stock],
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.sell_point_service.analyze",
        lambda *args, **kwargs: SellPointResponse(
            trade_date="2026-03-23",
            hold_positions=[],
            reduce_positions=[],
            sell_positions=[sell_point],
            total_count=1,
        ),
    )
    monkeypatch.setattr(
        "app.services.stock_checkup.stock_filter_service.attach_sell_analysis",
        lambda stock_pools, sell_analysis: stock_pools,
    )
    monkeypatch.setattr(
        stock_checkup_service,
        "_load_history_payload",
        lambda *args, **kwargs: ([], {}, "2026-03-20"),
    )

    async def fake_llm(*args, **kwargs):
        return None, LlmCallStatus(enabled=False, success=False, status="disabled", message="未启用")

    monkeypatch.setattr(
        "app.services.stock_checkup.llm_explainer_service.explain_stock_checkup_with_status",
        fake_llm,
    )

    result = await stock_checkup_service.checkup(
        "002463",
        "2026-03-23",
        StockCheckupTarget.HOLDING,
    )

    assert result.stock_found_in_candidates is False
    assert result.rule_snapshot.sell_view.sell_signal_tag == "卖出"
    assert result.rule_snapshot.strategy.current_strategy == "放弃"
    assert result.llm_report is None
    assert result.llm_status.status == "disabled"
