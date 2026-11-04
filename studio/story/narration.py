"""Narration planning: prosody per emotion, chapter-level synthesis groups, word-timed splitting, pauses, sync report.

Pure helpers (no network): the voice stage feeds them an engine that can return word timings. Anything the engine
cannot do (no word timing) falls back to the older one-call-per-segment path.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

Word = tuple[float, float, str]
MAX_GROUP_SECONDS = 150.0


# ---------- stage directions ----------
_ACTORS = r"(?:Quill|Dusty|Dash|Vizier Vex|Vex|Captain Blunder|Blunder|Madame Coin|Coin|Admiral Brine|Brine|" \
          r"Inspector Hindsight|Hindsight|Ironhand(?: the Smith)?|Almanac Alma|Alma|She|He|They)"
_ACTIONS = (r"states?|puts?|sets?|closes?|opens?|whistles?|nods?|sighs?|pauses?|looks?|turns?|walks?|slams?|"
            r"shrugs?|grins?|smiles?|waves?|points?|picks?|lowers?|raises?|leans?|steps?|stares?|gasps?|"
            r"laughs?|winks?|clears?|taps?|folds?|unrolls?|rolls?|flips?|slides?|hands?|shakes?|frowns?")
_DIRECTION = re.compile(
    rf"^(?:(?:Then|Now|Next|Meanwhile|Finally|Slowly)[, ]+)?(?:{_ACTORS})\s+(?:{_ACTIONS})\b"
    r"|^No jokes here\b|^Nobody speaks\b|^(?:Everyone|The room) (?:goes|falls|is) (?:quiet|silent)\b|^Silence\b",
    re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def spoken(text: str) -> str:
    """Narration minus stage directions ("Quill states it plainly. Dash puts down the pen."): those describe on-screen
    action only, so they are never spoken or captioned. Text that is all direction is returned unchanged."""
    keep = [x for x in _SENT.split(text.strip()) if x and not _DIRECTION.match(x.strip())]
    return " ".join(keep) if keep else text


# ---------- prosody ----------
def emotion_of(seg: dict, idx: int) -> str:
    """The segment's emotion key for the profile's voice table."""
    e = str(seg.get("emotion") or "").strip().lower()
    if e in ("hook", "neutral", "reveal", "tense", "warm", "excited"):
        return e
    if idx == 0:
        return "hook"
    return {"reveal": "reveal", "pattern_break": "tense", "question": "neutral", "example": "warm"}.get(
        str(seg.get("beat") or ""), "neutral")


def prosody_for(profile: dict, emotion: str) -> dict:
    """{rate, pitch, volume} offsets (percent, Hz, percent) for an emotion."""
    v = profile["voice"]
    base = v.get("neutral", {})
    return {k: int((v.get(emotion) or base).get(k, 0)) for k in ("rate", "pitch", "volume")}


def edge_args(p: dict) -> dict:
    """edge-tts strings from numeric offsets."""
    return {"rate": f"{p['rate']:+d}%", "pitch": f"{p['pitch']:+d}Hz", "volume": f"{p['volume']:+d}%"}


def pause_after(profile: dict, segs: list[dict], i: int) -> float:
    """Seconds of silence to append to segment i: before a reveal (next segment) or after a loop plant."""
    pauses = profile["voice"].get("pauses", {})
    out = 0.0
    nxt = segs[i + 1] if i + 1 < len(segs) else None
    if nxt is not None and (nxt.get("beat") == "reveal" or emotion_of(nxt, i + 1) == "reveal"):
        out = max(out, float(pauses.get("before_reveal", 0.0)))
    if segs[i].get("plants_loop"):
        out = max(out, float(pauses.get("after_plant", 0.0)))
    if nxt is not None and nxt.get("chapter") and nxt.get("chapter") != segs[i].get("chapter"):
        out = max(out, float(pauses.get("chapter", 0.0)))
    return round(out, 2)


# ---------- grouping ----------
def groups(segs: list[dict], profile: dict) -> list[list[int]]:
    """Consecutive segments of one chapter and one emotion, so intonation continues; capped in length."""
    out: list[list[int]] = []
    cur: list[int] = []
    cur_key, cur_len = None, 0.0
    for i, s in enumerate(segs):
        key = (s.get("chapter") or "", emotion_of(s, i))
        dur = float(s.get("est_seconds") or 0)
        if cur and (key != cur_key or cur_len + dur > MAX_GROUP_SECONDS):
            out.append(cur)
            cur, cur_len = [], 0.0
        cur.append(i)
        cur_key, cur_len = key, cur_len + dur
    if cur:
        out.append(cur)
    return out


def group_key(texts: list[str], prosody: dict, voice: str, engine: str) -> str:
    return hashlib.sha1(json.dumps([texts, prosody, voice, engine]).encode()).hexdigest()[:16]


# ---------- splitting by word timing ----------
def _tokens(text: str) -> list[str]:
    return text.split()


def split_points(words: list[Word], texts: list[str], total: float) -> list[float] | None:
    """Cut times between segments from word timings, or None if the word counts do not line up.

    Words are matched to segments by cumulative word count; each cut sits in the gap between the last word of one
    segment and the first of the next. Mismatch above 8% means the engine tokenised differently: do not guess."""
    counts = [len(_tokens(t)) for t in texts]
    if not counts or abs(len(words) - sum(counts)) > max(2, 0.08 * sum(counts)):
        return None
    scale = len(words) / max(1, sum(counts))
    cuts, acc = [], 0
    for c in counts[:-1]:
        acc += c
        k = min(len(words) - 1, max(1, round(acc * scale)))
        cuts.append(round((words[k - 1][1] + words[k][0]) / 2, 3))
    return cuts


def words_per_segment(words: list[Word], texts: list[str], cuts: list[float]) -> list[list[Word]]:
    """Words of each segment re-based to the start of that segment's audio."""
    bounds = [0.0, *cuts, float("inf")]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        out.append([(round(s - a, 3), round(e - a, 3), w) for s, e, w in words if a <= (s + e) / 2 < b])
    return out


