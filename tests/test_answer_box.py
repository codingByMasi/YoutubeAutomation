"""The paste-back box: tolerant JSON reading and clear results for every handoff step."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from studio.errors import StudioError
from studio.models import Idea, Video
from studio.stages import research, story
from studio.stages import script as sc
from studio.util.answer_json import normalize_answer, parse_answer
from studio.web import service as svc
from tests.test_story import SAMPLE, critique_answer, good_outline

OBJ = {"a": 1, "b": ["x", "y"], "c": {"d": "He said “hi”"}}
TXT = json.dumps(OBJ, ensure_ascii=False, indent=2)


@pytest.mark.parametrize("wrapped", [
    TXT,
    f"```json\n{TXT}\n```",
    f"```\n{TXT}\n```",
    f"Here is the JSON you asked for:\n\n```json\n{TXT}\n```\n\nLet me know if you want changes!",
    f"Sure! {TXT} Hope that helps.",
    "﻿" + TXT,
    TXT.replace('"b": ["x", "y"]', '"b": ["x", "y",]'),
    TXT.replace('"a": 1,', '"a": 1, // note\n'),
    TXT.replace('"d": "He said', '"d": "He\nsaid'),  # raw newline inside a string
])
def test_parse_tolerates_chat_artefacts(wrapped):
    got = parse_answer(wrapped)
    assert got["a"] == 1 and got["b"] == ["x", "y"]


def test_parse_smart_quote_delimiters():
    got = parse_answer('{“a”: “one”, “b”: 2}')
    assert got == {"a": "one", "b": 2}


def test_stray_brace_in_intro_text():
    assert parse_answer('Use {curly} braces? Answer: {"a": 1}') == {"a": 1}


@pytest.mark.parametrize("bad, needle", [
    ("", "empty"),
    ("   \n", "empty"),
    ("no json here at all", "no JSON object"),
    ('{"a": 1, "b": }', "line 1"),
    ('{\n  "a": 1,\n  "b": [1, 2\n  "c": 3\n}', "line"),
    ('{"a": "cut off', "cut off"),
])
def test_parse_errors_are_friendly(bad, needle):
    with pytest.raises(StudioError) as e:
        parse_answer(bad)
    assert needle in str(e.value) and "Next:" in str(e.value)


def test_normalize_is_strict_json():
    assert json.loads(normalize_answer(f"```json\n{TXT}\n```")) == OBJ


def _scripted(ctx):
    idea = svc.add_manual_topic(ctx, "how coffee shops make money")
    v = research.approve(ctx, idea.id)
    (ctx.settings.project_dir(v.id) / "prompts").mkdir(parents=True, exist_ok=True)
    return idea, v


def test_script_paste_with_fences_and_chatter(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    res = svc.submit_script(ctx, idea.id, v.id, "Here you go:\n```json\n" + json.dumps(SAMPLE) + "\n```\nEnjoy!")
    assert res.ok, res.error
    assert "Saved your script answer" in res.summary
    assert ctx.session.get(Video, v.id).stage == "scripted"


def test_outline_flow_success_and_summary(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    res = svc.submit_task(ctx, v.id, "outline", "```json\n" + json.dumps(good_outline()) + "\n```",
                          story.run_outline, idea.id)
    assert res.ok, res.error
    assert "outline" in res.summary and "Outline OK" in res.summary
    assert story.load_outline(ctx.settings.project_dir(v.id))["big_idea"]


def test_outline_validation_failure_lists_problems_and_keeps_nothing(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    bad = good_outline()
    bad["beats"] = bad["beats"][:3]
    res = svc.submit_task(ctx, v.id, "outline", json.dumps(bad), story.run_outline, idea.id)
    assert not res.ok and "need 10-18 beats" in res.error and "Nothing was saved" in res.error
    assert not (ctx.settings.project_dir(v.id) / "prompts" / "outline.response.json").exists()


@pytest.mark.parametrize("mangle", [
    lambda d: d.update(hooks=["just a string", "another", "third"]),
    lambda d: d.update(beats=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
    lambda d: d.update(loops="none"),
    lambda d: d.update(ending="the end"),
])
def test_wrong_shapes_never_crash(make_ctx, mangle):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    d = good_outline()
    mangle(d)
    res = svc.submit_task(ctx, v.id, "outline", json.dumps(d), story.run_outline, idea.id)
    assert not res.ok and res.error and "Traceback" not in res.error


def test_critique_flow(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    assert svc.submit_script(ctx, idea.id, v.id, json.dumps(SAMPLE)).ok
    revised = copy.deepcopy(SAMPLE)
    revised["segments"][0]["narration"] = "A five dollar coffee costs thirty cents to make. Where does the rest go?"
    res = svc.submit_task(ctx, v.id, "critique", "```json\n" + json.dumps(critique_answer(revised, hook=2)) + "\n```",
                          story.run_critique, v.id)
    assert res.ok, res.error
    assert "script review and rewrite" in res.summary
    assert "thirty cents" in sc.load_package(ctx, v.id)["segments"][0]["narration"]


def test_critique_missing_keys_is_friendly(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    assert svc.submit_script(ctx, idea.id, v.id, json.dumps(SAMPLE)).ok
    res = svc.submit_task(ctx, v.id, "critique", '{"verdict": "ok"}', story.run_critique, v.id)
    assert not res.ok and "scores." in res.error and "fixes is empty" in res.error


def test_empty_and_garbage_paste(make_ctx):
    ctx = make_ctx()
    idea, v = _scripted(ctx)
    for text in ("", "nope", '{"a": '):
        res = svc.submit_task(ctx, v.id, "outline", text, story.run_outline, idea.id)
        assert not res.ok and "Next:" in res.error


def test_capture_turns_unexpected_errors_into_messages():
    def boom():
        raise KeyError("scores")

    res = svc.capture(boom)
    assert not res.ok and "KeyError" in res.error and "Next:" in res.error


def test_growth_and_kids_parsers_share_tolerance():
    from studio.growth.store import extract_json
    from studio.kids.page import llm_json

    assert extract_json("```json\n{\"a\": 1,}\n```") == {"a": 1}
    assert llm_json("Sure:\n{“a”: 1}") == {"a": 1}
    with pytest.raises(ValueError):
        llm_json("nothing")


def test_apply_answer_flash_and_error(make_ctx, monkeypatch):
    """The UI helper stores a success message that survives the rerun, and shows errors in place."""
    import streamlit as st

    from studio.web import handoff_ui

    ctx = make_ctx()
    idea, v = _scripted(ctx)
    shown = {}
    monkeypatch.setattr(st, "error", lambda m: shown.setdefault("err", m))
    monkeypatch.setattr(st, "spinner", lambda *_: __import__("contextlib").nullcontext())
    monkeypatch.setattr(st, "expander", lambda *_: __import__("contextlib").nullcontext())
    monkeypatch.setattr(st, "code", lambda *_a, **_k: None)
    st.session_state.clear()
    assert not handoff_ui.apply_answer(ctx, v.id, "outline", "garbage", story.run_outline, (idea.id,))
    assert "nothing was saved" in shown["err"]
    assert handoff_ui.apply_answer(ctx, v.id, "outline", json.dumps(good_outline()), story.run_outline, (idea.id,))
    assert "outline" in st.session_state["flash_ok"]["summary"]
    assert Path(ctx.settings.project_dir(v.id)).exists() and Idea and True
