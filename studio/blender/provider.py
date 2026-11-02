"""Find Blender, check it, and render a kids scene to a PNG sequence. Optional; callers fall back to 2D."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from studio.errors import StudioError

SCRIPT = Path(__file__).with_name("scene_script.py")
MIN_VERSION = (4, 2)  # Eevee Next (4.2+) is the supported renderer; older versions are rejected with a clear message
WINDOWS_GLOBS = [r"C:\Program Files\Blender Foundation\Blender *\blender.exe"]
RENDER_TIMEOUT = 1800
POLL_SECONDS = 2.0


def find_blender(configured: str = "") -> Path | None:
    """Locate blender: BLENDER_PATH setting, then PATH, then the default Windows install folders."""
    if configured:
        p = Path(configured)
        return p if p.is_file() else None
    found = shutil.which("blender")
    if found:
        return Path(found)
    for pattern in WINDOWS_GLOBS:
        hits = sorted(glob.glob(pattern), reverse=True)
        if hits:
            return Path(hits[0])
    return None


def version(exe: Path) -> tuple[int, int] | None:
    """Return (major, minor) from `blender --version`, or None if it cannot be read."""
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if line.startswith("Blender "):
            parts = line.split()[1].split(".")
            try:
                return int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                return None
    return None


def usable(configured: str = "") -> tuple[Path | None, str]:
    """(path, reason): the Blender to use, or None and a plain-English reason why 2D will be used instead."""
    exe = find_blender(configured)
    if exe is None:
        why = f"BLENDER_PATH={configured!r} is not a file." if configured else "Blender was not found."
        return None, why + " Install Blender 4.2+ or set BLENDER_PATH in .env (README: 3D renderer)."
    v = version(exe)
    if v is None or v < MIN_VERSION:
        got = ".".join(map(str, v)) if v else "unknown"
        return None, f"Blender at {exe} is version {got}; 4.2 or newer is needed."
    return exe, ""


class SceneStopped(StudioError):
    """A 3D scene was stopped before it finished (too slow, or the owner cancelled)."""

    def __init__(self, what: str, why: str, next_step: str, cancelled: bool = False) -> None:
        super().__init__(what, why, next_step)
        self.cancelled = cancelled


class SceneTooSlow(SceneStopped):
    """Stopped early because the speed so far shows the scene would overrun its time limit."""


def _stop(proc: subprocess.Popen) -> None:
    proc.kill()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def render_frames(exe: Path, cfg: dict, out_dir: Path, timeout: float = RENDER_TIMEOUT,
                  on_frame: Callable[[int, int], None] | None = None,
                  should_stop: Callable[[], bool] | None = None) -> list[Path]:
    """Run Blender headless on `cfg` (see scene_script.py) and return the rendered PNG files in order.

    Polls the output folder every 2 s: `on_frame(done, total)` reports progress, `should_stop()` cancels, and a render
    that runs past `timeout` seconds is killed. Both raise SceneStopped.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f_*.png"):
        old.unlink()
    cfg_file = out_dir / "scene3d.json"
    cfg_file.write_text(json.dumps({**cfg, "out_dir": str(out_dir)}), encoding="utf-8")
    total = max(1, round(cfg.get("duration", 0) * cfg.get("fps", 0))) if cfg.get("duration") else 0
    cmd = [str(exe), "-b", "--factory-startup", "-P", str(SCRIPT), "--", str(cfg_file)]
    log_path = out_dir / "blender.log"
    start = time.monotonic()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=os.environ)
        try:
            while True:
                try:
                    proc.wait(timeout=POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if on_frame and total:
                    on_frame(len(list(out_dir.glob("f_*.png"))), total)
                if should_stop and should_stop():
                    _stop(proc)
                    raise SceneStopped("A 3D scene was cancelled.", "You asked to stop 3D rendering.",
                                       "The rest of this video's scenes are drawn in 2D.", cancelled=True)
                if time.monotonic() - start > timeout:
                    _stop(proc)
                    raise SceneStopped("Blender took too long to render a scene.",
                                       f"No result after {int(timeout)} s.",
                                       "Use a lower resolution (draft) or fewer 3D scenes, or set RENDERER=2d.")
        except BaseException:
            if proc.poll() is None:
                _stop(proc)  # Ctrl+C or any error must not leave Blender running in the background
            raise
    frames = sorted(out_dir.glob("f_*.png"))
    if proc.returncode != 0 or not frames:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-800:].strip()
        raise StudioError("Blender failed to render a scene.", tail, "Re-run with RENDERER=2d, or update Blender and "
                          "your graphics driver.")
    return frames