def ffmpeg_cut(src: Path, dst: Path, start: float, end: float | None, pad: float = 0.0) -> None:
    """Cut [start, end) from src into dst (mp3), optionally padding silence at the end."""
    exe = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [exe, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src)]
    if end is not None:
        cmd += ["-t", f"{max(0.05, end - start):.3f}"]
    if pad > 0:
        cmd += ["-af", f"apad=pad_dur={pad:.2f}"]
    cmd += ["-c:a", "libmp3lame", "-q:a", "4", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


# ---------- caption sync ----------
def sync_report(caption_words: list[Word], reference: list[Word], narrations: list[str]) -> list[dict]:
    """Per segment: drift in ms between caption word times and a reference alignment (whisper) of the audio.

    Words are paired by index inside each segment (the first and last word of the segment, the worst drift wins)."""
    counts = [len(_tokens(t)) for t in narrations]
    if not caption_words or not reference or abs(len(caption_words) - len(reference)) > 0.1 * len(reference):
        return []
    n = min(len(caption_words), len(reference))
    out, a = [], 0
    for i, c in enumerate(counts):
        b = min(n, a + c)
        if b <= a:
            continue
        pairs = [(caption_words[k], reference[k]) for k in (a, b - 1)]
        drift = max(abs(cw[0] - rw[0]) for cw, rw in pairs)
        drift = max(drift, max(abs(cw[1] - rw[1]) for cw, rw in pairs))
        out.append({"segment": i + 1, "drift_ms": round(drift * 1000)})
        a = b
    return out


def abs_words(seg_words: list[list[list]], spans: list[tuple[float, float]]) -> list[Word]:
    """Absolute word times from per-segment stored words ([s, e, text] relative to each segment's audio)."""
    out: list[Word] = []
    for ws, (start, _) in zip(seg_words, spans):
        out += [(round(start + s, 3), round(start + e, 3), t) for s, e, t in ws]
    return out


def clean_token(t: str) -> str:
    return re.sub(r"\W+", "", t.lower())
