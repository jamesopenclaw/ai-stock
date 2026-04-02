"""
LLM 解释增强服务

只对规则结果做人话解释和摘要，不改动交易结论。
"""
import hashlib
import json
from typing import Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.models.schemas import (
    LlmCallStatus,
    LlmPoolsSummary,
    LlmSellSummary,
    LlmStockCheckupReport,
    SellPointResponse,
    StockCheckupRuleSnapshot,
    StockCheckupTarget,
    StockOutput,
    StockPoolsOutput,
)
from app.services.llm_client import llm_client
from app.services.llm_cache_service import llm_cache_service


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
你是短线交易系统的卖点解释助手。你的职责是把规则生成的卖点建议改写成更容易理解、可直接执行的人话说明。

严格遵守：
1. 你的角色只是解释规则结果，不是重新做投资判断。
2. 不能新增未给出的价格、仓位、市场事实、排序依据或交易结论。
3. 不能改变卖出/减仓/持有结论，只能重写说明。
4. 解释时优先使用输入中的结构化上下文，例如 pnl_profile、quote_context、reason_code_hint、execution_focus，再结合 sell_reason、sell_trigger_cond、sell_comment，不要只机械复读原字段。
5. action_sentence 要回答“为什么当前是拿/减/清”，让用户知道当前重点是保护利润、观察承接，还是提高退出效率；如果 can_sell_today=false，必须先明确“今天不能卖/不能减”，只能写观察或下一交易日条件，不能写成立即执行。
6. trigger_sentence 要回答“接下来盯什么变化”，优先把 sell_trigger_cond 口语化为一个更像交易员盘中盯盘的话术；不要和 action_sentence 说重复的话。
7. risk_sentence 要回答“如果不处理或看错，最容易吃什么亏”，优先结合已有 sell_comment、quote_context、pnl_profile，避免空泛风险提示。
8. 对持有结论，重点解释“还能拿的原因”和“继续拿的前提”；对减仓结论，重点解释“为什么先防守而不是直接走”；对卖出结论，重点解释“为什么现在优先退出”。
9. 如果 reduce_reason_code=protect_profit，优先写“利润保护/先锁一部分”；如果是 structure_loose，优先写“强度下降/结构松动”；如果是 env_weak，优先写“环境转弱/先收缩风险”；如果是 rebound_exit，优先写“借反抽处理/不恋战”。
10. 当 sell_signal_tag=减仓 时，优先表述为“强度下降/结构分歧/先做防守/先保护利润”，不要使用“日线已坏/必须离场/继续持有没有意义/结构彻底失效”这类只适用于卖出结论的措辞。
11. 如果 payload 明确说明是 partial_sample，page_summary 和 action_summary 只能总结“已提供样本”，不能写成对全部持仓的全局结论。
12. 文案要短、直接、有交易价值，避免空话、套话和三句几乎一模一样的复述。
13. plain_note 必须是一段适合直接展示在股票卡片上的连续说明文字，像交易员给用户的简短解读，不要写成“动作：/时机：/风险：”这种模板格式。
14. 输出必须是 JSON 对象，字段只允许：
page_summary, action_summary, notes
15. notes 是数组，每项字段只允许：
ts_code, plain_note, action_sentence, trigger_sentence, risk_sentence
""".strip()

    STOCK_CHECKUP_SYSTEM_PROMPT = """
你是 A 股短线交易系统里的个股全面体检助手。你的任务是基于已经给定的规则事实，输出一份结构化体检报告。

