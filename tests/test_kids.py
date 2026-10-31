"""Kids mode: script validation, prompt handoff, scene timing, rendering and checklist (no network)."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from studio.errors import PendingLLMResponse, StudioError
from studio.kids import build, checklist, demo, draw, spec
from studio.kids import script as kscript

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "kids_sample.json").read_text())


def good() -> dict:
    return copy.deepcopy(SAMPLE)


def test_sample_is_valid() -> None:
    assert spec.validate(good()) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.update(scenes=d["scenes"][:3]), "at least 4 scenes"),
    (lambda d: d["scenes"][2].update(kind="verse"), "chorus must appear at least twice"),
    (lambda d: d["scenes"][4]["lines"].__setitem__(0, "A different chorus line"), "word for word"),
    (lambda d: d["scenes"][0]["lines"].__setitem__(0, "one two three four five six seven eight nine"), "1 to 8 words"),
    (lambda d: d["scenes"][0]["visual"].update(characters=["dragon"]), "characters"),
    (lambda d: d["scenes"][0]["visual"].update(motion="explode"), "motion"),
    (lambda d: d.update(title="Cocomelon style ducks"), "franchises"),
    (lambda d: d.update(source="public_domain"), "source_note"),
    (lambda d: d.update(source="stolen"), "source"),
])
def test_validation_rejects(mutate, needle: str) -> None:
    d = good()
    mutate(d)
    assert any(needle in p for p in spec.validate(d))


def test_banned_names_match_whole_words_only() -> None:
    d = good()
    d["scenes"][0]["lines"][0] = "A jjump over the pond"  # contains 'jj' but not as a word
    assert spec.validate(d) == []


def test_prompt_lists_rules_and_vocabulary() -> None:
    p = kscript.build_prompt("counting ducks")
    assert "counting ducks" in p and "ORIGINAL" in p and "no Cocomelon" in p
    assert all(c in p for c in spec.CHARACTERS)


def test_script_stage_hands_off_then_accepts(make_ctx) -> None:
    ctx = make_ctx()
    with pytest.raises(PendingLLMResponse):
        kscript.run(ctx, "Counting Ducks")
    d = kscript.project_dir(ctx, "counting-ducks")
    assert (d / "prompts" / "kids_script.prompt.md").exists()
    (d / "prompts" / "kids_script.response.json").write_text(json.dumps(good()))
    data = kscript.run(ctx, "Counting Ducks")
    assert data["slug"] == "counting-ducks" and (d / "script.json").exists()


def test_script_stage_reports_problems(make_ctx) -> None:
    ctx = make_ctx()
    d = kscript.project_dir(ctx, "bad")
    bad = good()
    bad["scenes"] = bad["scenes"][:2]
    (d / "prompts").mkdir(exist_ok=True)
    (d / "prompts" / "kids_script.response.json").write_text(json.dumps(bad))
    with pytest.raises(StudioError, match="failed validation"):
        kscript.run(ctx, "bad")


def test_slugify_rejects_empty() -> None:
    with pytest.raises(StudioError):
        kscript.slugify("!!!")


def test_scene_timing_and_line_highlight() -> None:
    assert build.scene_seconds(1.0) == build.MIN_SCENE_SECONDS
    assert build.scene_seconds(10.0) == 10.0 + build.TAIL
    scene = {"lines": ["one two", "three four five six"]}  # 2 and 4 words -> split 1/3, 2/3
    assert build.line_index(scene, 0.5, 6.0) == 0
    assert build.line_index(scene, 2.5, 6.0) == 1
    assert build.line_index(scene, 99, 6.0) == 1


def test_motion_pops_in_in_order() -> None:
    assert draw.motion("bounce", 0.0, 2, 100)[2] == 0.0  # third item not yet visible
    assert draw.motion("bounce", 5.0, 2, 100)[2] == pytest.approx(1.0)


def test_every_character_and_background_draws() -> None:
    img = Image.new("RGB", (200, 200), "white")
    for name in spec.CHARACTERS:
        d = draw.ImageDraw.Draw(img)
        draw.draw_character(d, name, 100, 100, 120)
    for bg in spec.BACKGROUNDS:
        assert draw.background(bg, 160, 90).size == (160, 90)


def test_demo_builds_playable_video_and_is_idempotent(make_ctx) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    ctx = make_ctx()
    out = demo.run(ctx)
    assert out.exists() and out.stat().st_size > 10_000
    assert (out.parent / "thumbnail.jpg").exists()
    stamp = out.stat().st_mtime_ns
    demo.run(ctx)  # build.run skips a finished video unless --force
    assert out.stat().st_mtime_ns == stamp


def test_build_without_script_fails_clearly(make_ctx) -> None:
    with pytest.raises(StudioError, match="No script"):
        build.run(make_ctx(), "nothing")


def test_checklist_never_publishes_and_flags_gaps(make_ctx, tmp_path: Path) -> None:
    (tmp_path / "script.json").write_text(json.dumps(good()))
    r = checklist.run(tmp_path)
    assert not r["ready_to_upload"]  # no video or thumbnail yet
    assert {a["id"] for a in r["auto"] if not a["ok"]} == {"video_built", "thumbnail_built"}
    assert any(m["id"] == "audience" for m in r["manual"])
    assert "never uploads" in checklist.render_text(r)
    assert (tmp_path / "made_for_kids_checklist.json").exists()


# ---------------- stage 2: SVG cast, camera, music, variety ----------------
from studio.kids import music, sprites, variety  # noqa: E402

needs_cairo = pytest.mark.skipif(not sprites.available(), reason="cairosvg/cairo not installed")


def test_builtin_cast_has_all_state_groups() -> None:
    files = sorted(sprites.BUILTIN.glob("*.svg"))
    assert {f.stem for f in files} >= {"duck", "bunny", "cat", "dog", "bird"}
    for f in files:
        assert sprites.missing_groups(f.read_text()) == [], f.name


def test_variant_keeps_one_eye_state_and_one_mouth_state() -> None:
    svg = (sprites.BUILTIN / "cat.svg").read_text()
    v = sprites.variant(svg, eyes_closed=True, mouth_open=False)
    assert 'id="eyes-closed"' in v and 'id="eyes-open"' not in v
    assert 'id="mouth-closed"' in v and 'id="mouth-open"' not in v


def test_blink_and_talking_timing() -> None:
    assert sprites.blink(0.05, 0) and not sprites.blink(1.0, 0)
    assert sprites.talking(0.0, 0, 3.0) and not sprites.talking(0.0, 1, 3.0)
    assert not sprites.talking(0.0, 0, 0.0)  # silent once the narration is over


@needs_cairo
def test_sprite_bank_renders_caches_and_falls_back(tmp_path: Path) -> None:
    bank = sprites.SpriteBank(tmp_path)
    a = bank.get("duck", 200)
    assert a is not None and a.mode == "RGBA" and a.width == 200
    assert bank.get("duck", 200) is a  # cached
    assert bank.get("star", 200) is None  # no SVG: caller draws the code shape


@needs_cairo
def test_owner_svg_overrides_builtin_and_bad_svg_is_ignored(tmp_path: Path) -> None:
    custom = (sprites.BUILTIN / "duck.svg").read_text().replace("#ffd93b", "#00ff00")
    (tmp_path / "duck.svg").write_text(custom)
    green = sprites.SpriteBank(tmp_path).get("duck", 120)
    stock = sprites.SpriteBank(None).get("duck", 120)
    assert green.getpixel((60, 28)) != stock.getpixel((60, 28))
    (tmp_path / "cat.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")  # missing groups
    assert sprites.SpriteBank(tmp_path).get("cat", 120) is not None  # falls through to the built-in cat


def test_camera_keeps_frame_size_for_every_move() -> None:
    img = Image.new("RGB", (160, 90), "white")
    for kind in draw.CAMERAS:
        for p in (0.0, 0.5, 1.0):
            assert draw.camera(img, p, kind).size == (160, 90)


def test_music_is_valid_wav_original_per_title_and_deterministic(tmp_path: Path) -> None:
    import wave

    a = music.render("Five Ducks", tmp_path / "a.wav")
    b = music.render("Five Ducks", tmp_path / "b.wav")
    c = music.render("Seven Frogs", tmp_path / "c.wav")
    with wave.open(str(a)) as w:
        assert w.getframerate() == music.RATE and w.getnchannels() == 1 and w.getnframes() > music.RATE * 10
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() != c.read_bytes()


def test_variety_flags_copies_and_repeated_cast() -> None:
    first, copy_ = good(), good()
    assert any("the same" in w for w in variety.compare(copy_, [first]))
    other = good()
    other["scenes"][0]["lines"] = ["Frogs hop on a log", "plop plop plop"]
    for s in other["scenes"][1:]:
        s["lines"] = ["Totally different words here", "nothing alike at all"]
    assert variety.compare(other, [first]) == []
    assert any("mass-produced" in w for w in variety.compare(other, [good(), good(), good()]))


def test_checklist_includes_variety_against_sibling_projects(tmp_path: Path) -> None:
    for name in ("kids_a", "kids_b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "script.json").write_text(json.dumps(good()))
    r = checklist.run(tmp_path / "kids_b")
    v = next(a for a in r["auto"] if a["id"] == "variety")
    assert not v["ok"] and not r["ready_to_upload"]


def test_invalid_camera_is_rejected() -> None:
    d = good()
    d["scenes"][0]["visual"]["camera"] = "spin"
    assert any("camera" in p for p in spec.validate(d))


def test_render_frame_with_sprites_and_camera_changes_pixels() -> None:
    scene = good()["scenes"][0]
    bg = draw.background("ocean", 320, 180)
    font = build.font_path(None)
    plain = draw.render_frame(scene, 1.0, bg, 0, font, False)
    fancy = draw.render_frame(scene, 1.0, bg, 0, font, False, sprites.SpriteBank(None), 2.0, 0.5, "zoom_in")
    assert plain.size == fancy.size == (320, 180)
    assert plain.tobytes() != fancy.tobytes()
