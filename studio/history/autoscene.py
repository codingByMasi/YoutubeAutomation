# ruff: noqa: E501  (keyword patterns)
"""Pick a scene for every history segment from what its narration says (who acts, where, what happens).

A pasted or old-shaped script has no `scene`, `cast` or `speech` keys. Without them the visuals stage used to fall
back to stock footage, photos, text cards and charts. This module fills the missing keys so every segment is drawn
by the cast renderer (`studio/history/render.py`). It never overwrites keys the script already has, and it never
adds a `photo`: photos and charts stay rare exceptions that the script must ask for.

Rules in plain words:
- violence or loss -> `silhouette` (never drawn in detail);
- two or more places we can put on the map -> `map` with a route through them;
- "first / then / finally" steps -> `diagram`; "N days" -> `calendar`;
- the first segment of a later chapter may open with the `lectern` host (at most every other chapter);
- everything else -> `skit`, with the characters picked from the words (money -> Madame Coin, plans -> Vizier Vex ...)
  and one or two short speech lines taken from the narration.
- the same scene type is never used three times in a row (`cast.scene_problems` enforces the same rule).
"""

from __future__ import annotations

import json
import re
from collections import Counter

from studio.history import cast

# Places on the schematic western-Mediterranean map in studio/history/render.py (x, y are 0..1 on that map).
PLACES: dict[str, tuple[float, float]] = {
    "spain": (0.14, 0.58), "iberia": (0.14, 0.58), "saguntum": (0.21, 0.58), "new carthage": (0.19, 0.70),
    "cartagena": (0.19, 0.70), "ebro": (0.25, 0.52), "pyrenees": (0.27, 0.46), "gaul": (0.42, 0.30),
    "rhone": (0.46, 0.38), "massilia": (0.47, 0.42), "alps": (0.58, 0.30), "po valley": (0.66, 0.34),
    "trebia": (0.66, 0.34), "rome": (0.72, 0.48), "italy": (0.74, 0.44), "trasimene": (0.70, 0.40),
    "cannae": (0.84, 0.54), "capua": (0.78, 0.56), "sardinia": (0.45, 0.66), "carthage": (0.62, 0.89),
    "africa": (0.40, 0.90), "zama": (0.54, 0.90), "numidia": (0.30, 0.90),
}
_STEP = re.compile(r"\b(first|second|third|then|next|finally|after that|step)\b", re.I)
_KILL = re.compile(r"\b(kill\w*|massacre\w*|slaughter\w*|executed|execution|crucif\w+|dead|died|death|bloodbath|"
                   r"slain|perish\w*|destroyed the city|burned? (?:it|the city)|butcher\w*)\b", re.I)
_DAYS = re.compile(r"\b(\d{1,2})\s+(days?|weeks?)\b", re.I)
_WHO: list[tuple[str, re.Pattern]] = [
    ("coin", re.compile(r"\b(tax\w*|tribute|debt|pay\w*|paid|silver|gold|talents?|coin\w*|cost\w*|money|price|ransom|"
                        r"indemnit\w+|treasur\w+|wage\w*|bankrupt\w*|loan\w*|ledger)\b", re.I)),
    ("vex", re.compile(r"\b(senate|senator\w*|plot\w*|scheme\w*|advis\w+|court\w*|politic\w+|treaty|treaties|"
                       r"negotiat\w+|secret\w*|rival\w*|council|oath)\b", re.I)),
    ("blunder", re.compile(r"\b(battle|general\w*|commander\w*|army|armies|soldier\w*|charge[ds]?|attack\w*|"
                           r"invad\w+|war|siege|legion\w*|mercenar\w+|victory|defeat\w*)\b", re.I)),
    ("dash", re.compile(r"\b(news|messenger|rode|arriv\w+|rumou?rs?|report\w*|word came|reached|sent word)\b", re.I)),
    ("brine", re.compile(r"\b(fleet\w*|ship\w*|sea|navy|naval|harbou?r\w*|sail\w*|blockade\w*|ports?|galley|galleys)\b", re.I)),
    ("hindsight", re.compile(r"\b(warning\w*|ignored|mistake\w*|overlooked|clue\w*|hindsight|should have|unaware|"
                             r"did not know|didn't know)\b", re.I)),
    ("ironhand", re.compile(r"\b(weapon\w*|iron|forge\w*|smith\w*|steel|armou?r\w*|catapult\w*|engineer\w*|"
                            r"factory|factories|siege engine\w*)\b", re.I)),
    ("alma", re.compile(r"\b(years? later|months? later|winter|spring|summer|autumn|\d{3,4}\s?(?:bc|bce|ad|ce))\b", re.I)),
    ("dusty", re.compile(r"\b(why|how come|wait|really\?|who paid|what\?)\b", re.I)),
]
_NOT_NAMES = {"the", "a", "an", "but", "and", "so", "then", "when", "after", "before", "in", "on", "at", "it", "he",
              "she", "they", "this", "that", "these", "those", "i", "we", "you", "his", "her", "their", "if", "as",
              "by", "for", "from", "with", "one", "two", "three", "part", "january", "february", "march", "april",
              "may", "june", "july", "august", "september", "october", "november", "december", "roman", "romans",
              "carthaginian", "carthaginians", "bc", "ad", "bce", "ce", "what", "why", "how", "who", "now", "here",
              "there", "not", "no", "yes", "some", "every", "each", "all", "once", "later", "meanwhile", "still"}
