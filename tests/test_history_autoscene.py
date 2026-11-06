# ruff: noqa: E501
"""Pasted history scripts get cartoon scenes picked from the narration; photos and charts stay rare."""

from studio.history import autoscene, cast
from studio.history import render as r

SEGS = [
    {"narration": "Hannibal was furious. The Romans had taken Sardinia and demanded more silver from Carthage.",
     "chapter": "The grudge", "visual_keywords": ["carthage"]},
    {"narration": "Hannibal marched from Spain over the Alps into Italy with elephants, and Rome had no idea.",
     "chapter": "The grudge"},
    {"narration": "The Senate argued about the cost. Every talent of silver paid for ships, and the treasury was empty.",
     "chapter": "The price"},
    {"narration": "At Cannae the Roman army was slaughtered; thousands died in a single afternoon.", "chapter": "The price"},
    {"narration": "First the legions formed a line. Then the cavalry circled behind. Finally the trap closed, step by step.",
     "chapter": "The price"},
    {"narration": "Hannibal waited 14 days outside the gates, and Rome still refused to talk.", "chapter": "The wait"},
]


def test_every_segment_gets_a_valid_scene_and_no_photo():
    segs = [dict(s) for s in SEGS]
    assert autoscene.assign(segs) == len(segs)
    assert all(s["scene"] in cast.SCENE_TYPES for s in segs)
    assert not any("photo" in s or "chart_data" in s for s in segs)
    assert cast.scene_problems({"segments": segs}) == []
    kinds = [s["scene"] for s in segs]
    assert "map" in kinds and "silhouette" in kinds and "skit" in kinds


def test_skit_has_cast_and_short_speech():
    segs = [dict(s) for s in SEGS]
    autoscene.assign(segs)
    for s in segs:
        if s["scene"] == "skit":
            assert s["cast"] and s["speech"]
            assert all(len(x["text"].split()) <= cast.MAX_SPEECH_WORDS for x in s["speech"])
    assert "Hannibal" in sum((s["cast"] for s in segs), [])  # the recurring figure becomes a character


def test_existing_scene_keys_are_kept():
    segs = [{"narration": "Anything at all happens here today.", "scene": "easel", "cast": ["Hannibal"],
             "scene_data": {"items": ["a"]}}]
    assert autoscene.assign(segs) == 0
    assert segs[0]["scene"] == "easel" and segs[0]["cast"] == ["Hannibal"]


def test_plain_word_scene_is_replaced():
    segs = [{"narration": "A plain word is not a scene type here.", "scene": "skit-ish"}]
    assert autoscene.assign(segs) == 1 and segs[0]["scene"] in cast.SCENE_TYPES


def test_no_three_in_a_row():
    segs = [{"narration": f"Something quiet happens in line number {i} today."} for i in range(8)]
    autoscene.assign(segs)
    kinds = [s["scene"] for s in segs]
    assert not any(kinds[i] == kinds[i + 1] == kinds[i + 2] for i in range(len(kinds) - 2))


def test_persist_keeps_other_fields(tmp_path):
    import json
    p = tmp_path / "script.json"
    p.write_text(json.dumps({"title": "T", "segments": [{"narration": "A quiet little scene is here.", "extra": 1}]}))
    segs = [{"narration": "A quiet little scene is here.", "extra": 1}]
    autoscene.assign(segs)
    autoscene.persist(p, segs)
    raw = json.loads(p.read_text())
    assert raw["title"] == "T" and raw["segments"][0]["extra"] == 1 and raw["segments"][0]["scene"] == "skit"


def test_font_is_a_real_truetype_font():
    f = r.font(40)
    assert f.getlength("Hannibal crosses the Alps") > 300  # the 10 px bitmap default would be far narrower
