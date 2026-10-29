import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from studio.errors import PendingLLMResponse
from studio.manage import ab_log, analytics_report, calendar, comments, run_all, status
from studio.models import ABTest, CommentDraft, Idea, MetricDaily, QuotaLog, Title, Video, utcnow
from tests.conftest import Answers
from tests.fakes import FakeService

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def live_video(ctx, yt_id="yt1", stage="scheduled", publish_at=None):
    idea = Idea(seed="s", topic="how coffee shops make money", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage=stage, youtube_video_id=yt_id,
              publish_at=publish_at or datetime(2026, 10, 6, 18))
    ctx.session.add(v)
    ctx.session.flush()
    ctx.session.add(Title(video_id=v.id, text="How a Coffee Shop Really Makes Money", style="how-x-really-works",
                          length=36, is_pick=True))
    ctx.session.commit()
    (ctx.settings.project_dir(v.id) / "script.json").write_text(json.dumps(dict(SAMPLE, build={"duration": 600})))
    return v


def use_fakes(ctx, data=None, analytics=None):
    (ctx.settings.root / "client_secret.json").write_text("{}")
    ctx.settings.channel_id = "UC1"
    data, analytics = data or FakeService(), analytics or FakeService()
    ctx.youtube_factory = lambda: (data, analytics)
    return data, analytics


# ---------- analytics ----------
def analytics_service():
    def query(**kw):
        dims, metrics = kw.get("dimensions"), kw["metrics"]
        if dims == "day" and metrics.startswith("views"):
            return {"columnHeaders": [{"name": n} for n in ("day", "views", "estimatedMinutesWatched",
                                                                "averageViewDuration")],
                    "rows": [["2026-10-20", 100, 300.0, 180], ["2026-10-21", 140, 420.0, 200]]}
        if dims == "day" and "Thumbnail" in metrics:
            raise RuntimeError("Unknown identifier (videoThumbnailImpressions)")
        if dims == "day,insightTrafficSourceType":
            return {"columnHeaders": [{"name": "day"}, {"name": "insightTrafficSourceType"}, {"name": "views"}],
                    "rows": [["2026-10-20", "YT_SEARCH", 60], ["2026-10-20", "SUGGESTED", 40]]}
        if dims == "elapsedVideoTimeRatio":
            return {"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}],
                    "rows": [[0.01, 1.0], [0.1, 0.8], [0.2, 0.75], [0.3, 0.45], [0.4, 0.42]]}
        return {}
    return FakeService({"reports.query": query})


def test_analytics_stores_metrics_and_writes_report(ctx):
    live_video(ctx)
    use_fakes(ctx, analytics=analytics_service())
    out = analytics_report.run(ctx, days=28, today=date(2026, 10, 28))
    rows = ctx.session.query(MetricDaily).order_by(MetricDaily.date).all()
    assert [r.views for r in rows] == [100, 140] and rows[0].ctr is None
    assert json.loads(rows[0].traffic_json) == {"YT_SEARCH": 60, "SUGGESTED": 40}
    text = out.read_text()
    for part in ("Best topics", "Title styles", "Video lengths", "Upload days", "Where viewers leave",
                 "What to make next", "3:00", "CTR are not available"):
        assert part in text
    # re-running replaces rows instead of duplicating them
    analytics_report.run(ctx, days=28, today=date(2026, 10, 28))
    assert ctx.session.query(MetricDaily).count() == 2
    assert ctx.session.query(QuotaLog).filter_by(endpoint="analytics.reports.query").count() > 0


def test_report_with_no_videos():
    assert "No published videos" in analytics_report.build_report([], [], 28)


def test_biggest_drop():
    assert analytics_report.biggest_drop([(0.0, 1), (0.1, 0.9), (0.5, 0.4), (0.6, 0.38)], 600) == (300.0, 0.5)


# ---------- ab-log ----------
def test_ab_log_records_change_with_before_metrics(ctx):
    v = live_video(ctx)
    today = utcnow().date()
    for i in range(1, 4):
        ctx.session.add(MetricDaily(youtube_video_id="yt1", date=today - timedelta(days=i), views=10 * i,
                                    watch_minutes=1, avg_view_duration=100, ctr=4.0))
    ctx.session.commit()
    ab_log.run(ctx, v.id, field="title", new="The Economics of a $5 Latte", old="Old title")
    t = ctx.session.query(ABTest).one()
    assert t.old_value == "Old title" and json.loads(t.metrics_before_json)["views_per_day"] == 20
    assert ctx.session.query(Title).filter_by(video_id=v.id, is_live=True).one().text.startswith("The Economics")


# ---------- comments ----------
def comment_service():
    threads = {"items": [
        {"snippet": {"topLevelComment": {"id": "c1", "snippet": {"textDisplay": "Great breakdown!"}}}},
        {"snippet": {"topLevelComment": {"id": "c2", "snippet": {"textDisplay": "Rent is higher in my city"}}}},
    ]}
    return FakeService({"commentThreads.list": lambda **kw: threads, "comments.insert": lambda **kw: {"id": "r"}})


