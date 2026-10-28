"""Captions: faster-whisper transcription when installed, otherwise timed from the script text."""

from __future__ import annotations

from pathlib import Path

from studio.util.logging import get_logger

log = get_logger("captions")
Cue = tuple[float, float, str]
MAX_WORDS, MAX_CHARS = 8, 42


def _chunks(text: str) -> list[str]:
    out, cur = [], []
    for w in text.split():
        if cur and (len(cur) >= MAX_WORDS or len(" ".join(cur + [w])) > MAX_CHARS):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
        if w.endswith((".", "?", "!")) and len(cur) >= 3:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def script_cues(spans: list[tuple[float, float]], narrations: list[str]) -> list[Cue]:
    """Cues from the narration, timed in proportion to word count within each segment."""
    cues: list[Cue] = []
    for (start, end), text in zip(spans, narrations):
        chunks = _chunks(text)
        words = sum(len(c.split()) for c in chunks) or 1
        t = start
        for c in chunks:
            d = (end - start) * len(c.split()) / words
            cues.append((round(t, 3), round(t + d, 3), c))
            t += d
    return cues


def whisper_cues(audio: Path, model_size: str = "small") -> list[Cue] | None:
    """Word-timed cues from faster-whisper, or None if it is not installed."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    log.info("Transcribing %s with faster-whisper (%s)", audio, model_size)
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(audio), word_timestamps=True, language="en")
    cues: list[Cue] = []
    words = [w for s in segments for w in (s.words or [])]
    cur: list = []
    for w in words:
        cur.append(w)
        text = "".join(x.word for x in cur).strip()
        if len(cur) >= MAX_WORDS or len(text) > MAX_CHARS or w.word.strip().endswith((".", "?", "!")):
            cues.append((cur[0].start, cur[-1].end, text))
            cur = []
    if cur:
        cues.append((cur[0].start, cur[-1].end, "".join(x.word for x in cur).strip()))
    return cues


def ts(seconds: float) -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue], offset: float = 0.0, window: tuple[float, float] | None = None) -> str:
    """SRT text; `offset` shifts every cue, `window` keeps only cues inside (start, end) re-based to 0."""
    lines, n = [], 0
    for start, end, text in cues:
        if window:
            if end <= window[0] or start >= window[1]:
                continue
            start, end = max(start, window[0]) - window[0], min(end, window[1]) - window[0]
        n += 1
        lines.append(f"{n}\n{ts(start + offset)} --> {ts(end + offset)}\n{text}\n")
    return "\n".join(lines)
