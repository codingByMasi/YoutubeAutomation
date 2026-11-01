"""`research` and `approve-idea`: find topics, score demand vs competition, flag outliers.

Research only finds topics. Competitor titles are used for scoring, never copied into scripts.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import typer

from studio import scope
from studio.context import Ctx
from studio.errors import StudioError
from studio.models import Idea, Video, utcnow
from studio.util.logging import get_logger
from studio.util.retry import with_retry

log = get_logger("research")

SMALL_CHANNEL_SUBS = 100_000   # channels below this count as "small"
OUTLIER_RATIO = 2.0            # views per subscriber at or above this is an outlier
LOOKBACK_DAYS = 180
SUGGEST_URL = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
STOPWORDS = set(
    "a an the of to in on for and or how why what is are does do x vs with my your their its".split()
)


@dataclass
class VideoStat:
    """One competitor video, reduced to the numbers scoring needs."""

    title: str
    views: int
    subs: int

    @property
    def ratio(self) -> float:
        return outlier_ratio(self.views, self.subs)

    @property
    def is_outlier(self) -> bool:
        return is_outlier(self.views, self.subs)


def outlier_ratio(views: int, subs: int) -> float:
    """Views per subscriber. Hidden or zero subscriber counts are treated as 1."""
    return views / max(subs, 1)


def is_small_channel(subs: int) -> bool:
    return subs < SMALL_CHANNEL_SUBS


def is_outlier(views: int, subs: int) -> bool:
    """A small channel whose video got at least OUTLIER_RATIO views per subscriber."""
    return is_small_channel(subs) and outlier_ratio(views, subs) >= OUTLIER_RATIO


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1}


def matches(topic: str, title: str) -> bool:
    """True if at least half of the topic's keywords appear in the title."""
    t = tokens(topic)
    return bool(t) and len(t & tokens(title)) >= max(1, math.ceil(len(t) / 2))


def score_topic(topic: str, position: int, total: int, videos: list[VideoStat]) -> dict[str, float]:
    """Demand, competition and outlier scores on 0-10 scales for one candidate topic."""
    matched = [v for v in videos if matches(topic, v.title)]
    pool, factor = (matched, 1.0) if matched else (videos, 0.8)
    if not pool:
        return {"demand": round(10 * (1 - position / max(total, 1)), 2), "competition": 0.0, "outlier": 0.0}
    med_views = statistics.median(v.views for v in pool)
    med_subs = statistics.median(v.subs for v in pool)
    demand = min(10.0, math.log10(med_views + 1) * 1.5) * factor + 2 * (1 - position / max(total, 1))
    competition = min(10.0, math.log10(med_subs + 1) * 1.5)
    outlier = min(10.0, sum(min(v.ratio, 10.0) for v in matched if v.is_outlier) / 2)
    return {"demand": round(demand, 2), "competition": round(competition, 2), "outlier": round(outlier, 2)}


def rank(ideas: list[Idea]) -> list[Idea]:
    """Highest demand minus competition plus outlier first."""
    return sorted(ideas, key=lambda i: i.rank_score, reverse=True)


def fetch_suggestions(seed: str) -> list[str]:
    """YouTube search autocomplete for the seed and a few question forms. Empty list on failure."""
    out: list[str] = []
    for q in (seed, f"how {seed}", f"why {seed}", f"{seed} explained"):
        def get(q=q) -> list[str]:
            with urllib.request.urlopen(SUGGEST_URL + urllib.parse.quote(q), timeout=10) as r:
                return json.loads(r.read().decode("utf-8", "replace"))[1]
        try:
            out += with_retry(get, "YouTube search suggestions", attempts=3)
        except Exception as exc:  # noqa: BLE001 - suggestions are best effort
            log.warning("Search suggestions unavailable for %r: %s", q, exc)
    seen, unique = set(), []
    for s in [seed] + out:
        k = s.strip().lower()
        if k and k not in seen:
            seen.add(k)
            unique.append(s.strip())
    return unique[:25]


