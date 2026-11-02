"""Plan preview: shows, before anything is rendered, exactly what the picture step and the edit will use.

Nothing here calls a network service or renders; it reads `script.json`, the production settings and the keys in `.env`.
The owner can approve the plan; the approval is tied to a fingerprint, so changing the script's visuals or the settings
asks for approval again.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from studio import production, scenes
from studio.blender import provider
from studio.config import Settings
from studio.errors import ConfigError
from studio.providers import footage
from studio.stages.script import CHART_GAP_MAX, timeline
from studio.stages.timing import shot_max_for, shots_needed, split_segment
from studio.util import ffmpeg as ff

FILE = "plan_approval.json"
SCENE_VIDEO_NOTE = "3D scene clips are drawn at 1280x720 and 15 fps, then scaled up in the final edit"


def _services(settings: Settings) -> dict:
    """Which picture sources are available (from keys only; nothing is contacted)."""
    try:
        stock = footage.resolve_provider(settings)
        stock_err = ""
    except ConfigError as exc:
        stock, stock_err = "none", exc.what
    photos = []
    if settings.image_provider in ("auto", "pixabay") and settings.pixabay_api_key:
        photos.append("Pixabay photos")
    if settings.image_provider in ("auto", "commons"):
        photos.append("Wikimedia Commons")
    return {"stock": stock, "stock_error": stock_err, "photos": photos}


def _chart_row(seg: dict) -> dict:
    chart = seg.get("chart_data") or {}
    if not chart:
        return {}
    return {"type": chart.get("type", "?"), "title": chart.get("title", ""),
            "points": len(chart.get("values") or chart.get("labels") or []),
            "sourced": bool(chart.get("source_ids"))}


def build(settings: Settings, video_id: int, pkg: dict, draft: bool = False) -> dict:
    """The plan: `global` (settings and tools), `segments` (one row each) and `warnings` (plain sentences)."""
    prod = production.resolve(settings, video_id)
    exe, why = provider.usable(settings.blender_path)
    svc = _services(settings)
    prof = ff.Profile(w=1280, h=720, fps=24) if draft else ff.Profile()
    has_whisper = shutil.which("faster-whisper") is not None or _has_module("faster_whisper")
    segs = pkg.get("segments", [])
    spans = timeline(segs)
    rows: list[dict] = []
    warnings: list[str] = []
    for pos, seg in enumerate(segs, 1):
        dur = spans[pos - 1][1] - spans[pos - 1][0]
        bg, _ = split_segment(dur, bool(seg.get("chart_data")))
        shots = max(1, shots_needed(bg, shot_max=shot_max_for(pos)))
        pl = scenes.plan_for(seg, pos, prod)
        scene = None
        if pl:
            mode = pl["mode"] if (pl["mode"] == "2d" or exe) else "2d"
            scene = {"kind": pl["scene"]["kind"], "mode": mode, "wanted": pl["mode"],
                     "fallback": pl["mode"] == "3d" and not exe}
        if svc["stock"] != "none" or svc["photos"]:
            picture = f"{shots} shot(s): stock video / photos"
        else:
            picture = "generated card (no stock source available)"
        rows.append({"n": pos, "chapter": seg.get("chapter") or "", "seconds": round(dur, 1),
                     "keywords": list(seg.get("visual_keywords") or []), "shots": shots, "picture": picture,
                     "chart": _chart_row(seg), "scene": scene, "narration": (seg.get("narration") or "")[:110]})
        if seg.get("chart_data") and not (seg["chart_data"].get("source_ids")):
            warnings.append(f"Segment {pos}: the chart has no source (every figure needs one).")
        if not seg.get("visual_keywords"):
            warnings.append(f"Segment {pos}: no stock search words; it will use a generated card.")
        if scene and scene["fallback"]:
            warnings.append(f"Segment {pos}: planned in 3D but Blender is not usable, so it will be drawn in 2D.")
    last = 0.0
    for (start, _), seg in zip(spans, segs):
        if seg.get("chart_data"):
            last = start
        elif start - last > CHART_GAP_MAX * 2 and not seg.get("scene"):
            warnings.append(f"{start - last:.0f}s pass without a chart or scene before {start / 60:.1f} min.")
            last = start
    if svc["stock_error"]:
        warnings.append(f"Stock video: {svc['stock_error']}")
    elif svc["stock"] == "none":
        warnings.append("No stock footage key (PIXABAY_API_KEY or PEXELS_API_KEY): backgrounds will be generated "
                        "cards and photos only.")
    if not svc["photos"]:
        warnings.append("Photo search is off (IMAGE_PROVIDER=none).")
    if production.wants_blender(prod) and not exe:
        warnings.append(f"3D was asked for but Blender cannot be used ({why}). Everything will be 2D.")
    threed = sum(1 for r in rows if r["scene"] and r["scene"]["mode"] == "3d")
    if threed:
        warnings.append(f"{SCENE_VIDEO_NOTE}.")
    if rows and not any(r["scene"] or r["chart"] for r in rows):
        warnings.append("No chart or scene anywhere in this script; the video will be stock backgrounds only.")
    if rows and not any(r["chart"] for r in rows):
        warnings.append("This script has no charts.")
    plan = {
        "global": {
            "resolution": f"{prof.w}x{prof.h} @ {prof.fps} fps" + (" (fast draft)" if draft else ""),
            "voice": f"{prod['voice'] or settings.tts_voice} ({prod['tts_provider'] or settings.tts_provider})",
            "music": f"{prod['music'] or 'generated'}, mood {prod['music_mood'] or 'default'}",
            "captions": "word-timed (Whisper)" if has_whisper else "timed from the script (install faster-whisper "
                                                                    "for word-accurate captions)",
            "scene_style": prod["scene_style"] or "2d", "renderer": prod["renderer"] or "2d",
            "blender": str(exe) if exe else f"not usable: {why}",
            "stock_video": svc["stock"], "photos": ", ".join(svc["photos"]) or "off",
            "minutes": round(spans[-1][1] / 60, 1) if spans else 0.0,
            "scenes_3d": threed,
            "scenes_2d": sum(1 for r in rows if r["scene"] and r["scene"]["mode"] == "2d"),
            "charts": sum(1 for r in rows if r["chart"]),
        },
        "segments": rows,
        "warnings": warnings,
    }
    plan["fingerprint"] = fingerprint(plan)
    return plan


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def fingerprint(plan: dict) -> str:
    """Short hash of everything the owner is approving."""
    core = {"g": plan["global"], "s": [{k: r[k] for k in ("n", "keywords", "chart", "scene")}
                                       for r in plan["segments"]]}
    return hashlib.sha1(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:12]


def approve(settings: Settings, video_id: int, plan: dict) -> None:
    """Remember that the owner approved this exact plan."""
    (settings.project_dir(video_id) / FILE).write_text(json.dumps({"fingerprint": plan["fingerprint"]}),
                                                       encoding="utf-8")


def is_approved(settings: Settings, video_id: int, plan: dict) -> bool:
    """True when the saved approval matches the current plan."""
    f: Path = settings.project_dir(video_id) / FILE
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("fingerprint") == plan["fingerprint"]
    except (OSError, ValueError):
        return False


def set_keywords(pkg: dict, position: int, keywords: list[str]) -> dict:
    """Replace one segment's stock search words (used by the preview's edit box)."""
    words = [k.strip() for k in keywords if k.strip()]
    if words:
        pkg["segments"][position - 1]["visual_keywords"] = words
    return pkg


def to_lines(plan: dict) -> list[str]:
    """Plain-text version for the CLI."""
    g = plan["global"]
    out = [f"Plan: {g['minutes']} min, {g['resolution']}, voice {g['voice']}, music {g['music']}",
           f"Scenes: {g['scenes_3d']} in 3D, {g['scenes_2d']} in 2D; charts: {g['charts']}; renderer {g['renderer']}, "
           f"scene style {g['scene_style']}",
           f"Blender: {g['blender']}", f"Stock video: {g['stock_video']}; photos: {g['photos']}",
           f"Captions: {g['captions']}", ""]
    for r in plan["segments"]:
        sc = f"{r['scene']['mode'].upper()} {r['scene']['kind']}" if r["scene"] else "-"
        ch = f"{r['chart']['type']} chart" if r["chart"] else "-"
        out.append(f"{r['n']:>2}. {r['seconds']:>5}s  scene: {sc:<18} chart: {ch:<12} "
                   f"search: {', '.join(r['keywords']) or '(none)'}")
    out += [""] + [f"  ! {w}" for w in plan["warnings"]]
    return out
