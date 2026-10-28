"""`shorts`: 2-3 vertical 9:16 highlight clips with large captions, cut from the built video."""

from __future__ import annotations

from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StageError
from studio.providers.whisper import script_cues, to_srt
from studio.stages.base import get_video, stage_index
from studio.stages.script import load_package, timeline, write_package
from studio.stages.timing import pick_short_windows
from studio.util import ffmpeg as ff


def run(ctx: Ctx, video_id: int, count: int = 3, force: bool = False) -> list[Path]:
    video = get_video(ctx.session, video_id)
    if stage_index(video.stage) < stage_index("built"):
        raise StageError(f"Video {video_id} has no built video yet (stage '{video.stage}').", "",
                         f"Run `build {video_id}` first.")
    pkg = load_package(ctx, video_id)
    out = ctx.settings.project_dir(video_id) / "shorts"
    existing = sorted(out.glob("short_*.mp4")) if out.exists() else []
    if existing and not force:
        typer.echo(f"Video {video_id}: {len(existing)} Shorts already cut. Use --force to redo them.")
        return existing
    ff.ensure_ffmpeg()
    out.mkdir(exist_ok=True)
    for old in existing:
        old.unlink()
    segs = pkg["segments"]
    spans = timeline(segs)
    windows = pick_short_windows(spans, segs, count)
    if len(windows) < 2:
        raise StageError("Could not find 2 Shorts-length runs (15-58 s) in this video.",
                         "Segments are too long or the video is too short.",
                         "Split long segments in script.json, or cut Shorts by hand from clean.mp4.")
    cues = script_cues(spans, [g["narration"] for g in segs])
    clean = Path(pkg.get("build", {}).get("clean") or ctx.settings.project_dir(video_id) / "clean.mp4")
    made, info = [], []
    for n, (i, j) in enumerate(windows, 1):
        start, end = spans[i][0], spans[j][1]
        srt = out / f"short_{n}.srt"
        srt.write_text(to_srt(cues, window=(start, end)), encoding="utf-8")
        dest = out / f"short_{n}.mp4"
        ff.run(ff.vertical_cmd(clean, start, end - start, dest, srt), f"cutting Short {n}")
        made.append(dest)
        info.append({"file": str(dest), "start": round(start, 2), "end": round(end, 2),
                     "segments": [i + 1, j + 1], "chapter": segs[i].get("chapter", "")})
    pkg["shorts"] = info
    write_package(ctx, video_id, pkg)
    typer.echo(f"Cut {len(made)} Shorts into {out}")
    return made
