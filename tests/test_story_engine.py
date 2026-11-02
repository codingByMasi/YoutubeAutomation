"""Story engine end to end with the fake LLM: plan -> script -> review, facts verified with mocked HTTP."""

from __future__ import annotations

import json

import pytest

from studio.errors import InvalidAnswer, PendingLLMResponse
from studio.models import Idea, Video
from studio.stages import script as sc
from studio.story import engine, ledger
from studio.story import facts as fm
from studio.story import profile as sp
from tests import fake_llm


def make_video(ctx):
    idea = Idea(seed="s", topic="how a shop makes money", status="approved")
    ctx.session.add(idea)
    ctx.session.commit()
    v = Video(idea_id=idea.id, stage="approved")
    ctx.session.add(v)
    ctx.session.commit()
    return idea, v


def set_type(ctx, ctype):
    from studio.growth import channels
    channels.update(ctx.settings.root, channels.active_id(ctx.settings.root), type=ctype)


def run_engine(ctx, pack_type, pack):
    idea, v = make_video(ctx)
    set_type(ctx, pack_type)
    out = ctx.settings.project_dir(v.id)
    plan = fake_llm.plan(pack)
    fake_llm.write(out, "story_plan", plan)
    with pytest.raises(PendingLLMResponse):  # script prompt written, waiting
        sc.run(ctx, idea.id, auto=True, fetch=fake_llm.fake_fetch)
    outline = json.loads((out / "outline.json").read_text())
    draft = fake_llm.script(pack, outline, outline["hook_type"])
    fake_llm.write(out, "script", draft)
    with pytest.raises(PendingLLMResponse):  # story_review prompt written
        sc.run(ctx, idea.id, auto=True, fetch=fake_llm.fake_fetch)
    saved = sc.load_package(ctx, v.id)
    fake_llm.write(out, "story_review", fake_llm.review(saved, pack))
    sc.run(ctx, idea.id, auto=True, fetch=fake_llm.fake_fetch)
    return idea, v, out


@pytest.mark.parametrize("ctype,pack", [("business", "explainer"), ("history", "history"), ("kids", "kids"),
                                        ("general", "general")])
def test_full_engine_per_channel_type(ctx, ctype, pack):
    idea, v, out = run_engine(ctx, ctype, pack)
    st = engine.load_state(out)
    assert st["plan"] == st["script"] == st["review"] == "done"
    assert (out / "facts.json").exists() and (out / "hooks.json").exists() and (out / "story_review.json").exists()
    assert (out / "script.original.json").exists() and (out / "script.v1.json").exists()
    rounds = json.loads((out / "story_review.json").read_text())
    assert len(rounds[0]["swipe_points"]) == 3 and rounds[0]["swipe_points"][0]["at_seconds"] >= 0
    assert ledger.load(ctx.settings.root)[-1]["video_id"] == v.id
    assert sc.load_package(ctx, v.id)["engine"] is True


def test_next_step_prints_pending_handoff(ctx):
    idea, v = make_video(ctx)
    with pytest.raises(PendingLLMResponse):
        sc.run(ctx, idea.id, auto=True, fetch=fake_llm.fake_fetch)
    what, cmd = engine.next_step(ctx, v.id)
    assert "story_plan" in what and f"script {idea.id} --auto" in cmd


def test_plan_answer_with_bad_shape_names_the_field(ctx):
    idea, v = make_video(ctx)
    bad = fake_llm.plan("explainer")
    bad["outline"]["beats"][2]["seconds"] = "slow"
    fake_llm.write(ctx.settings.project_dir(v.id), "story_plan", bad)
    with pytest.raises(InvalidAnswer) as e:
        sc.run(ctx, idea.id, auto=True, fetch=fake_llm.fake_fetch)
    assert any("outline.beats[2].seconds" in p for p in e.value.problems)


def test_changed_prompt_archives_stale_answer(ctx, tmp_path):
    from studio.llm import ask_json
    ask_json_dir = tmp_path
    with pytest.raises(PendingLLMResponse):
        ask_json(ctx.settings, ask_json_dir, "t", "prompt one")
    (ask_json_dir / "prompts" / "t.response.json").write_text('{"a": 1}')
    assert ask_json(ctx.settings, ask_json_dir, "t", "prompt one") == {"a": 1}
    with pytest.raises(PendingLLMResponse):  # topic changed -> old answer is not reused
        ask_json(ctx.settings, ask_json_dir, "t", "prompt two")
    assert (ask_json_dir / "prompts" / "t.stale1.json").exists()


def test_unverified_fact_needs_estimate_wording_and_manual_accept(ctx):
    idea, v = make_video(ctx)
    out = ctx.settings.project_dir(v.id)
    fake_llm.write(out, "story_plan", fake_llm.plan("explainer"))
    with pytest.raises(PendingLLMResponse):
        sc.run(ctx, idea.id, auto=True, fetch=lambda url: (404, ""))  # every source unfetchable
    facts = fm.load_facts(out)
    assert {f["status"] for f in facts} == {"unfetchable"}
    engine.accept_fact(ctx, v.id, "f1")
    assert next(f for f in fm.load_facts(out) if f["id"] == "f1")["status"] == "manual"


def test_review_rejects_quote_still_present(ctx):
    idea, v, out = run_engine(ctx, "business", "explainer")
    pkg = sc.load_package(ctx, v.id)
    prof = sp.get("explainer")
    d = fake_llm.review(pkg)
    d["revised"] = pkg  # unchanged: the swipe quotes are still there
    probs = engine.validate_review(d, pkg, prof, fm.load_facts(out), ["hook"])
    assert any("still in the rewrite" in p for p in probs)
