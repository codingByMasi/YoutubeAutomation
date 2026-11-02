# ruff: noqa: E501  (SVG path data)
"""The history channel's cast: recurring original characters, historical figures built from one body, scene rules.

Everything here is original. The reference videos were studied for structure only; do not trace or imitate any
existing channel's characters. SVGs follow the kids sprite contract (`studio/kids/sprites.py`): four groups
`eyes-open`, `eyes-closed`, `mouth-closed`, `mouth-open`, so `SpriteBank(user_dir=...)` can blink and lip-sync them.
"""

from __future__ import annotations

import re
from pathlib import Path

SCENE_TYPES = ("lectern", "skit", "map", "diagram", "easel", "archive", "calendar", "silhouette", "title")
MAX_SPEECH_LINES = 4
MAX_SPEECH_WORDS = 10
HEADWEAR = ("none", "fur_hat", "helmet", "crown", "turban", "cap", "hood", "laurel")
PROPS = ("none", "sword", "scroll", "shield", "staff", "coin", "banner")

# Recurring cast: one job each. `role` is what the writer may use the character for.
ROSTER: dict[str, dict] = {
    "quill": {"name": "Quill", "role": "host: stands at the lectern, opens and closes chapters, asks the chapter question",
              "body": "#2E7D87", "headwear": "laurel", "prop": "scroll", "badge": "Q"},
    "dusty": {"name": "Dusty", "role": "viewer stand-in: the ordinary person who asks what the viewer is thinking",
              "body": "#C9A66B", "headwear": "cap", "prop": "none", "badge": "D"},
    "vex": {"name": "Vizier Vex", "role": "the schemer: advisers, rival courtiers, anyone who quietly pulls strings",
            "body": "#5B3A7A", "headwear": "hood", "prop": "scroll", "badge": "V"},
    "blunder": {"name": "Captain Blunder", "role": "the overconfident officer: stands in for a doomed or foolish plan",
                "body": "#A33B3B", "headwear": "helmet", "prop": "sword", "badge": "B"},
    "coin": {"name": "Madame Coin", "role": "the treasurer: counts what a war, a tax or a trade really cost",
             "body": "#B8892B", "headwear": "turban", "prop": "coin", "badge": "C"},
    "dash": {"name": "Dash", "role": "the courier: delivers bad news and ends chapters on a cliffhanger",
             "body": "#6E8B3D", "headwear": "cap", "prop": "scroll", "badge": "R"},
}

# Faction colours for historical figures and map flags (one colour per side, kept for the whole video).
FACTION_COLORS = ["#C0392B", "#2471A3", "#1E8449", "#B7950B", "#7D3C98", "#CA6F1E", "#117A65", "#566573"]

_SKIN = "#F2D2B1"
_INK = "#2b2b3d"
_HEAD = {
    "none": "",
    "fur_hat": '<ellipse cx="200" cy="108" rx="82" ry="38" fill="#7a5233"/><ellipse cx="200" cy="124" rx="78" ry="14" fill="#e9dcc3"/>',
    "helmet": '<path d="M112 140 Q200 30 288 140 Z" fill="#8c96a3"/><rect x="108" y="136" width="184" height="14" rx="6" fill="#6b7480"/>',
    "crown": '<path d="M130 128 L146 74 L172 112 L200 66 L228 112 L254 74 L270 128 Z" fill="#e0b43a"/>',
    "turban": '<ellipse cx="200" cy="112" rx="90" ry="46" fill="#f1ece0"/><circle cx="200" cy="82" r="10" fill="#c0392b"/>',
    "cap": '<path d="M116 136 Q200 52 284 136 Z" fill="#4a5568"/><rect x="110" y="132" width="110" height="12" rx="6" fill="#39424f"/>',
    "hood": '<path d="M104 190 Q96 60 200 56 Q304 60 296 190 Q250 120 200 120 Q150 120 104 190 Z" fill="#3d2a52"/>',
    "laurel": '<path d="M120 128 Q160 92 200 96 Q240 92 280 128" stroke="#4f8a3c" stroke-width="12" fill="none" stroke-linecap="round"/>',
}
_PROP = {
    "none": "",
    "sword": '<rect x="318" y="190" width="10" height="130" fill="#b8c0cc"/><rect x="302" y="288" width="42" height="10" fill="#7a5233"/>',
    "scroll": '<rect x="300" y="236" width="70" height="44" rx="10" fill="#f1e4c4" stroke="#b89968" stroke-width="4"/>',
    "shield": '<path d="M300 220 H370 V270 Q335 316 300 270 Z" fill="#8c3b3b" stroke="#5d2626" stroke-width="5"/>',
    "staff": '<rect x="326" y="150" width="9" height="200" rx="4" fill="#7a5233"/><circle cx="330" cy="146" r="14" fill="#e0b43a"/>',
    "coin": '<circle cx="332" cy="262" r="28" fill="#e0b43a" stroke="#a9811c" stroke-width="5"/>',
    "banner": '<rect x="322" y="120" width="8" height="220" fill="#7a5233"/><path d="M330 126 H388 V196 H330 Z" fill="{color}"/>',
}


