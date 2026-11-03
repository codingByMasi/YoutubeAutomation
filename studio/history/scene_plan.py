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

Recurring cast (use for their job; you may also name up to 3 historical figures from the narration):
{roster}

For each segment return: "n" (its number), "scene", "cast" (1-3 roster ids or figure names; required for a skit),
"speech" (skit only: at most {cast.MAX_SPEECH_LINES} lines of at most {cast.MAX_SPEECH_WORDS} words, each
{{"who": "...", "text": "..."}}, invented tone-setting dialogue, never a quote presented as real), and "scene_data":
- map: {{"title": "...", "points": [{{"x": 0-1, "y": 0-1, "label": "..."}}]}} using these known places on the map:
  {places}. Positions are given by the studio for known places; use only those names as labels.
- diagram: {{"title": "...", "steps": ["3-5 short steps"]}}
- calendar: {{"title": "...", "days": 1-31}}
- lectern: {{"title": "...", "question": "..."}}
- silhouette: {{"title": "one plain sentence on the human cost"}}
Write ONLY this JSON object: {{"segments": [{{"n": 1, "scene": "skit", "cast": ["blunder", "dusty"], "speech": [...],
"scene_data": {{}}}}, ...]}} with exactly {len(segments)} entries.

Segments:
{lines}
"""


def validate(data: dict, n: int) -> list[str]:
    """Problems with Claude's answer (empty when fine)."""
    rows = data.get("segments")
    if not isinstance(rows, list) or len(rows) != n:
        return [f"`segments` must be a list of exactly {n} entries"]
    probe = {"segments": [{k: r.get(k) for k in ("scene", "cast", "speech") if r.get(k) is not None}
                          for r in rows if isinstance(r, dict)]}
    out = cast.scene_problems(probe)
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict) or r.get("scene") not in cast.SCENE_TYPES:
            out.append(f"entry {i}: `scene` must be one of {list(cast.SCENE_TYPES)}")
    return out


def merge(segments: list[dict], data: dict) -> None:
    """Copy the answer's scene keys into the segments that lack a scene (existing keys always win)."""
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


def assign(settings: Settings, work_dir: Path, segments: list[dict], say=print) -> str:
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
        return "rules"
    merge(segments, data)
    autoscene.assign(segments)  # fills anything the answer left without cast/data
    return "claude"
