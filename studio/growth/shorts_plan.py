"""Shorts plan: pick the best 3 moments of a script, with hook line, on-screen text and posting day."""

from __future__ import annotations

SHORT_MIN, SHORT_MAX = 25.0, 55.0  # clean loops; growth-playbook.md section 5
HOOK_WORDS = 12  # the first ~2 seconds must land the hook


def _score(seg: dict, i: int) -> int:
    return (3 if i == 0 else 0) + (2 if seg.get("chart_data") else 0) + (1 if seg.get("beat") else 0)


def short_hook(text: str) -> str:
    """First sentence, cut to at most HOOK_WORDS words so it can be said and read in about 2 seconds."""
    first = text.split(".")[0].split("?")[0].strip() or text.strip()
    words = first.split()
    return first if len(words) <= HOOK_WORDS else " ".join(words[:HOOK_WORDS]).rstrip(",;:") + "..."


def plan(pkg: dict, count: int = 3, long_video_title: str = "") -> list[dict]:
    """Group consecutive segments into 25-55 s windows around the highest-scoring moments."""
    segs = pkg["segments"]
    order = sorted(range(len(segs)), key=lambda i: (-_score(segs[i], i), i))
    used: set[int] = set()
    out = []
    for i in order:
        if i in used:
            continue
        window, total = [i], float(segs[i].get("est_seconds", 0))
        j = i + 1
        while total < SHORT_MIN and j < len(segs) and j not in used:
            window.append(j)
            total += float(segs[j].get("est_seconds", 0))
            j += 1
        if total < SHORT_MIN or total > SHORT_MAX:
            continue
        used.update(window)
        narration = " ".join(segs[k]["narration"] for k in window)
        first = short_hook(segs[window[0]]["narration"])
        out.append({
            "segments": window, "seconds": round(total), "hook_line": first,
            "narration": narration,
            "on_screen_text": (segs[window[0]].get("chapter") or "").upper()[:30],
            "why": "opening hook" if window[0] == 0 else "chart moment" if segs[window[0]].get("chart_data")
            else "retention beat",
            "pinned_comment": f"Full breakdown: {long_video_title or 'see the channel'}",
            "cta": "Full breakdown on the channel. Link to the full video in the pinned comment and related video.",
            "related_video": long_video_title,
            "tags": "#Shorts #business #economics",
        })
        if len(out) == count:
            break
    days = (2, 9, 16)  # stagger over ~3 weeks so the long video lands first and Shorts keep feeding it
    for n, s in enumerate(out):
        s["post_day_offset"] = days[n] if n < len(days) else days[-1] + 7 * (n - 2)
    return out
