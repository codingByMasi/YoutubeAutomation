"""`shorts`: 2-3 vertical 9:16 highlight clips with large captions, cut from the built video."""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StageError
from studio.providers import captions
from studio.quality import shorts_review
from studio.stages.base import get_video, stage_index
from studio.stages.script import load_package, timeline, write_package
from studio.stages.timing import ranked_short_windows
from studio.util import ffmpeg as ff

MAX_ATTEMPTS = 12  # runs tried before giving up


def hook_text(seg: dict, limit: int = 48) -> str:
    """The opening line of a Short as a short title: its first question, else its first sentence, when short enough;
    otherwise the chapter name."""
    parts = re.split(r"(?<=[.!?])\s+", str(seg.get("narration", "")).strip())
    for pick in [next((p for p in parts if p.endswith("?")), ""), parts[0] if parts else ""]:
        if 3 <= len(pick) <= limit:
            return pick
    return str(seg.get("chapter") or "")[:limit]


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
    ranked = ranked_short_windows(spans, segs, count)
    if len(ranked) < 2:
        raise StageError("Could not find 2 Shorts-length runs (15-58 s) in this video.",
                         "Segments are too long or the video is too short.",
                         "Split long segments in script.json, or cut Shorts by hand from clean.mp4.")
    words_file = ctx.settings.project_dir(video_id) / "words.json"  # word times saved by `build`
    saved = json.loads(words_file.read_text(encoding="utf-8")) if words_file.exists() else None
    words = [tuple(w) for w in saved["words"]] if saved else captions.words_from_script(
        spans, [g["narration"] for g in segs])
    style = captions.CaptionStyle(1080, 1920, shorts=True)
    clean = Path(pkg.get("build", {}).get("clean") or ctx.settings.project_dir(video_id) / "clean.mp4")
    cast = any(g.get("scene") for g in segs)  # drawn scenes keep their figures in the middle: zoom in
    made, info, attempts, chosen = [], [], [], []
    for i, j in ranked:  # a Short must pass its own review; a failing run is replaced by the next-best one
        if len(made) == count or len(attempts) >= MAX_ATTEMPTS:
            break
        if any(not (j < a or i > b) for a, b in chosen):
            continue
        n = len(made) + 1
        start, end = spans[i][0], spans[j][1]
        hook = hook_text(segs[i])  # a title over the first seconds: the Short opens on its point
        ass = captions.write_ass(out / f"short_{n}.ass", words, style, window=(start, end),
                                 chapters=[(start, hook)] if hook else None)
        dest = out / f"short_{n}.mp4"
        ff.run(ff.vertical_cmd(clean, start, end - start, dest, ass, zoom=cast), f"cutting Short {n}")
        verdict = shorts_review.review_short(dest, segs[i:j + 1], pkg.get("characters"),
                                             ass.read_text(encoding="utf-8"), hook)
        attempts.append({"segments": [i + 1, j + 1], "ok": verdict["ok"], "issues": verdict["issues"]})
        if not verdict["ok"]:
            typer.secho(f"Short from segments {i + 1}-{j + 1} failed its review ({'; '.join(verdict['issues'][:3])}); "
                        "trying the next run.", fg=typer.colors.YELLOW)
            continue
        chosen.append((i, j))
        made.append(dest)
        info.append({"file": str(dest), "start": round(start, 2), "end": round(end, 2),
                     "segments": [i + 1, j + 1], "chapter": segs[i].get("chapter", ""), "title": hook,
                     "review": {"ok": True, "facts": verdict["facts"]}})
    for extra in out.glob("short_*"):  # leftovers of a run that failed its review
        m = re.match(r"short_(\d+)\.", extra.name)
        if m and int(m.group(1)) > len(made):
            extra.unlink()
    (out / "shorts_review.json").write_text(json.dumps({"accepted": info, "attempts": attempts}, indent=2),
                                            encoding="utf-8")
    if len(made) < 2:
        raise StageError("Fewer than 2 Shorts passed their review.",
                         "; ".join(f"segments {a['segments']}: {', '.join(a['issues'][:2])}" for a in attempts[:4]),
                         "Fix those problems in the script or scenes (the retention review lists them), rebuild, and "
                         "run `shorts` again.")
    pkg["shorts"] = info
    write_package(ctx, video_id, pkg)
    typer.echo(f"Cut {len(made)} Shorts into {out}")
    return made
