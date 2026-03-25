"""
个股体检 API 测试
"""
# flake8: noqa: E501
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1 import stock  # noqa: E402
from app.models.schemas import (  # noqa: E402
    LlmCallStatus,
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
        return sample

    monkeypatch.setattr(stock.stock_checkup_service, "checkup", fake_checkup)

    response = await stock.get_stock_checkup(
        "002463.SZ",
        trade_date="2026-03-23",
        checkup_target=StockCheckupTarget.OBSERVE,
        force_llm_refresh=False,
    )

    assert response.code == 200
    assert response.data["trade_date"] == "2026-03-23"
    assert response.data["rule_snapshot"]["basic_info"]["stock_name"] == "沪电股份"
    assert response.data["llm_status"]["status"] == "disabled"
