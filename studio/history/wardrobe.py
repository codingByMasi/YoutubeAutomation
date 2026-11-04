# ruff: noqa: E501  (SVG path data)
"""Wardrobe for the history cast: the same character (face, body shape, name, badge letter, voice) in the costume of
the story's era.

An outfit only changes what is drawn *around* the recognisable base: headwear, a garment over the body, an optional
cape behind it, a collar, and (for characters without a signature prop) the prop. The eyes, mouth, skin, silhouette
and letter badge are never touched, so blinking, lip-sync and recognition keep working. Everything is code-drawn SVG,
no GPU and no extra files. Colours with `{body}` / `{dark}` use the character's own colour so each one stays
identifiable in every era. Original art only.
"""

from __future__ import annotations

import colorsys
import re

DEFAULT = "default"

# Props the outfit never replaces: the character's job is built around them.
SIGNATURE_PROPS = {"coin", "magnifier", "hammer", "hourglass", "telescope"}

# Each outfit: name, keywords (topic words that suggest it), and SVG parts. `head`/`cape`/`garment`/`collar`/`prop`
# are SVG fragments in the 400x400 character canvas; any may be "" (nothing changes for that part).
OUTFITS: dict[str, dict] = {
    "roman": {
        "name": "Ancient Rome",
        "keywords": ("rome", "roman", "caesar", "legion", "punic", "carthage", "hannibal", "augustus", "republic", "gladiator", "pompey", "senate"),
        "cape": '<path d="M128 214 L96 350 Q200 372 304 350 L272 214Z" fill="#b3282d"/>',
        "garment": '<rect x="130" y="224" width="140" height="14" fill="#a8adb5"/><rect x="130" y="244" width="140" height="14" fill="#9aa0a9"/><rect x="130" y="264" width="140" height="14" fill="#a8adb5"/><rect x="130" y="320" width="140" height="44" fill="#b3282d"/><path d="M146 320 V364 M170 320 V364 M194 320 V364 M218 320 V364 M242 320 V364 M262 320 V364" stroke="#7d1a1e" stroke-width="3"/>',
        "collar": '<rect x="150" y="212" width="100" height="12" rx="6" fill="#e0b43a"/>',
        "head": '<path d="M114 140 Q200 36 286 140Z" fill="#b0b6bf"/><rect x="108" y="134" width="184" height="14" rx="6" fill="#8a919b"/><path d="M186 58 Q200 20 214 58 L214 96 H186Z" fill="#b3282d"/><path d="M114 140 Q104 190 128 200 L130 150Z M286 140 Q296 190 272 200 L270 150Z" fill="#9aa0a9"/>',
        "prop": '<rect x="296" y="204" width="62" height="96" rx="10" fill="#b3282d" stroke="#7d1a1e" stroke-width="5"/><circle cx="327" cy="252" r="12" fill="#e0b43a"/>',
    },
    "greek": {
        "name": "Ancient Greece",
        "keywords": ("greece", "greek", "athens", "sparta", "spartan", "alexander", "persian wars", "marathon", "thermopylae", "pericles", "macedon"),
        "cape": '<path d="M132 214 L104 336 Q200 352 296 336 L268 214Z" fill="#c9332c"/>',
        "garment": '<rect x="130" y="212" width="140" height="150" fill="#f4efe2"/><path d="M130 340 H270 M130 348 H270" stroke="{body}" stroke-width="6"/><path d="M130 352 h14 v-8 h14 v8 h14 v-8 h14 v8 h14 v-8 h14 v8 h14 v-8 h14 v8" stroke="{dark}" stroke-width="3" fill="none"/>',
        "collar": '<path d="M150 216 Q200 244 250 216" stroke="{body}" stroke-width="10" fill="none"/>',
        "head": '<path d="M112 140 Q200 32 288 140Z" fill="#c79a3b"/><rect x="108" y="136" width="184" height="12" rx="6" fill="#a87f2a"/><path d="M200 36 Q130 20 112 96 Q150 60 200 66 Q250 60 288 96 Q270 20 200 36Z" fill="#c9332c"/>',
        "prop": '<rect x="330" y="120" width="8" height="230" rx="3" fill="#7a5233"/><path d="M334 96 L346 130 L322 130Z" fill="#b8c0cc"/>',
    },
    "viking": {
        "name": "Norse / Viking",
        "keywords": ("viking", "norse", "norway", "scandinav", "odin", "thor", "valhalla", "ragnar", "danelaw", "longship", "iceland", "lindisfarne", "saga"),
        "cape": '<path d="M126 214 L94 346 Q200 370 306 346 L274 214Z" fill="#6b4a2f"/><path d="M96 340 Q200 366 304 340 L306 350 Q200 376 94 350Z" fill="#e9dcc3"/>',
        "garment": '<rect x="130" y="244" width="140" height="120" fill="{body}"/><rect x="130" y="300" width="140" height="10" fill="#3b2c1c"/><circle cx="200" cy="305" r="7" fill="#e0b43a"/><path d="M130 244 H270" stroke="{dark}" stroke-width="6"/>',
        "collar": '<path d="M128 214 Q200 262 272 214 L276 230 Q200 290 124 230Z" fill="#e9dcc3"/><path d="M134 222 l6 12 M156 232 l4 12 M244 232 l-4 12 M266 222 l-6 12" stroke="#bfae8b" stroke-width="3"/>',
        "head": '<path d="M114 142 Q200 40 286 142Z" fill="#8c96a3"/><rect x="108" y="136" width="184" height="12" rx="6" fill="#6b7480"/><rect x="195" y="128" width="10" height="64" rx="3" fill="#6b7480"/><path d="M200 70 V132" stroke="#59616b" stroke-width="5"/><path d="M104 150 Q92 200 108 236 M296 150 Q308 200 292 236" stroke="#c79a3b" stroke-width="12" fill="none" stroke-linecap="round"/>',
        "prop": '<circle cx="334" cy="262" r="40" fill="#a8742f" stroke="#5d3b16" stroke-width="6"/><circle cx="334" cy="262" r="12" fill="#b8c0cc"/><path d="M334 222 V302 M294 262 H374" stroke="#5d3b16" stroke-width="4"/>',
    },
    "medieval": {
        "name": "Medieval",
        "keywords": ("medieval", "middle ages", "crusade", "knight", "feudal", "castle", "plague", "black death", "charlemagne", "norman", "hundred years", "magna carta", "monastery"),
        "cape": "",
        "garment": '<rect x="130" y="212" width="140" height="152" fill="{body}"/><path d="M200 212 V364" stroke="{dark}" stroke-width="5"/><rect x="130" y="324" width="140" height="40" fill="{dark}"/><path d="M130 326 H270" stroke="#e0b43a" stroke-width="5"/><rect x="130" y="296" width="140" height="10" fill="#e0b43a" opacity="0.9"/>',
        "collar": '<path d="M148 214 Q200 240 252 214 L252 226 Q200 252 148 226Z" fill="#f1ece0"/>',
        "head": '<path d="M112 140 Q200 40 288 140 Q250 112 200 112 Q150 112 112 140Z" fill="#8b2f45"/><path d="M104 150 Q92 214 126 224 Q114 180 128 146Z M296 150 Q308 214 274 224 Q286 180 272 146Z" fill="#6b2233"/><path d="M118 134 Q200 100 282 134" stroke="#e0b43a" stroke-width="6" fill="none"/>',
        "prop": '<rect x="298" y="236" width="62" height="50" rx="6" fill="#6b3a1f" stroke="#e0b43a" stroke-width="4"/><path d="M304 244 H354 M304 266 H354" stroke="#f1e4c4" stroke-width="4"/>',
    },
    "desert": {
        "name": "Desert / Silk Road",
        "keywords": ("arab", "caliph", "islamic", "baghdad", "desert", "silk road", "caravan", "ottoman", "mamluk", "bedouin", "saladin", "mongol", "timur", "persia", "sultan", "mecca", "sahara"),
        "cape": "",
        "garment": '<rect x="130" y="212" width="140" height="152" fill="#f1ece0"/><rect x="130" y="212" width="140" height="22" fill="{body}"/><path d="M130 340 H270" stroke="{body}" stroke-width="8"/><path d="M130 352 H270" stroke="{dark}" stroke-width="4"/><path d="M200 234 V300" stroke="#d8cfb8" stroke-width="3"/>',
        "collar": '<path d="M110 150 Q86 214 124 250 Q130 200 140 152Z M290 150 Q314 214 276 250 Q270 200 260 152Z" fill="#f4efe2"/>',
        "head": '<path d="M110 140 Q200 36 290 140 Q250 104 200 104 Q150 104 110 140Z" fill="#f4efe2"/><path d="M100 140 Q84 200 106 250 Q124 190 128 142Z M300 140 Q316 200 294 250 Q276 190 272 142Z" fill="#f4efe2" stroke="#d8cfb8" stroke-width="3"/><path d="M124 118 Q200 90 276 118" stroke="#2b2b3d" stroke-width="9" fill="none" stroke-linecap="round"/>',
        "prop": '<rect x="334" y="220" width="8" height="120" rx="3" fill="#7a5233"/><path d="M326 216 H350 L346 188 H330Z" fill="#e0b43a" stroke="#a9811c" stroke-width="3"/><circle cx="338" cy="204" r="6" fill="#ffd36b"/>',
    },
    "egyptian": {
        "name": "Ancient Egypt",
        "keywords": ("egypt", "pharaoh", "pyramid", "nile", "cleopatra", "tutankhamun", "ramses", "sphinx", "mesopotamia", "babylon", "sumer"),
        "cape": "",
        "garment": '<rect x="130" y="300" width="140" height="64" fill="#f4efe2"/><path d="M130 300 H270" stroke="#e0b43a" stroke-width="8"/><path d="M148 312 V364 M170 312 V364 M192 312 V364 M214 312 V364 M236 312 V364 M256 312 V364" stroke="#d8cfb8" stroke-width="3"/>',
        "collar": '<path d="M130 214 Q200 288 270 214 Q200 258 130 214Z" fill="#e0b43a"/><path d="M146 226 Q200 276 254 226" stroke="#2f6fa8" stroke-width="7" fill="none"/><path d="M156 238 Q200 276 244 238" stroke="#c9332c" stroke-width="5" fill="none"/>',
        "head": '<path d="M108 146 Q200 36 292 146 L276 244 Q258 240 252 224 L252 150 Q200 112 148 150 L148 224 Q142 240 124 244Z" fill="#e0b43a"/><path d="M130 100 Q200 70 270 100 M122 118 Q200 88 278 118 M116 136 Q200 106 284 136" stroke="#2f6fa8" stroke-width="8" fill="none"/><path d="M200 70 q-10 -26 0 -40 q10 14 0 40Z" fill="#c9332c"/>',
        "prop": '<rect x="334" y="196" width="8" height="150" rx="3" fill="#e0b43a"/><ellipse cx="338" cy="184" rx="14" ry="20" fill="none" stroke="#e0b43a" stroke-width="7"/><path d="M322 214 H354" stroke="#e0b43a" stroke-width="7" stroke-linecap="round"/>',
    },
    "samurai": {
        "name": "Feudal Japan",
        "keywords": ("japan", "samurai", "shogun", "edo", "tokugawa", "meiji", "ninja", "sengoku", "kyoto", "tokyo", "nobunaga", "china", "han dynasty", "ming", "qing", "tang dynasty", "dynasty", "imperial china", "korea"),
        "cape": "",
        "garment": '<rect x="130" y="212" width="140" height="152" fill="{body}"/><path d="M130 236 H270 M130 258 H270 M130 280 H270 M130 302 H270" stroke="#e0b43a" stroke-width="4"/><path d="M158 212 V364 M200 212 V364 M242 212 V364" stroke="{dark}" stroke-width="3"/><rect x="130" y="322" width="140" height="12" fill="#2b2b3d"/>',
        "collar": '<path d="M120 212 H280 L292 242 H108Z" fill="{dark}"/><path d="M126 222 H274" stroke="#e0b43a" stroke-width="4"/>',
        "head": '<path d="M110 142 Q200 38 290 142Z" fill="#2b2b3d"/><path d="M104 140 Q116 196 140 214 L140 150Z M296 140 Q284 196 260 214 L260 150Z" fill="{dark}"/><rect x="104" y="134" width="192" height="12" rx="5" fill="#e0b43a"/><path d="M130 70 Q200 -6 270 70 Q200 38 130 70Z" fill="#e0b43a"/>',
        "prop": '<rect x="324" y="150" width="8" height="190" rx="3" fill="#2b2b3d"/><path d="M322 214 H334 L336 150 H320Z" fill="#c9332c"/>',
    },
    "renaissance": {
        "name": "Renaissance",
        "keywords": ("renaissance", "medici", "florence", "venice", "leonardo", "michelangelo", "gutenberg", "printing press", "machiavelli", "fugger", "bank", "banking", "tudor", "elizabeth", "henry viii", "reformation", "luther"),
        "cape": '<path d="M130 214 L106 336 Q200 354 294 336 L270 214Z" fill="{dark}"/>',
        "garment": '<rect x="130" y="212" width="140" height="152" fill="{body}"/><path d="M200 212 V364" stroke="#e0b43a" stroke-width="4"/><path d="M146 240 H190 M146 262 H190 M210 240 H254 M210 262 H254 M146 284 H190 M210 284 H254" stroke="{dark}" stroke-width="6" stroke-linecap="round"/><circle cx="200" cy="312" r="5" fill="#e0b43a"/><circle cx="200" cy="336" r="5" fill="#e0b43a"/>',
        "collar": '<ellipse cx="200" cy="222" rx="76" ry="22" fill="#f4efe2" stroke="#d8cfb8" stroke-width="4"/><path d="M146 222 q8 -10 16 0 q8 -10 16 0 q8 -10 16 0 q8 -10 16 0 q8 -10 16 0 q8 -10 16 0 q8 -10 16 0" stroke="#d8cfb8" stroke-width="3" fill="none"/>',
        "head": '<ellipse cx="200" cy="118" rx="96" ry="24" fill="{dark}"/><path d="M130 118 Q200 24 270 118Z" fill="{body}"/><path d="M262 92 Q330 34 340 96 Q300 76 276 112Z" fill="#f4efe2" stroke="#d8cfb8" stroke-width="3"/>',
        "prop": '<rect x="326" y="196" width="8" height="140" rx="3" fill="#7a5233"/><path d="M330 192 Q356 156 366 196 Q346 178 332 206Z" fill="#f4efe2" stroke="#b89968" stroke-width="3"/><rect x="304" y="250" width="56" height="40" rx="5" fill="#f1e4c4" stroke="#b89968" stroke-width="4"/>',
    },
    "sail": {
        "name": "Age of Sail",
        "keywords": ("pirate", "navy", "age of sail", "colonial", "east india", "trafalgar", "armada", "empire", "slave trade", "columbus", "magellan", "revolution", "napoleon", "waterloo", "american revolution", "french revolution", "trade company", "opium"),
        "cape": "",
        "garment": '<rect x="130" y="212" width="140" height="152" fill="{body}"/><path d="M130 212 L200 300 L270 212 L270 230 L200 330 L130 230Z" fill="{dark}"/><path d="M200 300 V364" stroke="{dark}" stroke-width="5"/><circle cx="172" cy="316" r="5" fill="#e0b43a"/><circle cx="172" cy="338" r="5" fill="#e0b43a"/><circle cx="228" cy="316" r="5" fill="#e0b43a"/><circle cx="228" cy="338" r="5" fill="#e0b43a"/><rect x="130" y="354" width="140" height="10" fill="#f4efe2"/>',
        "collar": '<path d="M162 212 L200 252 L238 212 L226 206 L200 232 L174 206Z" fill="#f4efe2"/>',
        "head": '<path d="M100 138 L200 40 L300 138 Q250 112 200 112 Q150 112 100 138Z" fill="#1f2d4d"/><path d="M100 138 Q200 108 300 138 L300 148 Q200 118 100 148Z" fill="#e0b43a"/><circle cx="200" cy="96" r="9" fill="#f4efe2"/>',
        "prop": '<rect x="296" y="236" width="64" height="18" rx="7" fill="#b8892b" transform="rotate(-24 296 244)"/><rect x="344" y="212" width="16" height="22" rx="6" fill="#7a5233" transform="rotate(-24 344 222)"/>',
    },
    "modern": {
        "name": "Modern 1900s",
        "keywords": ("world war", "wwi", "wwii", "ww1", "ww2", "great war", "trench", "nazi", "soviet", "cold war", "1914", "1939", "industrial", "railway", "telegraph", "great depression", "stock market", "oil", "cold-war", "vietnam", "korean war"),
        "cape": "",
        "garment": '<rect x="130" y="212" width="140" height="152" fill="{body}"/><rect x="130" y="300" width="140" height="12" fill="#3b2c1c"/><rect x="190" y="298" width="20" height="16" fill="#e0b43a"/><rect x="142" y="238" width="34" height="30" fill="{dark}"/><rect x="224" y="238" width="34" height="30" fill="{dark}"/><path d="M200 212 V364" stroke="{dark}" stroke-width="4"/>',
        "collar": '<path d="M158 212 L200 244 L242 212 L234 206 L200 226 L166 206Z" fill="{dark}"/>',
        "head": '<path d="M108 140 Q200 44 292 140 Q200 128 108 140Z" fill="#6f7a52"/><path d="M96 142 Q200 118 304 142 L298 154 Q200 130 102 154Z" fill="#59623f"/>',
        "prop": '<rect x="300" y="240" width="64" height="44" rx="4" fill="#d8c9a3" stroke="#8a7a5a" stroke-width="4"/><path d="M310 256 L328 248 L340 266 L354 254" stroke="#8a7a5a" stroke-width="3" fill="none"/>',
    },
}

