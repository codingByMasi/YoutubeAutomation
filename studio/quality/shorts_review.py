"""Review of a cut Short, for any video: the same kinds of checks the main video gets, run on the Short's own file.

`review_short` measures the file (duration, loudness, true peak, silence, first sound, how much the picture moves),
checks that its captions fit the frame and that it opens on a story moment with a title, and re-runs the script-level
retention checks and the drawn-scene checks on the segments it covers. The `shorts` step keeps only Shorts that pass,
trying the next-best run when one fails, and saves every verdict in `shorts_review.json`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MIN_SECONDS, MAX_SECONDS = 15.0, 58.0
LUFS_RANGE = (-16.5, -11.5)  # integrated loudness a Short may have
TRUE_PEAK_MAX = -1.0  # dBFS
FIRST_SOUND_MAX = 0.6  # seconds: a Short starts talking at once
STILL_MAX = 2.5  # seconds the picture may hold almost still
SILENCE_MAX = 1.0  # seconds of silence (below -45 dB) that is allowed


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stderr


def measure(path: Path) -> dict:
    """Loudness, peak, silence, first sound and picture movement of a Short, from ffmpeg's own meters."""
    import numpy as np
    out: dict = {}
    r = _run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"])
    tail = r[r.rindex("Summary:"):] if "Summary:" in r else ""
    m = re.search(r"I:\s+(-?[0-9.]+) LUFS", tail)
    p = re.search(r"Peak:\s+(-?[0-9.]+) dBFS", tail)
    out["lufs"] = float(m.group(1)) if m else None
    out["true_peak"] = float(p.group(1)) if p else None
    r = _run(["ffmpeg", "-nostats", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=0.5", "-f", "null", "-"])
    out["silences"] = [float(x) for x in re.findall(r"silence_duration: ([0-9.]+)", r)]
    starts = re.findall(r"silence_start: ([0-9.]+)", r)
    out["first_sound"] = float(re.findall(r"silence_end: ([0-9.]+)", r)[0]) if starts and float(starts[0]) < 0.05 \
        and re.findall(r"silence_end: ([0-9.]+)", r) else 0.0
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    out["duration"] = float(dur or 0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "fps=2,scale=96:170,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 170, 96).astype(float) if raw else np.zeros((0, 170, 96))
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.array([])
    best = cur = 0
    for still in diffs < 0.4:
        cur = cur + 1 if still else 0
        best = max(best, cur)
    out["longest_still"] = best / 2
    out["moving_share"] = float((diffs > 1.0).mean()) if len(diffs) else 0.0
    return out


def caption_problems(ass_text: str, width: int = 1080, size: int = 84) -> list[str]:
    """Caption phrases wider than the frame (the style does not wrap, so they would be cut off)."""
    from studio.util import fonts
    f = fonts.load(size, False)
    out = []
    for m in re.finditer(r"Dialogue: 0,[^,]*,[^,]*,Default,,0,0,0,,(.*)", ass_text):
        plain = re.sub(r"\{[^}]*\}", "", m.group(1))
        if f.getlength(plain) * 1.08 > width - 60:
            out.append(f"the caption {plain[:30]!r} is wider than the frame")
    return out[:3]


def review_short(path: Path, window: list[dict], characters: list[dict] | None, ass_text: str, title: str,
                 facts: dict | None = None) -> dict:
    """{ok, issues, facts} for one Short. `window` are the script segments it covers, in order."""
    from studio.stages.timing import NEEDS_CONTEXT
    f = facts if facts is not None else measure(path)
    issues: list[str] = []
    if not MIN_SECONDS <= f["duration"] <= MAX_SECONDS:
        issues.append(f"it runs {f['duration']:.0f} s; a Short should be {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} s")
    if f["lufs"] is None or not LUFS_RANGE[0] <= f["lufs"] <= LUFS_RANGE[1]:
        issues.append(f"loudness is {f['lufs']} LUFS (wanted {LUFS_RANGE[0]} to {LUFS_RANGE[1]})")
    if f["true_peak"] is not None and f["true_peak"] > TRUE_PEAK_MAX:
        issues.append(f"true peak {f['true_peak']} dBFS is above {TRUE_PEAK_MAX}: it may clip")
    if any(s > SILENCE_MAX for s in f["silences"]):
        issues.append(f"{max(f['silences']):.1f} s of silence inside it")
    if f["first_sound"] > FIRST_SOUND_MAX:
        issues.append(f"nothing is heard for the first {f['first_sound']:.1f} s")
    if f["longest_still"] > STILL_MAX:
        issues.append(f"the picture holds still for {f['longest_still']:.1f} s")
    if window and window[0].get("scene") in NEEDS_CONTEXT:
        issues.append(f"it opens on a {window[0]['scene']} card that needs the scene before it")
    if not title.strip() or "Banner" not in ass_text:
        issues.append("it has no title over the first seconds (the hook)")
    issues += caption_problems(ass_text)
    sub = {"segments": [dict(s) for s in window], "characters": characters}
    if any(s.get("scene") for s in window):
        from studio.history import scene_check
        issues += [p.split(": ", 1)[-1] for p in scene_check.check_package(sub)[:3]]
        from studio.quality import retention_review as rr
        for it in rr.long_cards(sub["segments"]) + rr.weak_start(sub["segments"]):
            issues.append(it["issue"])
    return {"ok": not issues, "issues": issues, "facts": f}
