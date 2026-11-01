"""Draws one segment's scene for the `visuals` stage: 3D clip through Blender, or 2D frames (also the fallback)."""

from __future__ import annotations

from pathlib import Path

import typer

from studio.blender.provider import SceneStopped, SceneTooSlow
from studio.errors import StudioError
from studio.scenes import render2d, render3d
from studio.scenes.budget import SceneBudget
from studio.stages.timing import split_segment


def draw(pl: dict, seg: dict, pos: int, out: Path, charts: Path, blender: render3d.Blender3D, footnote: str,
         duration: float, budget: SceneBudget | None = None) -> dict:
    """Render the planned scene for segment `pos`: 3D clips go in `out`, 2D step frames in `charts`.

    Returns {"mode": "2d"|"3d", "frames": [...], "clip": path|None, "fell_back": bool, "kind": kind}. A 3D scene
    that cannot be rendered (Blender missing, failing, too slow or cancelled) is drawn in 2D instead and says so;
    `budget` shortens scenes that would take too long and carries progress and the cancel flag.
    """
    scene, mode, fell_back = pl["scene"], pl["mode"], False
    stem = f"scene_{pos:03d}"
    if mode == "3d":
        exe = blender.exe
        if exe is None:
            mode, fell_back = "2d", True
        else:
            clip_out = out / f"{stem}.mp4"
            replaces_chart = scene["kind"] == "chart3d"
            secs = duration if replaces_chart or not seg.get("chart_data") else split_segment(duration, True)[0]
            budget = budget or SceneBudget()
            for attempt in range(2):
                secs3, note = budget.seconds_to_render(secs, render3d.FPS_3D)
                if secs3 is None:
                    typer.secho(f"3D scene for segment {pos} drawn in 2D: {note}.", fg=typer.colors.YELLOW)
                    mode, fell_back = "2d", True
                    break
                if note:
                    typer.echo(f"3D scene for segment {pos}: {note}.")
                budget.start(pos, render3d.FPS_3D)
                try:
                    render3d.render(exe, scene, secs3, footnote, clip_out, out / f"{stem}_frames",
                                    timeout=budget.timeout(), on_frame=budget.on_frame, should_stop=budget.should_stop)
                    budget.done(round(secs3 * render3d.FPS_3D))
                    return {"mode": "3d", "frames": [], "clip": clip_out, "fell_back": False, "kind": scene["kind"],
                            "replaces_chart": replaces_chart}
                except SceneTooSlow as exc:
                    typer.echo(f"3D scene for segment {pos} stopped: {exc.why}")
                    if attempt == 1:
                        mode, fell_back = "2d", True
                except SceneStopped as exc:  # timeout or cancel
                    budget.cancelled = budget.cancelled or exc.cancelled
                    typer.secho(f"3D scene for segment {pos} stopped, using 2D: {exc.what} {exc.why}",
                                fg=typer.colors.YELLOW)
                    mode, fell_back = "2d", True
                    break
                except StudioError as exc:
                    typer.secho(f"3D scene for segment {pos} failed, using 2D: {exc.what}", fg=typer.colors.YELLOW)
                    mode, fell_back = "2d", True
                    break
    frames = render2d.render(scene, footnote, charts, stem)
    return {"mode": "2d", "frames": frames, "clip": None, "fell_back": fell_back, "kind": scene["kind"],
            "replaces_chart": False}
