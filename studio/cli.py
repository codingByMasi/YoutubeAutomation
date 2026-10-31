"""Typer entry point: `python -m studio.cli --help`."""

from __future__ import annotations

import sys

import typer

from studio.context import Ctx, build_ctx
from studio.errors import StudioError

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="YouTube Channel Studio: research -> script -> voice -> visuals -> build -> "
                       "thumbnail -> review (typed yes) -> publish -> analytics.")
_state: dict = {"verbose": False}
FORCE = typer.Option(False, "--force", help="Re-run even if this stage is already done.")


def _ctx() -> Ctx:
    if "ctx" not in _state:
        _state["ctx"] = build_ctx(verbose=_state["verbose"])
    return _state["ctx"]


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs.")) -> None:
    _state["verbose"] = verbose


# ---------------- Topics ----------------
@app.command()
def research(seed: str = typer.Argument(..., help="Seed topic, e.g. 'how cruise lines make money'."),
             force: bool = typer.Option(False, "--force", help="Ignore today's cached results for this seed."),
             limit: int = typer.Option(15, help="How many ideas to show.")) -> None:
    """Find topic ideas for a seed, flag small-channel outliers, and rank by demand vs competition."""
    from studio.stages import research as m
    m.run(_ctx(), seed, force=force, limit=limit)


@app.command("approve-idea")
def approve_idea(idea_id: int = typer.Argument(..., help="Idea id from the research table.")) -> None:
    """Approve a topic and create its video record."""
    from studio.stages import research as m
    m.approve(_ctx(), idea_id)


# ---------------- Production ----------------
@app.command()
def script(idea_id: int = typer.Argument(..., help="Approved idea id."), force: bool = FORCE) -> None:
    """Generate 15 titles, the full script, and the segment list (script.md + script.json)."""
    from studio.stages import script as m
    m.run(_ctx(), idea_id, force=force)


@app.command()
def voice(video_id: int, force: bool = FORCE) -> None:
    """Synthesize narration per segment and record real durations."""
    from studio.stages import voice as m
    m.run(_ctx(), video_id, force=force)


@app.command()
def visuals(video_id: int, force: bool = FORCE) -> None:
    """Fetch stock clips, render charts/number cards, and record licences."""
    from studio.stages import visuals as m
    m.run(_ctx(), video_id, force=force)


@app.command()
def build(video_id: int, force: bool = FORCE) -> None:
    """Assemble the final 1080p MP4 with captions, music, intro and outro."""
    from studio.stages import build as m
    m.run(_ctx(), video_id, force=force)


@app.command()
def shorts(video_id: int, count: int = typer.Option(3, min=2, max=3), force: bool = FORCE) -> None:
    """Cut 2-3 vertical 9:16 Shorts from a built video."""
    from studio.stages import shorts as m
    m.run(_ctx(), video_id, count=count, force=force)


@app.command()
def thumbnail(video_id: int, force: bool = FORCE) -> None:
    """Generate 3 thumbnail variants (1280x720, under 2 MB)."""
    from studio.stages import thumbnail as m
    m.run(_ctx(), video_id, force=force)


# ---------------- Gate ----------------
@app.command()
def review(video_id: int,
           thumb: int = typer.Option(1, help="Which thumbnail variant to use (1-3)."),
           title: str | None = typer.Option(None, help="Override the picked title."),
           force: bool = FORCE) -> None:
    """Show the pre-publish checklist and require a typed 'yes'."""
    from studio.stages import review as m
    m.run(_ctx(), video_id, thumb=thumb, title=title, force=force)


@app.command()
def publish(video_id: int,
            at: str | None = typer.Option(None, "--at", help="Publish time, e.g. '2026-11-05 18:00' (local)."),
            playlist: str | None = typer.Option(None, help="Playlist id to add the video to.")) -> None:
    """Upload as private/scheduled with all metadata. Needs `review` and a typed 'yes'."""
    from studio.stages import publish as m
    m.run(_ctx(), video_id, at=at, playlist=playlist)


# ---------------- Management ----------------
@app.command()
def analytics(days: int = typer.Option(28, help="Days of history to pull.")) -> None:
    """Pull per-video metrics and write a plain-English report."""
    from studio.manage import analytics_report as m
    m.run(_ctx(), days=days)


