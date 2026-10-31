"""Kids build stage: narrate each scene, draw animated frames, and assemble one MP4 (and a thumbnail)."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from pathlib import Path

from PIL import ImageDraw, ImageFont

from studio.context import Ctx
from studio.errors import StageError, StudioError
from studio.kids import build3d, draw, music, spec
from studio.kids.script import project_dir
from studio.kids.sprites import SpriteBank
from studio.providers.brand import font_path
from studio.providers.tts import get_tts
from studio.util import ffmpeg as ff

KIDS_VOICE = "en-US-AnaNeural"  # edge-tts child-friendly voice; override with KIDS_TTS_VOICE
MIN_SCENE_SECONDS = 3.0
TAIL = 0.6


def scene_seconds(narration: float) -> float:
    """Scene length: the narration plus a short tail, never shorter than the minimum."""
    return max(MIN_SCENE_SECONDS, narration + TAIL)


def line_index(scene: dict, t: float, narration: float) -> int:
    """Which lyric line is being sung at time t, weighted by word count."""
    total = sum(spec.words(ln) for ln in scene["lines"]) or 1
    acc = 0.0
    for i, ln in enumerate(scene["lines"]):
        acc += spec.words(ln) / total * narration
        if t < acc:
            return i
    return len(scene["lines"]) - 1


def _scene_cmd(audio: Path, dur: float, w: int, h: int, fps: int, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
            "-i", str(audio), "-af", "apad", "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]


def render_scene(scene: dict, audio: Path, narration: float, out: Path, size: tuple[int, int], fps: int,
                 font_file: str, counting: bool, sprites: SpriteBank | None = None, cam: str = "") -> None:
    """Draw every frame of one scene and pipe it into ffmpeg together with the narration."""
    w, h = size
    dur = scene_seconds(narration)
    bg = draw.background(scene["visual"]["background"], w, h)
    proc = subprocess.Popen(ff.low_memory_cmd(_scene_cmd(audio, dur, w, h, fps, out)), stdin=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        for f in range(round(dur * fps)):
            t = f / fps
            frame = draw.render_frame(scene, t, bg, line_index(scene, t, narration), font_file, counting,
                                      sprites, narration, t / dur, cam)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise StudioError("ffmpeg failed while drawing a kids scene.", err.strip()[-800:],
                              "Check ffmpeg is installed and re-run with --force.")
    except BrokenPipeError as exc:
        raise StudioError("ffmpeg closed early while drawing a kids scene.", proc.stderr.read().decode()[-800:],
                          "Check ffmpeg is installed and re-run with --force.") from exc
    finally:
        if proc.poll() is None:
            proc.kill()


def _music(ctx: Ctx) -> Path | None:
    files = sorted(p for p in (ctx.settings.assets_dir / "music").glob("*") if p.suffix.lower() in (".mp3",
        ".wav", ".m4a"))
    return files[0] if files else None


def run(ctx: Ctx, slug: str, force: bool = False, size: tuple[int, int] = (1280, 720), fps: int = 15,
        renderer: str | None = None) -> Path:
    """Build projects/kids_<slug>/final.mp4 from script.json. Idempotent: skips if final.mp4 exists.

    `renderer` is "2d" or "blender" (default: the RENDERER setting). Blender falls back to 2D when unavailable.
    """
    d = project_dir(ctx, slug)
    final = d / "final.mp4"
    if final.exists() and not force:
        return final
    script_file = d / "script.json"
    if not script_file.exists():
        raise StageError(f"No script for {slug}.", "The kids build needs projects/kids_<slug>/script.json.",
                         "Run `kids script \"<topic>\"` first.")
    data = json.loads(script_file.read_text(encoding="utf-8"))
    problems = spec.validate(data)
    if problems:
        raise StudioError("script.json is invalid:\n  - " + "\n  - ".join(problems), "",
                          "Fix the script (see the prompt file) and re-run.")
    ff.ensure_ffmpeg()
    settings = ctx.settings
    if settings.tts_provider == "edge":
        settings = dataclasses.replace(settings, tts_voice=os.getenv("KIDS_TTS_VOICE", KIDS_VOICE))
    tts = get_tts(settings)
    font_file = font_path(ctx.settings.assets_dir)
    counting = data["kind"] == "counting"
    sprites = SpriteBank(ctx.settings.assets_dir / "kids" / "characters")
    exe = build3d.choose(renderer or ctx.settings.renderer, ctx.settings.blender_path)
    if exe is not None:
        fps = build3d.FPS_3D
    parts: list[Path] = []
    for i, scene in enumerate(data["scenes"], 1):
        audio, clip = d / f"scene{i:02d}.mp3", d / f"scene{i:02d}.mp4"
        # Chorus scenes are identical, so a repeated chorus reuses the same narration file.
        if not audio.exists() or force:
            tts.synth(". ".join(scene["lines"]) + ".", audio)
        narr = ff.probe_duration(audio)
        cam = scene.get("visual", {}).get("camera") or draw.CAMERAS[(i - 1) % len(draw.CAMERAS)]
        if exe is not None:
            build3d.render_scene(exe, scene, audio, narr, clip, size, fps, font_file, counting, cam,
                                 d / f"frames3d_{i:02d}")
        else:
            render_scene(scene, audio, narr, clip, size, fps, font_file, counting, sprites, cam)
        parts.append(clip)
    lst = ff.concat_list(parts, d / "scenes.txt")
    joined = d / "joined.mp4"
    ff.run(ff.concat_cmd(lst, joined), "joining kids scenes")
    track = _music(ctx)
    if track is None:  # no track in assets/music: make an original tune from the title
        track = music.render(data["title"], d / "music.wav")
    ff.run(["ffmpeg", "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(track), "-filter_complex",
            "[1:a]volume=-20dB[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v",
            "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final)], "mixing music")
    thumbnail(data, d / "thumbnail.jpg", font_file)
    return final


def thumbnail(data: dict, out: Path, font_file: str, size: tuple[int, int] = (1280, 720)) -> Path:
    """Bright 1280x720 thumbnail: first scene's characters with a short title. No faces of real children."""
    first = data["scenes"][0]
    img = draw.background(first["visual"]["background"], *size)
    d = ImageDraw.Draw(img)
    chars = first["visual"]["characters"][:3]
    for i, c in enumerate(chars):
        draw.draw_character(d, c, size[0] * (i + 1) / (len(chars) + 1), size[1] * 0.3, size[1] * 0.38, idx=i)
    f = ImageFont.truetype(font_file, 84)
    words_, lines, cur = data["title"].split(), [], ""
    for wd in words_:  # wrap so long titles stay inside the frame
        if cur and len(cur) + len(wd) + 1 > 16:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    lines.append(cur)
    for k, ln in enumerate(lines[:3]):
        d.text((size[0] / 2, size[1] * (0.68 + 0.14 * k)), ln, font=f, anchor="mm", fill=(255, 235, 60),
               stroke_width=8, stroke_fill=draw.INK)
    img.save(out, "JPEG", quality=88)
    return out

