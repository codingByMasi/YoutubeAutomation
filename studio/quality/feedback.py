"""Retention feedback loop: turn per-video retention/CTR data into per-channel script and edit rules.

Data comes from YouTube Analytics (live) or, when that is unavailable, from clearly labelled mock curves so the
loop can be tried without an account. Rules learned from mock data are stored but never applied to real scripts
unless the owner passes `--apply-mock`.
"""

from __future__ import annotations

import json
import statistics
import zlib
from datetime import UTC, date, datetime, timedelta

from studio.context import Ctx
from studio.errors import StudioError
from studio.growth import channels
from studio.models import Video
from studio.quality import profiles, rules
from studio.stages.script import timeline

HOOK_SECONDS = 30.0
RETENTION_TARGET = {"explainer": 0.60, "story": 0.55, "kids": 0.70}  # share still watching at 0:30
AVG_PCT_TARGET = {"explainer": 0.40, "story": 0.40, "kids": 0.55}
DROP_WINDOW = 0.10  # a drop is measured over 10% of the video
DROP_LIMIT = 0.12


def curve_at(curve: list[tuple[float, float]], ratio: float) -> float:
    """Audience watch ratio at an elapsed-time ratio (linear interpolation, clamped to the ends)."""
    pts = sorted(curve)
    if not pts:
        return 0.0
    if ratio <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= ratio <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (ratio - x0) / (x1 - x0)
    return pts[-1][1]


def mock_curve(seed: int, points: int = 21) -> list[tuple[float, float]]:
    """A deterministic, plausible retention curve (steep early loss, one mid-video dip). Not real data."""
    rnd = zlib.crc32(str(seed).encode())
    hook_loss = 0.25 + (rnd % 20) / 100        # 25-44% gone by 30s of a 10 minute video
    dip_at = 0.3 + ((rnd >> 5) % 40) / 100     # dip between 30% and 70%
    out = []
    for i in range(points):
        x = i / (points - 1)
        y = 1.0 - hook_loss * min(1.0, x / 0.05) - 0.35 * max(0.0, x - 0.05)
        if abs(x - dip_at) <= 0.05:
            y -= 0.08 * (1 - abs(x - dip_at) / 0.05)
        out.append((round(x, 3), round(max(0.02, y), 3)))
    return out


def features(rec: dict, pkg: dict | None = None) -> dict:
    """Numbers and places derived from one video's curve: hook retention, worst drop and where it fell."""
    curve = [(float(a), float(b)) for a, b in rec["curve"]]
    dur = float(rec.get("duration") or 0) or 600.0
    hook_ratio = min(1.0, HOOK_SECONDS / dur)
    avg = statistics.mean(y for _, y in curve) if curve else 0.0
    worst, at = 0.0, 0.0
    span = 1 - DROP_WINDOW - hook_ratio
    for i in range(20 if span > 0 else 0):
        a = hook_ratio + span * i / 19
        loss = curve_at(curve, a) - curve_at(curve, min(1.0, a + DROP_WINDOW))
        if loss > worst:
            worst, at = loss, a
    where = ""
    if pkg and pkg.get("segments"):
        spans = timeline(pkg["segments"])
        total = spans[-1][1] or 1
        for (start, end), seg in zip(spans, pkg["segments"]):
            if start / total <= at + DROP_WINDOW / 2 <= end / total:
                where = (seg.get("chapter") or "").strip()
                break
    return {"video_id": rec.get("video_id"), "hook_retention": round(curve_at(curve, hook_ratio), 3),
            "avg_view_pct": round(avg, 3), "worst_drop": round(worst, 3), "worst_drop_at": round(at, 3),
            "worst_drop_where": where, "end_retention": round(curve_at(curve, 0.9), 3),
            "ctr": rec.get("ctr"), "duration": dur, "source": rec.get("source", "youtube")}


def derive(feats: list[dict], ctype: str, source: str) -> dict:
    """Aggregate per-video features into tuning, edit rules and lessons for a channel type."""
    base = profiles.thresholds(ctype)
    n = len(feats)
    med = lambda k: statistics.median(f[k] for f in feats)  # noqa: E731
    tuning: dict = {}
    edit: dict = {}
    lessons: list[dict] = []
    conf = "low" if n < 2 else "medium" if n < 4 else "high"
    if n == 0:
        return {"tuning": tuning, "edit": edit, "lessons": lessons}
    target = RETENTION_TARGET[ctype]
    w30 = med("hook_retention")
    if w30 < target:
        cut = 6 if w30 < target - 0.1 else 3
        tuning["hook_max_seconds"] = max(8, base["hook_max_seconds"] - cut)
        edit["hook_shot_max_seconds"] = 2.5
        lessons.append({"area": "hook", "confidence": conf, "text": (
            f"Only {w30 * 100:.0f}% of viewers are still watching at 0:30 (target {target * 100:.0f}%). Keep the hook "
            f"to {tuning['hook_max_seconds']:g} seconds, put the surprising number or contradiction in the first "
            "sentence, state the payoff immediately and skip all setup.")})
    drop = med("worst_drop")
    if drop >= DROP_LIMIT:
        tuning["beat_gap_max"] = max(20, base["beat_gap_max"] - 10)
        edit["shot_max_seconds"] = 4.0
        spot = [f["worst_drop_where"] for f in feats if f["worst_drop_where"]]
        place = f" (most often around: {', '.join(sorted(set(spot))[:3])})" if spot else ""
        lessons.append({"area": "pacing", "confidence": conf, "text": (
            f"Audience loses about {drop * 100:.0f} points in one tenth of the video mid-way{place}. Add a retention "
            f"beat or chart at least every {tuning['beat_gap_max']:g}s, change the picture every 4s and avoid two "
            "flat explanation segments in a row.")})
    avg_target = AVG_PCT_TARGET[ctype]
    if med("avg_view_pct") < avg_target - 0.1:
        tuning["sentence_max_words"] = max(10, base["sentence_max_words"] - 3)
        lessons.append({"area": "script", "confidence": conf, "text": (
            f"Average viewed is {med('avg_view_pct') * 100:.0f}% (target {avg_target * 100:.0f}%). Use shorter, "
            f"plainer "
            f"sentences (under {tuning['sentence_max_words']:g} words) and cut any section that repeats a point.")})
    if med("end_retention") < 0.15:
        lessons.append({"area": "ending", "confidence": conf, "text": (
            "Few viewers reach the end. Pay off the hook earlier, keep the final section under 45 seconds and put "
            "the call to action right after the payoff.")})
    ctrs = [f["ctr"] for f in feats if f.get("ctr") is not None]
    if ctrs:
        ctr = statistics.median(ctrs)
        if ctr < 0.03:
            lessons.append({"area": "packaging", "confidence": conf, "text": (
                f"CTR is low ({ctr * 100:.1f}%). Use a title with one concrete number under 55 characters and a "
                "thumbnail of 1-3 words; change one element at a time.")})
        elif ctr >= 0.06 and w30 < target:
            lessons.append({"area": "packaging", "confidence": conf, "text": (
                f"CTR is strong ({ctr * 100:.1f}%) but the hook loses viewers: make sure the first 15 seconds "
                "delivers exactly what the title and thumbnail promise.")})
    if not lessons:
        lessons.append({"area": "keep", "confidence": conf, "text": (
            "Retention is on target. Keep the current hook length, beat spacing and visual pace.")})
    return {"tuning": tuning, "edit": edit, "lessons": lessons}


