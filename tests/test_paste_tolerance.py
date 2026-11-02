"""Realistic Claude replies pasted into the Script screen: near-misses must be fixed or explained, not rejected."""
from __future__ import annotations

import json

import pytest

from studio.story import engine
from studio.web import service as svc
from tests import fake_llm
from tests.test_story_engine import make_video, set_type


def _at_script_step(ctx, ctype="business", pack="explainer"):
    idea, v = make_video(ctx)
    set_type(ctx, ctype)
    out = ctx.settings.project_dir(v.id)
    run = lambda c: engine.auto(c, v, fetch=fake_llm.fake_fetch)  # noqa: E731
    svc.capture(run, ctx)
    res = svc.submit_task(ctx, v.id, "story_plan", json.dumps(fake_llm.plan(pack)), run)
    assert res.ok or res.pending, (res.error, res.problems)
    outline = json.loads((out / "outline.json").read_text())
    return idea, v, out, run, outline


def _paste(ctx, v, run, data, fence=True):
    text = json.dumps(data, indent=2)
    if fence:
        text = "Here is your script:\n\n```json\n" + text + "\n```\n\nLet me know if you want changes!"
    return svc.submit_task(ctx, v.id, "script", text, run)


def test_baseline_ok(make_ctx):
    ctx = make_ctx()
    idea, v, out, run, outline = _at_script_step(ctx)
    d = fake_llm.script("explainer", outline, outline["hook_type"])
    res = _paste(ctx, v, run, d)
    assert res.ok or res.pending, (res.error, res.problems)


def _case(make_ctx, mutate):
    ctx = make_ctx()
    idea, v, out, run, outline = _at_script_step(ctx)
    d = fake_llm.script("explainer", outline, outline["hook_type"])
    mutate(d, outline)
    return _paste(ctx, v, run, d)


def rough_seconds(d, o):
    for s in d["segments"]:
        s["est_seconds"] = round(s["est_seconds"] / 5) * 5 or 5


def hook_case(d, o):
    d["hook_type"] = d["hook_type"].replace("_", " ").title()


def no_hook(d, o):
    d.pop("hook_type")


def long_sentences(d, o):
    for s in d["segments"][2:6]:
        s["narration"] = s["narration"].replace(". ", " and then ")


def drop_visuals(d, o):
    for s in d["segments"][:3]:
        s.pop("visual_intent", None)


def fewer_segments(d, o):
    d["segments"] = d["segments"][:12]


def lowercase_beats(d, o):
    for s in d["segments"]:
        s["beat"] = "Explain"


def short_thumb(d, o):
    d["thumbnail_texts"] = ["One", "Two"]


def ten_titles(d, o):
    d["titles"] = d["titles"][:10]


@pytest.mark.parametrize("fn", [rough_seconds, hook_case, no_hook, long_sentences, drop_visuals, lowercase_beats,
                                ten_titles])
def test_near_miss_is_accepted(make_ctx, fn):
    res = _case(make_ctx, fn)
    assert res.ok or res.pending, (res.error, res.problems)


def test_extra_thumbnail_texts_and_titles_are_trimmed(make_ctx):
    def many(d, o):
        d["thumbnail_texts"] = ["One two three four five six seven", "B", "C", "D"]
        d["titles"] = d["titles"] + [{"text": f"Extra {i}", "style": "x", "is_pick": True} for i in range(3)]
    res = _case(make_ctx, many)
    assert res.ok or res.pending, (res.error, res.problems)


@pytest.mark.parametrize("fn", [fewer_segments, short_thumb])
def test_real_gaps_are_still_named_in_plain_words(make_ctx, fn):
    res = _case(make_ctx, fn)
    assert not res.ok and res.problems
    assert svc.fix_request(res.problems)
