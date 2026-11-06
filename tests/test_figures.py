# ruff: noqa: E501
"""Characters are described by the script and composed from attributes; any role works."""
import subprocess

from studio.history import autoscene, cast, figures, scene_plan
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


def test_cast_draws_described_characters_and_old_fixed_names_from_their_own_words(tmp_path):
    cst = r.Cast(tmp_path, [SOLDIER])
    assert cst.described("spearman") is SOLDIER
    assert cst.described("Quill") == {"name": "Quill", "role": "Quill"}  # old scripts: no fixed art, no crash
    spr = cst.sprite("Spearman", 200, 0.0, 0, False)
    assert spr.size == (200, 200) and not _same(spr, cst.sprite("Quill", 200, 0.0, 0, False))
    assert cst.sprite("Dusty", 120, 0.0, 0, True).size == (120, 120)


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


def test_unusual_roles_are_drawn_from_their_own_description_not_the_fixed_cast(tmp_path):
    mapmaker = {"name": "Mapmaker Odo", "gender": "male", "age": "elder", "clothing": {"type": "apron", "color": "teal"},
                "props": ["scroll"]}
    fisher = {"name": "Fisherwoman", "gender": "female", "clothing": {"type": "dress", "color": "navy"}}
    cst = r.Cast(tmp_path, [mapmaker, fisher])
    assert cst.described("Mapmaker Odo") is mapmaker
    assert cst.described("mapmaker") is mapmaker  # a short role name finds the described character
    assert cst.described("fisherwoman") is fisher
    spy = cst.described("Mir Jafar")  # never described: still its own person
    assert spy == {"name": "Mir Jafar", "role": "Mir Jafar"}
    a, b, c = (cst.sprite(n, 200, 0.0, 0, False) for n in ("mapmaker", "fisherwoman", "Mir Jafar"))
    assert not _same(a, b) and not _same(b, c)


def test_describe_asks_only_for_names_the_script_has_not_described():
    segs = [{"scene": "skit", "cast": ["Coin", "Mir Jafar"], "speech": [{"who": "Ramesh", "text": "x"}]},
            {"scene": "skit", "cast": ["Admiral"]}]
    assert scene_plan.undescribed(segs, None) == ["Coin", "Mir Jafar", "Ramesh", "Admiral"]
    assert scene_plan.undescribed(segs, [{"name": "Madame Coin"}, {"name": "Mir Jafar"}]) == ["Ramesh", "Admiral"]


def test_rule_fallback_casts_only_people_the_script_names_never_the_fixed_cast():
    from studio.history import autoscene
    text = "Hannibal paid the tax and counted the silver."
    assert autoscene._pick_cast(text, ["Hannibal"], 0) == ["Hannibal"]  # noqa: SLF001
    assert autoscene._pick_cast("Why did the taxes rise?", [], 3) == [cast.GENERIC]  # noqa: SLF001


def test_characters_in_one_video_get_different_faces():
    names = ["Gaius", "Dido", "Baal", "Tiro", "Hannibal", "Sophe", "Odo", "Nell", "Rolf", "Livia"]
    faces = {tuple(figures.normalize({"name": n})["face"][k] for k in ("shape", "eyes", "brows", "nose", "mouth")) for n in names}
    assert len(faces) >= 9  # same template, different faces
    pics = {figures.draw({"name": n}, 120).tobytes() for n in names}
    assert len(pics) == len(names)  # even undescribed people each get their own picture


def test_script_face_words_win_and_unknown_words_fall_back():
    n = figures.normalize({"name": "Hannibal", "face": {"nose": "hooked", "eyes": "sharp", "brows": "stern"}, "posture": "proud"})
    assert (n["face"]["nose"], n["face"]["eyes"], n["face"]["brows"], n["face"]["posture"]) == ("hooked", "sharp", "stern", "proud")
    odd = figures.normalize({"name": "Zed", "face": {"nose": "trunk"}})
    assert odd["face"]["nose"] in figures.FACE_OPTIONS["nose"]
    assert figures.normalize({"name": "Zed"}) == figures.normalize({"name": "Zed"})  # stable across scenes


def test_every_face_option_and_posture_draws():
    for part, options in figures.FACE_OPTIONS.items():
        for o in options:
            assert figures.draw({"name": "t", "face": {part: o}}, 80).getchannel("A").getbbox() is not None
    for p in figures.POSTURES:
        assert figures.draw({"name": "t", "posture": p}, 80).getchannel("A").getbbox() is not None


def test_a_returning_name_looks_different_in_another_story_but_not_inside_one(tmp_path):
    from studio.history import figures
    spec = {"name": "Napoleon", "role": "Emperor of the French", "gender": "male", "age": "adult"}
    a = figures.normalize({**spec, "look_seed": "French Empire|10"})
    assert a == figures.normalize({**spec, "look_seed": "French Empire|10"})  # stable within one story
    others = [figures.normalize({**spec, "look_seed": f"Story {k}|{k}"}) for k in range(6)]
    assert any(o["face"] != a["face"] for o in others)  # the same name in another story is not a copy
    assert any(figures.normalize({**spec, "role": f"Role {k}", "look_seed": "x"})["face"] != a["face"] for k in range(6))
    from studio.history import render as r
    same = r.Cast(tmp_path, [spec], "T|1").sprite("Napoleon", 200, 0, 0, False)
    again = r.Cast(tmp_path, [spec], "T|1").sprite("Napoleon", 200, 0, 0, False)
    assert same.tobytes() == again.tobytes()
    assert r.fingerprint({"scene": "title"}, 4.0, None, [spec], "T|1") != r.fingerprint({"scene": "title"}, 4.0, None, [spec], "T|2")
