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


GRADE = "eq=contrast=1.05:saturation=1.08:gamma=0.98"  # one gentle look so mixed stock sources feel like one film
BLUR_BELOW_ASPECT = 1.5  # photos narrower than this keep their whole frame on a blurred backdrop instead of a hard crop
MOTIONS = ("in", "pan_right", "out", "pan_left", "in_top")  # cycled shot by shot so no two neighbours move alike
XFADE_SECONDS = 0.3


def clip_cmd(src: Path, duration: float, out: Path, start: float = 0.0) -> list[str]:
    """Loop/trim a stock clip to `duration`, fill the frame, no audio."""
    return ["ffmpeg", "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}",
            "-vf", f"{_fit()},{GRADE}", "-an", "-c:v", "libx264", "-preset", profile().preset,
            "-crf", str(profile().crf), str(out)]


def motion_exprs(motion: str, frames: int) -> tuple[str, str, str]:
    """zoompan (z, x, y) expressions for a camera move that runs smoothly over `frames` frames."""
    n = max(frames - 1, 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "in": (f"1+0.10*on/{n}", cx, cy),
        "out": (f"1.10-0.10*on/{n}", cx, cy),
        "pan_right": ("1.10", f"(iw-iw/zoom)*on/{n}", cy),
        "pan_left": ("1.10", f"(iw-iw/zoom)*(1-on/{n})", cy),
        "in_top": (f"1+0.12*on/{n}", cx, "(ih-ih/zoom)*0.25"),
    }.get(motion, (f"1+0.10*on/{n}", cx, cy))


