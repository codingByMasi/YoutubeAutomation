"""Short-form style captions: 2-4 big words at a time, the spoken word highlighted, chapter banners (ASS subtitles).

Word times come from faster-whisper when it is installed. Without it they are estimated from the segment
timings: each segment's real duration is shared between its words by length, with a pause after sentences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

Word = tuple[float, float, str]
MAX_PHRASE_WORDS, MAX_PHRASE_CHARS = 4, 26
HIGHLIGHT = "&H0000D7FF&"   # ASS colours are BGR: this is amber
MONEY = "&H0050E050&"       # green for figures
BANNER_SECONDS = 2.8


@dataclass
class CaptionStyle:
    """Sizes in pixels for a given output frame."""

    w: int = 1920
    h: int = 1080
    font: str = "DejaVu Sans"
    shorts: bool = False

    @property
    def size(self) -> int:
        return round(self.h * (0.044 if self.shorts else 0.048))

    @property
    def margin_v(self) -> int:
        return round(self.h * (0.30 if self.shorts else 0.075))


def words_from_script(spans: list[tuple[float, float]], narrations: list[str]) -> list[Word]:
    """Estimated word times: a segment's duration is shared by word length (+ a pause after sentence ends)."""
    out: list[Word] = []
    for (start, end), text in zip(spans, narrations):
        toks = text.split()
        if not toks:
            continue
        weights = [len(t.strip(".,!?;:")) + 2 + (4 if t.endswith((".", "?", "!")) else 1 if t.endswith(",") else 0)
                   for t in toks]
        scale = (end - start) / sum(weights)
        t = start
        for tok, wgt in zip(toks, weights):
            out.append((round(t, 3), round(t + wgt * scale, 3), tok))
            t += wgt * scale
    return out


def phrases(words: list[Word]) -> list[list[Word]]:
    """Group words into short on-screen phrases, breaking at punctuation and size limits."""
    out: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= MAX_PHRASE_WORDS or len(" ".join(x[2] for x in cur + [w])) > MAX_PHRASE_CHARS):
            out.append(cur)
            cur = []
        cur.append(w)
        if w[2].endswith((".", "?", "!", ",", ";", ":")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _clean(word: str) -> str:
    return re.sub(r"[{}\\]", "", word).upper()


def _ts(seconds: float) -> str:
    cs = int(round(max(seconds, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _is_figure(word: str) -> bool:
    return bool(re.search(r"\d|[$€£₹%]", word))


def to_ass(words: list[Word], style: CaptionStyle | None = None, chapters: list[tuple[float, str]] | None = None,
           window: tuple[float, float] | None = None, offset: float = 0.0) -> str:
    """ASS file text. `window` keeps only words inside (start, end) re-based to 0; `offset` shifts everything."""
    st = style or CaptionStyle()
    lo, hi = window or (0.0, float("inf"))
    base = lo if window else 0.0
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {st.w}
PlayResY: {st.h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st.font},{st.size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,{max(4, st.size // 14)},2,2,60,60,{st.margin_v},1
Style: Banner,{st.font},{round(st.size * 0.62)},&H00FFFFFF,&H000000FF,&H00201810,&H00201810,-1,0,0,0,100,100,1,0,3,14,0,7,60,60,{round(st.h * 0.06)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""  # noqa: E501
    lines = []
    for start, title in chapters or []:
        if lo <= start < hi and title:
            a = start - base + offset
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(a + BANNER_SECONDS)},Banner,,0,0,0,,"
                         f"{{\\fad(250,300)}} {_clean(title)} ")
    for ph in phrases([w for w in words if w[1] > lo and w[0] < hi]):
        for i, (s, e, _) in enumerate(ph):
            nxt = ph[i + 1][0] if i + 1 < len(ph) else e  # no gap inside a phrase: it never flickers
            a, b = max(s, lo) - base + offset, min(max(nxt, e), hi) - base + offset
            if b <= a:
                continue
            parts = []
            for j, (_, _, tok) in enumerate(ph):
                if j == i:
                    col = MONEY if _is_figure(tok) else HIGHLIGHT
                    parts.append(f"{{\\c{col}\\fscx100\\fscy100\\t(0,90,\\fscx116\\fscy116)}}{_clean(tok)}{{\\r}}")
                else:
                    parts.append(_clean(tok))
            lines.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Default,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"


def write_ass(path: Path, *args, **kw) -> Path:
    path.write_text(to_ass(*args, **kw), encoding="utf-8")
    return path