ERAS = tuple(OUTFITS)


def _dark(hex_colour: str, factor: float = 0.68) -> str:
    """A darker shade of a #RRGGBB colour (same hue) for trims, seams and shadows."""
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb(h, s, v * factor)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def known(outfit: str | None) -> bool:
    """True for the default outfit (None, '' or 'default') and every era in `OUTFITS`."""
    return (outfit or DEFAULT) == DEFAULT or outfit in OUTFITS


def parts(outfit: str | None, body: str, prop: str = "none") -> dict[str, str] | None:
    """SVG fragments for an outfit worn by a character with colour `body` and prop `prop`; None for the default outfit.

    Keys: cape, garment, collar, head, prop (prop is "" when the character keeps their own). Unknown outfits raise ValueError."""
    if not outfit or outfit == DEFAULT:
        return None
    if outfit not in OUTFITS:
        raise ValueError(f"outfit {outfit!r} not in {[DEFAULT, *ERAS]}")
    o, dark = OUTFITS[outfit], _dark(body)

    def swap(s: str) -> str:
        return s.replace("{body}", body).replace("{dark}", dark)

    keep_prop = prop in SIGNATURE_PROPS
    return {"cape": swap(o["cape"]), "garment": swap(o["garment"]), "collar": swap(o["collar"]),
            "head": swap(o["head"]), "prop": "" if keep_prop else swap(o["prop"])}