def image_cmd(src: Path, duration: float, out: Path, zoom: bool = True, motion: int = 0,
              aspect: float | None = None) -> list[str]:
    """Still image to video with a camera move (Ken Burns) so the frame never looks frozen.

    `motion` picks the move from MOTIONS (cycled by the caller). `aspect` (width/height of the photo): if it is
    not wide enough for a clean crop, the whole photo is shown over a blurred copy of itself.
    """
    p = profile()
    zoom = zoom and p.zoom
    frames = max(1, round(duration * p.fps))
    big_w, big_h = p.w * 3 // 2, p.h * 3 // 2  # 1.5x is enough headroom for the move and half the memory of 2x
    if aspect is not None and aspect < BLUR_BELOW_ASPECT:
        fill = (f"split[a][b];[a]scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},"
                f"boxblur=40:4[bg];[b]scale={big_w}:{big_h}:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2")
    else:
        fill = f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h}"
    if zoom:
        z, x, y = motion_exprs(MOTIONS[motion % len(MOTIONS)], frames)
        vf = f"{fill},zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={p.w}x{p.h}:fps={p.fps},{GRADE},format=yuv420p"
    else:
        vf = f"{_fit()},{GRADE}"
    return ["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf,
            "-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf), "-r", str(p.fps), str(out)]


def xfade_cmd(parts: list[Path], durations: list[float], out: Path, fade: float = XFADE_SECONDS) -> list[str]:
    """Join shots with cross-dissolves. Every part except the last must have been rendered `fade` seconds
    longer than its slot in `durations`; the overlap then eats exactly that extra, so the total stays put."""
    if len(parts) != len(durations) or len(parts) < 2:
        raise ValueError("xfade needs matching parts/durations and at least two shots")
    fade = min(fade, min(durations) / 2)
    cmd = ["ffmpeg", "-y"]
    for part in parts:
        cmd += ["-i", str(part)]
    chain, offset, prev = [], 0.0, "[0:v]"
    for k in range(1, len(parts)):
        offset += durations[k - 1]
        label = f"[x{k}]" if k < len(parts) - 1 else "[v]"
        chain.append(f"{prev}[{k}:v]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}{label}")
        prev = label
    p = profile()
    return cmd + ["-filter_complex", ";".join(chain), "-map", "[v]", "-c:v", "libx264", "-preset", p.preset,
                  "-crf", str(p.crf), "-pix_fmt", "yuv420p", str(out)]


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


def sfx_filters(events: list[tuple[str, float]], first_input: int) -> tuple[list[str], list[str]]:
    """(inputs, filter lines) placing each sound effect at its time. `events` are (kind, seconds); inputs are
    ordered by sorted kind starting at ffmpeg input index `first_input`; the mixed result is labelled [sfx]."""
    kinds = sorted({k for k, _ in events})
    lines, labels = [], []
    for ki, kind in enumerate(kinds):
        times = sorted(t for k, t in events if k == kind)
        outs = [f"[{kind}{n}]" for n in range(len(times))]
        lines.append(f"[{first_input + ki}:a]asplit={len(times)}{''.join(outs)}" if len(times) > 1
                     else f"[{first_input + ki}:a]anull{outs[0]}")
        for lab, at in zip(outs, times):
            ms = max(0, round(at * 1000))
            lines.append(f"{lab}adelay={ms}:all=1,volume={SFX_DB.get(kind, -12)}dB[d_{lab[1:-1]}]")
            labels.append(f"[d_{lab[1:-1]}]")
    lines.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0[sfx]")
    return kinds, lines


SFX_DB = {"whoosh": -14, "pop": -17, "hit": -12}
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"  # YouTube's reference loudness is about -14 LUFS


def mix_cmd(video: Path, voice: Path, out: Path, music: Path | None, music_db: float = -20.0,
            subtitles: Path | None = None, sfx: dict[str, Path] | None = None,
            sfx_events: list[tuple[str, float]] | None = None, total: float | None = None) -> list[str]:
    """Mux narration onto the video, with looped music ducked under the voice, optional sound effects at
    given times, loudness-normalised. Burns subtitles when given (re-encodes the picture)."""
    cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(voice)]
    vf = ["-vf", _sub_filter(subtitles)] if subtitles else []
    events = [e for e in (sfx_events or []) if sfx and e[0] in sfx]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    kinds: list[str] = []
    if events:
        kinds = sorted({k for k, _ in events})
        for k in kinds:
            cmd += ["-i", str(sfx[k])]
    if music or events:
        fade_out = f",afade=t=out:st={max(total - 3.0, 0):.2f}:d=3" if total else ""
        parts = []
        mix_in = ["[1:a]"]
        if music:
            parts += ["[1:a]asplit=2[vo][vk]",
                      f"[2:a]volume={music_db}dB,afade=t=in:d=1.5{fade_out}[m0]",
                      "[m0][vk]sidechaincompress=threshold=0.015:ratio=8:attack=15:release=400:makeup=1[md]"]
            mix_in = ["[vo]", "[md]"]
        if events:
            _, lines = sfx_filters(events, 3 if music else 2)
            parts += lines
            mix_in.append("[sfx]")
        parts.append(f"{''.join(mix_in)}amix=inputs={len(mix_in)}:duration=first:dropout_transition=0:"
                     f"normalize=0,{LOUDNORM}[a]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-af", LOUDNORM, "-map", "0:v", "-map", "1:a"]
    p = profile()
    # Without subtitles the picture is already encoded: copy it instead of encoding the whole video again.
    video_codec = (["-c:v", "libx264", "-preset", p.preset, "-crf", str(p.crf), "-pix_fmt", "yuv420p"] if subtitles
                   else ["-c:v", "copy"])
    return cmd + vf + [*video_codec, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                       "-movflags", "+faststart", str(out)]


SUB_STYLE = "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1," \
            "Outline=2,Shadow=0,MarginV=30"


def _sub_filter(path: Path) -> str:
    """ffmpeg filter that burns a .ass (styled) or .srt subtitle file."""
    if Path(path).suffix.lower() == ".ass":
        return f"ass='{_escape_sub(path)}'"
    return f"subtitles='{_escape_sub(path)}':force_style='{SUB_STYLE}'"


def _escape_sub(path: Path | None) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'") if path else ""


def vertical_cmd(src: Path, start: float, duration: float, out: Path, subtitles: Path | None) -> list[str]:
    """Cut a 9:16 1080x1920 Short: blurred fill background with the 16:9 frame centred."""
    fc = ("[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          "boxblur=20:2[b];[fg]scale=1080:-2[f];[b][f]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if subtitles and Path(subtitles).suffix.lower() == ".ass":
        fc += f",ass='{_escape_sub(subtitles)}'"
    elif subtitles:
        fc += f",subtitles='{_escape_sub(subtitles)}':force_style='{SUB_STYLE},FontSize=12,MarginV=55'"
    fc += "[v]"
    return ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-filter_complex", fc,
            "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-movflags", "+faststart", str(out)]
