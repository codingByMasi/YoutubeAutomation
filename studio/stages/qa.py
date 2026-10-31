"""`qa`: flag weak spots (retention, visuals, ending) before the owner reviews the video. Read-only, never blocks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from studio.context import Ctx
from studio.stages.base import get_video
from studio.stages.script import load_package, pacing_warnings, timeline
from studio.stages.timing import shot_max_for, shots_needed, split_segment
from studio.stages.visuals import chart_gaps

WEAK_OPENERS = re.compile(r"^\s*(hey|hi|hello|welcome|in this video|today we|today i|so today|what'?s up|"
                          r"before we (start|begin)|don'?t forget to)", re.I)
HOOK_TRIGGERS = re.compile(r"\?|\d|\$|€|£|₹|\b(never|nobody|secret|actually|really|but|except|instead)\b", re.I)
TEASER = re.compile(r"\b(but first|in a moment|later in this video|by the end|we'?ll (get|come) to|"
                    r"stay with me|here'?s the (catch|twist)|that(?:'s| is) not (even )?(the|where)|"
                    r"the real reason)\b", re.I)
CTA_WORDS = re.compile(r"\b(subscribe|comment|next video|watch next|follow|let me know|tell me)\b", re.I)
LONG_SEGMENT = 35.0
MAX_SENTENCE_WORDS = 22
MAX_CARD_SHARE = 0.3


def _dur(seg: dict) -> float:
    return float(seg.get("real_seconds") or seg.get("est_seconds") or 0)


def segment_flags(pos: int, seg: dict) -> list[str]:
    """Problems with one segment's visuals and pacing."""
    flags = []
    vis = seg.get("visual") or {}
    if vis.get("kind") == "card":
        flags.append("no real picture found: plain title card on screen")
    paths = vis.get("paths") or []
    bg_s, _ = split_segment(_dur(seg), bool(seg.get("chart_data")))
    needed = shots_needed(bg_s, shot_max=shot_max_for(pos))
    if vis.get("kind") != "card" and needed >= 3 and len(set(paths)) * 2 < needed:
        flags.append(f"only {len(set(paths))} different picture(s) for {needed} shots: it will look repetitive")
    if _dur(seg) > LONG_SEGMENT and not seg.get("beat") and not seg.get("chart_data"):
        flags.append(f"{_dur(seg):.0f}s with no retention beat or chart: split it or add a turn")
    return flags


def quality_report(pkg: dict) -> dict:
    """{score, warnings, segments} for a script package (visuals optional: only checked when present)."""
    segs = pkg.get("segments") or []
    warnings: list[str] = []
    per_seg: dict[int, list[str]] = {}
    if segs:
        hook = segs[0]["narration"]
        first = " ".join(re.split(r"(?<=[.!?])\s+", hook)[:2])
        if WEAK_OPENERS.match(hook):
            warnings.append("Hook opens with a greeting or 'in this video': start on the problem or the number.")
        elif not HOOK_TRIGGERS.search(first):
            warnings.append("Hook has no question, number or contrast in its first two sentences.")
        if _dur(segs[0]) > 15:
            warnings.append(f"Hook is {_dur(segs[0]):.0f}s: it should be 15s or less.")
        loops = sum(bool(TEASER.search(g["narration"])) or bool(g.get("open_loop")) for g in segs[:-1])
        if len(segs) >= 6 and loops < 2:
            warnings.append(f"Only {loops} open loop(s) (teasers that pay off later): aim for 2 or more.")
        if not CTA_WORDS.search(segs[-1]["narration"]):
            warnings.append("The last segment has no clear call to action (subscribe, comment, next video).")
        sentences = [s for g in segs for s in re.split(r"(?<=[.!?])\s+", g["narration"]) if s.strip()]
        avg = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        if avg > MAX_SENTENCE_WORDS:
            warnings.append(f"Sentences average {avg:.0f} words: spoken scripts work best under {MAX_SENTENCE_WORDS}.")
    warnings += pacing_warnings(segs)
    warnings += chart_gaps(segs) if any(g.get("visual") for g in segs) else []
    cards = 0
    for pos, seg in enumerate(segs, 1):
        flags = segment_flags(pos, seg)
        cards += (seg.get("visual") or {}).get("kind") == "card"
        if flags:
            per_seg[pos] = flags
    if segs and cards / len(segs) > MAX_CARD_SHARE:
        warnings.append(f"{cards} of {len(segs)} segments are plain cards. Add a PIXABAY_API_KEY (free) for photos "
                        "and footage, or use more concrete visual_keywords.")
    if pkg.get("visual_rejects"):
        warnings.append(f"{len(pkg['visual_rejects'])} stock candidates were rejected by the quality gate "
                        "(corrupt, too small, blurry, portrait or duplicate).")
    for pos, flags in per_seg.items():
        warnings += [f"Segment {pos} ({(segs[pos - 1].get('chapter') or '')[:30]}): {f}" for f in flags]
    score = max(0, 100 - 8 * len(warnings))
    spans = timeline(segs)
    return {"score": score, "warnings": warnings, "segments": {str(k): v for k, v in per_seg.items()},
            "minutes": round(spans[-1][1] / 60, 1) if spans else 0}


def write_report(out: Path, report: dict) -> Path:
    path = out / "qa.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def run(ctx: Ctx, video_id: int) -> dict:
    """Print the quality report for a video (works after `script`; visuals checks appear after `visuals`)."""
    get_video(ctx.session, video_id)
    report = quality_report(load_package(ctx, video_id))
    write_report(ctx.settings.project_dir(video_id), report)
    colour = typer.colors.GREEN if report["score"] >= 80 else typer.colors.YELLOW
    typer.secho(f"Quality score {report['score']}/100 for {report['minutes']} min.", fg=colour)
    for w in report["warnings"]:
        typer.secho(f"  - {w}", fg=typer.colors.YELLOW)
    if not report["warnings"]:
        typer.echo("  No weak spots found.")
    return report
