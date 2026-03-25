"""
单股卖点 SOP 服务测试
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    AccountPosition,
    MarketEnvOutput,
    MarketEnvTag,
    RiskLevel,
    SellPointOutput,
    SellPointResponse,
    SellPointType,
    SellPriority,
    SellSignalTag,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
    StructureStateTag,
)
from app.services.sell_point_sop import sell_point_sop_service  # noqa: E402


def _sample_holding(**overrides):
    payload = {
        "ts_code": "002463.SZ",
        "stock_name": "沪电股份",
        "holding_qty": 300,
        "cost_price": 30.0,
        "market_price": 33.2,
        "pnl_pct": 10.67,
        "holding_market_value": 9960.0,
        "buy_date": "2026-03-20",
        "can_sell_today": True,
        "holding_reason": "进攻仓，趋势延续",
        "holding_days": 3,
        "quote_time": "2026-03-23 10:32:00",
        "data_source": "realtime_sina",
    }
    payload.update(overrides)
    return AccountPosition(**payload)


def _sample_scored_stock():
    return StockOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        change_pct=3.5,
        close=33.2,
        open=32.8,
        high=33.6,
        low=32.6,
        pre_close=32.08,
        vol_ratio=1.7,
        turnover_rate=7.2,
        stock_score=90.0,
        candidate_source_tag="持仓补齐",
        candidate_bucket_tag="趋势延续",
        stock_strength_tag=StockStrengthTag.STRONG,
        stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
        stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
        stock_core_tag=StockCoreTag.CORE,
        stock_pool_tag=StockPoolTag.HOLDING_PROCESS,
        structure_state_tag=StructureStateTag.START,
        stock_falsification_cond="跌破MA10",
        stock_comment="强趋势",
    )


def _history_rows():
    rows = []
    base = 28.0
    for idx in range(25):
        close = base + idx * 0.18
        rows.append(
            {
                "close": round(close, 2),
                "high": round(close + 0.48, 2),
                "low": round(close - 0.34, 2),
            }
        )
    return rows


@pytest.mark.asyncio
async def test_sell_point_sop_service_returns_reduce_plan(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=56,
        sentiment_score=58,
        overall_score=57,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=33.2,
        open=32.8,
        high=33.6,
        low=32.6,
        pre_close=32.08,
        change_pct=3.5,
        turnover_rate=7.2,
        amount=150000,
        avg_price=33.0,
        vol_ratio=1.7,
        quote_time="2026-03-23 10:32:00",
        data_source="realtime_sina",
    )
    holding = _sample_holding()
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[holding.model_dump()],
        holdings=[holding],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=60000,
            total_position_ratio=0.4,
            holding_count=2,
            today_new_buy_count=0,
        ),
    )
    sell_point = SellPointOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        market_price=33.2,
        cost_price=30.0,
        pnl_pct=10.67,
        holding_qty=300,
        holding_days=3,
        can_sell_today=True,
        quote_time="2026-03-23 10:32:00",
        data_source="realtime_sina",
        sell_signal_tag=SellSignalTag.REDUCE,
        sell_point_type=SellPointType.REDUCE_POSITION,
        sell_trigger_cond="冲高无量时先减仓",
        sell_reason="先保护利润",
        sell_priority=SellPriority.MEDIUM,
        sell_comment="先落袋一部分",
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [_sample_scored_stock()],
    )
    monkeypatch.setattr(
        sell_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.sell_point_service.analyze",
        lambda *args, **kwargs: SellPointResponse(
            trade_date="2026-03-23",
            hold_positions=[],
            reduce_positions=[sell_point],
            sell_positions=[],
            total_count=1,
        ),
    )

    result = await sell_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.basic_info.stock_name == "沪电股份"
    assert result.account_context.pnl_status == "厚利"
    assert result.daily_judgement.sell_point_level in {"B", "C"}
    assert "站均价线上" in result.intraday_judgement.price_vs_avg_line
    assert result.intraday_judgement.conclusion == "减"
    assert result.order_plan.proactive_take_profit_price != "[当前不适用]"
    assert result.order_plan.observe_level != "[当前不适用]"
    assert result.execution.action == "减"


@pytest.mark.asyncio
async def test_sell_point_sop_service_returns_clear_plan_for_weak_loser(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.DEFENSE,
        breakout_allowed=False,
        risk_level=RiskLevel.HIGH,
        market_comment="防守环境",
        index_score=32,
        sentiment_score=30,
        overall_score=31,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=27.0,
        open=27.8,
        high=28.1,
        low=26.8,
        pre_close=28.5,
        change_pct=-5.26,
        turnover_rate=8.5,
        amount=180000,
        vol_ratio=2.1,
        quote_time=None,
        data_source="daily",
    )
    holding = _sample_holding(
        market_price=27.0,
        pnl_pct=-10.0,
        holding_market_value=8100.0,
        holding_reason="待处理仓，逻辑失效",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[holding.model_dump()],
        holdings=[holding],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=20000,
            total_position_ratio=0.8,
            holding_count=5,
            today_new_buy_count=0,
        ),
    )
    scored = _sample_scored_stock()
    scored.change_pct = -5.26
    scored.close = 27.0
    scored.open = 27.8
    scored.high = 28.1
    scored.low = 26.8
    scored.structure_state_tag = StructureStateTag.DIVERGENCE

    sell_point = SellPointOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        market_price=27.0,
        cost_price=30.0,
        pnl_pct=-10.0,
        holding_qty=300,
        holding_days=3,
        can_sell_today=True,
        sell_signal_tag=SellSignalTag.SELL,
        sell_point_type=SellPointType.STOP_LOSS,
        sell_trigger_cond="反抽无力时卖出",
        sell_reason="趋势破坏，优先退出",
        sell_priority=SellPriority.HIGH,
        sell_comment="不要继续拖",
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored],
    )
    monkeypatch.setattr(
        sell_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.sell_point_service.analyze",
        lambda *args, **kwargs: SellPointResponse(
            trade_date="2026-03-23",
            hold_positions=[],
            reduce_positions=[],
            sell_positions=[sell_point],
            total_count=1,
        ),
    )

    result = await sell_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.account_context.role == "待处理仓"
    assert result.daily_judgement.sell_point_level == "D"
    assert result.intraday_judgement.conclusion == "清"
    assert result.order_plan.rebound_sell_price != "[当前不适用]"
    assert result.order_plan.break_stop_price != "[当前不适用]"
    assert result.order_plan.observe_level == "[当前不适用]"
    assert result.execution.action == "清"


@pytest.mark.asyncio
async def test_sell_point_sop_prefers_realtime_single_stock_input_for_intraday(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=56,
        sentiment_score=58,
        overall_score=57,
    )
    context_stock = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=33.2,
        open=32.8,
        high=33.6,
        low=32.6,
        pre_close=32.08,
        change_pct=3.5,
        turnover_rate=7.2,
        amount=150000,
        vol_ratio=1.7,
        quote_time=None,
        data_source="daily",
    )
    holding = _sample_holding()
    context = SimpleNamespace(
        trade_date="2026-03-24",
        resolved_stock_trade_date="2026-03-21",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[context_stock],
        holdings_list=[holding.model_dump()],
        holdings=[holding],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=60000,
            total_position_ratio=0.4,
            holding_count=2,
            today_new_buy_count=0,
        ),
    )
    sell_point = SellPointOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        market_price=33.2,
        cost_price=30.0,
        pnl_pct=10.67,
        holding_qty=300,
        holding_days=3,
        can_sell_today=True,
        quote_time="2026-03-24 10:32:00",
        data_source="realtime_sina",
        sell_signal_tag=SellSignalTag.REDUCE,
        sell_point_type=SellPointType.REDUCE_POSITION,
        sell_trigger_cond="冲高无量时先减仓",
        sell_reason="先保护利润",
        sell_priority=SellPriority.MEDIUM,
        sell_comment="先落袋一部分",
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: SimpleNamespace(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            close=33.2,
            open=32.8,
            high=33.6,
            low=32.6,
            pre_close=32.08,
            change_pct=3.5,
            turnover_rate=7.2,
            amount=150000,
            avg_price=33.0,
            intraday_volume_ratio=1.9,
            vol_ratio=1.7,
            quote_time="2026-03-24 10:32:00",
            data_source="realtime_sina",
        ),
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [_sample_scored_stock()],
    )
    monkeypatch.setattr(
        sell_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-21"),
    )
    monkeypatch.setattr(
        "app.services.sell_point_sop.sell_point_service.analyze",
        lambda *args, **kwargs: SellPointResponse(
            trade_date="2026-03-24",
            hold_positions=[],
            reduce_positions=[sell_point],
            sell_positions=[],
            total_count=1,
        ),
    )

    result = await sell_point_sop_service.analyze("002463.SZ", "2026-03-24")

    assert "站均价线上" in result.intraday_judgement.price_vs_avg_line
    assert "相对放量 1.9" in result.intraday_judgement.volume_quality
    assert "[需确认]" not in result.intraday_judgement.intraday_structure
    assert result.basic_info.data_source == "realtime_sina"


def test_sell_point_sop_price_vs_avg_line_uses_realtime_avg():
    relation = sell_point_sop_service._resolve_price_vs_avg_line(
        SimpleNamespace(close=27.0, avg_price=27.55),
        27.0,
    )

    assert "压均价线下" in relation
