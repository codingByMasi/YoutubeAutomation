"""Kids scenes rendered with Blender (optional, PC only): 3D frames plus the same lyric captions as the 2D path."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from studio.blender import provider
from studio.errors import StudioError
from studio.kids import draw
from studio.util import ffmpeg as ff

FPS_3D = 24


def choose(renderer: str, blender_path: str = "") -> Path | None:
    """Return the Blender executable to use, or None for the 2D renderer (with a visible notice on fallback)."""
    if renderer != "blender":
        return None
    exe, why = provider.usable(blender_path)
    if exe is None:
        print(f"Note: using the 2D renderer. {why}", file=sys.stderr)
    return exe


def scene_config(scene: dict, dur: float, size: tuple[int, int], fps: int, cam: str) -> dict:
    """The JSON handed to Blender for one scene (characters, motion, camera, size)."""
    v = scene["visual"]
    return {"background": v["background"], "characters": v["characters"],
            "count": v.get("count", len(v["characters"])), "motion": v["motion"], "camera": cam,
            "duration": dur, "fps": fps, "width": size[0], "height": size[1]}


def render_scene(exe: Path, scene: dict, audio: Path, narration: float, out: Path, size: tuple[int, int], fps: int,
                 font_file: str, counting: bool, cam: str, work: Path) -> None:
    """Render one scene with Blender, add captions (and the counting number), and mux with the narration."""
    from studio.kids.build import _scene_cmd, line_index, scene_seconds

    dur = scene_seconds(narration)
    frames = provider.render_frames(exe, scene_config(scene, dur, size, fps, cam), work)
    proc = subprocess.Popen(ff.low_memory_cmd(_scene_cmd(audio, dur, size[0], size[1], fps, out)),
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = scene["visual"].get("count", len(scene["visual"]["characters"]))
    try:
        for f in range(round(dur * fps)):
            t = f / fps
            with Image.open(frames[min(f, len(frames) - 1)]) as im:
                img = im.convert("RGB")
            if counting:
                d = draw.ImageDraw.Draw(img)
                d.text((size[0] * 0.9, size[1] * 0.12), str(min(n, int(t / 0.45) + 1)),
                       font=draw._font(font_file, int(size[1] * 0.2)), anchor="mm", fill=(255, 235, 60),
                       stroke_width=6, stroke_fill=draw.INK)
            draw.draw_lyrics(img, scene["lines"], line_index(scene, t, narration), font_file)
            proc.stdin.write(img.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise StudioError("ffmpeg failed while joining 3D frames.", err.strip()[-800:],
                              "Check ffmpeg is installed and re-run with --force.")
    except BrokenPipeError as exc:
        raise StudioError("ffmpeg closed early while joining 3D frames.", "", "Re-run with --force.") from exc
    finally:
        if proc.poll() is None:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)
