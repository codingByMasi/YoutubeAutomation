"""History/kids prompts carry no finance wording or template placeholders; plan hook numbers must be backed."""

from __future__ import annotations

import pytest

from studio.errors import PendingLLMResponse, StudioError
from studio.growth import channels
from studio.stages import script as sc
from studio.story import engine, prompts, style
from studio.story import profile as sp

FINANCE = ("show the money", "How X Makes Money", "educational, not", "money flow", "unit economics",
           "faceless narration with charts", "photographable", "60-120 seconds")


def test_history_script_prompt_has_no_finance_wording_or_placeholders(ctx):
    root = ctx.settings.root
    channels.add(root, "History Unrolled", type="history", niche="History", audience="Curious learners 16-55")
    text = sc.build_prompt(root, "Everything About Roman Empire")
    low = text.lower()
    for bad in FINANCE:
        assert bad.lower() not in low, bad
    assert not style.PLACEHOLDER.search(text)
    assert "cartoon cast" in low


@pytest.mark.parametrize("pack", ["history", "kids", "general", "explainer"])
def test_every_pack_style_is_placeholder_free(pack):
    prof = sp.get(pack)
    s = style.for_profile(prof, "- **Banned phrases:** \"x\", [add more]\n- brand colors [HEX CODES]; font [FONT NAME]")
    assert not style.PLACEHOLDER.search(s)


def test_compose_fails_loudly_on_placeholder():
    with pytest.raises(StudioError):
        prompts.compose("script", sp.get("history"), topic="t", style="colors [HEX CODES]")


def test_brief_is_type_specific():
    p = dict(channels.DEFAULTS, type="history", name="H", niche="History")
    text = channels.summary(p)
    assert "charts and diagrams" not in text and "maps, timelines and archive-style" not in text
    assert "cartoon cast" in text


def test_hook_numbers_must_be_covered_by_beat_one():
    facts = [{"id": "f4", "claim": "On 4 September 476 Odoacer deposed Romulus"},
             {"id": "f8", "claim": "The army peaked at about 450,000 by 211", "figure": 450000}]
    hook = {"line": "How does an empire of 450,000 soldiers end with a teenager?"}
    beat1 = {"key_fact": "Odoacer deposed the boy in 476.", "fact_ids": ["f4"]}
    out = {"audience_question": "How did it end?", "beats": [beat1]}
    assert any("450000" in p for p in engine.hook_coverage_problems(out, facts, hook))
    beat1["fact_ids"] = ["f4", "f8"]
    assert engine.hook_coverage_problems(out, facts, hook) == []


def test_unsourced_superlative_is_flagged():
    facts = [{"id": "f1", "claim": "The army peaked at about 450,000"}]
    out = {"audience_question": "How did the biggest army of the ancient world fall?",
           "beats": [{"key_fact": "x", "fact_ids": ["f1"]}]}
    assert any("biggest" in p for p in engine.hook_coverage_problems(out, facts, {"line": "Hi."}))


def _plan_prompt(ctx, ctype):
    from tests.test_story_engine import make_video, set_type
    idea, v = make_video(ctx)
    set_type(ctx, ctype)
    with pytest.raises(PendingLLMResponse):
        engine.run_plan(ctx, v)
    return (ctx.settings.project_dir(v.id) / "prompts" / "story_plan.prompt.md").read_text(encoding="utf-8")


def test_kids_plan_prompt_is_kid_shaped(ctx):
    text = _plan_prompt(ctx, "kids")
    for bad in ("filings", "annual reports", "billion USD", "number_stakes", "cannot be skipped",
                "At least two planted in the first 60 seconds"):
        assert bad not in text, bad
    assert "optional for this channel" in text


def test_history_plan_prompt_has_no_finance_sources_or_units(ctx):
    text = _plan_prompt(ctx, "history")
    for bad in ("annual reports", "billion USD", "number_stakes"):
        assert bad not in text, bad
    assert "20 seconds at most" not in text