@app.command("ab-log")
def ab_log(video_id: int,
           field: str | None = typer.Option(None, help="title or thumbnail"),
           new: str | None = typer.Option(None, help="New value (title text or thumbnail path)."),
           old: str | None = typer.Option(None, help="Old value (defaults to the current live value).")) -> None:
    """Record a title/thumbnail change with before/after metrics. Without options, lists and refreshes."""
    from studio.manage import ab_log as m
    m.run(_ctx(), video_id, field=field, new=new, old=old)


@app.command()
def comments(target: str = typer.Argument(..., help="A video id to draft replies, or 'post'."),
             file: str | None = typer.Argument(None, help="With 'post': the drafts file to post from.")) -> None:
    """Draft replies to recent comments (never posts). `comments post <file>` posts with per-reply 'yes'."""
    from studio.manage import comments as m
    if target == "post":
        if not file:
            raise StudioError("`comments post` needs a drafts file.", "",
                              "Run `comments post projects/<id>/comments_drafts.json`.")
        m.post(_ctx(), file)
    else:
        m.draft(_ctx(), int(target))


@app.command()
def calendar(weeks: int = typer.Option(4)) -> None:
    """4-week content calendar from approved ideas, with gaps flagged against cadence."""
    from studio.manage import calendar as m
    m.run(_ctx(), weeks=weeks)


@app.command()
def status(sync: bool = typer.Option(False, "--sync", help="Check YouTube and mark published videos live.")) -> None:
    """One-screen table of every video and its stage."""
    from studio.manage import status as m
    m.run(_ctx(), sync=sync)


@app.command("run-all")
def run_all(seed: str) -> None:
    """Research a seed, then take the top approved idea through thumbnail and stop at review."""
    from studio.manage import run_all as m
    m.run(_ctx(), seed)


@app.command()
def quota() -> None:
    """Show today's YouTube API quota use."""
    for bucket, v in _ctx().quota.summary().items():
        typer.echo(f"{bucket:7} used {v['used']:>5} of {v['budget']:>5}  ({v['remaining']} left)")


@app.command()
def demo(force: bool = FORCE) -> None:
    """Dry run: build a playable MP4 from bundled sample inputs (no API keys needed)."""
    from studio.manage import demo as m
    m.run(_ctx(), force=force)


# ---------------- Kids mode (separate from the long-form pipeline) ----------------
kids_app = typer.Typer(no_args_is_help=True, help="Kids mode: original nursery-rhyme and learning-song videos. "
                       "Never uploads; finish with `kids checklist` and upload by hand.")
app.add_typer(kids_app, name="kids")


@kids_app.command("script")
def kids_script(topic: str = typer.Argument(..., help="e.g. 'counting five little ducks'."),
    force: bool = FORCE) -> None:
    """Write the kids script prompt (exit 3), then validate Claude's answer into script.json."""
    from studio.kids import script as m
    d = m.run(_ctx(), topic, force=force)
    typer.echo(f"Script ready: projects/kids_{d['slug']}/script.json ({len(d['scenes'])} scenes).")


@kids_app.command("build")
def kids_build(topic: str, force: bool = FORCE) -> None:
    """Narrate and animate every scene into projects/kids_<slug>/final.mp4 (+ thumbnail.jpg)."""
    from studio.kids import build as m
    from studio.kids.script import slugify
    typer.echo(f"Built {m.run(_ctx(), slugify(topic), force=force)}")


@kids_app.command("checklist")
def kids_checklist(topic: str) -> None:
    """Show the Made for Kids checklist and save it next to the video."""
    from studio.kids import checklist as m
    from studio.kids.script import project_dir, slugify
    typer.echo(m.render_text(m.run(project_dir(_ctx(), slugify(topic)))))


@kids_app.command("demo")
def kids_demo(force: bool = FORCE) -> None:
    """Keyless dry run: build a sample counting-song video with silent narration."""
    from studio.kids import demo as m
    typer.echo(f"Built {m.run(_ctx(), force=force)}")


def run() -> None:
    """Entry point that prints StudioErrors cleanly."""
    try:
        app()
    except StudioError as exc:
        typer.secho(str(exc), fg=typer.colors.RED if exc.exit_code != 3 else typer.colors.YELLOW, err=True)
        sys.exit(exc.exit_code)
    except KeyboardInterrupt:
        typer.echo("Cancelled.", err=True)
        sys.exit(130)


if __name__ == "__main__":
    run()
