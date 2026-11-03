"""Photo scene: one real photo shown as a proper scene (full frame or framed inset) with a caption plate.

Drawn with Pillow (1280x720, 24 fps) and piped to ffmpeg, with a slow push-in. The photo is a stock image found
by the `visuals` stage; the clip becomes the segment's `scene_clip`, like the drawn cast scenes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from studio.errors import StudioError
from studio.util import ffmpeg as ff
from studio.util import fonts

W, H, FPS = 1280, 720, 24
INK = (43, 43, 61)
PAPER = (239, 227, 200)
SANS, SERIF = False, True  # font faces for `_font` (see studio/util/fonts.py)
CODE_STAMP = "photo-scene-1"


def _font(size: int, serif: bool = SANS) -> ImageFont.ImageFont:
    return fonts.load(size, serif)


def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


def _plate(img: Image.Image, text: str, cx: int, cy: int) -> None:
    """Caption plate: paper-coloured box with ink text, centred on (cx, cy)."""
    if not text:
        return
    f = _font(34, SERIF)
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), text, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    x0, y0 = cx - tw // 2 - 28, cy - th // 2 - 16
    d.rounded_rectangle((x0 + 5, y0 + 6, x0 + tw + 61, y0 + th + 38), 14, fill=(0, 0, 0))
    d.rounded_rectangle((x0, y0, x0 + tw + 56, y0 + th + 32), 14, fill=PAPER, outline=INK, width=4)
    d.text((x0 + 28 - box[0], y0 + 16 - box[1]), text, font=f, fill=INK)


def compose(photo: Path, caption: str = "", layout: str = "inset") -> Image.Image:
    """The still picture, 6% larger than the frame so the push-in has room: 'full' fills the frame, 'inset' puts a
    framed photo on a darkened blurred copy of itself. Raises StudioError for an unreadable photo."""
    try:
        src = Image.open(photo).convert("RGB")
    except (OSError, ValueError) as exc:
        raise StudioError(f"Could not open the photo {Path(photo).name}.", str(exc),
                          "Delete it from assets/cache and re-run `visuals --force`.") from exc
    bw, bh = round(W * 1.06), round(H * 1.06)
    if layout == "full":
        img = _cover(src, bw, bh)
        strip = (0, bh - 190, bw, bh)
        img.paste(Image.blend(img.crop(strip), Image.new("RGB", (bw, 190)), 0.45), strip[:2])
        _plate(img, caption, bw // 2, bh - 90)
    else:
        img = ImageEnhance.Brightness(_cover(src, bw, bh).filter(ImageFilter.GaussianBlur(18))).enhance(0.55)
        pic = _cover(src, 860, 484)
        frame = Image.new("RGB", (884, 508), PAPER)
        frame.paste(pic, (12, 12))
        ImageDraw.Draw(frame).rectangle((0, 0, 883, 507), outline=INK, width=4)
        img.paste(frame, ((bw - 884) // 2, (bh - 508) // 2 - 30))
        _plate(img, caption, bw // 2, (bh + 508) // 2 - 30 + 52)
    return img


def fingerprint(photo: Path, caption: str, layout: str, dur: float) -> str:
    """Hash of everything that decides how the clip looks (re-render only when it changes)."""
    p = Path(photo)
    keys = {"p": f"{p.name}:{p.stat().st_size if p.exists() else 0}", "c": caption, "l": layout,
            "d": round(dur, 2), "v": CODE_STAMP}
    return hashlib.sha1(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:12]


def render_photo_scene(photo: Path, out: Path, dur: float, caption: str = "", layout: str = "inset") -> Path:
    """Render the photo scene to `out` (silent H.264, 1280x720, 24 fps, `dur` seconds). Reuses an identical clip."""
    ff.ensure_ffmpeg()
    stamp = out.with_suffix(".stamp")
    fp = fingerprint(photo, caption, layout, dur)
    if out.exists() and stamp.exists() and stamp.read_text() == fp:
        return out
    big = compose(photo, caption, layout)
    n = max(1, round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           str(out)]
    proc = subprocess.Popen(ff.low_memory_cmd(cmd), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(n):
            z = 1.0 - 0.0472 * (f / max(n - 1, 1))  # push in from the whole 106% canvas to a 101% crop
            cw, ch = big.width * z, big.height * z
            x0, y0 = (big.width - cw) / 2, (big.height - ch) / 2
            frame = big.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise StudioError("ffmpeg failed while drawing a photo scene.", err.strip()[-600:],
                              "Check ffmpeg is installed and re-run `visuals --force`.")
    except BrokenPipeError as exc:
        raise StudioError("ffmpeg closed early while drawing a photo scene.", proc.stderr.read().decode()[-600:],
                          "Check ffmpeg is installed and re-run `visuals --force`.") from exc
    finally:
        if proc.poll() is None:
            proc.kill()
    stamp.write_text(fp)
    return out
