"""ffmpeg/ffprobe helpers. Command builders are pure functions so they can be unit tested."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from studio.errors import StudioError
from studio.util.logging import get_logger

log = get_logger("ffmpeg")
W, H = 1920, 1080
FPS = 30


@dataclass(frozen=True)
class Profile:
    """Encoding settings. Draft mode (STUDIO_DRAFT=1) trades quality for speed: 720p, 24 fps, no zoom."""

    w: int = W
    h: int = H
    fps: int = FPS
    preset: str = "veryfast"
    crf: int = 20
    zoom: bool = True
    draft: bool = False


def profile() -> Profile:
    """Current profile, read from the environment each call so the UI can switch it per run."""
    if os.getenv("STUDIO_DRAFT", "").strip().lower() in ("1", "true", "yes"):
        return Profile(w=1280, h=720, fps=24, preset="ultrafast", crf=28, zoom=False, draft=True)
    return Profile()


def install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ffmpeg"
    if system == "Windows":
        return "winget install ffmpeg (then reopen the terminal)"
    return "sudo apt install ffmpeg"


def ensure_ffmpeg() -> None:
    """Raise a clear error if ffmpeg or ffprobe is not on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise StudioError(f"{tool} not found.", "Video and audio steps need ffmpeg on PATH.",
                              f"Install it: {install_hint()}")


OOM_CODES = (-9, 137)  # SIGKILL: what the kernel sends when a container runs out of memory


def low_memory_cmd(cmd: list[str]) -> list[str]:
    """Cap x264 threads and lookahead so small hosts (e.g. 1 GB cloud apps) do not run out of memory.

    STUDIO_FFMPEG_THREADS (default 2) sets the cap; 0 leaves ffmpeg's defaults.
    """
    try:
        threads = int(os.getenv("STUDIO_FFMPEG_THREADS", "2"))
    except ValueError:
        threads = 2
    if threads <= 0 or "libx264" not in cmd:
        return cmd
    return [*cmd[:-1], "-x264-params", f"threads={threads}:lookahead_threads=1:rc-lookahead=10", cmd[-1]]


def run(cmd: list[str], what: str) -> None:
    """Run an ffmpeg command; on failure show the tail of stderr."""
    cmd = low_memory_cmd(cmd)
    log.debug("ffmpeg: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode in OOM_CODES:
        raise StudioError(f"ffmpeg was killed while {what}.", "The host ran out of memory (exit code "
                          f"{p.returncode}). Free hosting has about 1 GB of RAM.",
                          "Run the app on your own computer for this video, or make it shorter, then re-run "
                          "the step.")
    if p.returncode != 0:
        raise StudioError(f"ffmpeg failed while {what}.", p.stderr.strip()[-1200:],
                          "Check the input files exist and are valid media, then re-run with --force.")


def probe_duration(path: Path) -> float:
    """Media duration in seconds via ffprobe."""
    ensure_ffmpeg()
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        return float(json.loads(p.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise StudioError(f"Could not read the duration of {path}.", p.stderr.strip()[-300:],
                          "Delete the file and re-run the stage with --force.") from exc


def has_audio_stream(path: Path) -> bool:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(p.stdout.strip())


# ---------- builders ----------
def _fit(w: int | None = None, h: int | None = None) -> str:
    p = profile()
    w, h = w or p.w, h or p.h
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={p.fps},format=yuv420p"


def clip_cmd(src: Path, duration: float, out: Path, start: float = 0.0) -> list[str]:
    """Loop/trim a stock clip to `duration`, fill 1920x1080, no audio."""
    return ["ffmpeg", "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}",
            "-vf", _fit(), "-an", "-c:v", "libx264", "-preset", profile().preset, "-crf", str(profile().crf),
            str(out)]


def image_cmd(src: Path, duration: float, out: Path, zoom: bool = True) -> list[str]:
    """Still image to video with a slow push-in so the frame never looks frozen."""
    p = profile()
    zoom = zoom and p.zoom
    frames = max(1, round(duration * p.fps))
    big_w, big_h = p.w * 3 // 2, p.h * 3 // 2  # 1.5x is enough headroom for the slow zoom and half the memory of 2x
    fill = f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h}"
    vf = (f"{fill},zoompan=z='min(zoom+0.0006,1.08)':d={frames}:s={p.w}x{p.h}:fps={p.fps},"
          "format=yuv420p" if zoom else _fit())
    return ["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf,
            "-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf), "-r", str(p.fps), str(out)]


def concat_list(paths: list[Path], list_file: Path) -> Path:
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), encoding="utf-8")
    return list_file


def concat_cmd(list_file: Path, out: Path, reencode: bool = False) -> list[str]:
    p = profile()
    codec = (["-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf), "-c:a", "aac"] if reencode
             else ["-c", "copy"])
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), *codec, str(out)]


def audio_concat_cmd(list_file: Path, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le", str(out)]


def mix_cmd(video: Path, voice: Path, out: Path, music: Path | None, music_db: float = -20.0,
            subtitles: Path | None = None) -> list[str]:
    """Mux narration (and optional looped music `music_db` under it) onto the video; burn subtitles."""
    cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(voice)]
    vf = ["-vf", f"subtitles='{_escape_sub(subtitles)}':force_style='{SUB_STYLE}'"] if subtitles else []
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        fc = (f"[2:a]volume={music_db}dB[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:"
              "normalize=0[a]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    p = profile()
    # Without subtitles the picture is already encoded: copy it instead of encoding the whole video again.
    video_codec = (["-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf), "-pix_fmt", "yuv420p"] if subtitles
                   else ["-c:v", "copy"])
    return cmd + vf + [*video_codec, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                       "-movflags", "+faststart", str(out)]


SUB_STYLE = "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1," \
            "Outline=2,Shadow=0,MarginV=30"


def _escape_sub(path: Path | None) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'") if path else ""


def vertical_cmd(src: Path, start: float, duration: float, out: Path, subtitles: Path | None) -> list[str]:
    """Cut a 9:16 1080x1920 Short: blurred fill background with the 16:9 frame centred."""
    fc = ("[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          "boxblur=20:2[b];[fg]scale=1080:-2[f];[b][f]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if subtitles:
        fc += f",subtitles='{_escape_sub(subtitles)}':force_style='{SUB_STYLE},FontSize=12,MarginV=55'"
    fc += "[v]"
    return ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-filter_complex", fc,
            "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-movflags", "+faststart", str(out)]
