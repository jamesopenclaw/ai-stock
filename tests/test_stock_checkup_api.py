"""
个股体检 API 测试
"""
# flake8: noqa: E501
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.core.security import AuthenticatedAccount  # noqa: E402
from app.models.schemas import (  # noqa: E402
    LlmCallStatus,
    StockPatternAnalysisResponse,
    StockPatternAnnotation,
    StockPatternBasicInfo,
    StockPatternCandle,
    StockPatternChartPayload,
    StockPatternFeatureSnapshot,
    StockPatternResult,
    StockCheckupLlmOverlay,
    StockCheckupLlmRequest,
    StockCheckupBasicInfo,
    StockCheckupDailyStructure,
    StockCheckupDirectionPosition,
    StockCheckupFinalConclusion,
    StockCheckupFundQuality,
    StockCheckupIntradayStrength,
    StockCheckupKeyLevels,
    StockCheckupMarketContext,
    StockCheckupPeerComparison,
    StockCheckupResponse,
    StockCheckupRuleSnapshot,
    StockCheckupStrategy,
    StockCheckupTarget,
    StockCheckupValuationProfile,
)


@pytest.mark.asyncio
async def test_get_stock_checkup_returns_response(monkeypatch):
    sample = StockCheckupResponse(
        trade_date="2026-03-23",
        resolved_trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        stock_found_in_candidates=True,
        rule_snapshot=StockCheckupRuleSnapshot(
            basic_info=StockCheckupBasicInfo(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                sector_name="元器件",
                board="主板",
                special_tags=["主板"],
            ),
            market_context=StockCheckupMarketContext(market_env_tag="进攻"),
            direction_position=StockCheckupDirectionPosition(),
            daily_structure=StockCheckupDailyStructure(),
            intraday_strength=StockCheckupIntradayStrength(),
            fund_quality=StockCheckupFundQuality(),
            peer_comparison=StockCheckupPeerComparison(),
            valuation_profile=StockCheckupValuationProfile(),
            key_levels=StockCheckupKeyLevels(),
            strategy=StockCheckupStrategy(current_strategy="观察"),
            final_conclusion=StockCheckupFinalConclusion(one_line_conclusion="先看不急做。"),
        ),
        llm_report=None,
        llm_status=LlmCallStatus(enabled=False, success=False, status="disabled", message="未启用"),
    )

    async def fake_checkup(*args, **kwargs):
        assert kwargs.get("include_llm", True) is True
        return sample

    monkeypatch.setattr(stock.stock_checkup_service, "checkup", fake_checkup)

    response = await stock.get_stock_checkup(
        "002463.SZ",
        trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        force_llm_refresh=False,
        include_llm=True,
    )

    assert response.code == 200
    assert response.data["trade_date"] == "2026-03-23"
    assert response.data["rule_snapshot"]["basic_info"]["stock_name"] == "沪电股份"
    assert response.data["llm_status"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_get_stock_checkup_include_llm_false(monkeypatch):
    sample = StockCheckupResponse(
        trade_date="2026-03-23",
        resolved_trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        stock_found_in_candidates=True,
        rule_snapshot=StockCheckupRuleSnapshot(
            basic_info=StockCheckupBasicInfo(
                ts_code="002463.SZ",
                stock_name="沪电股份",
                sector_name="元器件",
                board="主板",
                special_tags=["主板"],
            ),
            market_context=StockCheckupMarketContext(market_env_tag="进攻"),
            direction_position=StockCheckupDirectionPosition(),
            daily_structure=StockCheckupDailyStructure(),
            intraday_strength=StockCheckupIntradayStrength(),
            fund_quality=StockCheckupFundQuality(),
            peer_comparison=StockCheckupPeerComparison(),
            valuation_profile=StockCheckupValuationProfile(),
            key_levels=StockCheckupKeyLevels(),
            strategy=StockCheckupStrategy(current_strategy="观察"),
            final_conclusion=StockCheckupFinalConclusion(one_line_conclusion="先看不急做。"),
        ),
        llm_report=None,
        llm_status=LlmCallStatus(
            enabled=True,
            success=False,
            status="pending",
            message="规则已就绪，LLM 解读异步加载中",
        ),
    )

    async def fake_checkup(*args, **kwargs):
        assert kwargs.get("include_llm") is False
        return sample

    monkeypatch.setattr(stock.stock_checkup_service, "checkup", fake_checkup)

    response = await stock.get_stock_checkup(
        "002463.SZ",
        trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        force_llm_refresh=False,
        include_llm=False,
        current_account=AuthenticatedAccount(
            id="acct-1",
            account_code="T1",
            account_name="测试账户",
        ),
    )

    assert response.code == 200
    assert response.data["llm_status"]["status"] == "pending"


@pytest.mark.asyncio
async def test_post_stock_checkup_llm_returns_overlay(monkeypatch):
    rule_snapshot = StockCheckupRuleSnapshot(
        basic_info=StockCheckupBasicInfo(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            board="主板",
            special_tags=["主板"],
        ),
        market_context=StockCheckupMarketContext(market_env_tag="进攻"),
        direction_position=StockCheckupDirectionPosition(),
        daily_structure=StockCheckupDailyStructure(),
        intraday_strength=StockCheckupIntradayStrength(),
        fund_quality=StockCheckupFundQuality(),
        peer_comparison=StockCheckupPeerComparison(),
        valuation_profile=StockCheckupValuationProfile(),
        key_levels=StockCheckupKeyLevels(),
        strategy=StockCheckupStrategy(current_strategy="观察"),
        final_conclusion=StockCheckupFinalConclusion(one_line_conclusion="先看不急做。"),
    )

    overlay = StockCheckupLlmOverlay(
        llm_report=None,
        llm_status=LlmCallStatus(
            enabled=True,
            success=True,
            status="success",
            message="LLM 解释增强已生效",
        ),
    )

    async def fake_overlay(*args, **kwargs):
        assert kwargs.get("force_llm_refresh") is True
        return overlay

    monkeypatch.setattr(stock.stock_checkup_service, "checkup_llm_overlay", fake_overlay)

    req = StockCheckupLlmRequest(
        rule_snapshot=rule_snapshot,
        trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        force_llm_refresh=True,
    )
    response = await stock.post_stock_checkup_llm(
        req,
        current_account=AuthenticatedAccount(
            id="acct-1",
            account_code="T1",
            account_name="测试账户",
        ),
    )

    assert response.code == 200
    assert response.data["llm_status"]["status"] == "success"


@pytest.mark.asyncio
async def test_get_stock_pattern_analysis_returns_response(monkeypatch):
    sample = StockPatternAnalysisResponse(
        trade_date="2026-04-14",
        resolved_trade_date="2026-04-14",
        basic_info=StockPatternBasicInfo(
            ts_code="002463.SZ",
            stock_name="沪电股份",
            sector_name="元器件",
            board="主板",
            trade_date="2026-04-14",
            resolved_trade_date="2026-04-14",
        ),
        feature_snapshot=StockPatternFeatureSnapshot(
            history_window=100,
            sufficient_history=True,
            ma_alignment="多头排列",
        ),
        chart_payload=StockPatternChartPayload(
            candles=[
                StockPatternCandle(
                    trade_date="2026-04-14",
                    open=10.0,
                    high=10.3,
                    low=9.9,
                    close=10.2,
                    volume=123456,
                )
            ],
            moving_averages={"ma5": [None], "ma10": [None]},
        ),
        pattern_analysis=StockPatternResult(
            primary_pattern="平台突破临界",
            confidence="中",
            pattern_phase="临近突破",
            pattern_summary="先看平台上沿是否有效突破。",
            breakout_level=10.28,
            defense_level=9.98,
            key_annotations=[
                StockPatternAnnotation(price=10.28, label="突破线", annotation_type="breakout"),
            ],
        ),
        llm_status=LlmCallStatus(enabled=False, success=False, status="disabled", message="未启用"),
    )

    async def fake_analyze(*args, **kwargs):
        return sample

    monkeypatch.setattr(stock.pattern_analysis_service, "analyze", fake_analyze)

    response = await stock.get_stock_pattern_analysis(
        "002463.SZ",
        trade_date="2026-04-14",
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["basic_info"]["stock_name"] == "沪电股份"
    assert response.data["pattern_analysis"]["primary_pattern"] == "平台突破临界"
    assert response.data["llm_status"]["status"] == "disabled"
