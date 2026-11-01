"""`kids sing`: write the melody and lyrics files for OpenUtau, or pick up the exported vocal."""

from __future__ import annotations

import json
from pathlib import Path

from studio.context import Ctx
from studio.errors import StageError
from studio.kids import openutau, sing, sing_files
from studio.kids.script import project_dir


def run(ctx: Ctx, slug: str, force: bool = False) -> dict[str, Path]:
    """Write projects/kids_<slug>/sung/{song.mid,song.ustx,lyrics.txt,sing_plan.json}. Idempotent."""
    d = project_dir(ctx, slug)
    script_file = d / "script.json"
    if not script_file.exists():
        raise StageError(f"No script for {slug}.", "The sung step needs projects/kids_<slug>/script.json.",
                         "Run `kids script \"<topic>\"` first.")
    out = d / "sung"
    files = {"midi": out / "song.mid", "ustx": out / "song.ustx", "lyrics": out / "lyrics.txt",
             "plan": out / "sing_plan.json"}
    if all(p.exists() for p in files.values()) and not force:
        return files
    plan = sing.build_plan(json.loads(script_file.read_text(encoding="utf-8")))
    return sing_files.write_all(plan, out)


def status(ctx: Ctx, slug: str) -> str:
    """One line saying whether a vocal has been exported yet (and so whether the build will use it)."""
    v = openutau.vocal_path(project_dir(ctx, slug) / "sung")
    return f"Vocal found: {v}. `kids build --force` will mix it." if v else \
        "No exported vocal yet. The build keeps the normal narration and background tune."
