"""Team dashboard stats helpers."""
from datetime import datetime, timezone

from backend.crm.store import (
    STATUS_PRESALES_COMPLETED,
    _lead_bucket_stats,
    period_bounds,
)


def test_period_bounds_month():
    start, end = period_bounds("month")
    assert start is not None and end is not None
    assert start.day == 1
    assert end >= start


def test_period_bounds_all():
    start, end = period_bounds("all")
    assert start is None and end is None


def test_lead_bucket_stats():
    rows = [
        {"assigned_at": "2026-07-04T10:00:00+00:00", "status": STATUS_PRESALES_COMPLETED},
        {"assigned_at": "2026-07-04T11:00:00+00:00", "status": "assigned"},
        {"assigned_at": "2026-01-01T10:00:00+00:00", "status": "assigned"},
    ]
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)
    stats = _lead_bucket_stats(rows, start, end)
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["achievement_pct"] == 50.0


def test_bi_annually_alias():
    start, _ = period_bounds("bi_annually")
    assert start is not None