严格遵守：
1. 只能使用输入里已有事实，不得新增价格、涨跌、仓位、板块地位、资金流细节。
2. 不能改变规则快照中的交易方向，只能解释、收敛和提炼。
3. 输出必须是 JSON 对象，字段只允许：
overall_summary, llm_report_sections, key_risks, one_line_conclusion
4. llm_report_sections 必须是数组，每项字段只允许：
key, title, content
5. content 要短、直接、可执行，避免空话和套话。
6. 对含有“[需确认]”的信息，要明确保守表达，不要脑补。
7. 最终一句话结论要像交易员复盘语气，清楚表达“能不能看、能不能做、错了怎么看”。
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

    def _sell_point_pnl_profile(self, pnl_pct: Optional[float]) -> str:
        value = float(pnl_pct or 0)
        if value >= 15:
            return "利润垫较厚"
        if value > 0:
            return "小幅盈利"
        if value <= -8:
            return "亏损较深"
        if value < 0:
            return "小幅亏损"
        return "盈亏接近持平"

    def _sell_point_quote_context(self, point) -> str:
        source = str(getattr(point, "data_source", "") or "")
        if source.startswith("realtime_"):
            return "当前是实时分时口径"
        return "当前不是实时分时口径，偏向日线回退"

    def _sell_point_reason_code_hint(self, point) -> str:
        mapping = {
            "protect_profit": "这类减仓更偏利润保护，不是判定彻底走坏。",
            "structure_loose": "这类减仓更偏结构松动，重点看强度是否继续下降。",
            "env_weak": "这类减仓更偏环境转弱下的防守动作。",
            "rebound_exit": "这类减仓更偏借反抽处理，不适合恋战。",
        }
        return mapping.get(str(getattr(point, "reduce_reason_code", "") or ""), "")

    def _sell_point_execution_focus(self, point) -> str:
        signal = getattr(point, "sell_signal_tag", None)
        signal_value = getattr(signal, "value", signal)
        pnl_profile = self._sell_point_pnl_profile(getattr(point, "pnl_pct", None))
        if signal_value == "卖出":
            return f"{pnl_profile}，当前重点是退出效率，不是继续博弈。"
        if signal_value == "减仓":
            return f"{pnl_profile}，当前重点是先做防守和仓位收缩，再看后续是否修复。"
        return f"{pnl_profile}，当前重点是确认承接是否延续，而不是急着处理。"

    def _cache_key(
        self,
        *,
        scene: str,
        account_id: str,
        trade_date: str,
        provider: str,
        model: str,
        payload: Dict,
    ) -> str:
        raw = json.dumps(
            {
                "scene": scene,
                "account_id": account_id,
                "trade_date": trade_date,
                "provider": provider,
                "model": model,
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
            "sector_profile_tag": getattr(stock.sector_profile_tag, "value", stock.sector_profile_tag),
            "stock_role_tag": getattr(stock.stock_role_tag, "value", stock.stock_role_tag),
            "day_strength_tag": getattr(stock.day_strength_tag, "value", stock.day_strength_tag),
            "structure_state_tag": getattr(stock.structure_state_tag, "value", stock.structure_state_tag),
            "next_tradeability_tag": getattr(stock.next_tradeability_tag, "value", stock.next_tradeability_tag),
            "stock_comment": stock.stock_comment,
            "stock_falsification_cond": stock.stock_falsification_cond,
            "why_this_pool": stock.why_this_pool,
            "not_other_pools": stock.not_other_pools,
            "pool_decision_summary": stock.pool_decision_summary,
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

    def _normalize_pool_empty_reason(self, value) -> str:
        """兼容 LLM 返回的字符串、分池字典或数组。"""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            parts = []
            for key, reason in value.items():
                text = str(reason or "").strip()
                if text:
                    parts.append(f"{key}: {text}")
            return "；".join(parts)
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        if value is None:
            return ""
        return str(value)

    def _normalize_pools_summary_payload(self, data: Dict) -> Dict:
        """在模型校验前对三池摘要做最小兼容清洗。"""
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["pool_empty_reason"] = self._normalize_pool_empty_reason(
            normalized.get("pool_empty_reason")
        )
        return normalized

    def _slice_pool_items(self, items: List[StockOutput], limit: int) -> List[StockOutput]:
        return list(items[: max(0, limit)])

    def _pool_llm_limits(self, stock_pools: StockPoolsOutput, total_limit: int) -> Dict[str, int]:
        available = {
            "holding": len(stock_pools.holding_process_pool),
            "account": len(stock_pools.account_executable_pool),
            "trend": len(stock_pools.trend_recognition_pool),
            "market": len(stock_pools.market_watch_pool),
        }
        limits = {"holding": 0, "account": 0, "trend": 0, "market": 0}
        order = ["holding", "account", "trend", "market"]
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
                "trend_recognition": len(stock_pools.trend_recognition_pool),
                "account_executable": len(stock_pools.account_executable_pool),
                "holding_process": len(stock_pools.holding_process_pool),
            },
            "market_watch_pool": [
                self._serialize_pool_stock(s, "market")
                for s in self._slice_pool_items(stock_pools.market_watch_pool, limits["market"])
            ],
            "trend_recognition_pool": [
                self._serialize_pool_stock(s, "trend")
                for s in self._slice_pool_items(stock_pools.trend_recognition_pool, limits["trend"])
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
        *,
        account_id: Optional[str] = None,
        force_refresh: bool = False,
        allow_live_request: bool = True,
    ) -> Optional[LlmPoolsSummary]:
        """生成三池页摘要，并回填个股人话说明。"""
        summary, _status = await self.summarize_stock_pools_with_status(
            stock_pools,
            market_env,
            account_id=account_id,
            force_refresh=force_refresh,
            allow_live_request=allow_live_request,
        )
        return summary

    async def summarize_stock_pools_with_status(
        self,
        stock_pools: StockPoolsOutput,
        market_env,
        *,
        account_id: Optional[str] = None,
        force_refresh: bool = False,
        allow_live_request: bool = True,
    ) -> tuple[Optional[LlmPoolsSummary], LlmCallStatus]:
        """生成三池页摘要，并返回调用状态。"""
        runtime = await llm_client.get_runtime_config()
        if not (
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        ):
            return None, LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message="LLM 未启用或配置不完整",
            )
        max_items = min(await self._runtime_max_input_items(), 6)
        payload = self._build_pool_payload(stock_pools, market_env, max_items)
        cache_key = self._cache_key(
            scene="stock_pools",
            account_id=str(account_id or ""),
            trade_date=stock_pools.trade_date,
            provider=str(runtime.get("provider") or ""),
            model=str(runtime.get("model") or ""),
            payload=payload,
        )

        if not force_refresh:
            cache_kwargs = {"account_id": account_id} if account_id else {}
            cached = await llm_cache_service.get_cache(
                cache_key=cache_key,
                **cache_kwargs,
            )
            if cached:
                try:
                    summary = LlmPoolsSummary.model_validate(
                        self._normalize_pools_summary_payload(cached)
                    )
                    self.apply_pool_summary(stock_pools, summary)
                    return summary, LlmCallStatus(
                        enabled=True,
                        success=True,
                        status="cached",
                        message="LLM 解读已命中缓存",
                    )
                except Exception as exc:
                    logger.warning(f"LLM 三池缓存校验失败: {exc}")

            if not allow_live_request:
                return None, LlmCallStatus(
                    enabled=True,
                    success=False,
                    status="cache_miss",
                    message="LLM 摘要未命中缓存，已跳过实时生成以保证页面响应",
                )

        llm_kwargs = {"account_id": account_id} if account_id else {}
        data, status = await llm_client.chat_json_with_status(
            self.POOLS_SYSTEM_PROMPT,
            payload,
            scene="stock_pools",
            trade_date=stock_pools.trade_date,
            **llm_kwargs,
        )
        if not data and status.status == "timeout":
            fallback_payload = self._build_pool_payload(stock_pools, market_env, 3)
            data, status = await llm_client.chat_json_with_status(
                self.POOLS_SYSTEM_PROMPT,
                fallback_payload,
                scene="stock_pools",
                trade_date=stock_pools.trade_date,
                **llm_kwargs,
            )
        if not data:
            return None, status

        try:
            summary = LlmPoolsSummary.model_validate(
                self._normalize_pools_summary_payload(data)
            )
            self.apply_pool_summary(stock_pools, summary)
            await llm_cache_service.upsert_cache(
                scene="stock_pools",
                cache_key=cache_key,
                trade_date=stock_pools.trade_date,
                provider=str(runtime.get("provider") or ""),
                model=str(runtime.get("model") or ""),
                payload=payload,
                response=summary.model_dump(),
                **llm_kwargs,
            )
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
            stock_pools.trend_recognition_pool,
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
        *,
        account_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[LlmSellSummary]:
        """生成卖点页摘要，并回填更可读的动作句。"""
        summary, _status = await self.rewrite_sell_points_with_status(
            sell_points,
            market_env,
            account_id=account_id,
            force_refresh=force_refresh,
        )
        return summary

    async def rewrite_sell_points_with_status(
        self,
        sell_points: SellPointResponse,
        market_env,
        *,
        account_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> tuple[Optional[LlmSellSummary], LlmCallStatus]:
        """生成卖点页摘要，并返回调用状态。"""
        runtime = await llm_client.get_runtime_config()
        if not (
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        ):
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
        sampled_points = points[:max_items]
        payload = {
            "prompt_version": "sell_points_v2",
            "trade_date": sell_points.trade_date,
            "market_env_tag": getattr(getattr(market_env, "market_env_tag", None), "value", None),
            "input_scope": "full" if len(points) <= max_items else "partial_sample",
            "positions_total_count": len(points),
            "positions_sampled_count": len(sampled_points),
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
                    "reduce_reason_code": point.reduce_reason_code,
                    "sell_trigger_cond": point.sell_trigger_cond,
                    "sell_comment": point.sell_comment,
                    "market_price": point.market_price,
                    "cost_price": point.cost_price,
                    "pnl_pct": point.pnl_pct,
                    "pnl_profile": self._sell_point_pnl_profile(point.pnl_pct),
                    "holding_days": point.holding_days,
                    "can_sell_today": point.can_sell_today,
                    "quote_context": self._sell_point_quote_context(point),
                    "reason_code_hint": self._sell_point_reason_code_hint(point),
                    "execution_focus": self._sell_point_execution_focus(point),
                }
                for point in sampled_points
            ],
        }
        cache_key = self._cache_key(
            scene="sell_points",
            account_id=str(account_id or ""),
            trade_date=sell_points.trade_date,
            provider=str(runtime.get("provider") or ""),
            model=str(runtime.get("model") or ""),
            payload=payload,
        )

        if not force_refresh:
            cache_kwargs = {"account_id": account_id} if account_id else {}
            cached = await llm_cache_service.get_cache(
                cache_key=cache_key,
                **cache_kwargs,
            )
            if cached:
                try:
                    summary = LlmSellSummary.model_validate(cached)
                    self.apply_sell_summary(sell_points, summary)
                    return summary, LlmCallStatus(
                        enabled=True,
                        success=True,
                        status="cached",
                        message="LLM 解读已命中缓存",
                    )
                except Exception as exc:
                    logger.warning(f"LLM 卖点缓存校验失败: {exc}")

        llm_kwargs = {"account_id": account_id} if account_id else {}
        data, status = await llm_client.chat_json_with_status(
            self.SELL_SYSTEM_PROMPT,
            payload,
            scene="sell_points",
            trade_date=sell_points.trade_date,
            **llm_kwargs,
        )
        if not data:
            return None, status

        try:
            summary = LlmSellSummary.model_validate(data)
            self.apply_sell_summary(sell_points, summary)
            await llm_cache_service.upsert_cache(
                scene="sell_points",
                cache_key=cache_key,
                trade_date=sell_points.trade_date,
                provider=str(runtime.get("provider") or ""),
                model=str(runtime.get("model") or ""),
                payload=payload,
                response=summary.model_dump(),
                **llm_kwargs,
            )
            return summary, status
        except Exception as exc:
            logger.warning(f"LLM 卖点摘要校验失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="validation_error",
                message=f"LLM 卖点摘要校验失败：{exc}",
            )

    def _build_checkup_payload(
        self,
        rule_snapshot: StockCheckupRuleSnapshot,
        checkup_target: StockCheckupTarget,
        trade_date: str,
        *,
        mode: str = "full",
    ) -> Dict:
        payload = {
            "trade_date": trade_date,
            "checkup_target": checkup_target.value,
            "rule_snapshot": rule_snapshot.model_dump(mode="json"),
        }
        if mode == "full":
            return payload

        raw = rule_snapshot.model_dump(mode="json")
        if mode == "compact":
            compact_snapshot = {
                "basic_info": {
                    "ts_code": raw["basic_info"].get("ts_code"),
                    "stock_name": raw["basic_info"].get("stock_name"),
                    "sector_name": raw["basic_info"].get("sector_name"),
                    "board": raw["basic_info"].get("board"),
                    "special_tags": raw["basic_info"].get("special_tags", [])[:3],
                },
                "market_context": {
                    "market_env_tag": raw["market_context"].get("market_env_tag"),
                    "market_phase": raw["market_context"].get("market_phase"),
                    "stock_market_alignment": raw["market_context"].get("stock_market_alignment"),
                    "tolerance_comment": raw["market_context"].get("tolerance_comment"),
                },
                "direction_position": {
                    "direction_name": raw["direction_position"].get("direction_name"),
                    "sector_level": raw["direction_position"].get("sector_level"),
                    "stock_role": raw["direction_position"].get("stock_role"),
                    "relative_strength": raw["direction_position"].get("relative_strength"),
                },
                "daily_structure": {
                    "ma_position_summary": raw["daily_structure"].get("ma_position_summary"),
                    "stage_position": raw["daily_structure"].get("stage_position"),
                    "range_position_20d": raw["daily_structure"].get("range_position_20d"),
                    "range_position_60d": raw["daily_structure"].get("range_position_60d"),
                    "structure_conclusion": raw["daily_structure"].get("structure_conclusion"),
                },
                "intraday_strength": {
                    "change_pct": raw["intraday_strength"].get("change_pct"),
                    "turnover_rate": raw["intraday_strength"].get("turnover_rate"),
                    "vol_ratio": raw["intraday_strength"].get("vol_ratio"),
                    "close_position": raw["intraday_strength"].get("close_position"),
                    "strength_level": raw["intraday_strength"].get("strength_level"),
                },
                "fund_quality": {
                    "cash_flow_quality": raw["fund_quality"].get("cash_flow_quality"),
                    "note": raw["fund_quality"].get("note"),
                },
                "peer_comparison": {
                    "relative_strength": raw["peer_comparison"].get("relative_strength"),
                    "recognizability": raw["peer_comparison"].get("recognizability"),
                    "peers": raw["peer_comparison"].get("peers", [])[:2],
                },
                "valuation_profile": {
                    "valuation_level": raw["valuation_profile"].get("valuation_level"),
                    "drive_type": raw["valuation_profile"].get("drive_type"),
                    "pe": raw["valuation_profile"].get("pe"),
                    "pb": raw["valuation_profile"].get("pb"),
                    "ps": raw["valuation_profile"].get("ps"),
                    "market_value": raw["valuation_profile"].get("market_value"),
                },
                "key_levels": {
                    "pressure_levels": raw["key_levels"].get("pressure_levels", [])[:2],
                    "support_levels": raw["key_levels"].get("support_levels", [])[:2],
                    "defense_level": raw["key_levels"].get("defense_level"),
                },
                "buy_view": raw.get("buy_view"),
                "sell_view": raw.get("sell_view"),
                "strategy": {
                    "current_characterization": raw["strategy"].get("current_characterization"),
                    "current_role": raw["strategy"].get("current_role"),
                    "current_strategy": raw["strategy"].get("current_strategy"),
                    "strategy_reason": raw["strategy"].get("strategy_reason"),
                    "risk_points": raw["strategy"].get("risk_points", [])[:3],
                },
                "final_conclusion": {
                    "one_line_conclusion": raw["final_conclusion"].get("one_line_conclusion"),
                },
            }
            return {
                "trade_date": trade_date,
                "checkup_target": checkup_target.value,
                "rule_snapshot": compact_snapshot,
                "payload_mode": "compact_retry",
            }

        ultra_snapshot = {
            "basic_info": {
                "ts_code": raw["basic_info"].get("ts_code"),
                "stock_name": raw["basic_info"].get("stock_name"),
                "sector_name": raw["basic_info"].get("sector_name"),
            },
            "market_context": {
                "market_env_tag": raw["market_context"].get("market_env_tag"),
                "stock_market_alignment": raw["market_context"].get("stock_market_alignment"),
            },
            "direction_position": {
                "sector_level": raw["direction_position"].get("sector_level"),
                "stock_role": raw["direction_position"].get("stock_role"),
            },
            "daily_structure": {
                "stage_position": raw["daily_structure"].get("stage_position"),
                "structure_conclusion": raw["daily_structure"].get("structure_conclusion"),
            },
            "intraday_strength": {
                "change_pct": raw["intraday_strength"].get("change_pct"),
                "strength_level": raw["intraday_strength"].get("strength_level"),
            },
            "fund_quality": {
                "cash_flow_quality": raw["fund_quality"].get("cash_flow_quality"),
            },
            "valuation_profile": {
                "valuation_level": raw["valuation_profile"].get("valuation_level"),
                "drive_type": raw["valuation_profile"].get("drive_type"),
            },
            "key_levels": {
                "pressure_levels": raw["key_levels"].get("pressure_levels", [])[:1],
                "support_levels": raw["key_levels"].get("support_levels", [])[:1],
                "defense_level": raw["key_levels"].get("defense_level"),
            },
            "strategy": {
                "current_strategy": raw["strategy"].get("current_strategy"),
                "strategy_reason": raw["strategy"].get("strategy_reason"),
                "risk_points": raw["strategy"].get("risk_points", [])[:2],
            },
            "final_conclusion": {
                "one_line_conclusion": raw["final_conclusion"].get("one_line_conclusion"),
            },
        }
        return {
            "trade_date": trade_date,
            "checkup_target": checkup_target.value,
            "rule_snapshot": ultra_snapshot,
            "payload_mode": "ultra_compact_retry",
        }

    async def explain_stock_checkup_with_status(
        self,
        rule_snapshot: StockCheckupRuleSnapshot,
        *,
        trade_date: str,
        checkup_target: StockCheckupTarget,
        account_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> tuple[Optional[LlmStockCheckupReport], LlmCallStatus]:
        runtime = await llm_client.get_runtime_config()
        if not (
            runtime.get("enabled")
            and str(runtime.get("api_key") or "").strip()
            and str(runtime.get("model") or "").strip()
            and str(runtime.get("base_url") or "").strip()
        ):
            return None, LlmCallStatus(
                enabled=False,
                success=False,
                status="disabled",
                message="LLM 未启用或配置不完整",
            )

        base_timeout = float(
            runtime.get("timeout_seconds") or settings.llm_timeout_seconds
        )
        checkup_http_timeout = max(
            base_timeout,
            float(settings.llm_stock_checkup_min_timeout_seconds),
        )

        payload = self._build_checkup_payload(
            rule_snapshot,
            checkup_target,
            trade_date,
        )
        cache_key = self._cache_key(
            scene="stock_checkup",
            account_id=str(account_id or ""),
            trade_date=trade_date,
            provider=str(runtime.get("provider") or ""),
            model=str(runtime.get("model") or ""),
            payload=payload,
        )
        if not force_refresh:
            cache_kwargs = {"account_id": account_id} if account_id else {}
            cached = await llm_cache_service.get_cache(
                cache_key=cache_key,
                **cache_kwargs,
            )
            if cached:
                try:
                    report = LlmStockCheckupReport.model_validate(cached)
                    return report, LlmCallStatus(
                        enabled=True,
                        success=True,
                        status="cached",
                        message="LLM 个股体检已命中缓存",
                    )
                except Exception as exc:
                    logger.warning(f"LLM 个股体检缓存校验失败: {exc}")

        llm_kwargs = {"account_id": account_id} if account_id else {}
        data, status = await llm_client.chat_json_with_status(
            self.STOCK_CHECKUP_SYSTEM_PROMPT,
            payload,
            scene="stock_checkup",
            trade_date=trade_date,
            request_label="stock_checkup_full",
            timeout_seconds=checkup_http_timeout,
            **llm_kwargs,
        )
        if not data and status.status == "timeout":
            fallback_payload = self._build_checkup_payload(
                rule_snapshot,
                checkup_target,
                trade_date,
                mode="compact",
            )
            data, status = await llm_client.chat_json_with_status(
                self.STOCK_CHECKUP_SYSTEM_PROMPT,
                fallback_payload,
                scene="stock_checkup",
                trade_date=trade_date,
                request_label="stock_checkup_compact_retry",
                timeout_seconds=checkup_http_timeout,
                **llm_kwargs,
            )
        if not data and status.status == "timeout":
            ultra_payload = self._build_checkup_payload(
                rule_snapshot,
                checkup_target,
                trade_date,
                mode="ultra_compact",
            )
            data, status = await llm_client.chat_json_with_status(
                self.STOCK_CHECKUP_SYSTEM_PROMPT,
                ultra_payload,
                scene="stock_checkup",
                trade_date=trade_date,
                request_label="stock_checkup_ultra_compact_retry",
                timeout_seconds=checkup_http_timeout,
                **llm_kwargs,
            )
        if not data:
            return None, status

        try:
            report = LlmStockCheckupReport.model_validate(data)
            await llm_cache_service.upsert_cache(
                scene="stock_checkup",
                cache_key=cache_key,
                trade_date=trade_date,
                provider=str(runtime.get("provider") or ""),
                model=str(runtime.get("model") or ""),
                payload=payload,
                response=report.model_dump(),
                **llm_kwargs,
            )
            return report, status
        except Exception as exc:
            logger.warning(f"LLM 个股体检校验失败: {exc}")
            return None, LlmCallStatus(
                enabled=True,
                success=False,
                status="validation_error",
                message=f"LLM 个股体检校验失败：{exc}",
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
                point.llm_plain_note = note.plain_note or None
                point.llm_action_sentence = note.action_sentence or None
                point.llm_trigger_sentence = note.trigger_sentence or None
                point.llm_risk_sentence = note.risk_sentence or None
        return sell_points


llm_explainer_service = LlmExplainerService()
