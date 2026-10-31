"""Growth tools: profile, series, packs, SEO, Shorts plan, fact check, performance, monetization, UI smoke."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from studio.errors import StudioError
from studio.growth import factcheck, monetize, packs, perf, profile, shorts_plan
from studio.growth import series as series_mod
from studio.stages import research
from studio.stages import script as script_stage
from studio.web import growth_service as g
from studio.web import service as svc

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def scripted(ctx):
    idea = svc.add_manual_topic(ctx, "how coffee shops make money")
    v = research.approve(ctx, idea.id)
    script_stage.save_package(ctx, v, json.loads(json.dumps(SAMPLE)))
    return v


def test_profile_defaults_and_save(root):
    assert profile.load(root)["language"] == "English"
    profile.save(root, {"name": "Money Maps", "bogus": 1})
    p = profile.load(root)
    assert p["name"] == "Money Maps" and "bogus" not in p
    assert "Money Maps" in profile.summary(p)


def test_series_flow_and_end_screen(root):
    s = series_mod.create(root, "Giants", "d", ["A", "B"])
    with pytest.raises(StudioError):
        series_mod.create(root, "giants")
    series_mod.link_video(root, "Giants", 0, 7, "Title A")
    cur, idx = series_mod.position(root, 7)
    es = series_mod.end_screen(cur, idx)
    assert es["next_topic"] == "B" and "Giants" in es["spoken"]
    assert series_mod.end_screen(cur, 1)["next_topic"] is None
    assert s["name"] == "Giants"


def test_series_import_skips_bad_and_duplicates(root):
    txt = 'Sure!\n```json\n{"series":[{"name":"X","topics":["a","b"]},{"name":"x","topics":["c"]},{"name":""}]}\n```'
    assert series_mod.import_series(root, txt) == ["X"]
    with pytest.raises(StudioError):
        series_mod.import_series(root, '{"series": []}')


def test_title_checklist_and_pack_parse():
    good, _ = packs.title_checklist("How Costco Makes $1 Billion From Fees")
    bad, notes = packs.title_checklist("YOU WON'T BELIEVE THIS SHOCKING TRICK")
    assert good >= 5 and bad == 0 and notes
    titles = [{"text": t} for t in ["How Costco Makes $1 Billion From Fees", "Costco", "Why Costco Sells Cheap Chicken",
                                    "The 5 Numbers Behind Costco", "Costco Business Model"]]
    thumbs = [{"text": "$4.9B FEES", "focal_element": "stack of cash", "emotion_or_tension": "big number",
               "colors": "navy and yellow"}, {"text": "a b c d e f"}, {"text": "WHY?", "focal_element": "cart"}]
    pack = packs.parse("```json\n" + json.dumps({"titles": titles, "thumbnails": thumbs}) + "\n```")
    assert pack["pick_title"] == pack["titles"][0]["text"]
    assert pack["thumbnails"][0]["score"] >= pack["thumbnails"][-1]["score"]
    with pytest.raises(StudioError):
        packs.parse(json.dumps({"titles": titles[:2], "thumbnails": thumbs}))


def test_seo_has_sources_chapters_credits_and_series(make_ctx):
    ctx = make_ctx()
    v = scripted(ctx)
    profile.save(ctx.settings.root, {"newsletter_url": "https://news.example/join"})
    series_mod.create(ctx.settings.root, "Cafes", "", ["How coffee shops make money", "Next one"])
    series_mod.link_video(ctx.settings.root, "Cafes", 0, v.id, "How coffee shops make money")
    out = g.seo_for(ctx, v.id)
    assert "Sources" in out["description"] and "Next in the series: Next one" in out["description"]
    assert "https://news.example/join" in out["description"]
    assert out["chapters"][0].startswith("0:00") and out["tags"] and out["chars"] <= 5000


def test_shorts_plan_picks_hook_first(make_ctx):
    ctx = make_ctx()
    v = scripted(ctx)
    plan = g.shorts_for(ctx, v.id)
    assert plan and all(20 <= s["seconds"] <= 45 for s in plan)
    segs = [{"narration": f"Sentence {i}. More.", "est_seconds": 12, "chart_data": {} if i != 2 else {"x": 1},
             "beat": None, "chapter": "c"} for i in range(8)]
    assert shorts_plan.plan({"segments": segs})[0]["segments"][0] == 0


def test_factcheck_blocks_placeholders_and_passes_when_ticked(make_ctx):
    ctx = make_ctx()
    v = scripted(ctx)
    assert not g.fact_check_passed(ctx, v.id)
    st = g.factcheck_for(ctx, v.id)
    assert any("placeholder" in p for p in st["problems"])
    pkg = json.loads(json.dumps(SAMPLE))
    pkg["sources"] = [{"id": "s1", "title": "10-K", "url_or_note": "https://sec.gov/x"}]
    pd = ctx.settings.project_dir(v.id)
    st = factcheck.status(pd, pkg)
    for it in st["items"]:
        factcheck.toggle(pd, it["id"], True)
    assert factcheck.status(pd, pkg)["passed"]
    ids = [i["id"] for i in factcheck.build_items(pkg)]
    assert ids == [i["id"] for i in factcheck.build_items(pkg)]  # stable across runs


def test_perf_csv_advice_and_retention(root):
    csv_text = ("Video title,Impressions,Impressions click-through rate (%),Views,Average view duration,"
                "Average percentage viewed (%)\nTotal,1,1,1,0:10,1\nHow X works,5000,1.4,70,4:32,24.5\n")
    rows = perf.parse_csv(csv_text)
    assert rows == [{"title": "How X works", "impressions": 5000.0, "ctr": 1.4, "views": 70.0,
                     "avg_view_seconds": 272.0, "avg_view_pct": 24.5}]
    curve = perf.parse_retention("0:00 100%\n0:30 48%\n1:00, 45")
    adv = perf.advice(rows[0], curve)
    assert any("CTR" in a for a in adv) and any("hook" in a for a in adv)
    entry = perf.add(root, rows[0], curve, 3)
    assert perf.load(root)[0]["advice"] == entry["advice"]
    assert "retention" in perf.prompt(rows[0], curve, "t", "p").lower()
    with pytest.raises(StudioError):
        perf.parse_csv("only header")


def test_monetize_progress_eta_and_checklist(root):
    monetize.log_progress(root, 100, 400, on=date(2026, 9, 1))
    monetize.log_progress(root, 200, 800, on=date(2026, 10, 1))
    pr = monetize.progress(root, today=date(2026, 10, 1))
    assert pr["subs_pct"] == 20 and pr["hours_pct"] == 20
    assert pr["eta"] and pr["eta"] > date(2026, 10, 1) and not pr["eligible_long_form"]
    monetize.toggle(root, "newsletter", True)
    assert "newsletter" in monetize.progress(root)["checked"]
    monetize.log_progress(root, 1200, 4100, on=date(2026, 11, 1))
    assert monetize.progress(root)["eligible_long_form"]


def test_calendar_rows_include_planned_series(make_ctx):
    ctx = make_ctx()
    series_mod.create(ctx.settings.root, "S", "", ["Planned topic"])
    rows = g.calendar_rows(ctx, 2, today=date(2026, 11, 2))
    assert any("Planned topic" in r[2] for r in rows)


def test_grow_page_renders(root, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("STUDIO_HOME", str(root))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.sidebar.radio[0].set_value("5. Grow the channel").run()
    assert not at.exception
