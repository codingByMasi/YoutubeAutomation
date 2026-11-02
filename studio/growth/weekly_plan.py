"""Weekly planner: how many videos each channel needs, on which days, and what is due.

Pure planning. It never uploads or publishes; it only suggests `--at` times for the existing `publish` command,
which keeps its private-by-default upload and typed-yes gate.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# Default rhythm per channel type: (weekdays 0=Mon, "HH:MM" local time). Used when the profile leaves them blank.
# Reasoning: adults watch business/history explainers after work or on a lazy weekend afternoon; kids content
# is watched with a parent at weekend mornings.
TYPE_RHYTHM: dict[str, tuple[tuple[int, ...], str]] = {
    "business": ((1, 3), "16:00"),   # Tue, Thu
    "history": ((6,), "15:00"),      # Sun
    "kids": ((5,), "09:00"),         # Sat
    "general": ((2,), "17:00"),      # Wed
}
# Suggested split of 4 videos a week across three channels (finance 2, history 1, kids 1).
SUGGESTED_SPLIT = {"business": 2, "history": 1, "kids": 1}

# Claude handoff prompts per video (prompt-file flow): outline, script, critique; facts for sourced channels.
HANDOFFS = {"business": 4, "history": 4, "kids": 2, "general": 3}
# Hands-on owner minutes per video (approve topic, answer/skim prompts, review + typed yes), excluding render.
OWNER_MIN = {"business": 25, "history": 25, "kids": 15, "general": 20}
# Machine render minutes per finished minute of video, from e2e-test/quality-report.md
# (60 s history: voice 31 s + visuals 55 s + build 47 s = ~2.2 min; kids build 48.5 s): about 2.2 min per minute.
RENDER_MIN_PER_VIDEO_MIN = 2.2
LENGTH_MIN = {"business": 8, "history": 8, "kids": 1, "general": 6}


def rhythm(profile: dict) -> tuple[list[int], str]:
    """Publish weekdays and time for a channel profile (profile values win over the type default)."""
    days, time_ = TYPE_RHYTHM.get(profile.get("type"), TYPE_RHYTHM["general"])
    days = list(profile.get("publish_days") or days)
    n = max(1, int(profile.get("posts_per_week") or len(days)))
    while len(days) < n:  # more posts than days: add the next free weekdays
        days.append(next(d for d in range(7) if d not in days))
    return sorted(days[:n]), profile.get("publish_time") or time_


def slots(profile: dict, week_start: date) -> list[datetime]:
    """This channel's publish datetimes for the week starting on `week_start` (a Monday)."""
    days, time_ = rhythm(profile)
    hh, mm = (int(x) for x in time_.split(":"))
    out = []
    for d in days:
        day = week_start + timedelta(days=(d - week_start.weekday()) % 7)
        out.append(datetime(day.year, day.month, day.day, hh, mm))
    return sorted(out)


def monday(day: date) -> date:
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())


def budget(profile: dict) -> dict:
    """Time budget for one channel for a week: render minutes, owner minutes, handoff prompts."""
    t, n = profile.get("type"), int(profile.get("posts_per_week") or 1)
    render = round(LENGTH_MIN.get(t, 6) * RENDER_MIN_PER_VIDEO_MIN, 1)
    return {"videos": n, "render_min_each": render, "render_min": round(render * n, 1),
            "owner_min": OWNER_MIN.get(t, 20) * n, "handoffs": HANDOFFS.get(t, 3) * n}


def build(channels: list[dict], due_by_channel: dict[str, list[dict]], today: date) -> dict:
    """Plan the current week. `due_by_channel[id]` = [{id, title, stage, publish_at}] of unpublished videos."""
    start = monday(today)
    rows, totals = [], {"videos": 0, "render_min": 0.0, "owner_min": 0, "handoffs": 0}
    for c in channels:
        due = list(due_by_channel.get(c["id"], []))
        b = budget(c)
        for k in ("videos", "render_min", "owner_min", "handoffs"):
            totals[k] += b[k]
        queue = [v for v in due if not v.get("publish_at")]
        for when in slots(c, start):
            fixed = next((v for v in due if v.get("publish_at") and v["publish_at"].date() == when.date()), None)
            pick = fixed or (queue.pop(0) if queue else None)
            rows.append({"channel": c["id"], "name": c["name"], "type": c["type"], "when": when,
                         "video": pick, "needs_topic": pick is None,
                         "at": when.strftime("%Y-%m-%d %H:%M")})
    rows.sort(key=lambda r: r["when"])
    return {"week_start": start, "rows": rows, "totals": totals,
            "budgets": {c["id"]: budget(c) for c in channels}}


def render_markdown(plan: dict) -> str:
    """Human-readable weekly plan."""
    lines = [f"# Week of {plan['week_start']:%Y-%m-%d}", "",
             "| When | Channel | Video | Next step |", "|---|---|---|---|"]
    for r in plan["rows"]:
        v = r["video"]
        if v:
            step = (f"`publish {v['id']} --at \"{r['at']}\"` (after review)" if not v.get("publish_at")
                    else "scheduled")
            lines.append(f"| {r['when']:%a %d %b %H:%M} | {r['name']} | "
                         f"#{v['id']} {v['title']} ({v['stage']}) | {step} |")
        else:
            lines.append(f"| {r['when']:%a %d %b %H:%M} | {r['name']} | NO TOPIC YET | "
                         f"`channels use {r['channel']}` then `suggest`, `approve-idea <id>` |")
    t = plan["totals"]
    lines += ["", f"Totals: {t['videos']} videos, ~{t['render_min']:.0f} min render (machine), "
              f"~{t['owner_min']} min of your time, {t['handoffs']} Claude handoff prompts.", ""]
    return "\n".join(lines)
