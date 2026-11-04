import shutil

import pytest

from studio.util import ffmpeg as ff


def test_popen_raw_is_quiet(monkeypatch):
    seen = {}
    monkeypatch.setattr(ff.subprocess, "Popen", lambda cmd, **k: seen.update(cmd=cmd) or object())
    ff.popen_raw(["ffmpeg", "-y", "-i", "-", "out.mp4"])
    assert seen["cmd"][:5] == ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_many_raw_frames_do_not_deadlock(tmp_path):
    """Regression: an unread stderr pipe froze long renders on Windows."""
    w, h, n = 320, 180, 300
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "30", "-i", "-",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp_path / "o.mp4")]
    proc = ff.popen_raw(cmd)
    frame = bytes(w * h * 3)
    for _ in range(n):
        proc.stdin.write(frame)
    proc.stdin.close()
    proc.stderr.read()
    assert proc.wait(timeout=120) == 0 and (tmp_path / "o.mp4").stat().st_size > 0
