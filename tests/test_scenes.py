"""Narrated 3D/2D scenes: choosing the style per channel, video and segment, 2D equivalents and the 3D fallback."""

import ast
import json
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from studio import production, scenes
from studio.blender import provider
from studio.cli import app
from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channel_types, channels
from studio.scenes import render2d, render3d
from studio.scenes import stage as scene_stage
from studio.stages import build as build_stage
from studio.stages import script as sc
from studio.stages import visuals, voice
from tests.test_voice_visuals import FakeTTS, scripted_video

TIMELINE = {"kind": "timeline", "title": "Rome", "source_ids": ["s1"],
            "items": [{"label": "753 BC", "text": "Founded"}, {"label": "27 BC", "text": "Empire begins"}]}
MAP = {"kind": "map", "title": "Route",
       "items": [{"label": "Rome", "x": .5, "y": .6}, {"label": "Carthage", "x": .4, "y": .8}]}
ARTIFACT = {"kind": "artifact", "title": "Coin", "items": [{"label": "Denarius", "shape": "coin"}]}
BAR = {"type": "bar", "title": "Share", "labels": ["A", "B"], "values": [65, 35], "unit": "%", "source_ids": ["s1"]}


# ---- which segments get which style ---------------------------------------------------------------------------

@pytest.mark.parametrize("style,override,expected", [
    ("2d", "", "2d"), ("", "", "2d"), ("mixed", "", "3d"), ("3d", "", "3d"),
    ("2d", "3d", "3d"), ("3d", "2d", "2d"), ("mixed", "2d", "2d"),
])
def test_explicit_scene_style_rules(style, override, expected):
    pl = scenes.plan({"scene": TIMELINE}, style, override)
    assert pl["mode"] == expected and pl["scene"]["kind"] == "timeline"


def test_scene_own_style_is_beaten_only_by_the_segment_override():
    seg = {"scene": {**MAP, "style": "2d"}}
    assert scenes.plan(seg, "3d")["mode"] == "2d"
    assert scenes.plan(seg, "3d", "3d")["mode"] == "3d"


@pytest.mark.parametrize("style,override,drawn", [
    ("3d", "", True), ("mixed", "", True), ("2d", "", False), ("mixed", "3d", True), ("3d", "2d", False)])
def test_bar_and_line_charts_become_3d_only_when_asked(style, override, drawn):
    seg = {"chart_data": BAR}
    pl = scenes.plan(seg, style, override)
    assert (pl is not None) is drawn
    if pl:
        assert pl["scene"]["kind"] == "chart3d" and [i["label"] for i in pl["scene"]["items"]] == ["A", "B"]
        assert pl["scene"]["items"][0]["display"] == "65%"


def test_other_charts_and_plain_segments_are_untouched():
    assert scenes.plan({}, "3d") is None
    assert scenes.plan({"chart_data": {"type": "flow", "labels": ["a", "b"], "values": [1, 2]}}, "3d", "3d") is None


def test_chart3d_scene_in_2d_needs_nothing_extra():
    assert scenes.plan({"scene": {"kind": "chart3d"}, "chart_data": BAR}, "2d") is None
    assert scenes.plan({"scene": {"kind": "chart3d"}, "chart_data": BAR}, "mixed")["mode"] == "3d"


# ---- validation -----------------------------------------------------------------------------------------------

