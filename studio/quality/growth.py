"""Growth checks for the quality gate: content-aware visuals (`fit`), title/thumbnail promise (`packaging`) and
channel-level repetition (`originality`). Rules of thumb from docs/growth-playbook.md, tunable, never YouTube rules."""

from __future__ import annotations

import re

from studio.growth import packs

STOP = {"the", "a", "an", "and", "of", "to", "in", "on", "for", "is", "are", "why", "how", "what", "your", "you",
        "this", "that", "with", "from", "really", "actually", "explained", "does", "make", "makes", "money"}
GENERIC_STOCK = ("handshake", "business meeting", "businessman", "businesswoman", "skyline", "cityscape", "typing",
                 "laptop", "office", "stock market", "money falling", "dollar bills", "coins", "team meeting",
                 "boardroom", "suit", "city", "success", "growth")
YEAR = re.compile(r"\b(?:1[5-9]|20)\d\d\b")
FIGURE = re.compile(r"\d")


def _issue(dim: str, severity: str, text: str, fix: str = "") -> dict:
    return {"dimension": dim, "severity": severity, "text": text, "fix": fix}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower())]


def _terms(text: str) -> list[str]:
    return [w for w in _words(text) if len(w) >= 4 and w not in STOP]


def _has_visual_proof(seg: dict) -> bool:
    vis = seg.get("visual") or {}
    return bool(seg.get("chart_data") or vis.get("scene") or vis.get("kind") in ("chart", "scene"))


def _is_stock(seg: dict) -> bool:
    kind = (seg.get("visual") or {}).get("kind")
    return kind in ("clip", "image") and not _has_visual_proof(seg)


def _generic(seg: dict) -> bool:
    kws = [k.lower() for k in seg.get("visual_keywords") or []]
    return bool(kws) and all(any(g in k for g in GENERIC_STOCK) for k in kws)


def check_fit(pkg: dict, t: dict) -> list[dict]:
    """Does what is on screen match what the narration is about? Skipped for types without `fit_checks`."""
    segs = pkg.get("segments") or []
    if not t.get("fit_checks") or not segs:
        return []
    out = []
    if any(g.get("visual") for g in segs):
        stock = sum(_is_stock(g) for g in segs)
        if len(segs) >= 5 and stock / len(segs) > t["stock_share_max"]:
            out.append(_issue("fit", "major", f"{stock} of {len(segs)} segments are generic stock footage "
                              f"(limit {t['stock_share_max'] * 100:.0f}%).",
                              "Show the argument: charts for numbers, timelines for dates, diagrams for how it works."))
    for pos, seg in enumerate(segs, 1):
        text = seg.get("narration", "")
        dates = YEAR.findall(text)
        if len(dates) >= 3 and not _has_visual_proof(seg):
            out.append(_issue("fit", "minor", f"Segment {pos} lists {len(dates)} dates with no timeline or chart.",
                              "Add a `timeline` scene or chart_data."))
        figures = len(FIGURE.findall(text)) and len(re.findall(r"\d[\d,.]*", text))
        if figures >= 3 and not _has_visual_proof(seg) and _is_stock(seg):
            out.append(_issue("fit", "major", f"Segment {pos} reads {figures} figures over stock footage.",
                              "Replace the footage with a chart or number card."))
    generic = sum(_generic(g) for g in segs)
    if len(segs) >= 5 and generic / len(segs) > 0.35:
        out.append(_issue("fit", "minor", f"{generic} of {len(segs)} segments use cliche stock keywords "
                          "(handshake, skyline, laptop...).", "Use keywords for the exact thing being discussed."))
    topic = set(_terms(" ".join([pkg.get("topic", "")] + [x.get("text", "") for x in pkg.get("titles", [])[:1]])))
    off = [pos for pos, g in enumerate(segs, 1) if _is_stock(g) and g.get("visual_keywords")
           and topic and not (topic & set(_terms(" ".join(g["visual_keywords"] + [g.get("narration", ""),
                                                                                   g.get("chapter", "")]))))]
    if off and len(off) / len(segs) > 0.25:
        out.append(_issue("fit", "major", f"Footage in segments {off[:5]} has nothing to do with the topic.",
                          "Rewrite their visual_keywords around the topic, or use a chart or diagram."))
    return out


