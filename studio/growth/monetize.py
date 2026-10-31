"""Partner Program progress tracker and monetization checklist.

Thresholds are from YouTube Help "YouTube Partner Program overview & eligibility" (checked 2026-10-31):
1,000 subscribers plus either 4,000 public long-form watch hours in the last 12 months or 10 million
public Shorts views in the last 90 days. Re-check before relying on them; YouTube changes the rules.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from studio.growth import store

SUBS_GOAL, HOURS_GOAL, SHORTS_VIEWS_GOAL = 1000, 4000.0, 10_000_000
NAME = "monetization"
CHECKLIST = [
    ("verification", "Turn on 2-Step Verification on the Google account"),
    ("strikes", "No active Community Guidelines strikes"),
    ("features", "Enable advanced features in YouTube Studio (phone verification)"),
    ("policies", "Read the YouTube monetization policies; reused/mass-produced content is the main risk, "
                 "so keep real analysis and your own voice-over script in every video"),
    ("adsense", "Create or link an AdSense account in YouTube Studio once eligible"),
    ("disclosure", "Mark synthetic or altered content honestly when YouTube asks"),
    ("affiliate", "Affiliate: join 1-2 programs that fit the niche (brokerage, books, tools) and disclose in the "
                  "description and pinned comment"),
    ("affiliate_rules", "Affiliate: only recommend what you would use; never promise returns"),
    ("newsletter", "Newsletter: create a free signup page (Substack/Beehiiv/Buttondown) and link it in every "
                   "description"),
    ("lead_magnet", "Newsletter: offer a small free one-page cheat sheet per series"),
    ("pinned", "Pin a comment with the newsletter and playlist link on every video"),
    ("sponsor", "Later (~5k subs): write a one-page media kit for sponsorships"),
]


def load(root: Path) -> dict:
    return store.load(store.channel_file(root, NAME), {"history": [], "checked": []})


def log_progress(root: Path, subs: int, watch_hours: float, shorts_views_90d: int = 0, on: date | None = None) -> dict:
    """Record today's numbers (one entry per day, replaced if re-entered)."""
    d = load(root)
    day = (on or date.today()).isoformat()
    d["history"] = [h for h in d["history"] if h["date"] != day] + [
        {"date": day, "subs": int(subs), "hours": float(watch_hours), "shorts_views": int(shorts_views_90d)}]
    d["history"].sort(key=lambda h: h["date"])
    store.save(store.channel_file(root, NAME), d)
    return d


def toggle(root: Path, item: str, value: bool) -> None:
    d = load(root)
    ticked = set(d["checked"])
    (ticked.add if value else ticked.discard)(item)
    d["checked"] = sorted(ticked)
    store.save(store.channel_file(root, NAME), d)


def _eta(history: list[dict], key: str, goal: float, today: date) -> date | None:
    """Linear projection from the first to the last entry; None without enough data or growth."""
    if len(history) < 2:
        return None
    a, b = history[0], history[-1]
    days = (date.fromisoformat(b["date"]) - date.fromisoformat(a["date"])).days
    rate = (b[key] - a[key]) / days if days > 0 else 0
    if b[key] >= goal:
        return today
    return today + timedelta(days=int((goal - b[key]) / rate) + 1) if rate > 0 else None


def progress(root: Path, today: date | None = None) -> dict:
    """Percent to each goal, projected dates, and whether the main path is met."""
    today = today or date.today()
    d = load(root)
    last = d["history"][-1] if d["history"] else {"subs": 0, "hours": 0.0, "shorts_views": 0}
    subs_pct = min(100.0, last["subs"] / SUBS_GOAL * 100)
    hours_pct = min(100.0, last["hours"] / HOURS_GOAL * 100)
    eta_subs, eta_hours = _eta(d["history"], "subs", SUBS_GOAL, today), _eta(d["history"], "hours", HOURS_GOAL, today)
    both = [e for e in (eta_subs, eta_hours) if e]
    return {"subs": last["subs"], "hours": last["hours"], "subs_pct": subs_pct, "hours_pct": hours_pct,
            "shorts_pct": min(100.0, last["shorts_views"] / SHORTS_VIEWS_GOAL * 100),
            "eta_subs": eta_subs, "eta_hours": eta_hours,
            "eta": max(both) if len(both) == 2 else None,
            "eligible_long_form": last["subs"] >= SUBS_GOAL and last["hours"] >= HOURS_GOAL,
            "eligible_shorts": last["subs"] >= SUBS_GOAL and last["shorts_views"] >= SHORTS_VIEWS_GOAL,
            "checked": set(d["checked"]), "history": d["history"]}
