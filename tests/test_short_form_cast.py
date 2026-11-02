"""60-second short-form preset, the history cast scene renderer, cast thumbnails, offline voice and kids roster art."""

from __future__ import annotations

import shutil

import pytest
from PIL import Image

from studio.history import render, thumb
from studio.kids import spec, sprites
from studio.kids.sprites import SpriteBank
from studio.providers import tts
from studio.quality import gate
from studio.scenes import plan, validate_scene
from studio.stages.story import validate_outline
from studio.story import profile as sp


def outline(n_beats: int, secs: float = 9.0, loops: int = 2) -> dict:
    beats = [{"n": i + 1, "chapter": "c", "seconds": secs if i else 6, "device": "question" if i % 2 == 0 else "reveal",
              "key_fact": "k"} for i in range(n_beats)]
    return {"audience_question": "q", "big_idea": "b", "promise": "p", "title_promise": "t", "beats": beats,
            "hooks": [{"formula": "cold_open", "line": "A short line. More.", "pick": i == 0} for i in range(3)],
            "loops": [{"id": f"L{i}", "question": "q", "plant": 1 + i, "payoff": 4 + i} for i in range(loops)],
            "ending": {"callback": "c", "takeaway": "t", "cta_question": "q", "next_video": "n"},
            "sources": [{"id": "s1", "title": "t", "url_or_note": "https://x"}], "thumbnail_ideas": ["a", "b", "c"]}


def test_short60_preset_changes_limits_only_when_chosen():
    short, normal = sp.get("history", {"preset": "short60"}), sp.get("history")
    assert short["short_form"] and short["min_beats"] == 5 and not normal.get("short_form")
    assert validate_outline(outline(7), short) == []
    assert any("need 10-18 beats" in p for p in validate_outline(outline(7), normal))
    assert any("at most 8 seconds" in p for p in validate_outline({**outline(7), "beats": [
        {**b, "seconds": 12 if i == 0 else b["seconds"]} for i, b in enumerate(outline(7)["beats"])]}, short))
    assert "SHORT FORM OVERRIDE" in sp.short_form_note(short) and sp.short_form_note(normal) == ""
    with pytest.raises(ValueError):
        sp.get("history", {"preset": "nope"})


def test_gate_uses_short_form_length_and_loops():
    pkg = {"segments": [{"narration": "Scouts say Hannibal is at the Alps. The consul laughs. Why would he?",
                         "est_seconds": 6, "plants_loop": "L1", "visual": {"scene": {"kind": "skit", "mode": "cast"}}}
                        for _ in range(7)] + [{"narration": "Tell us which pass you would bet on.", "est_seconds": 5}],
           "sources": [{"id": "s1"}]}
    short = sp.get("history", {"preset": "short60"})
    rep = gate.evaluate(pkg, "story", None, story_profile=short)
    text = " ".join(i["message"] if "message" in i else str(i) for i in rep["issues"])
    assert "under" not in text and "open loop" not in text
    assert gate._picture_kind(pkg["segments"][0]) == "skit"


def test_string_scene_is_a_cast_scene_not_a_2d_3d_scene():
    assert validate_scene("skit", "segment 1") == []
    assert plan({"scene": "skit", "narration": "x"}, "2d") is None


needs_cairo = pytest.mark.skipif(not sprites.available(), reason="cairosvg/cairo not installed")


@needs_cairo
@pytest.mark.parametrize("kind,data", [
    ("lectern", {"title": "Autumn, 218 BC", "question": "Which pass?"}),
    ("skit", {}), ("map", {"points": [{"label": "A", "x": 0.2, "y": 0.5}, {"label": "B", "x": 0.7, "y": 0.4}]}),
    ("diagram", {"steps": ["a", "b", "c"], "disputed": True}), ("calendar", {"days": 16, "title": "Days"}),
    ("easel", {"title": "List", "items": ["one", "two"]}), ("archive", {"title": "A"}),
    ("silhouette", {"title": "Who?"}), ("title", {"title": "Next"})])
def test_every_cast_scene_draws_a_full_frame(tmp_path, kind, data):
    seg = {"scene": kind, "scene_data": data, "cast": ["quill", "Hannibal"], "chapter": "c",
           "speech": [{"who": "quill", "text": "Hello there"}], "visual_keywords": ["alps"]}
    sc = render.Scene(seg, 6.0, render.Cast(tmp_path), render.envelope(None, 144))
    for t in (0.2, 3.0, 5.9):
        assert sc.frame(t).size == (1280, 720)