def guess_era(text: str) -> str:
    """Best-matching era id for a topic/title/narration text, or the default when nothing matches.

    Whole words or word starts only, so 'bank' does not fire inside 'embankment'. Ties go to the first era listed."""
    low = (text or "").lower()
    best, best_n = DEFAULT, 0
    for eid, o in OUTFITS.items():
        n = sum(1 for k in o["keywords"] if re.search(rf"(?<![a-z]){re.escape(k)}", low))
        if n > best_n:
            best, best_n = eid, n
    return best


def era_for(seg: dict, pkg: dict | None = None) -> str:
    """The outfit for one segment: its own `era`, else the video's `era`, else a guess from the title, else default.

    Old scripts have no `era` and a title that matches nothing, so they keep the default look."""
    for src in (seg, pkg or {}):
        e = str(src.get("era") or "").strip().lower()
        if e:
            return e if known(e) else DEFAULT
    return guess_era(_title_of(pkg or {}))


def _title_of(pkg: dict) -> str:
    """The video's title for era guessing: `title`, else the picked entry of `titles`, else the topic.
    (Scripts store `titles` and `topic`, not `title`, so a guess from `title` alone never found anything.)"""
    if pkg.get("title"):
        return str(pkg["title"])
    titles = [t for t in pkg.get("titles") or [] if isinstance(t, dict) and t.get("text")]
    pick = next((t for t in titles if t.get("is_pick")), titles[0] if titles else None)
    return str(pick["text"] if pick else pkg.get("topic") or "")


def prompt_line() -> str:
    """One line for the planner and script prompts that lists the eras the writer may choose."""
    return ("Costumes: the cast keeps its face, name and voice but dresses for the story. Set a top-level `era` "
            f"(one of {', '.join(ERAS)}, or {DEFAULT}) and, only when the story jumps to another period, an `era` on "
            "that segment. Leave it out to let the studio guess from the title.")