_STOP_TAIL = {"a", "an", "the", "of", "to", "and", "but", "in", "on", "at", "for", "with", "by", "that", "which", "was", "from", "than", "into", "over", "about",
              "is", "were", "his", "her", "their", "its"}


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'’$%.-]+", text)


def _trim_line(text: str, limit: int = cast.MAX_SPEECH_WORDS) -> str:
    """A short on-screen line from a sentence: first clause, at most `limit` words, no dangling article."""
    text = re.sub(r"^(and|but|so|then|now|well|however|meanwhile)\b[, ]*", "", text.strip(), flags=re.I)
    clause = re.split(r"[;:,—]| - ", text, maxsplit=1)[0]
    if len(clause.split()) > limit - 2:  # still long: stop at the first "and"/"but"/"while" if that leaves a real line
        head = re.split(r"\s+(?:and|but|while|because|so|as)\s+", clause, maxsplit=1)[0]
        if len(head.split()) >= 3:
            clause = head
    words = clause.split()
    if len(words) < 3:
        words = text.split()
    words = words[:limit]
    while len(words) > 3 and words[-1].lower().strip(".,!?") in _STOP_TAIL:
        words.pop()
    out = " ".join(words).strip(" ,;:-")
    return out[:1].upper() + out[1:] if out else ""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.strip().split()) >= 3]


def _quoted(text: str) -> list[str]:
    return [q.strip() for q in re.findall(r"[\"“]([^\"”]{6,80})[\"”]", text) if len(q.split()) <= cast.MAX_SPEECH_WORDS]


def places_in(text: str) -> list[str]:
    """Known map places named in `text`, in the order they are first mentioned."""
    low = text.lower()
    hits = [(low.find(p), p) for p in PLACES if re.search(rf"\b{re.escape(p)}\b", low)]
    hits.sort()
    return [p for _, p in hits]


def figures(segments: list[dict], limit: int = 3) -> list[str]:
    """Named people that recur across the script: capitalised mid-sentence somewhere, in 2+ segments, not a place."""
    place_words = {w for p in PLACES for w in p.split()}
    mid: set[str] = set()
    per_seg: list[set[str]] = []
    for seg in segments:
        here: set[str] = set()
        for sent in re.split(r"(?<=[.!?])\s+", str(seg.get("narration", ""))):
            for j, tok in enumerate(_words(sent)):
                t = tok.strip(".,!?'\u2019")
                if t[:1].isupper() and t.isalpha() and len(t) > 2 and t.lower() not in _NOT_NAMES \
                        and t.lower() not in place_words:
                    here.add(t)
                    if j > 0:
                        mid.add(t)
        per_seg.append(here)
    count: Counter[str] = Counter(t for here in per_seg for t in here)
    return [n for n, c in count.most_common(limit) if c >= 3 or (c >= 2 and n in mid)]


def _pick_cast(text: str, figs: list[str], k: int) -> list[str]:
    """Primary character from the words, a counterpart, and a recurring historical figure if the text names one."""
    primary = next((cid for cid, rx in _WHO if rx.search(text)), None)
    default = ["blunder", "vex", "coin", "dash", "hindsight"]
    primary = primary or default[k % len(default)]
    named = [f for f in figs if re.search(rf"\b{re.escape(f)}\b", text)]
    second = named[0] if named else ("dusty" if primary != "dusty" else "quill")
    out = [primary, second]
    if len(named) > 1:
        out.append(named[1])
    return out[:3]


