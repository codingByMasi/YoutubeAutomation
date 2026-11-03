# ruff: noqa: E501  (SVG path data)
"""The history channel's cast: recurring original characters, historical figures built from one body, scene rules.

Everything here is original. The reference videos were studied for structure only; do not trace or imitate any
existing channel's characters. SVGs follow the kids sprite contract (`studio/kids/sprites.py`): four groups
`eyes-open`, `eyes-closed`, `mouth-closed`, `mouth-open`, so `SpriteBank(user_dir=...)` can blink and lip-sync them.
"""

from __future__ import annotations

import re
from pathlib import Path

from studio.errors import StudioError
from studio.history import wardrobe
from studio.providers import voices

SCENE_TYPES = ("lectern", "skit", "map", "diagram", "easel", "archive", "calendar", "silhouette", "title")
MAX_SPEECH_LINES = 4
MAX_SPEECH_WORDS = 10
HEADWEAR = ("none", "fur_hat", "helmet", "crown", "turban", "cap", "hood", "laurel")
PROPS = ("none", "sword", "scroll", "shield", "staff", "coin", "banner")

# Recurring cast: one job each. `role` is what the writer may use the character for.
ROSTER: dict[str, dict] = {
    "quill": {"name": "Quill", "role": "host: stands at the lectern, opens and closes chapters, asks the chapter question",
              "body": "#2E7D87", "headwear": "laurel", "prop": "scroll", "badge": "Q", "shape": "standard",
              "personality": "Warm, precise, gently ironic; never rushes a point.",
              "voice": {"edge": "en-GB-RyanNeural", "rate": -2, "pitch": -2, "kokoro": "bm_george", "speed": 0.98}},
    "dusty": {"name": "Dusty", "role": "viewer stand-in: the ordinary person who asks what the viewer is thinking",
              "body": "#C9A66B", "headwear": "cap", "prop": "none", "badge": "D", "shape": "standard",
              "personality": "Plain-spoken and curious; says 'wait, so who paid for that?'.",
              "voice": {"edge": "en-US-GuyNeural", "rate": 6, "pitch": 4, "kokoro": "am_adam", "speed": 1.05}},
    "vex": {"name": "Vizier Vex", "role": "the schemer: advisers, rival courtiers, anyone who quietly pulls strings",
            "body": "#5B3A7A", "headwear": "hood", "prop": "scroll", "badge": "V", "shape": "standard",
            "personality": "Smooth, patient, always three moves ahead and never in the frame when it goes wrong.",
            "voice": {"edge": "en-GB-ThomasNeural", "rate": -10, "pitch": -6, "kokoro": "bm_lewis", "speed": 0.9}},
    "blunder": {"name": "Captain Blunder", "role": "the overconfident officer: stands in for a doomed or foolish plan",
                "body": "#A33B3B", "headwear": "helmet", "prop": "sword", "badge": "B", "shape": "standard",
                "personality": "Loud, certain and wrong; every plan is 'foolproof'.",
                "voice": {"edge": "en-US-ChristopherNeural", "rate": 4, "pitch": -4, "kokoro": "am_fenrir", "speed": 1.05}},
    "coin": {"name": "Madame Coin", "role": "the treasurer: counts what a war, a tax or a trade really cost",
             "body": "#B8892B", "headwear": "turban", "prop": "coin", "badge": "C", "shape": "standard",
             "personality": "Dry, exact, unimpressed by glory; only the ledger is real.",
             "voice": {"edge": "en-GB-SoniaNeural", "rate": -4, "pitch": 0, "kokoro": "bf_emma", "speed": 0.95}},
    "dash": {"name": "Dash", "role": "the courier: delivers bad news and ends chapters on a cliffhanger",
             "body": "#6E8B3D", "headwear": "cap", "prop": "scroll", "badge": "R", "shape": "standard",
             "personality": "Out of breath, anxious, always arriving with the worst timing.",
             "voice": {"edge": "en-AU-WilliamNeural", "rate": 18, "pitch": 6, "kokoro": "am_puck", "speed": 1.2}},
    "brine": {"name": "Admiral Brine", "role": "the sea-power expert: fleets, harbours, trade routes and blockades",
              "body": "#2B4C7E", "headwear": "bicorn", "prop": "telescope", "badge": "A", "shape": "wide",
              "personality": "Gruff and salty; sees every problem as a question of who controls the water.",
              "voice": {"edge": "en-IE-ConnorNeural", "rate": -12, "pitch": -10, "kokoro": "bm_daniel", "speed": 0.9}},
    "hindsight": {"name": "Inspector Hindsight", "role": "the 'what they did not know' detective: points out the clue everyone missed",
                  "body": "#C94F7C", "headwear": "deerstalker", "prop": "magnifier", "badge": "H", "shape": "tall",
                  "personality": "Dry, sharp and fond of 'obviously, in hindsight'; keeps a list of warnings ignored.",
                  "voice": {"edge": "en-GB-LibbyNeural", "rate": -2, "pitch": 0, "kokoro": "bf_isabella", "speed": 1.0}},
    "ironhand": {"name": "Ironhand", "role": "the smith: weapons, tools, factories and the technology behind who won",
                 "body": "#3F4A5A", "headwear": "goggles", "prop": "hammer", "badge": "I", "shape": "stocky",
                 "personality": "Blunt and practical; thinks battles are decided at the forge long before the field.",
                 "voice": {"edge": "en-US-EricNeural", "rate": -14, "pitch": -14, "kokoro": "am_onyx", "speed": 0.85}},
    "alma": {"name": "Almanac Alma", "role": "the timekeeper: dates, calendars, how long it all took",
             "body": "#E07B39", "headwear": "pointed", "prop": "hourglass", "badge": "T", "shape": "small",
             "personality": "Brisk, cheerful and fussy about dates; hates 'sometime around then'.",
             "voice": {"edge": "en-CA-ClaraNeural", "rate": 2, "pitch": 2, "kokoro": "af_heart", "speed": 1.0}},
}

