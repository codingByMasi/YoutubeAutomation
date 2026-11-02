"""Safety screening for kids and history scripts. Flags go into the quality gate; nothing is ever auto-published.

Text: Detoxify when installed, else a keyword list. Frames: an NSFW classifier only if one is installed (otherwise
skipped and said so). Kids use the strict list; history flags graphic-violence wording that risks demonetization.
"""

from __future__ import annotations

import importlib.util
import re

KIDS_WORDS = ("kill", "killed", "die", "died", "dead", "death", "blood", "bloody", "gun", "knife", "weapon", "monster",
              "scary", "terrify", "terrified", "hate", "stupid", "idiot", "ugly", "hurt", "cry", "crying", "fight",
              "hit him", "hit her", "alone in the dark", "buy", "subscribe", "http", "www.")
HISTORY_WORDS = ("beheaded", "decapitated", "disembowel", "gore", "mutilated", "torso", "entrails", "corpses piled",
                 "raped", "rape", "slaughtered", "massacred in graphic")


def keyword_flags(text: str, words: tuple[str, ...]) -> list[str]:
    low = text.lower()
    return [w for w in words if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low)]


def detoxify_scores(texts: list[str]) -> list[float] | None:
    """Max toxicity per text with Detoxify, or None when it is not installed / cannot load."""
    if importlib.util.find_spec("detoxify") is None:
        return None
    try:
        from detoxify import Detoxify
        res = Detoxify("original").predict(texts)
        return [max(res[k][i] for k in res) for i in range(len(texts))]
    except Exception:  # noqa: BLE001 - optional model; keywords remain
        return None


def text_issues(pkg: dict, profile: dict) -> list[dict]:
    """[{severity, text, fix}] for kids/history scripts."""
    if profile.get("name") not in ("kids", "history"):
        return []
    words = KIDS_WORDS if profile["name"] == "kids" else HISTORY_WORDS
    segs = pkg.get("segments") or []
    out = []
    scores = detoxify_scores([str(s.get("narration", "")) for s in segs]) if segs else None
    for i, s in enumerate(segs, 1):
        hits = keyword_flags(str(s.get("narration", "")), words)
        if hits:
            out.append({"severity": "critical" if profile["name"] == "kids" else "major",
                        "text": f"segment {i} uses unsafe or demonetization-risk wording: {', '.join(hits[:4])}.",
                        "fix": "Reword gently: describe feelings and consequences, not graphic detail."})
        if scores and scores[i - 1] > 0.5:
            out.append({"severity": "major", "text": f"segment {i} scores {scores[i - 1]:.2f} on the toxicity check.",
                        "fix": "Soften the wording."})
    return out


def frame_issues(frame_paths: list) -> list[dict]:
    """NSFW check on sample frames if a classifier is installed; [] (skipped) otherwise."""
    if importlib.util.find_spec("nudenet") is None:
        return []
    try:
        from nudenet import NudeDetector
        det = NudeDetector()
        bad = [str(p) for p in frame_paths if any(d.get("score", 0) > 0.6 for d in det.detect(str(p)))]
    except Exception:  # noqa: BLE001
        return []
    return [{"severity": "critical", "text": f"{len(bad)} frame(s) look unsafe: {bad[0]}",
             "fix": "Replace that clip in `visuals`."}] if bad else []
