"""Slow 3D renders: progress, time limits, 2D fallback, resume and cancel. Blender is replaced by tiny scripts."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from studio.blender import provider
from studio.blender.provider import SceneStopped, SceneTooSlow
from studio.scenes import render3d
from studio.scenes import stage as scene_stage
from studio.scenes.budget import SceneBudget
from studio.util import progress

CHART = {"kind": "chart3d", "title": "t", "items": [{"label": "a", "value": 1, "display": "1"}]}


def sleeper(tmp_path: Path, seconds: int = 30) -> Path:
    exe = tmp_path / "blender"
    exe.write_text(f"#!/bin/sh\nsleep {seconds}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(provider, "POLL_SECONDS", 0.1)


def cfg(seconds=2.0, fps=15):
    return {"duration": seconds, "fps": fps}


def test_render_frames_kills_blender_after_timeout(tmp_path):
    with pytest.raises(SceneStopped, match="too long"):
        provider.render_frames(sleeper(tmp_path), cfg(), tmp_path / "f", timeout=0.3)


def test_render_frames_cancel_stops_and_reports(tmp_path):
    with pytest.raises(SceneStopped) as e:
        provider.render_frames(sleeper(tmp_path), cfg(), tmp_path / "f", should_stop=lambda: True)
    assert e.value.cancelled


def test_render_frames_reports_progress(tmp_path):
    seen = []
    exe = tmp_path / "blender"
    exe.write_text("#!/bin/sh\nmkdir -p \"$(dirname \"$6\")\"\nd=$(dirname \"$6\")\ntouch $d/f_0001.png\nsleep 0.5\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    provider.render_frames(exe, cfg(), tmp_path / "f", on_frame=lambda d, t: seen.append((d, t)))
    assert seen and seen[0][1] == 30 and seen[-1][0] >= 1


def test_budget_shortens_then_drops_slow_scenes():
    b = SceneBudget(per_scene=60, total=1000)
    assert b.seconds_to_render(20, 15) == (20, "")  # speed unknown: try it
    b.start(1, 15)
    b.spent, b.frames_done = 300.0, 300  # 1 s per frame
    secs, note = b.seconds_to_render(20, 15)  # 60 s allowed = 60 frames = 4 s: below the minimum
    assert secs is None and "limit" in note
    b.frames_done = 3000  # 0.1 s per frame: 60 s allowed = 600 frames = 40 s
    assert b.seconds_to_render(20, 15)[0] == 20
    b.frames_done = 600  # 0.5 s per frame: 120 frames = 8 s
    secs, note = b.seconds_to_render(20, 15)
    assert secs == 8.0 and "shortened" in note


def test_budget_total_and_cancel():
    b = SceneBudget(per_scene=60, total=100)
    b.spent = 100
    assert b.seconds_to_render(10, 15)[0] is None
    b2 = SceneBudget(per_scene=60, total=100)
    b2.cancelled = True
    assert "cancelled" in b2.seconds_to_render(10, 15)[1]


def test_budget_stops_scene_that_is_clearly_too_slow(tmp_path):
    b = SceneBudget(per_scene=10, total=1000, folder=tmp_path)
    b.start(1, 15)
    b._t0 -= 20  # 20 s elapsed for 10 frames of 300
    with pytest.raises(SceneTooSlow):
        b.on_frame(10, 300)
    assert b.sec_per_frame == pytest.approx(2.0, rel=0.1)


def fake_exe(monkeypatch):
    b = render3d.Blender3D()
    b._done, b._exe = True, Path("blender")
    return b


def test_slow_scene_is_shortened_and_retried(tmp_path, monkeypatch):
    calls = []
    b = None

    def fake(exe, scene, seconds, footnote, out, work, **kw):
        calls.append(seconds)
        if len(calls) == 1:
            b._t0 -= 4  # looks like 0.4 s per frame: 20 s of video needs 120 s, only 10 s fit in 60 s
            kw["on_frame"](10, 300)
        out.write_bytes(b"mp4")
        return out

    monkeypatch.setattr(render3d, "render", fake)
    b = SceneBudget(per_scene=60, total=1000, count=1)
    res = scene_stage.draw({"scene": CHART, "mode": "3d"}, {}, 1, tmp_path, tmp_path / "c", fake_exe(monkeypatch),
                           "", 20.0, b)
    assert res["mode"] == "3d" and len(calls) == 2 and calls[1] < calls[0]


def test_cancel_draws_rest_in_2d(tmp_path, monkeypatch, capsys):
    def fake(exe, scene, seconds, footnote, out, work, **kw):
        raise SceneStopped("A 3D scene was cancelled.", "x", "y", cancelled=True)

    monkeypatch.setattr(render3d, "render", fake)
    b = SceneBudget(count=2)
    pl = {"scene": CHART, "mode": "3d"}
    seg = {"chart_data": {"type": "bar"}}
    r1 = scene_stage.draw(pl, {}, 1, tmp_path, tmp_path / "c", fake_exe(monkeypatch), "", 8.0, b)
    monkeypatch.setattr(render3d, "render", lambda *a, **k: pytest.fail("must not render after cancel"))
    r2 = scene_stage.draw(pl, seg, 2, tmp_path, tmp_path / "c", fake_exe(monkeypatch), "", 8.0, b)
    assert r1["fell_back"] and r2["fell_back"] and b.cancelled
    assert "cancelled" in capsys.readouterr().out + ""


def test_finished_clip_is_reused(tmp_path, monkeypatch):
    runs = []

    def fake_frames(exe, c, out_dir, **kw):
        runs.append(1)
        out_dir.mkdir(parents=True, exist_ok=True)
        f = out_dir / "f_0001.png"
        f.write_bytes(b"x")
        return [f]

    monkeypatch.setattr(provider, "render_frames", fake_frames)
    monkeypatch.setattr(render3d.ff, "run", lambda cmd, what: Path(cmd[-1]).write_bytes(b"mp4"))
    out = tmp_path / "scene_001.mp4"
    render3d.render(Path("b"), CHART, 4.0, "", out, tmp_path / "w")
    render3d.render(Path("b"), CHART, 4.0, "", out, tmp_path / "w")
    assert len(runs) == 1
    render3d.render(Path("b"), CHART, 5.0, "", out, tmp_path / "w")  # different length: redone
    assert len(runs) == 2


def test_progress_file_and_cancel_flag(tmp_path):
    assert not progress.is_active(tmp_path)
    progress.write(tmp_path, stage="visuals", label="3D scene 1 of 2", done=3, total=10)
    assert progress.is_active(tmp_path) and progress.read(tmp_path)["done"] == 3
    assert not progress.is_active(tmp_path, now=progress.read(tmp_path)["updated"] + 600)  # stale
    progress.request_cancel(tmp_path)
    assert progress.cancelled(tmp_path)
    progress.clear_cancel(tmp_path)
    progress.finish(tmp_path)
    assert not progress.cancelled(tmp_path) and not progress.is_active(tmp_path)
    assert progress.fmt_duration(45) == "45 s" and progress.fmt_duration(720) == "12 min"
    assert progress.fmt_duration(7500) == "2 h 05 min"


def test_panel_model_shows_done_now_waiting():
    from studio.web import service as svc
    rec = {"stage": "visuals", "label": "3D scene 4 of 13", "done": 12, "total": 31, "noun": "segments",
           "frame": 150, "frames": 300, "eta_seconds": 7200, "detail": "segment 13 of 31, frame 150 of 300"}
    m = svc.panel_model("voiced", rec)
    assert [i["state"] for i in m["items"]] == ["done", "now", "waiting", "waiting"]
    assert "12 of 31 segments done, 19 to go" in m["counts"] and "2 h 00 min" in m["eta"]
    assert 0.4 < m["step_fraction"] < 0.45 and 0.35 < m["overall"] < 0.40
    idle = svc.panel_model("scripted", None)
    assert not idle["running"] and all(i["state"] == "waiting" for i in idle["items"])


def test_stage_records_progress_and_finishes(tmp_path):
    with progress.tracking(tmp_path, "voice", 4, "segments") as run:
        run.step(2, "Voicing segment 2 of 4")
        rec = progress.read(tmp_path)
        assert (rec["done"], rec["total"]) == (2, 4) and rec["eta_seconds"] is not None
        assert progress.is_active(tmp_path)
    assert not progress.is_active(tmp_path)
