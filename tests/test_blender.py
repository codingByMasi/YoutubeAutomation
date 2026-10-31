"""Optional Blender renderer: discovery, fallback to 2D, config for Blender, and the in-Blender script's syntax.

Blender itself is never run here (it is PC-only); render_frames is replaced with a fake that writes PNGs.
"""

from __future__ import annotations

import ast
import shutil
import stat
import sys
from pathlib import Path

import pytest
from PIL import Image

from studio.blender import provider
from studio.config import load_settings
from studio.errors import ConfigError, StudioError
from studio.kids import build3d, demo

SCENE = {"kind": "verse", "lines": ["One little duck", "Swims in the pond"],
         "visual": {"background": "ocean", "characters": ["duck"], "count": 3, "motion": "bounce"}}


def fake_blender(tmp_path: Path, version_line: str = "Blender 4.5.1") -> Path:
    exe = tmp_path / "blender"
    exe.write_text(f"#!/bin/sh\necho '{version_line}'\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def test_find_blender_uses_setting_then_path(tmp_path, monkeypatch) -> None:
    exe = fake_blender(tmp_path)
    assert provider.find_blender(str(exe)) == exe
    assert provider.find_blender(str(tmp_path / "nope")) is None
    monkeypatch.setattr(provider.shutil, "which", lambda name: str(exe))
    assert provider.find_blender() == exe


def test_usable_checks_version(tmp_path) -> None:
    assert provider.usable(str(fake_blender(tmp_path)))[0] is not None
    exe, why = provider.usable(str(fake_blender(tmp_path, "Blender 3.6.2")))
    assert exe is None and "4.2" in why
    exe, why = provider.usable(str(tmp_path / "missing"))
    assert exe is None and "BLENDER_PATH" in why


def test_missing_blender_falls_back_to_2d(monkeypatch, capsys) -> None:
    monkeypatch.setattr(provider, "find_blender", lambda configured="": None)
    assert build3d.choose("blender") is None
    assert "2D renderer" in capsys.readouterr().err
    assert build3d.choose("2d") is None  # the default never touches Blender


def test_scene_config_matches_scene() -> None:
    cfg = build3d.scene_config(SCENE, 5.0, (1280, 720), 24, "pan_left")
    assert cfg["count"] == 3 and cfg["characters"] == ["duck"] and cfg["camera"] == "pan_left"
    assert (cfg["width"], cfg["height"], cfg["fps"], cfg["duration"]) == (1280, 720, 24, 5.0)


def test_render_frames_reports_blender_failure(tmp_path, monkeypatch) -> None:
    exe = fake_blender(tmp_path)  # prints a version and renders nothing
    with pytest.raises(StudioError, match="Blender failed"):
        provider.render_frames(exe, build3d.scene_config(SCENE, 1, (64, 36), 4, ""), tmp_path / "f")


def test_blender_path_builds_video_with_captions(make_ctx, monkeypatch) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

    def fake_render(exe, cfg, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(round(cfg["duration"] * cfg["fps"])):
            f = out_dir / f"f_{i + 1:04d}.png"
            Image.new("RGB", (cfg["width"], cfg["height"]), (120, 200, 255)).save(f)
            files.append(f)
        return files

    monkeypatch.setattr(build3d, "choose", lambda renderer, path="": Path("blender") if renderer == "blender" else None)
    monkeypatch.setattr(provider, "render_frames", fake_render)
    out = demo.run(make_ctx(), renderer="blender")
    assert out.exists() and out.stat().st_size > 10_000
    assert not list(out.parent.glob("frames3d_*"))  # temporary frames are cleaned up


def test_renderer_setting_validated(root, monkeypatch) -> None:
    monkeypatch.setenv("RENDERER", "unreal")
    with pytest.raises(ConfigError, match="RENDERER"):
        load_settings(root)
    monkeypatch.setenv("RENDERER", "blender")
    monkeypatch.setenv("BLENDER_PATH", "C:/x/blender.exe")
    s = load_settings(root)
    assert s.renderer == "blender" and s.blender_path == "C:/x/blender.exe"


def test_default_renderer_is_2d(root) -> None:
    assert load_settings(root).renderer == "2d"


def test_scene_script_is_standalone_and_py311_to_313_syntax() -> None:
    """It runs inside Blender's own Python, so it must not import studio and must parse on 3.11-3.13."""
    src = provider.SCRIPT.read_text(encoding="utf-8")
    for version in ((3, 11), (3, 12), (3, 13)):
        tree = ast.parse(src, feature_version=version)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= {"bpy", "json", "math", "os", "sys"}


def test_scene_script_knows_every_character_and_background() -> None:
    from studio.kids import spec

    src = provider.SCRIPT.read_text(encoding="utf-8")
    ns = {k: v for k, v in zip(("BODY", "SKY", "GROUND"), [None] * 3, strict=True)}
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ns:
            ns[node.targets[0].id] = ast.literal_eval(node.value)
    assert set(spec.CHARACTERS) <= set(ns["BODY"]) and set(spec.BACKGROUNDS) <= set(ns["SKY"]) == set(ns["GROUND"])


def test_python_in_use_is_supported() -> None:
    """The project targets 3.11+, and the owner's PC has 3.12, so 3.12 must be accepted."""
    assert sys.version_info >= (3, 11)
