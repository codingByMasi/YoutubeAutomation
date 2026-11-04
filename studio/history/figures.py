# ruff: noqa: E501  (drawing code)
"""Open-ended characters drawn from a description, not from a fixed list of types.

Claude describes every character a script uses as structured attributes (see `normalize`): gender, age, build, skin,
hair, facial hair, clothing, armour, headwear, props, colours. `draw` composes the sprite from those parts with
Pillow (no cairo, no GPU). Any value is accepted: known words get a proper drawing, an unknown clothing, headwear or
prop word falls back to a generic shape in the character's accent colour, so an unfamiliar role never breaks. The
same spec always produces the same picture, so a character looks identical across the whole video.

The canvas contract is the cast sprites': a square `px` picture with the feet line at 84% of its height.
"""

from __future__ import annotations

import hashlib
import re

from PIL import Image, ImageDraw

INK = (43, 43, 61)
SKIN = {"pale": "#F8DEC8", "fair": "#F2D2B1", "light": "#F2D2B1", "olive": "#D9AE82", "tan": "#CD9C6B",
        "brown": "#A86F45", "dark": "#7A4A2D", "deep": "#5A3420", "ebony": "#4A2A1B"}
COLORS = {"black": "#2b2b3d", "white": "#f4efe2", "grey": "#8c96a3", "gray": "#8c96a3", "silver": "#b8c0cc",
          "gold": "#e0b43a", "yellow": "#e0c040", "orange": "#d9772b", "red": "#b3282d", "crimson": "#9c1f2d",
          "purple": "#6a3d8f", "violet": "#6a3d8f", "blue": "#2f5f9f", "navy": "#1f2d4d", "teal": "#2e7d87",
          "green": "#3d7a45", "olive_green": "#6b7a3a", "brown": "#7a5233", "tan": "#c9a66b", "cream": "#f1e4c4",
          "pink": "#c94f7c", "blond": "#d8b45a", "blonde": "#d8b45a", "auburn": "#8a3b22", "ginger": "#b5521f"}
HAIR_DEFAULT = {"child": "#6b4a2f", "young": "#3a2a20", "adult": "#3a2a20", "elder": "#c9c9c9"}
BUILD_W = {"slim": 0.84, "average": 1.0, "stocky": 1.15, "broad": 1.28, "heavy": 1.28, "tall": 0.92, "small": 0.86}
BUILD_H = {"tall": 1.1, "small": 0.9}
AGE_H = {"child": 0.66, "young": 0.96, "adult": 1.0, "elder": 0.95}
LONG_GARMENTS = ("dress", "gown", "robe", "toga", "cloak", "kimono", "chiton", "habit", "cassock", "skirt", "kaftan")


# Defaults for a character the script describes only loosely: what people of that era plausibly wear (see wardrobe.py).
ERA_STYLE: dict[str, dict] = {
    "roman": {"clothing": "toga", "color": "#e9e2cf", "trim": "#7d1a1e"},
    "greek": {"clothing": "chiton", "color": "#f4efe2", "trim": "#2f5f9f"},
    "viking": {"clothing": "tunic", "color": "#7a5233", "trim": "#e9dcc3"},
    "medieval": {"clothing": "tunic", "color": "#8b2f45", "trim": "#e0b43a"},
    "desert": {"clothing": "robe", "color": "#f1ece0", "trim": "#2e7d87", "headwear": "headscarf"},
    "egyptian": {"clothing": "kilt", "color": "#f4efe2", "trim": "#e0b43a"},
    "samurai": {"clothing": "kimono", "color": "#2f5f9f", "trim": "#e0b43a"},
    "renaissance": {"clothing": "coat", "color": "#6a3d8f", "trim": "#e0b43a", "headwear": "hat"},
    "sail": {"clothing": "coat", "color": "#1f2d4d", "trim": "#e0b43a", "headwear": "hat"},
    "modern": {"clothing": "coat", "color": "#6f7a52", "trim": "#3b2c1c", "headwear": "cap"},
}


# Face and body variety. A script may name any of these per character (`"face": {"shape", "eyes", "brows", "nose",
# "mouth", "marks"}`, optional `"posture"`); whatever it leaves out is picked from the character's name, so two people in
# one video never share a face, and the same person is the same in every scene.
FACE_OPTIONS: dict[str, tuple[str, ...]] = {
    "shape": ("round", "oval", "square", "long", "heart"),
    "eyes": ("round", "narrow", "wide", "sleepy", "sharp"),
    "brows": ("arched", "flat", "stern", "thick", "raised"),
    "nose": ("button", "long", "hooked", "broad", "pointy"),
    "mouth": ("smile", "flat", "smirk", "small", "grin"),
    "marks": ("none", "none", "freckles", "scar", "mole"),
}
POSTURES = ("upright", "slouch", "lean_left", "lean_right", "proud")
HAIR_FEMALE = ("long", "bun", "braid", "ponytail", "curly")
HAIR_OTHER = ("short", "curly", "buzz", "short", "ponytail")


