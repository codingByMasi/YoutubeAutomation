"""Multi-channel analytics, per-channel sign-in and channel types (all APIs mocked)."""

import json
from datetime import date

import pytest
from typer.testing import CliRunner

from studio.cli import app
from studio.config import load_settings
from studio.errors import StudioError
from studio.growth import channel_types, channels
from studio.manage import multi_analytics as m
from studio.stages import discover
from studio.stages.publish import upload_body
from studio.youtube import auth
from studio.youtube.analytics_api import YouTubeAnalytics
from studio.youtube.data_api import YouTubeData
from tests.fakes import FakeService

START, END = date(2026, 10, 1), date(2026, 10, 7)


def _live_pair(ctx, views=700, prev=350):
    def query(**kw):
        dims = kw.get("dimensions")
        if dims == "day":
            return {"columnHeaders": [{"name": n} for n in ("day", "views", "estimatedMinutesWatched",
                                                            "subscribersGained", "subscribersLost")],
                    "rows": [[f"2026-10-0{i}", 100, 300, 5, 1] for i in range(1, 8)]}
        if dims == "video":
            return {"columnHeaders": [{"name": n} for n in ("video", "views", "estimatedMinutesWatched",
                                                            "averageViewPercentage")],
                    "rows": [["vidA", 500, 900, 48.5], ["vidB", 200, 100, 30.0]]}
        v = prev if kw["startDate"] < "2026-10-01" else views
        return {"columnHeaders": [{"name": n} for n in ("views", "estimatedMinutesWatched", "averageViewDuration",
                                                        "averageViewPercentage", "subscribersGained",
                                                        "subscribersLost")],
                "rows": [[v, 2100, 180, 41.2, 35, 7]]}

    yt = FakeService({
        "videos.list": lambda **kw: {"items": [{"id": "vidA", "snippet": {"title": "Alpha"}},
                                               {"id": "vidB", "snippet": {"title": "Beta"}}]},
        "channels.list": lambda **kw: {"items": [{"id": "UCabc", "snippet": {"title": "Money Maps"},
                                                  "statistics": {"subscriberCount": "1234"}}]}})
    ya = FakeService({"reports.query": query})
    return YouTubeData(yt, ctx.quota), YouTubeAnalytics(ya, ctx.quota), ya


def test_type_defaults_and_aliases(root):
    assert channel_types.normalize("Economics") == "business" and channel_types.normalize("") == "business"
    with pytest.raises(StudioError):
        channel_types.normalize("cooking")
    cid = channels.add(root, "Tiny Tunes", type="kids")
    p = channels.get(root, cid)
    assert p["type"] == "kids" and "toddlers" in p["niche"].lower()
    assert channels.type_info(root)["made_for_kids"] and "Made for Kids" in channels.summary(p)
    assert channels.brief(root) is not None
    # mixed formats side by side
    channels.add(root, "Old Empires", type="history", activate=False)
    assert {c["type"] for c in channels.list_channels(root)} == {"business", "kids", "history"}


def test_kids_type_drives_settings_upload_and_topics(root):
    channels.add(root, "Tiny Tunes", type="kids")
    s = load_settings(root)
    assert s.made_for_kids and s.channel_key == "tiny-tunes"
    assert s.token_path == root / "tokens" / "tiny-tunes.json"
    review = {"title": "t", "description": "d", "tags": [], "category_id": "27", "synthetic_media": False}
    assert upload_body(review, None, s.made_for_kids)["status"]["selfDeclaredMadeForKids"] is True
    assert upload_body(review, None)["status"]["selfDeclaredMadeForKids"] is False


def test_auto_suggest_uses_type_phrases(ctx):
    channels.add(ctx.settings.root, "Tiny Tunes", type="kids")
    asked = []
    discover.auto_suggest(ctx, count=3, suggest=lambda q: asked.append(q) or [])
    assert asked and any(w in " ".join(asked) for w in ("song", "lullaby", "animal"))


def test_default_channel_keeps_original_token(root):
    assert load_settings(root).token_path == root / "token.json"


def test_each_channel_has_its_own_token_and_signin(root):
    channels.add(root, "Money Maps", type="business")
    channels.add(root, "Tiny Tunes", type="kids", activate=False)
    base = load_settings(root)
    a, b = auth.settings_for(base, "money-maps"), auth.settings_for(base, "tiny-tunes")
    assert a.token_path != b.token_path and b.made_for_kids and not a.made_for_kids

    class Creds:
        valid = True

        def __init__(self, tag):
            self.tag = tag

        def to_json(self):
            return json.dumps({"tag": self.tag})

    auth.get_credentials(a, run_flow=lambda s: Creds("a"))
    assert auth.is_signed_in(a) and not auth.is_signed_in(b)
    auth.get_credentials(b, run_flow=lambda s: Creds("b"))
    assert json.loads(a.token_path.read_text()) == {"tag": "a"}
    assert json.loads(b.token_path.read_text()) == {"tag": "b"}


