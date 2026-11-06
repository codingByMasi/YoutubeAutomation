# ruff: noqa: E501  (drawing code)
"""History cast scene renderer: draws one segment's scene (skit, map, diagram, calendar, easel, title,
silhouette, archive) as an MP4 clip with the script's own characters acting in it.

Frames are drawn with Pillow (1280x720, 24 fps) and piped to ffmpeg. Characters are drawn one by one from the
script's descriptions by `studio/history/figures.py` (blinking eyes, mouth driven by the narration loudness). The clip becomes the segment's
`scene_clip`, so `build` shows it as one continuous shot. Everything here is original art drawn in code.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from studio.errors import StudioError
from studio.history import autoscene, cast, figures, maps, speech_audio, wardrobe
from studio.kids.sprites import blink
from studio.util import ffmpeg as ff
from studio.util import fonts

W, H, FPS = 1280, 720, 24
INK = (43, 43, 61)
PAPER = (239, 227, 200)
PAPER_DARK = (222, 205, 165)
WOOD = (122, 82, 51)
SEA = (176, 205, 210)
LAND = (222, 204, 160)
LAND_EDGE = (150, 122, 76)
RED = (192, 57, 43)
BACKDROPS = ("parchment", "mountains", "hall", "night", "snow", "field", "market", "plain", "sea", "desert")
DEFAULT_BACKDROP = {"lectern": "parchment", "skit": "hall", "map": "parchment", "diagram": "parchment",
                    "easel": "parchment", "archive": "parchment", "calendar": "parchment", "silhouette": "night",
                    "title": "night"}
_fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    """Cached bold font (serif for titles, sans for labels), the same size on every OS."""
    key = ("s" if serif else "n", size)
    if key not in _fonts:
        _fonts[key] = fonts.load(size, serif)
    return _fonts[key]


def ease(x: float) -> float:
    """Smooth 0..1 ramp (ease-out cubic)."""
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------- backdrops (drawn once per scene, 2x then shrunk)
def _gradient(top: tuple, bottom: tuple, w: int = W, h: int = H) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t)
    return Image.fromarray(np.repeat(arr, w, axis=1).astype("uint8"), "RGB")


def _vignette(img: Image.Image, strength: float = 0.35) -> Image.Image:
    y, x = np.ogrid[:H, :W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    f = 1 - strength * np.clip(d - 0.55, 0, 1) ** 1.5
    return Image.fromarray((np.asarray(img) * f[:, :, None]).astype("uint8"), "RGB")


def _ridge(rng: random.Random, base: float, amp: float, rough: float = 0.55, n: int = 7) -> list[tuple[float, float]]:
    """A jagged mountain skyline by midpoint displacement; points are (x, y) in pixels at 1x."""
    ys = [base + rng.uniform(-amp, amp), base + rng.uniform(-amp, amp)]
    a = amp
    for _ in range(n):
        out = []
        for i in range(len(ys) - 1):
            out += [ys[i], (ys[i] + ys[i + 1]) / 2 + rng.uniform(-a, a)]
        ys = out + [ys[-1]]
        a *= rough
    return [(i * W / (len(ys) - 1), y) for i, y in enumerate(ys)]


def _mountains() -> Image.Image:
    img = _gradient((124, 130, 178), (244, 205, 160))
    rng = random.Random(218)
    layers = [(0.58, 120, (150, 150, 190), False), (0.66, 110, (116, 118, 160), False), (0.76, 95, (84, 88, 120), True)]
    for base, amp, col, snow in layers:
        pts = _ridge(rng, H * base, amp)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).polygon([*pts, (W, H), (0, H)], fill=255)
        if snow:
            layer = Image.new("RGB", (W, H), (240, 244, 252))
            shifted = Image.new("L", (W, H), 0)
            ImageDraw.Draw(shifted).polygon([(x, y + 34) for x, y in pts] + [(W, H), (0, H)], fill=255)
            rock = ImageChops.multiply(mask, shifted)
            layer.paste(Image.new("RGB", (W, H), col), mask=rock)
            img.paste(layer, mask=mask)
        else:
            img.paste(Image.new("RGB", (W, H), col), mask=mask)
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(H * 0.86), W, H], fill=(96, 84, 74))
    d.rectangle([0, int(H * 0.86), W, int(H * 0.86) + 8], fill=(124, 108, 92))
    return _vignette(img, 0.3)


def _hall() -> Image.Image:
    img = _gradient((232, 214, 180), (205, 183, 140))
    d = ImageDraw.Draw(img)
    for x in range(-40, W + 80, 220):  # pillars
        d.rectangle([x, 0, x + 70, int(H * 0.84)], fill=(214, 196, 158))
        d.rectangle([x + 58, 0, x + 70, int(H * 0.84)], fill=(190, 170, 130))
        d.rectangle([x - 10, 0, x + 80, 36], fill=(196, 176, 136))
        d.rectangle([x - 10, int(H * 0.84) - 26, x + 80, int(H * 0.84)], fill=(196, 176, 136))
    d.rectangle([0, int(H * 0.84), W, H], fill=(150, 118, 84))
    for k in range(0, W, 160):
        d.line([k, int(H * 0.84), k - 60, H], fill=(128, 98, 68), width=3)
    return _vignette(img, 0.35)


def _night() -> Image.Image:
    img = _gradient((24, 28, 58), (70, 62, 96))
    rng = random.Random(7)
    d = ImageDraw.Draw(img)
    for _ in range(90):
        x, y, r = rng.randint(0, W), rng.randint(0, int(H * 0.6)), rng.choice([1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 246, 214))
    pts = _ridge(random.Random(3), H * 0.82, 40)
    d.polygon([*pts, (W, H), (0, H)], fill=(30, 28, 50))
    return _vignette(img, 0.3)


def _parchment() -> Image.Image:
    img = _gradient((244, 233, 207), (226, 208, 168))
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 4, (H, W, 1))
    img = Image.fromarray(np.clip(np.asarray(img) + noise, 0, 255).astype("uint8"), "RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([22, 22, W - 22, H - 22], outline=(170, 138, 88), width=4)
    d.rectangle([34, 34, W - 34, H - 34], outline=(196, 166, 116), width=2)
    return _vignette(img, 0.4)


def _snow() -> Image.Image:
    """A snowy pass: pale sky, layered white ridges, a trampled path."""
    img = _gradient((176, 196, 220), (236, 242, 250))
    rng = random.Random(41)
    for base, amp, col in [(0.46, 90, (196, 208, 230)), (0.58, 80, (222, 230, 244)), (0.7, 60, (244, 247, 252))]:
        pts = _ridge(rng, H * base, amp)
        ImageDraw.Draw(img).polygon([*pts, (W, H), (0, H)], fill=col)
    d = ImageDraw.Draw(img)
    for _ in range(14):  # dark pines
        x, y = rng.randint(0, W), rng.randint(int(H * 0.55), int(H * 0.8))
        for k in range(3):
            d.polygon([(x - 26 + k * 4, y - k * 26), (x, y - 46 - k * 26), (x + 26 - k * 4, y - k * 26)], fill=(52, 84, 84))
    d.rectangle([0, int(H * 0.84), W, H], fill=(250, 252, 255))
    d.polygon([(0, H), (W * 0.35, int(H * 0.84)), (W * 0.55, int(H * 0.84)), (W * 0.4, H)], fill=(214, 224, 240))
    return _vignette(img, 0.25)


def _field() -> Image.Image:
    """A green plain with a river and far blue mountains (a battlefield or a march)."""
    img = _gradient((150, 206, 238), (222, 240, 250))
    rng = random.Random(77)
    pts = _ridge(rng, H * 0.42, 40)
    d = ImageDraw.Draw(img)
    d.polygon([*pts, (W, H), (0, H)], fill=(146, 168, 204))
    pts2 = _ridge(rng, H * 0.47, 22)
    d.polygon([*pts2, (W, H), (0, H)], fill=(118, 160, 134))
    d.rectangle([0, int(H * 0.5), W, H], fill=(120, 176, 84))
    d.polygon([(0, int(H * 0.58)), (W, int(H * 0.54)), (W, int(H * 0.62)), (0, int(H * 0.68))], fill=(110, 178, 218))
    d.rectangle([0, int(H * 0.84), W, H], fill=(96, 154, 66))
    for _ in range(60):
        x, y = rng.randint(0, W), rng.randint(int(H * 0.7), H)
        d.line([(x, y), (x + 3, y - 12)], fill=(78, 138, 54), width=3)
    return _vignette(img, 0.25)


def _market(palms: bool = False) -> Image.Image:
    """A sunny sandy square: pale wall, banner posts, a wooden stage (palms only in the desert variant)."""
    img = _gradient((250, 226, 172), (236, 204, 144))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(H * 0.5)], fill=(176, 160, 138))
    for x in range(0, W, 90):  # rock/wall texture
        d.rectangle([x, 0, x + 60, int(H * 0.5)], fill=(166 - x % 9, 150, 128))
    d.rectangle([0, int(H * 0.5), W, H], fill=(226, 200, 134))
    d.rectangle([80, int(H * 0.52), W - 80, int(H * 0.6)], fill=(214, 170, 96))
    d.rectangle([80, int(H * 0.6), W - 80, int(H * 0.64)], fill=(160, 118, 66))
    for x in (160, W - 220) if palms else ():  # palms
        d.line([(x, int(H * 0.52)), (x - 10, int(H * 0.22))], fill=(120, 84, 48), width=12)
        for ang in range(-60, 70, 30):
            ex, ey = x - 10 + math.sin(math.radians(ang)) * 90, int(H * 0.22) + 40 - math.cos(math.radians(ang)) * 30
            d.line([(x - 10, int(H * 0.22)), (ex, ey)], fill=(70, 140, 70), width=12)
    return _vignette(img, 0.3)


def _plain() -> Image.Image:
    """A white void with a thin floor line, for props, money and gags."""
    img = Image.new("RGB", (W, H), (250, 249, 244))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(H * 0.86), W, H], fill=(236, 232, 222))
    d.line([(0, int(H * 0.86)), (W, int(H * 0.86))], fill=(205, 198, 184), width=4)
    return img


def _sea() -> Image.Image:
    img = _gradient((168, 214, 238), (236, 246, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(H * 0.5), W, H], fill=(62, 128, 176))
    for k in range(9):
        y = int(H * 0.54) + k * 26
        for x in range(-40 + (k % 2) * 60, W, 120):
            d.arc([x, y, x + 80, y + 22], 200, 340, fill=(180, 220, 240), width=4)
    d.rectangle([0, int(H * 0.5) - 3, W, int(H * 0.5) + 3], fill=(236, 246, 250))
    return _vignette(img, 0.25)


_BACK = {"parchment": _parchment, "mountains": _mountains, "hall": _hall, "night": _night, "snow": _snow,
         "field": _field, "market": _market, "plain": _plain, "sea": _sea, "desert": lambda: _market(True)}
_back_cache: dict[str, Image.Image] = {}


def backdrop(kind: str) -> Image.Image:
    """Cached backdrop picture (1280x720 RGB)."""
    kind = kind if kind in _BACK else "parchment"
    if kind not in _back_cache:
        _back_cache[kind] = _BACK[kind]()
    return _back_cache[kind]


# ---------------------------------------------------------------- characters
def card_question(narration: str, title: str = "", limit: int = 70) -> str:
    """Line for a chapter card that has no `question`: the narration's last question, else its last sentence.
    Returns "" if that would only repeat the title."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", narration.strip()) if p.strip()]
    pick = next((p for p in reversed(parts) if p.endswith("?")), parts[-1] if parts else "")
    if len(pick) > limit or pick.lower().rstrip(".!? ") == title.lower().rstrip(".!? "):
        return ""
    return pick