def _pick(h: int, shift: int, options: tuple) -> str:
    return options[(h >> shift) % len(options)]


def _face(spec: dict, h: int) -> dict:
    """The character's face parts: the script's own words where known, otherwise a stable pick from the name."""
    given = spec.get("face") if isinstance(spec.get("face"), dict) else {}
    face = {}
    for i, (part, options) in enumerate(FACE_OPTIONS.items()):
        want = _word(given.get(part) or (spec.get(f"face_{part}") if part != "marks" else spec.get("marks")))
        face[part] = want if want in options else _pick(h, 8 + 9 * i, options)
    face["head_scale"] = 0.93 + ((h >> 70) % 15) / 100  # 0.93 .. 1.07
    face["eye_gap"] = 0.30 + ((h >> 80) % 13) / 100  # 0.30 .. 0.42 of the head radius
    face["posture"] = _word(spec.get("posture")) if _word(spec.get("posture")) in POSTURES else _pick(h, 90, POSTURES)
    return face


def colour(value: object, default: str) -> tuple[int, int, int]:
    """RGB for a hex string or a colour/skin word; anything unknown gives `default` (a hex string)."""
    v = str(value or "").strip().lower().replace(" ", "_")
    v = (COLORS.get(v) or SKIN.get(v) or v).lower()
    if not re.fullmatch(r"#?[0-9a-f]{6}", v):
        v = default
    v = v.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _dark(c: tuple, f: float = 0.68) -> tuple:
    return tuple(int(x * f) for x in c)


def _light(c: tuple, f: float = 0.35) -> tuple:
    return tuple(int(x + (255 - x) * f) for x in c)


def _word(value: object) -> str:
    return re.sub(r"[^a-z]+", "_", str(value or "").lower()).strip("_")


def normalize(spec: dict, era_style: dict | None = None) -> dict:
    """A complete description from whatever Claude gave: every missing or unknown part gets a sensible default.

    `gender` is only what the script says (female, male or neutral); it is never guessed from a name."""
    spec = dict(spec or {})
    era_style = era_style or {}
    gender = _word(spec.get("gender")) if _word(spec.get("gender")) in ("female", "male") else "neutral"
    age = _word(spec.get("age")) if _word(spec.get("age")) in AGE_H else "adult"
    hair = spec.get("hair") if isinstance(spec.get("hair"), dict) else {"style": spec.get("hair")}
    cloth = spec.get("clothing") if isinstance(spec.get("clothing"), dict) else {"type": spec.get("clothing")}
    h = int(hashlib.sha1(str(spec.get("name", "")).lower().encode()).hexdigest(), 16)
    accent = spec.get("accent_color") or spec.get("color") or f"#{(h >> 4) & 0xFFFFFF:06x}"
    props = spec.get("props") or ([spec["prop"]] if spec.get("prop") else [])
    props = [props] if isinstance(props, str) else list(props)
    elder_m = age == "elder" and gender != "female" and h % 3 == 0
    ctype = _word(cloth.get("type")) or era_style.get("clothing") or ("dress" if gender == "female" else "tunic")
    return {
        "name": str(spec.get("name") or ""), "role": str(spec.get("role") or ""), "gender": gender, "age": age,
        "build": _word(spec.get("build")) or "average",
        "skin": colour(spec.get("skin"), SKIN["fair"]),
        "hair_style": _word(hair.get("style")) or (
            "receding" if elder_m else _pick(h, 3, HAIR_FEMALE if gender == "female" else HAIR_OTHER)),
        "hair_color": colour(hair.get("color"), HAIR_DEFAULT[age]),
        "facial_hair": _word(spec.get("facial_hair")) or (
            _pick(h, 40, ("none", "none", "mustache", "beard", "goatee")) if gender == "male" and age in ("adult", "elder") else "none"),
        "face": _face(spec, h),
        "clothing": ctype,
        "cloth_color": colour(cloth.get("color") or era_style.get("color"), accent if isinstance(accent, str) else "#2E7D87"),
        "trim": colour(cloth.get("trim") or era_style.get("trim"), "#e0b43a"),
        "armour": _word(spec.get("armour") or spec.get("armor")) or "none",
        "headwear": _word(spec.get("headwear")) or era_style.get("headwear") or "none",
        "head_color": colour(spec.get("headwear_color"), "#8c96a3"),
        "props": [_word(p) for p in props if _word(p)][:2],
        "accent": colour(accent, "#2E7D87"),
        "cape": colour(spec.get("cape_color"), "#b3282d") if spec.get("cape") or spec.get("cape_color") else None,
        "badge": str(spec.get("badge") or (spec.get("name") or "?")[:1]),
    }


