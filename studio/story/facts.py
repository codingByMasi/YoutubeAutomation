"""Verified fact ledger: facts.json is written by the story_plan task (with web search); code verifies each fact.

Verification fetches `source_url`, confirms HTTP success and that the figure (or quote) appears in the page text.
Statuses: verified | unverified (page read, figure not found) | unfetchable (error, blocked, not text).
Outline and script prompts see only ids + status; narration numbers and chart values must trace to fact ids.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

FACT_KEYS = ("id", "claim", "figure", "unit", "year", "source_url", "quote_snippet", "is_estimate")
UA = "Mozilla/5.0 (compatible; YouTubeChannelStudio/1.0; fact-check; +https://github.com/codingByMasi)"
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9,
         "t": 1e12, "tn": 1e12, "trillion": 1e12, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7}
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%|percent|per cent|"
                 r"thousand|million|billion|trillion|lakhs?|crores?|mn|bn|tn|[kmbt])?\b", re.I)
ESTIMATE_WORDS = re.compile(r"\b(about|around|roughly|approximately|approx|estimated|estimate|nearly|almost|"
                            r"some|up to|more than|over|close to|an estimated)\b|~", re.I)
Fetcher = Callable[[str], tuple[int, str]]  # url -> (http status, page text)


# ---------- numbers ----------
def parse_numbers(text: str) -> list[tuple[float, bool]]:
    """[(value scaled by million/billion/..., is_percent)] for every number in text."""
    out = []
    for m in NUM.finditer(text):
        raw = float(m.group(1).replace(",", ""))
        suf = (m.group(2) or "").lower()
        if suf in ("%", "percent", "per cent"):
            out.append((raw, True))
        else:
            out.append((raw * SCALE.get(suf, 1.0), False))
    return out


def to_number(figure: object) -> float | None:
    """A fact's `figure` (number or string like '1.2 billion') as a plain float, else None."""
    if isinstance(figure, bool):
        return None
    if isinstance(figure, (int, float)):
        return float(figure)
    nums = parse_numbers(str(figure))
    return nums[0][0] if nums else None


def close(a: float, b: float, rel: float = 0.011) -> bool:
    """Equal within ~1% (rounding)."""
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def numbers_match(a: float, b: float) -> bool:
    """True if a and b are the same figure, allowing 1.2B vs 1,200M style scale differences."""
    if close(a, b):
        return True
    if a == 0 or b == 0:
        return False
    for scale in (1e3, 1e6, 1e9, 1e12, 1e5, 1e7):
        if close(a * scale, b) or close(a, b * scale):
            return True
    return False


# ---------- fetching ----------
def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))).strip()


