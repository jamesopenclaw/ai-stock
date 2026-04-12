"""
通知触发引擎
"""
from __future__ import annotations

import time
from threading import RLock
from typing import Optional

from loguru import logger
from sqlalchemy import select

from app.core.database import async_session_factory
from app.data.tushare_client import normalize_ts_code
from app.models.schemas import MarketEnvTag, NotificationPriority, SellSignalTag, StockPoolTag
from app.models.trading_account import TradingAccount
from app.services.decision_context import SharedDecisionContext, decision_context_service
from app.services.decision_flow import FullDecisionBundle, decision_flow_service
from app.services.market_data_gateway import market_data_gateway
from app.services.notification_service import notification_service
from app.services.notification_state_service import (
    NotificationStateInput,
    notification_state_service,
)
from app.services.review_snapshot import review_snapshot_service


class NotificationEngine:
    """基于当前账户状态生成关键通知事件。"""

    NOTIFICATION_CANDIDATE_LIMIT = 100
    STABLE_STOCK_POOLS_SNAPSHOT_VERSION = 7

    MANAGED_EVENT_TYPES = {
        "holding_to_sell",
        "holding_to_reduce",
        "candidate_to_executable",
        "candidate_near_trigger",
        "radar_candidate_near_execution",
        "market_env_downgraded",
        "realtime_source_degraded",
    }

    REFRESH_TTL_SECONDS = 20

    STATE_TYPE_MARKET = "market_env"
    STATE_TYPE_HOLDING = "holding_signal"
    STATE_TYPE_CANDIDATE = "candidate_signal"
    STATE_TYPE_RADAR_EXECUTION = "radar_execution_signal"
    STATE_TYPE_REALTIME = "realtime_source"

    MARKET_STATE_KEY = "market"
    REALTIME_STATE_KEY = "realtime-source"
    NON_LIVE_REALTIME_SOURCES = {"realtime_cache"}

    def __init__(self):
        self._refresh_cache: dict[str, float] = {}
        self._cache_lock = RLock()

    async def list_active_accounts(self) -> list[tuple[str, Optional[str]]]:
        """列出需要参与通知刷新的有效交易账户。"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(TradingAccount.id, TradingAccount.owner_user_id)
                .where(TradingAccount.status == "active")
                .order_by(TradingAccount.created_at.asc())
            )
            return [(row.id, row.owner_user_id) for row in result.all()]

    async def refresh_active_accounts(
        self,
        *,
        trade_date: Optional[str] = None,
        force: bool = False,
    ) -> int:
        """批量刷新全部有效账户的通知事件。"""
        accounts = await self.list_active_accounts()
        shared_context = None
        resolved_trade_date = trade_date or time.strftime("%Y-%m-%d")
        if accounts:
            try:
                shared_context = await decision_context_service.build_shared_context(
                    resolved_trade_date,
                    top_gainers=self.NOTIFICATION_CANDIDATE_LIMIT,
                )
            except Exception as exc:
                logger.warning(
                    "notification shared context build failed trade_date={} error={}",
                    resolved_trade_date,
                    exc,
                )
        for account_id, user_id in accounts:
            await self.refresh_account_events(
                account_id,
                user_id=user_id,
                trade_date=resolved_trade_date,
                force=force,
                shared_context=shared_context,
            )
        return len(accounts)

    async def refresh_account_events(
        self,
        account_id: str,
        *,
        user_id: Optional[str] = None,
        trade_date: Optional[str] = None,
        force: bool = False,
        shared_context: Optional[SharedDecisionContext] = None,
    ) -> None:
        resolved_trade_date = trade_date or time.strftime("%Y-%m-%d")
        with self._cache_lock:
            last = self._refresh_cache.get(account_id, 0.0)
            if not force and time.monotonic() - last < self.REFRESH_TTL_SECONDS:
                return
            self._refresh_cache[account_id] = time.monotonic()

        try:
            bundle = await decision_flow_service.build_full_decision(
                resolved_trade_date,
                top_gainers=self.NOTIFICATION_CANDIDATE_LIMIT,
                account_id=account_id,
                shared_context=shared_context,
            )
        except Exception as exc:
            logger.warning("notification refresh failed account_id={} error={}", account_id, exc)
            return

        await self._sync_stable_snapshot_if_needed(
            account_id,
            trade_date=resolved_trade_date,
            bundle=bundle,
        )

        market_env = bundle.context.market_env
        buy_analysis = bundle.buy_analysis
        sell_analysis = bundle.sell_analysis
        active_keys: set[str] = set()

        await self._sync_market_event(
            account_id,
            user_id=user_id,
            trade_date=resolved_trade_date,
            market_env=market_env,
            active_keys=active_keys,
        )
        await self._sync_holding_events(
            account_id,
            user_id=user_id,
            trade_date=resolved_trade_date,
            sell_analysis=sell_analysis,
            active_keys=active_keys,
        )
        await self._sync_candidate_events(
            account_id,
            user_id=user_id,
            trade_date=resolved_trade_date,
            buy_analysis=buy_analysis,
            active_keys=active_keys,
        )
        await self._sync_realtime_source_event(
            account_id,
            user_id=user_id,
            trade_date=resolved_trade_date,
            buy_analysis=buy_analysis,
            sell_analysis=sell_analysis,
            active_keys=active_keys,
        )

        await notification_service.resolve_inactive_events(
            account_id,
            active_dedupe_keys=active_keys,
            event_types=set(self.MANAGED_EVENT_TYPES),
        )

    async def _sync_stable_snapshot_if_needed(
        self,
        account_id: str,
        *,
        trade_date: str,
        bundle: FullDecisionBundle,
    ) -> None:
        if market_data_gateway.should_use_realtime_quote(trade_date):
            return

        stock_pools = bundle.stock_pools.model_copy(deep=True)
        stock_pools.resolved_trade_date = bundle.context.resolved_stock_trade_date
        stock_pools.candidate_data_status = getattr(bundle.context, "candidate_data_status", None)
        stock_pools.candidate_data_message = getattr(bundle.context, "candidate_data_message", None)
        stock_pools.sector_scan_trade_date = getattr(bundle.context, "sector_scan_trade_date", None)
        stock_pools.sector_scan_resolved_trade_date = getattr(bundle.context, "sector_scan_resolved_trade_date", None)
        stock_pools.snapshot_version = self.STABLE_STOCK_POOLS_SNAPSHOT_VERSION
        stock_pools.market_env = bundle.context.market_env
        stock_pools.theme_leaders = list(getattr(bundle.context.sector_scan, "theme_leaders", []) or [])[:3]
        stock_pools.industry_leaders = list(getattr(bundle.context.sector_scan, "industry_leaders", []) or [])[:3]
        stock_pools.mainline_sectors = list(getattr(bundle.context.sector_scan, "mainline_sectors", []) or [])[:5]
        stock_pools.sub_mainline_sectors = list(getattr(bundle.context.sector_scan, "sub_mainline_sectors", []) or [])[:3]
        stock_pools.snapshot_status_message = None

        await review_snapshot_service.save_stock_pools_page_snapshot_safe(
            trade_date,
            self.NOTIFICATION_CANDIDATE_LIMIT,
            stock_pools,
            account_id=account_id,
        )

    async def _sync_market_event(self, account_id, *, user_id, trade_date, market_env, active_keys: set[str]) -> None:
        current_rank = self._market_rank(market_env.market_env_tag)
        changes = await notification_state_service.sync_states(
            account_id,
            state_type=self.STATE_TYPE_MARKET,
            trade_date=trade_date,
            states=[
                NotificationStateInput(
                    state_key=self.MARKET_STATE_KEY,
                    current_value=getattr(market_env.market_env_tag, "value", str(market_env.market_env_tag)),
                    current_rank=current_rank,
                    entity_type="market",
                    entity_code="market",
                    payload={"market_env_tag": getattr(market_env.market_env_tag, "value", None)},
                )
            ],
        )
        change = changes[self.MARKET_STATE_KEY]
        if change.current_rank != 2:
            return

        dedupe_key = self._dedupe_key(account_id, "market_env_downgraded", "market", trade_date)
        active_keys.add(dedupe_key)
        if change.previous_rank >= 2:
            return

        await notification_service.upsert_event(
            account_id,
            user_id=user_id,
            event_type="market_env_downgraded",
            category="market",
            priority=NotificationPriority.HIGH.value,
            title="市场转为防守，先缩手",
            message="当前环境偏防守，盘中优先处理旧仓和风险，不宜继续追新仓。",
            action_label="去市场页",
            action_target_type="route",
            action_target_payload={"route": "/market"},
            entity_type="market",
            entity_code="market",
            trade_date=trade_date,
            dedupe_key=dedupe_key,
            trigger_value={"market_env_tag": change.current_value},
        )

    async def _sync_holding_events(self, account_id, *, user_id, trade_date, sell_analysis, active_keys: set[str]) -> None:
        point_by_key = {}
        state_inputs: list[NotificationStateInput] = []

        for point in [
            *(sell_analysis.hold_positions or []),
            *(sell_analysis.reduce_positions or []),
            *(sell_analysis.sell_positions or []),
        ]:
            code = normalize_ts_code(point.ts_code)
            state_key = f"holding:{code}"
            rank = self._sell_signal_rank(point.sell_signal_tag)
            point_by_key[state_key] = point
            state_inputs.append(
                NotificationStateInput(
                    state_key=state_key,
                    current_value=getattr(point.sell_signal_tag, "value", str(point.sell_signal_tag)),
                    current_rank=rank,
                    entity_type="stock",
                    entity_code=code,
                    payload={"sell_signal_tag": getattr(point.sell_signal_tag, "value", None)},
                )
            )

        changes = await notification_state_service.sync_states(
            account_id,
            state_type=self.STATE_TYPE_HOLDING,
            trade_date=trade_date,
            states=state_inputs,
        )

        for state_key, change in changes.items():
            if change.current_rank <= 0:
                continue
            point = point_by_key.get(state_key)
            if point is None:
                continue

            code = normalize_ts_code(point.ts_code)
            if change.current_rank >= 2:
                dedupe_key = self._dedupe_key(account_id, "holding_to_sell", code, trade_date)
                active_keys.add(dedupe_key)
                if change.previous_rank >= 2:
                    continue
                await notification_service.upsert_event(
                    account_id,
                    user_id=user_id,
                    event_type="holding_to_sell",
                    category="holding",
                    priority=NotificationPriority.HIGH.value,
                    title=f"{point.stock_name}转为建议卖出",
                    message=point.sell_reason or point.sell_trigger_cond or "盘中优先退出，不再拖延。",
                    action_label="看卖点详解",
                    action_target_type="sell_analysis",
                    action_target_payload=self._stock_action_payload("/sell", "sell_analysis", point.ts_code, point.stock_name),
                    entity_type="stock",
                    entity_code=code,
                    trade_date=trade_date,
                    data_source=point.data_source,
                    dedupe_key=dedupe_key,
                    trigger_value={"sell_signal_tag": change.current_value},
                )
                continue

            dedupe_key = self._dedupe_key(account_id, "holding_to_reduce", code, trade_date)
            active_keys.add(dedupe_key)
            if change.previous_rank >= 1:
                continue
            await notification_service.upsert_event(
                account_id,
                user_id=user_id,
                event_type="holding_to_reduce",
                category="holding",
                priority=NotificationPriority.HIGH.value,
                title=f"{point.stock_name}转为建议减仓",
                message=point.sell_reason or point.sell_trigger_cond or "盘中优先先降仓防守。",
                action_label="看卖点详解",
                action_target_type="sell_analysis",
                action_target_payload=self._stock_action_payload("/sell", "sell_analysis", point.ts_code, point.stock_name),
                entity_type="stock",
                entity_code=code,
                trade_date=trade_date,
                data_source=point.data_source,
                dedupe_key=dedupe_key,
                trigger_value={"sell_signal_tag": change.current_value},
            )

    async def _sync_candidate_events(self, account_id, *, user_id, trade_date, buy_analysis, active_keys: set[str]) -> None:
        point_by_key = {}
        state_inputs: list[NotificationStateInput] = []

        for point in (buy_analysis.available_buy_points or []):
            if point.stock_pool_tag != StockPoolTag.ACCOUNT_EXECUTABLE.value:
                continue
            code = normalize_ts_code(point.ts_code)
            state_key = f"candidate:{code}"
            rank = 1
            state_value = "executable"
            execution_tag = str(getattr(point, "execution_proximity_tag", "") or "")
            execution_gap_pct = getattr(point, "execution_reference_gap_pct", None)
            if execution_tag == "接近执行位":
                rank = 2
                state_value = "near_execution"
            elif point.buy_trigger_gap_pct is not None and abs(float(point.buy_trigger_gap_pct)) <= 1.0:
                rank = 2
                state_value = "near_trigger"
            point_by_key[state_key] = point
            state_inputs.append(
                NotificationStateInput(
                    state_key=state_key,
                    current_value=state_value,
                    current_rank=rank,
                    entity_type="stock",
                    entity_code=code,
                    payload={
                        "buy_signal_tag": getattr(point.buy_signal_tag, "value", None),
                        "execution_proximity_tag": execution_tag or None,
                        "execution_reference_gap_pct": execution_gap_pct,
                        "buy_trigger_gap_pct": point.buy_trigger_gap_pct,
                    },
                )
            )

        changes = await notification_state_service.sync_states(
            account_id,
            state_type=self.STATE_TYPE_CANDIDATE,
            trade_date=trade_date,
            states=state_inputs,
        )

        for state_key, change in changes.items():
            if change.current_rank <= 0:
                continue
            point = point_by_key.get(state_key)
            if point is None:
                continue

            code = normalize_ts_code(point.ts_code)
            if change.current_rank >= 2:
                dedupe_key = self._dedupe_key(account_id, "candidate_near_trigger", code, trade_date)
                active_keys.add(dedupe_key)
                if change.previous_rank >= 2:
                    continue
                execution_tag = str(getattr(point, "execution_proximity_tag", "") or "")
                execution_gap_pct = getattr(point, "execution_reference_gap_pct", None)
                gap_pct = execution_gap_pct if execution_gap_pct is not None else point.buy_trigger_gap_pct
                gap_text = f"{float(gap_pct):+.2f}%" if gap_pct is not None else "接近"
                message = getattr(point, "execution_proximity_note", None)
                title = f"{point.stock_name}接近主买位"
                if not message:
                    if execution_tag == "接近执行位":
                        message = f"距离主买位 {gap_text}，先看确认条件和量能，不要抢动作。"
                    else:
                        message = f"距离触发位 {gap_text}，先看确认条件和量能，不要抢动作。"
                        title = f"{point.stock_name}接近触发位"
                await notification_service.upsert_event(
                    account_id,
                    user_id=user_id,
                    event_type="candidate_near_trigger",
                    category="candidate",
                    priority=NotificationPriority.MEDIUM.value,
                    title=title,
                    message=message,
                    action_label="看买点详解",
                    action_target_type="buy_analysis",
                    action_target_payload=self._stock_action_payload("/buy", "buy_analysis", point.ts_code, point.stock_name),
                    entity_type="stock",
                    entity_code=code,
                    trade_date=trade_date,
                    data_source=point.buy_data_source,
                    dedupe_key=dedupe_key,
                    trigger_value={
                        "buy_signal_tag": getattr(point.buy_signal_tag, "value", None),
                        "buy_trigger_gap_pct": point.buy_trigger_gap_pct,
                    },
                )
                continue

            dedupe_key = self._dedupe_key(account_id, "candidate_to_executable", code, trade_date)
            active_keys.add(dedupe_key)
            if change.previous_rank >= 1:
                continue
            await notification_service.upsert_event(
                account_id,
                user_id=user_id,
                event_type="candidate_to_executable",
                category="candidate",
                priority=NotificationPriority.MEDIUM.value,
                title=f"{point.stock_name}进入可执行名单",
                message=point.buy_comment or "当前已进入账户可参与池，执行前仍要等买点确认。",
                action_label="看买点详解",
                action_target_type="buy_analysis",
                action_target_payload=self._stock_action_payload("/buy", "buy_analysis", point.ts_code, point.stock_name),
                entity_type="stock",
                entity_code=code,
                trade_date=trade_date,
                data_source=point.buy_data_source,
                dedupe_key=dedupe_key,
                trigger_value={"buy_signal_tag": getattr(point.buy_signal_tag, "value", None)},
            )

    async def _sync_realtime_source_event(
        self,
        account_id,
        *,
        user_id,
        trade_date,
        buy_analysis,
        sell_analysis,
        active_keys: set[str],
    ) -> None:
        active_sources = []
        if market_data_gateway.should_use_realtime_quote(trade_date):
            active_sources = [
                *(point.buy_data_source for point in (buy_analysis.available_buy_points or [])[:3]),
                *(point.data_source for point in (sell_analysis.sell_positions or [])[:2]),
                *(point.data_source for point in (sell_analysis.reduce_positions or [])[:2]),
            ]

        degraded = bool(active_sources) and not any(self._is_live_realtime_source(source) for source in active_sources)
        changes = await notification_state_service.sync_states(
            account_id,
            state_type=self.STATE_TYPE_REALTIME,
            trade_date=trade_date,
            states=[
                NotificationStateInput(
                    state_key=self.REALTIME_STATE_KEY,
                    current_value="degraded" if degraded else "healthy",
                    current_rank=1 if degraded else 0,
                    entity_type="system",
                    entity_code=self.REALTIME_STATE_KEY,
                    payload={"sources": active_sources[:5]},
                )
            ],
        )
        change = changes[self.REALTIME_STATE_KEY]
        if change.current_rank <= 0:
            return

        dedupe_key = self._dedupe_key(account_id, "realtime_source_degraded", "system", trade_date)
        active_keys.add(dedupe_key)
        if change.previous_rank >= 1:
            return

        await notification_service.upsert_event(
            account_id,
            user_id=user_id,
            event_type="realtime_source_degraded",
            category="system",
            priority=NotificationPriority.INFO.value,
            title="实时行情暂未接通，当前是回退口径",
            message="盘中提醒正在使用最近可用口径，临场动作前请更看重确认条件，不要只看价格线。",
            action_label="去市场页",
            action_target_type="route",
            action_target_payload={"route": "/market"},
            entity_type="system",
            entity_code=self.REALTIME_STATE_KEY,
            trade_date=trade_date,
            dedupe_key=dedupe_key,
            trigger_value={"sources": active_sources[:5]},
        )

    async def sync_radar_execution_proximity_events(
        self,
        account_id: str,
        *,
        user_id: Optional[str],
        trade_date: str,
        stock_pools,
    ) -> int:
        """实时雷达：股票新进入账户池“接近执行位”时写入站内消息。"""
        if not account_id or not stock_pools:
            return 0

        point_by_key = {}
        state_inputs: list[NotificationStateInput] = []
        for stock in getattr(stock_pools, "account_executable_pool", []) or []:
            code = normalize_ts_code(getattr(stock, "ts_code", "") or "")
            if not code:
                continue
            proximity_tag = str(getattr(stock, "execution_proximity_tag", "") or "")
            is_near_execution = proximity_tag == "接近执行位"
            state_key = f"radar-execution:{code}"
            state_value = "near_execution" if is_near_execution else "account_candidate"
            rank = 2 if is_near_execution else 1
            point_by_key[state_key] = stock
            state_inputs.append(
                NotificationStateInput(
                    state_key=state_key,
                    current_value=state_value,
                    current_rank=rank,
                    entity_type="stock",
                    entity_code=code,
                    payload={
                        "stock_name": getattr(stock, "stock_name", ""),
                        "execution_proximity_tag": proximity_tag,
                        "execution_proximity_note": getattr(stock, "execution_proximity_note", None),
                        "execution_reference_gap_pct": getattr(stock, "execution_reference_gap_pct", None),
                        "next_tradeability_tag": getattr(getattr(stock, "next_tradeability_tag", None), "value", getattr(stock, "next_tradeability_tag", None)),
                    },
                )
            )

        changes = await notification_state_service.sync_states(
            account_id,
            state_type=self.STATE_TYPE_RADAR_EXECUTION,
            trade_date=trade_date,
            states=state_inputs,
        )

        active_keys: set[str] = set()
        emitted_count = 0
        for state_key, change in changes.items():
            if change.current_rank < 2:
                continue
            stock = point_by_key.get(state_key)
            if stock is None:
                continue

            code = normalize_ts_code(getattr(stock, "ts_code", "") or "")
            dedupe_key = self._dedupe_key(account_id, "radar_candidate_near_execution", code, trade_date)
            active_keys.add(dedupe_key)
            if change.previous_rank >= 2:
                continue

            gap_pct = getattr(stock, "execution_reference_gap_pct", None)
            gap_text = f"{float(gap_pct):+.2f}%" if gap_pct is not None else "接近"
            note = getattr(stock, "execution_proximity_note", None) or "已进入雷达账户池的接近执行位，先看量能和确认条件。"
            item = await notification_service.upsert_event(
                account_id,
                user_id=user_id,
                event_type="radar_candidate_near_execution",
                category="candidate",
                priority=NotificationPriority.MEDIUM.value,
                title=f"{getattr(stock, 'stock_name', code)}接近执行位",
                message=f"{note} 当前距执行参考约 {gap_text}，不要脱离买点详解直接下单。",
                action_label="看买点详解",
                action_target_type="buy_analysis",
                action_target_payload=self._stock_action_payload(
                    "/buy",
                    "buy_analysis",
                    getattr(stock, "ts_code", code),
                    getattr(stock, "stock_name", ""),
                ),
                entity_type="stock",
                entity_code=code,
                trade_date=trade_date,
                data_source=getattr(stock, "data_source", None),
                dedupe_key=dedupe_key,
                trigger_value=dict(change.payload or {}),
            )
            if item is not None:
                emitted_count += 1

        await notification_service.resolve_inactive_events(
            account_id,
            active_dedupe_keys=active_keys,
            event_types={"radar_candidate_near_execution"},
        )
        return emitted_count

    def _market_rank(self, market_env_tag) -> int:
        value = getattr(market_env_tag, "value", market_env_tag)
        if value == MarketEnvTag.DEFENSE.value:
            return 2
        if value == MarketEnvTag.NEUTRAL.value:
            return 1
        return 0

    def _sell_signal_rank(self, sell_signal_tag) -> int:
        value = getattr(sell_signal_tag, "value", sell_signal_tag)
        if value == SellSignalTag.SELL.value:
            return 2
        if value == SellSignalTag.REDUCE.value:
            return 1
        return 0

    def _is_live_realtime_source(self, source: object) -> bool:
        value = str(source or "").strip()
        return value.startswith("realtime_") and value not in self.NON_LIVE_REALTIME_SOURCES

    def _dedupe_key(self, account_id: str, event_type: str, entity_code: str, trade_date: str) -> str:
        return f"{account_id}:{event_type}:{entity_code}:{trade_date}"

    def _stock_action_payload(self, route: str, action: str, ts_code: str, stock_name: str) -> dict:
        return {
            "route": route,
            "query": {
                "notification_action": action,
                "ts_code": ts_code,
                "stock_name": stock_name,
            },
        }


notification_engine = NotificationEngine()