def _speech(text: str, who: list[str]) -> list[dict]:
    lines = _quoted(text)
    if not lines:
        sents = _sentences(text)
        lines = [_trim_line(s) for s in sents[:2]]
        if len(sents) == 1 and len(sents[0].split()) > 14:
            lines = [_trim_line(sents[0])]
    out = []
    for i, ln in enumerate([ln for ln in lines if ln][:3]):
        out.append({"who": who[i % len(who)], "text": ln})
    return out


def _steps(text: str) -> list[str]:
    sents = _sentences(text)
    return [_trim_line(s, 7) for s in sents[:4]] if len(sents) >= 3 else []


def choose(seg: dict, idx: int, prev_chapter: str | None, figs: list[str], recent: list[str],
           lectern_ok: bool) -> str:
    """The scene type for one segment (see the module docstring for the rules)."""
    text = str(seg.get("narration", ""))
    kw = " ".join(str(k) for k in seg.get("visual_keywords") or [])
    if idx == 0:
        return "skit"  # the cold open is always a small scene in progress
    if idx > 0 and lectern_ok and seg.get("chapter") and seg.get("chapter") != prev_chapter:
        return "lectern"
    if _KILL.search(text) and idx > 0:
        return "silhouette"
    if len(places_in(text + " " + kw)) >= 2:
        return "map"
    if len(_STEP.findall(text)) >= 3 and len(_sentences(text)) >= 3:
        return "diagram"
    if _DAYS.search(text) and idx > 0:
        return "calendar"
    return "skit"


def assign(segments: list[dict], force: bool = False) -> int:
    """Fill `scene`/`cast`/`speech`/`scene_data` for every segment that lacks a valid scene. Returns how many changed."""
    changed = 0
    figs = figures(segments)
    recent: list[str] = []
    prev_chapter: str | None = None
    last_lectern = -99
    for i, seg in enumerate(segments):
        text = str(seg.get("narration", ""))
        have = seg.get("scene") if isinstance(seg.get("scene"), str) and seg["scene"] in cast.SCENE_TYPES else None
        if have and not force:
            recent.append(have)
            prev_chapter = seg.get("chapter") or prev_chapter
            continue
        lectern_ok = i - last_lectern >= 5
        scene = choose(seg, i, prev_chapter, figs, recent, lectern_ok)
        if len(recent) >= 2 and recent[-1] == recent[-2] == scene and scene not in ("map", "diagram"):
            scene = "skit" if scene != "skit" else "silhouette" if _KILL.search(text) else "lectern"
        who = _pick_cast(text, figs, i)
        data: dict = {}
        speech: list[dict] = []
        if scene == "lectern":
            last_lectern = i
            who = ["quill"]
            data = {"title": str(seg.get("chapter") or "")}
        elif scene == "skit":
            speech = _speech(text, who)
        elif scene == "map":
            names = places_in(text + " " + " ".join(str(k) for k in seg.get("visual_keywords") or []))[:4]
            data = {"points": [{"x": PLACES[n][0], "y": PLACES[n][1], "label": n.title()} for n in names],
                    "title": str(seg.get("chapter") or "")}
            who = [who[0]]
        elif scene == "diagram":
            data = {"steps": _steps(text), "title": str(seg.get("chapter") or "How it worked")}
            who = [who[0]]
        elif scene == "calendar":
            m = _DAYS.search(text)
            days = int(m.group(1)) * (7 if m and m.group(2).lower().startswith("week") else 1) if m else 7
            data = {"days": max(1, min(days, 31)), "title": "Days pass"}
            who = ["alma"]
        elif scene == "silhouette":
            data = {"title": _trim_line(text, 6)}
            who = [who[-1] if who[-1] not in ("dusty",) else who[0]]
        seg["scene"] = scene
        seg.setdefault("cast", who)
        if not seg.get("cast"):
            seg["cast"] = who
        if speech and not seg.get("speech"):
            seg["speech"] = speech
        if data and not seg.get("scene_data"):
            seg["scene_data"] = data
        recent.append(scene)
        prev_chapter = seg.get("chapter") or prev_chapter
        changed += 1
    return changed


def persist(script_json, segments: list[dict]) -> None:
    """Write the filled scene keys into script.json without touching any other field of the file."""
    from pathlib import Path

    p = Path(script_json)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    rows = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or len(rows) != len(segments):
        return  # the loader dropped or reshaped segments: leave the file alone rather than guess
    for row, seg in zip(rows, segments, strict=True):
        if isinstance(row, dict):
            for k in ("scene", "cast", "speech", "scene_data"):
                if k in seg and (k not in row or k == "speech"):  # speech also carries each line's audio and length
                    row[k] = seg[k]
    p.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
