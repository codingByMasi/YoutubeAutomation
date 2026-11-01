"""Channel identity: niche statement, mascot (host character), visual theme and playlists.

Every field lives on a channel profile (see `channels`), so each channel can have its own look and cast.
Nothing here is tied to one channel: `PRESETS` are starting points the owner can apply and then edit.
The mascot is drawn procedurally (no art files needed); drop your own art into assets to override it.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from studio.errors import StudioError

MASCOT_KINDS = ("coin", "owl", "robot")
MOODS = ("happy", "surprised", "thinking")
CARD_STYLES = ("none", "card")  # intro / outro: nothing, or a short branded title/sign-off card
MASCOT_FIELDS = {"name": "", "kind": "coin", "color": "", "look": "", "personality": "", "catchphrase": "",
                 "intro_line": "", "outro_line": "", "on_thumbnail": True}
THEME_FIELDS = {"bg": "", "accent": "", "accent2": "", "text": "", "heading_font": "", "intro_style": "none",
                "outro_style": "card", "thumbnail_style": "", "motion": ""}
PLAYLIST_FIELDS = {"name": "", "description": "", "title_pattern": "", "topics": [], "youtube_id": ""}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

PRESETS: dict[str, dict] = {
    "finance-stories": {
        "label": "Finance and business stories (e.g. how a founder went from near bankruptcy to richest)",
        "niche": "True business stories: how famous companies and founders won, nearly died and came back, "
                 "told with real numbers",
        "niche_statement": "Business stories with receipts: how companies and founders really made (and lost) "
                           "their money, explained in 8-12 minutes with sourced numbers and no hype.",
        "tagline": "Follow the money.",
        "mascot": {
            "name": "Penny", "kind": "coin", "color": "#F5B700",
            "look": "A small gold coin with big round eyes, a tiny smile and a shine on one edge; "
                    "expressive, never human.",
            "personality": "Curious, a little cheeky, always asks 'but where did the money come from?'. Skeptical "
                           "of hype; admits when a number is an estimate.",
            "catchphrase": "Follow the money.",
            "intro_line": "", "outro_line": "That's the story. Follow the money, and I'll see you in the next one.",
            "on_thumbnail": True,
        },
        "theme": {
            "bg": "#0B1F3A", "accent": "#F5B700", "accent2": "#38BDF8", "text": "#F8FAFC",
            "heading_font": "", "intro_style": "none", "outro_style": "card",
            "thumbnail_style": "one huge number or a before/after, Penny reacting in the corner",
            "motion": "slow push-ins, charts that build, quick whoosh cuts",
        },
        "playlists": [
            {"name": "Comeback Stories", "title_pattern": "How {name} went from {low} to {high}",
             "description": "Founders and companies that nearly died, then won.",
             "topics": ["How Elon Musk went from near bankruptcy to the richest person in the world",
                        "How Apple went from 90 days of cash to the biggest company on Earth",
                        "How Nvidia went from a gaming chip maker to the world's most valuable company",
                        "How Netflix beat Blockbuster after being laughed out of the room"]},
            {"name": "How Giants Make Money", "title_pattern": "How {company} actually makes money",
             "description": "Plain-English business models, with the real revenue split.",
             "topics": ["How Costco makes money when it sells so cheap",
                        "How Spotify makes money while paying artists billions",
                        "How Amazon makes money (it is not retail)",
                        "How Visa makes money without lending a cent"]},
            {"name": "Biggest Business Mistakes", "title_pattern": "The ${amount} mistake that sank {company}",
             "description": "Expensive, well-documented blunders and what they teach.",
             "topics": ["Why Kodak invented the digital camera and still went bankrupt",
                        "The $20 billion mistake: how Quibi burned its cash in six months",
                        "How WeWork went from $47 billion to bankrupt",
                        "Why Blockbuster turned down buying Netflix for $50 million"]},
        ],
    },
    "explainer": {
        "label": "General explainer (neutral starting point for any niche)",
        "niche": "", "niche_statement": "", "tagline": "Let's figure it out.",
        "mascot": {"name": "Ollie", "kind": "owl", "color": "#8B5E3C",
                   "look": "A round brown owl with large glasses-like eye rings.",
                   "personality": "Patient, curious, explains things step by step.",
                   "catchphrase": "Let's figure it out.", "intro_line": "",
                   "outro_line": "Thanks for watching. See you in the next one.", "on_thumbnail": True},
        "theme": {"bg": "#14213D", "accent": "#FCA311", "accent2": "#7DD3FC", "text": "#F8FAFC",
                  "heading_font": "", "intro_style": "none", "outro_style": "card", "thumbnail_style": "",
                  "motion": ""},
        "playlists": [],
    },
}


# ---------- validation ----------
def _color(value: str, field: str) -> str:
    value = (value or "").strip()
    if value and not _HEX.match(value):
        raise StudioError(f"'{value}' is not a valid colour for {field}.", "Colours are written like #F5B700.",
                          f"Fix the {field} value.")
    return value


def clean_mascot(values: dict | None) -> dict:
    """Keep known mascot fields; check kind and colour. An empty dict means 'no mascot'."""
    if not values:
        return {}
    out = {k: values.get(k, d) for k, d in MASCOT_FIELDS.items()}
    out["kind"] = str(out["kind"] or "coin").strip().lower()
    if out["kind"] not in MASCOT_KINDS:
        raise StudioError(f"'{out['kind']}' is not a mascot kind.", f"Choose one of: {', '.join(MASCOT_KINDS)}.",
                          "Change mascot kind.")
    out["color"] = _color(out["color"], "mascot colour")
    out["on_thumbnail"] = bool(out["on_thumbnail"])
    for k in ("name", "look", "personality", "catchphrase", "intro_line", "outro_line"):
        out[k] = str(out[k] or "").strip()
    if not out["name"]:
        raise StudioError("The mascot needs a name.", "The name was empty.", "Give it a short name, e.g. Penny.")
    return out


def clean_theme(values: dict | None) -> dict:
    """Keep known theme fields; check colours and intro/outro styles. Empty means 'use the channel colours'."""
    if not values:
        return {}
    out = {k: values.get(k, d) for k, d in THEME_FIELDS.items()}
    for k in ("bg", "accent", "accent2", "text"):
        out[k] = _color(out[k], f"theme {k}")
    for k in ("intro_style", "outro_style"):
        out[k] = str(out[k] or "none").strip().lower()
        if out[k] not in CARD_STYLES:
            raise StudioError(f"'{out[k]}' is not a valid theme {k}.", f"Choose one of: {', '.join(CARD_STYLES)}.",
                              f"Change theme {k}.")
    for k in ("heading_font", "thumbnail_style", "motion"):
        out[k] = str(out[k] or "").strip()
    return out


def clean_playlists(values: list | None) -> list[dict]:
    """Keep known playlist fields; names must be unique. Topics may be a list or one per line."""
    out, seen = [], set()
    for item in values or []:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        p = {k: item.get(k, d) for k, d in PLAYLIST_FIELDS.items()}
        for k in ("name", "description", "title_pattern", "youtube_id"):
            p[k] = str(p[k] or "").strip()
        topics = p["topics"].splitlines() if isinstance(p["topics"], str) else p["topics"]
        p["topics"] = [str(t).strip() for t in topics if str(t).strip()]
        if p["name"].lower() in seen:
            raise StudioError(f"Two playlists are called '{p['name']}'.", "Playlist names must be different.",
                              "Rename one of them.")
        seen.add(p["name"].lower())
        out.append(p)
    return out


def preset(name: str) -> dict:
    """A deep copy of a preset, or a helpful error."""
    if name not in PRESETS:
        raise StudioError(f"Unknown identity preset '{name}'.", f"Known presets: {', '.join(PRESETS)}.",
                          "Pick one of them.")
    return copy.deepcopy(PRESETS[name])


def preset_fields(name: str) -> dict:
    """Profile fields to set when applying a preset (blank niche is left alone)."""
    p = preset(name)
    fields = {k: p[k] for k in ("niche", "niche_statement", "tagline", "mascot", "theme", "playlists") if p.get(k)}
    for key in ("mascot", "theme"):
        fields[key] = copy.deepcopy(p[key])
    return fields


# ---------- colours ----------
def colors(profile: dict) -> dict:
    """The theme as concrete colours: bg, accent, accent2, text. Missing ones fall back to the brand colours."""
    t = profile.get("theme") or {}
    return {"bg": t.get("bg") or profile.get("brand_primary") or "#0B1F3A",
            "accent": t.get("accent") or profile.get("brand_accent") or "#F5B700",
            "accent2": t.get("accent2") or "#38BDF8", "text": t.get("text") or "#F8FAFC"}


def has_theme(profile: dict) -> bool:
    """True if the owner set theme colours (so they override the type default palette)."""
    t = profile.get("theme") or {}
    return bool(t.get("bg") or t.get("accent"))


# ---------- prompt brief ----------
def brief(profile: dict) -> str:
    """Text for script/series/title prompts: niche statement, host persona, playlists. Empty if nothing is set."""
    lines = []
    if profile.get("niche_statement"):
        lines.append(f"Positioning: {profile['niche_statement']}")
    m = profile.get("mascot") or {}
    if m:
        lines.append(
            f"Mascot/host persona: {m['name']} ({m['look'] or 'a friendly character'}). Personality: "
            f"{m['personality'] or 'friendly'}. {m['name']} is a recurring character who reacts and asks the "
            f"viewer's questions; they never state facts or figures (the narration and sources do)."
            + (f" Signature line, used at most once per video, usually at the end: \"{m['catchphrase']}\"."
               if m["catchphrase"] else ""))
    if profile.get("playlists"):
        pl = "; ".join(f"{p['name']}" + (f" (titles like \"{p['title_pattern']}\")" if p["title_pattern"] else "")
                       for p in profile["playlists"])
        lines.append(f"Playlists (every video belongs to exactly one): {pl}.")
    return " ".join(lines)


# ---------- playlists <-> series ----------
def sync_playlists(root: Path, profile: dict) -> list[str]:
    """Create a series for each profile playlist that has none yet; returns the names created.

    Series are the studio's playlist planner (ordered videos, next-video end screens). Existing series are never
    changed, so edits made in the app are kept."""
    from studio.growth import series

    have = {s["name"].lower() for s in series.load(root)}
    made = []
    for p in profile.get("playlists") or []:
        if p["name"].lower() in have:
            series.set_meta(root, p["name"], youtube_id=p["youtube_id"], title_pattern=p["title_pattern"])
            continue
        series.create(root, p["name"], p["description"], p["topics"])
        series.set_meta(root, p["name"], youtube_id=p["youtube_id"], title_pattern=p["title_pattern"])
        made.append(p["name"])
    return made


def playlist_id_for(root: Path, video_id: int) -> str | None:
    """The YouTube playlist id for the series a video belongs to, or None when it has none/unknown."""
    from studio.growth import series

    pos = series.position(root, video_id)
    return (pos[0].get("youtube_id") or None) if pos else None


# ---------- drawing ----------
def _font(profile: dict, assets: Path | None, size: int) -> ImageFont.FreeTypeFont:
    from studio.providers import brand

    custom = (profile.get("theme") or {}).get("heading_font", "")
    if custom and assets and (assets / "fonts" / custom).exists():
        return ImageFont.truetype(str(assets / "fonts" / custom), size)
    return ImageFont.truetype(brand.font_path(assets), size)


def _face(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, mood: str) -> None:
    ex, ey, er = r * 0.34, r * 0.1, r * 0.22
    for sx in (-1, 1):
        x = cx + sx * ex
        d.ellipse([x - er, cy - ey - er, x + er, cy - ey + er], fill="#FFFFFF", outline="#1B1B1B",
                  width=max(2, int(r * 0.03)))
        px, py = {"happy": (0, 0.05), "surprised": (0, 0), "thinking": (0.35, -0.3)}[mood]
        pr = er * (0.62 if mood == "surprised" else 0.5)
        d.ellipse([x + px * er - pr, cy - ey + py * er - pr, x + px * er + pr, cy - ey + py * er + pr], fill="#1B1B1B")
    my, w = cy + r * 0.42, max(3, int(r * 0.05))
    if mood == "happy":
        d.arc([cx - r * 0.3, my - r * 0.22, cx + r * 0.3, my + r * 0.18], 15, 165, fill="#1B1B1B", width=w)
    elif mood == "surprised":
        d.ellipse([cx - r * 0.1, my - r * 0.08, cx + r * 0.1, my + r * 0.14], fill="#1B1B1B")
    else:
        d.line([cx - r * 0.18, my, cx + r * 0.18, my - r * 0.04], fill="#1B1B1B", width=w)


def mascot_image(mascot: dict, size: int = 400, mood: str = "happy") -> Image.Image:
    """Square RGBA picture of the mascot (transparent background). `mood`: happy, surprised or thinking."""
    mood = mood if mood in MOODS else "happy"
    big = size * 3  # draw large, then shrink for smooth edges
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = big / 2, big * 0.42
    base = mascot.get("color") or "#F5B700"
    dark = _shade(base, 0.72)
    kind = mascot.get("kind", "coin")
    if kind == "owl":
        d.polygon([(c - r * 0.8, c - r * 0.65), (c - r * 0.55, c - r * 1.1), (c - r * 0.2, c - r * 0.8)], fill=dark)
        d.polygon([(c + r * 0.8, c - r * 0.65), (c + r * 0.55, c - r * 1.1), (c + r * 0.2, c - r * 0.8)], fill=dark)
        d.ellipse([c - r * 0.95, c - r * 0.85, c + r * 0.95, c + r * 1.0], fill=base, outline=dark, width=big // 60)
        d.polygon([(c - r * 0.1, c + r * 0.12), (c + r * 0.1, c + r * 0.12), (c, c + r * 0.34)], fill="#F59E0B")
        _face(d, c, c - r * 0.1, r * 0.9, mood)
    elif kind == "robot":
        d.line([c, c - r * 1.0, c, c - r * 0.75], fill=dark, width=big // 40)
        d.ellipse([c - r * 0.1, c - r * 1.12, c + r * 0.1, c - r * 0.92], fill=dark)
        d.rounded_rectangle([c - r * 0.9, c - r * 0.78, c + r * 0.9, c + r * 0.85], radius=r * 0.25, fill=base,
                            outline=dark, width=big // 60)
        _face(d, c, c - r * 0.05, r * 0.95, mood)
    else:  # coin
        d.ellipse([c - r, c - r, c + r, c + r], fill=dark)
        d.ellipse([c - r * 0.94, c - r * 0.97, c + r * 0.94, c + r * 0.9], fill=base)
        d.ellipse([c - r * 0.8, c - r * 0.82, c + r * 0.8, c + r * 0.76], outline=dark, width=big // 90)
        d.arc([c - r * 0.7, c - r * 0.72, c + r * 0.7, c + r * 0.66], 200, 260, fill="#FFFFFF", width=big // 50)
        _face(d, c, c - r * 0.06, r * 0.95, mood)
    return img.resize((size, size), Image.LANCZOS)


def _shade(hex_color: str, k: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"#{int(r * k):02X}{int(g * k):02X}{int(b * k):02X}"


def paste_mascot(img: Image.Image, profile: dict, size: int, corner: str = "tr", mood: str = "happy",
                 margin: int = 18) -> Image.Image:
    """Put the channel's mascot on an image (thumbnail). No-op when the channel has no mascot or turned it off."""
    m = profile.get("mascot") or {}
    if not m or not m.get("on_thumbnail", True):
        return img
    pic = mascot_image(m, size, mood)
    x = img.width - size - margin if "r" in corner else margin
    y = img.height - size - margin if "b" in corner else margin
    out = img.convert("RGBA")
    out.alpha_composite(pic, (x, y))
    return out.convert("RGB")