def test_comment_drafts_never_post(ctx):
    v = live_video(ctx)
    data, _ = use_fakes(ctx, data=comment_service())
    with pytest.raises(PendingLLMResponse):
        comments.draft(ctx, v.id)
    prompts = list((ctx.settings.project_dir(v.id) / "prompts").glob("comments_*.prompt.md"))
    assert len(prompts) == 1 and "c2: Rent is higher" in prompts[0].read_text()
    resp = prompts[0].with_name(prompts[0].name.replace(".prompt.md", ".response.json"))
    resp.write_text(json.dumps({"replies": [{"comment_id": "c1", "reply": "Thanks for watching!"},
                                            {"comment_id": "c2", "reply": "Good point, rent varies a lot."}]}))
    out = comments.draft(ctx, v.id)
    assert len(json.loads(out.read_text())) == 2
    assert "comments.insert" not in data.names()


def test_comment_post_needs_yes_per_reply(ctx):
    v = live_video(ctx)
    data, _ = use_fakes(ctx, data=comment_service())
    for cid, reply in (("c1", "Thanks!"), ("c2", "Good point.")):
        ctx.session.add(CommentDraft(video_id=v.id, youtube_comment_id=cid, comment_text="x", draft_reply=reply,
                                     status="drafted"))
    ctx.session.commit()
    f = ctx.settings.project_dir(v.id) / "d.json"
    f.write_text(json.dumps([{"id": c.id, "reply": c.draft_reply} for c in ctx.session.query(CommentDraft)]))
    ctx.confirm = Answers("yes", "no")
    assert comments.post(ctx, str(f)) == 1
    assert data.names().count("comments.insert") == 1
    assert [c.status for c in ctx.session.query(CommentDraft).order_by(CommentDraft.id)] == ["posted", "drafted"]
    ctx.confirm = Answers("yes")
    assert comments.post(ctx, str(f)) == 1  # the skipped one; the posted one is never re-posted
    assert data.names().count("comments.insert") == 2


# ---------- calendar ----------
def test_calendar_fills_slots_and_flags_gaps():
    start = date(2026, 11, 2)  # Monday
    rows = calendar.plan(start, 4, [(date(2026, 11, 3), "A")], ["B", "C"])
    longs = [r for r in rows if r[1] == "long"]
    assert len(longs) == 8 and len([r for r in rows if r[1] == "short"]) == 12
    assert longs[0][2] == "A (scheduled)" and longs[1][2] == "B" and longs[2][2] == "C"
    assert sum(1 for r in longs if r[2] == "GAP") == 5
    shorts = [r for r in rows if r[1] == "short"]
    assert shorts[0][2] == "GAP"  # Monday before any long video is out
    assert shorts[1][2].startswith("Short from: A")


def test_calendar_command_writes_file(ctx):
    live_video(ctx, publish_at=datetime(2026, 11, 3, 18))
    out = calendar.run(ctx, today=date(2026, 11, 2))
    assert "(scheduled)" in out.read_text() and "GAP" in out.read_text()


# ---------- status ----------
def test_status_sync_marks_public_videos_live(ctx):
    v = live_video(ctx)
    data, _ = use_fakes(ctx, data=FakeService({"videos.list": lambda **kw: {
        "items": [{"id": "yt1", "status": {"privacyStatus": "public"}}]}}))
    status.run(ctx, sync=True)
    assert v.stage == "live"


def test_status_lists_videos(ctx, capsys):
    live_video(ctx)
    status.run(ctx)
    out = capsys.readouterr().out
    assert "scheduled" in out and "How a Coffee Shop" in out and "Quota today" in out


# ---------- run-all ----------
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_run_all_stops_at_review_gate(ctx, monkeypatch):
    from studio.providers.tts import SilentTTS
    from studio.stages import research, visuals, voice

    monkeypatch.setattr(research, "fetch_suggestions", lambda seed: [seed, "how coffee shops make money"])
    monkeypatch.setattr(voice, "get_tts", lambda settings: SilentTTS())

    class NoStock:
        def __init__(self, *a, **k):
            pass

        def find(self, keywords, exclude):
            return None
    monkeypatch.setattr(visuals, "make_footage", lambda settings: ("pexels", NoStock()))
    yt = FakeService({
        "search.list": lambda **kw: {"items": [{"id": {"videoId": "v1"}}]},
        "videos.list": lambda **kw: {"items": [{"id": "v1", "snippet": {"title": "How Coffee Shops Make Money",
                                                                       "channelId": "ch1"},
                                                "statistics": {"viewCount": "90000"}}]},
        "channels.list": lambda **kw: {"items": [{"id": "ch1", "statistics": {"subscriberCount": "3000"}}]},
    })
    use_fakes(ctx, data=yt)
    ctx.confirm = Answers()

    with pytest.raises(PendingLLMResponse):
        run_all.run(ctx, "coffee shop economics")
    v = ctx.session.query(Video).one()
    (ctx.settings.project_dir(v.id) / "prompts" / "script.response.json").write_text(json.dumps(SAMPLE))
    run_all.run(ctx, "coffee shop economics")
    assert v.stage == "thumbnailed"
    out = ctx.settings.project_dir(v.id)
    assert (out / "final.mp4").stat().st_size > 10_000 and len(list((out / "thumbs").glob("thumb_*.jpg"))) == 3
    assert ctx.confirm.asked == []                       # never reached the review prompt
    assert "videos.insert" not in yt.names()             # never uploaded
    assert yt.names().count("search.list") == 1          # second run reused today's research
    assert not (out / "review.json").exists()
