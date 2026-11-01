"""Says plainly which renderer a video will use (or used) and why: 3D scenes, 2D fallback, and the reason."""

from __future__ import annotations

import json
from pathlib import Path

from studio import production, scenes
from studio.blender import provider
from studio.config import Settings

FILE = "render_report.json"


def preflight(settings: Settings, video_id: int, segs: list[dict] | None = None) -> dict:
    """What a build would do: verdict ("3D"/"2D"), planned_3d (segment numbers), blender (path or None), notes.

    `notes` are plain sentences saying why a video would come out 2D and what to change.
    """
    prod = production.resolve(settings, video_id)
    exe, why = provider.usable(settings.blender_path)
    segs = segs or []
    planned = []
    for pos, seg in enumerate(segs, 1):
        pl = scenes.plan_for(seg, pos, prod)
        if pl and pl["mode"] == "3d":
            planned.append(pos)
    src = prod["sources"]
    notes: list[str] = []
    if not production.wants_blender(prod):
        notes.append(f"3D is off: renderer is '{prod['renderer'] or '2d'}' (from {src['renderer']}) and scene style is "
                     f"'{prod['scene_style'] or '2d'}' (from {src['scene_style']}). Pick Mixed or 3D under "
                     "'Look and sound for this video' to turn it on.")
    elif exe is None:
        notes.append(f"3D was asked for, but Blender cannot be used, so everything is drawn in 2D. {why}")
    elif segs and not planned:
        notes.append("3D is on and Blender works, but this script has no scene and no bar or line chart to draw in 3D. "
                     "Ask for scenes (timeline, map, artifact, 3D chart) when writing the script, or set single "
                     "segments to 3D in the picker.")
    verdict = "3D" if production.wants_blender(prod) and exe is not None and (planned or not segs) else "2D"
    return {"verdict": verdict, "planned_3d": planned, "blender": str(exe) if exe else None, "notes": notes,
            "renderer": prod["renderer"], "scene_style": prod["scene_style"]}


def save(settings: Settings, video_id: int, report: dict) -> Path:
    """Write the report for the video next to its other files."""
    f = settings.project_dir(video_id) / FILE
    f.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return f


def load(settings: Settings, video_id: int) -> dict | None:
    """The saved report, or None when the video has not been through `visuals` yet."""
    f = settings.project_dir(video_id) / FILE
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def summary(report: dict) -> list[str]:
    """Plain lines for the CLI and the app."""
    got = report.get("scenes", {})
    lines = [f"Renderer used: {report['verdict']}  (3D scenes drawn: {got.get('3d', 0)}, "
             f"2D scenes: {got.get('2d', 0)}, animated charts: {report.get('animated_charts', 0)})"]
    return lines + [f"  ! {n}" for n in report["notes"]]
