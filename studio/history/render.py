# ruff: noqa: E501  (drawing code)
"""History cast scene renderer: draws one segment's scene (lectern, skit, map, diagram, calendar, easel, title,
silhouette, archive) as an MP4 clip with the recurring cast acting in it.

Frames are drawn with Pillow (1280x720, 24 fps) and piped to ffmpeg. Characters are the SVG sprites from
`studio/history/cast.py` (blinking eyes, mouth driven by the narration loudness). The clip becomes the segment's
`scene_clip`, so `build` shows it as one continuous shot. Everything here is original art drawn in code.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

from studio.errors import StudioError
from studio.history import cast
from studio.kids.sprites import SpriteBank, blink
from studio.util import ffmpeg as ff

W, H, FPS = 1280, 720, 24
INK = (43, 43, 61)
PAPER = (239, 227, 200)
PAPER_DARK = (222, 205, 165)
WOOD = (122, 82, 51)
SEA = (176, 205, 210)
LAND = (222, 204, 160)
LAND_EDGE = (150, 122, 76)
RED = (192, 57, 43)
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BACKDROPS = ("parchment", "mountains", "hall", "night")
DEFAULT_BACKDROP = {"lectern": "parchment", "skit": "hall", "map": "parchment", "diagram": "parchment",
                    "easel": "parchment", "archive": "parchment", "calendar": "parchment", "silhouette": "night",
                    "title": "night"}
_fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    """Cached bold font (serif for titles, sans for labels); falls back to Pillow's default."""
    key = ("s" if serif else "n", size)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype(BOLD if serif else SANS, size)
        except OSError:
            _fonts[key] = ImageFont.load_default()
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


_BACK = {"parchment": _parchment, "mountains": _mountains, "hall": _hall, "night": _night}
_back_cache: dict[str, Image.Image] = {}


def backdrop(kind: str) -> Image.Image:
    """Cached backdrop picture (1280x720 RGB)."""
    kind = kind if kind in _BACK else "parchment"
    if kind not in _back_cache:
        _back_cache[kind] = _BACK[kind]()
    return _back_cache[kind]


# ---------------------------------------------------------------- characters
class Cast:
    """Sprites for the recurring roster plus the video's own historical figures (same faction colour all video)."""

    def __init__(self, work: Path) -> None:
        self.dir = work / "figures"
        self.dir.mkdir(parents=True, exist_ok=True)
        cast.export_roster(self.dir)
        self.figs: dict[str, str] = {}  # figure name -> file stem
        self.bank = SpriteBank(self.dir)
        self.ok = self.bank.enabled

    def key(self, who: str) -> str:
        """File stem for a roster id or a named historical figure (generated once, stable for the video)."""
        who = (who or "dusty").strip()
        low = who.lower()
        if low in cast.ROSTER:
            return low
        for cid, c in cast.ROSTER.items():  # "Captain Blunder" -> blunder
            if low == c["name"].lower():
                return cid
        if who not in self.figs:
            h = int(hashlib.sha1(who.encode()).hexdigest(), 16)
            stem = f"fig_{len(self.figs) + 1}"
            heads = [x for x in cast.HEADWEAR if x != "none"]
            props = [x for x in cast.PROPS if x != "none"]
            svg = cast.build_svg(cast.faction_color(len(self.figs)), heads[h % len(heads)],
                                 props[(h >> 8) % len(props)], who[:1])
            (self.dir / f"{stem}.svg").write_text(svg, encoding="utf-8")
            self.bank._svg.pop(stem, None)  # noqa: SLF001
            self.figs[who] = stem
        return self.figs[who]

    def sprite(self, who: str, px: int, t: float, i: int, talking: bool, silhouette: bool = False) -> Image.Image:
        """The character as an RGBA picture `px` wide; eyes blink, the mouth follows `talking`."""
        img = self.bank.get(self.key(who), px, eyes_closed=blink(t, i), mouth_open=talking) if self.ok else None
        if img is None:  # no cairosvg: a simple round fallback so the scene still reads
            img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse([px * 0.2, px * 0.1, px * 0.8, px * 0.7], fill=(242, 210, 177, 255))
            d.rounded_rectangle([px * 0.3, px * 0.55, px * 0.7, px * 0.95], 20, fill=(46, 125, 135, 255))
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
    """Title banner across the top of a scene."""
    box = (int((W - width) / 2), cy - 52, int((W + width) / 2), cy + (86 if sub else 52))
    shadowed_box(img, box, (252, 244, 222), outline=WOOD, radius=18, width=5)
    d = ImageDraw.Draw(img)
    centered(d, (W / 2, cy), text, font(56))
    if sub:
        centered(d, (W / 2, cy + 58), sub, font(30, serif=False), fill=(110, 84, 52))


