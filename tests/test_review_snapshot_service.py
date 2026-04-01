import pytest
from types import SimpleNamespace

from app.models.review_snapshot import ReviewSnapshot
from app.models.schemas import (
    BuyPointOutput,
    BuyPointResponse,
    BuyPointType,
    BuySignalTag,
    MarketEnvTag,
    RiskLevel,
)
from app.services.review_snapshot import ReviewSnapshotService


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.execute_calls = 0
        self.commit_called = False
        self.added_rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        self.execute_calls += 1
        if self.execute_calls > 1:
            raise AssertionError("unchanged buy snapshots should not issue delete statements")
        return _ScalarResult(self._rows)

    def add_all(self, rows):
        self.added_rows.extend(rows)

    async def commit(self):
        self.commit_called = True


@pytest.mark.asyncio
async def test_save_analysis_snapshot_skips_unchanged_buy_rows(monkeypatch):
    service = ReviewSnapshotService()
    existing_rows = [
        ReviewSnapshot(
            trade_date="2026-03-29",
            account_id="acct-001",
            snapshot_type="buy_available",
            ts_code="000001.SZ",
            stock_name="平安银行",
            candidate_source_tag="量比异动",
            candidate_bucket_tag="强势确认",
            buy_signal_tag="可买",
            buy_point_type="回踩承接",
            base_price=12.34,
        ),
        ReviewSnapshot(
            trade_date="2026-03-29",
            account_id="acct-001",
            snapshot_type="buy_observe",
            ts_code="000002.SZ",
            stock_name="万科A",
            candidate_source_tag="量比异动",
            candidate_bucket_tag="趋势回踩",
            buy_signal_tag="观察",
            buy_point_type="突破",
            base_price=9.87,
        ),
    ]
    fake_session = _Session(existing_rows)
    monkeypatch.setattr(
        "app.services.review_snapshot.async_session_factory",
        lambda: fake_session,
    )

    buy_analysis = BuyPointResponse(
        trade_date="2026-03-29",
        market_env_tag=MarketEnvTag.NEUTRAL,
        available_buy_points=[
            BuyPointOutput(
                ts_code="000001.SZ",
                stock_name="平安银行",
                candidate_source_tag="量比异动",
                candidate_bucket_tag="强势确认",
                buy_signal_tag=BuySignalTag.CAN_BUY,
                buy_point_type=BuyPointType.RETRACE_SUPPORT,
                buy_trigger_cond="回踩确认",
                buy_confirm_cond="量价配合",
                buy_invalid_cond="跌破失效",
                buy_trigger_price=12.34,
                buy_risk_level=RiskLevel.MEDIUM,
                buy_account_fit="适合",
                buy_comment="测试",
            )
        ],
        observe_buy_points=[
            BuyPointOutput(
                ts_code="000002.SZ",
                stock_name="万科A",
                candidate_source_tag="量比异动",
                candidate_bucket_tag="趋势回踩",
                buy_signal_tag=BuySignalTag.OBSERVE,
                buy_point_type=BuyPointType.BREAKTHROUGH,
                buy_trigger_cond="放量突破",
                buy_confirm_cond="封板确认",
                buy_invalid_cond="跌回平台",
                buy_trigger_price=9.87,
                buy_risk_level=RiskLevel.MEDIUM,
                buy_account_fit="适合",
                buy_comment="测试",
            )
        ],
        not_buy_points=[],
        total_count=2,
    )

    saved = await service.save_analysis_snapshot(
        "2026-03-29",
        buy_analysis=buy_analysis,
        account_id="acct-001",
    )

    assert saved == 0
    assert fake_session.execute_calls == 1
    assert fake_session.commit_called is False
    assert fake_session.added_rows == []


