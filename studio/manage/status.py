"""`status`: one table of every video and its stage; `--sync` marks published videos live."""

from __future__ import annotations

import typer

from studio.context import Ctx
from studio.models import Idea, Title, Video
from studio.stages.base import STAGE_COMMAND, STAGES, advance


def next_step(v: Video) -> str:
    i = STAGES.index(v.stage)
    if v.stage == "approved":
        return f"script {v.idea_id}"
    if v.stage in ("scheduled", "live"):
        return "status --sync" if v.stage == "scheduled" else "analytics"
    return f"{STAGE_COMMAND[STAGES[i + 1]]} {v.id}"


def sync_live(ctx: Ctx) -> int:
    """Mark scheduled videos that are now public as live. Returns how many changed."""
    vids = ctx.session.query(Video).filter_by(stage="scheduled").all()
    if not vids:
        return 0
    data, _ = ctx.youtube("status")
    by_id = {it["id"]: it for it in data.videos([v.youtube_video_id for v in vids], part="status")}
    changed = 0
    for v in vids:
        st = by_id.get(v.youtube_video_id, {}).get("status", {})
        if st.get("privacyStatus") == "public":
            advance(v, "live")
            changed += 1
    ctx.session.commit()
    return changed


def run(ctx: Ctx, sync: bool = False) -> list[Video]:
    s = ctx.session
    if sync:
        typer.echo(f"Synced with YouTube: {sync_live(ctx)} video(s) now live.")
    vids = s.query(Video).order_by(Video.id).all()
    if not vids:
        typer.echo("No videos yet. Start with: research \"<seed>\"")
        return []
    typer.echo(f"{'ID':>3}  {'STAGE':<13}  {'YOUTUBE':<12}  {'PUBLISH AT':<16}  {'NEXT':<18}  TITLE")
    for v in vids:
        t = s.query(Title).filter_by(video_id=v.id, is_pick=True).first()
        name = t.text if t else s.get(Idea, v.idea_id).topic
        when = f"{v.publish_at:%Y-%m-%d %H:%M}" if v.publish_at else "-"
        typer.echo(f"{v.id:>3}  {v.stage:<13}  {v.youtube_video_id or '-':<12}  {when:<16}  {next_step(v):<18}  "
                   f"{name[:60]}")
    q = ctx.quota.summary()["units"]
    typer.echo(f"\nQuota today: {q['used']} of {q['budget']} units used.")
    return vids