def test_scene_validation():
    ok = scenes.validate_scene
    assert ok(TIMELINE, "s", None, {"s1"}) == [] and ok(MAP, "s") == [] and ok(ARTIFACT, "s") == []
    assert ok(None, "s") == []
    assert "scene kind 'orbit'" in ok({"kind": "orbit"}, "s")[0]
    assert any("source_ids" in p for p in ok({**TIMELINE, "source_ids": []}, "s"))
    assert any("unknown source id" in p for p in ok(TIMELINE, "s", None, {"zz"}))
    assert any("between 0 and 1" in p for p in ok({**MAP, "items": [{"label": "a", "x": 2, "y": 0.1}] * 2}, "s"))
    assert any("exactly 1" in p for p in ok({**ARTIFACT, "items": ARTIFACT["items"] * 2}, "s"))
    assert any("shape" in p for p in ok({**ARTIFACT, "items": [{"label": "x", "shape": "ufo"}]}, "s"))
    assert any("needs items" in p for p in ok({"kind": "map"}, "s"))
    assert any("bar/line" in p for p in ok({"kind": "chart3d"}, "s", {"chart_data": {"type": "pie"}}))
    assert ok({"kind": "chart3d"}, "s", {"chart_data": BAR}) == []
    assert any("style" in p for p in ok({**MAP, "style": "4d"}, "s"))


def test_script_package_validation_includes_scenes():
    pkg = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())
    assert sc.validate_package(pkg) == []
    pkg["segments"][1]["scene"] = {"kind": "timeline", "items": [{"label": "1", "text": "x"}] * 2}
    problems = sc.validate_package(pkg)
    assert any("segment 2" in p and "timeline" in p for p in problems)
    pkg["segments"][1]["scene"] = TIMELINE
    assert sc.validate_package(pkg) == []


# ---- settings: channel type default < channel < video < segment -----------------------------------------------

def test_type_defaults_and_precedence(root):
    s = Settings(root=root)
    got = {t: production.resolve(s, channel_id=channels.add(root, f"c-{t}", type=t))["scene_style"]
           for t in channel_types.TYPES}
    assert got == {"business": "mixed", "history": "mixed", "kids": "2d", "general": "2d"}
    cid = channels.add(root, "Hist", type="history", scene_style="3d")
    r = production.resolve(s, channel_id=cid)
    assert (r["scene_style"], r["sources"]["scene_style"]) == ("3d", "channel")
    production.set_video(s, 7, scene_style="2d")
    r = production.resolve(s, 7, cid)
    assert (r["scene_style"], r["sources"]["scene_style"]) == ("2d", "video")
    with pytest.raises(StudioError, match="not a valid scene_style"):
        production.set_video(s, 7, scene_style="holo")
    with pytest.raises(StudioError, match="not a valid scene_style"):
        channels.add(root, "Bad", scene_style="holo")


def test_explicit_2d_renderer_beats_the_type_default_but_not_an_explicit_style(root):
    s = Settings(root=root)
    cid = channels.add(root, "Hist", type="history", renderer="2d")
    r = production.resolve(s, channel_id=cid)
    assert (r["scene_style"], r["sources"]["scene_style"]) == ("2d", "renderer")
    cid2 = channels.add(root, "Hist2", type="history", renderer="2d", scene_style="3d")
    assert production.resolve(s, channel_id=cid2)["scene_style"] == "3d"
    assert not production.wants_blender(production.resolve(s, channel_id=cid))


def test_segment_styles_roundtrip_and_survive_other_edits(root):
    s = Settings(root=root)
    assert production.set_segment_style(s, 4, 3, "3d") == {3: "3d"}
    production.set_video(s, 4, voice="en-GB-RyanNeural")
    assert production.segment_styles(s, 4) == {3: "3d"}
    assert production.resolve(s, 4)["segment_styles"] == {3: "3d"}
    assert "3: 3d" in production.describe(s, 4) and production.wants_blender(production.resolve(s, 4))
    assert production.set_segment_style(s, 4, 3, "") == {}
    with pytest.raises(StudioError, match="not a valid segment style"):
        production.set_segment_style(s, 4, 1, "5d")
    production.clear_video(s, 4)
    assert production.segment_styles(s, 4) == {}