def card_image(profile: dict, kind: str, title: str = "", next_line: str = "", assets: Path | None = None,
               size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Branded intro ('intro') or sign-off ('outro') card in the channel's theme, with the mascot if there is one."""
    w, h = size
    col = colors(profile)
    img = Image.new("RGB", size, col["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 18, w, h], fill=col["accent"])
    m = profile.get("mascot") or {}
    left = w * 0.08
    if m:
        pic = mascot_image(m, int(h * 0.52), "happy" if kind == "outro" else "surprised")
        img.paste(pic, (int(w * 0.08), int(h * 0.24)), pic)
        left = w * 0.08 + h * 0.52 + w * 0.04
    big, small = _font(profile, assets, int(h * 0.09)), _font(profile, assets, int(h * 0.05))
    if kind == "intro":
        head, sub = title or profile.get("name", ""), profile.get("tagline", "")
    else:
        head = (m.get("outro_line") if m else "") or "Thanks for watching."
        sub = next_line or profile.get("tagline", "")
    y = h * 0.3
    for line in _wrap(d, head, big, w - left - w * 0.06)[:4]:
        d.text((left, y), line, font=big, fill=col["text"])
        y += h * 0.11
    for line in _wrap(d, sub, small, w - left - w * 0.06)[:3]:
        d.text((left, y + h * 0.03), line, font=small, fill=col["accent"])
        y += h * 0.065
    return img


def _wrap(d: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def card_clip_cmd(png: Path, seconds: float, out: Path) -> list[str]:
    """ffmpeg command turning a card picture into a short silent video clip."""
    return ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", f"{seconds:.2f}", "-r", "30", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]