class Cast:
    """Sprites for the video's own characters, each drawn from the script's description of it."""

    def __init__(self, work: Path, characters: list[dict] | None = None, look_seed: str = "") -> None:
        self.look_seed = look_seed  # per video: unspecified face parts differ between stories, not between scenes
        # characters the script describes (name, gender, age, clothing, props ...): drawn from those attributes
        self.chars = {str(c.get("name", "")).strip().lower(): c for c in characters or []
                      if isinstance(c, dict) and str(c.get("name", "")).strip()}
        self._cs: dict[tuple, Image.Image] = {}

    def extra(self, side: int, i: int, color: str, px: int, t: float, talking: bool = False) -> Image.Image:
        """A crowd member: a small figure in a side's colour, drawn like any other character (blinks, mouth)."""
        px = int(round(px))
        n = i % 4
        spec = {"name": f"extra {side}-{n}", "role": "soldier", "clothing": {"type": "tunic", "color": color},
                "headwear": ("helmet", "cap", "hat", "hood")[n], "build": ("average", "stocky", "slim", "broad")[n]}
        return self._from_spec(spec, px, blink(t, i + 7 * side), talking, wardrobe.DEFAULT)

    def described(self, who: str) -> dict:
        """The script's own description of this character.

        A name that is not in the script's list is drawn from its own words, never mapped to a fixed cast
        member (there is none): "Mir Jafar" or "the mapmaker" get a person of their own."""
        low = (who or cast.GENERIC).strip().lower()
        found = self.chars.get(low)
        if found is None and low:  # "mapmaker" <-> "Mapmaker Odo": one name contains the other
            found = next((c for k, c in self.chars.items() if low in k or k in low), None)
        if found is None:
            found = {"name": who or cast.GENERIC, "role": who or cast.GENERIC}
        return found

    def _from_spec(self, spec: dict, px: int, closed: bool, talking: bool, era: str) -> Image.Image:
        key = (str(spec.get("name", "")).lower(), px, closed, talking, era)
        if key not in self._cs:
            spec = {**spec, "look_seed": self.look_seed}
            self._cs[key] = figures.draw(spec, px, closed, talking, figures.ERA_STYLE.get(era))
        return self._cs[key]

    def sprite(self, who: str, px: int, t: float, i: int, talking: bool, silhouette: bool = False,
               era: str = wardrobe.DEFAULT) -> Image.Image:
        """The character as an RGBA picture `px` wide; eyes blink, the mouth follows `talking`."""
        px = int(round(px))
        img = self._from_spec(self.described(who), px, blink(t, i), talking, era)
        if silhouette:
            solid = Image.new("RGBA", img.size, (18, 14, 28, 255))
            img = Image.composite(solid, Image.new("RGBA", img.size, (0, 0, 0, 0)), img.getchannel("A"))
        return img


