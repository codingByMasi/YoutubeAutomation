from datetime import date, datetime

import pytest

from studio.errors import StudioError
from studio.growth import channels
from studio.growth import weekly_plan as wp

MON = date(2026, 11, 2)


def test_defaults_give_four_videos_across_three_channels():
    chans = [{"id": "fin", "name": "Fin", "type": "business", "posts_per_week": 2},
             {"id": "his", "name": "His", "type": "history", "posts_per_week": 1},
             {"id": "kid", "name": "Kid", "type": "kids", "posts_per_week": 1}]
    plan = wp.build(chans, {}, MON)
    assert len(plan["rows"]) == 4 and plan["totals"]["videos"] == 4
    assert [r["when"].strftime("%a %H:%M") for r in plan["rows"]] == [
        "Tue 16:00", "Thu 16:00", "Sat 09:00", "Sun 15:00"]
    assert all(r["needs_topic"] for r in plan["rows"])


def test_due_videos_fill_slots_and_scheduled_keep_dates():
    c = [{"id": "fin", "name": "Fin", "type": "business", "posts_per_week": 2}]
    due = {"fin": [{"id": 1, "title": "A", "stage": "review", "publish_at": datetime(2026, 11, 5, 16)},
                   {"id": 2, "title": "B", "stage": "script", "publish_at": None}]}
    rows = wp.build(c, due, MON)["rows"]
    assert rows[0]["video"]["id"] == 2 and rows[1]["video"]["id"] == 1
    assert "publish 2 --at" in wp.render_markdown(wp.build(c, due, MON))


def test_profile_overrides_and_validation(root):
    cid = channels.add(root, "X", publish_days=[4, 1], publish_time="18:30", posts_per_week=2)
    p = channels.get(root, cid)
    assert p["publish_days"] == [1, 4] and wp.rhythm(p) == ([1, 4], "18:30")
    with pytest.raises(StudioError):
        channels.update(root, cid, publish_time="25:99")
    with pytest.raises(StudioError):
        channels.update(root, cid, publish_days=[9])


def test_budget_uses_measured_render_ratio():
    b = wp.budget({"type": "history", "posts_per_week": 1})
    assert b["render_min_each"] == round(8 * wp.RENDER_MIN_PER_VIDEO_MIN, 1) and b["handoffs"] == 4
