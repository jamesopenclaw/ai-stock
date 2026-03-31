"""
复盘快照与分层统计服务
"""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, delete, or_, select

from app.core.database import async_session_factory
from app.models.review_snapshot import ReviewSnapshot
from app.models.schemas import StockPoolsOutput
from app.models.stock_pool_snapshot import StockPoolSnapshot
from app.services.market_data_gateway import market_data_gateway

logger = logging.getLogger(__name__)


class ReviewSnapshotService:
    """保存每日快照并输出分层复盘统计。"""

    SNAPSHOT_TYPES = {
        "pool_market": "观察池",
        "pool_account": "可参与池",
        "buy_available": "可买",
        "buy_observe": "观察",
        "buy_add": "加仓",
    }
    BUY_SNAPSHOT_TYPES = ("buy_available", "buy_observe")
    ADD_SNAPSHOT_TYPES = ("buy_add",)
    BUY_STATS_SNAPSHOT_TYPES = BUY_SNAPSHOT_TYPES + ADD_SNAPSHOT_TYPES

    def __init__(self):
        self._outcome_refresh_task: Optional[asyncio.Task] = None

    def _normalize_account_id(self, account_id: Optional[str]) -> str:
        return str(account_id or "").strip()

    def _snapshot_signature(self, row: ReviewSnapshot) -> Tuple:
        """只比较落库字段，忽略主键和时间戳。"""
        return (
            row.snapshot_type or "",
            row.account_id or "",
            row.ts_code or "",
            row.stock_name or "",
            row.candidate_source_tag or "",
            row.candidate_bucket_tag or "",
            row.buy_signal_tag or "",
            row.buy_point_type or "",
            row.stock_pool_tag or "",
            round(float(row.stock_score or 0.0), 4),
            round(float(row.base_price or 0.0), 4),
            row.trade_mode or "",
            row.add_position_decision or "",
            int(row.add_position_score_total or 0),
            row.add_position_scene or "",
        )

    async def _analysis_snapshot_unchanged(
        self,
        session,
        trade_date: str,
        normalized_account_id: str,
        snapshot_types: Tuple[str, ...],
        rows: List[ReviewSnapshot],
    ) -> bool:
        """同一交易日快照内容未变化时跳过重写，避免反复 DELETE + INSERT。"""
        result = await session.execute(
            select(ReviewSnapshot)
            .where(ReviewSnapshot.trade_date == trade_date)
            .where(ReviewSnapshot.account_id == normalized_account_id)
            .where(ReviewSnapshot.snapshot_type.in_(snapshot_types))
        )
        existing_rows = result.scalars().all()
        if len(existing_rows) != len(rows):
            return False
        existing_signatures = sorted(self._snapshot_signature(row) for row in existing_rows)
        target_signatures = sorted(self._snapshot_signature(row) for row in rows)
        return existing_signatures == target_signatures

    def _review_snapshot_scope_clause(self, normalized_account_id: str):
        return or_(
            and_(
                ReviewSnapshot.snapshot_type == "pool_market",
                ReviewSnapshot.account_id == "",
            ),
            and_(
                ReviewSnapshot.snapshot_type != "pool_market",
                ReviewSnapshot.account_id == normalized_account_id,
            ),
        )

    async def get_stock_pools_page_snapshot(
        self,
        trade_date: str,
        candidate_limit: int,
        account_id: Optional[str] = None,
    ) -> Optional[StockPoolsOutput]:
        """读取完整三池页快照，命中后可直接返回页面结果。"""
        normalized_account_id = self._normalize_account_id(account_id)
        async with async_session_factory() as session:
            result = await session.execute(
                select(StockPoolSnapshot).where(
                    StockPoolSnapshot.trade_date == trade_date,
                    StockPoolSnapshot.candidate_limit == candidate_limit,
                    StockPoolSnapshot.account_id == normalized_account_id,
                )
            )
            row = result.scalar_one_or_none()

        if not row or not row.payload_json:
            return None

        try:
            payload = json.loads(row.payload_json)
            if row.resolved_trade_date and not payload.get("resolved_trade_date"):
                payload["resolved_trade_date"] = row.resolved_trade_date
            return StockPoolsOutput.model_validate(payload)
        except Exception as exc:
            logger.warning("三池快照反序列化失败: %s", exc)
            return None

    async def save_stock_pools_page_snapshot(
        self,
        trade_date: str,
        candidate_limit: int,
        stock_pools: StockPoolsOutput,
        account_id: Optional[str] = None,
    ) -> int:
        """保存完整三池页快照，供后续页面直接读取。"""
        normalized_account_id = self._normalize_account_id(account_id)
        payload_json = json.dumps(
            stock_pools.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )

        async with async_session_factory() as session:
            await session.execute(
                delete(StockPoolSnapshot).where(
                    StockPoolSnapshot.trade_date == trade_date,
                    StockPoolSnapshot.candidate_limit == candidate_limit,
                    StockPoolSnapshot.account_id == normalized_account_id,
                )
            )
            session.add(
                StockPoolSnapshot(
                    trade_date=trade_date,
                    account_id=normalized_account_id,
                    candidate_limit=candidate_limit,
                    resolved_trade_date=stock_pools.resolved_trade_date or "",
                    payload_json=payload_json,
                )
            )
            await session.commit()

        return 1

    async def save_stock_pools_page_snapshot_safe(
        self,
        trade_date: str,
        candidate_limit: int,
        stock_pools: StockPoolsOutput,
        account_id: Optional[str] = None,
    ) -> int:
        """安全保存完整三池页快照，失败时只记日志。"""
        try:
            snapshot_kwargs = {"account_id": account_id} if account_id else {}
            return await self.save_stock_pools_page_snapshot(
                trade_date,
                candidate_limit,
                stock_pools,
                **snapshot_kwargs,
            )
        except Exception as exc:
            logger.warning("三池页快照写入失败: %s", exc)
            return 0

    async def save_analysis_snapshot(
        self,
        trade_date: str,
        stock_pools=None,
        buy_analysis=None,
        add_position_analysis=None,
        sell_analysis=None,
        account_output=None,
        account_id: Optional[str] = None,
    ) -> int:
        """保存某交易日的候选池与买点快照，支持三池页/买点页部分写入。"""
        normalized_account_id = self._normalize_account_id(account_id)
        rows = []
        delete_targets: List[Tuple[str, str]] = []

        if stock_pools is not None:
            delete_targets.extend([
                ("pool_market", ""),
                ("pool_account", normalized_account_id),
            ])
            for stock in stock_pools.market_watch_pool:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
                        account_id="",
                        snapshot_type="pool_market",
                        ts_code=stock.ts_code,
                        stock_name=stock.stock_name,
                        candidate_source_tag=stock.candidate_source_tag,
                        candidate_bucket_tag=stock.candidate_bucket_tag,
                        stock_pool_tag=stock.stock_pool_tag.value,
                        stock_score=stock.stock_score,
                        base_price=stock.close or 0.0,
                    )
                )

            for stock in stock_pools.account_executable_pool:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
                        account_id=normalized_account_id,
                        snapshot_type="pool_account",
                        ts_code=stock.ts_code,
                        stock_name=stock.stock_name,
                        candidate_source_tag=stock.candidate_source_tag,
                        candidate_bucket_tag=stock.candidate_bucket_tag,
                        stock_pool_tag=stock.stock_pool_tag.value,
                        stock_score=stock.stock_score,
                        base_price=stock.close or 0.0,
                    )
                )

        if buy_analysis is not None:
            delete_targets.extend([
                ("buy_available", normalized_account_id),
                ("buy_observe", normalized_account_id),
            ])
            for bp in buy_analysis.available_buy_points:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
                        account_id=normalized_account_id,
                        snapshot_type="buy_available",
                        ts_code=bp.ts_code,
                        stock_name=bp.stock_name,
                        candidate_source_tag=bp.candidate_source_tag,
                        candidate_bucket_tag=bp.candidate_bucket_tag,
                        buy_signal_tag=bp.buy_signal_tag.value,
                        buy_point_type=bp.buy_point_type.value,
                        base_price=bp.buy_trigger_price or 0.0,
                    )
                )

            for bp in buy_analysis.observe_buy_points:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
                        account_id=normalized_account_id,
                        snapshot_type="buy_observe",
                        ts_code=bp.ts_code,
                        stock_name=bp.stock_name,
                        candidate_source_tag=bp.candidate_source_tag,
                        candidate_bucket_tag=bp.candidate_bucket_tag,
                        buy_signal_tag=bp.buy_signal_tag.value,
                        buy_point_type=bp.buy_point_type.value,
                        base_price=bp.buy_trigger_price or 0.0,
                    )
                )

        if add_position_analysis is not None:
            delete_targets.append(("buy_add", normalized_account_id))
            for item in add_position_analysis:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
                        account_id=normalized_account_id,
                        snapshot_type="buy_add",
                        ts_code=item.get("ts_code", ""),
                        stock_name=item.get("stock_name", ""),
                        candidate_source_tag=item.get("candidate_source_tag", "") or "",
                        candidate_bucket_tag=item.get("candidate_bucket_tag", "") or "",
                        buy_signal_tag=item.get("buy_signal_tag", "") or "",
                        buy_point_type=item.get("buy_point_type", "") or "",
                        stock_score=float(item.get("stock_score") or 0.0),
                        base_price=float(item.get("base_price") or 0.0),
                        trade_mode=item.get("trade_mode", "") or "",
                        add_position_decision=item.get("add_position_decision", "") or "",
                        add_position_score_total=int(item.get("add_position_score_total") or 0),
                        add_position_scene=item.get("add_position_scene", "") or "",
                    )
                )

        if not delete_targets:
            return 0

        async with async_session_factory() as session:
            if stock_pools is None:
                analysis_rows = [
                    row
                    for row in rows
                    if row.snapshot_type in self.BUY_STATS_SNAPSHOT_TYPES
                ]
                analysis_snapshot_types = tuple(
                    sorted({row.snapshot_type for row in analysis_rows})
                )
                if analysis_rows and analysis_snapshot_types:
                    if await self._analysis_snapshot_unchanged(
                        session,
                        trade_date,
                        normalized_account_id,
                        analysis_snapshot_types,
                        analysis_rows,
                    ):
                        return 0
            for snapshot_type, target_account_id in delete_targets:
                await session.execute(
                    delete(ReviewSnapshot)
                    .where(ReviewSnapshot.trade_date == trade_date)
                    .where(ReviewSnapshot.snapshot_type == snapshot_type)
                    .where(ReviewSnapshot.account_id == target_account_id)
                )
            if rows:
                session.add_all(rows)
            await session.commit()

        return len(rows)

    async def save_analysis_snapshot_safe(
        self,
        trade_date: str,
        stock_pools=None,
        buy_analysis=None,
        add_position_analysis=None,
        account_id: Optional[str] = None,
    ) -> int:
        """安全保存分析快照，失败时只记日志。"""
        try:
            snapshot_kwargs = {"account_id": account_id} if account_id else {}
            return await self.save_analysis_snapshot(
                trade_date,
                stock_pools=stock_pools,
                buy_analysis=buy_analysis,
                add_position_analysis=add_position_analysis,
                **snapshot_kwargs,
            )
        except Exception as exc:
            logger.warning("分析快照写入失败: %s", exc)
            return 0

    async def refresh_snapshot_outcomes(
        self,
        limit_days: int = 20,
        max_rows: Optional[int] = None,
    ) -> int:
        """补齐未计算的 1/3/5 日表现。"""
        updated = 0
        today = datetime.now().strftime("%Y-%m-%d")

        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    ReviewSnapshot.id,
                    ReviewSnapshot.trade_date,
                    ReviewSnapshot.ts_code,
                    ReviewSnapshot.base_price,
                )
                .where(ReviewSnapshot.resolved_days < 5)
                .order_by(ReviewSnapshot.trade_date.asc(), ReviewSnapshot.id.asc())
                .limit(max_rows or (limit_days * 200))
            )
            rows = [
                {
                    "id": row.id,
                    "trade_date": row.trade_date,
                    "ts_code": row.ts_code,
                    "base_price": float(row.base_price or 0),
                }
                for row in result.all()
            ]

        updates = []
        for row in rows:
            if row["trade_date"] >= today:
                continue
            compact = row["trade_date"].replace("-", "")
            future_dates = market_data_gateway.get_future_trade_dates(compact, count=5)
            if not future_dates:
                continue

            closes: List[float] = []
            for d in future_dates:
                detail = market_data_gateway.get_stock_detail(row["ts_code"], d)
                close = float(detail.get("close") or 0)
                if close > 0:
                    closes.append(close)

            if not closes or row["base_price"] <= 0:
                continue

            payload = {
                "id": row["id"],
                "resolved_days": len(closes),
            }
            if len(closes) >= 1:
                payload["return_1d"] = round((closes[0] - row["base_price"]) / row["base_price"] * 100, 2)
            if len(closes) >= 3:
                payload["return_3d"] = round((closes[2] - row["base_price"]) / row["base_price"] * 100, 2)
            if len(closes) >= 5:
                payload["return_5d"] = round((closes[4] - row["base_price"]) / row["base_price"] * 100, 2)
            updates.append(payload)

        if not updates:
            return 0

        async with async_session_factory() as session:
            result = await session.execute(
                select(ReviewSnapshot).where(
                    ReviewSnapshot.id.in_([item["id"] for item in updates])
                )
            )
            row_map = {row.id: row for row in result.scalars().all()}

            for payload in updates:
                row = row_map.get(payload["id"])
                if not row:
                    continue
                row.return_1d = float(payload.get("return_1d") or 0)
                row.return_3d = float(payload.get("return_3d") or 0)
                row.return_5d = float(payload.get("return_5d") or 0)
                row.resolved_days = int(payload["resolved_days"])
                updated += 1

            if updated:
                await session.commit()

        return updated

    def is_refresh_running(self) -> bool:
        """当前是否正在后台补齐复盘收益。"""
        return bool(self._outcome_refresh_task and not self._outcome_refresh_task.done())

    def ensure_background_refresh(self, limit_days: int = 20) -> bool:
        """如未运行，则在后台启动一次收益补齐。"""
        if self.is_refresh_running():
            return False

        async def _runner():
            try:
                total_updated = 0
                while True:
                    updated = await self.refresh_snapshot_outcomes(
                        limit_days=limit_days,
                        max_rows=10,
                    )
                    total_updated += updated
                    if updated <= 0:
                        break
                    await asyncio.sleep(0.2)
                logger.info("复盘收益后台补齐完成，累计更新 %s 条快照", total_updated)
            except Exception as exc:
                logger.warning("复盘收益后台补齐失败: %s", exc)
            finally:
                self._outcome_refresh_task = None

        self._outcome_refresh_task = asyncio.create_task(_runner())
        return True

    def _aggregate_bucket_stats(self, rows: Iterable[ReviewSnapshot]) -> List[Dict]:
        """聚合分层统计。"""
        stats = defaultdict(
            lambda: {
                "candidate_bucket_tag": "",
                "snapshot_type": "",
                "trade_mode": "",
                "add_position_decision": "",
                "add_position_scene": "",
                "count": 0,
                "resolved_1d_count": 0,
                "resolved_3d_count": 0,
                "resolved_5d_count": 0,
                "avg_return_1d": 0.0,
                "avg_return_3d": 0.0,
                "avg_return_5d": 0.0,
                "win_rate_1d": 0.0,
                "win_rate_3d": 0.0,
                "win_rate_5d": 0.0,
                "_sum_1d": 0.0,
                "_sum_3d": 0.0,
                "_sum_5d": 0.0,
                "_win_1d": 0,
                "_win_3d": 0,
                "_win_5d": 0,
            }
        )

        for row in rows:
            key = (
                row.snapshot_type,
                row.candidate_bucket_tag or "未分层",
                row.add_position_decision or "",
            )
            item = stats[key]
            item["snapshot_type"] = key[0]
            item["candidate_bucket_tag"] = key[1]
            item["trade_mode"] = row.trade_mode or ""
            item["add_position_decision"] = key[2]
            item["add_position_scene"] = row.add_position_scene or ""
            item["count"] += 1
            if row.resolved_days >= 1:
                item["resolved_1d_count"] += 1
                item["_sum_1d"] += row.return_1d
                if row.return_1d > 0:
                    item["_win_1d"] += 1
            if row.resolved_days >= 3:
                item["resolved_3d_count"] += 1
                item["_sum_3d"] += row.return_3d
                if row.return_3d > 0:
                    item["_win_3d"] += 1
            if row.resolved_days >= 5:
                item["resolved_5d_count"] += 1
                item["_sum_5d"] += row.return_5d
                if row.return_5d > 0:
                    item["_win_5d"] += 1

        result = []
        for item in stats.values():
            if item["resolved_1d_count"] > 0:
                item["avg_return_1d"] = round(item["_sum_1d"] / item["resolved_1d_count"], 2)
                item["win_rate_1d"] = round(item["_win_1d"] / item["resolved_1d_count"] * 100, 2)
            if item["resolved_3d_count"] > 0:
                item["avg_return_3d"] = round(item["_sum_3d"] / item["resolved_3d_count"], 2)
                item["win_rate_3d"] = round(item["_win_3d"] / item["resolved_3d_count"] * 100, 2)
            if item["resolved_5d_count"] > 0:
                item["avg_return_5d"] = round(item["_sum_5d"] / item["resolved_5d_count"], 2)
                item["win_rate_5d"] = round(item["_win_5d"] / item["resolved_5d_count"] * 100, 2)
            del item["_sum_1d"]
            del item["_sum_3d"]
            del item["_sum_5d"]
            del item["_win_1d"]
            del item["_win_3d"]
            del item["_win_5d"]
            result.append(item)

        result.sort(key=lambda x: (x["snapshot_type"], x["count"]), reverse=False)
        return result

    def _resolved_window_and_metrics(self, item: Dict) -> Tuple[int, float, float]:
        if item["resolved_5d_count"] > 0:
            return 5, float(item["avg_return_5d"] or 0), float(item["win_rate_5d"] or 0)
        if item["resolved_3d_count"] > 0:
            return 3, float(item["avg_return_3d"] or 0), float(item["win_rate_3d"] or 0)
        if item["resolved_1d_count"] > 0:
            return 1, float(item["avg_return_1d"] or 0), float(item["win_rate_1d"] or 0)
        return 0, 0.0, 0.0

    def _build_bias_entry(self, item: Dict) -> Optional[Dict]:
        window, avg_return, win_rate = self._resolved_window_and_metrics(item)
        resolved_count = int(
            item["resolved_5d_count"] or item["resolved_3d_count"] or item["resolved_1d_count"] or 0
        )
        if window <= 0 or resolved_count < 2:
            return None

        raw_score = avg_return * 0.8 + (win_rate - 50.0) * 0.08
        confidence = min(1.0, resolved_count / 8.0)
        score = round(max(-8.0, min(8.0, raw_score * confidence)), 2)
        if score >= 2:
            label = "复盘加分"
        elif score <= -2:
            label = "复盘降权"
        else:
            label = "复盘中性"
        return {
            "score": score,
            "label": label,
            "reason": (
                f"最近{window}日该类信号样本{resolved_count}条，均值{avg_return:.2f}%，"
                f"胜率{win_rate:.2f}%，当前判定为{label}。"
            ),
            "resolved_count": resolved_count,
        }

    def _build_review_bias_profile_from_rows(self, rows: Iterable[ReviewSnapshot]) -> Dict:
        bucket_stats = self._aggregate_bucket_stats(rows)
        exact: Dict[Tuple[str, str], Dict] = {}
        bucket_rollup: Dict[str, Dict] = {}

        for item in bucket_stats:
            entry = self._build_bias_entry(item)
            if not entry:
                continue
            bucket = item["candidate_bucket_tag"] or "未分层"
            exact[(item["snapshot_type"], bucket)] = entry

            current = bucket_rollup.get(bucket)
            if current is None or (
                entry["resolved_count"], abs(entry["score"])
            ) > (current["resolved_count"], abs(current["score"])):
                bucket_rollup[bucket] = entry

        return {"exact": exact, "bucket": bucket_rollup}

    async def get_review_bias_profile(self, limit_days: int = 10, account_id: Optional[str] = None) -> Dict:
        """为三池/买点排序提供复盘反馈画像。"""
        normalized_account_id = self._normalize_account_id(account_id)
        async with async_session_factory() as session:
            date_rows = await session.execute(
                select(ReviewSnapshot.trade_date)
                .distinct()
                .where(self._review_snapshot_scope_clause(normalized_account_id))
                .order_by(ReviewSnapshot.trade_date.desc())
                .limit(limit_days)
            )
            trade_dates = [row[0] for row in date_rows.all()]
            if not trade_dates:
                return {"exact": {}, "bucket": {}}

            result = await session.execute(
                select(ReviewSnapshot)
                .where(ReviewSnapshot.trade_date.in_(trade_dates))
                .where(
                    ReviewSnapshot.snapshot_type.in_(
                        ["buy_available", "buy_observe", "pool_account", "pool_market"]
                    )
                )
                .where(self._review_snapshot_scope_clause(normalized_account_id))
            )
            rows = result.scalars().all()

        if not rows:
            return {"exact": {}, "bucket": {}}
        return self._build_review_bias_profile_from_rows(rows)

    async def get_review_bias_profile_safe(self, limit_days: int = 10, account_id: Optional[str] = None) -> Dict:
        """安全读取复盘反馈画像，失败时回退为空画像而不影响主流程。"""
        try:
            return await self.get_review_bias_profile(limit_days=limit_days, account_id=account_id)
        except Exception as exc:
            logger.warning("读取复盘反馈画像失败，已降级为空画像: %s", exc)
            return {"exact": {}, "bucket": {}}

    async def get_review_stats(
        self,
        limit_days: int = 10,
        refresh_outcomes: bool = False,
        account_id: Optional[str] = None,
    ) -> Dict:
        """获取最近 N 个交易日的分层复盘统计。"""
        normalized_account_id = self._normalize_account_id(account_id)
        refreshed_count = 0
        if refresh_outcomes:
            refreshed_count = await self.refresh_snapshot_outcomes(limit_days=limit_days)

        async with async_session_factory() as session:
            pending_1d_rows = await session.execute(
                select(ReviewSnapshot.id)
                .where(ReviewSnapshot.resolved_days < 1)
                .where(self._review_snapshot_scope_clause(normalized_account_id))
            )
            pending_3d_rows = await session.execute(
                select(ReviewSnapshot.id)
                .where(ReviewSnapshot.resolved_days < 3)
                .where(self._review_snapshot_scope_clause(normalized_account_id))
            )
            pending_5d_rows = await session.execute(
                select(ReviewSnapshot.id)
                .where(ReviewSnapshot.resolved_days < 5)
                .where(self._review_snapshot_scope_clause(normalized_account_id))
            )
            pending_1d_count = len(pending_1d_rows.all())
            pending_3d_count = len(pending_3d_rows.all())
            pending_5d_count = len(pending_5d_rows.all())

            date_rows = await session.execute(
                select(ReviewSnapshot.trade_date)
                .distinct()
                .where(self._review_snapshot_scope_clause(normalized_account_id))
                .order_by(ReviewSnapshot.trade_date.desc())
                .limit(limit_days)
            )
            trade_dates = [row[0] for row in date_rows.all()]
            if not trade_dates:
                return {"trade_dates": [], "bucket_stats": [], "snapshot_count": 0}

            result = await session.execute(
                select(ReviewSnapshot)
                .where(ReviewSnapshot.trade_date.in_(trade_dates))
                .where(ReviewSnapshot.snapshot_type.in_(self.BUY_STATS_SNAPSHOT_TYPES))
                .where(self._review_snapshot_scope_clause(normalized_account_id))
            )
            rows = result.scalars().all()
            stats_mode = "buy"

            if not rows:
                result = await session.execute(
                    select(ReviewSnapshot)
                    .where(ReviewSnapshot.trade_date.in_(trade_dates))
                    .where(ReviewSnapshot.snapshot_type.in_(["pool_account", "pool_market"]))
                    .where(self._review_snapshot_scope_clause(normalized_account_id))
                )
                rows = result.scalars().all()
                stats_mode = "pool"

        return {
            "trade_dates": sorted(trade_dates),
            "snapshot_count": len(rows),
            "bucket_stats": self._aggregate_bucket_stats(rows),
            "stats_mode": stats_mode,
            "pending_outcome_count": pending_5d_count,
            "pending_1d_count": pending_1d_count,
            "pending_3d_count": pending_3d_count,
            "pending_5d_count": pending_5d_count,
            "refreshed_outcome_count": refreshed_count,
            "refresh_in_progress": self.is_refresh_running(),
        }


review_snapshot_service = ReviewSnapshotService()
