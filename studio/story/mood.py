"""Mood-aware music plan: a mood per chapter from segment emotions, and where the bed drops before a twist."""

from __future__ import annotations

from collections import Counter

EMO_MOOD = {"tense": "tense", "reveal": "neutral", "hook": "neutral", "neutral": "neutral", "warm": "resolve",
            "excited": "resolve"}


def plan(segs: list[dict], spans: list[tuple[float, float]], profile: dict) -> dict:
    """{chapters: [(start, end, mood)], drops: [seconds], stingers: [seconds]} for the video.

    The last chapter resolves; the bed drops before `pattern_break` segments marked tense (not for kids)."""
    chapters: list[list] = []
    votes: list[Counter] = []
    for seg, (a, b) in zip(segs, spans):
        key = seg.get("chapter") or ""
        if not chapters or chapters[-1][3] != key:
            chapters.append([a, b, "neutral", key])
            votes.append(Counter())
        chapters[-1][1] = b
        votes[-1][EMO_MOOD.get(str(seg.get("emotion") or "neutral"), "neutral")] += 1
    for ch, v in zip(chapters, votes):
        ch[2] = v.most_common(1)[0][0]
    if chapters:
        chapters[-1][2] = "resolve"
    drops: list[float] = []
    stingers: list[float] = []
    for seg, (a, _) in zip(segs, spans):
        if seg.get("beat") == "reveal" and profile.get("stinger_on_reveal", True):
            stingers.append(a)
        if profile.get("drop_before_twist", True) and not profile.get("kids") and seg.get("beat") == "pattern_break" \
                and a > 5:
            drops.append(a)
    return {"chapters": [(a, b, m) for a, b, m, _ in chapters], "drops": drops, "stingers": stingers}


def mood_folder_track(music_dir, mood: str):
    """First audio file in assets/music/<mood>/ if the owner supplied one, else None."""
    from pathlib import Path
    d = Path(music_dir) / mood
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
                return p
    return None