def _pick_title(pkg: dict) -> str:
    return next((x["text"] for x in pkg.get("titles", []) if x.get("is_pick")), "")


def check_packaging(pkg: dict, t: dict, in_series: bool | None = None) -> list[dict]:
    """Title/thumbnail promise kept by the hook, plus variants to test. `in_series` None means unknown."""
    segs = pkg.get("segments") or []
    title = _pick_title(pkg)
    out = []
    if not title or not segs:
        return out
    score, notes = packs.title_checklist(title)
    if score < 3:
        out.append(_issue("packaging", "minor", f"Title scores {score}/6 on the packaging checklist ({notes[0]}).",
                          "Try a variant with a number or a curiosity gap."))
    opening = " ".join([segs[0].get("narration", "")] + ([segs[1].get("narration", "")] if len(segs) > 1 else []))
    prefixes = {w[:5] for w in _terms(opening + " " + pkg.get("topic", ""))}
    wanted = _terms(title)
    hit = [w for w in wanted if w[:5] in prefixes]
    if wanted and len(hit) / len(wanted) < 0.34:
        out.append(_issue("packaging", "major", "The title's promise does not appear in the opening 30 seconds.",
                          "Say the title's idea in the hook, or change the title: a mismatch causes early drop-off."))
    thumbs = pkg.get("thumbnail_texts") or []
    if len(pkg.get("titles", [])) < 3 or len(thumbs) < 2:
        out.append(_issue("packaging", "minor", "Fewer than 3 titles or 2 thumbnail texts to test.",
                          "Make a pack (`pack`) so you can run YouTube's Test & Compare."))
    for th in thumbs:
        if len(str(th).split()) > 4:
            out.append(_issue("packaging", "minor", f"Thumbnail text {th!r} is over 4 words.", "Cut it to 1-4 words."))
            break
    if t.get("series_hint") and in_series is False:
        out.append(_issue("packaging", "minor", "This video is not part of a series.",
                          "Add it to a series so the end screen can lead to the next video."))
    return out


def _shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    w = _words(text)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def check_originality(pkg: dict, t: dict, peers: list[tuple[str, dict]] | None = None) -> list[dict]:
    """Flag mass-produced patterns: scripts or structures that barely differ from the channel's recent videos."""
    segs = pkg.get("segments") or []
    if not t.get("originality_checks") or not segs:
        return []
    out = []
    if not str(pkg.get("originality_note") or "").strip():
        out.append(_issue("originality", "minor", "No originality_note: what is this video's own angle?",
                          "State the original analysis or viewpoint in one sentence."))
    mine = _shingles(" ".join(g.get("narration", "") for g in segs))
    chapters = {(g.get("chapter") or "").strip().lower() for g in segs if g.get("chapter")}
    for label, other in peers or []:
        osegs = other.get("segments") or []
        theirs = _shingles(" ".join(g.get("narration", "") for g in osegs))
        sim = len(mine & theirs) / max(1, min(len(mine), len(theirs)))
        if sim > t["similarity_max"]:
            out.append(_issue("originality", "critical", f"The script repeats {sim * 100:.0f}% of {label}.",
                              "Give this video a different angle and new wording: YouTube demonetises near-copies."))
            continue
        och = {(g.get("chapter") or "").strip().lower() for g in osegs if g.get("chapter")}
        if len(chapters) >= 4 and len(chapters & och) / len(chapters) >= 0.8:
            out.append(_issue("originality", "major", f"Chapter structure is almost identical to {label}.",
                              "Vary the structure (case study, comparison, myth-busting), not just the topic."))
    return out
