"""`calendar`: 4-week content plan from approved ideas, with gaps flagged against the cadence."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import typer

from studio import scope
from studio.context import Ctx
from studio.models import Idea, Title, Video
from studio.stages.base import stage_index

# SPEC section 1 default cadence: 2 long videos + 3 Shorts per week.
LONG_DAYS = (1, 4)        # Tuesday, Friday
SHORT_DAYS = (0, 2, 5)    # Monday, Wednesday, Saturday
SHORTS_PER_VIDEO = 3


def slots(start: date, weeks: int) -> list[tuple[date, str]]:
    """(date, 'long'|'short') slots from start for N weeks."""
    out = []
    for i in range(weeks * 7):
        d = start + timedelta(days=i)
        if d.weekday() in LONG_DAYS:
            out.append((d, "long"))
        elif d.weekday() in SHORT_DAYS:
            out.append((d, "short"))
    return out


def suggest_publish(start: date, taken: list[date], publish_time: str = "16:00") -> datetime:
    """Next free long-video slot at least 2 days after `start`, at the channel's `publish_time` (HH:MM).

    Spacing matters more than the exact hour: a steady rhythm beats raw volume (growth-playbook.md section 6).
    """
    try:
        hh, mm = (int(x) for x in publish_time.split(":"))
    except ValueError:
        hh, mm = 16, 0
    for d, kind in slots(start + timedelta(days=2), 8):
        if kind == "long" and d not in taken:
            return datetime(d.year, d.month, d.day, hh, mm)
    d = start + timedelta(days=3)
    return datetime(d.year, d.month, d.day, hh, mm)


def plan(start: date, weeks: int, scheduled: list[tuple[date, str]], queue: list[str]) -> list[tuple[date, str, str]]:
    """Fill slots: scheduled videos keep their dates, queued videos take the next free long slots,
    and Shorts from each placed video fill the Shorts slots after it. Empty slots are 'GAP'."""
    table = {(d, k): "" for d, k in slots(start, weeks)}
    placed: list[tuple[date, str]] = []
    for d, label in scheduled:
        if (d, "long") in table:
            table[(d, "long")] = f"{label} (scheduled)"
        placed.append((d, label))
    q = list(queue)
    for d, k in sorted(table):
        if k == "long" and not table[(d, k)] and q:
            label = q.pop(0)
            table[(d, k)] = label
            placed.append((d, label))
    shorts = [(d, label) for d, label in sorted(placed) for _ in range(SHORTS_PER_VIDEO)]
    for d, k in sorted(table):
        if k == "short" and not table[(d, k)]:
            nxt = next((i for i, (pd, _) in enumerate(shorts) if pd <= d), None)
            if nxt is not None:
                table[(d, k)] = f"Short from: {shorts.pop(nxt)[1]}"
    return [(d, k, v or "GAP") for (d, k), v in sorted(table.items())]


def run(ctx: Ctx, weeks: int = 4, today: date | None = None) -> Path:
    s = ctx.session
    start = today or date.today()

    def label(v: Video) -> str:
        t = s.query(Title).filter_by(video_id=v.id, is_pick=True).first()
        return f"#{v.id} {t.text if t else s.get(Idea, v.idea_id).topic}"

    vids = [v for v in scope.videos(s).all() if not s.get(Idea, v.idea_id).seed.startswith("__")]
    scheduled = [(v.publish_at.date(), label(v)) for v in vids if v.publish_at and v.publish_at.date() >= start]
    queue = [label(v) for v in sorted((v for v in vids if not v.youtube_video_id),
                                      key=lambda v: (-stage_index(v.stage), v.id))]
    rows = plan(start, weeks, scheduled, queue)
    gaps = sum(1 for r in rows if r[2] == "GAP")
    lines = [f"# Content calendar from {start:%Y-%m-%d} ({weeks} weeks)", "", "| Date | Day | Type | Content |",
             "|---|---|---|---|"]
    lines += [f"| {d:%Y-%m-%d} | {d:%a} | {k} | {v} |" for d, k, v in rows]
    long_gaps = sum(1 for r in rows if r[2] == "GAP" and r[1] == "long")
    lines += ["", f"{gaps} empty slots ({long_gaps} long)." +
              (f" Approve {long_gaps} more idea(s) to keep the 2-per-week cadence." if long_gaps else "")]
    text = "\n".join(lines) + "\n"
    out = ctx.settings.root / "reports" / "calendar.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    for d, k, v in rows:
        colour = typer.colors.RED if v == "GAP" else None
        typer.secho(f"{d:%Y-%m-%d} {d:%a}  {k:<5}  {v}", fg=colour)
    typer.echo(lines[-1] + f"\nSaved to {out}")
    return out
