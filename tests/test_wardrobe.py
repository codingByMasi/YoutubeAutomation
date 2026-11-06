"""Story eras: characters dress for the story; old scripts keep the default look."""

from __future__ import annotations

import pytest

from studio.history import cast, render, wardrobe


def test_starter_wardrobe_has_8_to_10_eras():
    assert 8 <= len(wardrobe.ERAS) <= 10


@pytest.mark.parametrize("era", wardrobe.ERAS)
def test_every_era_dresses_a_character_who_has_no_clothes_described(era):
    from studio.history import figures
    assert era in figures.ERA_STYLE
    spec = {"name": "Gaius"}
    plain = figures.draw(spec, 160)
    dressed = figures.draw(spec, 160, era_style=figures.ERA_STYLE[era])
    assert dressed.size == plain.size == (160, 160)


def test_default_era_is_known_and_unknown_one_is_not():
    assert wardrobe.known(None) and wardrobe.known("default") and wardrobe.known("roman")
    assert not wardrobe.known("space_age")


def test_guess_and_era_for_fall_back_to_default():
    assert wardrobe.guess_era("How Hannibal beat Rome at Cannae") == "roman"
    assert wardrobe.guess_era("Why Vikings raided Lindisfarne") == "viking"
    assert wardrobe.guess_era("How the Black Death rewired Europe") == "medieval"
    assert wardrobe.guess_era("An embankment collapses") == wardrobe.DEFAULT
    assert wardrobe.guess_era("") == wardrobe.DEFAULT
    assert wardrobe.era_for({"narration": "x"}, {"title": "Quiet topic"}) == wardrobe.DEFAULT  # old script
    assert wardrobe.era_for({}, {"title": "Rome", "era": "greek"}) == "greek"  # script beats guess
    assert wardrobe.era_for({"era": "egyptian"}, {"era": "greek"}) == "egyptian"  # segment beats video
    assert wardrobe.era_for({"era": "nonsense"}, {"title": "Rome"}) == wardrobe.DEFAULT


def test_script_check_flags_a_bad_era_and_prompt_lists_eras():
    pkg = {"era": "bronze", "segments": [{"scene": "title", "era": "mars"}]}
    problems = cast.scene_problems(pkg)
    assert any("'bronze'" in p for p in problems) and any("'mars'" in p for p in problems)
    assert cast.scene_problems({"era": "Roman", "segments": [{"scene": "title"}]}) == []
    block = cast.prompt_block({"cast": True, "depiction": {"rules": []}})
    assert all(e in block for e in wardrobe.ERAS)


def test_scene_fingerprint_changes_with_era():
    seg = {"scene": "title", "cast": ["Hannibal"], "chapter": "c"}
    assert render.fingerprint(seg, 2.0, None) != render.fingerprint({**seg, "era": "roman"}, 2.0, None)


def test_old_fixed_names_get_their_own_figure_and_unknown_era_does_not_crash(tmp_path):
    c = render.Cast(tmp_path)
    for who in ("Quill", "Captain Blunder", "Dusty"):  # names from old scripts: drawn from their own words
        assert c.sprite(who, 120, 0.0, 0, False, era="roman").size == (120, 120)
    assert c.sprite("Hannibal", 120, 0.0, 0, False, era="not-an-era").size == (120, 120)  # unknown era: no crash


def test_scene_clip_renders_in_costume(tmp_path):
    out = tmp_path / "c.mp4"
    seg = {"scene": "title", "cast": ["Hannibal"], "era": "viking", "scene_data": {"title": "Longships"}}
    render.render_scene(seg, 0.5, out, tmp_path)
    assert out.exists() and out.stat().st_size > 1000
