"""Retention review: judge a script as a first-time viewer would and say what to change, for any video.

Pure checks on the script package (no rendering), so it runs inside `qa` and `build` for every channel type and is
shown in the app next to the quality score. Each finding has the issue, why it loses viewers, and a concrete fix.
The visual "picture holds still" check lives in `studio.history.scene_check` (it needs the drawn frames).
"""

from __future__ import annotations

import re

CARD_SCENES = ("title", "calendar", "easel", "silhouette", "archive")  # a still card with the narrator talking over it
CARD_MAX_SECONDS = 6.0
HOOK_SECONDS = 30.0
NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
           "7": 7}
THINGS = r"(?:decisions?|mistakes?|reasons?|things?|ways?|steps?|secrets?|choices?|lessons?|rules?|moments?|causes?|" \
         r"problems?|moves?|blunders?|errors?|factors?)"
PROMISE = re.compile(rf"\b({'|'.join(NUMBERS)})\s+(?:[a-z]+\s+)?({THINGS})\b", re.I)
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh")
WORD_N = {1: ("one", "1"), 2: ("two", "2"), 3: ("three", "3"), 4: ("four", "4"), 5: ("five", "5"), 6: ("six", "6"),
          7: ("seven", "7")}
BACKSTORY = re.compile(r"\b(?:go back|rewind|back to the beginning|born|in the beginning|years earlier|let'?s start)\b|"
                       r"\b(?:1[0-9]{3}|20[0-9]{2})\b", re.I)
WEIGHT = {"major": 2.0, "minor": 1.0}


def _dur(seg: dict) -> float:
    return float(seg.get("real_seconds") or seg.get("est_seconds") or 0)


def _item(key: str, severity: str, issue: str, why: str, fix: str, segments: list[int] | None = None) -> dict:
    return {"id": key, "severity": severity, "issue": issue, "why": why, "fix": fix, "segments": segments or []}


def uncounted_promise(segs: list[dict]) -> list[dict]:
    """The hook promises N things ("three decisions") but the script never counts them out."""
    if not segs:
        return []
    m = PROMISE.search(str(segs[0].get("narration", "")))
    if not m:
        return []
    n, noun = NUMBERS[m.group(1).lower()], m.group(2).lower().rstrip("s")
    found: set[int] = set()
    for seg in segs[1:]:
        text = str(seg.get("narration", "")).lower()
        counter = (seg.get("scene_data") or {}).get("counter") if isinstance(seg.get("scene_data"), dict) else None
        if isinstance(counter, dict) and int(counter.get("of") or 0) == n and 1 <= int(counter.get("n") or 0) <= n:
            found.add(int(counter["n"]))
        for k in range(1, n + 1):
            names = "|".join(WORD_N[k])
            ordinal = ORDINALS[k - 1]
            if re.search(rf"\b(?:{noun}s?|number|reason|step|move|mistake|decision)\s+(?:{names})\b", text) or \
                    re.search(rf"\b{ordinal}\b", text):
                found.add(k)
    if len(found) >= n:
        return []
    return [_item(
        "uncounted_promise", "major",
        f"The hook promises \"{m.group(0)}\" but only {len(found)} of {n} are counted out later.",
        "The viewer is waiting for the answer and cannot tell how far in they are, so there is nothing to wait for.",
        f"Name each one as it arrives (\"{noun.capitalize()} one ...\", \"{noun.capitalize()} two ...\") and add "
        f"scene_data.counter {{\"n\": 1, \"of\": {n}, \"label\": \"{noun.capitalize()}\"}} to that segment so "
        "the screen shows the count.", [1])]


def weak_start(segs: list[dict]) -> list[dict]:
    """The first 30 seconds: a still hook picture, or backstory right after the hook."""
    out: list[dict] = []
    if not segs:
        return out
    if segs[0].get("scene") in CARD_SCENES:
        out.append(_item("hook_card", "major", f"The hook is shown on a still {segs[0]['scene']} card.",
                         "The first seconds decide whether a viewer stays; a card with nothing happening loses them.",
                         "Open on a skit or an action scene that shows the moment the hook describes.", [1]))
    t = 0.0
    for i, seg in enumerate(segs, 1):
        if i > 1 and t < HOOK_SECONDS and seg.get("scene") not in ("skit", None):
            first = re.split(r"(?<=[.!?])\s+", str(seg.get("narration", "")).strip())[0]
            if BACKSTORY.search(first):
                out.append(_item(
                    "backstory_first", "major",
                    f"Segment {i} (before {HOOK_SECONDS:.0f}s) turns into backstory: \"{first[:60]}\".",
                    "Right after the promise the video becomes a lecture (a date, a birth, \"go back to ...\"), the "
                    "most common place to leave.",
                    "Keep the story moving: open on a consequence or the first turn, and put the date or origin "
                    "inside a scene that has something happening.", [i]))
                break
        t += _dur(seg)
    return out


