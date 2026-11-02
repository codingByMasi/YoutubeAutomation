# ruff: noqa: E501  (drawing code)
"""Channel branding for the history channel "Quill's Past": 800x800 profile icon and 2560x1440 banner.

Reuses the cast SVGs (`studio.history.cast`), the map and fonts from the scene renderer, so the art matches the
videos. Everything is original. Run: `python -m studio.history.channel_art [out_dir]`.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFilter

from studio.history import cast
from studio.history import render as R

CREAM = (244, 233, 207)
TEAL = (46, 125, 135)
TEAL_DARK = (30, 86, 94)
INK = R.INK
NAME = "Quill's Past"
TAGLINE = "History, told like a story"
BANNER = (2560, 1440)
SAFE = (507, 508, 2053, 931)  # YouTube's all-devices safe area (1546x423, centred)
DEFAULT_OUT = Path("assets/history/channel-art")


def _sprite(char_id: str, px: int, viewbox: str | None = None) -> Image.Image:
    """Character SVG as an RGBA picture; `viewbox` crops it (e.g. head only)."""
    svg = cast.roster_svg(char_id)
    for gid in ("eyes-closed", "mouth-open"):  # still picture: keep only the open eyes and closed mouth
        svg = re.sub(rf'<g id="{gid}">.*?</g>', "", svg, flags=re.S)
    if viewbox:
        svg = svg.replace('viewBox="0 0 400 400" width="400" height="400"', f'viewBox="{viewbox}"')
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=px))).convert("RGBA")


def _shadow(img: Image.Image, canvas: Image.Image, xy: tuple[int, int], off: int = 10, blur: int = 12, a: int = 90) -> None:
    """Paste `img` with a soft paper-cutout drop shadow."""
    sh = Image.new("RGBA", img.size, (60, 40, 20, 0))
    sh.putalpha(img.getchannel("A").point(lambda v: v * a // 255))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(sh, (xy[0] + off, xy[1] + off))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    canvas.alpha_composite(img, xy)


def _feather(size: int) -> Image.Image:
    """A small quill feather (cream vane, teal-dark shaft), pointing down-left, on a transparent square."""
    s = 4
    im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    n = size * s
    vane = [(n * 0.92, n * 0.06), (n * 0.62, n * 0.10), (n * 0.30, n * 0.42), (n * 0.12, n * 0.86), (n * 0.30, n * 0.62),
            (n * 0.55, n * 0.40), (n * 0.80, n * 0.30)]
    d.polygon(vane, fill=(250, 244, 228, 255), outline=(*INK, 255))
    d.line([(n * 0.94, n * 0.04), (n * 0.10, n * 0.94)], fill=(*TEAL_DARK, 255), width=n // 36)
    d.polygon([(n * 0.10, n * 0.94), (n * 0.06, n * 0.99), (n * 0.17, n * 0.88)], fill=(*INK, 255))
    return im.resize((size, size), Image.LANCZOS)


def make_icon() -> Image.Image:
    """800x800 profile picture: Quill on a cream disc with a teal ring and a feather (YouTube crops to a circle)."""
    n = 800
    img = Image.new("RGBA", (n, n), (*TEAL_DARK, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([20, 20, n - 20, n - 20], fill=(*TEAL, 255))
    d.ellipse([52, 52, n - 52, n - 52], fill=(*CREAM, 255))
    d.ellipse([70, 70, n - 70, n - 70], outline=(200, 170, 118, 255), width=4)
    head = _sprite("quill", 620, "88 40 224 280")  # head and shoulders; the disc below crops the body
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    _shadow(head, layer, ((n - head.width) // 2, 150), off=8, blur=8)
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse([52, 52, n - 52, n - 52], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (n, n), 0), mask))
    img.alpha_composite(layer)
    f = _feather(250)
    _shadow(f, img, (480, 78), off=6, blur=6)
    return img.convert("RGB")


def _backdrop() -> Image.Image:
    """Faded map of the Mediterranean on parchment, with route lines, filling the full 2560x1440."""
    w, h = BANNER
    m = R._map_base().resize(BANNER, Image.LANCZOS).convert("RGBA")  # noqa: SLF001
    m.alpha_composite(Image.new("RGBA", BANNER, (*CREAM, 120)))
    d = ImageDraw.Draw(m)
    pts = [(220, 1100), (620, 860), (1000, 1010), (1500, 1150), (1950, 1000), (2350, 780)]
    for a, b in zip(pts, pts[1:]):
        R._dashed(d, a, b, (160, 60, 50, 200), 8)  # noqa: SLF001
    for x, y in (pts[0], pts[-1]):
        d.line([x - 22, y - 22, x + 22, y + 22], fill=(170, 50, 40, 230), width=10)
        d.line([x - 22, y + 22, x + 22, y - 22], fill=(170, 50, 40, 230), width=10)
    d.rectangle([40, 40, w - 40, h - 40], outline=(170, 138, 88, 255), width=8)
    d.rectangle([66, 66, w - 66, h - 66], outline=(196, 166, 116, 255), width=3)
    return m


def make_banner() -> Image.Image:
    """2560x1440 banner. Title, tagline and all three characters sit inside the 1546x423 safe area."""
    img = _backdrop()
    x0, y0, x1, y1 = SAFE
    panel = Image.new("RGBA", BANNER, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([x0 + 6, y0 + 20, x0 + 660, y1 - 20], 36, fill=(250, 244, 228, 255),
                                           outline=(*INK, 255), width=6)
    _shadow(panel, img, (0, 0), off=12, blur=14, a=110)
    d = ImageDraw.Draw(img)
    tf = R.font(92)
    while d.textlength(NAME, font=tf) > 580:
        tf = R.font(tf.size - 4)
    cx = x0 + 320
    d.text((cx, y0 + 140), NAME, font=tf, fill=(*TEAL_DARK, 255), anchor="mm")
    d.line([cx - 250, y0 + 205, cx + 250, y0 + 205], fill=(200, 170, 118, 255), width=5)
    sf = R.font(40, serif=False)
    while d.textlength(TAGLINE, font=sf) > 580:
        sf = R.font(sf.size - 2, serif=False)
    d.text((cx, y0 + 262), TAGLINE, font=sf, fill=(*INK, 255), anchor="mm")
    # cast: Dusty, Quill (host, biggest, centre), Vizier Vex; feet share one line at the bottom of the safe area
    feet = y1 - 30  # body bottom (0.9 of the sprite square) sits here
    for cid, px, centre in (("dusty", 400, 1290), ("vex", 420, 1860), ("quill", 520, 1560)):
        s = _sprite(cid, px)
        _shadow(s, img, (centre - px // 2, feet - round(px * 0.9)))
    return img.convert("RGB")


def main(out: Path = DEFAULT_OUT) -> list[Path]:
    """Write icon.png and banner.png into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "channel-icon-800.png", out / "channel-banner-2560x1440.png"]
    make_icon().save(paths[0])
    make_banner().save(paths[1])
    return paths


if __name__ == "__main__":
    for p in main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT):
        print(p)