def test_title_intro_follows_scene_style(root):
    s = Settings(root=root)
    cid = channels.add(root, "Gen", type="general")
    assert not production.wants_blender(production.resolve(s, channel_id=cid))
    channels.update(root, cid, scene_style="mixed")
    assert production.wants_blender(production.resolve(s, channel_id=cid))
    channels.update(root, cid, scene_style="", renderer="blender")
    assert production.wants_blender(production.resolve(s, channel_id=cid))


# ---- 2D equivalents -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("scene,frames", [(TIMELINE, 2), (MAP, 2), (ARTIFACT, 1)])
def test_2d_versions_draw_frames_that_reveal_step_by_step(tmp_path, scene, frames):
    out = render2d.render(scene, "Source: test", tmp_path, "scene_001")
    assert len(out) == frames
    with Image.open(out[0]) as im:
        assert im.size == (1920, 1080)


def test_chart3d_has_no_separate_2d_frames(tmp_path):
    assert render2d.render({"kind": "chart3d", "items": []}, "", tmp_path, "x") == []


@pytest.mark.parametrize("shape", scenes.SHAPES)
def test_every_artifact_shape_draws(tmp_path, shape):
    sc_ = {**ARTIFACT, "items": [{"label": "x", "shape": shape}]}
    assert render2d.render(sc_, "", tmp_path, "a")[0].exists()


# ---- 3D with and without Blender --------------------------------------------------------------------------------

def _fake_render(calls):
    def fake(exe, scene, seconds, footnote, out, work):
        calls.append((scene["kind"], round(seconds, 1), footnote))
        out.write_bytes(b"mp4")
        return out
    return fake


