"""`voice`: narration audio per segment; real durations replace estimates."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer

from studio.context import Ctx
from studio.models import Segment
from studio.providers.tts import TTS, get_tts
from studio.stages.base import get_video, run_stage
from studio.stages.script import load_package, pacing_warnings, write_package
from studio.util.ffmpeg import probe_duration

VOICE_WORKERS = 4


def apply_real_durations(pkg: dict, rows: list[Segment], durations: dict[int, float]) -> float:
    """Write real seconds into DB rows and the package; return the new total length in seconds."""
    for row in rows:
        if row.position in durations:
            row.real_seconds = round(durations[row.position], 3)
            pkg["segments"][row.position - 1]["real_seconds"] = row.real_seconds
    return round(sum(float(s.get("real_seconds") or s["est_seconds"]) for s in pkg["segments"]), 3)


def run(ctx: Ctx, video_id: int, force: bool = False, tts: TTS | None = None,
        measure: Callable = probe_duration) -> None:
    s = ctx.session
    video = get_video(s, video_id)

    def work() -> None:
        engine = tts or get_tts(ctx.settings)
        out = ctx.settings.project_dir(video_id) / "voice"
        out.mkdir(exist_ok=True)
        pkg = load_package(ctx, video_id)
        rows = s.query(Segment).filter_by(video_id=video_id).order_by(Segment.position).all()
        durations = {}

        def voice_row(row: Segment) -> tuple[Segment, Path]:
            path = out / f"seg_{row.position:03d}.mp3"
            if force or not path.exists() or path.stat().st_size == 0:
                engine.synth(row.narration, path)
            return row, path

        # Synthesis waits on the network, so a few at once is much faster; results are kept in order.
        with typer.progressbar(length=len(rows), label=f"Voicing {len(rows)} segments ({engine.name})") as bar, \
                ThreadPoolExecutor(VOICE_WORKERS) as pool:
            for row, path in pool.map(voice_row, rows):
                row.audio_path = str(path)
                durations[row.position] = measure(path)
                bar.update(1)
        total = apply_real_durations(pkg, rows, durations)
        est = sum(r.est_seconds for r in rows)
        write_package(ctx, video_id, pkg)
        typer.echo(f"Narration: {total / 60:.1f} min (estimated {est / 60:.1f} min).")
        for w in pacing_warnings(pkg["segments"], "real_seconds"):
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)

    r = run_stage(s, video, "voiced", work, force)
    typer.echo(r.message + (f" Next: visuals {video_id}" if r.ran else ""))
