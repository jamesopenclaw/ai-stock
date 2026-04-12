from datetime import datetime

from app.main import _is_market_monitor_window


def test_market_monitor_window_matches_a_share_sessions():
    assert _is_market_monitor_window(datetime(2026, 4, 13, 9, 25))
    assert _is_market_monitor_window(datetime(2026, 4, 13, 11, 30))
    assert _is_market_monitor_window(datetime(2026, 4, 13, 13, 0))
    assert _is_market_monitor_window(datetime(2026, 4, 13, 15, 0))
    assert not _is_market_monitor_window(datetime(2026, 4, 13, 9, 24))
    assert not _is_market_monitor_window(datetime(2026, 4, 13, 12, 0))
    assert not _is_market_monitor_window(datetime(2026, 4, 13, 15, 1))
    assert not _is_market_monitor_window(datetime(2026, 4, 12, 10, 0))