def fetch_competitor_stats(ctx: Ctx, seed: str) -> list[VideoStat]:
    """Top recent videos for the seed with view and subscriber counts (1 search + 2 list calls)."""
    data, _ = ctx.youtube("research")
    ctx.quota.check({"search.list": 1, "videos.list": 1, "channels.list": 1})
    after = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = data.search_videos(seed, after)
    ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
    vids = data.videos(ids, part="snippet,statistics")
    chans = {c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0) or 0)
             for c in data.channels(sorted({v["snippet"]["channelId"] for v in vids}))}
    return [VideoStat(v["snippet"]["title"], int(v.get("statistics", {}).get("viewCount", 0) or 0),
                      chans.get(v["snippet"]["channelId"], 0)) for v in vids]


def _print_ideas(ideas: list[Idea], limit: int) -> None:
    typer.echo(f"{'ID':>4}  {'RANK':>5}  {'DEMAND':>6}  {'COMP':>5}  {'OUTLIER':>7}  STATUS    TOPIC")
    for i in rank(ideas)[:limit]:
        typer.echo(f"{i.id:>4}  {i.rank_score:>5.1f}  {i.demand_score:>6.1f}  {i.competition_score:>5.1f}  "
                   f"{i.outlier_score:>7.1f}  {i.status:<8}  {i.topic}")


def run(ctx: Ctx, seed: str, force: bool = False, limit: int = 15, suggest=None, competitors=None) -> list[Idea]:
    """Research a seed, save ideas, print a ranked table. Same seed on the same day reuses results."""
    suggest = suggest or fetch_suggestions
    competitors = competitors or fetch_competitor_stats
    s = ctx.session
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = scope.ideas(s).filter(Idea.seed == seed, Idea.created_at >= today).all()
    if existing and not force:
        typer.echo(f"Using today's research for {seed!r} (use --force to fetch again).")
        _print_ideas(existing, limit)
        return rank(existing)

    topics = suggest(seed)
    videos = competitors(ctx, seed)
    if not topics:
        raise StudioError(f"No topic ideas found for {seed!r}.", "Search suggestions returned nothing.",
                          "Try a broader seed, e.g. 'how airlines make money'.")
    from studio.stages.discover import _custom_niche, clean_topics
    topics = [seed] + clean_topics([t for t in topics if t.lower() != seed.lower()], seed, known=[seed],
                                   strict=not _custom_niche(ctx))
    outliers = sorted((v for v in videos if v.is_outlier), key=lambda v: v.ratio, reverse=True)
    from studio.stages.discover import is_duplicate, key_tokens
    seen = [key_tokens(i.topic) for i in scope.ideas(s).all()]
    ideas = []
    for pos, topic in enumerate(topics):
        if is_duplicate(topic, seen):
            continue
        seen.append(key_tokens(topic))
        sc = score_topic(topic, pos, len(topics), videos)
        ideas.append(Idea(seed=seed, topic=topic, demand_score=sc["demand"],
                          competition_score=sc["competition"], outlier_score=sc["outlier"]))
    s.add_all(ideas)
    s.commit()
    typer.echo(f"Analysed {len(videos)} recent videos; {len(outliers)} small-channel outliers "
               f"(<{SMALL_CHANNEL_SUBS:,} subs, >= {OUTLIER_RATIO}x views per sub).")
    for v in outliers[:5]:
        typer.echo(f"  outlier {v.ratio:5.1f}x  {v.views:>10,} views / {v.subs:>8,} subs  (topic signal only)")
    if not ideas:
        typer.echo("All suggested topics are already in your ideas list.")
    _print_ideas(ideas, limit)
    typer.echo("Approve one with: approve-idea <ID>")
    return rank(ideas)


def approve(ctx: Ctx, idea_id: int) -> Video:
    """Mark an idea approved and create its video row (idempotent)."""
    s = ctx.session
    idea = s.get(Idea, idea_id)
    if idea is None:
        raise StudioError(f"Idea {idea_id} not found.", "", "Run `research \"<seed>\"` and use an ID from the table.")
    video = s.query(Video).filter(Video.idea_id == idea_id).first()
    if video:
        typer.echo(f"Idea {idea_id} is already approved as video {video.id} (stage '{video.stage}').")
        return video
    idea.status = "approved"
    video = Video(idea_id=idea_id, stage="approved")
    s.add(video)
    s.commit()
    typer.echo(f"Approved idea {idea_id}: {idea.topic}\nCreated video {video.id}. Next: script {idea_id}")
    return video
