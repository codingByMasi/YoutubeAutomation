from datetime import datetime

import pytest

from studio.errors import QuotaError
from studio.models import QuotaLog
from studio.youtube.quota import PACIFIC, QuotaTracker, next_reset, quota_day


def tracker(session, limit=1000, margin=100, now=datetime(2026, 11, 2, 10, 0, tzinfo=PACIFIC)):
    return QuotaTracker(session, limit, margin, clock=lambda: now)


def test_every_call_is_logged_with_cost(ctx):
    q = tracker(ctx.session)
    with q.spend("captions.insert"):
        pass
    with q.spend("videos.list"):
        pass
    rows = ctx.session.query(QuotaLog).all()
    assert [(r.endpoint, r.units, r.ok) for r in rows] == [("captions.insert", 400, True), ("videos.list", 1, True)]
    assert q.used() == 401 and q.remaining() == 1000 - 100 - 401


def test_failed_call_still_counts(ctx):
    q = tracker(ctx.session)
    with pytest.raises(RuntimeError), q.spend("thumbnails.set"):
        raise RuntimeError("boom")
    row = ctx.session.query(QuotaLog).one()
    assert row.ok is False and q.used() == 50


def test_safety_margin_blocks_before_the_call(ctx):
    q = tracker(ctx.session, limit=1000, margin=500)
    with q.spend("captions.insert"):  # 400 of 500 budget
        pass
    ran = False
    with pytest.raises(QuotaError) as e, q.spend("captions.insert"):
        ran = True
    assert not ran
    msg = str(e.value)
    assert "need 400 units, 100 left" in msg and "safety margin 500" in msg and "Wait for the reset" in msg


def test_search_and_upload_have_separate_call_buckets(ctx):
    q = QuotaTracker(ctx.session, 10000, 500, bucket_limits={"search": 2, "upload": 1})
    for _ in range(2):
        with q.spend("search.list"):
            pass
    assert q.used("units") == 0 and q.used("search") == 2
    with pytest.raises(QuotaError) as e:
        q.check({"search.list": 1})
    assert "search.list calls" in str(e.value)
    q.check({"videos.insert": 1})
    with pytest.raises(QuotaError):
        q.check({"videos.insert": 2})


def test_plan_check_sums_units(ctx):
    q = tracker(ctx.session, limit=1000, margin=500)
    q.check({"captions.insert": 1, "thumbnails.set": 2})  # 500 == budget, allowed
    with pytest.raises(QuotaError):
        q.check({"captions.insert": 1, "thumbnails.set": 3})


def test_usage_resets_on_new_pacific_day(ctx):
    day1 = datetime(2026, 11, 2, 23, 30, tzinfo=PACIFIC)
    q1 = tracker(ctx.session, now=day1)
    with q1.spend("captions.insert"):
        pass
    q2 = tracker(ctx.session, now=datetime(2026, 11, 3, 0, 5, tzinfo=PACIFIC))
    assert q1.used() == 400 and q2.used() == 0
    assert next_reset(day1).hour == 0 and next_reset(day1).day == 3
    assert quota_day(day1).isoformat() == "2026-11-02"


def test_unknown_endpoint_is_rejected(ctx):
    with pytest.raises(KeyError):
        tracker(ctx.session).check({"videos.delete": 1})
