"""History channel cast: sprite contract, scene rules, prompt block, profile wiring."""

from __future__ import annotations

from studio.history import cast
from studio.story import checks, prompts
from studio.story import profile as sp


def test_no_fixed_cast_and_no_shared_character_template():
    assert not hasattr(cast, "ROSTER") and not hasattr(cast, "build_svg")


def seg(scene=None, **kw):
    d = {"narration": "x", "est_seconds": 5}
    if scene:
        d["scene"] = scene
    d.update(kw)
    return d


def test_scene_problems():
    ok = {"segments": [seg("skit", cast=["Odo"], speech=[{"who": "Odo", "text": "Where is the pay?"}]),
                       seg("map"), seg("map"), seg("map"), seg()]}
    assert cast.scene_problems(ok) == []
    bad = {"segments": [seg("dance"), seg("skit", speech=[{"who": "a", "text": "word " * 13}] * 7),
                        seg("map", speech=[{"who": "a", "text": "hi"}])]}
    text = " | ".join(cast.scene_problems(bad))
    assert "not one of" in text and "needs `cast`" in text and "7 speech lines" in text
    assert "13 words" in text and "only belong to a 'skit'" in text
    three = {"segments": [seg("easel"), seg("easel"), seg("easel")]}
    assert any("three 'easel'" in p for p in cast.scene_problems(three))


def test_history_profile_turns_on_cast_checks_and_prompt_block():
    h = sp.get("history")
    assert sp.enabled(h, "cast_scenes") and not sp.enabled(sp.get("explainer"), "cast_scenes")
    assert checks.profile_problems({"segments": [seg("dance")]}, {**h, "flags": {"cast_scenes": True}}) != []
    assert "Cast and depiction" in cast.prompt_block(h) and cast.prompt_block(sp.get("explainer")) == ""
    out = prompts.compose("script", h, topic="t", brief="b", style="s", outline="o", learned="", competitors="")
    assert "Cast and depiction" in out and "- quill:" not in out


def test_prompt_does_not_force_fixed_roster():
    text = cast.prompt_block(sp.get("history"))
    assert "at most 2 new" not in text and "use them for their job" not in text
    assert "Invent the cast the story needs" in text and "no fixed or recurring cast" in text


def test_no_fixed_cast_or_host_is_offered_to_the_writer():
    """Prompts must not hand the script writer any fixed character: every character comes from the story."""
    from studio.history import scene_plan
    block = cast.prompt_block(sp.get("history"))
    plan = scene_plan.build_prompt([{"chapter": "c", "narration": "Napoleon crowns himself."}])
    for name in ("quill", "dusty", "vex", "blunder", "dash", "brine", "hindsight", "ironhand", "alma"):
        assert name not in (block + plan).lower().replace("quillon", "")
    assert "roster ids" not in plan and "lectern" not in plan.lower()


def test_faction_colors_wrap():
    assert cast.faction_color(0) == cast.faction_color(len(cast.FACTION_COLORS))


def test_a_still_card_longer_than_six_seconds_is_rejected_at_script_time():
    from studio.history import cast
    seg = {"scene": "calendar", "est_seconds": 14, "narration": "x"}
    probs = cast.scene_problems({"segments": [seg]})
    assert any("calendar card" in p and "6 s" in p for p in probs)
    assert not any("card" in p for p in cast.scene_problems({"segments": [{**seg, "est_seconds": 5}]}))
    diagram = {**seg, "scene": "diagram", "est_seconds": 14}
    assert not any("card" in p for p in cast.scene_problems({"segments": [diagram]}))


def test_the_history_script_prompt_carries_the_retention_rules():
    from pathlib import Path
    text = (Path(__file__).parents[1] / "studio" / "prompts" / "history" / "script.md").read_text(encoding="utf-8")
    for must in ("scene_data.counter", "scene_data.cliff", "at most 6 seconds", "a setup, a twist"):
        assert must in text