def long_cards(segs: list[dict]) -> list[dict]:
    """Still cards (title, calendar, list board, silhouette, archive) that hold the screen for too long."""
    long = [i for i, s in enumerate(segs, 1) if s.get("scene") in CARD_SCENES and _dur(s) > CARD_MAX_SECONDS]
    if not long:
        return []
    return [_item(
        "long_cards", "major",
        f"{len(long)} still card(s) hold the screen for more than {CARD_MAX_SECONDS:.0f} s "
        f"(segments {', '.join(map(str, long[:8]))}).",
        "Text under narration with nothing happening is where thumbs move.",
        "Shorten each to one line (about 15 words), or turn it into a skit, map or diagram scene with action.", long)]


def flat_skits(segs: list[dict]) -> list[dict]:
    """Skits with a single line have no room for a setup and a turn."""
    skits = [(i, s) for i, s in enumerate(segs, 1) if s.get("scene") == "skit"]
    if len(skits) < 3:
        return []
    flat = [i for i, s in skits if len(s.get("speech") or []) <= 1]
    if len(flat) * 2 <= len(skits):
        return []
    return [_item(
        "flat_skits", "major", f"{len(flat)} of {len(skits)} skits have one line or none.",
        "One line is a statement, not a joke: there is no setup, no turn and no punch.",
        "Give each skit 2-3 short lines: a setup, a twist that answers it, and a punch. Vary who speaks and where.",
        flat)]


def no_cliffhangers(segs: list[dict]) -> list[dict]:
    """Chapters should end on a question or a turn the next one answers."""
    ends = [i for i in range(len(segs)) if i + 1 == len(segs) or segs[i + 1].get("chapter") != segs[i].get("chapter")]
    if len(ends) < 4:
        return []
    bare = []
    for i in ends[:-1]:
        s = segs[i]
        sd = s.get("scene_data") if isinstance(s.get("scene_data"), dict) else {}
        if not (sd.get("cliff") or str(s.get("narration", "")).strip().endswith("?")):
            bare.append(i + 1)
    if len(bare) * 2 <= len(ends) - 1:
        return []
    return [_item(
        "no_cliffhangers", "minor", f"{len(bare)} of {len(ends) - 1} chapters end without a question or a turn.",
        "A chapter that ends flat gives the viewer a natural place to stop.",
        "End each chapter on the question the next one answers, and add scene_data.cliff with it so the screen "
        "shows it.",
        bare)]


def no_peak(segs: list[dict]) -> list[dict]:
    """The emotional peak (the human cost) needs room: a held scene with no joke."""
    if len(segs) < 8:
        return []
    half = len(segs) // 2
    held = [s for s in segs[half:] if s.get("emotion") == "warm" and _dur(s) >= 10
            and (s.get("scene") in ("skit", "silhouette")) and len(s.get("speech") or []) <= 1]
    if held:
        return []
    return [_item("no_peak", "minor", "No emotional peak is given room in the second half.",
                  "Every story needs one moment that is slowed down and played straight; without it the ending "
                  "has nothing to land on.",
                  "Give the human cost (a named person, the retreat, the loss) its own 12-20 s segment: emotion "
                  "'warm', one held shot, at most one line, no joke.")]


def no_narrator(pkg: dict, segs: list[dict]) -> list[dict]:
    """Drawn scenes need the narrator on screen: a voice with no face is the first thing viewers notice."""
    if not any(s.get("scene") for s in segs) or str(pkg.get("narrator") or "").strip():
        return []
    return [_item("no_narrator", "major", "The narration has no visible speaker: no narrator character is set.",
                  "Viewers hear a voice for most of the video and see nobody talking, so the picture and the voice "
                  "feel unrelated.",
                  "Add a top-level `narrator` (the name of a character the script describes, for example the "
                  "storyteller) so it is shown on screen with its mouth moving to the narration.")]


def no_places(segs: list[dict]) -> list[dict]:
    """Skits should say where and when they happen, so the backdrop and the line belong together."""
    skits = [(i, s) for i, s in enumerate(segs, 1) if s.get("scene") == "skit"]
    if len(skits) < 3:
        return []
    bare = [i for i, s in skits if not (isinstance(s.get("scene_data"), dict) and s["scene_data"].get("place"))]
    if len(bare) * 2 <= len(skits):
        return []
    return [_item("no_places", "minor", f"{len(bare)} of {len(skits)} skits have no place and date tag.",
                  "Without a tag the viewer cannot tell where a scene is, so a generic hall or field means nothing.",
                  "Add scene_data.place to each skit (for example \"Notre-Dame, Paris, 1804\"); it is shown in the "
                  "corner of the scene.", bare)]


def review(pkg: dict) -> dict:
    """{score (0-10), items} for a script package. Each item: id, severity, issue, why, fix, segments."""
    segs = [s for s in (pkg.get("segments") or []) if isinstance(s, dict)]
    items = (uncounted_promise(segs) + weak_start(segs) + long_cards(segs) + flat_skits(segs) + no_cliffhangers(segs)
             + no_peak(segs) + no_narrator(pkg, segs) + no_places(segs))
    score = max(0.0, 10.0 - sum(WEIGHT[i["severity"]] for i in items))
    return {"score": round(score, 1), "items": items}


def lines(rev: dict) -> list[str]:
    """One plain line per finding, for the QA warnings and the CLI."""
    return [f"Retention: {i['issue']} Fix: {i['fix']}" for i in rev["items"]]
