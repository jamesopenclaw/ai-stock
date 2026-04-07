"""
单股买点 SOP 服务测试
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    BuyPointType,
    BuySignalTag,
    MarketEnvOutput,
    MarketEnvTag,
    NextTradeabilityTag,
    RiskLevel,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockPoolTag,
    StockStrengthTag,
    StockTradeabilityTag,
    StructureStateTag,
    StockPoolsOutput,
)
from app.services.buy_point_sop import buy_point_sop_service  # noqa: E402


def _sample_scored_stock(pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE):
    return StockOutput(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        change_pct=4.8,
        close=28.1,
        open=27.6,
        high=28.3,
        low=27.5,
        pre_close=26.81,
        vol_ratio=1.8,
        turnover_rate=7.4,
        stock_score=92.0,
        candidate_source_tag="买点分析",
        candidate_bucket_tag="趋势回踩",
        stock_strength_tag=StockStrengthTag.STRONG,
        stock_continuity_tag=StockContinuityTag.SUSTAINABLE,
        stock_tradeability_tag=StockTradeabilityTag.TRADABLE,
        stock_core_tag=StockCoreTag.CORE,
        stock_pool_tag=pool_tag,
        structure_state_tag=StructureStateTag.START,
        next_tradeability_tag=NextTradeabilityTag.RETRACE_CONFIRM,
        stock_falsification_cond="跌破MA10",
        stock_comment="趋势结构完整",
    )


def _history_rows():
    rows = []
    base = 23.0
    for idx in range(25):
        close = base + idx * 0.18
        rows.append(
            {
                "close": round(close, 2),
                "high": round(close + 0.45, 2),
                "low": round(close - 0.35, 2),
            }
        )
    return rows


def _history_rows_with_higher_pressure():
    rows = _history_rows()
    for row in rows[-20:]:
        row["high"] = round(row["high"] + 1.6, 2)
    return rows


def _zone_low(zone: str) -> float:
    return float(zone.split("-")[0])


def _zone_high(zone: str) -> float:
    return float(zone.split("-")[1])


@pytest.mark.asyncio
async def test_buy_point_sop_service_returns_structured_buy_plan(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=82,
        sentiment_score=84,
        overall_score=83,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=28.1,
        open=27.6,
        high=28.3,
        low=27.5,
        pre_close=26.81,
        change_pct=4.8,
        turnover_rate=7.4,
        amount=180000,
        avg_price=27.85,
        intraday_volume_ratio=2.4,
        vol_ratio=1.8,
        quote_time="2026-03-23 10:36:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock()
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        account_executable_pool=[scored_stock],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows_with_higher_pressure(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.CAN_BUY,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩 MA5 一带企稳再看",
            buy_confirm_cond="缩量回踩，二次放量拉起",
            buy_invalid_cond="跌破 MA10 则放弃",
            buy_invalid_price=27.2,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.basic_info.stock_name == "沪电股份"
    assert result.account_context.account_conclusion == "轻仓新开仓，可试错"
    assert result.daily_judgement.buy_point_level == "A"
    assert "站均价线上" in result.intraday_judgement.price_vs_avg_line
    assert result.intraday_judgement.volume_quality == "实时放量跟随（相对放量 2.4）"
    assert result.intraday_judgement.conclusion == "买"
    assert result.order_plan.low_absorb_price == "27.45-27.66"
    assert result.order_plan.breakout_price == "28.31-28.45"
    assert result.order_plan.retrace_confirm_price == "28.06-28.28"
    assert result.order_plan.give_up_price == "28.88"
    assert "放量过 28.31-28.45 并站稳再考虑" in result.order_plan.trigger_condition
    assert result.order_plan.invalid_condition.startswith("跌破 27.20 且无法快速收回")
    assert result.position_advice.suggestion == "中仓参与"
    assert result.position_advice.recommended_position_pct == 0.3
    assert result.position_advice.recommended_order_pct == 0.3
    assert result.position_advice.recommended_shares == 1000
    assert result.position_advice.recommended_lots == 10
    assert result.position_advice.recommended_order_amount == 28100.0
    assert result.execution.action == "买"


@pytest.mark.asyncio
async def test_buy_point_sop_service_marks_add_position_context(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=55,
        sentiment_score=56,
        overall_score=55.5,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=27.2,
        open=27.3,
        high=27.8,
        low=26.9,
        pre_close=27.0,
        change_pct=0.74,
        turnover_rate=6.1,
        amount=120000,
        avg_price=27.05,
        vol_ratio=0.9,
        quote_time=None,
        data_source="daily",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[{"ts_code": "002463.SZ"}],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=35000,
            total_position_ratio=0.55,
            holding_count=3,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock(pool_tag=StockPoolTag.HOLDING_PROCESS)
    scored_stock.change_pct = 0.74
    scored_stock.close = 27.2
    scored_stock.open = 27.3
    scored_stock.high = 27.8
    scored_stock.low = 26.9
    scored_stock.stock_pool_tag = StockPoolTag.HOLDING_PROCESS
    scored_stock.structure_state_tag = StructureStateTag.REPAIR
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        holding_process_pool=[scored_stock],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.OBSERVE,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="先看回踩后能否企稳",
            buy_confirm_cond="重新放量站回均线",
            buy_invalid_cond="跌破前低放弃加仓",
            buy_invalid_price=26.5,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.account_context.current_use == "加仓"
    assert "同一只股票持仓" in result.account_context.same_direction_exposure
    assert result.account_context.account_conclusion == "已有同一只股票持仓，只能按加仓语境处理"
    assert result.intraday_judgement.conclusion == "等确认"
    assert result.order_plan.low_absorb_price == "26.91-27.07"
    assert result.order_plan.breakout_price == "27.73-27.89"
    assert result.order_plan.give_up_price == "27.87"
    assert result.order_plan.below_no_buy == "26.50"
    assert "先看回踩后能否企稳" in result.order_plan.trigger_condition


@pytest.mark.asyncio
async def test_buy_point_sop_service_builds_positive_add_position_decision(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=80,
        sentiment_score=83,
        overall_score=81.5,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=28.1,
        open=27.7,
        high=28.35,
        low=27.6,
        pre_close=27.3,
        change_pct=2.93,
        turnover_rate=6.8,
        amount=160000,
        avg_price=27.92,
        intraday_volume_ratio=1.9,
        vol_ratio=1.7,
        quote_time="2026-03-23 10:35:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[
            {
                "ts_code": "002463.SZ",
                "holding_qty": 200,
                "cost_price": 26.8,
                "market_price": 28.1,
                "pnl_pct": 4.85,
                "holding_market_value": 5620,
            }
        ],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=70000,
            total_position_ratio=0.28,
            holding_count=2,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock(pool_tag=StockPoolTag.HOLDING_PROCESS)
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        holding_process_pool=[scored_stock],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows_with_higher_pressure(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.CAN_BUY,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩确认后再加",
            buy_confirm_cond="承接后放量再起",
            buy_invalid_cond="跌破 MA10 放弃",
            buy_invalid_price=27.2,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.account_context.current_use == "加仓"
    assert result.add_position_decision is not None
    assert result.add_position_decision.decision == "可加"
    assert result.add_position_decision.score_total >= 8
    assert result.position_advice.suggestion == "标准加仓"
    assert result.position_advice.increment_position_pct == 0.2
    assert result.position_advice.recommended_position_pct == 0.2562
    assert result.position_advice.recommended_order_pct == 0.2
    assert result.position_advice.recommended_shares == 700
    assert result.position_advice.recommended_lots == 7
    assert result.position_advice.recommended_order_amount == 19670.0
    assert result.position_advice.exit_priority == "先撤新增仓"
    assert result.execution.action == "加"


@pytest.mark.asyncio
async def test_buy_point_sop_service_blocks_losing_add_position(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-23",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=55,
        sentiment_score=56,
        overall_score=55.5,
    )
    target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=27.2,
        open=27.0,
        high=27.5,
        low=26.9,
        pre_close=27.3,
        change_pct=-0.37,
        turnover_rate=5.0,
        amount=100000,
        avg_price=27.08,
        intraday_volume_ratio=1.2,
        vol_ratio=1.1,
        quote_time="2026-03-23 10:35:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-03-23",
        resolved_stock_trade_date="2026-03-23",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[
            {
                "ts_code": "002463.SZ",
                "holding_qty": 200,
                "cost_price": 28.0,
                "market_price": 27.2,
                "pnl_pct": -2.86,
                "holding_market_value": 5440,
            }
        ],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=50000,
            total_position_ratio=0.45,
            holding_count=2,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock(pool_tag=StockPoolTag.HOLDING_PROCESS)
    scored_stock.change_pct = -0.37
    scored_stock.close = 27.2
    pools = StockPoolsOutput(
        trade_date="2026-03-23",
        holding_process_pool=[scored_stock],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-23"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.OBSERVE,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="先观察",
            buy_confirm_cond="重新转强再说",
            buy_invalid_cond="跌破就放弃",
            buy_invalid_price=26.5,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-23")

    assert result.add_position_decision is not None
    assert result.add_position_decision.decision == "不加"
    assert any("亏损" in item for item in result.add_position_decision.blockers)
    assert result.position_advice.suggestion == "继续持有"
    assert result.execution.action == "不加"


def test_buy_point_sop_account_context_blocks_breakthrough_when_weak_holding_pending():
    account = SimpleNamespace(
        total_asset=100000,
        available_cash=78000,
        total_position_ratio=0.22,
        holding_count=1,
        today_new_buy_count=0,
    )
    market_env = SimpleNamespace(market_env_tag=MarketEnvTag.ATTACK)
    target_stock = _sample_scored_stock()
    target_stock.sector_name = "芯片"
    target_stock.next_tradeability_tag = NextTradeabilityTag.BREAKTHROUGH
    exposure = buy_point_sop_service._build_direction_exposure(
        "002463.SZ",
        "芯片",
        [{"ts_code": "000001.SZ", "sector_name": "银行"}],
        "2026-03-23",
    )

    account_context = buy_point_sop_service._build_account_context(
        account,
        market_env,
        exposure,
        target_stock,
        "002463.SZ",
        [
            {
                "ts_code": "000001.SZ",
                "stock_name": "弱票",
                "sector_name": "银行",
                "holding_market_value": 12000,
                "pnl_pct": -5.2,
                "can_sell_today": True,
            }
        ],
    )
    advice = buy_point_sop_service._build_position_advice(
        account,
        market_env,
        SimpleNamespace(close=28.1),
        account_context,
        exposure,
        SimpleNamespace(buy_point_level="A"),
        SimpleNamespace(conclusion="买"),
        SimpleNamespace(below_no_buy="27.20"),
    )

    assert "先处理旧仓" in account_context.account_conclusion
    assert advice.suggestion == "不出手"
    assert "先处理旧仓" in advice.reason


def test_buy_point_sop_account_context_warns_same_sector_exposure_for_new_position():
    account = SimpleNamespace(
        total_asset=100000,
        available_cash=80000,
        total_position_ratio=0.2,
        holding_count=1,
        today_new_buy_count=0,
    )
    market_env = SimpleNamespace(market_env_tag=MarketEnvTag.ATTACK)
    target_stock = _sample_scored_stock()
    target_stock.sector_name = "算力"
    target_stock.next_tradeability_tag = NextTradeabilityTag.RETRACE_CONFIRM
    exposure = buy_point_sop_service._build_direction_exposure(
        "002463.SZ",
        "算力",
        [{"ts_code": "300010.SZ", "sector_name": "算力"}],
        "2026-03-23",
    )

    account_context = buy_point_sop_service._build_account_context(
        account,
        market_env,
        exposure,
        target_stock,
        "002463.SZ",
        [
            {
                "ts_code": "300010.SZ",
                "stock_name": "算力先手仓",
                "sector_name": "算力",
                "holding_market_value": 15000,
                "pnl_pct": 2.3,
                "can_sell_today": True,
            }
        ],
    )
    advice = buy_point_sop_service._build_position_advice(
        account,
        market_env,
        SimpleNamespace(close=18.2),
        account_context,
        exposure,
        SimpleNamespace(buy_point_level="A"),
        SimpleNamespace(conclusion="买"),
        SimpleNamespace(below_no_buy="17.80"),
    )

    assert "已有同板块持仓" in account_context.account_conclusion
    assert advice.suggestion == "轻仓试错"
    assert "已有同板块持仓" in advice.reason


def test_buy_point_sop_market_profile_changes_entry_size_and_guidance():
    market_env = SimpleNamespace(
        market_env_tag=MarketEnvTag.NEUTRAL,
        market_env_profile="中性偏谨慎",
    )

    suitability = buy_point_sop_service._market_suitability(
        market_env.market_env_tag,
        market_env.market_env_profile,
    )
    position_pct = buy_point_sop_service._resolve_entry_position_pct("轻仓试错", market_env)
    market_state = buy_point_sop_service._resolve_market_state(
        market_env.market_env_tag,
        market_env.market_env_profile,
    )

    assert "低吸和回踩确认" in suitability
    assert position_pct == 0.12
    assert market_state == "谨慎分化市"


def test_buy_point_sop_breakout_price_stays_above_low_absorb():
    target_input = SimpleNamespace(
        close=7.38,
        high=7.40,
        low=7.35,
        vol_ratio=1.1,
    )
    levels = buy_point_sop_service._build_daily_levels(
        SimpleNamespace(high=7.40, low=7.35),
        [
            {"close": 6.80, "high": 7.00, "low": 6.60},
            {"close": 6.90, "high": 7.04, "low": 6.70},
            {"close": 7.10, "high": 7.12, "low": 6.95},
            {"close": 7.22, "high": 7.24, "low": 7.05},
            {"close": 7.30, "high": 7.32, "low": 7.18},
            {"close": 7.34, "high": 7.36, "low": 7.24},
            {"close": 7.36, "high": 7.38, "low": 7.28},
            {"close": 7.38, "high": 7.40, "low": 7.35},
            {"close": 7.37, "high": 7.39, "low": 7.31},
            {"close": 7.38, "high": 7.40, "low": 7.34},
        ],
    )
    stock = _sample_scored_stock()
    stock.close = 7.38
    stock.high = 7.40
    stock.low = 7.35
    stock.change_pct = 2.1
    plan = buy_point_sop_service._build_order_plan(
        target_input,
        stock,
        SimpleNamespace(
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩承接",
            buy_invalid_cond="跌破支撑放弃",
            buy_invalid_price=7.20,
        ),
        SimpleNamespace(market_env_tag=MarketEnvTag.NEUTRAL),
        SimpleNamespace(
            position_status="轻仓（仓位 20%）",
            same_direction_exposure="暂无明显同方向重复暴露。",
            current_use="新开仓",
        ),
        SimpleNamespace(buy_point_level="B"),
        SimpleNamespace(intraday_structure="回踩承接"),
        levels,
    )

    assert _zone_low(plan.breakout_price) > _zone_low(plan.low_absorb_price)


def test_buy_point_sop_retrace_confirm_ref_does_not_use_far_below_spot_anchor():
    target_input = SimpleNamespace(
        close=127.0,
        high=127.8,
        low=121.5,
        vol_ratio=3.9,
    )
    stock = _sample_scored_stock()
    stock.close = 127.0
    stock.high = 127.8
    stock.low = 121.5
    stock.change_pct = 6.7
    plan = buy_point_sop_service._build_order_plan(
        target_input,
        stock,
        SimpleNamespace(
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩承接再看",
            buy_invalid_cond="跌破支撑放弃",
            buy_invalid_price=98.01,
        ),
        SimpleNamespace(market_env_tag=MarketEnvTag.DEFENSE),
        SimpleNamespace(
            position_status="轻仓（仓位 9%）",
            same_direction_exposure="暂无明显同方向重复暴露。",
            current_use="新开仓",
            account_conclusion="轻仓新开仓，可试错",
        ),
        SimpleNamespace(buy_point_level="C"),
        SimpleNamespace(intraday_structure="回踩承接"),
        SimpleNamespace(
            ma5=121.2,
            ma10=118.4,
            ma20=110.6,
            prev_high=104.5,
            prev_low=101.3,
            range_high_20d=104.5,
            range_low_20d=86.2,
        ),
    )

    assert _zone_low(plan.low_absorb_price) > 120
    assert _zone_low(plan.retrace_confirm_price) > 120
    assert _zone_high(plan.retrace_confirm_price) < 123


def test_buy_point_sop_retrace_floor_ratio_is_board_aware():
    assert buy_point_sop_service._retrace_reference_floor_ratio("002463.SZ") == 0.93
    assert buy_point_sop_service._retrace_reference_floor_ratio("301408.SZ") == 0.88
    assert buy_point_sop_service._retrace_reference_floor_ratio("688521.SH") == 0.88
    assert buy_point_sop_service._retrace_reference_floor_ratio("830001.BJ") == 0.82


def test_buy_point_sop_chinext_allows_wider_retrace_before_downgrade():
    assert buy_point_sop_service._normalize_retrace_confirm_ref(
        19.66,
        "301408.SZ",
        "回踩承接",
        17.52,
        18.04,
    ) == 17.52


def test_buy_point_sop_main_board_downgrades_same_retrace_distance():
    assert buy_point_sop_service._normalize_retrace_confirm_ref(
        19.66,
        "002408.SZ",
        "回踩承接",
        17.52,
        18.04,
    ) == 18.04


def test_buy_point_sop_retrace_confirm_zone_stays_above_invalid_line():
    target_input = SimpleNamespace(
        close=18.12,
        open=17.84,
        high=18.36,
        low=17.72,
        vol_ratio=1.1,
    )
    stock = _sample_scored_stock()
    stock.close = 18.12
    stock.open = 17.84
    stock.high = 18.36
    stock.low = 17.72
    stock.change_pct = 3.6

    plan = buy_point_sop_service._build_order_plan(
        target_input,
        stock,
        SimpleNamespace(
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩承接再看",
            buy_invalid_cond="跌破支撑放弃",
            buy_invalid_price=17.48,
        ),
        SimpleNamespace(market_env_tag=MarketEnvTag.DEFENSE),
        SimpleNamespace(
            position_status="轻仓（仓位 13%）",
            same_direction_exposure="暂无明显同方向重复暴露。",
            current_use="新开仓",
            account_conclusion="轻仓新开仓，可试错",
        ),
        SimpleNamespace(buy_point_level="C"),
        SimpleNamespace(intraday_structure="回踩承接"),
        SimpleNamespace(
            ma5=17.78,
            ma10=17.55,
            ma20=17.26,
            prev_high=17.05,
            prev_low=16.96,
            range_high_20d=17.05,
            range_low_20d=16.12,
        ),
    )

    assert _zone_low(plan.low_absorb_price) > float(plan.below_no_buy)
    assert _zone_low(plan.retrace_confirm_price) > float(plan.below_no_buy)
    assert _zone_low(plan.retrace_confirm_price) > 17.70


@pytest.mark.asyncio
async def test_buy_point_sop_prefers_realtime_single_stock_input_for_intraday(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-24",
        market_env_tag=MarketEnvTag.ATTACK,
        breakout_allowed=True,
        risk_level=RiskLevel.LOW,
        market_comment="进攻环境",
        index_score=80,
        sentiment_score=82,
        overall_score=81,
    )
    context_stock = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=6.95,
        open=6.88,
        high=7.02,
        low=6.80,
        pre_close=6.73,
        change_pct=3.27,
        turnover_rate=5.2,
        amount=80000,
        vol_ratio=4.0,
        quote_time=None,
        data_source="daily",
    )
    realtime_target_input = SimpleNamespace(
        ts_code="002463.SZ",
        stock_name="沪电股份",
        sector_name="元器件",
        close=6.95,
        open=6.88,
        high=7.02,
        low=6.80,
        pre_close=6.73,
        change_pct=3.27,
        turnover_rate=5.2,
        amount=80000,
        avg_price=6.90,
        intraday_volume_ratio=2.2,
        vol_ratio=4.0,
        quote_time="2026-03-24 10:35:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-03-24",
        resolved_stock_trade_date="2026-03-21",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[context_stock],
        holdings_list=[],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock()
    scored_stock.close = 6.95
    scored_stock.open = 6.88
    scored_stock.high = 7.02
    scored_stock.low = 6.80
    scored_stock.change_pct = 3.27
    pools = StockPoolsOutput(
        trade_date="2026-03-24",
        account_executable_pool=[scored_stock],
        total_count=1,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: realtime_target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-21"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.OBSERVE,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩承接再看",
            buy_confirm_cond="承接后重新放量",
            buy_invalid_cond="跌破支撑放弃",
            buy_invalid_price=6.78,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-24")

    assert result.basic_info.quote_time == "2026-03-24 10:35:00"
    assert result.basic_info.data_source == "realtime_sina"
    assert "站均价线上" in result.intraday_judgement.price_vs_avg_line
    assert result.intraday_judgement.volume_quality == "实时放量跟随（相对放量 2.2）"
    assert "[需确认]" not in result.intraday_judgement.intraday_structure


@pytest.mark.asyncio
async def test_buy_point_sop_falls_back_when_target_input_and_scored_stock_missing(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-03-30",
        market_env_tag=MarketEnvTag.NEUTRAL,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="中性环境",
        index_score=50,
        sentiment_score=51,
        overall_score=50,
    )
    context = SimpleNamespace(
        trade_date="2026-03-30",
        resolved_stock_trade_date="2026-03-27",
        market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[],
        holdings_list=[],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.2,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )
    pools = StockPoolsOutput(
        trade_date="2026-03-30",
        total_count=0,
    )

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("context missing")),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("detail missing")),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-03-27"),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        lambda *args, **kwargs: SimpleNamespace(
            buy_signal_tag=BuySignalTag.OBSERVE,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="先看回踩承接",
            buy_confirm_cond="站稳后再看",
            buy_invalid_cond="跌破就放弃",
            buy_invalid_price=0.0,
        ),
    )

    result = await buy_point_sop_service.analyze("002463.SZ", "2026-03-30")

    assert result.basic_info.ts_code == "002463.SZ"
    assert result.basic_info.data_source == "fallback"
    assert result.basic_info.candidate_bucket_tag == ""


@pytest.mark.asyncio
async def test_buy_point_sop_prefers_source_pool_tag_from_pools_page(monkeypatch):
    market_env = MarketEnvOutput(
        trade_date="2026-04-03",
        market_env_tag=MarketEnvTag.DEFENSE,
        breakout_allowed=False,
        risk_level=RiskLevel.MEDIUM,
        market_comment="防守环境",
        index_score=42,
        sentiment_score=44,
        overall_score=43,
    )
    target_input = SimpleNamespace(
        ts_code="301172.SZ",
        stock_name="君逸数码",
        sector_name="软件服务",
        close=27.05,
        open=26.88,
        high=27.33,
        low=26.51,
        pre_close=26.84,
        change_pct=0.78,
        turnover_rate=5.3,
        amount=88000,
        avg_price=26.91,
        intraday_volume_ratio=1.4,
        vol_ratio=1.2,
        quote_time="2026-04-03 10:26:00",
        data_source="realtime_sina",
    )
    context = SimpleNamespace(
        trade_date="2026-04-03",
        resolved_stock_trade_date="2026-04-03",
        market_env=market_env,
        realtime_market_env=market_env,
        sector_scan=SimpleNamespace(),
        stocks=[target_input],
        holdings_list=[],
        holdings=[],
        account=SimpleNamespace(
            total_asset=100000,
            available_cash=80000,
            total_position_ratio=0.08,
            holding_count=1,
            today_new_buy_count=0,
        ),
    )
    scored_stock = _sample_scored_stock(pool_tag=StockPoolTag.NOT_IN_POOL)
    scored_stock.ts_code = "301172.SZ"
    scored_stock.stock_name = "君逸数码"
    pools = StockPoolsOutput(
        trade_date="2026-04-03",
        total_count=0,
    )
    captured = {}

    async def fake_build_context(*args, **kwargs):
        return context

    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_context",
        fake_build_context,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.merge_single_stock_into_context",
        lambda trade_date, stocks, ts_code, candidate_source_tag="买点分析": (stocks, True),
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.decision_context_service.build_single_stock_input",
        lambda *args, **kwargs: target_input,
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.filter_with_context",
        lambda *args, **kwargs: [scored_stock],
    )
    monkeypatch.setattr(
        "app.services.buy_point_sop.stock_filter_service.classify_pools",
        lambda *args, **kwargs: pools,
    )
    monkeypatch.setattr(
        buy_point_sop_service,
        "_load_history_payload",
        lambda *args, **kwargs: (_history_rows(), "2026-04-03"),
    )

    def fake_analyze_stock_buy_point(stock, *_args, **_kwargs):
        captured["pool_tag"] = stock.stock_pool_tag
        signal = BuySignalTag.OBSERVE if stock.stock_pool_tag == StockPoolTag.ACCOUNT_EXECUTABLE else BuySignalTag.NOT_BUY
        return SimpleNamespace(
            buy_signal_tag=signal,
            buy_point_type=BuyPointType.RETRACE_SUPPORT,
            buy_trigger_cond="回踩承接再看",
            buy_confirm_cond="承接后重新放量",
            buy_invalid_cond="跌破支撑放弃",
            buy_invalid_price=26.17,
        )

    monkeypatch.setattr(
        "app.services.buy_point_sop.buy_point_service._analyze_stock_buy_point",
        fake_analyze_stock_buy_point,
    )

    result = await buy_point_sop_service.analyze(
        "301172.SZ",
        "2026-04-03",
        preferred_pool_tag=StockPoolTag.ACCOUNT_EXECUTABLE.value,
    )

    assert captured["pool_tag"] == StockPoolTag.ACCOUNT_EXECUTABLE
    assert result.daily_judgement.buy_point_level != "D"