def default_fetcher(url: str) -> tuple[int, str]:
    """GET a page with a timeout and user-agent. Returns (status, text); (0, reason) on network failure."""
    import requests
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": UA, "Accept": "text/html,text/plain,*/*"})
    except requests.RequestException as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    ctype = r.headers.get("content-type", "").lower()
    if "pdf" in ctype or not ("text" in ctype or "html" in ctype or "json" in ctype or "xml" in ctype):
        return r.status_code, ""
    if "html" in ctype:
        return r.status_code, extract_text(r.text)
    return r.status_code, r.text


def extract_text(raw_html: str) -> str:
    """Main text of a page: trafilatura when installed (cleaner), else the built-in tag stripper.

    The stripped text is always included too, so a figure in a table trafilatura drops is still found."""
    plain = html_to_text(raw_html)
    try:
        import trafilatura
        main = trafilatura.extract(raw_html, include_tables=True, include_comments=False) or ""
    except Exception:  # noqa: BLE001 - optional dependency; any failure falls back to the plain text
        return plain
    return f"{main}\n{plain}" if main else plain


def _cached(cache: Path | None, url: str, fetch: Fetcher) -> tuple[int, str]:
    if cache is None:
        return fetch(url)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["status"] == 200:  # failures are retried next time
            return d["status"], d["text"]
    status, text = fetch(url)
    f.write_text(json.dumps({"url": url, "status": status, "text": text[:400000]}), encoding="utf-8")
    return status, text


# ---------- verification ----------
def figure_in_text(figure: object, text: str) -> bool:
    """True if the number appears in the page text (tolerates 1.2B vs 1,200 million, 12% vs 12 percent)."""
    target = to_number(figure)
    if target is None:
        return False
    for val, is_pct in parse_numbers(text):
        if numbers_match(val, target):
            return True
    return False


def snippet_in_text(snippet: str, text: str) -> bool:
    """True if the quoted snippet (or nearly all of its words, in order-free coverage) is on the page."""
    norm = lambda s: re.sub(r"[^a-z0-9% ]+", " ", s.lower())  # noqa: E731
    a, b = " ".join(norm(snippet).split()), " ".join(norm(text).split())
    if len(a) < 12:
        return False
    if a in b:
        return True
    try:
        from rapidfuzz import fuzz  # optional: tolerant of small wording differences
        if len(a) <= len(b) and fuzz.partial_ratio(a, b) >= 92:
            return True
    except ImportError:
        pass
    toks = [w for w in a.split() if len(w) > 3]
    if len(toks) < 4:
        return False
    page = set(b.split())
    return sum(w in page for w in toks) / len(toks) >= 0.9


def verify_fact(fact: dict, fetch: Fetcher = default_fetcher, cache: Path | None = None) -> dict:
    """Copy of the fact with status (verified|unverified|unfetchable), http_status and a note."""
    out = dict(fact)
    url = str(fact.get("source_url") or "").strip()
    out["checked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    if not url.startswith(("http://", "https://")):
        return {**out, "status": "unfetchable", "http_status": None, "note": "no source_url"}
    status, text = _cached(cache, url, fetch)
    out["http_status"] = status
    if not 200 <= status < 300 or not text:
        why = text[:80] if status == 0 else f"HTTP {status}" if not 200 <= status < 300 else "not a text page"
        return {**out, "status": "unfetchable", "note": f"could not read the source ({why})"}
    if figure_in_text(fact.get("figure"), text):
        return {**out, "status": "verified", "note": "figure found in the page text"}
    if fact.get("quote_snippet") and snippet_in_text(str(fact["quote_snippet"]), text):
        return {**out, "status": "verified", "note": "quote found in the page text"}
    return {**out, "status": "unverified", "note": "page read but neither the figure nor the quote is in it"}


def verify_all(facts: list[dict], fetch: Fetcher = default_fetcher, cache: Path | None = None) -> list[dict]:
    """Verify every fact; one failing fetch never stops the rest."""
    out = []
    for f in facts:
        try:
            out.append(verify_fact(f, fetch, cache))
        except Exception as exc:  # noqa: BLE001 - a bad fact must not stop the batch
            out.append({**f, "status": "unfetchable", "note": f"{type(exc).__name__}: {exc}"})
    return out


# ---------- schema + files ----------
def validate_facts(facts: object) -> list[str]:
    """Shape problems in the facts list from story_plan."""
    if not isinstance(facts, list) or not facts:
        return ["facts must be a non-empty list"]
    problems, seen = [], set()
    for i, f in enumerate(facts, 1):
        if not isinstance(f, dict):
            problems.append(f"fact {i} is not an object")
            continue
        fid = str(f.get("id", "")).strip()
        if not fid or fid in seen:
            problems.append(f"fact {i}: id is empty or duplicated ({fid!r})")
        seen.add(fid)
        for k in ("claim", "unit", "source_url"):
            if k not in f:
                problems.append(f"fact {fid or i}: missing {k}")
        if not str(f.get("claim", "")).strip():
            problems.append(f"fact {fid or i}: claim is empty")
        if "is_estimate" not in f or not isinstance(f.get("is_estimate"), bool):
            problems.append(f"fact {fid or i}: is_estimate must be true or false")
        if f.get("figure") is not None and to_number(f.get("figure")) is None:
            problems.append(f"fact {fid or i}: figure {f.get('figure')!r} is not a number (use null for no figure)")
        if not f.get("is_estimate") and not str(f.get("source_url", "")).startswith("http"):
            problems.append(f"fact {fid or i}: a non-estimate fact needs a real https source_url")
    return problems


def facts_path(project: Path) -> Path:
    return project / "facts.json"


def load_facts(project: Path) -> list[dict]:
    p = facts_path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_facts(project: Path, facts: list[dict]) -> None:
    facts_path(project).write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")


def prompt_view(facts: list[dict]) -> list[dict]:
    """What outline and script prompts see: ids, claims, figures and verification status only."""
    keys = ("id", "claim", "figure", "unit", "year", "is_estimate", "status")
    return [{k: f.get(k) for k in keys} for f in facts]


def summary(facts: list[dict]) -> str:
    n = {s: sum(f.get("status") == s for f in facts) for s in ("verified", "unverified", "unfetchable")}
    return f"{len(facts)} facts: {n['verified']} verified, {n['unverified']} unverified, {n['unfetchable']} unfetchable"


# ---------- tracing numbers in a script ----------
_SPOKEN_OK = 10  # plain counts up to ten ("three reasons") need no fact
YEAR = re.compile(r"^(1[0-9]{3}|20[0-9]{2})$")


def narration_numbers(text: str) -> list[tuple[str, float]]:
    """[(as written, scaled value)] for figures in narration; small counts and plain years are skipped."""
    out = []
    for m in NUM.finditer(text):
        raw = m.group(1)
        suf = (m.group(2) or "").lower()
        val = float(raw.replace(",", "")) * (SCALE.get(suf, 1.0) if suf not in ("%", "percent", "per cent") else 1.0)
        if not suf and val <= _SPOKEN_OK and "." not in raw:
            continue
        if not suf and YEAR.match(raw):
            continue
        out.append((m.group(0).strip(), val))
    return out


def trace_problems(pkg: dict, facts: list[dict], allow_estimates: bool = True) -> list[str]:
    """Every figure in narration and every chart value must trace to a cited fact id.

    Unverified/unfetchable facts are allowed only when flagged is_estimate and worded as estimates."""
    by_id = {str(f["id"]): f for f in facts}
    problems: list[str] = []
    for i, seg in enumerate(pkg.get("segments") or [], 1):
        text = str(seg.get("narration", ""))
        ids = [str(x) for x in (seg.get("fact_ids") or [])]
        unknown = [x for x in ids if x not in by_id]
        if unknown:
            problems.append(f"segment {i}: unknown fact id(s) {unknown}; use ids from facts.json")
        cited = [by_id[x] for x in ids if x in by_id]
        figs = [v for f in cited if (v := to_number(f.get("figure"))) is not None]
        illustrative = any(w in text.lower() for w in ("made-up", "made up", "imagine", "hypothetical",
                                                       "for example", "say you", "suppose"))
        if not illustrative:
            for written, val in narration_numbers(text):
                if not any(numbers_match(val, g) for g in figs):
                    problems.append(f"segment {i}: the figure {written!r} is not in the facts it cites "
                                    f"{ids or 'none'}; add the fact (with a source) or remove the number")
        for f in cited:
            if f.get("status") in ("unverified", "unfetchable"):
                if not (allow_estimates and f.get("is_estimate")):
                    problems.append(f"segment {i}: fact {f['id']} is {f['status']} and not flagged is_estimate; "
                                    "verify it, mark it an estimate, or drop it")
                elif not ESTIMATE_WORDS.search(text):
                    problems.append(f"segment {i}: fact {f['id']} is an estimate; word it as one "
                                    "('about', 'roughly', 'an estimated')")
        chart = seg.get("chart_data")
        if chart and chart.get("values"):
            cids = [str(x) for x in (chart.get("fact_ids") or ids)]
            cfigs = [v for x in cids if x in by_id and (v := to_number(by_id[x].get("figure"))) is not None]
            illus = any(w in " ".join(map(str, [chart.get("title", ""), *(chart.get("labels") or [])])).lower()
                        for w in ("made-up", "made up", "illustrat", "hypothetical", "example"))
            if not illus:
                for v in chart["values"]:
                    if isinstance(v, (int, float)) and not any(numbers_match(float(v), g) for g in cfigs):
                        problems.append(f"segment {i}: chart value {v} does not match any fact in "
                                        f"{cids or 'none'} (add fact_ids to the chart)")
    return problems[:25]
