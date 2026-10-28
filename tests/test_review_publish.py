import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from studio.errors import GateError, StageError, StudioError
from studio.models import Asset, Idea, Video
from studio.stages import publish, review
from studio.stages.thumbnail import save_under_limit
from tests.conftest import Answers
from tests.fakes import FakeService

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def ready_video(ctx, stage="thumbnailed", licence="Pexels License"):
    idea = Idea(seed="s", topic="t", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage=stage)
    ctx.session.add(v)
    ctx.session.commit()
    out = ctx.settings.project_dir(v.id)
    pkg = dict(SAMPLE, segments=[dict(s, real_seconds=12) for s in SAMPLE["segments"]],
               build={"intro_seconds": 0, "duration": 72})
    (out / "script.json").write_text(json.dumps(pkg))
    (out / "final.mp4").write_bytes(b"\x00" * 1000)
    (out / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    (out / "thumbs").mkdir()
    for i in (1, 2, 3):
        save_under_limit(Image.new("RGB", (1280, 720), "navy"), out / "thumbs" / f"thumb_{i}.jpg")
    ctx.session.add(Asset(video_id=v.id, kind="clip", path=str(out / "c.mp4"), licence=licence,
                          attribution_url="https://pexels.com/v/1"))
    ctx.session.commit()
    return v


# ---------- review ----------
def test_review_requires_typed_yes(ctx):
    v = ready_video(ctx)
    ctx.confirm = Answers("y")
    with pytest.raises(GateError):
        review.run(ctx, v.id)
    assert v.stage == "thumbnailed" and not (ctx.settings.project_dir(v.id) / "review.json").exists()
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    assert v.stage == "reviewed"
    data = json.loads((ctx.settings.project_dir(v.id) / "review.json").read_text())
    assert data["title"].startswith("How a Coffee Shop") and data["video_sha256"]
    assert "not financial advice" in data["description"] and "Chapters\n0:00" in data["description"]
    assert "Pexels" in data["description"]


def test_review_fails_on_unknown_licence_without_asking(ctx):
    v = ready_video(ctx, licence="unknown")
    ctx.confirm = Answers("yes")
    with pytest.raises(StudioError) as e:
        review.run(ctx, v.id)
    assert "Review failed" in str(e.value) and ctx.confirm.asked == [] and v.stage == "thumbnailed"


def test_review_fails_when_chart_has_no_source(ctx):
    v = ready_video(ctx)
    p = ctx.settings.project_dir(v.id) / "script.json"
    pkg = json.loads(p.read_text())
    pkg["segments"][2]["chart_data"]["source_ids"] = []
    p.write_text(json.dumps(pkg))
    ctx.confirm = Answers("yes")
    with pytest.raises(StudioError):
        review.run(ctx, v.id)
    assert v.stage == "thumbnailed"


def test_review_cannot_skip_thumbnail(ctx):
    v = ready_video(ctx, stage="built")
    with pytest.raises(StageError):
        review.run(ctx, v.id)


def test_chapters_start_at_zero_and_merge_short_parts():
    segs = [{"chapter": "Hook", "est_seconds": 8}, {"chapter": "Customer", "est_seconds": 30},
            {"chapter": "Customer", "est_seconds": 20}, {"chapter": "Blip", "est_seconds": 5},
            {"chapter": "Money", "est_seconds": 40}]
    ch = review.chapters(segs, intro_seconds=4)
    assert ch[0][0] == 0
    assert all(b[0] - a[0] >= 10 for a, b in zip(ch, ch[1:]))
    assert "Blip" not in [n for _, n in ch]


# ---------- publish ----------
def yt(ctx, publish_at_returned=True):
    def insert(**kw):
        st = dict(kw["body"]["status"])
        if not publish_at_returned:
            st.pop("publishAt", None)
        return {"id": "abc123", "status": st}

    svc = FakeService({"videos.insert": insert,
                       "videos.list": lambda **kw: {"items": []}})
    ctx.youtube_factory = lambda: (svc, FakeService())
    (ctx.settings.root / "client_secret.json").write_text("{}")
    ctx.settings.channel_id = "UC1"
    return svc


def test_publish_refuses_without_review(ctx):
    v = ready_video(ctx)
    svc = yt(ctx)
    ctx.confirm = Answers("yes")
    with pytest.raises(StageError):
        publish.run(ctx, v.id)
    assert svc.calls == [] and v.stage == "thumbnailed"


def test_publish_refuses_without_typed_yes(ctx):
    v = ready_video(ctx)
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    svc = yt(ctx)
    ctx.confirm = Answers("no")
    with pytest.raises(GateError):
        publish.run(ctx, v.id)
    assert svc.calls == [] and v.stage == "reviewed"


def test_publish_schedules_with_metadata_and_disclosure(ctx):
    v = ready_video(ctx)
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    svc = yt(ctx)
    ctx.confirm = Answers("yes")
    when = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    publish.run(ctx, v.id, at=when, playlist="PL1")
    assert v.stage == "scheduled" and v.youtube_video_id == "abc123"
    body = next(kw for n, kw in svc.calls if n == "videos.insert")["body"]
    assert body["status"]["privacyStatus"] == "private" and body["status"]["publishAt"].endswith("Z")
    assert body["status"]["containsSyntheticMedia"] is False
    assert body["snippet"]["categoryId"] == "27" and "Chapters" in body["snippet"]["description"]
    assert {"thumbnails.set", "captions.insert", "playlistItems.insert"} <= set(svc.names())
    # second run: nothing left, no new calls
    n = len(svc.calls)
    publish.run(ctx, v.id, playlist="PL1")
    assert len(svc.calls) == n


def test_publish_reports_forced_private(ctx, capsys):
    v = ready_video(ctx)
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    yt(ctx, publish_at_returned=False)
    ctx.confirm = Answers("yes")
    publish.run(ctx, v.id, at=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"))
    assert "locked to private" in capsys.readouterr().out
    assert json.loads((ctx.settings.project_dir(v.id) / "review.json").read_text())["publish_state"]["forced_private"]


def test_publish_refuses_if_file_changed_after_review(ctx):
    v = ready_video(ctx)
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    (ctx.settings.project_dir(v.id) / "final.mp4").write_bytes(b"different")
    svc = yt(ctx)
    ctx.confirm = Answers("yes")
    with pytest.raises(StudioError) as e:
        publish.run(ctx, v.id)
    assert "changed after it was reviewed" in str(e.value) and svc.calls == []


def test_publish_checks_quota_before_uploading(ctx):
    from studio.errors import QuotaError
    from studio.models import QuotaLog
    from studio.youtube.quota import quota_day
    v = ready_video(ctx)
    ctx.confirm = Answers("yes")
    review.run(ctx, v.id)
    ctx.session.add(QuotaLog(date=quota_day(), endpoint="captions.insert", units=9300, ok=True))
    ctx.session.commit()
    svc = yt(ctx)
    ctx.confirm = Answers("yes")
    with pytest.raises(QuotaError):
        publish.run(ctx, v.id)
    assert svc.calls == []


def test_parse_when():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    assert publish.parse_when("2026-11-05T18:00:00+0000", now) == datetime(2026, 11, 5, 18, tzinfo=UTC)
    with pytest.raises(StudioError):
        publish.parse_when("2020-01-01 10:00", now)
    with pytest.raises(StudioError):
        publish.parse_when("next tuesday", now)
