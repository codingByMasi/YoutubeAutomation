"""Feedback loop: per-video story metrics from real analytics, summaries for the next story_plan, retention heatmap.

Stored as JSON per channel (growth/story_metrics.json): hook_type vs hook retention, drop-off beat/loop, title style
vs CTR. Mock curves are never stored here. With fewer than 3 real videos the prompt block is simply empty.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.growth import store

NAME = "story_metrics"
COMP = "competitor_titles"
MIN_REAL = 3


def _load(root: Path) -> dict:
    return store.load(store.channel_file(root, NAME), {})


def record_competitors(root: Path, titles: list[dict]) -> None:
    """Keep the top outlier titles from research (pattern references only)."""
    store.save(store.channel_file(root, COMP), titles[:8])


def competitor_text(root: Path, n: int = 5) -> str:
    items = store.load(store.channel_file(root, COMP), [])[:n]
    if not items:
        return "(none yet: run `research` to collect outlier titles)"
    return "\n".join(f"- \"{i['title']}\" ({i['views']:,} views on a {i['subs']:,}-subscriber channel)" for i in items)


def beat_at(pkg: dict, at_ratio: float) -> dict:
    """The segment (chapter, beat, loops) at a fraction of the video, for the heatmap and drop-off stats."""
    from studio.story.loops import starts
    segs = pkg.get("segments") or []
    if not segs:
        return {}
    st = starts(segs)
    total = st[-1] + float(segs[-1].get("real_seconds") or segs[-1].get("est_seconds") or 0)
    t = at_ratio * total
    i = max(0, sum(1 for s in st if s <= t) - 1)
    seg = segs[i]
    return {"segment": i + 1, "chapter": seg.get("chapter", ""), "beat": seg.get("beat") or "explain",
            "plants_loop": seg.get("plants_loop"), "pays_loop": seg.get("pays_loop"), "seconds": round(t)}


def record_metrics(ctx, records: list[dict], feats: list[dict]) -> int:
    """Store story metrics for real (non-mock) records. Returns how many were stored."""
    from studio.models import Title
    root = ctx.settings.root
    data = _load(root)
    n = 0
    for rec, f in zip(records, feats):
        if rec.get("source") == "mock" or not rec.get("video_id"):
            continue
        vid = rec["video_id"]
        p = ctx.settings.project_dir(vid) / "script.json"
        pkg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        title = ctx.session.query(Title).filter_by(video_id=vid, is_pick=True).first()
        data[str(vid)] = {
            "video_id": vid, "hook_type": pkg.get("hook_type", ""), "hook_line": (pkg.get("segments") or [{}])[0]
            .get("narration", "")[:90], "arc": pkg.get("arc", ""), "hook_retention": f["hook_retention"],
            "avg_view_pct": f["avg_view_pct"], "ctr": f.get("ctr"), "title_style": title.style if title else "",
            "drop": beat_at(pkg, f["worst_drop_at"]), "worst_drop": f["worst_drop"]}
        n += 1
    store.save(store.channel_file(root, NAME), data)
    return n


def prompt_text(root: Path) -> str:
    """Top 3 and bottom 3 videos by hook retention as short summaries; empty note if fewer than 3 real videos."""
    rows = list(_load(root).values())
    if len(rows) < MIN_REAL:
        return "(not enough real videos yet)"
    rows.sort(key=lambda r: -r["hook_retention"])
    fmt = lambda r: (f"hook_type={r['hook_type'] or '?'} \"{r['hook_line'][:60]}\" -> {r['hook_retention']:.0%} "  # noqa: E731
                     f"still watching at 0:30; biggest drop at {r['drop'].get('chapter') or '?'} "
                     f"({r['drop'].get('beat', '?')} beat); title style {r['title_style'] or '?'}")
    top, bottom = rows[:3], rows[-3:] if len(rows) >= 6 else rows[3:] or rows[-1:]
    return "Worked best:\n" + "\n".join(f"- {fmt(r)}" for r in top) + "\nWorked worst:\n" + \
        "\n".join(f"- {fmt(r)}" for r in bottom)


def heatmap_lines(root: Path) -> list[str]:
    """Retention heatmap section for the analytics report: where viewers leave, per outline beat and loop."""
    rows = list(_load(root).values())
    if not rows:
        return []
    lines = ["", "## Retention heatmap (where viewers leave)", "",
             "| Video | Drop | At | Chapter | Beat | Loop | Hook retention |", "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -r["worst_drop"]):
        d = r["drop"] or {}
        loop = d.get("plants_loop") or d.get("pays_loop") or ""
        lines.append(f"| #{r['video_id']} | -{r['worst_drop']:.0%} | {d.get('seconds', 0) // 60}:"
                     f"{d.get('seconds', 0) % 60:02d} | {d.get('chapter', '')} | {d.get('beat', '')} | {loop} | "
                     f"{r['hook_retention']:.0%} |")
    by_beat: dict[str, list[float]] = {}
    for r in rows:
        by_beat.setdefault((r["drop"] or {}).get("beat", "?"), []).append(r["worst_drop"])
    lines += ["", "Average worst drop by beat type: " + ", ".join(
        f"{b} {sum(v) / len(v):.0%} ({len(v)})" for b, v in sorted(by_beat.items(), key=lambda x: -sum(x[1]) / len(x[1])))]  # noqa: E501
    return lines
