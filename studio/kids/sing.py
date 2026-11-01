"""Turn a kids script into a singable melody plan: one note per syllable, same tune for repeated lines.

Pure functions, no I/O. The plan is written out as MIDI/USTX by `sing_files` for OpenUtau to sing.
"""

from __future__ import annotations

import hashlib
import random
import re

TEMPO = 104  # same as music.py so a sung vocal and the background bed share a pulse
PPQ = 480  # ticks per quarter note (OpenUtau's default resolution)
ROOT_MIDI = 60  # C4; the tune uses a C major pentatonic scale like music.py
PENTATONIC = [0, 2, 4, 7, 9]
REST_BEATS = 1.0
LAST_NOTE_BEATS = 2.0

_VOWEL_GROUP = re.compile(r"[aeiouy]+", re.I)


def syllables(word: str) -> int:
    """Rough English syllable count (at least 1). Good enough for simple children's words."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ie")) and n > 1:
        n -= 1  # silent final e: "little" keeps it, "hope" loses it
    if w.endswith("ed") and not w.endswith(("ted", "ded")) and n > 1:
        n -= 1
    return max(1, n)


def _pitch(step: int) -> int:
    octave, idx = divmod(step, len(PENTATONIC))
    return ROOT_MIDI + 12 * octave + PENTATONIC[idx]


def line_steps(text: str, count: int) -> list[int]:
    """Scale steps (0-9) for one lyric line. Seeded by the text, so the same line always gets the same tune."""
    rng = random.Random(int(hashlib.sha256(text.strip().lower().encode()).hexdigest()[:12], 16))
    cur = rng.choice([0, 2, 4])
    steps = []
    for _ in range(count):
        cur = min(9, max(0, cur + rng.choice([-2, -1, 0, 1, 1, 2])))
        steps.append(cur)
    return steps


def line_notes(text: str) -> list[dict]:
    """Notes for one line. A word's first note holds the word; extra syllables get "+" (OpenUtau's continuation)."""
    syl: list[str] = []
    for word in text.split():
        n = syllables(word)
        if n:
            syl += [word.strip(",.!?;:\"'")] + ["+"] * (n - 1)
    steps = line_steps(text, len(syl))
    return [{"lyric": ly, "tone": _pitch(s), "beats": 1.0} for ly, s in zip(syl, steps)]


def build_plan(script: dict, tempo: int = TEMPO) -> dict:
    """Plan for the whole song: notes with start/length in beats and seconds, plus where each scene starts."""
    beat = 60.0 / tempo
    notes, scenes, pos = [], [], 0.0
    last_scene = len(script["scenes"]) - 1
    for si, scene in enumerate(script["scenes"]):
        scenes.append({"scene": si + 1, "start_beat": pos, "start_s": round(pos * beat, 3)})
        for li, text in enumerate(scene["lines"]):
            ln = line_notes(text)
            if not ln:
                continue
            ln[-1]["beats"] = LAST_NOTE_BEATS
            if si == last_scene and li == len(scene["lines"]) - 1:
                ln[-1]["tone"] = ROOT_MIDI  # end the song on the home note
            for n in ln:
                notes.append({**n, "start_beat": pos, "start_s": round(pos * beat, 3)})
                pos += n["beats"]
            pos += REST_BEATS
    return {"title": script["title"], "tempo": tempo, "ppq": PPQ, "notes": notes, "scenes": scenes,
            "total_beats": pos, "total_s": round(pos * beat, 3)}