@needs_cairo
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")
def test_render_scene_makes_a_clip_and_reuses_it(tmp_path):
    seg = {"scene": "lectern", "scene_data": {"title": "T"}, "cast": ["quill"]}
    out = tmp_path / "s.mp4"
    render.render_scene(seg, 1.0, out, tmp_path)
    assert out.exists() and out.stat().st_size > 1000
    first = out.stat().st_mtime_ns
    render.render_scene(seg, 1.0, out, tmp_path)  # same scene and length: nothing is drawn again
    assert out.stat().st_mtime_ns == first
    render.render_scene({**seg, "scene_data": {"title": "Other"}}, 1.0, out, tmp_path)
    assert out.stat().st_mtime_ns != first


@needs_cairo
def test_historical_figure_keeps_its_faction_colour_and_cast_thumbnails_are_1280x720(tmp_path):
    cst = render.Cast(tmp_path)
    a = cst.key("Hannibal")
    assert a == cst.key("Hannibal") and cst.key("Scipio") != a and cst.key("Captain Blunder") == "blunder"
    pkg = {"segments": [{"scene": "skit", "cast": ["blunder", "dash"]}]}
    imgs = thumb.make(pkg, ["Rome laughed", "x", "Which pass?"], tmp_path)
    assert len(imgs) == 3 and all(isinstance(i, Image.Image) and i.size == (1280, 720) for i in imgs)


def test_envelope_without_audio_is_a_talking_pattern():
    e = render.envelope(None, 48)
    assert len(e) == 48 and min(e) >= 0 and max(e) <= 1


def test_offline_kokoro_is_only_used_when_its_model_files_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("KOKORO_ONNX_DIR", str(tmp_path))
    monkeypatch.setenv("STUDIO_HOME", str(tmp_path))
    assert tts.KokoroOnnxTTS.model_dir() is None and not tts.KokoroOnnxTTS.available()
    for f in tts.KokoroOnnxTTS.FILES:
        (tmp_path / f).write_bytes(b"x")
    assert tts.KokoroOnnxTTS.model_dir() == tmp_path


def test_kids_roster_has_animated_2d_art_and_puddles_are_allowed():
    for name in ("pip", "benny", "mango", "dotty", "tilly"):
        svg = (sprites.BUILTIN / f"{name}.svg").read_text(encoding="utf-8")
        assert not sprites.missing_groups(svg), name
    assert "puddle" in spec.CHARACTERS
    if sprites.available():
        assert SpriteBank().get("pip", 120) is not None


# ---------- cast of ten per channel, per-character voices ----------
def test_kids_roster_has_ten_with_voices_and_sprites() -> None:
    from studio.kids import cast
    roster = cast.load()
    assert len(roster) >= 10 and {"ollie", "gigi", "zuzu", "marlo", "rosie"} <= set(roster)
    for cid, c in roster.items():
        assert c["voice"]["edge"].endswith("Neural") and 0.7 <= c["voice"]["speed"] <= 1.3, cid
        if cid in ("ollie", "gigi", "zuzu", "marlo", "rosie"):
            assert not sprites.missing_groups((sprites.BUILTIN / f"{cid}.svg").read_text()), cid
    assert len({c["main"] for c in roster.values()}) == len(roster)
    assert len({c["voice"]["edge"] + str(c["voice"]["pitch"]) for c in roster.values()}) == len(roster)
    assert cast.voice_for("nobody")["edge"]


def test_history_cast_has_ten_valid_distinct_characters(tmp_path) -> None:
    from studio.history import cast
    assert len(cast.ROSTER) == 10 and {"brine", "hindsight", "ironhand", "alma"} <= set(cast.ROSTER)
    cast.check_roster()
    assert len({c["body"] for c in cast.ROSTER.values()}) == 10
    for f in cast.export_roster(tmp_path):
        assert not sprites.missing_groups(f.read_text(encoding="utf-8")), f.name
    assert cast.voice_for("dash")["rate"] == 18 and cast.build_svg(shape="tall") != cast.build_svg()
    with pytest.raises(ValueError):
        cast.build_svg(shape="giant")
    # generated figures still draw only from the base headwear/props, so old videos do not change
    assert "bicorn" not in cast.HEADWEAR and "telescope" not in cast.PROPS


def test_voice_check_reports_what_to_fix() -> None:
    from studio.errors import StudioError
    from studio.providers import voices
    assert voices.check({"edge": "en-US-AnaNeural", "rate": "5"})["rate"] == 5
    for bad in ({"edge": "ana"}, {"kokoro": "x"}, {"rate": 99}, {"speed": "fast"}):
        with pytest.raises(StudioError):
            voices.check(bad)
    assert voices.prosody(voices.DEFAULT) == {"rate": 0, "pitch": 0, "volume": 0}
