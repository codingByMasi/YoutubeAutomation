"""Optional GPU use: NVENC command rewrite, safe fallback to the CPU, Whisper CUDA status and the Fix this rule."""

from __future__ import annotations

import pytest

from studio import health
from studio.providers import whisper
from studio.util import ffmpeg as ff
from studio.util import gpu


@pytest.fixture(autouse=True)
def _fresh():
    gpu.reset()
    yield
    gpu.reset()


def test_nvenc_cmd_translates_x264_flags():
    cmd = ["ffmpeg", "-i", "a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-tune", "film",
           "-x264-params", "threads=2", "-pix_fmt", "yuv420p", "out.mp4"]
    out = gpu.nvenc_cmd(cmd)
    assert out == ["ffmpeg", "-i", "a", "-c:v", "h264_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "20",
                   "-b:v", "0", "-pix_fmt", "yuv420p", "out.mp4"]
    copy = ["ffmpeg", "-i", "a", "-c:v", "copy", "o.mp4"]
    assert gpu.nvenc_cmd(copy) == copy


def test_off_switch_and_no_gpu_keep_cpu(monkeypatch):
    monkeypatch.setattr(gpu, "probe", lambda: (True, "ok"))
    monkeypatch.setenv("STUDIO_GPU", "off")
    assert not gpu.available() and gpu.status()["usable"] and not gpu.status()["on"]
    monkeypatch.setenv("STUDIO_GPU", "auto")
    assert gpu.available()
    monkeypatch.setattr(gpu, "probe", lambda: (False, "no card"))
    assert not gpu.available() and gpu.status()["message"] == "no card"


def test_probe_reports_old_driver(monkeypatch):
    class P:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    calls = [P(0, "V....D h264_nvenc"), P(1, "", "Driver does not support the required nvenc API version")]
    monkeypatch.setattr(gpu.subprocess, "run", lambda *a, **k: calls.pop(0))
    ok, why = gpu.probe()
    assert not ok and "driver" in why.lower()


def test_run_uses_gpu_then_falls_back_on_failure(monkeypatch):
    seen: list[list[str]] = []

    def fake(cmd, **k):
        seen.append(cmd)
        return type("P", (), {"returncode": 1 if "h264_nvenc" in cmd else 0, "stderr": ""})()

    monkeypatch.setenv("STUDIO_GPU", "auto")
    monkeypatch.setattr(gpu, "probe", lambda: (True, "ok"))
    monkeypatch.setattr(ff.subprocess, "run", fake)
    ff.run(["ffmpeg", "-c:v", "libx264", "-crf", "20", "o.mp4"], "testing")
    assert "h264_nvenc" in seen[0] and "libx264" in seen[1]  # tried the GPU, then re-ran on the CPU
    assert not gpu.available()  # and stays on the CPU for the rest of the run
    seen.clear()
    ff.run(["ffmpeg", "-c:v", "libx264", "o.mp4"], "testing")
    assert len(seen) == 1 and "libx264" in seen[0]


def test_run_stays_on_cpu_without_gpu(monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setenv("STUDIO_GPU", "auto")
    monkeypatch.setattr(gpu, "probe", lambda: (False, "none"))
    monkeypatch.setattr(ff.subprocess, "run", lambda cmd, **k: seen.append(cmd) or type(
        "P", (), {"returncode": 0, "stderr": ""})())
    ff.run(["ffmpeg", "-c:v", "libx264", "o.mp4"], "testing")
    assert len(seen) == 1 and "libx264" in seen[0]


def test_whisper_status_explains_missing_cuda_libs(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 1))
    monkeypatch.setattr(whisper, "_load_cuda_libs", lambda: "cublas64_12.dll")
    st = whisper.cuda_status(refresh=True)
    assert st["gpu"] and st["problem"] and not st["on_gpu"] and "CPU" in st["message"]
    monkeypatch.setattr(whisper, "_load_cuda_libs", lambda: None)
    assert whisper.cuda_status(refresh=True)["on_gpu"]
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    st = whisper.cuda_status(refresh=True)
    assert not st["gpu"] and not st["problem"]
    whisper._cuda_cache = None


def test_cuda_error_maps_to_fix_this_rule(tmp_path):
    cause, fix = health.diagnose("captions", "RuntimeError: Library cublas64_12.dll is not found or cannot be loaded")
    assert fix == "gpu_libs" and "graphics card" in cause
    assert health.fix_label(fix)


def test_setup_accepts_only_known_gpu_values(tmp_path):
    from studio.errors import StudioError
    from studio.web import setup_service as setup

    assert setup.save_env(tmp_path, {"STUDIO_GPU": "off"}) == ["STUDIO_GPU"]
    with pytest.raises(StudioError):
        setup.save_env(tmp_path, {"STUDIO_GPU": "maybe"})
