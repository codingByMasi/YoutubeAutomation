"""Draws one segment's scene for the `visuals` stage: 3D clip through Blender, or 2D frames (also the fallback)."""

from __future__ import annotations

from pathlib import Path

import typer

from studio.errors import StudioError
from studio.scenes import render2d, render3d
from studio.stages.timing import split_segment


def draw(pl: dict, seg: dict, pos: int, out: Path, charts: Path, blender: render3d.Blender3D, footnote: str,
         duration: float, audio: Path | None = None) -> dict:
    """Render the planned scene for segment `pos`: 3D clips go in `out`, 2D step frames in `charts`.

    Returns {"mode": "2d"|"3d", "frames": [...], "clip": path|None, "fell_back": bool, "kind": kind}. A 3D scene
    that cannot be rendered (Blender missing or failing) is drawn in 2D instead and says so.
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
            try:
                render3d.render(exe, scene, secs, footnote, clip_out, out / f"{stem}_frames", audio)
                return {"mode": "3d", "frames": [], "clip": clip_out, "fell_back": False, "kind": scene["kind"],
                        "replaces_chart": replaces_chart}
            except StudioError as exc:
                typer.secho(f"3D scene for segment {pos} failed, using 2D: {exc.what}", fg=typer.colors.YELLOW)
                mode, fell_back = "2d", True
    frames = render2d.render(scene, footnote, charts, stem)
    return {"mode": "2d", "frames": frames, "clip": None, "fell_back": fell_back, "kind": scene["kind"],
            "replaces_chart": False}
