"""ffmpeg/ffprobe helpers. Command builders are pure functions so they can be unit tested."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path

from studio.errors import StudioError
from studio.util.logging import get_logger

log = get_logger("ffmpeg")
W, H = 1920, 1080
FPS = 30


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


def run(cmd: list[str], what: str) -> None:
    """Run an ffmpeg command; on failure show the tail of stderr."""
    log.debug("ffmpeg: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
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
def _fit(w: int = W, h: int = H) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS},format=yuv420p"


def clip_cmd(src: Path, duration: float, out: Path, start: float = 0.0) -> list[str]:
    """Loop/trim a stock clip to `duration`, fill 1920x1080, no audio."""
    return ["ffmpeg", "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}",
            "-vf", _fit(), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]


def image_cmd(src: Path, duration: float, out: Path, zoom: bool = True) -> list[str]:
    """Still image to video with a slow push-in so the frame never looks frozen."""
    frames = max(1, round(duration * FPS))
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='min(zoom+0.0006,1.08)':d={frames}:s={W}x{H}:fps={FPS},"
          "format=yuv420p" if zoom else _fit())
    return ["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(out)]


def concat_list(paths: list[Path], list_file: Path) -> Path:
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), encoding="utf-8")
    return list_file


def concat_cmd(list_file: Path, out: Path, reencode: bool = False) -> list[str]:
    codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac"] if reencode else ["-c", "copy"]
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
    return cmd + vf + ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                       str(out)]


SUB_STYLE = "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1," \
            "Outline=2,Shadow=0,MarginV=40"


def _escape_sub(path: Path | None) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'") if path else ""


def vertical_cmd(src: Path, start: float, duration: float, out: Path, subtitles: Path | None) -> list[str]:
    """Cut a 9:16 1080x1920 Short: blurred fill background with the 16:9 frame centred."""
    fc = ("[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          "boxblur=20:2[b];[fg]scale=1080:-2[f];[b][f]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if subtitles:
        fc += f",subtitles='{_escape_sub(subtitles)}':force_style='{SUB_STYLE},FontSize=14,MarginV=120'"
    fc += "[v]"
    return ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-filter_complex", fc,
            "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-movflags", "+faststart", str(out)]
