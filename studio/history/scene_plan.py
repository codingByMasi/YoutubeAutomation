"""One-time scene assignment for a script that has no scene types, answered by Claude (prompt-file handoff).

`visuals` calls `assign(...)` when a cast channel's script has segments without a `scene`. Claude reads each
segment's narration and chooses what best shows it (skit, map, diagram, calendar, silhouette, lectern), who acts,
the short speech lines and the map points. The answer is validated, saved into script.json and never asked again.
If the provider fails (not merely pending), the built-in word rules in `autoscene` fill in so nothing stalls.
"""

from __future__ import annotations

from pathlib import Path

from studio import llm
from studio.config import Settings
from studio.errors import PendingLLMResponse
from studio.history import autoscene, cast

ONE_LINE = "No scenes assigned for this script."


def missing(segments: list[dict]) -> list[int]:
    """Indexes (0-based) of segments with no valid cast-scene type."""
    return [i for i, s in enumerate(segments)
            if not (isinstance(s.get("scene"), str) and s["scene"] in cast.SCENE_TYPES)]


def build_prompt(segments: list[dict]) -> str:
    roster = "\n".join(f"- {cid}: {c['name']}, {c['role']}" for cid, c in cast.ROSTER.items())
    places = ", ".join(sorted(autoscene.PLACES))
    lines = "\n".join(f"{i}. [{s.get('chapter', '')}] {s.get('narration', '')}" for i, s in enumerate(segments, 1))
    return f"""You assign a cartoon scene to every segment of a history video script. Choose what best SHOWS the
narration at that moment, the way an animated explainer would: characters acting it out, a moving map, a diagram of
how something worked, a calendar for time passing, a silhouette for violence. Photos and charts are NOT scene types
and must not be used here.

Scene types: {', '.join(cast.SCENE_TYPES)} (do not use `archive` or `easel` unless the narration names a single
document or a list). Rules: the first segment is a `skit`; never three of the same scene type in a row (maps and
diagrams excepted); `lectern` only at the start of a new chapter, at most every fifth segment; violence or loss is a
`silhouette`, never drawn in detail.

Characters come from THIS script. List every person or creature that appears on screen (not the narrator), the way
the script describes them: a general, a queen, a merchant's child, a sailor, a priestess, a spy, an elephant keeper,
anyone. The list is open-ended: describe each one with attributes, never with a fixed type. Keep the same look for
the whole video. Per character return:
  "name" (as the script names them, or a short role like "Roman consul"), "role", "gender" (female, male or neutral:
  only what the script says; never guess from a name), "age" (child, young, adult, elder), "build" (slim, average,
  stocky, broad, tall, small), "skin" (a word like pale, olive, tan, brown, dark, or a hex colour), "hair"
  {{"style": none/short/long/bun/braid/ponytail/curly, "color": "..."}}, "facial_hair" (none, mustache, beard,
  goatee), "clothing" {{"type": e.g. tunic, robe, dress, gown, toga, coat, apron, kimono, kilt, "color": "...",
  "trim": "..."}}, "armour" (none, chainmail, breastplate, plate), "headwear" (e.g. helmet, crown, hood, turban, veil,
  hat, cap, laurel, none), "props" (up to 2: sword, spear, shield, staff, bow, scroll, book, torch, purse, hammer,
  banner, or any object), "accent_color", optional "cape_color", optional "pitch" (low, mid, high) for the voice.
Dress them for the story's era and place (what people there and then wore). Use the recurring cast below only for
the host (`quill`, at the lectern) and for light helper roles; everything else is a character from the list above.
Recurring cast:
{roster}

For each segment return: "n" (its number), "scene", "cast" (1-3 character names from your list
or roster ids; required for a skit), "speech" (skit only: at most {cast.MAX_SPEECH_LINES} lines of at most
{cast.MAX_SPEECH_WORDS} words, each
{{"who": "...", "text": "..."}}, invented tone-setting dialogue, never a quote presented as real), and "scene_data":
- map: {{"title": "...", "points": [{{"x": 0-1, "y": 0-1, "label": "..."}}]}} using these known places on the map:
  {places}. Positions are given by the studio for known places; use only those names as labels.
- diagram: {{"title": "...", "steps": ["3-5 short steps"]}}
- calendar: {{"title": "...", "days": 1-31}}
- lectern: {{"title": "...", "question": "..."}}
- silhouette: {{"title": "one plain sentence on the human cost"}}
Write ONLY this JSON object: {{"characters": [...], "segments": [{{"n": 1, "scene": "skit",
"cast": ["Roman consul", "Scout"], "speech": [...], "scene_data": {{}}}}, ...]}}
with exactly {len(segments)} entries.

Segments:
{lines}
"""


def validate(data: dict, n: int) -> list[str]:
    """Problems with Claude's answer (empty when fine)."""
    rows = data.get("segments")
    if not isinstance(rows, list) or len(rows) != n:
        return [f"`segments` must be a list of exactly {n} entries"]
    chars = data.get("characters", [])
    if not isinstance(chars, list) or any(not isinstance(c, dict) or not str(c.get("name", "")).strip() for c in chars):
        return ["`characters` must be a list of objects that each have a `name`"]
    probe = {"segments": [{k: r.get(k) for k in ("scene", "cast", "speech") if r.get(k) is not None}
                          for r in rows if isinstance(r, dict)]}
    out = cast.scene_problems(probe)
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict) or r.get("scene") not in cast.SCENE_TYPES:
            out.append(f"entry {i}: `scene` must be one of {list(cast.SCENE_TYPES)}")
    return out


