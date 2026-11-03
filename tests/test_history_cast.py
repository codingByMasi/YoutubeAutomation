"""History channel cast: sprite contract, scene rules, prompt block, profile wiring."""

from __future__ import annotations

import pytest

from studio.history import cast
from studio.kids import sprites
from studio.story import checks, prompts
from studio.story import profile as sp


def test_roster_svgs_follow_the_sprite_contract(tmp_path):
    files = cast.export_roster(tmp_path)
    assert len(files) == len(cast.ROSTER)
    for f in files:
        assert not sprites.missing_groups(f.read_text(encoding="utf-8")), f.name
    bank = sprites.SpriteBank(user_dir=tmp_path)
    assert bank._source("quill") is not None


def test_build_svg_validates_inputs():
    svg = cast.build_svg("#112233", "crown", "banner", "k7")
    assert ">K<" in svg and "#112233" in svg
    for bad in (dict(headwear="tophat"), dict(prop="laser"), dict(body="red")):
        with pytest.raises(ValueError):
            cast.build_svg(**bad)


def seg(scene=None, **kw):
    d = {"narration": "x", "est_seconds": 5}
    if scene:
        d["scene"] = scene
    d.update(kw)
    return d


def test_scene_problems():
    ok = {"segments": [seg("skit", cast=["quill"], speech=[{"who": "quill", "text": "Where is the pay?"}]),
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
    assert "Quill" in cast.prompt_block(h) and cast.prompt_block(sp.get("explainer")) == ""
    out = prompts.compose("script", h, topic="t", brief="b", style="s", outline="o", learned="", competitors="")
    assert "Cast and depiction" in out and "Captain Blunder" in out


def test_faction_colors_wrap():
    assert cast.faction_color(0) == cast.faction_color(len(cast.FACTION_COLORS))
