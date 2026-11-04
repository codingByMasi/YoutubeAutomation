"""History (cast) channel through voice, visuals and build with heavy tools stubbed, so a missing key fails in CI."""

from __future__ import annotations

from studio.history import cast as cast_mod
from studio.history import render as cast_render
from studio.history import speech_audio
from studio.stages import build, visuals, voice
from studio.stages import script as sc
from tests.test_dry_run import TimedSilent
from tests.test_story_engine import run_engine


def test_history_cast_flow_runs_every_stage(ctx, monkeypatch):
    monkeypatch.setenv("STUDIO_DRAFT", "1")
    monkeypatch.setenv("STUDIO_NO_CHART_ANIM", "1")
    idea, v, out = run_engine(ctx, "history", "history")
    monkeypatch.setattr(voice, "get_tts", lambda settings: TimedSilent())
    voice.run(ctx, v.id)

    def fake_scene(seg, duration, path, *a, **k):  # stands in for the cartoon renderer
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path
    monkeypatch.setattr(cast_render, "render_scene", fake_scene)
    monkeypatch.setattr(cast_render, "Cast", lambda *a, **k: object())
    monkeypatch.setattr(speech_audio, "synth_lines", lambda *a, **k: False)
    pkg = sc.load_package(ctx, v.id)
    for g in pkg["segments"]:
        g["scene"] = sorted(cast_mod.SCENE_TYPES)[0]
    sc.write_package(ctx, v.id, pkg)
    monkeypatch.setattr(visuals, "check_media", lambda path, kind: [])
    visuals.run(ctx, v.id, stock=None, images=None)
    segs = sc.load_package(ctx, v.id)["segments"]
    assert all("visual" in g for g in segs)  # the key the render report and build read

    seen = {}

    def fake_picture(segments, work, limits=None, **k):
        seen["visuals"] = [g.get("visual") for g in segments]
        return [work / "a.mp4"], [[] for _ in segments]
    monkeypatch.setattr(build, "render_picture", fake_picture)

    class Stop(Exception):
        pass

    def stop_after_picture(cmd, what=""):
        raise Stop
    monkeypatch.setattr(build.ff, "run", stop_after_picture)
    try:
        build.run(ctx, v.id)
    except Stop:
        pass
    assert all(seen["visuals"])
