"""Per-channel rules learned from retention data. Stored in the channel's growth folder (rules.json)."""

from __future__ import annotations

from pathlib import Path

from studio.growth import store

NAME = "rules"
EMPTY: dict = {"source": "", "videos": 0, "updated": "", "tuning": {}, "edit": {}, "lessons": [], "evidence": []}


def load(root: Path) -> dict:
    """The active channel's learned rules (empty defaults before any feedback run)."""
    return {**EMPTY, **store.load(store.channel_file(root, NAME), {})}


def save(root: Path, data: dict) -> Path:
    return store.save(store.channel_file(root, NAME), data)


def trusted(learned: dict) -> bool:
    """Only rules learned from real YouTube data change real scripts; mock-derived rules stay advisory."""
    return learned.get("source") == "youtube" or bool(learned.get("applied_mock"))


def tuning(learned: dict) -> dict:
    """Gate threshold overrides, or {} when the rules came from mock data."""
    return learned.get("tuning", {}) if trusted(learned) else {}


def edit_limits(root: Path) -> dict:
    """Edit rules (e.g. shot_max_seconds) the build and visuals stages respect for this channel."""
    learned = load(root)
    return learned.get("edit", {}) if trusted(learned) else {}


def lessons_text(root: Path) -> str:
    """A block for the script prompt: what this channel's own audience data says. Empty when there is none."""
    learned = load(root)
    if not trusted(learned) or not learned["lessons"]:
        return ""
    lines = [f"- {x['text']}" for x in learned["lessons"]]
    return (f"\n\nLessons from this channel's own retention data ({learned['videos']} video(s); follow them, "
            "they override the generic rules above where they conflict):\n" + "\n".join(lines))
