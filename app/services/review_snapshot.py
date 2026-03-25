"""
复盘快照与分层统计服务
"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List

from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.data.tushare_client import tushare_client
from app.models.review_snapshot import ReviewSnapshot


class ReviewSnapshotService:
    """保存每日快照并输出分层复盘统计。"""

    SNAPSHOT_TYPES = {
        "pool_market": "观察池",
        "pool_account": "可参与池",
        "buy_available": "可买",
        "buy_observe": "观察",
    }

    async def save_analysis_snapshot(self, trade_date: str, stock_pools=None, buy_analysis=None) -> int:
        """保存某交易日的候选池与买点快照，支持三池页/买点页部分写入。"""
        rows = []
        snapshot_types_to_replace = []

        if stock_pools is not None:
            snapshot_types_to_replace.extend(["pool_market", "pool_account"])
            for stock in stock_pools.market_watch_pool:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
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
            snapshot_types_to_replace.extend(["buy_available", "buy_observe"])
            for bp in buy_analysis.available_buy_points:
                rows.append(
                    ReviewSnapshot(
                        trade_date=trade_date,
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

        if not snapshot_types_to_replace:
            return 0

        async with async_session_factory() as session:
            await session.execute(
                delete(ReviewSnapshot)
                .where(ReviewSnapshot.trade_date == trade_date)
                .where(ReviewSnapshot.snapshot_type.in_(snapshot_types_to_replace))
            )
            if rows:
                session.add_all(rows)
            await session.commit()

        return len(rows)

    async def refresh_snapshot_outcomes(self, limit_days: int = 20) -> int:
        """补齐未计算的 1/3/5 日表现。"""
        updated = 0
        today = datetime.now().strftime("%Y-%m-%d")

        async with async_session_factory() as session:
            result = await session.execute(
                select(ReviewSnapshot)
                .where(ReviewSnapshot.resolved_days < 5)
                .order_by(ReviewSnapshot.trade_date.desc())
                .limit(limit_days * 200)
            )
            rows = result.scalars().all()

            for row in rows:
                if row.trade_date >= today:
                    continue
                compact = row.trade_date.replace("-", "")
                future_dates = tushare_client.get_future_trade_dates(compact, count=5)
                if not future_dates:
                    continue

                closes: List[float] = []
                for d in future_dates:
                    detail = tushare_client.get_stock_detail(row.ts_code, d)
                    close = float(detail.get("close") or 0)
                    if close > 0:
                        closes.append(close)

                if not closes or row.base_price <= 0:
                    continue

                if len(closes) >= 1:
                    row.return_1d = round((closes[0] - row.base_price) / row.base_price * 100, 2)
                if len(closes) >= 3:
                    row.return_3d = round((closes[2] - row.base_price) / row.base_price * 100, 2)
                if len(closes) >= 5:
                    row.return_5d = round((closes[4] - row.base_price) / row.base_price * 100, 2)
                row.resolved_days = len(closes)
                updated += 1

            if updated:
                await session.commit()

        return updated

    def _aggregate_bucket_stats(self, rows: Iterable[ReviewSnapshot]) -> List[Dict]:
        """聚合分层统计。"""
        stats = defaultdict(
            lambda: {
                "candidate_bucket_tag": "",
                "snapshot_type": "",
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
            key = (row.snapshot_type, row.candidate_bucket_tag or "未分层")
            item = stats[key]
            item["candidate_bucket_tag"] = key[1]
            item["snapshot_type"] = key[0]
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

    async def get_review_stats(self, limit_days: int = 10) -> Dict:
        """获取最近 N 个交易日的分层复盘统计。"""
        await self.refresh_snapshot_outcomes(limit_days=limit_days)

        async with async_session_factory() as session:
            date_rows = await session.execute(
                select(ReviewSnapshot.trade_date)
                .distinct()
                .order_by(ReviewSnapshot.trade_date.desc())
                .limit(limit_days)
            )
            trade_dates = [row[0] for row in date_rows.all()]
            if not trade_dates:
                return {"trade_dates": [], "bucket_stats": [], "snapshot_count": 0}

            result = await session.execute(
                select(ReviewSnapshot)
                .where(ReviewSnapshot.trade_date.in_(trade_dates))
                .where(ReviewSnapshot.snapshot_type.in_(["buy_available", "buy_observe"]))
            )
            rows = result.scalars().all()
            stats_mode = "buy"

            if not rows:
                result = await session.execute(
                    select(ReviewSnapshot)
                    .where(ReviewSnapshot.trade_date.in_(trade_dates))
                    .where(ReviewSnapshot.snapshot_type.in_(["pool_account", "pool_market"]))
                )
                rows = result.scalars().all()
                stats_mode = "pool"

        return {
            "trade_dates": sorted(trade_dates),
            "snapshot_count": len(rows),
            "bucket_stats": self._aggregate_bucket_stats(rows),
            "stats_mode": stats_mode,
        }


review_snapshot_service = ReviewSnapshotService()