def paste(img: Image.Image, sprite: Image.Image, cx: float, bottom: float) -> None:
    """Paste an RGBA sprite centred on cx with its feet line (84% down the 400px canvas) at `bottom`."""
    x = int(cx - sprite.width / 2)
    y = int(bottom - sprite.height * 0.94)
    img.paste(sprite, (x, y), sprite)


def envelope(audio: Path | None, n_frames: int) -> list[float]:
    """Narration loudness per video frame, 0..1 (drives mouths). Without audio, a steady talking pattern."""
    if audio and Path(audio).exists():
        try:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
                                 capture_output=True, check=True, timeout=120).stdout
            x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            win = 8000 // FPS
            n = max(1, len(x) // win)
            rms = np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1))
            ref = float(np.percentile(rms, 90)) or 1.0
            e = np.clip(rms / ref, 0, 1)
            e = np.pad(e, (0, max(0, n_frames - len(e))))[:n_frames]
            return [float(v) for v in e]
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
    return [0.5 + 0.5 * math.sin(i * 1.7) for i in range(n_frames)]


# ---------------------------------------------------------------- drawing helpers
def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return [*lines, cur] if cur else lines


def shadowed_box(img: Image.Image, box: tuple[int, int, int, int], fill: tuple, outline: tuple = INK,
                 radius: int = 22, width: int = 4, alpha: int = 255) -> None:
    """Rounded card with a soft drop shadow (composited so the alpha is honoured)."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x0 + 6, y0 + 8, x1 + 6, y1 + 8], radius, fill=(0, 0, 0, 70))
    d.rounded_rectangle(box, radius, fill=(*fill, alpha), outline=(*outline, alpha), width=width)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def centered(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, f: ImageFont.FreeTypeFont,
             fill: tuple = INK, stroke: tuple | None = None, sw: int = 0) -> None:
    d.text(xy, text, font=f, fill=fill, anchor="mm", stroke_width=sw, stroke_fill=stroke or fill)


def bubble(img: Image.Image, text: str, cx: float, tail_y: float, alpha: float = 1.0) -> None:
    """Speech bubble whose tail points down at (cx, tail_y)."""
    f = font(34, serif=False)
    lines = wrap(text, f, 340)
    w = int(max(f.getlength(x) for x in lines)) + 44
    h = len(lines) * 44 + 28
    x0 = int(min(max(cx - w / 2, 30), W - w - 30))
    y0 = int(tail_y - 46 - h)
    a = int(255 * alpha)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x0 + 5, y0 + 7, x0 + w + 5, y0 + h + 7], 26, fill=(0, 0, 0, int(60 * alpha)))
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], 26, fill=(255, 255, 255, a), outline=(*INK, a), width=4)
    tx = min(max(cx, x0 + 40), x0 + w - 40)
    d.polygon([(tx - 16, y0 + h - 2), (tx + 16, y0 + h - 2), (cx, tail_y - 6)], fill=(255, 255, 255, a), outline=(*INK, a))
    d.line([(tx - 16, y0 + h), (tx + 16, y0 + h)], fill=(255, 255, 255, a), width=6)
    for k, ln in enumerate(lines):
        d.text((x0 + w / 2, y0 + 14 + 22 + k * 44), ln, font=f, fill=(*INK, a), anchor="mm")
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def banner(img: Image.Image, text: str, cy: int, sub: str = "", width: int = 880) -> None:
    """Title banner across the top of a scene. A long title shrinks, then wraps to two lines, so it is never cut off."""
    size = 56
    while size > 34 and font(size).getlength(text) > width - 60:
        size -= 4
    lines = wrap(text, font(size), width - 60)[:2]
    extra = (len(lines) - 1) * (size + 6)
    box = (int((W - width) / 2), cy - 52 - extra // 2, int((W + width) / 2), cy + (86 if sub else 52) + extra // 2 + extra % 2)
    shadowed_box(img, box, (252, 244, 222), outline=WOOD, radius=18, width=5)
    d = ImageDraw.Draw(img)
    for k, ln in enumerate(lines):
        centered(d, (W / 2, cy - extra // 2 + k * (size + 6)), ln, font(size))
    if sub:
        centered(d, (W / 2, cy + 58 + extra // 2), sub, font(30, serif=False), fill=(110, 84, 52))


_DATE = re.compile(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December)"
                   r"(?: \d{4})?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|"
                   r"December) \d{4}\b")


# ---------------------------------------------------------------- the scene drawers
_BACK_WORDS = [("snow", ("snow", "snowy", "alps", "blizzard", "winter", "frost")),
               ("sea", ("ship", "fleet", "sail", "harbour", "harbor", "naval", "sea", "ocean", "shore", "shoreline", "coast",
                       "coastline", "wave")),
               ("field", ("battle", "plain", "river", "field", "march", "army", "legion", "camp", "valley", "elephant")),
               ("market", ("tax", "silver", "coin", "market", "trade", "merchant", "debt", "mercenary", "wage",
                           "square")),
               ("desert", ("carthage", "desert", "africa", "oasis", "sahara", "egypt")),
               ("mountains", ("mountain", "cliff", "peak")),
               ("night", ("night", "dark", "torch", "assassin", "secret", "plot", "plotter", "candlelit")),
               ("plain", ("contract", "treaty", "gag", "paper", "list", "number"))]


def guess_backdrop(text: str) -> str | None:
    """A backdrop that fits the place a skit is set in, or None for the default hall. Whole words only (so "pass" in
    "bypass" or "frozen" in "frozen with shock" never picks snow) and the group with most hits wins."""
    low = text.lower()
    best, top = None, 0
    for name, words in _BACK_WORDS:
        hits = sum(len(re.findall(r"\b" + w + r"s?\b", low)) for w in words)
        if hits > top:
            best, top = name, hits
    return best


def setting_words(seg: dict) -> str:
    """The words that say WHERE a scene happens: what the script says must be shown, the staging and the drawn
    objects. The narration is left out on purpose: it talks about the events, not the room (a ship sunk, a pope
    "frozen" with shock, a winter in another year), and picked sea or snow for skits that were not set there."""
    intent = seg.get("visual_intent") if isinstance(seg.get("visual_intent"), dict) else {}
    return " ".join(str(x) for x in [intent.get("must_show") or "", seg.get("staging") or "",
                                     *(seg.get("visual_keywords") or [])])


def diagram_layout(n: int) -> tuple[int, int]:
    """(box width, left edge of the first box) for `n` step boxes."""
    cw = min(300, (W - 200 - (n - 1) * 60) // n)
    return cw, (W - (cw * n + 60 * (n - 1))) // 2


def diagram_text(text: str, cw: int) -> tuple[int, list[str]]:
    """Font size and lines that show a whole step inside a box `cw` wide and 250 tall: the largest size at which no
    word is cut and at most four lines are needed (a long step gets a smaller font, never lost words)."""
    for size in (38, 34, 30, 27, 24):
        lines = wrap(text, font(size), cw - 36)
        if len(lines) <= (3 if size >= 34 else 4) and all(font(size).getlength(w) <= cw - 36 for w in text.split()):
            return size, lines
    return 22, wrap(text, font(22), cw - 36)[:5]


def _label_boxes(xy: list[tuple[float, float]], labels: list[str], f: ImageFont.FreeTypeFont) -> list[tuple]:
    """A box for each marker's name: above it, or higher / to either side when that would sit on an earlier name."""
    boxes: list[tuple] = []
    for (x, y), text in zip(xy, labels):
        bw = f.getlength(text) + 28
        # above the marker first (the marching army is drawn just below it), then below the army
        offs = [(dx, -92 - row * 58) for row in range(3) for dx in (-bw / 2, 30, -30 - bw, 40 + bw, -40 - 2 * bw)]
        offs += [(dx, 110 + row * 58) for row in range(2) for dx in (-bw / 2, 30, -30 - bw)]
        pick = None
        for dx, dy in offs:
            cx, cy = min(max(x + dx, 20), W - 20 - bw), min(max(y + dy, 140), H - 72)  # keep it in the picture
            if all(cx + bw + 6 <= b[0] or b[2] + 6 <= cx or cy + 58 <= b[1] or b[3] + 6 <= cy for b in boxes):
                pick = (cx, cy)
                break
        pick = pick or (min(max(x - bw / 2, 20), W - 20 - bw), min(max(y - 92, 140), H - 72))
        boxes.append((int(pick[0]), int(pick[1]), int(pick[0] + bw), int(pick[1] + 52)))
    return boxes