def sketch(spec: dict) -> dict:
    """Spec as it affects the picture (used in scene fingerprints so an edited character redraws)."""
    return normalize(spec)


def draw(spec: dict, px: int, eyes_closed: bool = False, mouth_open: bool = False,
         era_style: dict | None = None) -> Image.Image:
    """Compose the character's sprite (RGBA, `px` square, feet at 84%) from its attributes."""
    from studio.history.render import font  # the shared bold font (badge letter)
    n = normalize(spec, era_style)
    k = 4
    s = px * k / 400.0
    im = Image.new("RGBA", (px * k, px * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def box(x0, y0, x1, y1):
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    def pts(*xy):
        return [(x * s, y * s) for x, y in xy]

    kid, elder = n["age"] == "child", n["age"] == "elder"
    bw = BUILD_W.get(n["build"], 1.0) * (0.9 if n["gender"] == "female" else 1.0) * (0.8 if kid else 1.0)
    bh = BUILD_H.get(n["build"], 1.0) * AGE_H[n["age"]]
    cx, feet = 200, 336
    hem_y = feet - 30 * bh
    sh_y = feet - 122 * bh  # shoulder line
    half = 62 * bw
    fc = n["face"]
    head_r = 66 * (1.12 if kid else 1.0) * fc["head_scale"]
    head_cy = sh_y - head_r * 0.72 - (6 if elder else 0)
    # posture shifts the head and hurries or lifts the shoulders so bodies differ as well as faces
    lean = {"lean_left": -9, "lean_right": 9, "slouch": 4}.get(fc["posture"], 0)
    head_cy += {"slouch": 8, "proud": -6}.get(fc["posture"], 0)
    hx0 = cx + lean  # the head's centre line
    skin, ink, col, trim, hair = n["skin"], INK, n["cloth_color"], n["trim"], n["hair_color"]
    long_g = n["clothing"] in LONG_GARMENTS or n["clothing"] == "dress"
    armoured = n["armour"] not in ("none", "")
    metal = (150, 158, 170)

    # back layers: cape, long hair
    if n["cape"]:
        d.polygon(pts((cx - half - 8, sh_y), (cx - half - 30, feet + 8), (cx + half + 30, feet + 8), (cx + half + 8, sh_y)),
                  fill=n["cape"], outline=ink)
    if n["hair_style"] in ("long", "braid", "ponytail", "bun_long") and n["hair_style"] != "ponytail":
        d.rounded_rectangle(box(cx - head_r - 6, head_cy - 10, cx + head_r + 6, head_cy + head_r * 1.9), int(26 * s), fill=hair,
                            outline=ink, width=int(3 * s))
    # legs (visible under short garments)
    if not long_g:
        for lx in (cx - half * 0.42, cx + half * 0.42):
            d.line([(lx * s, hem_y * s), (lx * s, (feet - 6) * s)], fill=_dark(col, 0.6) if n["clothing"] in ("trousers", "coat") else skin,
                   width=int(11 * s))
            d.rounded_rectangle(box(lx - 22, feet - 8, lx + 22, feet + 6), int(7 * s), fill=ink)
    # arms (behind the torso edge)
    sleeve = metal if armoured else col
    d.line([((cx - half) * s, (sh_y + 8) * s), ((cx - half - 22) * s, (sh_y + 62 * bh) * s)], fill=sleeve, width=int(19 * s))
    d.line([((cx + half) * s, (sh_y + 8) * s), ((cx + half + 40) * s, (sh_y + 40 * bh) * s)], fill=sleeve, width=int(19 * s))
    d.ellipse(box(cx - half - 36, sh_y + 52 * bh, cx - half - 10, sh_y + 76 * bh), fill=skin, outline=ink, width=int(3 * s))
    hand_r = (cx + half + 40, sh_y + 40 * bh)
    d.ellipse(box(hand_r[0] - 13, hand_r[1] - 12, hand_r[0] + 13, hand_r[1] + 14), fill=skin, outline=ink, width=int(3 * s))
    # torso / garment
    waist = half * (0.86 if n["gender"] == "female" else 1.0)
    if long_g or n["clothing"] == "dress":
        flare = half * (1.5 if n["clothing"] in ("dress", "gown", "skirt") else 1.25)
        d.polygon(pts((cx - half, sh_y), (cx + half, sh_y), (cx + waist * 0.92, sh_y + 60 * bh),
                      (cx + flare, feet - 4), (cx - flare, feet - 4), (cx - waist * 0.92, sh_y + 60 * bh)), fill=col, outline=ink)
        d.line([((cx - flare + 6) * s, (feet - 14) * s), ((cx + flare - 6) * s, (feet - 14) * s)], fill=trim, width=int(7 * s))
        d.rectangle(box(cx - waist * 0.9, sh_y + 52 * bh, cx + waist * 0.9, sh_y + 62 * bh), fill=trim)
    else:
        d.polygon(pts((cx - half, sh_y), (cx + half, sh_y), (cx + half * 0.9, hem_y), (cx - half * 0.9, hem_y)), fill=col, outline=ink)
        d.line([((cx - half * 0.9) * s, hem_y * s), ((cx + half * 0.9) * s, hem_y * s)], fill=trim, width=int(7 * s))
        if n["clothing"] in ("tunic", "apron", "kilt", "chiton", "uniform", "coat", "jacket", "robe_short"):
            d.rectangle(box(cx - half * 0.95, sh_y + 58 * bh, cx + half * 0.95, sh_y + 68 * bh), fill=trim if n["clothing"] != "coat" else _dark(col))
        if n["clothing"] in ("coat", "jacket", "uniform"):
            d.line([(cx * s, sh_y * s), (cx * s, hem_y * s)], fill=_dark(col), width=int(4 * s))
            for by in (sh_y + 30 * bh, sh_y + 58 * bh):
                d.ellipse(box(cx - 5, by - 5, cx + 5, by + 5), fill=trim)
        if n["clothing"] == "apron":
            d.polygon(pts((cx - half * 0.55, sh_y + 20 * bh), (cx + half * 0.55, sh_y + 20 * bh), (cx + half * 0.7, hem_y), (cx - half * 0.7, hem_y)),
                      fill=_light(col, 0.7), outline=ink)
    if armoured:  # breastplate / mail over the torso
        a = n["armour"]
        d.polygon(pts((cx - half * 0.94, sh_y + 4), (cx + half * 0.94, sh_y + 4), (cx + half * 0.8, sh_y + 66 * bh),
                      (cx - half * 0.8, sh_y + 66 * bh)), fill=metal, outline=ink)
        step = 14 if a in ("plate", "lamellar") else 10
        for yy in range(int(sh_y + 16), int(sh_y + 62 * bh), step):
            d.line([((cx - half * 0.8) * s, yy * s), ((cx + half * 0.8) * s, yy * s)], fill=_dark(metal, 0.8), width=int(3 * s))
        d.ellipse(box(cx - half - 16, sh_y - 6, cx - half + 14, sh_y + 20), fill=_light(metal, 0.2), outline=ink, width=int(3 * s))
        d.ellipse(box(cx + half - 14, sh_y - 6, cx + half + 16, sh_y + 20), fill=_light(metal, 0.2), outline=ink, width=int(3 * s))
        for xx in range(-4, 5):  # skirt straps
            d.rectangle(box(cx + xx * half * 0.2 - 8, sh_y + 66 * bh, cx + xx * half * 0.2 + 8, hem_y + 4), fill=col, outline=ink)
    d.ellipse(box(cx - 17, sh_y + 8 * bh, cx + 17, sh_y + 40 * bh), fill=(252, 244, 222), outline=ink, width=int(3 * s))  # badge
    d.text((cx * s, (sh_y + 24 * bh) * s), (n["badge"] or "?")[:1], font=font(int(30 * s), False), fill=ink, anchor="mm")
    # neck and head
    d.rectangle(box(cx - 10, sh_y - 14, cx + 10, sh_y + 4), fill=skin)
    body_cx, cx = cx, hx0
    hw0, hc0 = n["headwear"], n["head_color"]
    if hw0 in ("hood", "cowl"):  # drapes behind the face
        d.pieslice(box(cx - head_r - 14, head_cy - head_r - 22, cx + head_r + 14, head_cy + head_r * 1.5), 180, 360,
                   fill=hc0 if hc0 != (140, 150, 163) else _dark(col, 0.8), outline=ink, width=int(4 * s))
        d.rectangle(box(cx - head_r - 14, head_cy + head_r * 0.3, cx + head_r + 14, sh_y + 10), fill=hc0 if hc0 != (140, 150, 163) else _dark(col, 0.8))
    elif hw0 in ("veil", "headscarf", "scarf"):
        d.pieslice(box(cx - head_r - 10, head_cy - head_r - 14, cx + head_r + 10, head_cy + head_r * 1.7), 180, 360, fill=n["accent"], outline=ink, width=int(4 * s))
        d.rectangle(box(cx - head_r - 10, head_cy + head_r * 0.4, cx + head_r + 10, sh_y + 10), fill=n["accent"])
    wf, hf = {"oval": (0.93, 1.1), "long": (0.86, 1.2), "heart": (1.0, 1.06), "square": (1.0, 1.04)}.get(fc["shape"], (1.0, 1.04))
    if fc["shape"] == "square":
        d.rounded_rectangle(box(cx - head_r * 0.96, head_cy - head_r, cx + head_r * 0.96, head_cy + head_r * hf), int(30 * s), fill=skin,
                            outline=ink, width=int(5 * s))
    else:
        d.ellipse(box(cx - head_r * wf, head_cy - head_r, cx + head_r * wf, head_cy + head_r * hf), fill=skin, outline=ink, width=int(5 * s))
        if fc["shape"] == "heart":  # narrower chin
            d.polygon(pts((cx - head_r * 0.62, head_cy + head_r * 0.45), (cx + head_r * 0.62, head_cy + head_r * 0.45), (cx, head_cy + head_r * 1.16)),
                      fill=skin, outline=ink)
            d.ellipse(box(cx - head_r * 0.7, head_cy + head_r * 0.2, cx + head_r * 0.7, head_cy + head_r * 0.8), fill=skin)
    ear_x = head_r * (0.93 if fc["shape"] in ("oval", "long") else 1.0)
    for sx in (-1, 1):  # ears
        d.ellipse(box(cx + sx * ear_x - 7, head_cy - 6, cx + sx * ear_x + 7, head_cy + 22), fill=skin, outline=ink, width=int(3 * s))
    # hair on top
    hs = n["hair_style"]
    if hs not in ("none", "bald", "shaved") and n["headwear"] not in ("helmet", "hood", "turban", "veil", "headscarf"):
        top = head_cy - head_r
        crown = {"buzz": 0.1, "receding": 0.0}.get(hs, 0.3)  # how far the hair comes down; a buzz cut hugs the skull
        if hs == "receding":  # hair only at the temples
            for sx in (-1, 1):
                d.pieslice(box(cx + sx * head_r * 0.62 - 26, top + 4, cx + sx * head_r * 0.62 + 26, head_cy + 8), 180, 360, fill=hair, outline=ink, width=int(3 * s))
        else:
            d.pieslice(box(cx - head_r - 3, top - 8, cx + head_r + 3, head_cy + head_r * crown), 180, 360, fill=hair, outline=ink, width=int(3 * s))
        if hs in ("bun", "bun_long"):
            d.ellipse(box(cx - 24, top - 34, cx + 24, top + 8), fill=hair, outline=ink, width=int(3 * s))
        elif hs == "ponytail":
            d.line([((cx + head_r - 6) * s, (head_cy - 18) * s), ((cx + head_r + 28) * s, (head_cy + 52) * s)], fill=hair, width=int(16 * s))
        elif hs == "braid":
            d.line([(cx * s, (head_cy + head_r) * s), ((cx - 10) * s, (head_cy + head_r + 60) * s)], fill=hair, width=int(14 * s))
        elif hs == "topknot":
            d.ellipse(box(cx - 16, top - 30, cx + 16, top + 2), fill=hair, outline=ink, width=int(3 * s))
        elif hs == "side_part":
            d.polygon(pts((cx - head_r, head_cy - 8), (cx - head_r * 0.2, top + 2), (cx + head_r * 0.25, head_cy - head_r * 0.55), (cx + head_r, head_cy - 8)),
                      fill=hair, outline=ink)
        elif hs == "curly":
            for ang in range(190, 360, 28):
                import math
                px_, py_ = cx + math.cos(math.radians(ang)) * (head_r + 4), head_cy + math.sin(math.radians(ang)) * (head_r + 2)
                d.ellipse(box(px_ - 14, py_ - 14, px_ + 14, py_ + 14), fill=hair, outline=ink, width=int(2 * s))
    # face: eyes, brows and nose follow this character's own face description
    ey = head_cy - 2
    gap, brow_dark = head_r * fc["eye_gap"], hair if not kid else ink
    ew, eh = {"narrow": (10, 6), "wide": (11, 14), "sleepy": (9, 9), "sharp": (11, 8)}.get(fc["eyes"], (9, 12))
    for sx in (-1, 1):
        ex = cx + sx * gap
        if eyes_closed:
            d.line([((ex - ew) * s, ey * s), ((ex + ew) * s, ey * s)], fill=ink, width=int(4 * s))
        else:
            if fc["eyes"] == "sharp":  # almond eye, outer corner lifted
                d.polygon(pts((ex - ew, ey + 3), (ex - ew * 0.3, ey - eh), (ex + ew, ey - eh * 0.6 + 0), (ex + ew * 0.3, ey + eh * 0.8)), fill=(255, 255, 255), outline=ink)
            else:
                d.ellipse(box(ex - ew, ey - eh, ex + ew, ey + eh), fill=(255, 255, 255), outline=ink, width=int(3 * s))
            pr_ = min(ew, eh) * 0.55
            d.ellipse(box(ex - pr_, ey - pr_ * 0.8, ex + pr_, ey + pr_ * 1.2), fill=ink)
            if fc["eyes"] == "sleepy":  # heavy lid over the top half
                d.pieslice(box(ex - ew, ey - eh, ex + ew, ey + eh), 180, 360, fill=_dark(skin, 0.86), outline=ink, width=int(3 * s))
        if n["gender"] == "female" and not kid:  # soft lashes
            d.line([((ex + sx * (ew + 1)) * s, (ey - eh) * s), ((ex + sx * (ew + 6)) * s, (ey - eh - 5) * s)], fill=ink, width=int(3 * s))
        brow = ey - eh - 8 - (3 if elder else 0)
        kind, bw_ = fc["brows"], int(4 * s)
        if kind == "thick":
            d.line([((ex - 12) * s, brow * s), ((ex + 12) * s, (brow - 2) * s)], fill=brow_dark, width=int(8 * s))
        elif kind == "stern":  # inner ends pulled down
            d.line([((ex - sx * 12) * s, (brow + 5) * s), ((ex + sx * 12) * s, (brow - 4) * s)], fill=brow_dark, width=bw_)
        elif kind == "arched":
            d.arc(box(ex - 13, brow - 10, ex + 13, brow + 8), 200, 340, fill=brow_dark, width=bw_)
        elif kind == "raised":
            d.line([((ex - 11) * s, (brow - 6) * s), ((ex + 11) * s, (brow - 6 - 4 * sx) * s)], fill=brow_dark, width=int(3 * s))
        else:
            d.line([((ex - 11) * s, brow * s), ((ex + 11) * s, (brow - (3 if elder else 0)) * s)], fill=brow_dark, width=bw_)
    ny, nose_c = ey + eh + 6, _dark(skin, 0.72)  # nose
    nk = fc["nose"]
    if nk == "long":
        d.line([(cx * s, (ey + 2) * s), (cx * s, (ny + 22) * s)], fill=nose_c, width=int(4 * s))
        d.arc(box(cx - 11, ny + 10, cx + 11, ny + 30), 20, 160, fill=nose_c, width=int(4 * s))
    elif nk == "hooked":
        d.arc(box(cx - 4, ey, cx + 18, ny + 26), 270, 70, fill=nose_c, width=int(4 * s))
    elif nk == "broad":
        d.ellipse(box(cx - 15, ny + 4, cx + 15, ny + 22), fill=_dark(skin, 0.9), outline=nose_c, width=int(3 * s))
    elif nk == "pointy":
        d.polygon(pts((cx - 7, ny + 18), (cx + 2, ny - 2), (cx + 10, ny + 18)), fill=_dark(skin, 0.92), outline=nose_c)
    else:  # button
        d.ellipse(box(cx - 6, ny + 6, cx + 6, ny + 18), fill=_dark(skin, 0.88), outline=nose_c, width=int(3 * s))
    mk = fc["marks"]  # freckles, a scar or a mole
    if mk == "freckles":
        for fx, fy in ((-26, 22), (-18, 28), (-32, 30), (26, 22), (18, 28), (32, 30)):
            d.ellipse(box(cx + fx - 2, ey + fy - 2, cx + fx + 2, ey + fy + 2), fill=_dark(skin, 0.6))
    elif mk == "scar":
        d.line([((cx + gap - 8) * s, (ey - eh - 14) * s), ((cx + gap + 12) * s, (ey + eh + 16) * s)], fill=(178, 70, 70), width=int(3 * s))
    elif mk == "mole":
        d.ellipse(box(cx + gap + 8, ey + 24, cx + gap + 14, ey + 30), fill=_dark(skin, 0.45))
    if kid:
        for ex in (cx - head_r * 0.55, cx + head_r * 0.55):
            d.ellipse(box(ex - 9, ey + 18, ex + 9, ey + 32), fill=(240, 160, 150, 150))
    if elder:
        for ex in (cx - head_r * 0.42, cx + head_r * 0.42):
            d.arc(box(ex - 10, ey + 14, ex + 10, ey + 34), 20, 160, fill=_dark(skin, 0.8), width=int(2 * s))
    my = head_cy + head_r * 0.52
    fh = n["facial_hair"]
    if fh in ("beard", "full_beard", "long_beard"):
        d.pieslice(box(cx - head_r * 0.82, head_cy - 6, cx + head_r * 0.82, head_cy + head_r * (1.5 if fh == "long_beard" else 1.25)),
                   10, 170, fill=hair, outline=ink, width=int(3 * s))
    mk_c = ink if fh not in ("beard", "full_beard", "long_beard") else (240, 230, 210)
    mw = {"small": 11, "grin": 24}.get(fc["mouth"], 18)
    if mouth_open:
        d.ellipse(box(cx - mw * 0.85, my - 10, cx + mw * 0.85, my + 14), fill=(120, 30, 40), outline=ink, width=int(3 * s))
    elif fc["mouth"] == "flat":
        d.line([((cx - mw) * s, (my + 2) * s), ((cx + mw) * s, (my + 2) * s)], fill=mk_c, width=int(4 * s))
    elif fc["mouth"] == "smirk":
        d.line([((cx - mw) * s, (my + 4) * s), ((cx + 4) * s, (my + 4) * s), ((cx + mw) * s, (my - 4) * s)], fill=mk_c, width=int(4 * s))
    elif fc["mouth"] == "grin":
        d.chord(box(cx - mw, my - 12, cx + mw, my + 14), 0, 180, fill=(250, 245, 235), outline=ink, width=int(3 * s))
    else:
        d.arc(box(cx - mw, my - 14, cx + mw, my + 10), 20, 160, fill=mk_c, width=int(4 * s))
    if fh in ("mustache", "goatee", "beard", "full_beard", "long_beard"):
        d.pieslice(box(cx - 26, my - 22, cx + 26, my - 2), 0, 180, fill=hair, outline=ink, width=int(2 * s))
    if fh == "goatee":
        d.ellipse(box(cx - 11, my + 10, cx + 11, my + 36), fill=hair, outline=ink, width=int(2 * s))
    # headwear
    hw, hc = n["headwear"], n["head_color"]
    top = head_cy - head_r
    if hw in ("helmet", "galea", "casque"):
        d.pieslice(box(cx - head_r - 6, top - 14, cx + head_r + 6, head_cy + head_r * 0.28), 180, 360, fill=metal, outline=ink, width=int(4 * s))
        d.rectangle(box(cx - head_r - 6, head_cy - head_r * 0.32, cx + head_r + 6, head_cy - head_r * 0.16), fill=_dark(metal, 0.8))
        d.polygon(pts((cx - 10, top - 10), (cx, top - 40), (cx + 10, top - 10)), fill=n["accent"], outline=ink)  # crest
    elif hw == "crown":
        d.polygon(pts((cx - 52, top + 14), (cx - 46, top - 30), (cx - 22, top), (cx, top - 40), (cx + 22, top), (cx + 46, top - 30), (cx + 52, top + 14)),
                  fill=(224, 180, 58), outline=ink)
    elif hw in ("circlet", "laurel", "wreath"):
        d.arc(box(cx - head_r, top - 6, cx + head_r, top + head_r), 190, 350, fill=(79, 138, 60) if hw != "circlet" else (224, 180, 58), width=int(11 * s))
    elif hw in ("hood", "cowl", "veil", "headscarf", "scarf"):
        pass  # drawn behind the face above
    elif hw in ("turban", "headwrap"):
        d.ellipse(box(cx - head_r - 8, top - 22, cx + head_r + 8, top + head_r * 0.75), fill=_light(n["accent"], 0.7), outline=ink, width=int(4 * s))
    elif hw in ("hat", "bicorn", "tricorn", "wide_hat"):
        d.ellipse(box(cx - head_r - 36, top + 4, cx + head_r + 36, top + 32), fill=hc if hc != (140, 150, 163) else n["accent"], outline=ink, width=int(4 * s))
        d.pieslice(box(cx - head_r * 0.7, top - 38, cx + head_r * 0.7, top + 40), 180, 360, fill=hc if hc != (140, 150, 163) else n["accent"], outline=ink, width=int(4 * s))
    elif hw not in ("none", ""):  # cap and anything unfamiliar: a simple cap in the character's accent colour
        d.pieslice(box(cx - head_r - 3, top - 12, cx + head_r + 3, head_cy + head_r * 0.2), 180, 360,
                   fill=hc if hc != (140, 150, 163) else n["accent"], outline=ink, width=int(4 * s))
    cx = body_cx
    # props in the right hand
    for pr in n["props"][:2]:
        hx, hy = hand_r
        if pr in ("sword", "gladius", "blade", "saber"):
            d.rectangle(box(hx - 5, hy - 108, hx + 5, hy + 8), fill=(190, 198, 210), outline=ink, width=int(2 * s))
            d.rectangle(box(hx - 20, hy + 6, hx + 20, hy + 16), fill=(122, 82, 51), outline=ink, width=int(2 * s))
        elif pr in ("spear", "pike", "lance", "javelin"):
            d.rectangle(box(hx - 4, hy - 170, hx + 4, hy + 40), fill=(122, 82, 51))
            d.polygon(pts((hx - 11, hy - 168), (hx, hy - 206), (hx + 11, hy - 168)), fill=(190, 198, 210), outline=ink)
        elif pr in ("shield", "buckler"):
            d.ellipse(box(cx - half - 70, sh_y + 20, cx - half - 4, sh_y + 100 * bh), fill=n["accent"], outline=ink, width=int(4 * s))
            d.ellipse(box(cx - half - 48, sh_y + 44, cx - half - 26, sh_y + 66), fill=(224, 180, 58), outline=ink, width=int(2 * s))
        elif pr in ("staff", "scepter", "sceptre", "crook"):
            d.rectangle(box(hx - 4, hy - 150, hx + 4, hy + 50), fill=(122, 82, 51))
            d.ellipse(box(hx - 12, hy - 166, hx + 12, hy - 142), fill=(224, 180, 58), outline=ink, width=int(2 * s))
        elif pr in ("bow", "crossbow"):
            d.arc(box(hx - 30, hy - 70, hx + 10, hy + 40), 270, 90, fill=(122, 82, 51), width=int(6 * s))
            d.line([((hx - 10) * s, (hy - 70) * s), ((hx - 10) * s, (hy + 40) * s)], fill=ink, width=int(2 * s))
        elif pr in ("scroll", "letter", "map", "document", "tablet"):
            d.rounded_rectangle(box(hx - 28, hy - 22, hx + 28, hy + 18), int(7 * s), fill=(241, 228, 196), outline=(184, 153, 104), width=int(3 * s))
        elif pr in ("book", "ledger"):
            d.rectangle(box(hx - 24, hy - 26, hx + 24, hy + 18), fill=(122, 60, 40), outline=ink, width=int(3 * s))
        elif pr in ("torch",):
            d.rectangle(box(hx - 4, hy - 60, hx + 4, hy + 36), fill=(122, 82, 51))
            d.ellipse(box(hx - 14, hy - 94, hx + 14, hy - 56), fill=(240, 150, 40), outline=(200, 80, 20), width=int(2 * s))
        elif pr in ("coin", "coins", "purse", "bag", "money_bag", "sack"):
            d.ellipse(box(hx - 24, hy - 20, hx + 24, hy + 26), fill=(160, 120, 60), outline=ink, width=int(3 * s))
            d.text((hx * s, (hy + 4) * s), "$", font=font(int(26 * s), False), fill=(240, 220, 120), anchor="mm")
        elif pr in ("hammer", "axe", "tool", "mallet"):
            d.rectangle(box(hx - 4, hy - 100, hx + 4, hy + 24), fill=(122, 82, 51))
            d.rectangle(box(hx - 26, hy - 112, hx + 22, hy - 82), fill=(89, 97, 107), outline=ink, width=int(2 * s))
        elif pr in ("banner", "flag", "standard"):
            d.rectangle(box(hx - 3, hy - 150, hx + 3, hy + 40), fill=(122, 82, 51))
            d.polygon(pts((hx + 3, hy - 148), (hx + 60, hy - 130), (hx + 3, hy - 100)), fill=n["accent"], outline=ink)
        elif pr in ("cup", "goblet", "wine"):
            d.polygon(pts((hx - 16, hy - 20), (hx + 16, hy - 20), (hx + 8, hy + 14), (hx - 8, hy + 14)), fill=(224, 180, 58), outline=ink)
        else:  # any other object: a small box in the accent colour so the character still holds something
            d.rounded_rectangle(box(hx - 22, hy - 22, hx + 22, hy + 22), int(7 * s), fill=n["accent"], outline=ink, width=int(3 * s))
    return im.resize((px, px), Image.LANCZOS)