# Body proportions: silhouette differs per character (x scale, y scale) around the feet.
SHAPES = {"standard": (1.0, 1.0), "tall": (0.84, 1.1), "wide": (1.2, 0.92), "stocky": (1.12, 0.96), "small": (0.84, 0.84)}
# Extras used by the recurring cast only (kept separate so generated historical figures never change).
CAST_HEADWEAR = {
    "bicorn": '<path d="M104 134 Q200 44 296 134 Q250 108 200 110 Q150 108 104 134Z" fill="#1f2d4d"/><path d="M104 134 L82 114 L124 122Z M296 134 L318 114 L276 122Z" fill="#1f2d4d"/><rect x="112" y="128" width="176" height="10" fill="#e0b43a"/>',
    "deerstalker": '<path d="M116 138 Q200 52 284 138Z" fill="#8a7a5a"/><path d="M116 138 Q200 118 284 138 L284 150 Q200 130 116 150Z" fill="#6e6044"/><path d="M104 150 Q92 190 112 200 Q122 170 126 150Z M296 150 Q308 190 288 200 Q278 170 274 150Z" fill="#6e6044"/>',
    "pointed": '<path d="M112 138 L204 14 L288 138Z" fill="#E07B39"/><ellipse cx="200" cy="138" rx="100" ry="12" fill="#b85a22"/><circle cx="204" cy="40" r="9" fill="#f6d36b"/>',
    "goggles": '<rect x="112" y="108" width="176" height="14" rx="6" fill="#3b3b46"/><circle cx="160" cy="104" r="22" fill="#9fd3e6" stroke="#3b3b46" stroke-width="8"/><circle cx="240" cy="104" r="22" fill="#9fd3e6" stroke="#3b3b46" stroke-width="8"/><path d="M118 124 Q200 76 282 124 L282 112 Q200 56 118 112Z" fill="#59616b"/>',
}
CAST_PROPS = {
    "telescope": '<rect x="296" y="236" width="64" height="18" rx="7" fill="#b8892b" transform="rotate(-24 296 244)"/><rect x="344" y="212" width="16" height="22" rx="6" fill="#7a5233" transform="rotate(-24 344 222)"/>',
    "magnifier": '<circle cx="338" cy="238" r="26" fill="#cfe9f2" fill-opacity="0.6" stroke="#7a5233" stroke-width="7"/><rect x="350" y="258" width="10" height="48" rx="4" fill="#7a5233" transform="rotate(-35 355 260)"/>',
    "hammer": '<rect x="330" y="196" width="9" height="124" rx="4" fill="#7a5233"/><rect x="304" y="186" width="60" height="30" rx="6" fill="#59616b"/>',
    "hourglass": '<path d="M312 220 H358 L342 252 L358 290 H312 L328 252Z" fill="#f1e4c4" stroke="#7a5233" stroke-width="5"/><path d="M322 280 H348 L335 266Z" fill="#e0b43a"/>',
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
              skin: str = _SKIN, shape: str = "standard", outfit: str = "default") -> str:
    """One character as SVG text (400x400) with the four sprite groups. Unknown headwear/prop/shape/outfit raise ValueError.

    Recurring-cast extras (`CAST_HEADWEAR`, `CAST_PROPS`) are accepted too; generated figures use the base lists.
    `outfit` is an era from `wardrobe.ERAS`: it swaps headwear, adds a garment/cape/collar and (unless the prop is a
    signature one) the prop. Face, skin, shape, badge letter and the four sprite groups stay as they are."""
    heads, props = {**_HEAD, **CAST_HEADWEAR}, {**_PROP, **CAST_PROPS}
    if headwear not in heads:
        raise ValueError(f"headwear {headwear!r} not in {list(HEADWEAR)}")
    if prop not in props:
        raise ValueError(f"prop {prop!r} not in {list(PROPS)}")
    if shape not in SHAPES:
        raise ValueError(f"shape {shape!r} not in {list(SHAPES)}")
    sx, sy = SHAPES[shape]
    for v in (body, skin):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError(f"colour {v!r} must look like #RRGGBB")
    fit = wardrobe.parts(outfit, body, prop)
    if fit:
        heads = {**heads, headwear: fit["head"]}
        props = {**props, prop: fit["prop"] or props[prop]}
    cape = f'{fit["cape"]}\n' if fit and fit["cape"] else ""
    garment = (f'<defs><clipPath id="bodyclip"><rect x="130" y="210" width="140" height="150" rx="52"/></clipPath></defs>'
               f'<g clip-path="url(#bodyclip)">{fit["garment"]}</g>\n') if fit and fit["garment"] else ""
    collar = f'{fit["collar"]}\n' if fit and fit["collar"] else ""
    wrap_open = "" if shape == "standard" else f'<g transform="translate(200 378) scale({sx} {sy}) translate(-200 -378)">\n'
    wrap_close = "" if shape == "standard" else "</g>\n"
    letter = re.sub(r"[^A-Za-z0-9]", "", badge)[:1].upper()
    badge_svg = (f'<circle cx="200" cy="292" r="22" fill="#fff"/><text x="200" y="301" text-anchor="middle" '
                 f'font-family="Arial,sans-serif" font-size="26" font-weight="700" fill="{_INK}">{letter}</text>'
                 if letter else "")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">\n'
        '<ellipse cx="200" cy="378" rx="96" ry="12" fill="#000" opacity="0.12"/>\n'
        f"{wrap_open}"
        f"{cape}"
        f'<rect x="130" y="210" width="140" height="150" rx="52" fill="{body}"/>\n'
        f"{garment}"
        f'<ellipse cx="118" cy="268" rx="20" ry="16" fill="{skin}"/><ellipse cx="282" cy="268" rx="20" ry="16" fill="{skin}"/>\n'
        f"{collar}{badge_svg}\n"
        f'<circle cx="200" cy="162" r="84" fill="{skin}"/>\n'
        f"{heads[headwear]}\n"
        f"{props[prop].replace('{color}', body)}\n"
        f'<g id="eyes-open"><ellipse cx="170" cy="160" rx="14" ry="18" fill="#fff"/><ellipse cx="230" cy="160" rx="14" ry="18" fill="#fff"/>'
        f'<circle cx="172" cy="163" r="8" fill="{_INK}"/><circle cx="232" cy="163" r="8" fill="{_INK}"/></g>\n'
        f'<g id="eyes-closed"><path d="M156 164 Q170 174 184 164" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/>'
        f'<path d="M216 164 Q230 174 244 164" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/></g>\n'
        f'<g id="mouth-closed"><path d="M178 206 Q200 220 222 206" stroke="{_INK}" stroke-width="6" fill="none" stroke-linecap="round"/></g>\n'
        f'<g id="mouth-open"><path d="M176 202 Q200 240 224 202 Z" fill="{_INK}"/></g>\n'
        f"{wrap_close}"
        "</svg>\n"
    )


