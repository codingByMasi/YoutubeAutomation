"""History thumbnails drawn from the cast: big shocked characters over a dramatic backdrop plus 2-3 big words.

Three layouts (A: characters on the mountains, B: map with a question mark, C: silhouette at night). Original art only.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from studio.history import cast, wardrobe
from studio.history import render as R

TW, TH = 1280, 720
YELLOW, WHITE, BLACK = (255, 214, 10), (255, 255, 255), (12, 10, 20)


def _text(img: Image.Image, text: str, xy: tuple[int, int], size: int, fill: tuple = WHITE, anchor: str = "lm") -> None:
    d = ImageDraw.Draw(img)
    f = R.font(size)
    lines = R.wrap(text.upper(), f, 620)[:3]
    y = xy[1] - (len(lines) - 1) * size * 0.55
    for i, ln in enumerate(lines):
        d.text((xy[0], y + i * size * 1.1), ln, font=f, fill=YELLOW if i == len(lines) - 1 else fill, anchor=anchor,
               stroke_width=max(6, size // 9), stroke_fill=BLACK)


def _cast_of(pkg: dict) -> list[str]:
    for s in pkg.get("segments", []):
        if s.get("scene") == "skit" and s.get("cast"):
            return list(s["cast"])[:2]
    named = [str(c["name"]) for c in pkg.get("characters") or [] if isinstance(c, dict) and c.get("name")]
    return named[:2] or [cast.GENERIC]


def make(pkg: dict, texts: list[str], work: Path) -> list[Image.Image]:
    """Three 1280x720 thumbnails for a history video."""
    cst = R.Cast(work)
    who = _cast_of(pkg)
    era = wardrobe.era_for({}, pkg)  # same characters, story-era costume
    texts = [*(texts or []), "", "", ""][:3]

    # A: two shocked characters in front of the mountains
    a = R.backdrop("mountains").copy()
    a = Image.blend(a, Image.new("RGB", a.size, (255, 190, 120)), 0.12)
    for i, w in enumerate(who):
        spr = cst.sprite(w, 560, 0.4, i, talking=True, era=era)
        R.paste(a, spr, 900 + (i * 190 - 95) * (1 if len(who) > 1 else 0), 790)
    _text(a, texts[0] or "Rome laughed", (50, 220), 130)

    # B: map and a huge question mark
    b = R._map_base().copy().filter(ImageFilter.GaussianBlur(2))  # noqa: SLF001
    d = ImageDraw.Draw(b)
    d.text((930, 330), "?", font=R.font(560), fill=R.RED, anchor="mm", stroke_width=18, stroke_fill=BLACK)
    spr_b = cst.sprite(who[-1], 420, 0.4, 0, True, era=era)
    b.paste(spr_b, (20, 330), spr_b)
    _text(b, texts[2] or texts[1] or "Which pass?", (50, 150), 130)

    # C: silhouette against the night sky
    c = R.backdrop("night").copy()
    spr = cst.sprite(who[0], 600, 0.4, 0, False, silhouette=True, era=era)
    R.paste(c, spr, 940, 745)
    _text(c, texts[1] or "Impossible road", (50, 300), 130)
    return [a, b, c]