class Scene:
    """One segment's scene. `frame(t)` returns the picture at second t of `dur`."""

    def __init__(self, seg: dict, dur: float, cst: Cast, env: list[float], faction0: int = 0) -> None:
        self.seg, self.dur, self.cast, self.env = seg, dur, cst, env
        self.kind = seg.get("scene") or "title"
        self.data = seg.get("scene_data") or {}
        self.who = list(seg.get("cast") or [cast.GENERIC])
        self.speech = [s for s in (seg.get("speech") or []) if isinstance(s, dict)]
        guess = guess_backdrop(setting_words(seg)) if self.kind == "skit" else None
        given = str(self.data.get("backdrop") or "").lower()  # the script's own choice wins when it is a known one
        self.back = given if given in BACKDROPS else guess or DEFAULT_BACKDROP.get(self.kind, "parchment")
        self.faction0 = faction0
        self.starts = speech_audio.line_times(self.speech, dur, seg.get("lines_at"))
        self.line_env: list[list[float] | None] = []
        for sp in self.speech:  # a voiced line moves its speaker's mouth with its own audio
            a = sp.get("audio")
            self.line_env.append(envelope(Path(a), max(1, round(float(sp.get("seconds") or 1) * FPS)))
                                 if a and Path(a).exists() else None)
        self.crowd = bool(self.data.get("crowd"))  # only when the script asks; never guessed from the narration words
        e = str(seg.get("era") or "").lower()
        self.era = e if e in wardrobe.OUTFITS else wardrobe.DEFAULT

    def camera(self, t: float) -> tuple[float, float, float]:
        """(zoom, focus x, focus y) at second t: a wide shot with a slow push, then hard cuts to a close-up of whoever
        is speaking (the reference videos cut between wide and close angles every few seconds)."""
        wide = (1.0 + 0.04 * (t / max(self.dur, 0.1)), 0.5, 0.5)
        if self.kind != "skit" or self.dur < 5.5:
            return wide
        shot = 4.5
        k = int(t // shot)
        if k % 2 == 0:
            return wide
        who = self.who[:4] or [cast.GENERIC]
        n = len(who)
        act = next((k for k in range(len(self.speech) - 1, -1, -1) if self._line_start(k) <= t), None)
        idx = 0
        if self.kind == "skit":
            if act is not None:
                sp = str(self.speech[act].get("who", "")).lower()
                idx = next((i for i, w in enumerate(who) if w.lower() == sp), k // 2 % n)
            else:
                idx = (k // 2) % n
            fx = (idx + 1) / (n + 1)
        else:
            fx = 0.75
        local = (t - k * shot) / shot
        return 1.3 + 0.05 * local, fx, 0.44

    def mouth(self, t: float, speaking: bool = True) -> bool:
        i = min(len(self.env) - 1, int(t * FPS))
        return speaking and bool(self.env) and self.env[i] > 0.28 and t < self.dur - 0.25

    def actor(self, img: Image.Image, who: str, cx: float, bottom: float, px: int, t: float, i: int, talking: bool,
              enter: float = 0.0, silhouette: bool = False) -> None:
        rise = (1 - ease((t - enter) / 0.5)) * 160 if t >= enter else 400
        bob = math.sin((t + i * 0.6) * 2.4) * 4 if t > enter + 0.5 else 0
        if talking and t > enter + 0.5:  # a little hop on every syllable-ish burst
            bob -= 5 * abs(math.sin(t * 11 + i))
        spr = self.cast.sprite(who, px, t, i, talking, silhouette, self.era)
        paste(img, spr, cx, bottom + rise + bob)

    def frame(self, t: float) -> Image.Image:
        fn = getattr(self, f"_{self.kind}", self._title)
        img = backdrop(self.back).copy()
        fn(img, t)
        return img

    def _lectern(self, img: Image.Image, t: float) -> None:
        """Older scripts used a host-at-a-lectern scene; it is now a plain title card (there is no host)."""
        self._title(img, t)

    # -- skit: two to four characters with speech bubbles
    def _crowd(self, img: Image.Image, t: float) -> None:
        """Two rows of small extras behind the speakers: our side on the left, the other side on the right."""
        rng = random.Random(len(str(self.seg.get("narration", ""))) + 11)
        count = int(self.data.get("crowd") or 14)
        for row, (bottom, px) in enumerate(((600, 150), (630, 190))):
            for i in range(count // 2):
                side = 0 if i % 2 == 0 else 1
                x = (W * (i + 0.5) / (count // 2)) + rng.randint(-26, 26)
                col = cast.faction_color(self.faction0 + side)
                bob = math.sin(t * 2.2 + i * 1.3 + row) * 3
                spr = self.cast.extra(side, i + row * 3, col, px, t, int(t * 6 + i) % 5 == 0)
                paste(img, spr, x, bottom + bob)

    def _skit(self, img: Image.Image, t: float) -> None:
        who = self.who[:4] or [cast.GENERIC]
        n = len(who)
        if self.crowd:
            self._crowd(img, t)
        for i, w in enumerate(who):
            cx = W * (i + 1) / (n + 1)
            lines = [k for k, s in enumerate(self.speech) if str(s.get("who", "")).lower() == w.lower()
                     ]
            active = self._active_line(t)
            talk = active is not None and active in lines and self._line_mouth(active, t)
            self.actor(img, w, cx, 640, 430 if n <= 2 else 340, t, i, talk,
                       enter=0.1 * i)
        act = self._active_line(t)
        for k, s in enumerate(self.speech):
            start = self._line_start(k)
            if t < start:
                continue
            # a bubble stays until the next line starts, so the viewer can finish reading
            nxt = self._line_start(k + 1) if k + 1 < len(self.speech) else self.dur + 1
            if t >= nxt:
                continue
            idx = next((i for i, w in enumerate(who) if w.lower() == str(s.get("who", "")).lower()), k % n)
            cx = W * (idx + 1) / (n + 1)
            bubble(img, str(s.get("text", "")), cx, 640 - (430 if n <= 2 else 340) * 0.78, ease((t - start) / 0.25))
        _ = act

    def _line_start(self, k: int) -> float:
        if k < len(self.starts):
            return self.starts[k]
        return self.dur + 1

    def _line_end(self, k: int) -> float:
        sec = float(self.speech[k].get("seconds") or 0)
        return self._line_start(k) + (sec if sec else 2.4)

    def _active_line(self, t: float) -> int | None:
        for k in range(len(self.speech)):
            if self._line_start(k) <= t < self._line_end(k):
                return k
        return None

    def _line_mouth(self, k: int, t: float) -> bool:
        """Is the speaker of line k mid-syllable at second t (audio loudness when the line is voiced)?"""
        env = self.line_env[k] if k < len(self.line_env) else None
        if env is None:
            return int(t * 7 + k) % 2 == 0
        i = int((t - self._line_start(k)) * FPS)
        return 0 <= i < len(env) and env[i] > 0.28

    # -- map: a schematic western-Mediterranean map with a growing route
    def _map(self, img: Image.Image, t: float) -> None:
        region = maps.pick_region(self.data, str(self.seg.get("narration", "")))
        if region is None:
            img.paste(_territories(self.faction0))
            pts = self.data.get("points") or []
        else:  # a real-place map: outlines and positions come from studio/history/maps.py, drawn as approximate
            img.paste(_geo_base(region))
            pts = maps.resolve_points(region, self.data.get("points") or [])
            d = ImageDraw.Draw(img)
            marks = [(p["x"] * (W - 160) + 80, p["y"] * (H - 220) + 130) for p in pts]
            for name, (lon, lat) in maps.REGIONS[region]["labels"].items():  # real names, clear of the markers and title
                x, y = (v * k for v, k in zip(maps.project(region, lon, lat), (W, H)))
                half = font(30, False).getlength(name) / 2 + 10
                x = min(max(x, half), W - half)  # a name near the border stays whole
                if y > 150 and all(abs(x - mx) > 190 or abs(y - my) > 110 for mx, my in marks):
                    centered(d, (x, y), name, font(30, False), fill=(250, 246, 230), stroke=(30, 36, 50), sw=3)
        d = ImageDraw.Draw(img)
        centered(d, (W - 190, H - 22), "Approximate map", font(24, False), fill=(235, 240, 245), stroke=(20, 40, 70), sw=2)
        n = len(pts)
        if n:
            prog = min(1.0, max(0.0, (t - 0.4) / max(1.0, self.dur * 0.72))) * (n - 1 if n > 1 else 1)
            xy = [(p["x"] * (W - 160) + 80, p["y"] * (H - 220) + 130) for p in pts]
            # route: dashed line up to `prog`
            for k in range(min(n - 1, int(prog) + 1)):
                a, b = xy[k], xy[k + 1]
                frac = 1.0 if k < int(prog) else prog - int(prog)
                _dashed(d, a, (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac), RED, 9)
                if frac > 0.02:
                    _arrow_head(d, a, (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac), RED)
            boxes = _label_boxes(xy, [str(p.get("label", "")) for p in pts], font(36))
            shown: list[int] = []  # names are drawn last, on top of the marching army
            for k, (x, y) in enumerate(xy):
                if k > prog + 0.05:
                    break
                col = cast.faction_color(self.faction0 + (0 if k < n - 1 else 1))
                pop = ease((prog - k + 0.3) / 0.4)
                r = int(16 + 6 * pop)
                d.ellipse([x - r, y - r, x + r, y + r], fill=hex_rgb(col), outline=INK, width=4)
                shown.append(k)
            if n > 1:  # an army marches at the head of the route, with a troop counter that counts up
                k0 = min(n - 2, int(prog))
                fr = min(1.0, prog - k0)
                hx = xy[k0][0] + (xy[k0 + 1][0] - xy[k0][0]) * fr
                hy = xy[k0][1] + (xy[k0 + 1][1] - xy[k0][1]) * fr
                col = cast.faction_color(self.faction0)
                for j in range(4):
                    bob = abs(math.sin(t * 7 + j)) * 6
                    paste(img, self.cast.extra(0, j, col, 96, t), hx + (j - 1.5) * 26, hy + 34 + (j % 2) * 10 - bob)
                troops = int(self.data.get("troops") or 0)
                if troops:
                    label = f"{int(troops * ease(min(1.0, prog / max(1, n - 1)))):,}"
                    shadowed_box(img, (int(hx - 86), int(hy + 46), int(hx + 86), int(hy + 92)), (252, 244, 222),
                                 outline=WOOD, radius=12, width=4)
                    centered(ImageDraw.Draw(img), (hx, hy + 69), label, font(30, False))
                d = ImageDraw.Draw(img)
            for k in shown:
                bx = boxes[k]
                shadowed_box(img, bx, (252, 244, 222), outline=WOOD, radius=14, width=4)
                d = ImageDraw.Draw(img)
                centered(d, ((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2), str(pts[k].get("label", "")), font(36))
            ff_, ft = self.data.get("flag_from"), self.data.get("flag_to")
            if ff_ and prog >= 0:
                _flag(d, xy[0][0] - 70, xy[0][1] + 40, cast.faction_color(self.faction0), str(ff_))
            if ft and prog >= n - 1.2:
                _flag(d, xy[-1][0] + 70, xy[-1][1] + 40, cast.faction_color(self.faction0 + 1), str(ft))
        title = self.data.get("title")
        if title:
            banner(img, str(title), 78, width=700)
        if self.who:
            self.actor(img, self.who[0], 1160, 650, 260, t, 0, False)  # the narrator is not this figure

    # -- diagram: numbered steps appear one after another
    def _diagram(self, img: Image.Image, t: float) -> None:
        steps = autoscene.steps_for(str(self.seg.get("narration", "")), self.data.get("steps")) \
            or [str(self.data.get("title") or self.seg.get("chapter") or "How it worked")]
        n = len(steps)
        banner(img, str(self.data.get("title") or self.seg.get("chapter", "")), 90, width=760)
        cw, x0 = diagram_layout(n)
        for k, s in enumerate(steps):
            start = 0.7 + k * (self.dur * 0.6) / n
            if t < start:
                continue
            p = ease((t - start) / 0.4)
            x = x0 + k * (cw + 60)
            y = 250 + int((1 - p) * 40)
            shadowed_box(img, (x, y, x + cw, y + 250), (252, 244, 222), outline=WOOD, radius=24, width=6)
            d = ImageDraw.Draw(img)
            d.ellipse([x + cw / 2 - 34, y - 34, x + cw / 2 + 34, y + 34], fill=hex_rgb(cast.faction_color(k)), outline=INK, width=4)
            centered(d, (x + cw / 2, y), str(k + 1), font(44), fill=(255, 255, 255))
            size, lines = diagram_text(s, cw)
            for j, ln in enumerate(lines):
                centered(d, (x + cw / 2, y + 125 - (len(lines) - 1) * size * 0.65 + j * size * 1.3), ln, font(size))
            if k + 1 < n and t > start + 0.5:
                _arrow_head(d, (x + cw + 6, y + 125), (x + cw + 54, y + 125), INK)
            if self.data.get("disputed") and k == 1:
                d.ellipse([x + cw - 48, y - 24, x + cw + 12, y + 36], fill=(255, 214, 90), outline=INK, width=4)
                centered(d, (x + cw - 18, y + 6), "?", font(48), fill=INK)
        if self.data.get("disputed") and t > 2:
            centered(ImageDraw.Draw(img), (W / 2, 535), "Told by Livy. Historians dispute this.", font(34, False),
                     fill=(110, 84, 52))
        if self.who:  # standing below the step boxes (they end at y=500), not in front of the first one
            self.actor(img, self.who[0], 130, 740, 250, t, 0, False)  # the narrator is not this figure

    # -- calendar: days cross off one by one
    def _calendar(self, img: Image.Image, t: float) -> None:
        if self.data.get("days") in (None, ""):  # no count of days: one page showing the date the script talks about
            return self._date_page(img, t)
        days = max(1, min(int(self.data.get("days") or 7), 31))
        banner(img, str(self.data.get("title") or self.seg.get("chapter") or "Days"), 90,
               str(self.data.get("label") or ""), width=900)
        cols = 8 if days > 10 else days
        cw, gap = 112, 14
        x0 = (W - (cols * cw + (cols - 1) * gap)) // 2
        y0 = 250
        done = int(min(days, max(0.0, (t - 0.6) / max(1.0, self.dur * 0.75 - 0.6) * days)))
        for k in range(days):
            r, c = divmod(k, cols)
            x, y = x0 + c * (cw + gap), y0 + r * (cw + gap)
            crossed = k < done
            shadowed_box(img, (x, y, x + cw, y + cw), (252, 244, 222) if not crossed else (236, 220, 190),
                         outline=WOOD, radius=14, width=4)
            d = ImageDraw.Draw(img)
            if crossed:  # a thin cross behind the number: the day stays readable
                d.line([(x + 30, y + 30), (x + cw - 30, y + cw - 30)], fill=RED, width=5)
                d.line([(x + cw - 30, y + 30), (x + 30, y + cw - 30)], fill=RED, width=5)
            centered(d, (x + cw / 2, y + cw / 2), str(k + 1), font(46), fill=INK if not crossed else (120, 96, 64))
        q = self.data.get("question")  # a closing "?" only when the script asks for one
        if q and done >= days and t > self.dur * 0.78:
            s = ease((t - self.dur * 0.78) / 0.4)
            centered(ImageDraw.Draw(img), (W - 150, 600), str(q) if isinstance(q, str) else "?", font(int(40 + 130 * s)),
                     fill=RED, stroke=PAPER, sw=6)
        if self.who:
            self.actor(img, self.who[0], 120, 650, 250, t, 0, False)  # the narrator is not this figure

    def _date_page(self, img: Image.Image, t: float) -> None:
        """One calendar page with the date from the script (`label`, else a date in the narration, else the title)."""
        text = " ".join(str(self.seg.get(k) or "") for k in ("narration",))
        m = _DATE.search(text)
        date = str(self.data.get("label") or (m.group(0) if m else "") or self.data.get("title") or
                   self.seg.get("chapter") or "")
        title = str(self.data.get("title") or self.seg.get("chapter") or "")
        if date.lower() != title.lower():  # with no real date the card already carries the title: not twice
            banner(img, title, 90, width=900)
        rise = ease(t / 0.5)
        shadowed_box(img, (340, int(230 + 30 * (1 - rise)), 940, int(520 + 30 * (1 - rise))), (252, 244, 222),
                     outline=WOOD, radius=16, width=6)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([340, int(230 + 30 * (1 - rise)), 940, int(300 + 30 * (1 - rise))], 16, fill=RED)
        size = 84
        while size > 40 and font(size).getlength(date) > 520:
            size -= 6
        centered(d, (640, int(410 + 30 * (1 - rise))), date, font(size))
        if self.who:
            self.actor(img, self.who[0], 120, 650, 250, t, 0, False)  # the narrator is not this figure

    # -- easel: a list or short chart on an easel
    def _easel(self, img: Image.Image, t: float) -> None:
        items = [str(x) for x in (self.data.get("items") or [])][:6]
        if not items:  # nothing to write on the board: show a title card instead of a blank easel
            return self._title(img, t)
        d = ImageDraw.Draw(img)
        d.polygon([(470, 560), (520, 560), (640, 300), (600, 300)], fill=WOOD)
        d.polygon([(810, 560), (760, 560), (640, 300), (680, 300)], fill=WOOD)
        shadowed_box(img, (300, 120, 980, 500), (252, 244, 222), outline=WOOD, radius=12, width=8)
        d = ImageDraw.Draw(img)
        centered(d, (640, 175), str(self.data.get("title") or ""), font(46))
        for k, it in enumerate(items):
            if t > 0.5 + k * 0.7:
                d.ellipse([360, 238 + k * 44 - 8, 376, 238 + k * 44 + 8], fill=hex_rgb(cast.faction_color(k)))
                d.text((392, 238 + k * 44), it, font=font(32, False), fill=INK, anchor="lm")
        if self.who:
            self.actor(img, self.who[0], 1090, 650, 400, t, 0, False)  # the narrator is not this figure

    def _archive(self, img: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(img)
        shadowed_box(img, (330, 110, 950, 500), (255, 252, 244), outline=WOOD, radius=10, width=10)
        d = ImageDraw.Draw(img)
        src = self.data.get("image")
        if src and Path(src).exists():
            pic = Image.open(src).convert("RGB").resize((560, 330))
            img.paste(pic, (360, 140))
        else:
            d.rectangle([360, 140, 920, 470], fill=(206, 190, 150))
            centered(d, (640, 305), "archive picture", font(40, False), fill=(120, 100, 70))
        centered(d, (640, 540), str(self.data.get("title") or ""), font(36, False), fill=(110, 84, 52))
        if self.who:
            self.actor(img, self.who[0], 1100, 650, 360, t, 0, False)  # the narrator is not this figure

    def _silhouette(self, img: Image.Image, t: float) -> None:
        push = 40 * min(1.0, t / max(self.dur, 1.0))  # a slow push-in so a long silhouette is never a still
        self.actor(img, self.who[0] if self.who else cast.GENERIC, 640, 700 + push, 520 + 2 * push, t, 0, False,
                   silhouette=True)
        d = ImageDraw.Draw(img)
        for k, ln in enumerate(wrap(str(self.data.get("title") or ""), font(48), 1100)[:3]):
            centered(d, (640, 100 + k * 62), ln, font(48), fill=(255, 246, 214))

    def _title(self, img: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(img)
        text = str(self.data.get("title") or self.seg.get("chapter", ""))
        size = 84
        while size > 48 and len(wrap(text, font(size), 1100)) > 2:  # a long title gets smaller, then two lines
            size -= 6
        lines = wrap(text, font(size), 1100)[:2]
        for k, ln in enumerate(lines):
            centered(d, (640, 300 - (len(lines) - 1) * size * 0.55 + k * size * 1.1), ln, font(size),
                     fill=(255, 246, 214), stroke=(20, 16, 40), sw=4)
        if self.who:
            self.actor(img, self.who[0], 640, 700, 360, t, 0, False)  # the narrator is not this figure


# ---------------------------------------------------------------- map base and small shapes
_MAP: Image.Image | None = None


def _smooth(pts: list[tuple[float, float]], k: int = 3) -> list[tuple[float, float]]:
    """Chaikin corner cutting: rounds a coastline drawn with a few points."""
    for _ in range(k):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        pts = out
    return pts


_REGIONS: dict[str, list[tuple[float, float]]] = {
    "iberia": [(0.03, 0.55), (0.06, 0.44), (0.16, 0.42), (0.26, 0.45), (0.27, 0.56), (0.22, 0.72), (0.12, 0.78), (0.05, 0.72)],
    "gaul": [(0.20, 0.44), (0.24, 0.20), (0.40, 0.08), (0.62, 0.10), (0.70, 0.30), (0.52, 0.36), (0.36, 0.50), (0.27, 0.54)],
    "italy": [(0.56, 0.34), (0.74, 0.28), (0.86, 0.42), (0.88, 0.58), (0.96, 0.70), (0.90, 0.80), (0.82, 0.66), (0.70, 0.54), (0.60, 0.42)],
    "africa": [(0.04, 0.92), (0.22, 0.84), (0.50, 0.86), (0.70, 0.88), (0.90, 0.90), (0.96, 1.02), (0.02, 1.02)],
    "sardinia": [(0.42, 0.62), (0.47, 0.60), (0.48, 0.68), (0.44, 0.72)],
}
_TERRITORY_SIDE = {"italy": 0, "iberia": 1, "africa": 1}  # which faction holds a region (others stay neutral)
_noise_cache: dict[int, np.ndarray] = {}


def _fractal(seed: int, w: int, h: int) -> np.ndarray:
    """Soft 0..1 noise (three octaves of smoothed random grids) for terrain texture."""
    rng = np.random.default_rng(seed)
    total = np.zeros((h, w), dtype=np.float32)
    amp, norm = 1.0, 0.0
    for cells in (6, 14, 34):
        g = (rng.random((cells, max(2, cells * w // h))) * 255).astype("uint8")
        total += amp * np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), dtype=np.float32) / 255.0
        norm += amp
        amp *= 0.5
    return total / norm


def _region_mask(names: list[str], S: int) -> Image.Image:
    m = Image.new("L", (W * S, H * S), 0)
    d = ImageDraw.Draw(m)
    for n in names:
        d.polygon(_smooth([(x * W * S, y * H * S) for x, y in _REGIONS[n]]), fill=255)
    return m


def _map_base() -> Image.Image:
    """Western Mediterranean drawn like a satellite map: textured sea and land, coast lines, snow-capped Alps."""
    global _MAP
    if _MAP is not None:
        return _MAP
    S = 2
    w, h = W * S, H * S
    land = _region_mask(list(_REGIONS), S)
    n1, n2 = _fractal(5, w, h), _fractal(9, w, h)
    sea = np.stack([18 + 26 * n1, 52 + 40 * n1, 96 + 52 * n1], axis=-1)
    t = n2[..., None]
    low, mid, high = np.array([86, 124, 66]), np.array([150, 138, 88]), np.array([118, 96, 72])
    ground = np.where(t < 0.5, low + (mid - low) * (t / 0.5), mid + (high - mid) * ((t - 0.5) / 0.5))
    ground = ground * (0.86 + 0.28 * n1[..., None])
    mask = np.asarray(land, dtype=np.float32)[..., None] / 255.0
    img = Image.fromarray(np.clip(sea * (1 - mask) + ground * mask, 0, 255).astype("uint8"), "RGB")
    d = ImageDraw.Draw(img)
    for name in _REGIONS:  # a pale shoreline
        pts = _smooth([(x * w, y * h) for x, y in _REGIONS[name]])
        d.line([*pts, pts[0]], fill=(196, 214, 204), width=4 * S)
    for k in range(7):  # the Alps: a row of snow-capped peaks
        x, y = (0.5 + k * 0.022) * w, (0.285 + math.sin(k * 0.9) * 0.012 + k * 0.008) * h
        s = 46 * S // 2 + (k % 3) * 6
        d.polygon([(x - s, y + s), (x, y - s), (x + s, y + s)], fill=(132, 118, 104), outline=(70, 60, 50))
        d.polygon([(x - s * 0.36, y - s * 0.28), (x, y - s), (x + s * 0.36, y - s * 0.28)], fill=(248, 250, 255))
    _MAP = _vignette(img.resize((W, H), Image.LANCZOS), 0.3)
    return _MAP


_geo_cache: dict[str, Image.Image] = {}


def _geo_base(region: str) -> Image.Image:
    """A coarse map of a real region (see maps.py): textured sea and land, shoreline, and the region's real names."""
    if region in _geo_cache:
        return _geo_cache[region]
    S = 2
    w, h = W * S, H * S
    land = Image.new("L", (w, h), 0)
    ld = ImageDraw.Draw(land)
    polys = [[maps.project(region, *pt) for pt in poly] for poly in maps.REGIONS[region]["land"]]
    for poly in polys:
        ld.polygon(_smooth([(x * w, y * h) for x, y in poly], 2), fill=255)
    n1, n2 = _fractal(5, w, h), _fractal(9, w, h)
    sea = np.stack([18 + 26 * n1, 52 + 40 * n1, 96 + 52 * n1], axis=-1)
    tt = n2[..., None]
    low, mid, high = np.array([86, 124, 66]), np.array([150, 138, 88]), np.array([118, 96, 72])
    ground = np.where(tt < 0.5, low + (mid - low) * (tt / 0.5), mid + (high - mid) * ((tt - 0.5) / 0.5))
    ground = ground * (0.86 + 0.28 * n1[..., None])
    mask = np.asarray(land, dtype=np.float32)[..., None] / 255.0
    img = Image.fromarray(np.clip(sea * (1 - mask) + ground * mask, 0, 255).astype("uint8"), "RGB")
    d = ImageDraw.Draw(img)
    for poly in polys:
        pts = _smooth([(x * w, y * h) for x, y in poly], 2)
        d.line([*pts, pts[0]], fill=(196, 214, 204), width=4 * S)
    out = _vignette(img.resize((W, H), Image.LANCZOS), 0.3)
    _geo_cache[region] = out
    return out


_terr_cache: dict[int, Image.Image] = {}


def _territories(faction0: int) -> Image.Image:
    """Base map with each side's territory tinted in its faction colour and outlined in white (like the references)."""
    if faction0 in _terr_cache:
        return _terr_cache[faction0]
    S = 2
    base = _map_base().resize((W * S, H * S), Image.LANCZOS).convert("RGBA")
    for name, side in _TERRITORY_SIDE.items():
        col = hex_rgb(cast.faction_color(faction0 + side))
        m = _region_mask([name], S)
        tint = Image.new("RGBA", base.size, (*col, 0))
        tint.putalpha(m.point(lambda v: 118 if v else 0))
        base = Image.alpha_composite(base, tint)
        edge = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m.filter(ImageFilter.MinFilter(5)))
        white = Image.new("RGBA", base.size, (255, 255, 255, 0))
        white.putalpha(edge)
        base = Image.alpha_composite(base, white)
    out = base.convert("RGB").resize((W, H), Image.LANCZOS)
    _terr_cache[faction0] = out
    return out


def _dashed(d: ImageDraw.ImageDraw, a: tuple, b: tuple, col: tuple, width: int) -> None:
    length = math.dist(a, b)
    if length < 1:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    pos = 0.0
    while pos < length:
        e = min(length, pos + 22)
        d.line([(a[0] + ux * pos, a[1] + uy * pos), (a[0] + ux * e, a[1] + uy * e)], fill=col, width=width)
        pos += 36


def _arrow_head(d: ImageDraw.ImageDraw, a: tuple, b: tuple, col: tuple) -> None:
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    p = [(b[0] + math.cos(ang) * 18, b[1] + math.sin(ang) * 18),
         (b[0] + math.cos(ang + 2.5) * 20, b[1] + math.sin(ang + 2.5) * 20),
         (b[0] + math.cos(ang - 2.5) * 20, b[1] + math.sin(ang - 2.5) * 20)]
    d.polygon(p, fill=col)


def _flag(d: ImageDraw.ImageDraw, x: float, y: float, color: str, text: str) -> None:
    d.rectangle([x - 3, y - 70, x + 3, y + 10], fill=WOOD)
    d.polygon([(x + 3, y - 70), (x + 92, y - 56), (x + 3, y - 36)], fill=hex_rgb(color), outline=INK)
    d.text((x + 8, y + 24), text, font=font(26, False), fill=INK, anchor="lm")


# ---------------------------------------------------------------- the entry point
_CODE_STAMP = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:8]  # drawing code changed -> redraw


def look_seed(pkg: dict, project_dir: Path) -> str:
    """What makes this video's characters differ from the same names in another video: its topic and project."""
    return f"{pkg.get('topic', '')}|{Path(project_dir).name}"


def fingerprint(seg: dict, dur: float, audio: Path | None, characters: list[dict] | None = None,
                seed: str = "") -> str:
    """Hash of everything that decides how a scene looks (re-render only when it changes)."""
    keys = {k: seg.get(k) for k in ("scene", "scene_data", "cast", "speech", "chapter", "era")}
    names = {str(n).lower() for n in seg.get("cast") or []} | {str(x.get("who", "")).lower()
                                                               for x in seg.get("speech") or [] if isinstance(x, dict)}
    keys["characters"] = [c for c in characters or [] if str(c.get("name", "")).lower() in names]
    pf = ff.profile()
    keys.update(look=seed, size=[pf.w, pf.h, pf.fps], dur=round(dur, 2),
                audio=audio.stat().st_size if audio and Path(audio).exists() else 0, code=_CODE_STAMP)
    return hashlib.sha1(json.dumps(keys, sort_keys=True, default=str).encode()).hexdigest()[:12]


def render_scene(seg: dict, dur: float, out: Path, work: Path, audio: Path | None = None, faction0: int = 0,
                 cst: Cast | None = None, characters: list[dict] | None = None) -> Path:
    """Render one cast scene to `out` (silent H.264 at the video profile size and frame rate, `dur` seconds). Reuses an identical earlier clip."""
    ff.ensure_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)  # a new project has no cast/ folder yet
    stamp = out.with_suffix(".stamp")
    fp = fingerprint(seg, dur, audio, characters, cst.look_seed if cst else "")
    if out.exists() and stamp.exists() and stamp.read_text() == fp:
        return out
    pf = ff.profile()
    ow, oh, fps = pf.w, pf.h, pf.fps  # drawn once, then resampled once straight to the video size and frame rate
    n = max(1, round(dur * fps))
    cst = cst or Cast(work, characters)
    scene = Scene(seg, dur, cst, envelope(audio, round(dur * FPS) + 1), faction0)
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}", "-r", str(fps), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
           str(out)]
    proc = ff.popen_raw(cmd)
    try:
        for f in range(n):
            t = f / fps
            img = scene.frame(t)
            z, fx, fy = scene.camera(t) if scene.kind != "map" else (1.0, 0.5, 0.5)
            cw, ch = W / max(z, 1.0), H / max(z, 1.0)
            x0 = min(max(fx * W - cw / 2, 0), W - cw)
            y0 = min(max(fy * H - ch / 2, 0), H - ch)
            img = img.resize((ow, oh), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
            proc.stdin.write(img.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise StudioError("ffmpeg failed while drawing a cast scene.", err.strip()[-600:],
                              "Check ffmpeg is installed and re-run `visuals --force`.")
    except BrokenPipeError as exc:
        raise StudioError("ffmpeg closed early while drawing a cast scene.", proc.stderr.read().decode()[-600:],
                          "Check ffmpeg is installed and re-run `visuals --force`.") from exc
    finally:
        if proc.poll() is None:
            proc.kill()
    stamp.write_text(fp)
    return out
