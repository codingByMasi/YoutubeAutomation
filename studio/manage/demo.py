"""`demo`: a dry run that builds a playable MP4 from the bundled sample script, with no API keys."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StudioError
from studio.models import Idea, Video
from studio.providers.tts import SilentTTS, get_tts
from studio.stages import build, script, thumbnail, visuals, voice

SAMPLE = Path(__file__).parent.parent / "samples" / "sample_script.json"
DEMO_SEED = "__demo__"


def run(ctx: Ctx, force: bool = False) -> Video:
    s = ctx.session
    pkg = json.loads(SAMPLE.read_text(encoding="utf-8"))
    idea = s.query(Idea).filter_by(seed=DEMO_SEED).first()
    if idea is None:
        idea = Idea(seed=DEMO_SEED, topic=f"[demo] {pkg['topic']}", status="approved")
        s.add(idea)
        s.flush()
        s.add(Video(idea_id=idea.id, stage="approved"))
        s.commit()
    video = s.query(Video).filter_by(idea_id=idea.id).one()
    resp = ctx.settings.project_dir(video.id) / "prompts" / "script.response.json"
    resp.parent.mkdir(exist_ok=True)
    resp.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    typer.echo(f"Demo video {video.id}: sample script, generated cards instead of stock footage.")
    if force and video.stage != "approved":
        video.stage = "approved"  # roll back so every stage below is redone from the sample
        s.commit()
    script.run(ctx, idea.id)
    tts = get_tts(ctx.settings)
    try:
        voice.run(ctx, video.id, force=force, tts=tts)
    except StudioError as exc:
        typer.secho(f"TTS '{tts.name}' unavailable ({exc.what}); using silent narration for the demo.",
                    fg=typer.colors.YELLOW)
        voice.run(ctx, video.id, force=True, tts=SilentTTS())
    visuals.run(ctx, video.id, force=force, stock=None)
    build.run(ctx, video.id, force=force)
    thumbnail.run(ctx, video.id, force=force)
    typer.echo(f"Done. Play {ctx.settings.project_dir(video.id) / 'final.mp4'}")
    return video
