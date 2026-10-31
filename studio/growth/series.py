"""Series and playlist planner: ordered videos that point to the next one, with end-screen text."""

from __future__ import annotations

from pathlib import Path

from studio.errors import StudioError
from studio.growth import store

NAME = "series"


def load(root: Path) -> list[dict]:
    return store.load(store.channel_file(root, NAME), {"series": []})["series"]


def _save(root: Path, series: list[dict]) -> None:
    store.save(store.channel_file(root, NAME), {"series": series})


def create(root: Path, name: str, description: str = "", topics: list[str] | None = None) -> dict:
    """New series; `topics` become its first (unproduced) entries in order."""
    name = name.strip()
    if not name:
        raise StudioError("The series name is empty.", "", "Type a name such as 'How Giants Make Money'.")
    series = load(root)
    if any(s["name"].lower() == name.lower() for s in series):
        raise StudioError(f"A series called '{name}' already exists.", "", "Pick another name or edit that one.")
    entry = {"name": name, "description": description.strip(),
             "entries": [{"topic": t.strip(), "video_id": None} for t in (topics or []) if t.strip()]}
    _save(root, series + [entry])
    return entry


def add_entry(root: Path, name: str, topic: str, video_id: int | None = None) -> None:
    series = load(root)
    s = _find(series, name)
    s["entries"].append({"topic": topic.strip(), "video_id": video_id})
    _save(root, series)


def link_video(root: Path, name: str, index: int, video_id: int, title: str) -> None:
    """Attach a made video (and its real title) to a planned slot."""
    series = load(root)
    e = _find(series, name)["entries"][index]
    e["video_id"], e["topic"] = video_id, title or e["topic"]
    _save(root, series)


def remove(root: Path, name: str) -> None:
    _save(root, [s for s in load(root) if s["name"] != name])


def _find(series: list[dict], name: str) -> dict:
    for s in series:
        if s["name"] == name:
            return s
    raise StudioError(f"No series called '{name}'.", "", "Create it first.")


def position(root: Path, video_id: int) -> tuple[dict, int] | None:
    """(series, index) containing the video, if any."""
    for s in load(root):
        for i, e in enumerate(s["entries"]):
            if e.get("video_id") == video_id:
                return s, i
    return None


def end_screen(series: dict, index: int) -> dict:
    """What to say and show at the end of entry `index`: next video line, playlist, subscribe."""
    entries = series["entries"]
    nxt = entries[index + 1]["topic"] if index + 1 < len(entries) else None
    if nxt:
        spoken = (f"Next in {series['name']}: {nxt}. It's on screen now, and the full playlist is in the "
                  f"description. Subscribe so you don't miss it.")
        description = f"Next in the series: {nxt}\nFull playlist: {series['name']}"
    else:
        spoken = f"That wraps up {series['name']}. Subscribe for the next series."
        description = f"Series: {series['name']} (final video so far)"
    return {"spoken": spoken, "description_line": description, "next_topic": nxt,
            "end_screen_elements": ["Next video in the series (video element)", f"Playlist: {series['name']}",
                                    "Subscribe button"]}


def prompt(profile_summary: str, existing_topics: list[str]) -> str:
    """Copy-paste prompt asking Claude to propose 2-3 series of 4-6 videos."""
    done = "\n".join(f"- {t}" for t in existing_topics) or "- (none yet)"
    return (
        f"You are a YouTube content strategist. {profile_summary}\n\n"
        "Propose 3 series (playlists) of 4-6 videos each. Videos in a series should build on each other so a "
        "viewer who finishes one wants the next. Topics must be original angles on real, checkable business "
        "facts. Do not copy any other creator's video.\n\nTopics already used (avoid):\n" + done +
        '\n\nReply with ONLY this JSON:\n{"series": [{"name": "...", "description": "one sentence", '
        '"topics": ["video 1 topic", "video 2 topic"]}]}')


def import_series(root: Path, text: str) -> list[str]:
    """Create the series from Claude's pasted JSON. Returns the names added (duplicates skipped)."""
    data = store.extract_json(text)
    items = data.get("series")
    if not isinstance(items, list) or not items:
        raise StudioError('The answer has no "series" list.', "", "Ask Claude to use the JSON shape in the prompt.")
    added = []
    for it in items:
        if not isinstance(it, dict) or not it.get("name") or not it.get("topics"):
            continue
        try:
            create(root, it["name"], it.get("description", ""), [str(t) for t in it["topics"]])
            added.append(it["name"])
        except StudioError:
            continue
    if not added:
        raise StudioError("No new series could be added.", "Each needs a new name and a list of topics.",
                          "Check the pasted JSON.")
    return added
