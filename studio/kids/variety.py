"""Variety check: warns when a kids video is too similar to earlier ones (repetitive-content risk)."""

from __future__ import annotations

import json
import re
from pathlib import Path

SIMILAR_LYRICS = 0.6  # share of the same words that counts as "near-identical"
SAME_CAST_LIMIT = 3  # this many earlier videos with the same kind and cast is a pattern


def _words(data: dict) -> set[str]:
    text = " ".join(ln for s in data["scenes"] for ln in s["lines"])
    return set(re.findall(r"[a-z']+", text.lower()))


def _cast(data: dict) -> tuple:
    return data["kind"], tuple(sorted({c for s in data["scenes"] for c in s["visual"]["characters"]}))


def compare(data: dict, others: list[dict]) -> list[str]:
    """Plain-English warnings about `data` versus earlier scripts. Empty means varied enough."""
    warns, mine, same_cast = [], _words(data), 0
    for o in others:
        theirs = _words(o)
        union = mine | theirs
        sim = len(mine & theirs) / len(union) if union else 0.0
        if sim >= SIMILAR_LYRICS:
            warns.append(f"Lyrics are {sim:.0%} the same as '{o.get('title', '?')}'. Write different words.")
        same_cast += _cast(o) == _cast(data)
    if same_cast >= SAME_CAST_LIMIT:
        warns.append(f"{same_cast} earlier videos use the same song type and characters. Change the teaching goal, "
                     "the cast or the setting so the channel does not look mass-produced.")
    return warns


def check(project: Path, data: dict) -> list[str]:
    """Compare a project with every other projects/kids_* folder next to it."""
    others = []
    for f in sorted(project.parent.glob("kids_*/script.json")):
        if f.parent != project and f.parent.name != "kids_demo":
            try:
                others.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return compare(data, others)
