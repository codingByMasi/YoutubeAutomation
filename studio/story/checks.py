"""Deterministic script checks that need no LLM: word counts vs seconds, sentence length and rhythm."""

from __future__ import annotations

import re
import statistics

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    """Split narration into sentences."""
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


def words(text: str) -> int:
    return len(text.split())


def wordcount_problems(pkg: dict, profile: dict) -> list[str]:
    """Words vs est_seconds per segment, and total length against the channel type's range."""
    segs = pkg.get("segments") or []
    wps, tol = float(profile["wps"]), float(profile["wps_tolerance"])
    problems, bad = [], []
    for i, s in enumerate(segs, 1):
        est = s.get("est_seconds")
        if not isinstance(est, (int, float)) or est <= 0:
            continue
        n = words(str(s.get("narration", "")))
        want = est * wps
        if not (1 - tol) * want <= n <= (1 + tol) * want:
            bad.append(f"segment {i}: {n} words but est_seconds={est:g} implies about {want:.0f} "
                       f"(set est_seconds = words / {wps:g})")
    problems += bad[:5]
    if len(bad) > 5:
        problems.append(f"... and {len(bad) - 5} more segments with words not matching est_seconds")
    total_words = sum(words(str(s.get("narration", ""))) for s in segs)
    secs = total_words / wps
    lo, hi = profile["min_minutes"] * 60, profile["max_minutes"] * 60
    if segs and secs < lo * 0.85:
        problems.append(f"narration is {total_words} words = about {secs / 60:.1f} min at {wps:g} words/s; "
                        f"this channel type targets {profile['min_minutes']}-{profile['max_minutes']} min "
                        f"({int(lo * wps)}-{int(hi * wps)} words). Add depth, not filler.")
    if segs and secs > hi * 1.2:
        problems.append(f"narration is {total_words} words = about {secs / 60:.1f} min, over the "
                        f"{profile['max_minutes']} min target ({int(hi * wps)} words). Cut the weakest section.")
    return problems


def sentence_problems(pkg: dict, profile: dict) -> list[str]:
    """Sentence-length cap, rhythm variety and banned phrases from the profile's own list."""
    cap = int(profile["sentence_max_words"])
    out: list[str] = []
    all_sents: list[int] = []
    long_ones: list[str] = []
    for i, seg in enumerate(pkg.get("segments") or [], 1):
        for s in sentences(str(seg.get("narration", ""))):
            n = words(s)
            all_sents.append(n)
            if n > cap:
                long_ones.append(f"segment {i}: {n} words: {s[:70]!r}")
    if all_sents and long_ones and (len(long_ones) / len(all_sents) > 0.04 or max(all_sents) > cap + 8):
        out.append(f"{len(long_ones)} sentence(s) are over the {cap}-word cap (write for the ear). Split these: "
                   + "; ".join(long_ones[:4]))
    if len(all_sents) >= 12 and not profile.get("kids"):
        mean = statistics.fmean(all_sents)
        cv = statistics.pstdev(all_sents) / mean if mean else 0
        if cv < 0.3:
            out.append(f"sentence lengths are too even (variation {cv:.2f}, need 0.30+): mix short punches of 3-6 "
                       "words with longer 12-18 word sentences.")
    return out


def banned_problems(pkg: dict, profile: dict) -> list[str]:
    """Banned phrases from the channel profile's list (40+ cliches) in narration."""
    from studio.story.banned import banned_in
    extra = profile.get("extra_banned") or []
    out = []
    for i, seg in enumerate(pkg.get("segments") or [], 1):
        for p in banned_in(str(seg.get("narration", "")), extra):
            out.append(f"segment {i}: banned phrase {p!r} - reword it")
    return out[:8]


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 and not w.endswith(("le", "ee")) else 0)
    return max(1, n)


def reading_grade(text: str) -> float | None:
    """Flesch-Kincaid grade of the narration: textstat when installed, else the same formula in code."""
    if not text.strip():
        return None
    try:
        import textstat
        return float(textstat.flesch_kincaid_grade(text))
    except ImportError:
        pass
    sents, ws = sentences(text), re.findall(r"[A-Za-z']+", text)
    if not sents or not ws:
        return None
    return 0.39 * len(ws) / len(sents) + 11.8 * sum(_syllables(w) for w in ws) / len(ws) - 15.59


def readability_problems(pkg: dict, profile: dict) -> list[str]:
    cap = profile.get("max_grade")
    if not cap:
        return []
    g = reading_grade(" ".join(str(s.get("narration", "")) for s in pkg.get("segments") or []))
    if g is not None and g > cap:
        return [f"reading level is grade {g:.1f}; this channel type's cap is {cap:g}. Use shorter words and sentences."]
    return []


def profile_problems(pkg: dict, profile: dict) -> list[str]:
    """All profile-driven script checks that are switched on for this channel type."""
    from studio.story.profile import enabled
    out: list[str] = []
    if enabled(profile, "word_count_check"):
        out += wordcount_problems(pkg, profile)
    if enabled(profile, "sentence_rules"):
        out += sentence_problems(pkg, profile) + banned_problems(pkg, profile) + readability_problems(pkg, profile)
    return out
