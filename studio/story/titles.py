"""Title checks done in code: does the opening deliver the title's promise, and which title ranks best."""

from __future__ import annotations

import re

STOP = set("a an the of to in on for and or how why what is are does do did can with my your their its this that "
           "you we it at by from vs about really actually".split())


def _stems(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        if w in STOP or len(w) < 3:
            continue
        for suf in ("ing", "es", "s", "ed"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def picked_title(pkg: dict) -> str:
    return next((t["text"] for t in pkg.get("titles", []) if t.get("is_pick")), "")


def promise_coverage(pkg: dict, segments: int = 2) -> float:
    """Share of the picked title's key words that appear in the first `segments` segments' narration."""
    key = _stems(picked_title(pkg))
    if not key:
        return 1.0
    opening = _stems(" ".join(str(s.get("narration", "")) for s in (pkg.get("segments") or [])[:segments]))
    return len(key & opening) / len(key)


def promise_problems(pkg: dict, minimum: float = 0.5) -> list[str]:
    """title_promise_fulfilled: the first two segments must deliver what the picked title promises."""
    cov = promise_coverage(pkg)
    if cov < minimum:
        return [f"The picked title \"{picked_title(pkg)}\" is not delivered in the first two segments "
                f"(only {cov * 100:.0f}% of its key words appear). Name the title's subject and promise in the hook, "
                "or pick a title that matches the opening."]
    return []


def score_title(text: str, opening: str = "") -> float:
    """0-100 heuristic: curiosity (number/question/contrast), clarity (length, no shouting), promise match."""
    s = 50.0
    if re.search(r"\d", text):
        s += 10
    if "?" in text or re.match(r"(?i)(why|how|what|the truth|inside)\b", text):
        s += 10
    if re.search(r"(?i)\b(but|not|never|actually|secret|real|hidden)\b", text):
        s += 6
    n = len(text)
    s += 10 if 35 <= n <= 62 else -10 if n > 69 else 0
    if any(len(w) > 3 and w.isupper() for w in re.findall(r"[A-Za-z]+", text)):
        s -= 20
    if opening:
        s += 20 * len(_stems(text) & _stems(opening)) / max(1, len(_stems(text)))
    return round(min(100.0, max(0.0, s)), 1)


def rank_titles(titles: list[dict], opening: str = "") -> list[dict]:
    """Titles with a `score`, best first (combine with the regex checklist in the quality gate)."""
    return sorted(({**t, "score": score_title(t.get("text", ""), opening)} for t in titles),
                  key=lambda t: -t["score"])
