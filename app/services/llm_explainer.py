"""
LLM 解释增强服务

只对规则结果做人话解释和摘要，不改动交易结论。
"""
from typing import Dict, List, Optional

from loguru import logger

from app.models.schemas import (
    LlmCallStatus,
    LlmPoolsSummary,
    LlmSellSummary,
    SellPointResponse,
    StockOutput,
    StockPoolsOutput,
)
from app.services.llm_client import llm_client


class LlmExplainerService:
    """面向页面的人话解释增强。"""

    POOLS_SYSTEM_PROMPT = """
你是短线交易系统的解释助手。你的职责只有一件事：把已经给定的规则结果翻译成清晰的人话。

严格遵守：
1. 不能新增价格、仓位、胜率、板块、结论等未提供事实。
2. 不能修改原有交易建议，只能解释“为什么会这样”。
3. 文案要短、直接、可执行，避免空话。
4. 输出必须是 JSON 对象，字段只允许：
page_summary, top_focus_summary, pool_empty_reason, stock_notes
5. stock_notes 是数组，每项字段只允许：
ts_code, plain_note, risk_note
6. 如果信息不足，保守表述，不要脑补。
""".strip()

    SELL_SYSTEM_PROMPT = """
你是短线交易系统的卖点解释助手。你的职责是把规则生成的卖点建议改写成更容易理解的动作句。

严格遵守：
1. 不能新增未给出的价格、仓位和市场事实。
2. 不能改变卖出/减仓/持有结论，只能重写说明。
3. action_sentence 要直接说明现在该怎么处理。
4. trigger_sentence 要直接说明什么情况下动手。
5. risk_sentence 要直接说明不处理的风险或当前注意点。
6. 输出必须是 JSON 对象，字段只允许：
page_summary, action_summary, notes
7. notes 是数组，每项字段只允许：
ts_code, action_sentence, trigger_sentence, risk_sentence
""".strip()

    async def is_enabled(self) -> bool:
        runtime = await llm_client.get_runtime_config()
        return bool(
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        )

    async def _runtime_max_input_items(self) -> int:
        runtime = await llm_client.get_runtime_config()
        return max(1, int(runtime.get("max_input_items") or 8))

    def _serialize_pool_stock(self, stock: StockOutput, pool_kind: str) -> Dict:
        data = {
            "ts_code": stock.ts_code,
            "stock_name": stock.stock_name,
            "sector_name": stock.sector_name,
            "change_pct": stock.change_pct,
            "stock_score": stock.stock_score,
            "candidate_bucket_tag": stock.candidate_bucket_tag,
            "candidate_source_tag": stock.candidate_source_tag,
            "stock_strength_tag": getattr(stock.stock_strength_tag, "value", stock.stock_strength_tag),
            "stock_continuity_tag": getattr(stock.stock_continuity_tag, "value", stock.stock_continuity_tag),
            "stock_tradeability_tag": getattr(stock.stock_tradeability_tag, "value", stock.stock_tradeability_tag),
            "stock_core_tag": getattr(stock.stock_core_tag, "value", stock.stock_core_tag),
            "stock_comment": stock.stock_comment,
            "stock_falsification_cond": stock.stock_falsification_cond,
        }
        if pool_kind == "account":
            data.update({
                "pool_entry_reason": stock.pool_entry_reason,
                "position_hint": stock.position_hint,
            })
        elif pool_kind == "holding":
            data.update({
                "sell_signal_tag": stock.sell_signal_tag,
                "sell_reason": stock.sell_reason,
                "sell_priority": stock.sell_priority,
                "pnl_pct": stock.pnl_pct,
                "holding_reason": stock.holding_reason,
            })
        return data

    def _slice_pool_items(self, items: List[StockOutput], limit: int) -> List[StockOutput]:
        return list(items[: max(0, limit)])

    def _pool_llm_limits(self, stock_pools: StockPoolsOutput, total_limit: int) -> Dict[str, int]:
        available = {
            "holding": len(stock_pools.holding_process_pool),
            "account": len(stock_pools.account_executable_pool),
            "market": len(stock_pools.market_watch_pool),
        }
        limits = {"holding": 0, "account": 0, "market": 0}
        order = ["holding", "account", "market"]
        remaining = max(1, total_limit)

        for key in order:
            if remaining <= 0:
                break
            if available[key] <= 0:
                continue
            base = min(available[key], 2, remaining)
            limits[key] = base
            remaining -= base

        for key in order:
            if remaining <= 0:
                break
            room = available[key] - limits[key]
            if room <= 0:
                continue
            extra = min(room, remaining)
            limits[key] += extra
            remaining -= extra

        return limits

    def _build_pool_payload(
        self,
        stock_pools: StockPoolsOutput,
        market_env,
        total_limit: int,
    ) -> Dict:
        limits = self._pool_llm_limits(stock_pools, total_limit)
        return {
            "trade_date": stock_pools.trade_date,
            "market_env_tag": getattr(getattr(market_env, "market_env_tag", None), "value", None),
            "market_comment": getattr(market_env, "market_comment", ""),
            "counts": {
                "market_watch": len(stock_pools.market_watch_pool),
                "account_executable": len(stock_pools.account_executable_pool),
                "holding_process": len(stock_pools.holding_process_pool),
            },
            "market_watch_pool": [
                self._serialize_pool_stock(s, "market")
                for s in self._slice_pool_items(stock_pools.market_watch_pool, limits["market"])
            ],
            "account_executable_pool": [
                self._serialize_pool_stock(s, "account")
                for s in self._slice_pool_items(stock_pools.account_executable_pool, limits["account"])
            ],
            "holding_process_pool": [
                self._serialize_pool_stock(s, "holding")
                for s in self._slice_pool_items(stock_pools.holding_process_pool, limits["holding"])
            ],
        }

    async def summarize_stock_pools(
        self,
        stock_pools: StockPoolsOutput,
        market_env,
    ) -> Optional[LlmPoolsSummary]:
        """生成三池页摘要，并回填个股人话说明。"""
        summary, _status = await self.summarize_stock_pools_with_status(stock_pools, market_env)
        return summary

    async def summarize_stock_pools_with_status(
        self,
        stock_pools: StockPoolsOutput,
        market_env,
    ) -> tuple[Optional[LlmPoolsSummary], LlmCallStatus]:
        """生成三池页摘要，并返回调用状态。"""
        if not await self.is_enabled():
            return None, LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message="LLM 未启用或配置不完整",
            )
        max_items = min(await self._runtime_max_input_items(), 6)
        payload = self._build_pool_payload(stock_pools, market_env, max_items)

        data, status = await llm_client.chat_json_with_status(self.POOLS_SYSTEM_PROMPT, payload)
        if not data and status.status == "timeout":
            fallback_payload = self._build_pool_payload(stock_pools, market_env, 3)
            data, status = await llm_client.chat_json_with_status(self.POOLS_SYSTEM_PROMPT, fallback_payload)
        if not data:
            return None, status

        try:
            summary = LlmPoolsSummary.model_validate(data)
            self.apply_pool_summary(stock_pools, summary)
            return summary, status
        except Exception as exc:
            logger.warning(f"LLM 三池摘要校验失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="validation_error",
                message=f"LLM 三池摘要校验失败：{exc}",
            )

    def apply_pool_summary(
        self,
        stock_pools: StockPoolsOutput,
        summary: LlmPoolsSummary,
    ) -> StockPoolsOutput:
        """将 LLM 个股解释回填到三池结果。"""
        notes = {note.ts_code: note for note in summary.stock_notes}
        for group in (
            stock_pools.market_watch_pool,
            stock_pools.account_executable_pool,
            stock_pools.holding_process_pool,
        ):
            for stock in group:
                note = notes.get(stock.ts_code)
                if not note:
                    continue
                stock.llm_plain_note = note.plain_note or None
                stock.llm_risk_note = note.risk_note or None
        return stock_pools

    async def rewrite_sell_points(
        self,
        sell_points: SellPointResponse,
        market_env,
    ) -> Optional[LlmSellSummary]:
        """生成卖点页摘要，并回填更可读的动作句。"""
        summary, _status = await self.rewrite_sell_points_with_status(sell_points, market_env)
        return summary

    async def rewrite_sell_points_with_status(
        self,
        sell_points: SellPointResponse,
        market_env,
    ) -> tuple[Optional[LlmSellSummary], LlmCallStatus]:
        """生成卖点页摘要，并返回调用状态。"""
        if not await self.is_enabled():
            return None, LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message="LLM 未启用或配置不完整",
            )
        max_items = await self._runtime_max_input_items()

        points = (
            list(sell_points.sell_positions)
            + list(sell_points.reduce_positions)
            + list(sell_points.hold_positions)
        )
        payload = {
            "trade_date": sell_points.trade_date,
            "market_env_tag": getattr(getattr(market_env, "market_env_tag", None), "value", None),
            "counts": {
                "sell": len(sell_points.sell_positions),
                "reduce": len(sell_points.reduce_positions),
                "hold": len(sell_points.hold_positions),
            },
            "positions": [
                {
                    "ts_code": point.ts_code,
                    "stock_name": point.stock_name,
                    "sell_signal_tag": getattr(point.sell_signal_tag, "value", point.sell_signal_tag),
                    "sell_point_type": getattr(point.sell_point_type, "value", point.sell_point_type),
                    "sell_priority": getattr(point.sell_priority, "value", point.sell_priority),
                    "sell_reason": point.sell_reason,
                    "sell_trigger_cond": point.sell_trigger_cond,
                    "sell_comment": point.sell_comment,
                    "pnl_pct": point.pnl_pct,
                    "holding_days": point.holding_days,
                    "can_sell_today": point.can_sell_today,
                }
                for point in points[:max_items]
            ],
        }

        data, status = await llm_client.chat_json_with_status(self.SELL_SYSTEM_PROMPT, payload)
        if not data:
            return None, status

        try:
            summary = LlmSellSummary.model_validate(data)
            self.apply_sell_summary(sell_points, summary)
            return summary, status
        except Exception as exc:
            logger.warning(f"LLM 卖点摘要校验失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="validation_error",
                message=f"LLM 卖点摘要校验失败：{exc}",
            )

    def apply_sell_summary(
        self,
        sell_points: SellPointResponse,
        summary: LlmSellSummary,
    ) -> SellPointResponse:
        """将 LLM 对卖点的人话解释回填到返回对象。"""
        notes = {note.ts_code: note for note in summary.notes}
        for group in (
            sell_points.sell_positions,
            sell_points.reduce_positions,
            sell_points.hold_positions,
        ):
            for point in group:
                note = notes.get(point.ts_code)
                if not note:
                    continue
                point.llm_action_sentence = note.action_sentence or None
                point.llm_trigger_sentence = note.trigger_sentence or None
                point.llm_risk_sentence = note.risk_sentence or None
        return sell_points


llm_explainer_service = LlmExplainerService()
