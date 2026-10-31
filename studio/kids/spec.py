"""Kids script format: vocabulary, validation and helpers. Pure functions, no I/O."""

from __future__ import annotations

import re

CHARACTERS = ["duck", "cat", "dog", "fish", "bunny", "bird", "star", "sun", "apple", "ball", "balloon", "flower"]
BACKGROUNDS = ["sky", "meadow", "ocean", "night", "farm"]
MOTIONS = ["bounce", "sway", "slide", "pop"]
KINDS = ["nursery_rhyme", "counting", "colors", "animals", "shapes", "bedtime"]
SOURCES = ["original", "public_domain"]
COLORS = ["red", "orange", "yellow", "green", "blue", "purple", "pink"]

# Existing franchises: never imitate their characters, songs or titles. Matched on whole words.
BANNED_NAMES = ["cocomelon", "jj", "pinkfong", "baby shark", "bluey", "peppa", "paw patrol", "ms rachel",
                "little baby bum", "super simple", "disney", "sesame", "mickey", "elmo"]
MAX_LINES_PER_SCENE = 4
MAX_WORDS_PER_LINE = 8
MIN_SCENES = 4


def words(text: str) -> int:
    return len(text.split())


def _banned(text: str) -> list[str]:
    low = text.lower()
    return [n for n in BANNED_NAMES if re.search(rf"\b{re.escape(n)}\b", low)]


def validate(data: dict) -> list[str]:
    """Return a list of problems with a kids script answer; empty means it is usable."""
    p: list[str] = []
    if not isinstance(data, dict):
        return ["The answer must be a JSON object."]
    for key in ("title", "description"):
        if not str(data.get(key, "")).strip():
            p.append(f"`{key}` is required.")
    if data.get("kind") not in KINDS:
        p.append(f"`kind` must be one of {KINDS}.")
    if data.get("source") not in SOURCES:
        p.append(f"`source` must be one of {SOURCES}.")
    elif data["source"] == "public_domain" and not str(data.get("source_note", "")).strip():
        p.append("`source_note` is required for public_domain: name the rhyme, where the text comes from and "
                 "why it is public domain (the words only; not a modern recording or arrangement).")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < MIN_SCENES:
        return p + [f"`scenes` must be a list of at least {MIN_SCENES} scenes."]
    chorus_texts = []
    for i, s in enumerate(scenes, 1):
        tag = f"scene {i}"
        if s.get("kind") not in ("verse", "chorus"):
            p.append(f"{tag}: `kind` must be verse or chorus.")
        lines = s.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES_PER_SCENE:
            p.append(f"{tag}: `lines` needs 1 to {MAX_LINES_PER_SCENE} lines.")
            continue
        for ln in lines:
            if not isinstance(ln, str) or not ln.strip() or words(ln) > MAX_WORDS_PER_LINE:
                p.append(f"{tag}: every line needs 1 to {MAX_WORDS_PER_LINE} words (got {ln!r}).")
        if s.get("kind") == "chorus":
            chorus_texts.append(tuple(lines))
        v = s.get("visual") or {}
        if v.get("background") not in BACKGROUNDS:
            p.append(f"{tag}: visual.background must be one of {BACKGROUNDS}.")
        if v.get("motion") not in MOTIONS:
            p.append(f"{tag}: visual.motion must be one of {MOTIONS}.")
        if v.get("camera") not in (None, "zoom_in", "zoom_out", "pan_left", "pan_right"):
            p.append(f"{tag}: visual.camera must be zoom_in, zoom_out, pan_left or pan_right if given.")
        chars = v.get("characters")
        if not isinstance(chars, list) or not chars or any(c not in CHARACTERS for c in chars):
            p.append(f"{tag}: visual.characters must be a non-empty list from {CHARACTERS}.")
        cnt = v.get("count", len(chars) if isinstance(chars, list) else 1)
        if not isinstance(cnt, int) or not 1 <= cnt <= 10:
            p.append(f"{tag}: visual.count must be a whole number from 1 to 10.")
    if len(chorus_texts) < 2:
        p.append("The chorus must appear at least twice (kind=chorus) so children can sing along.")
    elif len(set(chorus_texts)) != 1:
        p.append("Every chorus scene must repeat the same lines word for word.")
    blob = " ".join([str(data.get("title", "")), str(data.get("description", "")),
                     " ".join(str(t) for t in data.get("tags", []))]
                    + [ln for s in scenes for ln in (s.get("lines") or []) if isinstance(ln, str)])
    for name in _banned(blob):
        p.append(f"Mentions {name!r}. Do not reference or imitate existing kids' franchises.")
    return p


def scene_words(scene: dict) -> int:
    return sum(words(ln) for ln in scene["lines"])
