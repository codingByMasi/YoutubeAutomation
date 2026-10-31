"""Title and thumbnail pack: 5 titles + 3 thumbnail concepts per topic, ranked by a written checklist."""

from __future__ import annotations

import re

from studio.errors import StudioError
from studio.growth import store
from studio.stages.script import validate_title

CURIOSITY = re.compile(r"\b(how|why|what|really|actually|secret|truth|hidden|\?)", re.I)
TITLE_COUNT, THUMB_COUNT = 5, 3


def title_checklist(text: str) -> tuple[int, list[str]]:
    """Score a title 0-6 against the checklist; returns (score, missed items). Hard rule breaks score 0."""
    hard = validate_title(text)
    if hard:
        return 0, hard
    notes, score = [], 0
    checks = [
        (len(text) <= 60, "60 characters or fewer so it is not cut off on phones"),
        (bool(re.search(r"\d", text)), "contains a specific number"),
        (bool(CURIOSITY.search(text)), "opens a curiosity gap (how / why / really / ?)"),
        (len(text.split()) <= 10, "10 words or fewer"),
        (not text.rstrip().endswith("!"), "no exclamation hype"),
        (bool(re.search(r"[A-Z]", text[:1])), "starts with a capital letter"),
    ]
    for ok, label in checks:
        score += ok
        if not ok:
            notes.append(f"missing: {label}")
    return score, notes


def thumb_checklist(t: dict) -> tuple[int, list[str]]:
    """Score a thumbnail concept 0-5."""
    notes, score = [], 0
    words = len(str(t.get("text", "")).split())
    checks = [
        (1 <= words <= 4, "text is 1-4 words"),
        (bool(t.get("focal_element")), "one clear focal element"),
        (bool(t.get("emotion_or_tension")), "shows a number, contrast or tension"),
        (bool(t.get("colors")), "colors named (high contrast, brand colors)"),
        (str(t.get("text", "")).strip().lower() not in str(t.get("title", "")).strip().lower() or words <= 2,
         "adds something the title does not already say"),
    ]
    for ok, label in checks:
        score += ok
        if not ok:
            notes.append(f"missing: {label}")
    return score, notes


def prompt(topic: str, profile_summary: str, script_summary: str = "") -> str:
    """Copy-paste prompt for Claude."""
    return (
        f"You are a YouTube packaging expert. {profile_summary}\n\nVideo topic: {topic}\n"
        + (f"What the script covers: {script_summary}\n" if script_summary else "")
        + f"\nWrite {TITLE_COUNT} title options (each under 60 characters, specific, honest, no clickbait lies, no "
        "ALL-CAPS words, no phrases like 'you won't believe') and "
        f"{THUMB_COUNT} different thumbnail concepts. A thumbnail has at most 4 words of text, one focal element, "
        "and high contrast. Original ideas only.\n\nReply with ONLY this JSON:\n"
        '{"titles": [{"text": "...", "style": "number|how|why|contrast"}],\n'
        ' "thumbnails": [{"text": "2-4 words", "focal_element": "what the eye lands on", '
        '"emotion_or_tension": "the number/contrast/tension shown", "colors": "e.g. navy background, yellow text", '
        '"layout": "split|full-bleed|big-number"}]}')


def parse(text: str) -> dict:
    """Validate Claude's pasted answer and return the ranked pack."""
    data = store.extract_json(text)
    titles, thumbs = data.get("titles"), data.get("thumbnails")
    problems = []
    if not isinstance(titles, list) or len(titles) != TITLE_COUNT:
        problems.append(f"need exactly {TITLE_COUNT} titles")
    if not isinstance(thumbs, list) or len(thumbs) != THUMB_COUNT:
        problems.append(f"need exactly {THUMB_COUNT} thumbnail concepts")
    if problems:
        raise StudioError("The pack is incomplete: " + "; ".join(problems) + ".",
                          "The prompt asks for 5 titles and 3 thumbnails.", "Ask Claude to follow the JSON shape.")
    ranked_t = []
    for t in titles:
        text_ = str(t.get("text", "")).strip()
        score, notes = title_checklist(text_)
        ranked_t.append({"text": text_, "style": t.get("style", ""), "score": score, "notes": notes})
    ranked_h = []
    for h in thumbs:
        score, notes = thumb_checklist(h)
        ranked_h.append({**{k: str(v) for k, v in h.items()}, "score": score, "notes": notes})
    ranked_t.sort(key=lambda x: -x["score"])
    ranked_h.sort(key=lambda x: -x["score"])
    return {"titles": ranked_t, "thumbnails": ranked_h, "pick_title": ranked_t[0]["text"],
            "pick_thumbnail": 0}


def save(project_dir, pack: dict) -> None:
    store.save(store.video_file(project_dir, "pack"), pack)


def load(project_dir) -> dict | None:
    return store.load(store.video_file(project_dir, "pack"), None)
