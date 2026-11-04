"""Visual mix: charts and still pictures are rare, animated cast scenes are the default.

`limit_charts` keeps at most MAX_CHARTS charts per video, never closer than MIN_CHART_GAP segments, and turns pie
charts into bar charts (bars grow on screen, pies would be a still frame). `STOCK_STILL_MAX` caps still stock
photos used as shot filler (they get a camera move in `build`, so they are never frozen).
"""

from __future__ import annotations

MAX_CHARTS = 3
MIN_CHART_GAP = 3        # segments between two charts
STOCK_STILL_MAX = 2      # stock photos per video outside script-requested photo scenes
DEFAULT_CAST_SCENE = "lectern"


def limit_charts(segs: list[dict]) -> list[str]:
    """Drop `chart_data` beyond the cap or too close to an earlier chart; return plain-language notes."""
    notes: list[str] = []
    kept: list[int] = []
    for pos, seg in enumerate(segs, 1):
        chart = seg.get("chart_data")
        if not chart:
            continue
        if len(kept) >= MAX_CHARTS or (kept and pos - kept[-1] <= MIN_CHART_GAP):
            seg["chart_data"] = None
            notes.append(f"segment {pos}: chart removed (charts are rare: at most {MAX_CHARTS} per video)")
            continue
        if chart.get("type") == "pie":
            chart["type"] = "bar"
            notes.append(f"segment {pos}: pie chart drawn as an animated bar chart")
        kept.append(pos)
    return notes


def cast_scene_for(seg: dict, valid: tuple[str, ...]) -> str | None:
    """The segment's cast scene, or the default animated one when the segment shows no chart."""
    scene = seg.get("scene")
    if isinstance(scene, str) and scene in valid:
        return scene
    return None if seg.get("chart_data") or scene else (DEFAULT_CAST_SCENE if DEFAULT_CAST_SCENE in valid else None)
