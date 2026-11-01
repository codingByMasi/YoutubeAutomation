"""Web helpers and a Streamlit smoke test (no network, no real keys)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from studio.errors import StudioError
from studio.models import Idea, Video
from studio.stages import research
from studio.web import service as svc

SAMPLE = Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json"


def _approved(ctx) -> tuple[Idea, Video]:
    idea = svc.add_manual_topic(ctx, "how airlines make money")
    return idea, research.approve(ctx, idea.id)


def test_apply_secrets_only_known_keys(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    applied = svc.apply_secrets({"PEXELS_API_KEY": "abc123", "EVIL": "x", "PIXABAY_API_KEY": ""})
    assert applied == ["PEXELS_API_KEY"] and os.environ["PEXELS_API_KEY"] == "abc123"
    assert "EVIL" not in os.environ
    monkeypatch.delenv("PEXELS_API_KEY")


def test_manual_topic_rejects_empty(make_ctx):
    with pytest.raises(StudioError):
        svc.add_manual_topic(make_ctx(), "  ")


def test_script_handoff_and_paste_flow(make_ctx):
    ctx = make_ctx()
    idea, video = _approved(ctx)
    from studio.stages import script

    res = svc.capture(script.run, ctx, idea.id)
    assert res.pending and not res.ok
    prompt = svc.read_prompt(ctx, video.id)
    assert prompt and "How to answer" not in prompt and "ONLY the JSON" in prompt

    bad = svc.submit_script(ctx, idea.id, video.id, "not json")
    assert not bad.ok and "valid JSON" in bad.error
    good = svc.submit_script(ctx, idea.id, video.id, SAMPLE.read_text(encoding="utf-8"))
    assert good.ok, good.error
    assert ctx.session.get(Video, video.id).stage == "scripted"
    assert svc.next_produce_stage(ctx.session.get(Video, video.id)) == "voice"


def test_review_gate_needs_typed_yes(make_ctx):
    ctx = make_ctx()
    assert ctx.confirm("anything") != "yes"
    wired = svc.make_ctx(ctx.settings.root, lambda _p: "no")
    assert wired.confirm("p") == "no"
    assert svc.make_ctx(ctx.settings.root).confirm("p") == ""


def test_zip_and_files(make_ctx):
    ctx = make_ctx()
    _, video = _approved(ctx)
    d = ctx.settings.project_dir(video.id)
    (d / "final.mp4").write_bytes(b"x")
    (d / "prompts").mkdir(exist_ok=True)
    (d / "prompts" / "script.prompt.md").write_text("secret-ish")
    import io
    import zipfile

    names = zipfile.ZipFile(io.BytesIO(svc.zip_outputs(ctx, video.id))).namelist()
    assert names == ["final.mp4"]


def test_app_renders_every_page(root, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("STUDIO_HOME", str(root))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.exception
    for page in ["1. Topics", "2. Script", "3. Make the video", "4. Review and download", "📊 Analytics",
                 "Channels", "Settings"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_outcome_from_process_maps_exit_codes():
    assert svc.outcome_from_process(0, "ok").ok
    assert svc.outcome_from_process(3, "wait").pending
    oom = svc.outcome_from_process(-9, "")
    assert not oom.ok and "ran out of memory" in oom.error and "Next:" in oom.error
    assert "exit code 1" in svc.outcome_from_process(1, "boom").error


def test_run_cli_runs_child_process(root):
    res = svc.run_cli(root, ["quota"])
    assert res.ok, res.error
    assert "units" in res.log


def test_ffmpeg_low_memory_and_oom(monkeypatch):
    from studio.util import ffmpeg as ff

    cmd = ["ffmpeg", "-i", "a", "-c:v", "libx264", "out.mp4"]
    out = ff.low_memory_cmd(cmd)
    assert out[-1] == "out.mp4" and "-x264-params" in out
    monkeypatch.setenv("STUDIO_FFMPEG_THREADS", "0")
    assert ff.low_memory_cmd(cmd) == cmd
    monkeypatch.setattr(ff.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": -9, "stderr": ""})())
    with pytest.raises(StudioError, match="out of memory"):
        ff.run(cmd, "testing")


def test_draft_profile_and_copy_mix(monkeypatch, tmp_path):
    from studio.util import ffmpeg as ff

    monkeypatch.delenv("STUDIO_DRAFT", raising=False)
    assert ff.profile().w == 1920 and ff.profile().zoom
    mix = ff.mix_cmd(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4", None)
    assert mix[mix.index("-c:v") + 1] == "copy"  # picture is not encoded a second time
    burn = ff.mix_cmd(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4", None, subtitles=tmp_path / "s.srt")
    assert burn[burn.index("-c:v") + 1] == "libx264"
    monkeypatch.setenv("STUDIO_DRAFT", "1")
    p = ff.profile()
    assert (p.w, p.h, p.preset, p.zoom) == (1280, 720, "ultrafast", False)
    assert "zoompan" not in " ".join(ff.image_cmd(tmp_path / "i.jpg", 5, tmp_path / "o.mp4"))
    assert "scale=1280:720" in " ".join(ff.clip_cmd(tmp_path / "c.mp4", 5, tmp_path / "o.mp4"))


def test_failing_image_source_is_dropped_after_two_failures():
    from studio.providers.images import ImageSearch

    calls = []

    class Down:
        def find(self, kws, exclude):
            calls.append(1)
            raise StudioError("down")

    s = ImageSearch([Down()])
    for _ in range(5):
        assert s.find(["a"], set()) is None
    assert len(calls) == 2


def test_browser_issues_and_preview_cmd(tmp_path):
    from studio.util import ffmpeg as ff

    good = {"video": {"codec_name": "h264", "pix_fmt": "yuv420p"}, "audio": {"codec_name": "aac"}}
    assert ff.browser_issues(good) == []
    bad = {"video": {"codec_name": "hevc", "pix_fmt": "yuv444p"}, "audio": {"codec_name": "mp3"}}
    assert len(ff.browser_issues(bad)) == 3 and ff.browser_issues({})
    cmd = ff.preview_cmd(tmp_path / "f.mp4", tmp_path / "p.mp4")
    assert "+faststart" in cmd and "yuv420p" in cmd and "scale=-2:480" in cmd[cmd.index("-vf") + 1]


def test_ensure_preview_builds_once_and_rebuilds_when_stale(make_ctx, monkeypatch):
    from studio.util import ffmpeg as ff

    ctx = make_ctx()
    _, video = _approved(ctx)
    d = ctx.settings.project_dir(video.id)
    assert svc.ensure_preview(ctx, video.id) is None  # nothing built yet
    (d / "final.mp4").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(ff, "ensure_ffmpeg", lambda: None)
    def fake_run(cmd, what):
        calls.append(1)
        Path(cmd[-1]).write_bytes(b"p")

    monkeypatch.setattr(ff, "run", fake_run)
    p = svc.ensure_preview(ctx, video.id)
    assert p.name == "preview.mp4" and p.exists() and len(calls) == 1
    svc.ensure_preview(ctx, video.id)
    assert len(calls) == 1  # cached
    os.utime(d / "final.mp4", (p.stat().st_mtime + 10,) * 2)
    svc.ensure_preview(ctx, video.id)
    assert len(calls) == 2  # final changed, preview rebuilt