def test_sign_in_records_youtube_channel_id_and_detects_mismatch(ctx):
    root = ctx.settings.root
    channels.add(root, "Money Maps")
    data, ya, _ = _live_pair(ctx)

    class Creds:
        valid = True

        def to_json(self):
            return "{}"

    out = m.sign_in(ctx.settings, "money-maps", run_flow=lambda s: Creds(), services=lambda c: (data, ya))
    assert out["youtube_channel_id"] == "UCabc" and channels.get(root, "money-maps")["youtube_channel_id"] == "UCabc"
    channels.update(root, "money-maps", youtube_channel_id="UCother")
    with pytest.raises(StudioError, match="expects UCother"):
        m.sign_in(ctx.settings, "money-maps", run_flow=lambda s: Creds(), services=lambda c: (data, ya))


def test_live_report_totals_top_videos_retention_and_range(ctx):
    root = ctx.settings.root
    channels.add(root, "Money Maps")
    data, ya, raw = _live_pair(ctx)
    r = m.channel_report(root, "money-maps", START, END, lambda c: (data, ya))
    assert r["source"] == "live"
    assert r["totals"]["views"] == 700 and r["previous"]["views"] == 350
    assert r["totals"]["watch_hours"] == 35.0 and r["totals"]["net_subs"] == 28
    assert r["totals"]["avg_view_pct"] == 41.2 and r["subscribers_total"] == 1234
    assert [v["title"] for v in r["top_videos"]] == ["Alpha", "Beta"] and r["top_videos"][0]["retention_pct"] == 48.5
    assert len(r["daily"]) == 7
    first = raw.calls[0][1]
    assert first["startDate"] == "2026-10-01" and first["endDate"] == "2026-10-07"


def test_not_signed_in_vs_demo_is_labelled(ctx):
    root = ctx.settings.root
    channels.add(root, "Tiny Tunes", type="kids")
    none = lambda c: None  # noqa: E731
    r = m.channel_report(root, "tiny-tunes", START, END, none)
    assert r["source"] == "not_signed_in" and "channels sign-in tiny-tunes" in r["message"] and not r["daily"]
    d1 = m.channel_report(root, "tiny-tunes", START, END, none, demo=True)
    d2 = m.channel_report(root, "tiny-tunes", START, END, none, demo=True)
    assert d1["source"] == "demo" and d1 == d2 and d1["totals"]["views"] > 0 and "SAMPLE DATA" in m.format_text(d1)


def test_overview_mixes_live_and_demo_and_isolates_failures(ctx):
    root = ctx.settings.root
    channels.add(root, "Money Maps")
    channels.add(root, "Tiny Tunes", type="kids", activate=False)
    channels.add(root, "Broken", activate=False)
    data, ya, _ = _live_pair(ctx)

    def services(cid):
        if cid == "broken":
            raise RuntimeError("boom")
        return (data, ya) if cid == "money-maps" else None

    with pytest.raises(RuntimeError):  # non-Studio errors from sign-in lookups are not hidden
        m.overview(root, START, END, services, demo=True)
    bad = {"default", "money-maps", "tiny-tunes"}
    reps = m.overview(root, START, END, lambda c: services(c) if c != "default" else None, demo=True,
                      only=sorted(bad))
    assert {r["channel_id"]: r["source"] for r in reps} == {"default": "demo", "money-maps": "live",
                                                            "tiny-tunes": "demo"}
    rows = m.comparison_rows(reps)
    live = next(r for r in rows if r["channel"] == "Money Maps")
    assert live["views_change_pct"] == 100.0 and live["top_video"] == "Alpha"
    assert "Money Maps" in m.format_comparison(rows)


def test_live_query_failure_is_reported_not_raised(ctx):
    root = ctx.settings.root
    channels.add(root, "Money Maps")
    data, _, _ = _live_pair(ctx)

    class Boom:
        def top_videos(self, *a, **k):
            raise RuntimeError("quota")

    r = m.channel_report(root, "money-maps", START, END, lambda c: (data, Boom()))
    assert r["source"] == "error" and "did not return analytics" in r["message"]


def test_date_range_rules():
    assert m.date_range(7, today=date(2026, 11, 1)) == (date(2026, 10, 25), date(2026, 10, 31))
    assert m.date_range(1, date(2026, 10, 1), date(2026, 10, 9)) == (date(2026, 10, 1), date(2026, 10, 9))
    with pytest.raises(StudioError):
        m.date_range(1, date(2026, 10, 9), date(2026, 10, 1))


def test_cli_type_stats_and_compare(root, monkeypatch):
    monkeypatch.chdir(root)
    monkeypatch.setenv("STUDIO_HOME", str(root))
    run = CliRunner().invoke
    r = run(app, ["channels", "add", "Tiny Tunes", "--type", "kids"])
    assert r.exit_code == 0, r.output
    assert "kids" in run(app, ["channels", "list"]).output
    assert "kids channel" in run(app, ["channels", "use", "tiny-tunes"]).output
    assert "Made for Kids: yes" in run(app, ["channels", "types"]).output
    r = run(app, ["channels", "stats", "tiny-tunes"])
    assert "not_signed_in" in r.output and "channels sign-in tiny-tunes" in r.output
    r = run(app, ["channels", "stats", "tiny-tunes", "--demo", "--from", "2026-10-01", "--to", "2026-10-07"])
    assert "SAMPLE DATA" in r.output and "2026-10-01 to 2026-10-07" in r.output
    r = run(app, ["channels", "compare", "--demo", "--days", "7"])
    assert r.exit_code == 0 and "Tiny Tunes" in r.output and "Source" in r.output
    assert run(app, ["channels", "stats", "--from", "oct"]).exit_code != 0
