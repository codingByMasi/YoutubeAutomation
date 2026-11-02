"""Whole flow per channel type with the fake LLM and a fake timed voice: story engine -> voice -> visuals -> build -> gate."""  # noqa: E501

from __future__ import annotations

import os
import subprocess

import pytest

from studio.stages import build, visuals, voice
from studio.stages import script as sc
from studio.story import narration
from studio.util.ffmpeg import ensure_ffmpeg
from tests.test_story_engine import run_engine


class TimedSilent:
    """Silent engine that also reports word times (as edge-tts WordBoundary would), so chapter mode is exercised."""

    name = "timed-silent"
    voice = "fake"

    def synth(self, text, out, **_):
        self.synth_timed(text, out)
        return out

    def synth_timed(self, text, out, prosody=None):
        ensure_ffmpeg()
        words = text.split()
        t, timed = 0.0, []
        for w in words:
            timed.append((round(t, 3), round(t + 0.38, 3), w))
            t += 0.4
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", f"{t:.2f}", "-c:a", "libmp3lame", "-q:a", "4", str(out)], check=True)
        return timed


slow = pytest.mark.skipif(os.getenv("STUDIO_SLOW_TESTS") != "1",
                          reason="renders 8-15 minute videos (about 2 min each); set STUDIO_SLOW_TESTS=1 to run")


@slow
@pytest.mark.parametrize("ctype,pack", [("business", "explainer"), ("history", "history"), ("kids", "kids")])
def test_dry_run_builds_final_mp4_and_gate_returns_verdict(ctx, monkeypatch, ctype, pack):
    monkeypatch.setenv("STUDIO_DRAFT", "1")
    monkeypatch.setenv("STUDIO_NO_CHART_ANIM", "1")
    idea, v, out = run_engine(ctx, ctype, pack)
    monkeypatch.setattr(voice, "get_tts", lambda settings: TimedSilent())
    voice.run(ctx, v.id)
    pkg = sc.load_package(ctx, v.id)
    assert all(s.get("words") for s in pkg["segments"])  # word times stored per segment
    assert (out / "voice" / "groups.json").exists()
    visuals.run(ctx, v.id, stock=None, images=None)
    build.run(ctx, v.id)
    assert (out / "final.mp4").stat().st_size > 10_000
    assert (out / "caption_sync.json").exists()
    from studio.quality import gate
    rep = gate.check_video(ctx, v.id, thumb=1)
    assert rep["verdict"] in ("pass", "warn", "block") and rep["score"] >= 0
    assert narration.groups(pkg["segments"], __import__("studio.story.profile", fromlist=["x"]).get(pack))
    # the voice step is resumable: a second run reuses the finished chapter groups
    before = {p.name: p.stat().st_mtime_ns for p in (out / "voice").glob("seg_*.mp3")}
    voice.run(ctx, v.id, force=False)
    assert before == {p.name: p.stat().st_mtime_ns for p in (out / "voice").glob("seg_*.mp3")}
