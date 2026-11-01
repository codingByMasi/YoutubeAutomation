"""`analytics`: pull per-video metrics into metrics_daily and write a plain-English report."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import typer

from studio import scope
from studio.context import Ctx
from studio.models import Idea, MetricDaily, Title, Video
from studio.stages.review import mmss

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def store_metrics(ctx: Ctx, yt_id: str, daily: list[dict], thumbs: list[dict], traffic: list[dict]) -> int:
    """Replace stored rows for the dates returned; return the number of days stored."""
    s = ctx.session
    by_day = {r["day"]: r for r in thumbs}
    traffic_by_day: dict[str, dict[str, int]] = defaultdict(dict)
    for r in traffic:
        traffic_by_day[r["day"]][r["insightTrafficSourceType"]] = int(r["views"])
    for r in daily:
        d = date.fromisoformat(r["day"])
        s.query(MetricDaily).filter_by(youtube_video_id=yt_id, date=d).delete()
        t = by_day.get(r["day"], {})
        s.add(MetricDaily(youtube_video_id=yt_id, date=d, views=int(r.get("views", 0)),
                          watch_minutes=float(r.get("estimatedMinutesWatched", 0)),
                          avg_view_duration=float(r.get("averageViewDuration", 0)),
                          impressions=int(t["videoThumbnailImpressions"]) if "videoThumbnailImpressions" in t else None,
                          ctr=float(t["videoThumbnailImpressionsClickRate"])
                          if "videoThumbnailImpressionsClickRate" in t else None,
                          traffic_json=json.dumps(traffic_by_day.get(r["day"], {}))))
    s.commit()
    return len(daily)


def biggest_drop(curve: list[tuple[float, float]], duration: float) -> tuple[float, float] | None:
    """(seconds into the video, share of audience lost) at the steepest retention drop, skipping the first 3%."""
    pts = [(x, y) for x, y in sorted(curve) if x >= 0.03]
    if len(pts) < 2:
        return None
    drops = [(pts[i][1] - pts[i + 1][1], pts[i + 1][0]) for i in range(len(pts) - 1)]
    loss, at = max(drops)
    return (at * duration, loss) if loss > 0 else None


def _length_bucket(minutes: float) -> str:
    return "<8 min" if minutes < 8 else "8-12 min" if minutes < 12 else "12-15 min" if minutes <= 15 else "15+ min"


def _avg_table(rows: list[dict], key: str) -> list[tuple[str, float, int]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r["views_per_day"])
    return sorted(((k, statistics.mean(v), len(v)) for k, v in groups.items()), key=lambda x: -x[1])


def build_report(rows: list[dict], next_ideas: list[str], days: int) -> str:
    """Plain-English markdown report from per-video summaries.

    Each row: title, topic, style, length_min, weekday, views, watch_minutes, avg_view_duration,
    views_per_day, ctr (or None), drop (seconds, loss) or None, drop_chapter.
    """
    lines = [f"# Channel report: last {days} days", ""]
    if not rows:
        return "\n".join(lines + ["No published videos with data yet. Publish a video and check back in a few days."])
    tv, tw = sum(r["views"] for r in rows), sum(r["watch_minutes"] for r in rows)
    lines += [f"{len(rows)} videos earned {tv:,} views and {tw / 60:,.0f} watch hours.", ""]
    if len(rows) < 3:
        lines += ["_With fewer than 3 videos these patterns are early signals, not conclusions._", ""]
    best = sorted(rows, key=lambda r: -r["views_per_day"])
    lines += ["## Best topics", ""]
    lines += [f"- **{r['title']}**: {r['views_per_day']:.0f} views/day, average view "
              f"{mmss(r['avg_view_duration'])}" + (f", CTR {r['ctr']:.1f}%" if r.get("ctr") is not None else "")
              for r in best[:3]]
    for label, key in (("Title styles", "style"), ("Video lengths", "length_bucket"), ("Upload days", "weekday")):
        table = _avg_table(rows, key)
        lines += ["", f"## {label}", ""]
        lines += [f"- {k or 'unlabelled'}: {v:.0f} views/day across {n} video{'s' if n > 1 else ''}"
                  for k, v, n in table]
        if len(table) > 1:
            lines.append(f"\nBest so far: **{table[0][0]}**.")
    lines += ["", "## Where viewers leave", ""]
    drops = [r for r in rows if r.get("drop")]
    if not drops:
        lines.append("No retention data yet (YouTube needs more views before it reports retention).")
    for r in drops:
        sec, loss = r["drop"]
        lines.append(f"- {r['title']}: biggest drop at {mmss(sec)}"
                     + (f" ({r['drop_chapter']})" if r.get("drop_chapter") else "")
                     + f", losing {loss * 100:.0f}% of viewers. Tighten that section or add a reveal before it.")
    ctrs = [r["ctr"] for r in rows if r.get("ctr") is not None]
    lines += ["", "## What to make next", ""]
    top_style = _avg_table(rows, "style")[0][0]
    lines.append(f"- Lead with the **{top_style}** title style; it has the most views per day.")
    lines.append(f"- Make more on topics like **{best[0]['topic']}**.")
    if ctrs and statistics.mean(ctrs) < 4:
        lines.append(f"- Average CTR is {statistics.mean(ctrs):.1f}%: test new thumbnails with `ab-log`.")
    if not ctrs:
        lines.append("- Impressions and CTR are not available through the Analytics API for this channel; "
                     "check them in YouTube Studio > Analytics > Reach.")
    if next_ideas:
        lines.append("- Approved ideas waiting: " + "; ".join(next_ideas[:5]))
    else:
        lines.append("- No approved ideas waiting: run `research` on 2-3 seeds.")
    return "\n".join(lines) + "\n"


def _chapter_at(review_path: Path, seconds: float) -> str:
    if not review_path.exists():
        return ""
    name = ""
    for t, n in json.loads(review_path.read_text()).get("chapters", []):
        if t <= seconds:
            name = n
    return name


def run(ctx: Ctx, days: int = 28, today: date | None = None) -> Path:
    ctx.settings.require("analytics")
    s = ctx.session
    end = (today or date.today()) - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    vids = scope.videos(s).filter(Video.youtube_video_id.isnot(None)).all()
    _, ya = ctx.youtube("analytics") if vids else (None, None)
    rows = []
    for v in vids:
        yt = v.youtube_video_id
        daily = ya.daily(yt, start, end)
        thumbs = ya.thumbnail_daily(yt, start, end)
        traffic = ya.traffic_daily(yt, start, end)
        store_metrics(ctx, yt, daily, thumbs, traffic)
        curve = ya.retention(yt, start, end)
        pkg_path = ctx.settings.project_dir(v.id) / "script.json"
        pkg = json.loads(pkg_path.read_text()) if pkg_path.exists() else {}
        duration = float(pkg.get("build", {}).get("duration") or 0)
        title = s.query(Title).filter_by(video_id=v.id, is_live=True).first() or \
            s.query(Title).filter_by(video_id=v.id, is_pick=True).first()
        mets = s.query(MetricDaily).filter(MetricDaily.youtube_video_id == yt, MetricDaily.date >= start).all()
        views = sum(m.views for m in mets)
        live_days = max(1, (end - max(start, (v.publish_at or v.created_at).date())).days + 1)
        ctr_vals = [m.ctr for m in mets if m.ctr is not None]
        drop = biggest_drop(curve, duration) if duration else None
        rows.append({
            "title": title.text if title else f"video {v.id}", "style": title.style if title else "",
            "topic": s.get(Idea, v.idea_id).topic, "length_min": duration / 60,
            "length_bucket": _length_bucket(duration / 60),
            "weekday": WEEKDAYS[(v.publish_at or v.created_at).weekday()], "views": views,
            "watch_minutes": sum(m.watch_minutes for m in mets),
            "avg_view_duration": statistics.mean([m.avg_view_duration for m in mets]) if mets else 0,
            "views_per_day": views / live_days, "ctr": statistics.mean(ctr_vals) if ctr_vals else None,
            "drop": drop, "drop_chapter": _chapter_at(ctx.settings.project_dir(v.id) / "review.json", drop[0])
            if drop else "",
        })
    waiting = [i.topic for i in scope.ideas(s).filter_by(status="approved").all()
               if not s.query(Video).filter(Video.idea_id == i.id, Video.youtube_video_id.isnot(None)).first()]
    report = build_report(rows, waiting, days)
    tag = "" if scope.channel_of(s) == "default" else f"_{scope.channel_of(s)}"
    out = ctx.settings.root / "reports" / f"analytics{tag}_{(today or date.today()).isoformat()}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    typer.echo(report)
    typer.echo(f"Saved to {out}")
    return out


def period_summary(ctx: Ctx, yt_id: str, start: datetime, end: datetime) -> dict:
    """Views/day, CTR and average view duration between two times (used by ab-log)."""
    mets = ctx.session.query(MetricDaily).filter(MetricDaily.youtube_video_id == yt_id,
                                                 MetricDaily.date >= start.date(), MetricDaily.date < end.date()).all()
    if not mets:
        return {}
    ctrs = [m.ctr for m in mets if m.ctr is not None]
    return {"days": len(mets), "views_per_day": round(sum(m.views for m in mets) / len(mets), 1),
            "avg_view_duration": round(statistics.mean(m.avg_view_duration for m in mets), 1),
            "ctr": round(statistics.mean(ctrs), 2) if ctrs else None}
