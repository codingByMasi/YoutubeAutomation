"""Cross-video repetition ledger: what each recent video of the channel looked like, so the next one differs.

Stored per channel in growth/story_ledger.json (the default channel) or growth/c/<id>/story_ledger.json.
An entry can also be computed from any script package (`entry_from_package`), so the originality check works
on videos that were made before the ledger existed.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from studio.growth import store

NAME = "story_ledger"
KEEP = 40
STOP = set("the a an of to and in on for is are was were it this that with as at by from you your we our".split())


def template(sentence: str, n: int = 4) -> str:
    """Opening-sentence template: first n words, digits masked, lower case."""
    w = re.sub(r"\d[\d,.]*", "#", sentence.lower())
    return " ".join(re.findall(r"[a-z#']+", w)[:n])


def _first_sentence(text: str) -> str:
    return (re.split(r"(?<=[.!?])\s+", text.strip()) or [""])[0]


def entry_from_package(pkg: dict, outline: dict | None = None, video_id: int | None = None) -> dict:
    """The structural fingerprint of one script package."""
    segs = pkg.get("segments") or []
    chapters: list[str] = []
    openings: list[str] = []
    for s in segs:
        ch = (s.get("chapter") or "").strip().lower()
        if ch and (not chapters or chapters[-1] != ch):
            chapters.append(ch)
            openings.append(template(_first_sentence(str(s.get("narration", "")))))
    beats = [(s.get("beat") or "explain") for s in segs]
    if outline and outline.get("beats"):
        beats = [b.get("device", "explain") for b in outline["beats"]]
    kw = Counter(w.lower() for s in segs for w in (s.get("visual_keywords") or []) if w.lower() not in STOP)
    arc = (outline or {}).get("arc") or pkg.get("arc") or ">".join(c.split()[0] for c in chapters if c)
    return {
        "video_id": video_id, "topic": pkg.get("topic", ""), "hook_type": pkg.get("hook_type") or "",
        "hook_first_line": _first_sentence(str(segs[0].get("narration", ""))) if segs else "",
        "arc_shape": arc, "chapters": chapters, "opening_templates": openings, "beat_sequence": beats,
        "top_visual_keywords": [k for k, _ in kw.most_common(8)],
    }


def path(root: Path) -> Path:
    return store.channel_file(root, NAME)


def load(root: Path) -> list[dict]:
    return store.load(path(root), [])


def record(root: Path, entry: dict) -> None:
    """Add (or replace by video_id) an entry; keeps the newest KEEP."""
    items = [e for e in load(root) if entry.get("video_id") is None or e.get("video_id") != entry["video_id"]]
    items.append(entry)
    store.save(path(root), items[-KEEP:])


def recent(root: Path, n: int = 5, exclude_video: int | None = None) -> list[dict]:
    return [e for e in load(root) if e.get("video_id") != exclude_video][-n:]


def recent_hook_types(root: Path, n: int = 3, exclude_video: int | None = None) -> list[str]:
    return [e["hook_type"] for e in recent(root, n, exclude_video) if e.get("hook_type")]


def prompt_text(root: Path, n: int = 5, exclude_video: int | None = None) -> str:
    """Short 'recent videos to differ from' block for the planning and script prompts."""
    rows = recent(root, n, exclude_video)
    if not rows:
        return "(no earlier videos on this channel yet)"
    lines = []
    for e in rows:
        lines.append(f"- {e.get('topic', '')[:60]}: hook_type={e.get('hook_type') or '?'}; opening "
                     f"\"{e.get('hook_first_line', '')[:70]}\"; arc={e.get('arc_shape', '')[:60]}; "
                     f"chapters={', '.join(e.get('chapters', [])[:6])}; "
                     f"visuals={', '.join(e.get('top_visual_keywords', [])[:5])}")
    return "\n".join(lines)


def similarity(a: dict, b: dict) -> dict:
    """Per-aspect similarity 0-1 between two entries."""
    sm = lambda x, y: SequenceMatcher(None, x, y).ratio() if x and y else 0.0  # noqa: E731
    ca, cb = set(a.get("chapters", [])), set(b.get("chapters", []))
    return {
        "beats": sm(a.get("beat_sequence", []), b.get("beat_sequence", [])),
        "chapters": len(ca & cb) / max(1, min(len(ca), len(cb))) if ca and cb else 0.0,
        "chapter_order": sm([c.split()[0] for c in a.get("chapters", []) if c],
                            [c.split()[0] for c in b.get("chapters", []) if c]),
        "opening": 1.0 if a.get("opening_templates", [""])[:1] == b.get("opening_templates", ["-"])[:1]
        and a.get("opening_templates") else 0.0,
        "arc": 1.0 if a.get("arc_shape") and a.get("arc_shape") == b.get("arc_shape") else 0.0,
    }


def structure_repeats(mine: dict, others: list[dict]) -> list[tuple[dict, dict]]:
    """[(other entry, similarity)] for entries whose structure (beats, chapters or arc) repeats this one's."""
    out = []
    for o in others:
        s = similarity(mine, o)
        if s["beats"] >= 0.85 or s["chapters"] >= 0.8 or s["chapter_order"] >= 0.85 or s["arc"] == 1.0:
            out.append((o, s))
    return out


def repetition_issues(mine: dict, others: list[dict], hook_window: int = 3) -> list[dict]:
    """[{severity, text, fix}] comparing this entry with the channel's recent ones (newest last)."""
    out: list[dict] = []
    last = others[-hook_window:]
    if mine.get("hook_type") and mine["hook_type"] in [o.get("hook_type") for o in last]:
        out.append({"severity": "major", "text": f"hook_type {mine['hook_type']!r} was used in one of the last "
                    f"{hook_window} videos.", "fix": "Pick a hook formula the channel has not used recently."})
    same_open = [o for o in others[-5:] if mine.get("opening_templates") and o.get("opening_templates")
                 and mine["opening_templates"][0] == o["opening_templates"][0]]
    if same_open:
        out.append({"severity": "major", "text": "The opening sentence template "
                    f"\"{mine['opening_templates'][0]}...\" repeats a recent video's.",
                    "fix": "Start the video with a different sentence shape."})
    reps = structure_repeats(mine, others[-6:])
    if reps:
        sev = "critical" if len(reps) >= 2 else "major"  # same structure for the 3rd time
        out.append({"severity": sev, "text": f"Same structure as {len(reps)} recent video(s) "
                    f"({'3rd time in a row' if len(reps) >= 2 else 'beats/chapters/arc'}).",
                    "fix": "Change the chapter structure and beat order (case study, comparison, myth-busting)."})
    return out
