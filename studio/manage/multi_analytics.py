"""Analytics across several channels: one page per channel, an all-channels overview and a comparison.

Each channel signs in on its own (its own token file), so every channel is queried with its own account.
Channels that are not signed in show "not signed in", or labelled sample data when `demo=True`.
Sample data is deterministic, never mixed with live numbers, and always marked `source == "demo"`.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channels
from studio.util.logging import get_logger
from studio.youtube import auth

log = get_logger("multi_analytics")

# (data service wrapper, analytics service wrapper) for a channel id, or None when not signed in.
Services = Callable[[str], tuple[Any, Any] | None]


def date_range(days: int = 28, start: date | None = None, end: date | None = None,
               today: date | None = None) -> tuple[date, date]:
    """Resolve a date filter. Give `days` (ending yesterday) or an explicit start and end."""
    if start or end:
        end = end or (today or date.today()) - timedelta(days=1)
        start = start or end - timedelta(days=days - 1)
    else:
        end = (today or date.today()) - timedelta(days=1)
        start = end - timedelta(days=days - 1)
    if start > end:
        raise StudioError(f"The start date {start} is after the end date {end}.",
                          "A date range must run forward in time.", "Swap the two dates.")
    return start, end


def _previous(start: date, end: date) -> tuple[date, date]:
    n = (end - start).days + 1
    return start - timedelta(days=n), start - timedelta(days=1)


def _totals(row: dict) -> dict:
    """Normalise one Analytics totals row into the shape the views use."""
    gained, lost = int(row.get("subscribersGained", 0) or 0), int(row.get("subscribersLost", 0) or 0)
    return {"views": int(row.get("views", 0) or 0),
            "watch_hours": round(float(row.get("estimatedMinutesWatched", 0) or 0) / 60, 1),
            "subs_gained": gained, "subs_lost": lost, "net_subs": gained - lost,
            "avg_view_duration": round(float(row.get("averageViewDuration", 0) or 0), 1),
            "avg_view_pct": round(float(row.get("averageViewPercentage", 0) or 0), 1)}


def _empty(channel: dict, start: date, end: date, source: str, message: str = "") -> dict:
    return {"channel_id": channel["id"], "name": channel["name"], "type": channel["type"], "source": source,
            "message": message, "start": start.isoformat(), "end": end.isoformat(),
            "totals": _totals({}), "previous": _totals({}), "subscribers_total": None, "daily": [],
            "top_videos": [], "hint": channels.channel_types.info(channel["type"])["analytics_hint"]}


def demo_data(channel: dict, start: date, end: date) -> dict:
    """Deterministic sample numbers for a channel (so screens and tests work without YouTube)."""
    seed = int(hashlib.sha256(channel["id"].encode()).hexdigest()[:8], 16)
    scale = 200 + seed % 1800  # channels differ by size
    rng = random.Random(seed)
    kids = channel["type"] == "kids"
    daily = []
    for i in range((end - start).days + 1):
        views = int(scale * (1 + 0.3 * rng.random()) * (3 if kids else 1))
        daily.append({"day": (start + timedelta(days=i)).isoformat(), "views": views,
                      "estimatedMinutesWatched": views * (1.1 if kids else 3.4),
                      "subscribersGained": int(views * 0.01), "subscribersLost": int(views * 0.002)})
    top = [{"video": f"demo{n}", "views": int(scale * 9 / n), "estimatedMinutesWatched": scale * 20 / n,
            "averageViewPercentage": round(55 - 4 * n + rng.random() * 3, 1)} for n in range(1, 6)]
    return {"daily": daily, "top": top, "titles": {t["video"]: f"Sample video {i}" for i, t in enumerate(top, 1)},
            "subs_total": scale * 40}


def _assemble(channel: dict, start: date, end: date, source: str, raw: dict, prev_row: dict) -> dict:
    out = _empty(channel, start, end, source)
    daily = raw["daily"]
    views = sum(int(d["views"]) for d in daily)
    minutes = sum(float(d["estimatedMinutesWatched"]) for d in daily)
    total_row = raw.get("totals") or {
        "views": views, "estimatedMinutesWatched": minutes,
        "averageViewDuration": minutes * 60 / views if views else 0,
        "averageViewPercentage": (sum(t["averageViewPercentage"] * t["views"] for t in raw["top"])
                                  / max(1, sum(t["views"] for t in raw["top"]))) if raw["top"] else 0,
        "subscribersGained": sum(int(d["subscribersGained"]) for d in daily),
        "subscribersLost": sum(int(d["subscribersLost"]) for d in daily)}
    out["totals"] = _totals(total_row)
    out["previous"] = _totals(prev_row)
    out["subscribers_total"] = raw.get("subs_total")
    out["daily"] = [{"day": d["day"], "views": int(d["views"]),
                     "watch_hours": round(float(d["estimatedMinutesWatched"]) / 60, 2),
                     "net_subs": int(d["subscribersGained"]) - int(d["subscribersLost"])} for d in daily]
    out["top_videos"] = [{"video_id": t["video"], "title": raw["titles"].get(t["video"], t["video"]),
                          "views": int(t["views"]), "watch_hours": round(float(t["estimatedMinutesWatched"]) / 60, 1),
                          "retention_pct": round(float(t["averageViewPercentage"]), 1)} for t in raw["top"]]
    return out


def default_services(settings: Settings) -> Services:
    """Live clients per channel, using each channel's own saved token. Never opens a browser."""
    from studio.context import build_ctx

    def make(channel_id: str):
        s = auth.settings_for(settings, channel_id)
        creds = auth.load_credentials(s)
        if creds is None:
            return None
        ctx = build_ctx(settings.root)
        ctx.settings = s
        ctx.youtube_factory = lambda: auth.build_services(s, creds)
        return ctx.youtube("analytics")

    return make