def merge(segments: list[dict], data: dict, store: dict | None = None) -> None:
    """Copy the answer's scene keys into the segments that lack a scene (existing keys always win). The script's
    character descriptions go to `store["characters"]` (saved top-level in script.json by the caller)."""
    if store is not None:
        seen: dict[str, dict] = {}
        for c in data.get("characters") or []:
            seen.setdefault(str(c["name"]).strip().lower(), c)
        store["characters"] = list(seen.values())
    for i in missing(segments):
        r = data["segments"][i]
        seg = segments[i]
        seg["scene"] = r["scene"]
        seg["cast"] = r.get("cast") or seg.get("cast") or ["quill"]
        if r.get("speech") and not seg.get("speech"):
            seg["speech"] = r["speech"]
        sd = dict(r.get("scene_data") or {})
        if r["scene"] == "map":  # places come from the studio's own map table, not from guessed coordinates
            pts = []
            for p in sd.get("points") or []:
                key = str(p.get("label", "")).lower()
                if key in autoscene.PLACES:
                    pts.append({"x": autoscene.PLACES[key][0], "y": autoscene.PLACES[key][1], "label": key.title()})
            sd["points"] = pts or [{"x": autoscene.PLACES[k][0], "y": autoscene.PLACES[k][1], "label": k.title()}
                                   for k in autoscene.places_in(str(seg.get("narration", "")))[:4]]
        if sd and not seg.get("scene_data"):
            seg["scene_data"] = sd


def assign(settings: Settings, work_dir: Path, segments: list[dict], say=print, store: dict | None = None) -> str:
    """Give every segment a scene. Returns 'claude' or 'rules'. Raises PendingLLMResponse while Claude's answer is
    still to be written (the usual claude_code handoff); the caller's CLI shows the one instruction line."""
    todo = missing(segments)
    if not todo:
        return "claude"
    say(ONE_LINE)
    try:
        data = llm.ask_json(settings, work_dir, "scenes", build_prompt(segments),
                            validate=lambda d: validate(d, len(segments)))
    except PendingLLMResponse:
        raise
    except Exception as exc:  # noqa: BLE001 - provider down or answer unusable: the word rules keep the video moving
        say(f"Claude could not assign scenes ({str(exc)[:100]}); used the built-in rules instead.")
        autoscene.assign(segments)
        if store is not None:
            store["characters"] = autoscene.characters_for(segments)
        return "rules"
    merge(segments, data, store)
    autoscene.assign(segments)  # fills anything the answer left without cast/data
    return "claude"


def undescribed(segments: list[dict], characters: list[dict] | None) -> list[str]:
    """Names on screen (skit cast and speakers, except the host) that the script has not described yet."""
    have = [str(c.get("name", "")).strip().lower() for c in characters or [] if isinstance(c, dict)]
    out: list[str] = []
    for s in segments:
        if s.get("scene") != "skit":
            continue
        names = [*(s.get("cast") or []), *(str(x.get("who", "")) for x in s.get("speech") or [] if isinstance(x, dict))]
        for n in names:
            low = str(n).strip().lower()
            if low in ("", "quill", "narrator") or any(low in h or h in low for h in have) or n in out:
                continue
            out.append(str(n))
    return out


def describe(settings: Settings, work_dir: Path, segments: list[dict], characters: list[dict] | None,
             say=print) -> list[dict]:
    """Ask Claude once to describe every on-screen character the script names but has not described (look follows
    the script: role, gender, age, build, clothing, era, props). Returns the full character list; a failed answer
    returns the list unchanged and those names are drawn from their own words."""
    names = undescribed(segments, characters)
    if not names:
        return list(characters or [])
    say("Characters in this script have no descriptions yet.")
    story = "\n".join(f"{i}. {s.get('narration', '')}" for i, s in enumerate(segments, 1))
    prompt = (f"""Describe each character below the way THIS script shows them, so a 2D cartoon artist can draw them:
never pick from a fixed type list; dress them for the story's era and place. Characters: {', '.join(names)}.
Per character return "name" (exactly as listed), "role", "gender" (female, male or neutral: only what the script
says; never guess from a name), "age" (child, young, adult, elder), "build", "skin", "hair" {{"style", "color"}},
"facial_hair", "clothing" {{"type", "color", "trim"}}, "armour", "headwear", "props" (up to 2), "accent_color",
optional "pitch" (low, mid, high). Write ONLY {{"characters": [...]}}.

Script:
{story}
""")
    try:
        data = llm.ask_json(settings, work_dir, "characters", prompt, validate=lambda d: validate_characters(d))
    except PendingLLMResponse:
        raise
    except Exception as exc:  # noqa: BLE001 - unusable answer: names are drawn from their own words instead
        say(f"Claude could not describe the characters ({str(exc)[:100]}); drawing them from their names.")
        return list(characters or [])
    return [*(characters or []), *(c for c in data["characters"])]


def validate_characters(data: dict) -> list[str]:
    """Problems with a character-description answer (empty when fine)."""
    rows = data.get("characters")
    if not isinstance(rows, list) or not rows or any(not isinstance(c, dict) or not str(c.get("name", "")).strip()
                                                    for c in rows):
        return ["`characters` must be a non-empty list of objects that each have a `name`"]
    return []
