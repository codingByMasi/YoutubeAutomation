"""YouTube Data API quota tracking.

Costs verified against https://developers.google.com/youtube/v3/determine_quota_cost on 2026-10-28:
search.list and videos.insert have their own daily buckets of 100 calls each; every other
endpoint draws from the shared daily unit budget (default 10,000). Quota resets at midnight Pacific.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from studio.errors import QuotaError
from studio.models import QuotaLog

PACIFIC = ZoneInfo("America/Los_Angeles")

# endpoint -> (bucket, units). Buckets: "units" (shared), "search" and "upload" (call-count buckets).
COSTS: dict[str, tuple[str, int]] = {
    "search.list": ("search", 1),
    "videos.insert": ("upload", 1),
    "videos.list": ("units", 1),
    "videos.update": ("units", 50),
    "channels.list": ("units", 1),
    "captions.insert": ("units", 400),
    "captions.list": ("units", 50),
    "thumbnails.set": ("units", 50),
    "playlists.list": ("units", 1),
    "playlistItems.insert": ("units", 50),
    "commentThreads.list": ("units", 1),
    "comments.insert": ("units", 50),
    # YouTube Analytics API has its own quota; logged for visibility, never charged to the Data API budget.
    "analytics.reports.query": ("analytics", 0),
}
BUCKET_LIMITS_DEFAULT = {"search": 100, "upload": 100}
LOGICAL_PREFIX = {"search": "search.list", "upload": "videos.insert"}


def quota_day(now: datetime | None = None) -> date:
    """The current quota day in Pacific time."""
    return (now or datetime.now(PACIFIC)).astimezone(PACIFIC).date()


def next_reset(now: datetime | None = None) -> datetime:
    """Next midnight Pacific."""
    now = (now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    return datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), PACIFIC)


class QuotaTracker:
    """Logs every call to quota_log and refuses calls that would cross the budget."""

    def __init__(
        self,
        session: Session,
        daily_limit: int = 10000,
        safety_margin: int = 500,
        bucket_limits: dict[str, int] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.s = session
        self.daily_limit = daily_limit
        self.safety_margin = safety_margin
        self.bucket_limits = bucket_limits or dict(BUCKET_LIMITS_DEFAULT)
        self.clock = clock or (lambda: datetime.now(PACIFIC))

    def _endpoints(self, bucket: str) -> list[str]:
        return [e for e, (b, _) in COSTS.items() if b == bucket]

    def used(self, bucket: str = "units") -> int:
        """Units (or calls, for search/upload) used today in a bucket. Failed calls still count."""
        total = (
            self.s.query(func.coalesce(func.sum(QuotaLog.units), 0))
            .filter(QuotaLog.date == quota_day(self.clock()), QuotaLog.endpoint.in_(self._endpoints(bucket)))
            .scalar()
        )
        return int(total or 0)

    def budget(self, bucket: str = "units") -> int:
        """Usable budget for a bucket after the safety margin (margin only applies to shared units)."""
        if bucket == "units":
            return self.daily_limit - self.safety_margin
        return self.bucket_limits.get(bucket, 0)

    def remaining(self, bucket: str = "units") -> int:
        return max(self.budget(bucket) - self.used(bucket), 0)

    def check(self, plan: dict[str, int]) -> None:
        """Raise QuotaError if running `plan` ({endpoint: call count}) would exceed any bucket."""
        need: dict[str, int] = {}
        for endpoint, calls in plan.items():
            bucket, units = self._cost(endpoint)
            need[bucket] = need.get(bucket, 0) + units * calls
        for bucket, units in need.items():
            if bucket == "analytics":
                continue
            if units > self.remaining(bucket):
                reset = next_reset(self.clock()).strftime("%Y-%m-%d %H:%M %Z")
                label = "units" if bucket == "units" else f"{LOGICAL_PREFIX[bucket]} calls"
                raise QuotaError(
                    f"Not enough YouTube quota: need {units} {label}, {self.remaining(bucket)} left today.",
                    f"Budget is {self.budget(bucket)} {label} per day"
                    + (f" (limit {self.daily_limit} minus safety margin {self.safety_margin})."
                       if bucket == "units" else "."),
                    f"Wait for the reset at {reset}, or request a quota increase in Google Cloud Console.",
                )

    def _cost(self, endpoint: str) -> tuple[str, int]:
        if endpoint not in COSTS:
            raise KeyError(f"Unknown endpoint {endpoint!r}; add its cost to quota.COSTS from the official docs.")
        return COSTS[endpoint]

    def log(self, endpoint: str, ok: bool) -> None:
        _, units = self._cost(endpoint)
        self.s.add(QuotaLog(date=quota_day(self.clock()), endpoint=endpoint, units=units, ok=ok))
        self.s.commit()

    @contextmanager
    def spend(self, endpoint: str) -> Iterator[None]:
        """Check budget, run the block, then log the call (as failed if the block raised)."""
        self.check({endpoint: 1})
        ok = False
        try:
            yield
            ok = True
        finally:
            self.log(endpoint, ok)

    def summary(self) -> dict[str, dict[str, int]]:
        """Used / budget / remaining for each enforced bucket."""
        return {
            b: {"used": self.used(b), "budget": self.budget(b), "remaining": self.remaining(b)}
            for b in ("units", "search", "upload")
        }
