"""Renderer, voice, music and colours resolved per video, channel and channel type; every combination mocked."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from studio import production
from studio.blender import provider, title_card
from studio.cli import app
from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channel_types, channels
from studio.kids import build3d
from studio.providers import brand, sound
from studio.stages import build as build_stage
from studio.stages import voice
from tests.test_voice_visuals import FakeTTS, scripted_video

TYPES = list(channel_types.TYPES)


def _settings(root, **kw) -> Settings:
    return Settings(root=root, **kw)


@pytest.mark.parametrize("ctype", TYPES)
def test_type_defaults(root, ctype):
    cid = channels.add(root, f"Chan {ctype}", type=ctype)
    r = production.resolve(_settings(root, renderer="2d", tts_voice="en-US-AndrewNeural", tts_provider="edge"),
                           channel_id=cid)
    t = channel_types.info(ctype)
    assert r["music_mood"] == t["music_mood"] and r["music"] == "generated" and r["renderer"] == "2d"
    assert r["palette"] == t["palette"] and r["mode"] == t["mode"]
    assert r["sources"]["voice"] == ".env"


@pytest.mark.parametrize("ctype", TYPES)
@pytest.mark.parametrize("renderer", ["2d", "blender"])
@pytest.mark.parametrize("music", ["generated", "none"])
def test_precedence_video_beats_channel_beats_type(root, ctype, renderer, music):
    cid = channels.add(root, "Mix", type=ctype, renderer=renderer, music=music, voice="en-GB-RyanNeural")
    s = _settings(root, renderer="2d", tts_voice="en-US-AndrewNeural")
    r = production.resolve(s, channel_id=cid)
    assert (r["renderer"], r["music"], r["voice"]) == (renderer, music, "en-GB-RyanNeural")
    assert r["sources"]["renderer"] == "channel"
    other = "2d" if renderer == "blender" else "blender"
    production.set_video(s, 7, renderer=other, voice="en-IN-PrabhatNeural", music_mood="major")
    r = production.resolve(s, 7, cid)
    assert (r["renderer"], r["voice"], r["music_mood"]) == (other, "en-IN-PrabhatNeural", "major")
    assert r["sources"]["renderer"] == "video" and r["music"] == music  # untouched fields follow the channel
    production.clear_video(s, 7)
    assert production.resolve(s, 7, cid)["renderer"] == renderer


def test_validation_and_custom_colours(root):
    with pytest.raises(StudioError, match="not a valid renderer"):
        channels.add(root, "Bad", renderer="unreal")
    s = _settings(root)
    with pytest.raises(StudioError, match="not a valid music"):
        production.set_video(s, 1, music="loud")
    with pytest.raises(StudioError, match="Unknown production setting"):
        production.set_video(s, 1, colour="red")
    cid = channels.add(root, "Brand", type="kids", brand_primary="#111111", brand_accent="#222222")
    r = production.resolve(s, channel_id=cid)
    assert r["palette"] == ("#111111", "#222222") and r["sources"]["palette"] == "channel"
    assert "Channel type: kids" in production.describe(s, channel_id=cid)


def test_apply_sets_voice_provider_renderer_and_kids_flag(root):
    cid = channels.add(root, "Tiny", type="kids", voice="en-US-JennyNeural", renderer="blender", tts_provider="silent")
    s = production.apply(_settings(root, renderer="2d"), channel_id=cid)
    assert (s.tts_voice, s.tts_provider, s.renderer, s.made_for_kids) == ("en-US-JennyNeural", "silent",
                                                                           "blender", True)


def test_voice_stage_uses_per_video_voice(ctx, monkeypatch):
    v = scripted_video(ctx)
    production.set_video(ctx.settings, v.id, voice="en-AU-WilliamNeural", tts_provider="silent")
    seen = []
    monkeypatch.setattr(voice, "get_tts", lambda s: seen.append((s.tts_voice, s.tts_provider)) or FakeTTS())
    voice.run(ctx, v.id, measure=lambda p: 5.0)
    assert seen == [("en-AU-WilliamNeural", "silent")]


def test_palette_context_restores_and_changes_colours():
    before = (brand.BG, brand.ACCENT, brand.SERIES[0])
    with brand.use(("#010203", "#040506")):
        assert (brand.BG, brand.ACCENT, brand.SERIES[0]) == ("#010203", "#040506", "#040506")
    assert (brand.BG, brand.ACCENT, brand.SERIES[0]) == before
    with brand.use(None):
        assert before[0] == brand.BG


def test_thumbnails_use_the_channel_palette(ctx):
    from studio.stages import thumbnail
    cid = channels.add(ctx.settings.root, "Tiny", type="kids")
    assert cid == "tiny"
    v = scripted_video(ctx)
    from studio.models import Video
    from studio.stages.base import advance
    for st in ("voiced", "visuals_ready", "built"):
        advance(ctx.session.get(Video, v.id), st)
    ctx.session.commit()
    thumbnail.run(ctx, v.id)
    px = Image.open(ctx.settings.project_dir(v.id) / "thumbs" / "thumb_3.jpg").convert("RGB").getpixel((600, 5))
    assert px[2] > px[0]  # kids blue (#1D4ED8); the default slate (#0F172A) has a blue channel of only 42
    assert px[2] > 150


def test_music_none_gives_silent_track_and_mood_changes_bed(tmp_path):
    out = sound.ensure_sound(tmp_path, "major")
    assert out["silence"].exists() and out["music"].name == "bed_major.wav"
    assert sound.ensure_sound(tmp_path, "minor")["music"].name == "bed_minor.wav"


@pytest.mark.parametrize("ctype", TYPES)
@pytest.mark.parametrize("renderer", ["2d", "blender"])
def test_narrated_intro_is_3d_only_when_requested_and_available(root, monkeypatch, ctype, renderer):
    cid = channels.add(root, "N", type=ctype, renderer=renderer)
    s = _settings(root, renderer="2d")
    prod = production.resolve(s, channel_id=cid)
    made = {}

    def fake_make(exe, title, palette, out, work, size, **kw):
        made.update(title=title, palette=palette)
        out.write_bytes(b"x")
        return out

    monkeypatch.setattr(title_card, "make", fake_make)
    monkeypatch.setattr(build3d, "choose", lambda r, p="": Path("blender") if r == "blender" else None)

    class C:
        settings = s

    tmp = root / "tmp"
    tmp.mkdir()
    card = build_stage._title_card(C, prod, {"titles": [{"text": "A", "is_pick": False},
                                                          {"text": "How X makes money", "is_pick": True}]}, tmp)
    if renderer == "2d":
        assert card is None and not made
    else:
        assert card is not None and made["title"] == "How X makes money"
        assert made["palette"] == channel_types.info(ctype)["palette"]


def test_blender_missing_falls_back_to_no_3d_intro(root, monkeypatch, capsys):
    monkeypatch.setattr(provider, "usable", lambda p="": (None, "Blender was not found."))

    class C:
        settings = _settings(root)

    assert build_stage._title_card(C, {"renderer": "blender", "palette": None}, {}, root) is None
    assert "2D renderer" in capsys.readouterr().err


def test_title_card_renders_frames_then_encodes(tmp_path, monkeypatch):
    seen = {}

    def fake_render(exe, cfg, out_dir):
        seen.update(cfg)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(3):
            f = out_dir / f"f_{i + 1:04d}.png"
            Image.new("RGB", (64, 36), (10, 20, 200)).save(f)
            files.append(f)
        return files

    monkeypatch.setattr(provider, "render_frames", fake_render)
    out = title_card.make(Path("blender"), "How a very long channel title really makes money", ("#111111", "#eeeeee"),
                          tmp_path / "t.mp4", tmp_path / "frames", (64, 36), fps=6, seconds=0.5)
    assert seen["kind"] == "title" and seen["bg"] == "#111111" and seen["text"].count("\n") <= 2
    if shutil.which("ffmpeg"):
        assert out.exists() and out.stat().st_size > 500


def test_real_bpy_title_render(tmp_path):
    pytest.importorskip("bpy")
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import scene_script as s; "
            "s.main(json.loads(sys.argv[2]))")
    cfg = {"kind": "title", "text": "How X\nmakes money", "bg": "#1D4ED8", "accent": "#FACC15", "duration": 0.25,
           "fps": 4, "width": 96, "height": 54, "out_dir": str(tmp_path), "background": "sky"}
    env = {**__import__("os").environ, "STUDIO_BLENDER_ENGINE": "CYCLES"}
    proc = subprocess.run([sys.executable, "-I", "-c", code, str(Path(provider.__file__).parent), json.dumps(cfg)],
                          capture_output=True, text=True, timeout=170, env=env)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert list(tmp_path.glob("f_*.png"))


def test_cli_production_commands_and_channel_options(root, monkeypatch):
    monkeypatch.chdir(root)
    monkeypatch.setenv("STUDIO_HOME", str(root))
    run = CliRunner().invoke
    r = run(app, ["channels", "add", "Tiny Tunes", "--type", "kids", "--renderer", "blender", "--music", "none"])
    assert r.exit_code == 0, r.output
    out = run(app, ["production", "show"]).output
    assert "blender" in out and "from channel" in out and "none" in out
    out = run(app, ["production", "set", "5", "--renderer", "2d", "--voice", "en-GB-SoniaNeural"]).output
    assert "2d" in out and "from video" in out and "en-GB-SoniaNeural" in out
    assert "blender" in run(app, ["production", "show"]).output  # channel itself unchanged
    assert "from video" not in run(app, ["production", "set", "5", "--renderer", "", "--voice", ""]).output
    assert run(app, ["production", "set", "5", "--renderer", "unreal"]).exit_code != 0
    assert "follows its channel" in run(app, ["production", "reset", "5"]).output
