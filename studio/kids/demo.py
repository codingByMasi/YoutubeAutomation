"""`kids demo`: build the bundled sample counting song with silent narration (no keys, no internet)."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from studio.context import Ctx
from studio.kids import build
from studio.kids.script import project_dir

SAMPLE = Path(__file__).parent.parent / "samples" / "kids_sample.json"


def run(ctx: Ctx, force: bool = False) -> Path:
    """Copy the sample script into projects/kids_demo and build it. Returns the MP4 path."""
    d = project_dir(ctx, "demo")
    shutil.copyfile(SAMPLE, d / "script.json")
    quiet = dataclasses.replace(ctx, settings=dataclasses.replace(ctx.settings, tts_provider="silent"))
    return build.run(quiet, "demo", force=force, size=(640, 360), fps=12)
