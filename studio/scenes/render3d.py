"""3D scene clips made with Blender (optional). Callers fall back to the 2D versions when Blender is unusable."""

from __future__ import annotations

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


def scene_config(scene: dict, seconds: float, size: tuple[int, int], footnote: str = "",
                 mouth: list | None = None) -> dict:
    """The JSON handed to Blender (see scene_script.build_scene) with the current channel colours."""
    host = {"action": scene.get("action", "present"), "set": scene.get("set", "studio"),
            "props": scene.get("props", []), "mascot": scene.get("mascot") or {}, "mouth": mouth or []}
    return {**(host if scene["kind"] == "host" else {}),
            "kind": "scene", "scene": scene["kind"], "title": scene.get("title", ""), "items": scene.get("items", []),
            "footnote": footnote, "bg": brand.BG, "fg": brand.FG, "muted": brand.MUTED, "accent": brand.ACCENT,
            "panel": "#1E293B" if brand.BG.lower() == "#0f172a" else brand.BG, "series": list(brand.SERIES),
            "duration": min(max(seconds, 2.0), MAX_SECONDS), "fps": FPS_3D, "width": size[0], "height": size[1]}


def encode_cmd(frames_dir: Path, out: Path) -> list[str]:
    """ffmpeg command: PNG sequence to a silent MP4 at 30 fps (frames are doubled by the rate change)."""
    return ["ffmpeg", "-y", "-framerate", str(FPS_3D), "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
            "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)]


def render(exe: Path, scene: dict, seconds: float, footnote: str, out: Path, work: Path,
           audio: Path | None = None) -> Path:
    """Render one scene to `out` (MP4, no audio) through Blender. A host scene's mouth follows `audio` if given."""
    out.parent.mkdir(parents=True, exist_ok=True)
    mouth = None
    if scene["kind"] == "host":
        from studio.scenes import host

        secs = min(max(seconds, 2.0), MAX_SECONDS)
        mouth = host.envelope(audio, secs, FPS_3D)
    cfg = scene_config(scene, seconds, size_for(ff.profile()), footnote, mouth)
    frames = provider.render_frames(exe, cfg, work)
    ff.run(encode_cmd(frames[0].parent, out), "encoding the 3D scene")
    return out