def test_aggregate_bucket_stats_splits_add_position_decisions():
    service = ReviewSnapshotService()
    rows = [
        ReviewSnapshot(
            trade_date="2026-03-30",
            account_id="acct-001",
            snapshot_type="buy_add",
            ts_code="002463.SZ",
            stock_name="沪电股份",
            candidate_bucket_tag="趋势回踩",
            trade_mode="加仓",
            add_position_decision="可加",
            add_position_scene="回踩确认",
            base_price=30.6,
            return_1d=3.2,
            return_3d=5.8,
            return_5d=7.1,
            resolved_days=5,
        ),
        ReviewSnapshot(
            trade_date="2026-03-31",
            account_id="acct-001",
            snapshot_type="buy_add",
            ts_code="000001.SZ",
            stock_name="平安银行",
            candidate_bucket_tag="趋势回踩",
            trade_mode="加仓",
            add_position_decision="仅可小加",
            add_position_scene="回踩确认",
            base_price=12.06,
            return_1d=0.4,
            return_3d=1.0,
            return_5d=1.6,
            resolved_days=5,
        ),
    ]

    stats = service._aggregate_bucket_stats(rows)

    assert len(stats) == 2
    stats_by_decision = {item["add_position_decision"]: item for item in stats}
    assert stats_by_decision["可加"]["snapshot_type"] == "buy_add"
    assert stats_by_decision["可加"]["trade_mode"] == "加仓"
    assert stats_by_decision["可加"]["add_position_scene"] == "回踩确认"
    assert stats_by_decision["仅可小加"]["snapshot_type"] == "buy_add"
    assert stats_by_decision["仅可小加"]["trade_mode"] == "加仓"


class _ExecuteRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ExecuteScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _RefreshReadSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        return _ExecuteRowsResult(self._rows)


class _RefreshWriteSession:
    def __init__(self, rows):
        self._rows = rows
        self.commit_called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        return _ExecuteScalarsResult(self._rows)

    async def commit(self):
        self.commit_called = True


@pytest.mark.asyncio
async def test_refresh_snapshot_outcomes_batches_quote_reads_by_future_date(monkeypatch):
    service = ReviewSnapshotService()
    pending_rows = [
        SimpleNamespace(id="row-1", trade_date="2026-03-20", ts_code="000001.SZ", base_price=10.0),
        SimpleNamespace(id="row-2", trade_date="2026-03-20", ts_code="000002.SZ", base_price=20.0),
    ]
    stored_rows = [
        ReviewSnapshot(id="row-1", trade_date="2026-03-20", ts_code="000001.SZ", base_price=10.0),
        ReviewSnapshot(id="row-2", trade_date="2026-03-20", ts_code="000002.SZ", base_price=20.0),
    ]
    read_session = _RefreshReadSession(pending_rows)
    write_session = _RefreshWriteSession(stored_rows)
    sessions = iter([read_session, write_session])

    monkeypatch.setattr(
        "app.services.review_snapshot.async_session_factory",
        lambda: next(sessions),
    )
    monkeypatch.setattr(
        "app.services.review_snapshot.datetime",
        type("FakeDatetime", (), {"now": staticmethod(lambda: SimpleNamespace(strftime=lambda fmt: "2026-04-01"))}),
    )
    monkeypatch.setattr(
        "app.services.review_snapshot.market_data_gateway.get_future_trade_dates",
        lambda trade_date, count=5: ["20260321", "20260324"],
    )
    quote_calls = []

    def fake_get_stock_quote_map(ts_codes, trade_date):
        quote_calls.append((tuple(sorted(ts_codes)), trade_date))
        mapping = {
            "20260321": {
                "000001.SZ": {"close": 10.5},
                "000002.SZ": {"close": 20.4},
            },
            "20260324": {
                "000001.SZ": {"close": 11.2},
                "000002.SZ": {"close": 21.0},
            },
        }
        return mapping[trade_date]

    monkeypatch.setattr(
        "app.services.review_snapshot.market_data_gateway.get_stock_quote_map",
        fake_get_stock_quote_map,
    )

    updated = await service.refresh_snapshot_outcomes(limit_days=10, max_rows=10)

    assert updated == 2
    assert quote_calls == [
        (("000001.SZ", "000002.SZ"), "20260321"),
        (("000001.SZ", "000002.SZ"), "20260324"),
    ]
    assert stored_rows[0].resolved_days == 2
    assert stored_rows[0].return_1d == 5.0
    assert stored_rows[1].return_1d == 2.0
    assert write_session.commit_called is True
