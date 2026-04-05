"""
LLM 解释增强测试
"""
# flake8: noqa: E501
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import (  # noqa: E402
    LlmPoolsSummary,
    LlmSellSummary,
    LlmStockCheckupReport,
    MarketEnvTag,
    SellPointOutput,
    SellPointResponse,
    SellPointType,
    SellPriority,
    SellSignalTag,
    StockContinuityTag,
    StockCoreTag,
    StockOutput,
    StockCheckupBasicInfo,
    StockCheckupDailyStructure,
    StockCheckupDirectionPosition,
    StockCheckupFinalConclusion,
    StockCheckupFundQuality,
    StockCheckupIntradayStrength,
    StockCheckupKeyLevels,
    StockCheckupMarketContext,
    StockCheckupPeerComparison,
    StockCheckupRuleSnapshot,
    StockCheckupStrategy,
    StockCheckupTarget,
    StockCheckupValuationProfile,
    StockPoolTag,
    StockPoolsOutput,
    StockStrengthTag,
    StockTradeabilityTag,
)
from app.services.llm_explainer import LlmExplainerService  # noqa: E402
from app.services.llm_explainer import llm_client, llm_cache_service  # noqa: E402


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

    @pytest.fixture
    def sample_checkup_snapshot(self):
        return StockCheckupRuleSnapshot(
            basic_info=StockCheckupBasicInfo(
                ts_code="000539.SZ",
                stock_name="粤电力A",
                sector_name="电力",
                board="主板",
                special_tags=["主板"],
            ),
            market_context=StockCheckupMarketContext(
                market_env_tag="进攻",
                market_phase="进攻",
                market_comment="市场偏强",
                stock_market_alignment="顺市场",
                tolerance_comment="容错率尚可",
            ),
            direction_position=StockCheckupDirectionPosition(
                direction_name="电力",
                sector_level="主线",
                stock_role="前排",
            ),
            daily_structure=StockCheckupDailyStructure(
                ma_position_summary="站上MA5，站上MA10",
                stage_position="修复",
                structure_conclusion="当前日线结构更像弱修复，仍需确认。",
            ),
            intraday_strength=StockCheckupIntradayStrength(
                change_pct=4.5,
                turnover_rate=12.3,
                vol_ratio=1.8,
                strength_level="偏强",
            ),
            fund_quality=StockCheckupFundQuality(
                recent_fund_flow="近3-5日量能偏强 [需确认]",
                cash_flow_quality="有分歧，但还能接受",
            ),
            peer_comparison=StockCheckupPeerComparison(
                relative_strength="板块内相对强",
                recognizability="具备辨识度",
            ),
            valuation_profile=StockCheckupValuationProfile(
                valuation_level="估值正常",
                drive_type="题材情绪",
            ),
            key_levels=StockCheckupKeyLevels(
                pressure_levels=[6.35],
                support_levels=[5.98],
                defense_level=5.98,
            ),
            strategy=StockCheckupStrategy(
                current_characterization="修复",
                current_role="前排",
                current_strategy="观察",
                strategy_reason="等修复确认后再决定是否参与。",
                risk_points=["跌破支撑"],
            ),
            final_conclusion=StockCheckupFinalConclusion(
                one_line_conclusion="这票能看，但不舒服追。",
            ),
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

    def test_summarize_stock_pools_uses_cache_before_calling_model(self, service, sample_stock_pools, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return {
                "page_summary": "命中缓存的三池摘要。",
                "top_focus_summary": "先看账户可参与池。",
                "pool_empty_reason": "",
                "stock_notes": [
                    {
                        "ts_code": "000539.SZ",
                        "plain_note": "缓存说明：先等买点确认。",
                        "risk_note": "缓存说明：承接转弱就放弃。",
                    }
                ],
            }

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("命中缓存后不应再调用模型")

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fail_if_called)

        summary, status = asyncio.run(service.summarize_stock_pools_with_status(sample_stock_pools, MockMarketEnv()))

        assert summary is not None
        assert summary.page_summary == "命中缓存的三池摘要。"
        assert status.success is True
        assert status.status == "cached"
        assert sample_stock_pools.account_executable_pool[0].llm_plain_note == "缓存说明：先等买点确认。"

    def test_summarize_stock_pools_normalizes_pool_empty_reason_dict(self, service, sample_stock_pools, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return None

        async def fake_cache_upsert(**kwargs):
            return None

        async def fake_chat(*args, **kwargs):
            status = type(
                "Status",
                (),
                {
                    "enabled": True,
                    "success": True,
                    "status": "fresh",
                    "message": "ok",
                },
            )()
            return (
                {
                    "page_summary": "今天以观察为主。",
                    "top_focus_summary": "先看账户可参与池。",
                    "pool_empty_reason": {
                        "market_watch_pool": "观察池样本不足。",
                        "account_executable_pool": "账户可参与条件未满足。",
                    },
                    "stock_notes": [],
                },
                status,
            )

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_cache_service, "upsert_cache", fake_cache_upsert)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fake_chat)

        summary, status = asyncio.run(service.summarize_stock_pools_with_status(sample_stock_pools, MockMarketEnv()))

        assert summary is not None
        assert "market_watch_pool: 观察池样本不足。" in summary.pool_empty_reason
        assert "account_executable_pool: 账户可参与条件未满足。" in summary.pool_empty_reason
        assert status.success is True

    def test_summarize_stock_pools_cache_miss_can_skip_live_request(self, service, sample_stock_pools, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return None

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("仅缓存模式未命中时不应发起实时模型请求")

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fail_if_called)

        summary, status = asyncio.run(
            service.summarize_stock_pools_with_status(
                sample_stock_pools,
                MockMarketEnv(),
                allow_live_request=False,
            )
        )

        assert summary is None
        assert status.enabled is True
        assert status.success is False
        assert status.status == "cache_miss"

    def test_rewrite_sell_points_force_refresh_bypasses_cache(self, service, sample_sell_response, monkeypatch):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        calls = {"model": 0, "cache_write": 0}

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return {
                "page_summary": "旧缓存摘要",
                "action_summary": "旧缓存动作",
                "notes": [
                    {
                        "ts_code": "601012.SH",
                        "action_sentence": "旧缓存动作句",
                        "trigger_sentence": "旧缓存触发句",
                        "risk_sentence": "旧缓存风险句",
                    }
                ],
            }

        async def fake_chat_json_with_status(*args, **kwargs):
            calls["model"] += 1
            return (
                {
                    "page_summary": "强制刷新后的卖点摘要",
                    "action_summary": "先减仓，再看修复。",
                    "notes": [
                        {
                            "ts_code": "601012.SH",
                            "action_sentence": "先减一部分，把仓位降下来。",
                            "trigger_sentence": "盘中冲高但量跟不上时就动手。",
                            "risk_sentence": "继续拖着不动，弱市里回撤会放大。",
                        }
                    ],
                },
                type(
                    "_Status",
                    (),
                    {
                        "enabled": True,
                        "success": True,
                        "status": "success",
                        "message": "LLM 解释增强已生效",
                    },
                )(),
            )

        async def fake_cache_upsert(**kwargs):
            calls["cache_write"] += 1

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fake_chat_json_with_status)
        monkeypatch.setattr(llm_cache_service, "upsert_cache", fake_cache_upsert)

        summary, status = asyncio.run(
            service.rewrite_sell_points_with_status(
                sample_sell_response,
                MockMarketEnv(),
                force_refresh=True,
            )
        )

        assert summary is not None
        assert summary.page_summary == "强制刷新后的卖点摘要"
        assert status.success is True
        assert calls["model"] == 1
        assert calls["cache_write"] == 1
        assert sample_sell_response.reduce_positions[0].llm_action_sentence == "先减一部分，把仓位降下来。"

    def test_sell_system_prompt_requires_sample_scope_and_t1_guardrails(self, service):
        prompt = service.SELL_SYSTEM_PROMPT

        assert "不是做简单翻译" in prompt
        assert "不是重新做投资判断" in prompt
        assert "can_sell_today=false" in prompt
        assert "今天不能卖/不能减" in prompt
        assert "partial_sample" in prompt
        assert "已提供样本" in prompt
        assert "不是 action_sentence/trigger_sentence/risk_sentence 的简单拼接" in prompt
        assert "避免多只股票只替换名称和价格" in prompt

    def test_rewrite_sell_points_payload_marks_partial_sample_and_includes_t1_flag(
        self,
        service,
        sample_sell_response,
        monkeypatch,
    ):
        class MockMarketEnv:
            market_env_tag = MarketEnvTag.DEFENSE
            market_comment = "市场偏弱"

        captured = {}

        locked_point = SellPointOutput(
            ts_code="300750.SZ",
            stock_name="宁德时代",
            market_price=201.5,
            cost_price=198.0,
            pnl_pct=1.7,
            holding_qty=100,
            holding_days=1,
            can_sell_today=False,
            sell_signal_tag=SellSignalTag.HOLD,
            sell_point_type=SellPointType.INVALID_EXIT,
            sell_trigger_cond="今日先观察，次日若走弱再处理",
            sell_reason="刚买入未过T+1，先盯次日反馈",
            sell_priority=SellPriority.LOW,
            sell_comment="今天不能动，重点看次日是否转弱",
        )
        expanded_response = SellPointResponse(
            trade_date="2026-03-20",
            hold_positions=[locked_point, locked_point.model_copy(update={"ts_code": "000001.SZ", "stock_name": "平安银行"})],
            reduce_positions=sample_sell_response.reduce_positions,
            sell_positions=[
                locked_point.model_copy(
                    update={
                        "ts_code": "600519.SH",
                        "stock_name": "贵州茅台",
                        "can_sell_today": True,
                        "sell_signal_tag": SellSignalTag.SELL,
                        "sell_point_type": SellPointType.STOP_PROFIT,
                        "sell_priority": SellPriority.HIGH,
                        "sell_reason": "冲高后承接不足，先兑现",
                        "sell_trigger_cond": "冲高回落且承接转弱时卖出",
                        "sell_comment": "别把浮盈拖回去",
                    }
                )
            ],
            total_count=4,
        )

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 3,
            }

        async def fake_cache_get(*, cache_key):
            return None

        async def fake_chat_json_with_status(system_prompt, payload, **kwargs):
            captured["system_prompt"] = system_prompt
            captured["payload"] = payload
            return (
                {
                    "page_summary": "仅根据已提供样本，先处理高优先级风险。",
                    "action_summary": "今天能动的先按规则执行，T+1 锁定的先观察。",
                    "notes": [],
                },
                type(
                    "_Status",
                    (),
                    {
                        "enabled": True,
                        "success": True,
                        "status": "success",
                        "message": "LLM 解释增强已生效",
                    },
                )(),
            )

        async def fake_cache_upsert(**kwargs):
            return None

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fake_chat_json_with_status)
        monkeypatch.setattr(llm_cache_service, "upsert_cache", fake_cache_upsert)

        summary, status = asyncio.run(
            service.rewrite_sell_points_with_status(
                expanded_response,
                MockMarketEnv(),
                force_refresh=True,
            )
        )

        assert summary is not None
        assert status.success is True
        assert captured["system_prompt"] == service.SELL_SYSTEM_PROMPT
        assert captured["payload"]["prompt_version"] == "sell_points_v3"
        assert captured["payload"]["input_scope"] == "partial_sample"
        assert captured["payload"]["positions_total_count"] == 4
        assert captured["payload"]["positions_sampled_count"] == 3
        assert len(captured["payload"]["positions"]) == 3
        assert any(item["can_sell_today"] is False for item in captured["payload"]["positions"])

    def test_explain_stock_checkup_returns_disabled_status_when_llm_disabled(self, service, sample_checkup_snapshot):
        report, status = asyncio.run(
            service.explain_stock_checkup_with_status(
                sample_checkup_snapshot,
                trade_date="2026-03-20",
                checkup_target=StockCheckupTarget.OBSERVE,
            )
        )

        assert report is None
        assert status.enabled is False
        assert status.status == "disabled"

    def test_explain_stock_checkup_uses_cache_before_model(self, service, sample_checkup_snapshot, monkeypatch):
        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return {
                "overall_summary": "命中缓存的个股体检摘要。",
                "llm_report_sections": [
                    {"key": "strategy", "title": "10）策略结论", "content": "先等修复确认。"}
                ],
                "key_risks": ["跌破支撑"],
                "one_line_conclusion": "这票能看，但不舒服追。",
            }

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("命中缓存后不应再调用模型")

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(llm_client, "chat_json_with_status", fail_if_called)

        report, status = asyncio.run(
            service.explain_stock_checkup_with_status(
                sample_checkup_snapshot,
                trade_date="2026-03-20",
                checkup_target=StockCheckupTarget.OBSERVE,
            )
        )

        assert isinstance(report, LlmStockCheckupReport)
        assert report.overall_summary == "命中缓存的个股体检摘要。"
        assert report.one_line_conclusion == "这票能看，但不舒服追。"
        assert status.success is True
        assert status.status == "cached"

    def test_explain_stock_checkup_retries_with_compact_and_ultra_payloads_after_timeout(
        self,
        service,
        sample_checkup_snapshot,
        monkeypatch,
    ):
        calls = []

        async def fake_runtime():
            return {
                "enabled": True,
                "api_key": "test-key",
                "model": "test-model",
                "base_url": "https://example.com/v1",
                "provider": "openai",
                "max_input_items": 8,
            }

        async def fake_cache_get(*, cache_key):
            return None

        async def fake_chat_json_with_status(system_prompt, payload, **kwargs):
            calls.append(payload)
            if len(calls) == 1:
                return (
                    None,
                    type(
                        "_Status",
                        (),
                        {
                            "enabled": True,
                            "success": False,
                            "status": "timeout",
                            "message": "模型请求超时",
                        },
                    )(),
                )
            if len(calls) == 2:
                return (
                    None,
                    type(
                        "_Status",
                        (),
                        {
                            "enabled": True,
                            "success": False,
                            "status": "timeout",
                            "message": "模型请求超时 [stock_checkup_compact_retry]",
                        },
                    )(),
                )
            return (
                {
                    "overall_summary": "精简后成功返回。",
                    "llm_report_sections": [
                        {
                            "key": "strategy",
                            "title": "10）策略结论",
                            "content": "先等确认。",
                        }
                    ],
                    "key_risks": ["跌破支撑"],
                    "one_line_conclusion": "这票能看，但不舒服追。",
                },
                type(
                    "_Status",
                    (),
                    {
                        "enabled": True,
                        "success": True,
                        "status": "success",
                        "message": "LLM 解释增强已生效",
                    },
                )(),
            )

        async def fake_cache_upsert(**kwargs):
            return None

        monkeypatch.setattr(llm_client, "get_runtime_config", fake_runtime)
        monkeypatch.setattr(llm_cache_service, "get_cache", fake_cache_get)
        monkeypatch.setattr(
            llm_client,
            "chat_json_with_status",
            fake_chat_json_with_status,
        )
        monkeypatch.setattr(llm_cache_service, "upsert_cache", fake_cache_upsert)

        report, status = asyncio.run(
            service.explain_stock_checkup_with_status(
                sample_checkup_snapshot,
                trade_date="2026-03-20",
                checkup_target=StockCheckupTarget.OBSERVE,
            )
        )

        assert report is not None
        assert report.overall_summary == "精简后成功返回。"
        assert status.success is True
        assert len(calls) == 3
        assert calls[0].get("payload_mode") is None
        assert calls[1].get("payload_mode") == "compact_retry"
        assert calls[2].get("payload_mode") == "ultra_compact_retry"
        assert len(calls[1]["rule_snapshot"]["peer_comparison"]["peers"]) <= 2
        assert "peer_comparison" not in calls[2]["rule_snapshot"]
