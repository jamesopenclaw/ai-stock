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
        account_context,
        exposure,
        SimpleNamespace(buy_point_level="A"),
        SimpleNamespace(conclusion="买"),
        SimpleNamespace(below_no_buy="17.80"),
    )

    assert "已有同板块持仓" in account_context.account_conclusion
    assert advice.suggestion == "轻仓试错"
    assert "已有同板块持仓" in advice.reason


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
