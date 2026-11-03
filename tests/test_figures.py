# ruff: noqa: E501
"""Characters are described by the script and composed from attributes; any role works."""
import subprocess

from studio.history import autoscene, figures, scene_plan
from studio.history import render as r
from studio.history import speech_audio as sa

SOLDIER = {"name": "Spearman", "gender": "male", "armour": "chainmail", "headwear": "helmet", "props": ["spear", "shield"]}
WOMAN = {"name": "Queen Dido", "gender": "female", "clothing": {"type": "gown", "color": "purple"}, "headwear": "crown",
         "hair": {"style": "long", "color": "auburn"}}


def _same(a, b):
    return a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def test_attributes_change_the_picture():
    a, b = figures.draw(SOLDIER, 200), figures.draw(WOMAN, 200)
    assert not _same(a, b) and a.size == (200, 200)
    assert not _same(figures.draw(dict(SOLDIER, skin="dark"), 200), a)
    assert not _same(figures.draw(dict(SOLDIER, age="child"), 200), a)
    assert not _same(figures.draw(dict(SOLDIER, props=["bow"]), 200), a)


def test_same_description_same_picture_and_blink_mouth_states():
    assert _same(figures.draw(WOMAN, 160), figures.draw(dict(WOMAN), 160))
    assert not _same(figures.draw(WOMAN, 160, eyes_closed=True), figures.draw(WOMAN, 160))
    assert not _same(figures.draw(WOMAN, 160, mouth_open=True), figures.draw(WOMAN, 160))


def test_unfamiliar_words_fall_back_instead_of_breaking():
    odd = {"name": "Zorblax", "clothing": {"type": "spacesuit", "color": "#123456"}, "headwear": "antennae",
           "props": ["glowing orb"], "armour": "force_field", "hair": {"style": "swirl"}, "skin": "teal", "build": "gaseous"}
    assert figures.draw(odd, 120).getchannel("A").getbbox() is not None
    assert figures.draw({}, 120).getchannel("A").getbbox() is not None  # an empty description still draws someone


def test_gender_is_never_guessed_from_a_name():
    assert figures.normalize({"name": "Maria"})["gender"] == "neutral"
    assert figures.normalize({"name": "Hannibal"})["gender"] == "neutral"
    assert figures.normalize({"name": "x", "gender": "female"})["gender"] == "female"


def test_era_supplies_clothes_only_when_the_script_gives_none():
    n = figures.normalize({"name": "x"}, figures.ERA_STYLE["roman"])
    assert n["clothing"] == "toga"
    n = figures.normalize({"name": "x", "clothing": {"type": "apron"}}, figures.ERA_STYLE["roman"])
    assert n["clothing"] == "apron"


def test_cast_draws_described_characters_but_keeps_the_recurring_host(tmp_path):
    cst = r.Cast(tmp_path, [SOLDIER, {"name": "Quill", "gender": "female"}])
    assert cst.described("spearman") is SOLDIER
    assert cst.described("quill") is None and cst.described("Quill") is None  # the host stays the recurring cast
    spr = cst.sprite("Spearman", 200, 0.0, 0, False)
    assert spr.size == (200, 200) and not _same(spr, cst.sprite("Quill", 200, 0.0, 0, False))


def test_scene_renders_with_script_characters(tmp_path):
    seg = {"scene": "skit", "narration": "A spearman and a queen argue.", "cast": ["Spearman", "Queen Dido"],
           "speech": [{"who": "Spearman", "text": "We march at dawn."}, {"who": "Queen Dido", "text": "Not without me."}]}
    sc = r.Scene(seg, 6.0, r.Cast(tmp_path, [SOLDIER, WOMAN]), [1.0] * 200, 0)
    assert sc.frame(3.0).size == (r.W, r.H)


def test_fingerprint_changes_when_a_character_is_edited():
    seg = {"scene": "skit", "cast": ["Spearman"], "speech": []}
    a = r.fingerprint(seg, 5.0, None, [SOLDIER])
    assert a != r.fingerprint(seg, 5.0, None, [dict(SOLDIER, skin="dark")])
    assert a == r.fingerprint(seg, 5.0, None, [SOLDIER, WOMAN])  # an unused character does not matter


def test_voices_follow_the_description():
    chars = [SOLDIER, WOMAN, {"name": "Boy", "age": "child"}, {"name": "Elder", "gender": "male", "age": "elder"}]
    male, female = sa.voice_for("Spearman", chars), sa.voice_for("Queen Dido", chars)
    assert male["kokoro"][1] == "m" and female["kokoro"][1] == "f"
    assert sa.voice_for("Boy", chars)["speed"] > 1.1 and sa.voice_for("Elder", chars)["speed"] < 1.0
    assert sa.voice_for("Spearman", chars) == sa.voice_for("Spearman", chars)
    explicit = sa.voice_from_spec({"name": "x", "voice": {"kokoro": "am_adam", "edge": "en-US-GuyNeural"}})
    assert explicit["kokoro"] == "am_adam"


def test_rule_based_characters_use_titles_not_names_for_gender():
    segs = [{"narration": "Queen Dido built a city. Dido trusted the sailors."},
            {"narration": "Later Dido saw a fleet. Hannibal was far away. Hannibal asked about Dido."},
            {"narration": "Then Hannibal crossed the Alps. Hannibal won."}]
    chars = {c["name"]: c for c in autoscene.characters_for(segs)}
    assert chars["Dido"]["gender"] == "female" and chars["Dido"]["headwear"] == "crown"  # from the word "Queen"
    assert chars["Hannibal"]["gender"] == "neutral"


def test_scene_plan_keeps_the_scripts_characters():
    store = {}
    data = {"characters": [SOLDIER, {"name": "spearman"}], "segments": [{"scene": "skit", "cast": ["Spearman"], "speech": []}]}
    assert scene_plan.validate(data, 1) == []
    scene_plan.merge([{"narration": "x"}], data, store)
    assert [c["name"] for c in store["characters"]] == ["Spearman"]  # duplicates by name collapse
    assert scene_plan.validate({"characters": ["bad"], "segments": [{}]}, 1)
    assert "characters" in scene_plan.build_prompt([{"narration": "A queen.", "chapter": "c"}])
    _ = subprocess