def roster_svg(char_id: str, outfit: str = "default") -> str:
    """SVG of a recurring character, optionally dressed for an era (see `studio.history.wardrobe`)."""
    c = ROSTER[char_id]
    return build_svg(c["body"], c["headwear"], c["prop"], c["badge"], shape=c.get("shape", "standard"), outfit=outfit)


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
    lines.append(wardrobe.prompt_line())
    lines.append(f"Scene types per segment: {', '.join(SCENE_TYPES)}. Add optional keys to each segment: `scene`, "
                 "`cast` (list of roster ids or figure names), `staging` (one sentence), `speech` (at most "
                 f"{MAX_SPEECH_LINES} on-screen lines of at most {MAX_SPEECH_WORDS} words, each "
                 '{"who": "...", "text": "..."}). Speech is invented dialogue: use it only for tone, never for quotes '
                 "you present as real; real quotes go in the narration with a source.")
    return "\n".join(lines)


def scene_problems(pkg: dict, profile: dict | None = None) -> list[str]:
    """Plain-language problems with the optional scene/cast/speech keys of each segment."""
    out: list[str] = []
    if pkg.get("era") and not wardrobe.known(str(pkg["era"]).lower()):
        out.append(f"era {pkg['era']!r} is not one of {[wardrobe.DEFAULT, *wardrobe.ERAS]}")
    run, prev = 0, None
    for i, s in enumerate(pkg.get("segments") or [], 1):
        scene = s.get("scene")
        if scene is None:
            run, prev = 0, None
            continue
        if scene not in SCENE_TYPES:
            out.append(f"segment {i}: scene {scene!r} is not one of {list(SCENE_TYPES)}")
        if s.get("era") and not wardrobe.known(str(s["era"]).lower()):
            out.append(f"segment {i}: era {s['era']!r} is not one of {[wardrobe.DEFAULT, *wardrobe.ERAS]}")
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


def voice_for(char_id: str) -> dict:
    """A recurring character's voice settings (see `studio.providers.voices`); unknown ids get the neutral default."""
    c = ROSTER.get(char_id)
    return voices.check(c["voice"], c["name"]) if c else dict(voices.DEFAULT)


def check_roster() -> None:
    """Raise a StudioError if any roster entry has a bad voice, headwear, prop or shape (used by tests)."""
    for cid, c in ROSTER.items():
        voices.check(c.get("voice", {}), c["name"])
        if c["headwear"] not in {**_HEAD, **CAST_HEADWEAR} or c["prop"] not in {**_PROP, **CAST_PROPS} or c.get("shape", "standard") not in SHAPES:
            raise StudioError(f"{cid}: unknown headwear, prop or shape.", "Values must exist in the cast tables.", "Fix the roster entry.")
