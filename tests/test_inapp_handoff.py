"""In-app LLM handoff: a pasted answer must be applied even if the prompt text changed since it was shown."""

from __future__ import annotations

import json

from studio.stages import research
from studio.stages import script as sc
from studio.web import service as svc
from tests.test_story import SAMPLE


def _video(ctx):
    idea = svc.add_manual_topic(ctx, "how coffee shops make money")
    return idea, research.approve(ctx, idea.id)


def test_paste_applies_even_if_prompt_changed_since_it_was_shown(make_ctx):
    ctx = make_ctx()
    idea, v = _video(ctx)
    res = svc.capture(sc.run, ctx, idea.id)
    assert res.pending
    shown = svc.read_prompt(ctx, v.id)
    assert shown
    # the prompt the code builds now differs from the one the user copied (code update, new ledger entry...)
    orig = sc.build_prompt
    sc.build_prompt = lambda *a, **k: orig(*a, **k) + "\nEXTRA RULE ADDED LATER"
    try:
        out = svc.submit_script(ctx, idea.id, v.id, "```json\n" + json.dumps(SAMPLE) + "\n```")
    finally:
        sc.build_prompt = orig
    assert out.ok, out.error


def test_user_messages_have_no_terminal_or_file_hints(make_ctx):
    ctx = make_ctx()
    idea, v = _video(ctx)
    res = svc.capture(sc.run, ctx, idea.id)
    msg = svc.plain_pending(res.error)
    for bad in ("re-run", "Claude Code", ".md", "prompts", "LLM_PROVIDER", "\\"):
        assert bad not in msg


def test_parse_failure_gives_copyable_fix_request(make_ctx):
    ctx = make_ctx()
    idea, v = _video(ctx)
    res = svc.submit_script(ctx, idea.id, v.id, '{"title": "cut off", "segments": [')
    assert not res.ok
    req = svc.reply_again_request(res.error)
    assert "JSON" in req and "complete" in req


def test_script_screen_states(make_ctx):
    from studio.web import wizard_service as wiz
    ctx = make_ctx()
    idea, v = _video(ctx)
    assert wiz.script_next_step(ctx, v)["step"] == 1
    svc.capture(sc.run, ctx, idea.id)
    assert wiz.script_next_step(ctx, v)["step"] == 2
    bad = svc.submit_script(ctx, idea.id, v.id, json.dumps({"title": "x"}))
    assert not bad.ok
    st = wiz.script_next_step(ctx, v)
    assert st["rejected"] and st["step"] == 3 and "not accepted" in st["headline"]


def test_engine_state_starts_with_story_plan(make_ctx):
    from studio.web import wizard_service as wiz
    ctx = make_ctx()
    idea, v = _video(ctx)
    st = wiz.script_next_step(ctx, v, engine=True)
    assert st["task"] == "story_plan" and st["step"] == 1


def test_script_flow_plan_first_then_done(make_ctx):
    from studio.story import engine
    from studio.web import wizard_service as wiz
    ctx = make_ctx()
    idea, v = _video(ctx)
    f = wiz.script_flow(ctx, v)
    assert f["current"] == "plan" and f["task"] == "story_plan"
    assert [s[0] for s in f["steps"]] == ["plan", "script", "review"] and f["done_count"] == 0
    out = ctx.settings.project_dir(v.id)
    st = engine.load_state(out)
    st["plan"] = "done"
    engine.save_state(out, st)
    assert wiz.script_flow(ctx, v)["current"] == "script"
    wiz.skip_review(ctx, v)
    assert wiz.script_flow(ctx, v)["current"] is None


def test_script_flow_legacy_script_goes_to_review(make_ctx):
    from studio.web import wizard_service as wiz
    ctx = make_ctx()
    idea, v = _video(ctx)
    v.stage = "scripted"
    ctx.session.commit()
    f = wiz.script_flow(ctx, v)
    assert f["legacy"] and f["current"] == "review" and f["steps"][0][2] == "skipped"
