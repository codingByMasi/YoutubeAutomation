"""`ab-log`: record title/thumbnail changes made in YouTube Studio, with before/after metrics.

This command only records. It never changes the live video.
"""

from __future__ import annotations

import json
from datetime import timedelta

import typer

from studio.context import Ctx
from studio.errors import StudioError
from studio.manage.analytics_report import period_summary
from studio.models import ABTest, Title, utcnow
from studio.stages.base import get_video

WINDOW_DAYS = 7


def _current(ctx: Ctx, video_id: int, field: str) -> str:
    last = ctx.session.query(ABTest).filter_by(video_id=video_id, field=field).order_by(ABTest.id.desc()).first()
    if last:
        return last.new_value
    review = ctx.settings.project_dir(video_id) / "review.json"
    data = json.loads(review.read_text()) if review.exists() else {}
    return data.get("title" if field == "title" else "thumbnail", "")


def refresh(ctx: Ctx, video_id: int) -> list[ABTest]:
    """Fill after-metrics for changes at least WINDOW_DAYS old."""
    video = get_video(ctx.session, video_id)
    tests = ctx.session.query(ABTest).filter_by(video_id=video_id).order_by(ABTest.changed_at).all()
    for t in tests:
        if t.metrics_after_json in ("", "{}") and utcnow() - t.changed_at >= timedelta(days=WINDOW_DAYS):
            after = period_summary(ctx, video.youtube_video_id or "", t.changed_at,
                                   t.changed_at + timedelta(days=WINDOW_DAYS))
            if after:
                t.metrics_after_json = json.dumps(after)
    ctx.session.commit()
    return tests


def run(ctx: Ctx, video_id: int, field: str | None = None, new: str | None = None, old: str | None = None) -> None:
    video = get_video(ctx.session, video_id)
    if field or new:
        if field not in ("title", "thumbnail") or not new:
            raise StudioError("ab-log needs --field title|thumbnail and --new.", "",
                              'Example: ab-log 3 --field title --new "The Economics of a $5 Latte"')
        if not video.youtube_video_id:
            raise StudioError(f"Video {video_id} is not on YouTube yet.", "A/B logs track live changes.",
                              f"Publish it first with `publish {video_id}`.")
        now = utcnow()
        before = period_summary(ctx, video.youtube_video_id, now - timedelta(days=WINDOW_DAYS), now)
        ctx.session.add(ABTest(video_id=video_id, field=field, old_value=old or _current(ctx, video_id, field),
                               new_value=new, changed_at=now, metrics_before_json=json.dumps(before)))
        if field == "title":
            ctx.session.query(Title).filter_by(video_id=video_id).update({"is_live": False})
            ctx.session.add(Title(video_id=video_id, text=new, style="ab-test", length=len(new), is_live=True))
        ctx.session.commit()
        typer.echo(f"Logged {field} change for video {video_id}. Make the same change in YouTube Studio if you "
                   f"have not already. After-metrics fill in after {WINDOW_DAYS} days (run `analytics`, then "
                   f"`ab-log {video_id}`).")
    for t in refresh(ctx, video_id):
        b, a = json.loads(t.metrics_before_json or "{}"), json.loads(t.metrics_after_json or "{}")
        typer.echo(f"[{t.changed_at:%Y-%m-%d}] {t.field}: {t.old_value!r} -> {t.new_value!r}\n"
                   f"    before: {b or 'no data'}\n    after:  {a or 'pending'}")
