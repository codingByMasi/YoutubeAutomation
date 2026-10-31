"""Fact and source checklist that must be completed before approval."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from studio.growth import store

PLACEHOLDER = ("illustrative", "replace before", "sample data", "todo", "tbd")
FIGURE = re.compile(r"(\$\s?\d|\d+\s?%|\d[\d,.]*\s?(million|billion|trillion|thousand)|\b\d{4,}\b)", re.I)
STANDARD = [
    ("dates", "Every figure states or implies its year/date, and the data is the latest available"),
    ("rounding", "Numbers are rounded honestly and units (USD, %, per year) are correct"),
    ("charts", "Each chart's numbers match its cited source"),
    ("claims", "No claim of guaranteed returns or personal financial advice"),
    ("original", "Wording and structure are my own; nothing is copied from another creator"),
    ("photos", "Photo and footage credits are in the description"),
]


def build_items(pkg: dict) -> list[dict]:
    """Items to tick: one per source, one per sentence containing a figure, plus standard checks."""
    items = [{"id": f"src:{s.get('id')}", "text": f"Source [{s.get('id')}] {s.get('title', '')} is real and opens: "
              f"{s.get('url_or_note', '')}"} for s in pkg.get("sources", [])]
    for i, seg in enumerate(pkg.get("segments", [])):
        for sent in re.split(r"(?<=[.!?])\s+", seg.get("narration", "")):
            if FIGURE.search(sent):
                items.append({"id": f"fig:{i}:{hashlib.md5(sent.encode()).hexdigest()[:8]}",
                              "text": f"Segment {i + 1}: \"{sent.strip()}\" matches a cited source"})
    return items + [{"id": f"std:{k}", "text": t} for k, t in STANDARD]


def auto_problems(pkg: dict) -> list[str]:
    """Problems no tick can fix: missing or placeholder sources."""
    problems = []
    sources = pkg.get("sources") or []
    if not sources:
        problems.append("The script lists no sources. Add them (Script page) before approving.")
    for s in sources:
        note = str(s.get("url_or_note", "")).lower()
        if not note.strip() or any(p in note for p in PLACEHOLDER):
            problems.append(f"Source [{s.get('id')}] is a placeholder: replace it with a real filing or article.")
    return problems


def load(project_dir: Path) -> dict:
    return store.load(store.video_file(project_dir, "factcheck"), {"checked": []})


def toggle(project_dir: Path, item_id: str, value: bool) -> None:
    d = load(project_dir)
    ticked = set(d["checked"])
    (ticked.add if value else ticked.discard)(item_id)
    store.save(store.video_file(project_dir, "factcheck"), {"checked": sorted(ticked)})


def status(project_dir: Path, pkg: dict) -> dict:
    """{items, checked, remaining, problems, passed}. Passed means every item ticked and no auto problems."""
    items, done = build_items(pkg), set(load(project_dir)["checked"])
    remaining = [i for i in items if i["id"] not in done]
    problems = auto_problems(pkg)
    return {"items": items, "checked": done, "remaining": remaining, "problems": problems,
            "passed": not remaining and not problems}