def test_3d_scene_renders_a_clip(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(render3d, "render", _fake_render(calls))
    b = render3d.Blender3D()
    b._done, b._exe = True, Path("blender")
    res = scene_stage.draw({"scene": TIMELINE, "mode": "3d"}, {}, 3, tmp_path, tmp_path / "c", b, "Source: x", 12.0)
    assert res["mode"] == "3d" and res["clip"].name == "scene_003.mp4" and not res["frames"]
    assert calls == [("timeline", 12.0, "Source: x")]


def test_scene_with_a_chart_renders_only_the_lead_in_3d(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(render3d, "render", _fake_render(calls))
    b = render3d.Blender3D()
    b._done, b._exe = True, Path("blender")
    scene_stage.draw({"scene": MAP, "mode": "3d"}, {"chart_data": BAR}, 1, tmp_path, tmp_path / "c", b, "", 20.0)
    assert calls[0][1] == 5.0  # the chart takes over after the lead-in


def test_missing_blender_falls_back_to_2d_with_one_note(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(provider, "find_blender", lambda configured="": None)
    b = render3d.Blender3D()
    pl = {"scene": TIMELINE, "mode": "3d"}
    res = [scene_stage.draw(pl, {}, p, tmp_path, tmp_path / "c", b, "", 8.0) for p in (1, 2)]
    assert all(r["mode"] == "2d" and r["fell_back"] and r["frames"] and not r["clip"] for r in res)
    assert capsys.readouterr().err.count("fall back to 2D") == 1


def test_failed_blender_render_falls_back_to_2d(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise StudioError("Blender failed to render a scene.", "crash", "use 2D")
    monkeypatch.setattr(render3d, "render", boom)
    b = render3d.Blender3D()
    b._done, b._exe = True, Path("blender")
    res = scene_stage.draw({"scene": MAP, "mode": "3d"}, {}, 2, tmp_path, tmp_path / "c", b, "", 8.0)
    assert res["mode"] == "2d" and res["fell_back"] and len(res["frames"]) == 2
    assert "using 2D" in capsys.readouterr().out


def test_scene_config_carries_channel_colours():
    from studio.providers import brand
    with brand.use(("#112233", "#445566")):
        cfg = render3d.scene_config({**TIMELINE}, 99.0, (1280, 720), "n")
    assert (cfg["bg"], cfg["accent"], cfg["kind"], cfg["scene"]) == ("#112233", "#445566", "scene", "timeline")
    assert cfg["duration"] == render3d.MAX_SECONDS and cfg["fps"] == render3d.FPS_3D


# ---- visuals and build integration ---------------------------------------------------------------------------------

def _scripted_with_scenes(ctx):
    v = scripted_video(ctx)
    pkg = sc.load_package(ctx, v.id)
    pkg["segments"][1]["scene"] = TIMELINE
    pkg["segments"][2]["scene"] = MAP
    pkg["segments"][4]["scene"] = ARTIFACT
    sc.write_package(ctx, v.id, pkg)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 8.0)
    return v


def test_visuals_mixes_3d_and_2d_scenes_per_segment(ctx, tmp_path, monkeypatch):
    v = _scripted_with_scenes(ctx)
    calls = []
    monkeypatch.setattr(render3d, "render", _fake_render(calls))
    monkeypatch.setattr(render3d.Blender3D, "exe", property(lambda self: Path("blender")))
    production.set_video(ctx.settings, v.id, scene_style="mixed")
    production.set_segment_style(ctx.settings, v.id, 3, "2d")  # the map stays 2D
    visuals.run(ctx, v.id, stock=None, images=None)
    pkg = sc.load_package(ctx, v.id)
    vis = {i: s["visual"] for i, s in enumerate(pkg["segments"], 1)}
    assert vis[2]["scene"]["mode"] == "3d" and Path(vis[2]["scene_clip"]).exists()
    assert vis[3]["scene"]["mode"] == "2d" and "scene_clip" not in vis[3]
    assert [Path(f).name[:12] for f in vis[3]["chart_frames"][:2]] == ["scene_003_01", "scene_003_02"]
    assert len(vis[3]["chart_frames"]) > 2  # the segment's own chart still follows the map
    assert vis[5]["scene"]["mode"] == "3d"
    assert [c[0] for c in calls] == ["timeline", "artifact"]
    assert "scene_clip" not in vis[1]
    from studio.models import Asset
    kinds = [a.kind for a in ctx.session.query(Asset).filter_by(video_id=v.id)]
    assert kinds.count("scene") == 3


def test_visuals_all_2d_never_touches_blender(ctx, monkeypatch):
    v = _scripted_with_scenes(ctx)
    monkeypatch.setattr(render3d, "render", lambda *a, **k: pytest.fail("Blender must not run for 2D"))
    production.set_video(ctx.settings, v.id, scene_style="2d")
    visuals.run(ctx, v.id, stock=None, images=None)
    pkg = sc.load_package(ctx, v.id)
    assert all(s["visual"].get("scene", {}).get("mode", "2d") == "2d" for s in pkg["segments"])


def test_3d_chart_replaces_the_2d_chart_and_keeps_its_source(ctx, monkeypatch):
    v = scripted_video(ctx)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 8.0)
    calls = []
    monkeypatch.setattr(render3d, "render", _fake_render(calls))
    monkeypatch.setattr(render3d.Blender3D, "exe", property(lambda self: Path("blender")))
    production.set_video(ctx.settings, v.id, scene_style="3d")
    visuals.run(ctx, v.id, stock=None, images=None)
    pkg = sc.load_package(ctx, v.id)
    bar = pkg["segments"][2]["visual"]  # the sample's only bar chart
    assert bar["scene_clip"] and "chart_frames" not in bar
    assert calls[0][0] == "chart3d" and "Source:" not in calls[0][2]  # sources live in the description
    assert pkg["segments"][0]["visual"].get("chart_frames")  # the number card stays 2D


def test_build_uses_a_3d_clip_as_one_continuous_shot(tmp_path, monkeypatch):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"x")
    card = tmp_path / "card.png"
    Image.new("RGB", (64, 36)).save(card)
    seg = {"est_seconds": 16, "real_seconds": 16, "visual": {"paths": [str(card)], "scene_clip": str(clip)}}
    cmds = []
    monkeypatch.setattr(build_stage.ff, "run", lambda cmd, what="": cmds.append(cmd))
    monkeypatch.setattr(build_stage.ff, "concat_list", lambda files, p: p)
    monkeypatch.setattr(build_stage.ff, "concat_cmd", lambda *a, **k: ["concat"])
    work = tmp_path / "w"
    work.mkdir()
    _, plans = build_stage.render_picture([seg], work)
    assert plans[0] == [(clip, 16.0)]


# ---- the Blender script itself ------------------------------------------------------------------------------------

def test_scene_script_knows_every_scene_kind():
    tree = ast.parse(provider.SCRIPT.read_text(encoding="utf-8"))
    table = next(n.value for n in tree.body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SCENES")
    assert {k.value for k in table.keys} == set(scenes.KINDS)


@pytest.mark.parametrize("kind,items", [
    ("chart3d", [{"label": "A", "value": 65, "display": "65%"}, {"label": "B", "value": 35, "display": "35%"}]),
    ("timeline", TIMELINE["items"]), ("map", MAP["items"]), ("artifact", ARTIFACT["items"])])
def test_real_blender_renders_every_scene_kind(tmp_path, monkeypatch, kind, items):
    """Runs the scene script for real through the `bpy` module (Cycles CPU, tiny frames); skipped without bpy."""
    pytest.importorskip("bpy")
    import importlib.util
    monkeypatch.setenv("STUDIO_BLENDER_ENGINE", "CYCLES")
    spec = importlib.util.spec_from_file_location("scene_script_real", provider.SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = render3d.scene_config({"kind": kind, "title": "T", "items": items}, 2.0, (96, 54), "Source: x")
    cfg.update(fps=2, out_dir=str(tmp_path))
    os.makedirs(tmp_path, exist_ok=True)
    mod.main(cfg)
    frames = sorted(tmp_path.glob("f_*.png"))
    assert len(frames) == 4
    with Image.open(frames[-1]) as im:
        assert im.size == (96, 54) and len(set(im.convert("RGB").getdata())) > 3


# ---- command line ----------------------------------------------------------------------------------------------------

def test_cli_scene_style_for_channel_video_and_segment(root, monkeypatch):
    monkeypatch.setenv("STUDIO_HOME", str(root))
    r = CliRunner()
    assert r.invoke(app, ["channels", "add", "Past", "--type", "history", "--scene-style", "3d"]).exit_code == 0
    assert channels.get(root, "past")["scene_style"] == "3d"
    res = r.invoke(app, ["production", "set", "5", "--scene-style", "2d"])
    assert res.exit_code == 0 and "scene_style" in res.output and "2d" in res.output
    res = r.invoke(app, ["production", "scene", "5", "3", "3d"])
    assert res.exit_code == 0 and "3: 3d" in res.output and "visuals 5 --force" in res.output
    res = r.invoke(app, ["production", "scene", "5", "3", "9d"])
    assert res.exit_code != 0 and "not a valid segment style" in str(res.exception)
    assert r.invoke(app, ["production", "show"]).exit_code == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_encode_command_makes_silent_30fps_video(tmp_path):
    cmd = render3d.encode_cmd(tmp_path, tmp_path / "o.mp4")
    assert "-an" in cmd and cmd[cmd.index("-r") + 1] == "30" and cmd[-1].endswith("o.mp4")


def test_mixed_style_turns_pie_charts_into_3d_too():
    """A script with no scenes still gets 3D: bar, line and pie charts all become 3D charts in mixed/3d style."""
    from studio import scenes
    seg = {"chart_data": {"type": "pie", "title": "Share", "labels": ["A", "B"], "values": [60, 40], "unit": "%"}}
    pl = scenes.plan(seg, "mixed")
    assert pl and pl["mode"] == "3d" and [i["label"] for i in pl["scene"]["items"]] == ["A", "B"]
    assert scenes.plan(seg, "2d") is None
