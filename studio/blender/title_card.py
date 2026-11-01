"""3D title card (optional Blender) used as the intro of narrated videos of any channel type."""

from __future__ import annotations

import textwrap
from pathlib import Path

from studio.blender import provider
from studio.util import ffmpeg as ff


def wrap_title(text: str, width: int = 18, lines: int = 3) -> str:
    """Break a title into at most `lines` short lines for the 3D text object."""
    parts = textwrap.wrap(text.strip(), width=width) or [text]
    if len(parts) > lines:
        parts = parts[:lines - 1] + [" ".join(parts[lines - 1:])]
    return "\n".join(parts)


def render_cmd(frames_dir: Path, fps: int, out: Path) -> list[str]:
    """ffmpeg command turning the PNG sequence into a silent-audio MP4 (so it joins the other pieces)."""
    return ["ffmpeg", "-y", "-framerate", str(fps), "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]


def make(exe: Path, title: str, palette: tuple[str, str] | None, out: Path, work: Path, size: tuple[int, int],
         fps: int = 24, seconds: float = 3.0) -> Path:
    """Render the title card with Blender and write it to `out`."""
    bg, accent = palette or ("#0F172A", "#F59E0B")
    cfg = {"kind": "title", "text": wrap_title(title), "bg": bg, "accent": accent, "duration": seconds, "fps": fps,
           "width": size[0], "height": size[1]}
    frames = provider.render_frames(exe, cfg, work)
    ff.run(render_cmd(frames[0].parent, fps, out), "encoding the 3D title card")
    return out
