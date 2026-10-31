"""Quality gate for downloaded photos and video clips: corrupt, tiny, blurry, blank or wrong-shaped media is rejected.

Broken-looking pictures in a finished video almost always come from a download that was never checked
(an HTML error page saved as .jpg, a 400 px thumbnail stretched to 1080p, a portrait photo cropped to a strip).
Every function here is pure and returns a list of human-readable problems; an empty list means the file is fine.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

MIN_W, MIN_H = 1280, 720          # smaller than 720p looks soft when scaled to 1080p
MIN_ASPECT, MAX_ASPECT = 1.25, 2.4  # landscape only; 16:9 is 1.78
MIN_SHARPNESS = 60.0              # variance of the edge map; below this the photo is mush
MIN_CONTRAST = 14.0               # grey-level standard deviation; below this it is a flat blank frame
MIN_CLIP_SECONDS = 2.0


def _interior(im: Image.Image) -> Image.Image:
    """Drop the 2 px border, where the edge filter reports false edges."""
    return im.crop((2, 2, im.width - 2, im.height - 2))


def check_image(path: Path, min_w: int = MIN_W, min_h: int = MIN_H) -> list[str]:
    """Problems with a still image: unreadable, too small, wrong aspect ratio, blurry or blank."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:  # verify() leaves the file unusable, so open it again
            im.load()
            w, h = im.size
            grey = im.convert("L")
    except Exception as exc:  # Pillow raises many types for broken data
        return [f"{path.name}: not a readable image ({type(exc).__name__})"]
    problems = []
    if w < min_w or h < min_h:
        problems.append(f"{path.name}: {w}x{h} is below {min_w}x{min_h}")
    aspect = w / h
    if not MIN_ASPECT <= aspect <= MAX_ASPECT:
        problems.append(f"{path.name}: aspect ratio {aspect:.2f} is not landscape ({MIN_ASPECT}-{MAX_ASPECT})")
    small = grey.resize((min(w, 640), max(1, round(min(w, 640) * h / w))))
    if ImageStat.Stat(small).stddev[0] < MIN_CONTRAST:
        problems.append(f"{path.name}: almost one flat colour (blank or placeholder image)")
    elif ImageStat.Stat(_interior(small.filter(ImageFilter.FIND_EDGES))).var[0] < MIN_SHARPNESS:
        problems.append(f"{path.name}: too blurry")
    return problems


def probe_video(path: Path) -> dict | None:
    """width/height/duration of the first video stream via ffprobe, or None if it cannot be read."""
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,duration:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        data = json.loads(p.stdout or "{}")
        stream = data["streams"][0]
        dur = stream.get("duration") or (data.get("format") or {}).get("duration")
        return {"width": int(stream["width"]), "height": int(stream["height"]), "duration": float(dur or 0)}
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None


def check_clip(path: Path, min_w: int = MIN_W, min_h: int = MIN_H) -> list[str]:
    """Problems with a stock video clip: unreadable, too small, portrait or too short."""
    info = probe_video(path)
    if info is None:
        return [f"{path.name}: not a readable video"]
    problems = []
    if info["width"] < min_w or info["height"] < min_h:
        problems.append(f"{path.name}: {info['width']}x{info['height']} is below {min_w}x{min_h}")
    if info["width"] < info["height"]:
        problems.append(f"{path.name}: portrait video")
    if 0 < info["duration"] < MIN_CLIP_SECONDS:
        problems.append(f"{path.name}: only {info['duration']:.1f}s long")
    return problems


def check_media(path: Path, kind: str) -> list[str]:
    """Dispatch on kind: 'clip' for video, anything else for a still image."""
    return check_clip(path) if kind == "clip" else check_image(path)


def dhash(path: Path, size: int = 8) -> int | None:
    """64-bit difference hash. Near-identical pictures differ in only a few bits (see `similar`)."""
    try:
        with Image.open(path) as im:
            g = im.convert("L").resize((size + 1, size))
        px = list(g.tobytes())
    except Exception:
        return None
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (px[row * (size + 1) + col] > px[row * (size + 1) + col + 1])
    return bits


def similar(a: int, b: int, max_bits: int = 6) -> bool:
    """True when two hashes describe (nearly) the same picture."""
    return bin(a ^ b).count("1") <= max_bits


def video_hash(path: Path) -> int | None:
    """dhash of the frame one second in, for de-duplicating clips (needs ffmpeg)."""
    out = path.with_suffix(".hash.jpg")
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(path), "-frames:v", "1", str(out)],
                       capture_output=True)
    if p.returncode != 0 or not out.exists():
        return None
    h = dhash(out)
    out.unlink(missing_ok=True)
    return h
