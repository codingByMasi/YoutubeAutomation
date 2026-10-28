"""`run-all`: research a seed, then take the top approved idea through thumbnail. Stops at the review gate."""

from __future__ import annotations

import typer

from studio.context import Ctx
from studio.models import Idea, Video
from studio.stages import build, research, script, thumbnail, visuals, voice
from studio.stages.base import stage_index


def pick_video(ctx: Ctx, ranked: list[Idea]) -> Video:
    """Highest-ranked approved idea still before the review gate; else approve the top new idea."""
    s = ctx.session
    approved = [i for i in research.rank(s.query(Idea).filter_by(status="approved").all())
                if not i.seed.startswith("__")]
    for idea in approved:
        v = s.query(Video).filter_by(idea_id=idea.id).first()
        if v and stage_index(v.stage) < stage_index("thumbnailed"):
            return v
    fresh = [i for i in ranked if i.status == "idea"]
    if not fresh:
        raise_no_ideas()
    typer.echo(f"No approved idea in progress; approving the top-ranked idea #{fresh[0].id}: {fresh[0].topic}")
    return research.approve(ctx, fresh[0].id)


def raise_no_ideas() -> None:
    from studio.errors import StudioError
    raise StudioError("No idea to work on.", "Every idea is rejected, finished, or already past thumbnail.",
                      "Run research with a new seed, or approve an idea with `approve-idea <id>`.")


def run(ctx: Ctx, seed: str) -> Video:
    ranked = research.run(ctx, seed)
    v = pick_video(ctx, ranked)
    typer.echo(f"\n== Working on video {v.id} ==")
    script.run(ctx, v.idea_id)       # may stop here for Claude Code to answer the prompt
    voice.run(ctx, v.id)
    visuals.run(ctx, v.id)
    build.run(ctx, v.id)
    thumbnail.run(ctx, v.id)
    typer.secho(f"\nStopped at the review gate. Watch {ctx.settings.project_dir(v.id) / 'final.mp4'}, then run "
                f"`review {v.id}`.", fg=typer.colors.GREEN)
    return v
