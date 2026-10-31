"""Frame drawing for kids scenes: original flat-shape characters, backgrounds and lyric captions.

Everything is drawn with Pillow primitives, so no art assets or paid tools are needed. Characters are
simple shapes with a smiling face; they are our own drawings, not copies of any existing character.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from studio.kids.spec import COLORS

COLOR_RGB = {"red": (230, 60, 60), "orange": (250, 150, 40), "yellow": (250, 215, 50), "green": (70, 180, 90),
             "blue": (60, 130, 230), "purple": (150, 90, 210), "pink": (245, 130, 180)}
INK = (40, 40, 60)


def _ell(d: ImageDraw.ImageDraw, cx: float, cy: float, rx: float, ry: float, fill, outline=None) -> None:
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=outline, width=max(1, int(rx * 0.05)))


def _face(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float) -> None:
    for sx in (-1, 1):
        _ell(d, cx + sx * s * 0.22, cy - s * 0.05, s * 0.07, s * 0.09, INK)
        _ell(d, cx + sx * s * 0.2, cy - s * 0.08, s * 0.025, s * 0.03, (255, 255, 255))
    d.arc([cx - s * 0.18, cy + s * 0.0, cx + s * 0.18, cy + s * 0.28], 15, 165, fill=INK, width=max(2, int(s * 0.04)))


def _star(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def draw_character(d: ImageDraw.ImageDraw, name: str, cx: float, cy: float, s: float, idx: int = 0) -> None:
    """Draw one character centred at (cx, cy), roughly s pixels tall."""
    h = s / 2
    if name == "duck":
        _ell(d, cx, cy + h * 0.35, h * 0.85, h * 0.6, (250, 215, 50))
        _ell(d, cx, cy - h * 0.35, h * 0.55, h * 0.55, (250, 215, 50))
        d.polygon([(cx + h * 0.4, cy - h * 0.3), (cx + h * 0.95, cy - h * 0.2), (cx + h * 0.4, cy - h * 0.05)],
                  fill=(250, 140, 40))
        _ell(d, cx + h * 0.1, cy - h * 0.5, h * 0.07, h * 0.08, INK)
    elif name in ("cat", "dog"):
        body = (250, 160, 70) if name == "cat" else (170, 115, 70)
        _ell(d, cx, cy + h * 0.45, h * 0.7, h * 0.5, body)
        if name == "cat":
            for sx in (-1, 1):
                d.polygon([(cx + sx * h * 0.65, cy - h * 0.25), (cx + sx * h * 0.5, cy - h * 0.95),
                           (cx + sx * h * 0.1, cy - h * 0.55)], fill=body)
        else:
            for sx in (-1, 1):
                _ell(d, cx + sx * h * 0.7, cy - h * 0.2, h * 0.25, h * 0.45, (110, 70, 40))
        _ell(d, cx, cy - h * 0.2, h * 0.65, h * 0.6, body)
        _face(d, cx, cy - h * 0.2, h * 1.1)
        if name == "cat":
            for sx in (-1, 1):
                for dy in (0.05, 0.15):
                    d.line([(cx + sx * h * 0.25, cy + h * dy), (cx + sx * h * 0.8, cy + h * (dy - 0.05))],
                        fill=INK, width=2)
    elif name == "fish":
        d.polygon([(cx - h * 0.5, cy), (cx - h * 1.05, cy - h * 0.45), (cx - h * 1.05, cy + h * 0.45)],
            fill=(250, 150, 40))
        _ell(d, cx + h * 0.1, cy, h * 0.8, h * 0.5, (70, 160, 240))
        _ell(d, cx + h * 0.5, cy - h * 0.1, h * 0.09, h * 0.1, INK)
    elif name == "bunny":
        for sx in (-1, 1):
            _ell(d, cx + sx * h * 0.28, cy - h * 0.85, h * 0.16, h * 0.55, (250, 245, 245))
            _ell(d, cx + sx * h * 0.28, cy - h * 0.85, h * 0.07, h * 0.4, (245, 170, 190))
        _ell(d, cx, cy + h * 0.45, h * 0.65, h * 0.5, (250, 245, 245))
        _ell(d, cx, cy - h * 0.15, h * 0.6, h * 0.55, (250, 245, 245))
        _face(d, cx, cy - h * 0.15, h)
    elif name == "bird":
        _ell(d, cx, cy, h * 0.75, h * 0.65, (90, 170, 245))
        _ell(d, cx - h * 0.15, cy + h * 0.1, h * 0.4, h * 0.25, (60, 130, 220))
        d.polygon([(cx + h * 0.65, cy - h * 0.15), (cx + h * 1.05, cy - h * 0.02), (cx + h * 0.65, cy + h * 0.1)],
                  fill=(250, 150, 40))
        _ell(d, cx + h * 0.35, cy - h * 0.25, h * 0.08, h * 0.09, INK)
    elif name == "star":
        d.polygon(_star(cx, cy, h), fill=(252, 220, 60), outline=(240, 170, 30))
        _face(d, cx, cy + h * 0.05, h * 0.8)
    elif name == "sun":
        for i in range(12):
            a = i * math.pi / 6
            d.line([(cx + h * 0.75 * math.cos(a), cy + h * 0.75 * math.sin(a)),
                    (cx + h * 1.0 * math.cos(a), cy + h * 1.0 * math.sin(a))], fill=(250, 190, 40),
                        width=max(3, int(h * 0.1)))
        _ell(d, cx, cy, h * 0.65, h * 0.65, (252, 220, 60))
        _face(d, cx, cy, h * 1.1)
    elif name == "apple":
        _ell(d, cx, cy + h * 0.1, h * 0.8, h * 0.8, (225, 55, 55))
        d.line([(cx, cy - h * 0.7), (cx + h * 0.1, cy - h * 1.0)], fill=(100, 70, 40), width=max(3, int(h * 0.08)))
        _ell(d, cx + h * 0.3, cy - h * 0.85, h * 0.25, h * 0.12, (80, 180, 80))
    elif name == "ball":
        col = COLOR_RGB[COLORS[idx % len(COLORS)]]
        _ell(d, cx, cy, h * 0.8, h * 0.8, col, outline=INK)
        d.arc([cx - h * 0.8, cy - h * 0.8, cx + h * 0.8, cy + h * 0.8], 200, 340, fill=(255, 255, 255),
            width=max(3, int(h * 0.08)))
    elif name == "balloon":
        col = COLOR_RGB[COLORS[idx % len(COLORS)]]
        _ell(d, cx, cy - h * 0.2, h * 0.6, h * 0.75, col)
        d.polygon([(cx - h * 0.1, cy + h * 0.55), (cx + h * 0.1, cy + h * 0.55), (cx, cy + h * 0.45)], fill=col)
        d.line([(cx, cy + h * 0.55), (cx + h * 0.1, cy + h * 1.0)], fill=INK, width=2)
    elif name == "flower":
        col = COLOR_RGB[COLORS[idx % len(COLORS)]]
        d.line([(cx, cy), (cx, cy + h)], fill=(70, 160, 80), width=max(3, int(h * 0.1)))
        for i in range(6):
            a = i * math.pi / 3
            _ell(d, cx + h * 0.45 * math.cos(a), cy - h * 0.2 + h * 0.45 * math.sin(a), h * 0.3, h * 0.3, col)
        _ell(d, cx, cy - h * 0.2, h * 0.28, h * 0.28, (252, 220, 60))


def motion(kind: str, t: float, i: int, s: float) -> tuple[float, float, float]:
    """(dx, dy, scale) for item i at time t. Pop-in over the first 0.4s after its turn."""
    appear = t - i * 0.45
    if appear < 0:
        return 0.0, 0.0, 0.0
    pop = min(1.0, appear / 0.35)
    scale = 1 - (1 - pop) ** 3 * 0.9 + (math.sin(appear * 2.0 * math.pi) * 0.05 if kind == "pop" else 0.0)
    dx = dy = 0.0
    if kind == "bounce":
        dy = -abs(math.sin(t * 2.0 * math.pi * 0.9 + i * 0.7)) * s * 0.3
    elif kind == "sway":
        dx = math.sin(t * 2.0 + i) * s * 0.12
        dy = math.cos(t * 2.0 + i) * s * 0.04
    elif kind == "slide":
        dx = math.sin(t * 1.0 + i * 0.5) * s * 0.5
    return dx, dy, scale


def background(name: str, w: int, h: int) -> Image.Image:
    """Static background for a scene."""
    top, bottom = {"sky": ((120, 200, 255), (200, 235, 255)), "meadow": ((130, 205, 255), (215, 240, 255)),
                   "ocean": ((120, 210, 240), (30, 110, 190)), "night": ((25, 30, 80), (70, 60, 130)),
                   "farm": ((140, 205, 250), (220, 240, 255))}[name]
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        f = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[k] + (bottom[k] - top[k]) * f) for k in range(3)))
    if name in ("sky", "meadow", "farm"):
        _ell(d, w * 0.25, h * 1.05, w * 0.6, h * 0.35, (110, 200, 110))
        _ell(d, w * 0.8, h * 1.1, w * 0.6, h * 0.35, (90, 185, 100))
    if name == "farm":
        d.rectangle([w * 0.04, h * 0.45, w * 0.2, h * 0.72], fill=(200, 70, 60))
        d.polygon([(w * 0.02, h * 0.45), (w * 0.12, h * 0.3), (w * 0.22, h * 0.45)], fill=(150, 50, 45))
    if name == "night":
        for k in range(30):
            sx, sy = (k * 997 % w), (k * 577 % int(h * 0.6))
            _ell(d, sx, sy, 2, 2, (255, 250, 220))
        _ell(d, w * 0.85, h * 0.15, h * 0.08, h * 0.08, (255, 250, 210))
    if name == "ocean":
        for k in range(8):
            d.arc([k * w / 7 - 60, h * 0.78, k * w / 7 + 60, h * 0.9], 200, 340, fill=(255, 255, 255), width=3)
    return img


def draw_clouds(d: ImageDraw.ImageDraw, t: float, w: int, h: int, bg: str) -> None:
    if bg in ("night", "ocean"):
        return
    for k in range(3):
        x = (t * 18 + k * w / 2.2) % (w + 300) - 150
        y = h * (0.12 + 0.1 * k)
        for dx, r in ((-40, 35), (0, 48), (45, 36)):
            _ell(d, x + dx, y, r, r * 0.7, (255, 255, 255))


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_lyrics(img: Image.Image, lines: list[str], active: int, font_file: str) -> None:
    """Big captions at the bottom; the line being sung is yellow and larger."""
    w, h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    base = max(18, h // 15)
    gap = int(base * 1.35)
    top = h - gap * len(lines) - base
    d.rounded_rectangle([w * 0.08, top - base * 0.5, w * 0.92, h - base * 0.4], radius=base, fill=(20, 20, 50, 120))
    for k, ln in enumerate(lines):
        on = k == active
        f = _font(font_file, int(base * (1.2 if on else 1.0)))
        d.text((w / 2, top + gap * k + gap / 2), ln, font=f, anchor="mm", fill=(255, 235,
            60) if on else (255, 255, 255),
               stroke_width=max(2, base // 10), stroke_fill=INK)


def render_frame(scene: dict, t: float, bg_img: Image.Image, lyric_idx: int, font_file: str,
                 big_number: bool) -> Image.Image:
    """One frame of a scene at time t seconds."""
    img = bg_img.copy()
    w, h = img.size
    d = ImageDraw.Draw(img)
    draw_clouds(d, t, w, h, scene["visual"]["background"])
    v = scene["visual"]
    chars = v["characters"]
    n = v.get("count", len(chars))
    size = min(h * 0.38, w * 0.8 / n)
    row_y = h * 0.42
    for i in range(n):
        x = w * (i + 0.5) / n
        dx, dy, sc = motion(v["motion"], t, i, size)
        if sc <= 0.02:
            continue
        draw_character(d, chars[i % len(chars)], x + dx, row_y + dy, size * sc, idx=i)
    if big_number:
        shown = min(n, int(t / 0.45) + 1)
        d.text((w * 0.9, h * 0.12), str(shown), font=_font(font_file, int(h * 0.2)), anchor="mm",
               fill=(255, 235, 60), stroke_width=6, stroke_fill=INK)
    draw_lyrics(img, scene["lines"], lyric_idx, font_file)
    return img
