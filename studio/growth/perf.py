"""Performance input: paste or upload YouTube Studio numbers, get next-script advice."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from studio.errors import StudioError
from studio.growth import store

NAME = "performance"
# CSV header keywords -> field
HEADERS = {"ctr": ("click-through", "ctr"), "impressions": ("impressions",), "views": ("views",),
           "avg_view_pct": ("average percentage viewed", "avg percentage", "average view percentage"),
           "avg_view_seconds": ("average view duration", "avg view duration"),
           "watch_hours": ("watch time (hours)", "watch hours"), "title": ("title", "video"),
           "subs": ("subscribers",)}


def _num(x: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(x))
    return float(m.group().replace(",", "")) if m else None


def _seconds(x: str) -> float | None:
    """'4:32', '0:04:32' or '272' to seconds."""
    parts = str(x).strip().split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    sec = 0.0
    for n in nums:
        sec = sec * 60 + n
    return sec


def parse_csv(text: str) -> list[dict]:
    """Rows from a YouTube Studio 'Content' export (Advanced mode). Unknown columns are ignored."""
    rows = list(csv.reader(io.StringIO(text.strip())))
    if len(rows) < 2:
        raise StudioError("The CSV has no data rows.", "Need a header line plus at least one video.",
                          "In YouTube Studio: Analytics > Advanced mode > Export > Comma-separated values.")
    cols: dict[int, str] = {}
    for i, h in enumerate(rows[0]):
        low = h.lower()
        for field, keys in HEADERS.items():
            if field not in cols.values() and any(k in low for k in keys):
                cols[i] = field
                break
    out = []
    for r in rows[1:]:
        if not r or str(r[0]).strip().lower() == "total":
            continue
        rec: dict = {}
        for i, field in cols.items():
            if i < len(r):
                rec[field] = r[i].strip() if field == "title" else (
                    _seconds(r[i]) if field == "avg_view_seconds" else _num(r[i]))
        if rec:
            out.append(rec)
    if not out:
        raise StudioError("No recognisable columns in the CSV.",
                          "Looked for impressions, click-through rate, views, average view duration/percentage.",
                          "Export from YouTube Studio Advanced mode, or use the quick form instead.")
    return out


def parse_retention(text: str) -> list[tuple[float, float]]:
    """Lines like '0:30 62%' or '30s, 62' to (seconds, percent still watching)."""
    pts = []
    for line in text.strip().splitlines():
        m = re.match(r"\s*([\d:]+)\s*s?[\s,;=-]+(\d+\.?\d*)\s*%?", line)
        if m and (sec := _seconds(m.group(1))) is not None:
            pts.append((sec, float(m.group(2))))
    return sorted(pts)


def advice(rec: dict, retention: list[tuple[float, float]] | None = None) -> list[str]:
    """Plain rules of thumb turned into next-script advice."""
    out = []
    ctr, apv = rec.get("ctr"), rec.get("avg_view_pct")
    if ctr is not None:
        if ctr < 2:
            out.append(f"CTR {ctr:g}% is low (<2%). Next video: test a sharper title with a concrete number and a "
                       "simpler thumbnail (1-3 words, one focal element). Change one thing at a time.")
        elif ctr < 5:
            out.append(f"CTR {ctr:g}% is average. A stronger curiosity gap in the title could lift it.")
        else:
            out.append(f"CTR {ctr:g}% is strong. Reuse this packaging style for the next video.")
    if apv is not None:
        if apv < 30:
            out.append(f"Average viewed {apv:g}% is low (<30%). Tighten the script: open with the payoff in the "
                       "first 10 seconds, cut setup, add a retention beat every 30-45 seconds.")
        elif apv < 45:
            out.append(f"Average viewed {apv:g}% is OK. Look at where the curve drops and add a chart or twist there.")
        else:
            out.append(f"Average viewed {apv:g}% is good. Keep the structure; consider a slightly longer video.")
    if retention:
        early = next((p for s, p in retention if s >= 30), None)
        if early is not None and early < 60:
            out.append(f"Only {early:g}% are still watching at 0:30: the hook is losing people. Next script: state "
                       "the surprising result in the first sentence, then promise how you will show it.")
        drops = [(b[0], a[1] - b[1]) for a, b in zip(retention, retention[1:]) if a[1] - b[1] >= 10]
        for sec, d in drops[:2]:
            out.append(f"Drop of {d:g} points before {int(sec // 60)}:{int(sec % 60):02d}: review what happens "
                       "there and shorten or add a visual change.")
    if rec.get("impressions") is not None and rec["impressions"] < 500:
        out.append("Under 500 impressions: too little data to judge packaging. Wait for more, and post Shorts "
                   "that point to this video.")
    return out or ["Not enough numbers to advise. Enter CTR and average percentage viewed at least."]


def prompt(rec: dict, retention: list[tuple[float, float]], topic: str, profile_summary: str) -> str:
    """Copy-paste prompt asking Claude for specific next-script changes."""
    curve = "\n".join(f"- {int(s // 60)}:{int(s % 60):02d} -> {p:g}% still watching"
                      for s, p in retention) or "- (none)"
    return (f"You are a YouTube retention coach. {profile_summary}\n\nVideo: {topic}\nStudio numbers: "
            f"{ {k: v for k, v in rec.items() if k != 'title'} }\nRetention curve:\n{curve}\n\n"
            "Give specific changes for the NEXT script (hook, pacing, visuals, title/thumbnail test). Be concrete "
            'and short. Reply with ONLY this JSON:\n{"diagnosis": "...", "next_script_changes": ["..."], '
            '"packaging_tests": ["..."]}')


def load(root: Path) -> list[dict]:
    return store.load(store.channel_file(root, NAME), {"records": []})["records"]


def add(root: Path, rec: dict, retention: list[tuple[float, float]], video_id: int | None, note: str = "") -> dict:
    """Store a record with its generated advice."""
    entry = {"video_id": video_id, "stats": rec, "retention": retention, "advice": advice(rec, retention),
             "note": note}
    store.save(store.channel_file(root, NAME), {"records": load(root) + [entry]})
    return entry
