"""Story-era costumes: same character, different outfit; old scripts keep the default look."""

from __future__ import annotations

import re

import pytest

from studio.history import cast, render, wardrobe
from studio.kids.sprites import GROUPS, SpriteBank, missing_groups

BASE = {"eyes-open", "eyes-closed", "mouth-closed", "mouth-open"}


def test_starter_wardrobe_has_8_to_10_eras():
    assert 8 <= len(wardrobe.ERAS) <= 10


@pytest.mark.parametrize("era", wardrobe.ERAS)
def test_every_outfit_keeps_the_sprite_contract_and_identity(era):
    for cid, c in cast.ROSTER.items():
        svg = cast.roster_svg(cid, era)
        assert missing_groups(svg) == [], f"{cid}/{era}"
        assert set(GROUPS) >= BASE
        # identity: same face parts, same badge letter, same silhouette wrapper as the default outfit
        base = cast.roster_svg(cid)
        for part in ('<g id="eyes-open">', '<g id="mouth-open">', f">{c['badge']}</text>"):
            assert part in svg
        assert re.findall(r"<g transform=[^>]*>", svg) == re.findall(r"<g transform=[^>]*>", base)
        assert "{body}" not in svg and "{dark}" not in svg
        assert svg != base


def test_costume_changes_headwear_and_garment_but_not_face():
    plain, roman = cast.roster_svg("quill"), cast.roster_svg("quill", "roman")
    face = lambda s: re.search(r'<g id="eyes-open">.*?</g>', s, re.S).group(0)  # noqa: E731
    assert face(plain) == face(roman)
    assert plain.count("<path") != roman.count("<path") or plain != roman
    assert "bodyclip" in roman and "bodyclip" not in plain


def test_signature_props_survive_a_costume():
    ironhand = cast.roster_svg("ironhand", "viking")
    assert cast.CAST_PROPS["hammer"] in ironhand
    quill = cast.roster_svg("quill", "viking")
    assert cast.CAST_PROPS["hammer"] not in quill
    assert wardrobe.OUTFITS["viking"]["prop"].split('"')[1] in quill or "circle" in quill


def test_character_colour_stays_visible_in_every_era():
    for era in wardrobe.ERAS:
        assert cast.ROSTER["vex"]["body"] in cast.roster_svg("vex", era), era


def test_default_outfit_is_unchanged_and_unknown_outfit_raises():
    assert cast.roster_svg("quill") == cast.roster_svg("quill", "default")
    assert "bodyclip" not in cast.roster_svg("dusty")
    with pytest.raises(ValueError):
        cast.roster_svg("quill", "space_age")


def test_figures_built_for_old_callers_do_not_change():
    plain = cast.build_svg("#C0392B", "helmet", "sword", "H")
    assert plain == cast.build_svg("#C0392B", "helmet", "sword", "H", outfit="default")


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
    pkg = {"era": "bronze", "segments": [{"scene": "lectern", "era": "mars"}]}
    problems = cast.scene_problems(pkg)
    assert any("'bronze'" in p for p in problems) and any("'mars'" in p for p in problems)
    assert cast.scene_problems({"era": "Roman", "segments": [{"scene": "lectern"}]}) == []
    block = cast.prompt_block({"cast": True, "depiction": {"rules": []}})
    assert all(e in block for e in wardrobe.ERAS)


def test_scene_fingerprint_changes_with_era():
    seg = {"scene": "lectern", "cast": ["quill"], "chapter": "c"}
    assert render.fingerprint(seg, 2.0, None) != render.fingerprint({**seg, "era": "roman"}, 2.0, None)


def test_cast_writes_one_outfit_file_per_character_and_era(tmp_path):
    c = render.Cast(tmp_path)
    assert c.key("quill") == "quill"
    assert c.key("Captain Blunder", "roman") == "blunder__roman"
    assert (c.dir / "blunder__roman.svg").exists()
    assert c.key("quill", "not-an-era") == "quill"  # unknown era: default look, no crash
    assert c.key("Hannibal", "roman").startswith("fig_")  # named figures keep their own look
    if c.ok:
        a = c.sprite("quill", 200, 0.4, 0, False)
        b = c.sprite("quill", 200, 0.4, 0, False, era="roman")
        assert a.size == b.size and a.tobytes() != b.tobytes()


def test_scene_clip_renders_in_costume(tmp_path):
    out = tmp_path / "c.mp4"
    seg = {"scene": "title", "cast": ["quill"], "era": "viking", "scene_data": {"title": "Longships"}}
    render.render_scene(seg, 0.5, out, tmp_path)
    assert out.exists() and out.stat().st_size > 1000


def test_preview_sheet_has_every_outfit():
    from studio.util import svg
    if not svg.available():
        pytest.skip("no SVG renderer")
    from studio.history import preview
    img = preview.sheet("quill")
    assert img.width == preview.COLS * preview.CELL
    assert img.height >= -(-(len(wardrobe.ERAS) + 1) // preview.COLS) * preview.CELL
    with pytest.raises(Exception, match="No recurring character"):
        preview.sheet("nobody")


def test_sprite_bank_loads_outfit_files(tmp_path):
    (tmp_path / "q.svg").write_text(cast.roster_svg("quill", "egyptian"), encoding="utf-8")
    bank = SpriteBank(tmp_path)
    if bank.enabled:
        assert bank.get("q", 120) is not None


def test_era_is_guessed_from_the_picked_title_or_topic_when_the_script_has_no_title():
    pkg = {"topic": "all about the british empire",
           "titles": [{"text": "A quiet title", "is_pick": False},
                      {"text": "How the East India Company Really Worked", "is_pick": True}]}
    assert wardrobe.era_for({"narration": "x"}, pkg) == "sail"
    assert wardrobe.era_for({}, {"topic": "the british empire and the navy"}) == "sail"
    assert wardrobe.era_for({}, {"titles": [{"text": "Quiet topic"}]}) == wardrobe.DEFAULT