# ---------------------------------------------------------------- the scene drawers
class Scene:
    """One segment's scene. `frame(t)` returns the picture at second t of `dur`."""

    def __init__(self, seg: dict, dur: float, cst: Cast, env: list[float], faction0: int = 0) -> None:
        self.seg, self.dur, self.cast, self.env = seg, dur, cst, env
        self.kind = seg.get("scene") or "title"
        self.data = seg.get("scene_data") or {}
        self.who = list(seg.get("cast") or ["quill"])
        self.speech = [s for s in (seg.get("speech") or []) if isinstance(s, dict)]
        kw = " ".join(str(k).lower() for k in seg.get("visual_keywords") or [])
        guess = "mountains" if self.kind == "skit" and any(w in kw for w in ("alps", "mountain", "snow")) else None
        self.back = self.data.get("backdrop") or guess or DEFAULT_BACKDROP.get(self.kind, "parchment")
        self.faction0 = faction0

    def mouth(self, t: float, speaking: bool = True) -> bool:
        i = min(len(self.env) - 1, int(t * FPS))
        return speaking and bool(self.env) and self.env[i] > 0.28 and t < self.dur - 0.25

    def actor(self, img: Image.Image, who: str, cx: float, bottom: float, px: int, t: float, i: int, talking: bool,
              enter: float = 0.0, silhouette: bool = False) -> None:
        rise = (1 - ease((t - enter) / 0.5)) * 160 if t >= enter else 400
        bob = math.sin((t + i * 0.6) * 2.4) * 4 if t > enter + 0.5 else 0
        if talking and t > enter + 0.5:  # a little hop on every syllable-ish burst
            bob -= 5 * abs(math.sin(t * 11 + i))
        spr = self.cast.sprite(who, px, t, i, talking, silhouette)
        paste(img, spr, cx, bottom + rise + bob)

    def frame(self, t: float) -> Image.Image:
        fn = getattr(self, f"_{self.kind}", self._title)
        img = backdrop(self.back).copy()
        fn(img, t)
        return img

    # -- lectern: host at a wooden lectern, chapter card on the left
    def _lectern(self, img: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(img)
        title, q = str(self.data.get("title") or self.seg.get("chapter", "")), str(self.data.get("question") or "")
        a = ease(t / 0.6)
        shadowed_box(img, (60, 170, 700, 470), (252, 244, 222), outline=WOOD, radius=20, width=6)
        d = ImageDraw.Draw(img)
        for k, ln in enumerate(wrap(title, font(58), 590)[:3]):
            centered(d, (380, 250 + k * 78 - (0 if a >= 1 else (1 - a) * 20)), ln, font(58))
        if q:
            d.line([(150, 372), (610, 372)], fill=WOOD, width=4)
            for k, ln in enumerate(wrap(q, font(34, False), 520)[:2]):
                centered(d, (380, 410 + k * 40), ln, font(34, False), fill=(110, 84, 52))
        host = self.who[0] if self.who else "quill"
        self.actor(img, host, 960, 545, 470, t, 0, self.mouth(t))
        d.polygon([(800, 545), (1120, 545), (1160, 640), (760, 640)], fill=WOOD)  # lectern front
        d.polygon([(780, 525), (1140, 525), (1120, 549), (800, 549)], fill=(158, 112, 72))
        d.rectangle([760, 632, 1160, 644], fill=(92, 60, 36))

    # -- skit: two to four characters with speech bubbles
    def _skit(self, img: Image.Image, t: float) -> None:
        who = self.who[:4] or ["dusty"]
        n = len(who)
        for i, w in enumerate(who):
            cx = W * (i + 1) / (n + 1)
            lines = [k for k, s in enumerate(self.speech) if str(s.get("who", "")).lower() == w.lower()
                     or cast.ROSTER.get(w, {}).get("name", "").lower() == str(s.get("who", "")).lower()]
            active = self._active_line(t)
            talk = active is not None and active in lines and int(t * 7 + i) % 2 == 0
            self.actor(img, w, cx, 640, 430 if n <= 2 else 340, t, i, talk or (not self.speech and self.mouth(t)),
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
            idx = next((i for i, w in enumerate(who) if w.lower() == str(s.get("who", "")).lower()
                        or cast.ROSTER.get(w, {}).get("name", "").lower() == str(s.get("who", "")).lower()), k % n)
            cx = W * (idx + 1) / (n + 1)
            bubble(img, str(s.get("text", "")), cx, 640 - (430 if n <= 2 else 340) * 0.78, ease((t - start) / 0.25))
        _ = act

    def _line_start(self, k: int) -> float:
        n = max(1, len(self.speech))
        return 0.5 + k * (self.dur - 1.2) / n

    def _active_line(self, t: float) -> int | None:
        for k in range(len(self.speech)):
            end = self._line_start(k + 1) if k + 1 < len(self.speech) else self.dur
            if self._line_start(k) <= t < min(end, self._line_start(k) + 2.4):
                return k
        return None

    # -- map: a schematic western-Mediterranean map with a growing route
    def _map(self, img: Image.Image, t: float) -> None:
        base = _map_base()
        img.paste(base)
        d = ImageDraw.Draw(img)
        pts = self.data.get("points") or []
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
            for k, (x, y) in enumerate(xy):
                if k > prog + 0.05:
                    break
                col = cast.faction_color(self.faction0 + (0 if k < n - 1 else 1))
                pop = ease((prog - k + 0.3) / 0.4)
                r = int(16 + 6 * pop)
                d.ellipse([x - r, y - r, x + r, y + r], fill=hex_rgb(col), outline=INK, width=4)
                label = str(pts[k].get("label", ""))
                f = font(36)
                bw = f.getlength(label) + 28
                shadowed_box(img, (int(x - bw / 2), int(y - 92), int(x + bw / 2), int(y - 40)), (252, 244, 222),
                             outline=WOOD, radius=14, width=4)
                d = ImageDraw.Draw(img)
                centered(d, (x, y - 66), label, f)
            ff_, ft = self.data.get("flag_from"), self.data.get("flag_to")
            if ff_ and prog >= 0:
                _flag(d, xy[0][0] - 70, xy[0][1] + 40, cast.faction_color(self.faction0), str(ff_))
            if ft and prog >= n - 1.2:
                _flag(d, xy[-1][0] + 70, xy[-1][1] + 40, cast.faction_color(self.faction0 + 1), str(ft))
        title = self.data.get("title")
        if title:
            banner(img, str(title), 78, width=700)
        if self.who:
            self.actor(img, self.who[0], 1160, 650, 260, t, 0, self.mouth(t))

    # -- diagram: numbered steps appear one after another
    def _diagram(self, img: Image.Image, t: float) -> None:
        steps = [str(s) for s in (self.data.get("steps") or ["Step one", "Step two", "Step three"])][:5]
        n = len(steps)
        banner(img, str(self.data.get("title") or self.seg.get("chapter", "")), 90, width=760)
        cw = min(300, (W - 200 - (n - 1) * 60) // n)
        x0 = (W - (cw * n + 60 * (n - 1))) // 2
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
            for j, ln in enumerate(wrap(s, font(38), cw - 40)[:3]):
                centered(d, (x + cw / 2, y + 100 + j * 50), ln, font(38))
            if k + 1 < n and t > start + 0.5:
                _arrow_head(d, (x + cw + 6, y + 125), (x + cw + 54, y + 125), INK)
            if self.data.get("disputed") and k == 1:
                d.ellipse([x + cw - 48, y - 24, x + cw + 12, y + 36], fill=(255, 214, 90), outline=INK, width=4)
                centered(d, (x + cw - 18, y + 6), "?", font(48), fill=INK)
        if self.data.get("disputed") and t > 2:
            centered(ImageDraw.Draw(img), (W / 2, 535), "Told by Livy. Historians dispute this.", font(34, False),
                     fill=(110, 84, 52))
        if self.who:
            self.actor(img, self.who[0], 130, 650, 250, t, 0, self.mouth(t))

    # -- calendar: days cross off one by one
    def _calendar(self, img: Image.Image, t: float) -> None:
        days = max(1, min(int(self.data.get("days", 7)), 31))
        banner(img, str(self.data.get("title") or "Days"), 90, str(self.data.get("label") or ""), width=700)
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
            centered(d, (x + cw / 2, y + cw / 2), str(k + 1), font(46), fill=INK if not crossed else (150, 128, 96))
            if crossed:
                d.line([(x + 14, y + 14), (x + cw - 14, y + cw - 14)], fill=RED, width=9)
                d.line([(x + cw - 14, y + 14), (x + 14, y + cw - 14)], fill=RED, width=9)
        if done >= days and t > self.dur * 0.78:
            s = ease((t - self.dur * 0.78) / 0.4)
            centered(ImageDraw.Draw(img), (W - 150, 600), "?", font(int(40 + 130 * s)), fill=RED, stroke=PAPER, sw=6)
        if self.who:
            self.actor(img, self.who[0], 120, 650, 250, t, 0, self.mouth(t))

    # -- easel: a list or short chart on an easel
    def _easel(self, img: Image.Image, t: float) -> None:
        items = [str(x) for x in (self.data.get("items") or [])][:6]
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
            self.actor(img, self.who[0], 1090, 650, 400, t, 0, self.mouth(t))

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
            self.actor(img, self.who[0], 1100, 650, 360, t, 0, self.mouth(t))

    def _silhouette(self, img: Image.Image, t: float) -> None:
        self.actor(img, self.who[0] if self.who else "dusty", 640, 700, 520, t, 0, False, silhouette=True)
        centered(ImageDraw.Draw(img), (640, 110), str(self.data.get("title") or ""), font(48), fill=(255, 246, 214))

    def _title(self, img: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(img)
        centered(d, (640, 300), str(self.data.get("title") or self.seg.get("chapter", "")), font(84),
                 fill=(255, 246, 214), stroke=(20, 16, 40), sw=4)
        if self.who:
            self.actor(img, self.who[0], 640, 700, 360, t, 0, self.mouth(t))


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


def _map_base() -> Image.Image:
    """Western Mediterranean as a hand-drawn schematic (Iberia, Gaul, Italy, North Africa, an Alps range)."""
    global _MAP
    if _MAP is not None:
        return _MAP
    S = 2
    img = _gradient(SEA, (156, 188, 196), W * S, H * S)
    d = ImageDraw.Draw(img)

    def land(norm: list[tuple[float, float]]) -> None:
        pts = _smooth([(x * W * S, y * H * S) for x, y in norm])
        d.polygon(pts, fill=LAND, outline=LAND_EDGE)
        d.line([*pts, pts[0]], fill=LAND_EDGE, width=5 * S // 2)

    land([(0.03, 0.55), (0.06, 0.44), (0.16, 0.42), (0.26, 0.45), (0.27, 0.56), (0.22, 0.72), (0.12, 0.78), (0.05, 0.72)])
    land([(0.20, 0.44), (0.24, 0.20), (0.40, 0.08), (0.62, 0.10), (0.70, 0.30), (0.52, 0.36), (0.36, 0.50), (0.27, 0.54)])
    land([(0.56, 0.34), (0.74, 0.28), (0.86, 0.42), (0.88, 0.58), (0.96, 0.70), (0.90, 0.80), (0.82, 0.66), (0.70, 0.54), (0.60, 0.42)])
    land([(0.04, 0.92), (0.22, 0.84), (0.50, 0.86), (0.70, 0.88), (0.90, 0.90), (0.96, 1.02), (0.02, 1.02)])
    land([(0.42, 0.62), (0.47, 0.60), (0.48, 0.68), (0.44, 0.72)])  # Sardinia
    for k in range(7):  # the Alps: a row of little snow-capped peaks
        x, y = (0.5 + k * 0.022) * W * S, (0.285 + math.sin(k * 0.9) * 0.012 + k * 0.008) * H * S
        s = 46 * S // 2 + (k % 3) * 6
        d.polygon([(x - s, y + s), (x, y - s), (x + s, y + s)], fill=(150, 130, 108), outline=LAND_EDGE)
        d.polygon([(x - s * 0.36, y - s * 0.28), (x, y - s), (x + s * 0.36, y - s * 0.28)], fill=(248, 250, 255))
    _MAP = _vignette(img.resize((W, H), Image.LANCZOS), 0.35)
    return _MAP


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


def fingerprint(seg: dict, dur: float, audio: Path | None) -> str:
    """Hash of everything that decides how a scene looks (re-render only when it changes)."""
    keys = {k: seg.get(k) for k in ("scene", "scene_data", "cast", "speech", "chapter")}
    keys.update(dur=round(dur, 2), audio=audio.stat().st_size if audio and Path(audio).exists() else 0, code=_CODE_STAMP)
    return hashlib.sha1(json.dumps(keys, sort_keys=True, default=str).encode()).hexdigest()[:12]


def render_scene(seg: dict, dur: float, out: Path, work: Path, audio: Path | None = None, faction0: int = 0,
                 cst: Cast | None = None) -> Path:
    """Render one cast scene to `out` (silent H.264, 1280x720, 24 fps, `dur` seconds). Reuses an identical earlier clip."""
    ff.ensure_ffmpeg()
    stamp = out.with_suffix(".stamp")
    fp = fingerprint(seg, dur, audio)
    if out.exists() and stamp.exists() and stamp.read_text() == fp:
        return out
    n = max(1, round(dur * FPS))
    cst = cst or Cast(work)
    scene = Scene(seg, dur, cst, envelope(audio, n), faction0)
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(ff.low_memory_cmd(cmd), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(n):
            t = f / FPS
            img = scene.frame(t)
            z = 1.0 + 0.035 * (t / max(dur, 0.1))  # slow push-in keeps every shot alive
            if z > 1.0005 and scene.kind not in ("map",):
                cw, ch = W / z, H / z
                x0, y0 = (W - cw) / 2, (H - ch) / 2
                img = img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
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