def channel_report(root: Path, channel_id: str, start: date, end: date, services: Services,
                   demo: bool = False) -> dict:
    """Analytics for one channel and date range. Live if signed in, else sample data (demo) or an empty note."""
    ch = {"id": channel_id, **channels.get(root, channel_id)}
    try:
        pair = services(channel_id)
    except StudioError as exc:
        return _empty(ch, start, end, "error", str(exc))
    if pair is None:
        if demo:
            raw = demo_data(ch, start, end)
            p0, p1 = _previous(start, end)
            prev = demo_data(ch, p0, p1)
            prev_row = {"views": sum(d["views"] for d in prev["daily"]),
                        "estimatedMinutesWatched": sum(d["estimatedMinutesWatched"] for d in prev["daily"]),
                        "subscribersGained": sum(d["subscribersGained"] for d in prev["daily"]),
                        "subscribersLost": sum(d["subscribersLost"] for d in prev["daily"])}
            return _assemble(ch, start, end, "demo", raw, prev_row)
        return _empty(ch, start, end, "not_signed_in",
                      f"Not signed in. Run `channels sign-in {channel_id}` (or press Sign in on the Channels page).")
    data, ya = pair
    try:
        p0, p1 = _previous(start, end)
        top = ya.top_videos(start, end)
        titles = {v["id"]: v["snippet"]["title"] for v in data.videos([t["video"] for t in top], part="snippet")}
        raw = {"daily": ya.channel_daily(start, end), "totals": ya.channel_totals(start, end), "top": top,
               "titles": titles,
               "subs_total": int(data.my_channel().get("statistics", {}).get("subscriberCount", 0) or 0)}
        prev_row = ya.channel_totals(p0, p1)
    except StudioError:
        raise
    except Exception as exc:  # noqa: BLE001 - one broken channel must not hide the others
        log.warning("Analytics for %s failed: %s", channel_id, exc)
        return _empty(ch, start, end, "error",
                      f"YouTube did not return analytics ({exc}). Check the sign-in and try again.")
    return _assemble(ch, start, end, "live", raw, prev_row)


def overview(root: Path, start: date, end: date, services: Services, demo: bool = False,
             only: list[str] | None = None) -> list[dict]:
    """A report per channel (all of them, or just `only`)."""
    ids = only or [c["id"] for c in channels.list_channels(root)]
    return [channel_report(root, cid, start, end, services, demo) for cid in ids]