def fetch_live(ctx: Ctx, analytics, days: int = 28, today: date | None = None) -> list[dict]:
    """Retention records for the channel's published videos via a YouTubeAnalytics-like object."""
    from studio import scope
    end = (today or date.today()) - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    recs = []
    for v in scope.videos(ctx.session).filter(Video.youtube_video_id.isnot(None)).all():
        curve = analytics.retention(v.youtube_video_id, start, end)
        if len(curve) < 3:
            continue
        daily = analytics.daily(v.youtube_video_id, start, end)
        ctrs = [float(r["ctr"]) for r in analytics.thumbnail_daily(v.youtube_video_id, start, end) if r.get("ctr")]
        recs.append({"video_id": v.id, "duration": _duration(ctx, v.id), "curve": curve,
                     "ctr": statistics.mean(ctrs) if ctrs else None, "days": len(daily), "source": "youtube"})
    return recs


def mock_records(ctx: Ctx) -> list[dict]:
    """Mock records for the channel's built videos (or one sample if none exist). Always source='mock'."""
    from studio import scope
    vids = scope.videos(ctx.session).all()
    seeds = [(v.id, _duration(ctx, v.id)) for v in vids] or [(0, 600.0)]
    return [{"video_id": vid, "duration": dur or 600.0, "curve": mock_curve(vid), "ctr": 0.025 + (vid % 4) * 0.01,
             "source": "mock"} for vid, dur in seeds]


def _package(ctx: Ctx, video_id: int) -> dict | None:
    path = ctx.settings.project_dir(video_id) / "script.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _duration(ctx: Ctx, video_id: int) -> float:
    pkg = _package(ctx, video_id) or {}
    return float((pkg.get("build") or {}).get("duration") or 0)


def learn(ctx: Ctx, records: list[dict], apply_mock: bool = False, now: datetime | None = None) -> dict:
    """Derive and store this channel's rules from records. Returns the stored rules."""
    if not records:
        raise StudioError("No retention data to learn from.",
                          "The channel has no published video with a retention curve yet.",
                          "Publish a video and wait a few days, or try `feedback learn --mock`.")
    root = ctx.settings.root
    ctype = profiles.channel_type(channels.get(root))
    source = "mock" if any(r.get("source") == "mock" for r in records) else "youtube"
    feats = [features(r, _package(ctx, r["video_id"]) if r.get("video_id") else None) for r in records]
    data = {"source": source, "videos": len(records), "channel_type": ctype,
            "updated": (now or datetime.now(UTC)).isoformat(timespec="seconds"), "evidence": feats,
            "applied_mock": bool(apply_mock and source == "mock"), **derive(feats, ctype, source)}
    rules.save(root, data)
    return data


def run(ctx: Ctx, mode: str = "auto", apply_mock: bool = False, days: int = 28, analytics=None, echo=print) -> dict:
    """`feedback learn`: live data when possible, mock when not (mode auto), or only one of them."""
    records: list[dict] = []
    if mode in ("auto", "live"):
        try:
            ya = analytics
            if ya is None:
                ctx.settings.require("analytics")
                _, ya = ctx.youtube("analytics")
            records = fetch_live(ctx, ya, days)
        except StudioError as exc:
            if mode == "live":
                raise
            echo(f"Live analytics unavailable ({exc.what}): using mock data.")
    if not records and mode in ("auto", "mock"):
        records = mock_records(ctx)
        echo("Using MOCK retention curves: the rules below are advisory and are not applied to scripts"
             + (" (you passed --apply-mock, so they are)." if apply_mock else " unless you pass --apply-mock."))
    data = learn(ctx, records, apply_mock=apply_mock)
    echo(f"Learned from {data['videos']} video(s), source: {data['source']}, channel type: {data['channel_type']}.")
    for x in data["lessons"]:
        echo(f"  - [{x['area']}, {x['confidence']} confidence] {x['text']}")
    if data["tuning"]:
        echo("Gate thresholds now: " + ", ".join(f"{k}={v:g}" for k, v in data["tuning"].items()))
    return data
