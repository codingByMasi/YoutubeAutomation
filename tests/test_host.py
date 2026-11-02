"""Host-character scenes: validation, automatic action choice, mouth envelope, config and 2D fallback.

Blender is never needed; a smoke test that builds every character/action/set/prop runs only where `bpy` is installed.
"""

from __future__ import annotations

import importlib.util
import math
import shutil
import struct
import sys
import wave
from pathlib import Path

import pytest

from studio import scenes
from studio.errors import StudioError
from studio.growth import identity
from studio.scenes import host, render2d, render3d

PENNY = {"name": "Penny", "kind": "coin", "color": "#F5B700"}


def prod(**kw) -> dict:
    return {"scene_style": "3d", "segment_styles": {}, "mascot": PENNY, "host": "auto", **kw}


def test_validate_accepts_defaults_and_rejects_unknowns():
    assert scenes.validate_scene({"kind": "host"}, "s1") == []
    ok = {"kind": "host", "action": "point", "set": "vault",
          "props": ["money_stack", {"kind": "logo_block", "label": "ACME"}]}
    assert scenes.validate_scene(ok, "s1") == []
    bad = scenes.validate_scene({"kind": "host", "action": "dance", "set": "moon", "props": ["rocket"]}, "s1")
    assert len(bad) == 3 and "dance" in bad[0]
    assert "at most" in scenes.validate_scene({"kind": "host", "props": ["bars_up"] * 5}, "s1")[0]


def test_a_prop_with_a_figure_needs_a_source():
    scene = {"kind": "host", "props": [{"kind": "money_stack", "figure": "$1.4B"}]}
    assert "source" in scenes.validate_scene(scene, "s1")[0]
    scene["source_ids"] = ["s1"]
    assert scenes.validate_scene(scene, "s1", source_ids={"s1"}) == []
    assert "unknown source" in scenes.validate_scene(scene, "s1", source_ids={"s2"})[0]


@pytest.mark.parametrize("text,action,set_", [
    ("Kodak went bankrupt in 2012.", "fall", "street"),
    ("Why did nobody see it coming?", "think", "studio"),
    ("Profit hit a record and doubled.", "celebrate", "stage"),
    ("The cash sat in the vault.", "point", "vault"),
])
def test_choose_reads_the_narration(text, action, set_):
    c = host.choose({"narration": text})
    assert (c["action"], c["set"]) == (action, set_)
    assert set(c["props"]) <= set(host.PROPS)


def test_choose_without_keywords_varies_but_stays_valid():
    seen = {host.choose({"narration": "Here is the plan."}, pos)["action"] for pos in range(1, 5)}
    assert len(seen) > 1 and seen <= set(host.ACTIONS)


def test_plan_for_adds_host_scenes_only_when_asked():
    seg = {"narration": "A calm intro."}
    pl = scenes.plan_for(seg, 1, prod())
    assert pl["mode"] == "3d" and pl["scene"]["kind"] == "host" and pl["scene"]["mascot"]["name"] == "Penny"
    assert scenes.plan_for(seg, 2, prod()) is None  # every other segment keeps stock footage
    assert scenes.plan_for(seg, 3, prod())["scene"]["kind"] == "host"
    assert scenes.plan_for(seg, 1, prod(host="off")) is None
    assert scenes.plan_for(seg, 1, prod(mascot={})) is None
    assert scenes.plan_for(seg, 1, prod(scene_style="2d")) is None
    assert scenes.plan_for({**seg, "chart_data": {"type": "flow"}}, 1, prod()) is None
    assert scenes.plan_for(seg, 1, prod(segment_styles={1: "2d"})) is None


def test_explicit_host_scene_gets_the_channel_mascot():
    pl = scenes.plan_for({"scene": {"kind": "host", "action": "wave"}}, 2, prod())
    assert pl["scene"]["action"] == "wave" and pl["scene"]["mascot"]["kind"] == "coin"


def test_every_channel_character_has_a_2d_picture():
    for kind in identity.MASCOT_KINDS:
        assert identity.mascot_image({"name": "x", "kind": kind}, 120).size == (120, 120)
    assert set(identity.MASCOT_KINDS) >= {"coin", "owl", "robot", "piggy", "bull", "analyst"}
    cleaned = identity.clean_mascot({"name": "Sam", "kind": "analyst", "skin": "#C68642", "hair_style": "curly"})
    assert cleaned["skin"] == "#C68642" and cleaned["hair_style"] == "curly"
    with pytest.raises(StudioError):
        identity.clean_mascot({"name": "Sam", "kind": "analyst", "hair_style": "mohawk"})


def test_scene_config_carries_the_host_fields():
    scene = {"kind": "host", "action": "point", "set": "vault", "props": ["bars_up"], "mascot": PENNY}
    cfg = render3d.scene_config(scene, 5.0, (640, 360), "", [0.5, 1.0])
    assert (cfg["scene"], cfg["action"], cfg["set"], cfg["props"]) == ("host", "point", "vault", ["bars_up"])
    assert cfg["mascot"]["kind"] == "coin" and cfg["mouth"] == [0.5, 1.0] and cfg["items"] == []
    assert "action" not in render3d.scene_config({"kind": "timeline", "items": []}, 5.0, (640, 360))


def test_envelope_without_audio_is_a_valid_pattern():
    env = host.envelope(None, 2.0, 15)
    assert len(env) == 30 and all(0.0 <= v <= 1.0 for v in env)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_envelope_follows_loudness(tmp_path):
    wav = tmp_path / "v.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
        loud = [int(12000 * math.sin(i * 0.3)) for i in range(8000)]  # 1 s of tone, then 1 s of silence
        w.writeframes(struct.pack("<16000h", *(loud + [0] * 8000)))
    env = host.envelope(wav, 2.0, 10)
    assert len(env) == 20 and min(env[:8]) > 0.5 and max(env[12:]) == 0.0


def test_unreadable_audio_falls_back(tmp_path):
    (tmp_path / "bad.mp3").write_bytes(b"not audio")
    assert len(host.envelope(tmp_path / "bad.mp3", 1.0, 10)) == 10


def test_2d_fallback_draws_the_mascot(tmp_path):
    frames = render2d.render({"kind": "host", "title": "Kodak", "action": "shock", "mascot": PENNY}, "", tmp_path, "s")
    assert len(frames) == 1 and frames[0].exists()


@pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="bpy (Blender as a module) not installed")
@pytest.mark.parametrize("kind", identity.MASCOT_KINDS)
def test_blender_builds_every_character_action_set_and_prop(kind, tmp_path):
    sys.path.insert(0, str(Path(render3d.__file__).parents[1] / "blender"))
    import scene_script as ss

    for i, action in enumerate(host.ACTIONS):
        cfg = {"kind": "scene", "scene": "host", "title": "t", "items": [], "footnote": "", "bg": "#0B1F3A",
               "fg": "#F8FAFC", "muted": "#94A3B8", "accent": "#F5B700", "panel": "#12294A",
               "series": ["#38BDF8", "#F5B700", "#22C55E", "#EF4444", "#A78BFA", "#FB923C"], "duration": 2.0, "fps": 6,
               "width": 64, "height": 36, "engine": "CYCLES", "samples": 1, "still": 3, "action": action,
               "set": host.SETS[i % len(host.SETS)], "props": [host.PROPS[(i + j) % len(host.PROPS)] for j in range(3)],
               "mascot": {"kind": kind, "color": "#F5B700"}, "out_dir": str(tmp_path / f"{kind}_{action}")}
        ss.main(cfg)
        assert (tmp_path / f"{kind}_{action}" / "still.png").exists()
