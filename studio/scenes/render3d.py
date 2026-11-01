"""3D scene clips made with Blender (optional). Callers fall back to the 2D versions when Blender is unusable."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from studio.blender import provider
from studio.providers import brand
from studio.util import ffmpeg as ff

FPS_3D = 15        # slow camera moves look fine at 15 fps and cost half the render time of 24
MAX_SECONDS = 30   # longer segments loop the clip (build trims or loops it to the narration)
MAX_SIZE = (1280, 720)  # light on a 4 GB GPU; ffmpeg scales the clip up to the video size


class Blender3D:
    """Finds a usable Blender once per run; `.exe` is None (with one printed note) when 3D is not possible."""

    def __init__(self, configured: str = "") -> None:
        self.configured, self._done, self._exe = configured, False, None

    @property
    def exe(self) -> Path | None:
        if not self._done:
            self._exe, why = provider.usable(self.configured)
            self._done = True
            if self._exe is None:
                print(f"Note: 3D scenes fall back to 2D. {why}", file=sys.stderr)
        return self._exe


def size_for(profile) -> tuple[int, int]:
    """Render size: the video size, but never more than 1280x720."""
    return min(profile.w, MAX_SIZE[0]), min(profile.h, MAX_SIZE[1])


def scene_config(scene: dict, seconds: float, size: tuple[int, int], footnote: str = "") -> dict:
    """The JSON handed to Blender (see scene_script.build_scene) with the current channel colours."""
    return {"kind": "scene", "scene": scene["kind"], "title": scene.get("title", ""), "items": scene["items"],
            "footnote": footnote, "bg": brand.BG, "fg": brand.FG, "muted": brand.MUTED, "accent": brand.ACCENT,
            "panel": "#1E293B" if brand.BG.lower() == "#0f172a" else brand.BG, "series": list(brand.SERIES),
            "duration": min(max(seconds, 2.0), MAX_SECONDS), "fps": FPS_3D, "width": size[0], "height": size[1]}


def encode_cmd(frames_dir: Path, out: Path) -> list[str]:
    """ffmpeg command: PNG sequence to a silent MP4 at 30 fps (frames are doubled by the rate change)."""
    return ["ffmpeg", "-y", "-framerate", str(FPS_3D), "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
            "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)]


def _fingerprint(cfg: dict) -> str:
    """Short hash of everything that changes how a scene looks (not where it is saved)."""
    body = json.dumps({k: v for k, v in cfg.items() if k != "out_dir"}, sort_keys=True)
    return hashlib.sha1(body.encode()).hexdigest()[:16]


def render(exe: Path, scene: dict, seconds: float, footnote: str, out: Path, work: Path, timeout: float | None = None,
           on_frame=None, should_stop=None) -> Path:
    """Render one scene to `out` (MP4, no audio) through Blender; a finished identical clip is reused (resume)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = scene_config(scene, seconds, size_for(ff.profile()), footnote)
    mark = out.with_suffix(".fp")
    fp = _fingerprint(cfg)
    if out.exists() and out.stat().st_size > 0 and mark.exists() and mark.read_text(encoding="utf-8") == fp:
        return out
    mark.unlink(missing_ok=True)
    kwargs = {k: v for k, v in (("timeout", timeout), ("on_frame", on_frame), ("should_stop", should_stop)) if v}
    frames = provider.render_frames(exe, cfg, work, **kwargs)
    ff.run(encode_cmd(frames[0].parent, out), "encoding the 3D scene")
    mark.write_text(fp, encoding="utf-8")
    return out