def build_svg(body: str = "#2E7D87", headwear: str = "none", prop: str = "none", badge: str = "",
              skin: str = _SKIN) -> str:
    """One character as SVG text (400x400) with the four sprite groups. Unknown headwear/prop raise ValueError."""
    if headwear not in HEADWEAR:
        raise ValueError(f"headwear {headwear!r} not in {list(HEADWEAR)}")
    if prop not in PROPS:
        raise ValueError(f"prop {prop!r} not in {list(PROPS)}")
    for v in (body, skin):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError(f"colour {v!r} must look like #RRGGBB")
    letter = re.sub(r"[^A-Za-z0-9]", "", badge)[:1].upper()
    badge_svg = (f'<circle cx="200" cy="292" r="22" fill="#fff"/><text x="200" y="301" text-anchor="middle" '
                 f'font-family="Arial,sans-serif" font-size="26" font-weight="700" fill="{_INK}">{letter}</text>'
                 if letter else "")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">\n'
        '<ellipse cx="200" cy="378" rx="96" ry="12" fill="#000" opacity="0.12"/>\n'
        f'<rect x="130" y="210" width="140" height="150" rx="52" fill="{body}"/>\n'
        f'<ellipse cx="118" cy="268" rx="20" ry="16" fill="{skin}"/><ellipse cx="282" cy="268" rx="20" ry="16" fill="{skin}"/>\n'
        f"{badge_svg}\n"
        f'<circle cx="200" cy="162" r="84" fill="{skin}"/>\n'
        f"{_HEAD[headwear]}\n"
        f"{_PROP[prop].replace('{color}', body)}\n"
        f'<g id="eyes-open"><ellipse cx="170" cy="160" rx="14" ry="18" fill="#fff"/><ellipse cx="230" cy="160" rx="14" ry="18" fill="#fff"/>'
        f'<circle cx="172" cy="163" r="8" fill="{_INK}"/><circle cx="232" cy="163" r="8" fill="{_INK}"/></g>\n'
        f'<g id="eyes-closed"><path d="M156 164 Q170 174 184 164" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/>'
        f'<path d="M216 164 Q230 174 244 164" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/></g>\n'
        f'<g id="mouth-closed"><path d="M178 206 Q200 220 222 206" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/></g>\n'
        f'<g id="mouth-open"><path d="M176 202 Q200 240 224 202 Z" fill="{_INK}"/></g>\n'
        "</svg>\n"
    )


def roster_svg(char_id: str) -> str:
    """SVG of a recurring character."""
    c = ROSTER[char_id]
    return build_svg(c["body"], c["headwear"], c["prop"], c["badge"])


def export_roster(dest: Path) -> list[Path]:
    """Write every recurring character as `<id>.svg` into `dest` (e.g. assets/history/characters/)."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for cid in ROSTER:
        f = dest / f"{cid}.svg"
        f.write_text(roster_svg(cid), encoding="utf-8")
        out.append(f)
    return out


def faction_color(index: int) -> str:
    """Colour for the n-th faction of a video (wraps)."""
    return FACTION_COLORS[index % len(FACTION_COLORS)]


def prompt_block(profile: dict) -> str:
    """Cast and depiction rules for the planner and script prompts ('' when the profile has no cast)."""
    dep = profile.get("depiction")
    if not profile.get("cast") or not dep:
        return ""
    lines = ["# Cast and depiction (original characters only; never imitate any other channel's characters)",
             "Recurring cast (use them for their job; add at most 2 new named figures per video):"]
    lines += [f"- {cid}: {c['name']}, {c['role']}" for cid, c in ROSTER.items()]
    lines.append("Historical figures: never a real likeness. Each gets a faction colour, a letter badge, one "
                 f"headwear from {list(HEADWEAR)} and one prop from {list(PROPS)}. Rules:")
    lines += [f"- {r}" for r in dep.get("rules", [])]
    lines.append(f"Scene types per segment: {', '.join(SCENE_TYPES)}. Add optional keys to each segment: `scene`, "
                 "`cast` (list of roster ids or figure names), `staging` (one sentence), `speech` (at most "
                 f"{MAX_SPEECH_LINES} on-screen lines of at most {MAX_SPEECH_WORDS} words, each "
                 '{"who": "...", "text": "..."}). Speech is invented dialogue: use it only for tone, never for quotes '
                 "you present as real; real quotes go in the narration with a source.")
    return "\n".join(lines)


def scene_problems(pkg: dict, profile: dict | None = None) -> list[str]:
    """Plain-language problems with the optional scene/cast/speech keys of each segment."""
    out: list[str] = []
    run, prev = 0, None
    for i, s in enumerate(pkg.get("segments") or [], 1):
        scene = s.get("scene")
        if scene is None:
            run, prev = 0, None
            continue
        if scene not in SCENE_TYPES:
            out.append(f"segment {i}: scene {scene!r} is not one of {list(SCENE_TYPES)}")
        run = run + 1 if scene == prev else 1
        prev = scene
        if run >= 3 and scene not in ("map", "diagram"):
            out.append(f"segments {i - 2}-{i}: three {scene!r} scenes in a row; change one to a different scene type")
        speech = s.get("speech") or []
        if scene != "skit" and speech:
            out.append(f"segment {i}: speech lines only belong to a 'skit' scene")
        if len(speech) > MAX_SPEECH_LINES:
            out.append(f"segment {i}: {len(speech)} speech lines; keep it to {MAX_SPEECH_LINES}")
        for line in speech:
            n = len(str(line.get("text", "")).split()) if isinstance(line, dict) else 99
            if n > MAX_SPEECH_WORDS:
                out.append(f"segment {i}: a speech line has {n} words; keep each under {MAX_SPEECH_WORDS + 1}")
        if scene == "skit" and not (s.get("cast") or []):
            out.append(f"segment {i}: a skit needs `cast` (at least one character)")
    return out