def comparison_rows(reports: list[dict]) -> list[dict]:
    """Flat rows for a side-by-side table, with change versus the previous period of equal length."""
    def change(now: float, before: float) -> float | None:
        return round((now - before) / before * 100, 1) if before else None

    rows = []
    for r in reports:
        t, p = r["totals"], r["previous"]
        rows.append({"channel": r["name"], "type": r["type"], "source": r["source"], "views": t["views"],
                     "views_change_pct": change(t["views"], p["views"]), "watch_hours": t["watch_hours"],
                     "watch_change_pct": change(t["watch_hours"], p["watch_hours"]), "net_subs": t["net_subs"],
                     "subscribers": r["subscribers_total"], "avg_view_duration": t["avg_view_duration"],
                     "retention_pct": t["avg_view_pct"],
                     "top_video": r["top_videos"][0]["title"] if r["top_videos"] else ""})
    return rows


def format_text(report: dict) -> str:
    """Plain-text page for one channel (CLI)."""
    t, p = report["totals"], report["previous"]
    lines = [f"{report['name']} [{report['type']}]  {report['start']} to {report['end']}  "
             f"({'SAMPLE DATA' if report['source'] == 'demo' else report['source']})"]
    if report["message"]:
        lines.append(f"  {report['message']}")
        return "\n".join(lines)
    lines += [f"  Views: {t['views']:,} (before: {p['views']:,})",
              f"  Watch hours: {t['watch_hours']:,} (before: {p['watch_hours']:,})",
              f"  Subscribers: {t['net_subs']:+,} net"
              + (f", {report['subscribers_total']:,} total" if report["subscribers_total"] else ""),
              f"  Retention: average view {t['avg_view_duration']:.0f}s, {t['avg_view_pct']}% of each video watched",
              f"  Tip: {report['hint']}", "  Top videos:"]
    lines += [f"    {i}. {v['title']}: {v['views']:,} views, {v['watch_hours']} h, {v['retention_pct']}% retained"
              for i, v in enumerate(report["top_videos"], 1)] or ["    (none yet)"]
    return "\n".join(lines)


def format_comparison(rows: list[dict]) -> str:
    """Aligned side-by-side table (CLI)."""
    def pct(v):
        return "n/a" if v is None else f"{v:+.0f}%"

    head = f"{'Channel':<22}{'Views':>10}{'chg':>7}{'Hours':>9}{'chg':>7}{'Net subs':>10}{'Retention':>11}  Source"
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(f"{r['channel'][:21]:<22}{r['views']:>10,}{pct(r['views_change_pct']):>7}{r['watch_hours']:>9,.0f}"
                   f"{pct(r['watch_change_pct']):>7}{r['net_subs']:>+10,}{r['retention_pct']:>10.0f}%  {r['source']}")
    return "\n".join(out)


def sign_in(settings: Settings, channel_id: str, run_flow=None, services: Callable | None = None) -> dict:
    """Sign a channel in with its own Google login and remember which YouTube channel it is.

    Runs the browser flow (`run_flow` is injectable for tests), then asks YouTube which channel the token
    works as and stores that id on the profile. Warns if it differs from an id already set.
    """
    s = auth.settings_for(settings, channel_id)
    kw = {"run_flow": run_flow} if run_flow else {}
    creds = auth.get_credentials(s, **kw)
    pair = (services or (lambda c: _live_pair(s, creds)))(channel_id)
    info = pair[0].my_channel() if pair else {}
    yt_id = info.get("id", "")
    existing = channels.get(settings.root, channel_id)["youtube_channel_id"]
    if yt_id and existing and existing != yt_id:
        raise StudioError(f"Signed in as channel {yt_id}, but this profile expects {existing}.",
                          "The Google account or channel you picked is a different one.",
                          f"Run `channels sign-in {channel_id}` again and pick the right channel, or edit the id.")
    if yt_id and not existing:
        channels.update(settings.root, channel_id, youtube_channel_id=yt_id)
    return {"channel_id": channel_id, "youtube_channel_id": yt_id,
            "title": info.get("snippet", {}).get("title", ""), "token": str(s.token_path)}


def _live_pair(settings: Settings, creds: Any):
    from studio.context import build_ctx

    ctx = build_ctx(settings.root)
    ctx.settings = settings
    ctx.youtube_factory = lambda: auth.build_services(settings, creds)
    return ctx.youtube("analytics")
