"""YouTube Analytics API v2 queries (separate quota from the Data API; calls are still logged)."""

from __future__ import annotations

from datetime import date
from typing import Any

from studio.util.logging import get_logger
from studio.util.retry import with_retry
from studio.youtube.quota import QuotaTracker

log = get_logger("analytics_api")

CORE_METRICS = "views,estimatedMinutesWatched,averageViewDuration"
# Not listed in the Analytics API metrics reference as of 2026-10-28; requested opportunistically.
CHANNEL_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                  "subscribersGained,subscribersLost")
THUMB_METRICS = "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"


def _rows(resp: dict) -> list[dict]:
    names = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in resp.get("rows", []) or []]


class YouTubeAnalytics:
    """Per-video daily metrics, traffic sources and retention curves."""

    def __init__(self, service: Any, quota: QuotaTracker) -> None:
        self.ya = service
        self.quota = quota

    def _query(self, **kw) -> list[dict]:
        def attempt() -> dict:
            with self.quota.spend("analytics.reports.query"):
                return self.ya.reports().query(ids="channel==MINE", **kw).execute()

        return _rows(with_retry(attempt, "YouTube Analytics query"))

    def daily(self, video_id: str, start: date, end: date) -> list[dict]:
        return self._query(startDate=start.isoformat(), endDate=end.isoformat(), metrics=CORE_METRICS,
                           dimensions="day", filters=f"video=={video_id}", sort="day")

    def thumbnail_daily(self, video_id: str, start: date, end: date) -> list[dict]:
        """Impressions and CTR per day, or [] if the API does not support these metrics."""
        try:
            return self._query(startDate=start.isoformat(), endDate=end.isoformat(), metrics=THUMB_METRICS,
                               dimensions="day", filters=f"video=={video_id}", sort="day")
        except Exception as exc:  # noqa: BLE001
            log.info("Impressions/CTR not available from the Analytics API: %s", exc)
            return []

    def traffic_daily(self, video_id: str, start: date, end: date) -> list[dict]:
        """Views per day per traffic source type."""
        return self._query(startDate=start.isoformat(), endDate=end.isoformat(), metrics="views",
                           dimensions="day,insightTrafficSourceType", filters=f"video=={video_id}")

    def retention(self, video_id: str, start: date, end: date) -> list[tuple[float, float]]:
        rows = self._query(startDate=start.isoformat(), endDate=end.isoformat(), metrics="audienceWatchRatio",
                           dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}")
        return [(float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"])) for r in rows]

    # --- channel-wide reports (used by the multi-channel analytics view) ---
    def channel_totals(self, start: date, end: date) -> dict:
        """One row of whole-channel totals for the range ({} if YouTube has no data)."""
        rows = self._query(startDate=start.isoformat(), endDate=end.isoformat(), metrics=CHANNEL_METRICS)
        return rows[0] if rows else {}

    def channel_daily(self, start: date, end: date) -> list[dict]:
        """Whole-channel views, minutes and subscribers per day."""
        return self._query(startDate=start.isoformat(), endDate=end.isoformat(),
                           metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
                           dimensions="day", sort="day")

    def top_videos(self, start: date, end: date, limit: int = 10) -> list[dict]:
        """Best videos by views, each with watch minutes and average percentage viewed (retention)."""
        return self._query(startDate=start.isoformat(), endDate=end.isoformat(),
                           metrics="views,estimatedMinutesWatched,averageViewPercentage",
                           dimensions="video", sort="-views", maxResults=limit)
