"""Timing math shared by visuals, build and shorts (pure functions)."""

from __future__ import annotations

import math
from pathlib import Path

SHOT_MAX = 6.0          # seconds before the picture must change
CHART_LEAD_MAX = 5.0    # stock footage shown before a chart takes over


def split_segment(duration: float, has_chart: bool) -> tuple[float, float]:
    """(background seconds, chart seconds) for a segment."""
    if not has_chart:
        return duration, 0.0
    if duration <= SHOT_MAX:
        return 0.0, duration
    lead = min(CHART_LEAD_MAX, max(2.0, duration * 0.3))
    return lead, duration - lead


def shots_needed(bg_seconds: float, cap: int = 4) -> int:
    """How many distinct background shots keep each one at or under SHOT_MAX seconds."""
    return 0 if bg_seconds <= 0 else min(cap, max(1, math.ceil(bg_seconds / SHOT_MAX)))


def plan_segment(duration: float, backgrounds: list[Path], chart_frames: list[Path]) -> list[tuple[Path, float]]:
    """Ordered (visual, seconds) parts that exactly fill `duration`.

    Background shots come first (cycled if there are fewer files than shots), then chart frames
    share the rest equally. With no backgrounds at all, charts fill the whole segment.
    """
    bg_s, chart_s = split_segment(duration, bool(chart_frames))
    if not backgrounds:
        bg_s, chart_s = 0.0, duration
    parts: list[tuple[Path, float]] = []
    n = max(1, math.ceil(bg_s / SHOT_MAX)) if bg_s > 0 else 0
    parts += [(backgrounds[i % len(backgrounds)], bg_s / n) for i in range(n)]
    if chart_frames and chart_s > 0:
        parts += [(f, chart_s / len(chart_frames)) for f in chart_frames]
    elif not parts and backgrounds:
        parts = [(backgrounds[0], duration)]
    # absorb rounding so the parts sum exactly to duration
    if parts:
        drift = duration - sum(p[1] for p in parts)
        parts[-1] = (parts[-1][0], parts[-1][1] + drift)
    return parts


def pick_short_windows(spans: list[tuple[float, float]], segs: list[dict], count: int,
                       min_len: float = 15.0, max_len: float = 58.0) -> list[tuple[int, int]]:
    """Choose up to `count` non-overlapping runs of whole segments (first, last index) for Shorts.

    Runs are 15-58 s; they are scored by reveals, questions and charts, skipping the final CTA segment.
    """
    def score(i: int, j: int) -> float:
        sc = 0.0
        for g in segs[i:j + 1]:
            sc += {"reveal": 3, "question": 2, "example": 1.5, "pattern_break": 1}.get(g.get("beat") or "", 0)
            sc += 2 if g.get("chart_data") else 0
        return sc / (j - i + 1)

    last = len(segs) - 2 if len(segs) > 2 else len(segs) - 1
    cands = []
    for i in range(0, last + 1):
        for j in range(i, last + 1):
            length = spans[j][1] - spans[i][0]
            if length > max_len:
                break
            if length >= min_len:
                cands.append((score(i, j), length, i, j))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    chosen: list[tuple[int, int]] = []
    for _, _, i, j in cands:
        if all(j < a or i > b for a, b in chosen):
            chosen.append((i, j))
        if len(chosen) == count:
            break
    return sorted(chosen)
