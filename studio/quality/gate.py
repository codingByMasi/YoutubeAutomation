"""Pre-publish quality gate: scores script, hook, pacing, visuals, audio and metadata; blocks or warns.

`evaluate` is pure (package + measured audio in, report out). `run` wires it to a video and its channel.
The gate never publishes and never replaces the typed `yes`; it can only add reasons to stop.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from studio.context import Ctx
from studio.quality import growth, profiles, rules
from studio.stages.qa import CTA_WORDS, HOOK_TRIGGERS, TEASER, WEAK_OPENERS, segment_flags
from studio.stages.script import banned_in, pacing_warnings, timeline, validate_package, validate_title
from studio.stages.visuals import chart_gaps

PAYOFF = re.compile(r"\b(by the end|you(?:'ll| will) (?:know|see|learn|understand)|here'?s (?:how|why|where)|"
                    r"let me show|we'?ll (?:find|see))\b", re.I)
PENALTY = {"critical": 45, "major": 22, "minor": 8}
LOCK_BELOW = 35  # any dimension under this blocks, whatever the average


def _issue(dim: str, severity: str, text: str, fix: str = "") -> dict:
    return {"dimension": dim, "severity": severity, "text": text, "fix": fix}


def _dur(seg: dict) -> float:
    return float(seg.get("real_seconds") or seg.get("est_seconds") or 0)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def check_script(pkg: dict, t: dict) -> list[dict]:
    segs = pkg.get("segments") or []
    out = []
    if not segs:
        return [_issue("script", "critical", "The script has no segments.", "Run `script` first.")]
    for p in validate_package(pkg):
        if "banned" in p or "source" in p:
            out.append(_issue("script", "critical", p, "Fix the script before publishing."))
    narration = " ".join(s["narration"] for s in segs)
    sents = [s for g in segs for s in _sentences(g["narration"])]
    avg = sum(len(s.split()) for s in sents) / max(len(sents), 1)
    if avg > t["sentence_max_words"]:
        out.append(_issue("script", "major", f"Sentences average {avg:.0f} words (limit {t['sentence_max_words']}).",
                          "Split long sentences: write for the ear."))
    if t["needs_sources"] and not pkg.get("sources"):
        out.append(_issue("script", "critical", "No sources listed.", "Every figure needs a source."))
    loops = sum(bool(TEASER.search(g["narration"])) or bool(g.get("open_loop")) for g in segs[:-1])
    if len(segs) >= 6 and loops < t["min_open_loops"]:
        out.append(_issue("script", "minor", f"Only {loops} open loop(s); aim for {t['min_open_loops']}+.",
                          "Plant a teaser early and pay it off later."))
    if t["needs_cta"]:
        last = segs[-1]["narration"]
        if not CTA_WORDS.search(last):
            out.append(_issue("script", "major", "No call to action in the last segment.",
                              "Ask one concrete question and name the next video."))
        elif "?" not in last and not re.search(r"\bnext video\b", last, re.I):
            out.append(_issue("script", "minor", "The call to action is generic.",
                              "Tie it to this topic: a specific question or the next video."))
    if banned_in(narration):
        out.append(_issue("script", "critical", f"Banned phrase in narration: {banned_in(narration)[0]!r}.",
                          "Reword it."))
    return out


def check_hook(pkg: dict, t: dict) -> list[dict]:
    segs = pkg.get("segments") or []
    if not segs:
        return []
    hook = segs[0]["narration"]
    first_sentence = (_sentences(hook) or [hook])[0]
    first_two = " ".join(_sentences(hook)[:2])
    out = []
    if WEAK_OPENERS.match(hook):
        out.append(_issue("hook", "critical", "The hook opens with a greeting or 'in this video'.",
                          "Start on the problem, the number or the contradiction."))
    elif not HOOK_TRIGGERS.search(first_two):
        out.append(_issue("hook", "major", "No question, number or contrast in the first two sentences.",
                          "Open with a specific figure, a contradiction or a question the viewer cannot answer yet."))
    if _dur(segs[0]) > t["hook_max_seconds"]:
        out.append(_issue("hook", "major", f"The hook runs {_dur(segs[0]):.0f}s (limit {t['hook_max_seconds']:g}s).",
                          "Cut the setup; state the payoff sooner."))
    if len(first_sentence.split()) > t["hook_first_sentence_words"]:
        out.append(_issue("hook", "minor", f"The first sentence has {len(first_sentence.split())} words "
                          f"(limit {t['hook_first_sentence_words']}).", "Make the first sentence shorter."))
    if t["needs_cta"] and not PAYOFF.search(hook):
        out.append(_issue("hook", "minor", "The hook never promises a payoff.",
                          "Add a line such as 'by the end you will know ...'."))
    if not pkg.get("hook_type") and t["needs_cta"]:
        out.append(_issue("hook", "minor", "hook_type is not recorded.", "Name the hook formula used."))
    return out


def check_pacing(pkg: dict, t: dict) -> list[dict]:
    segs = pkg.get("segments") or []
    out = []
    spans = timeline(segs, "real_seconds" if all(s.get("real_seconds") for s in segs) else "est_seconds")
    total = spans[-1][1] if spans else 0
    if total < t["min_minutes"] * 60:
        out.append(_issue("pacing", "major", f"Length {total / 60:.1f} min is under {t['min_minutes']:g} min.",
                          "Add depth, not filler."))
    last = 0.0
    for (start, _), seg in zip(spans, segs):
        if seg.get("beat") or seg.get("chart_data"):
            if start - last > t["beat_gap_max"]:
                out.append(_issue("pacing", "major", f"{start - last:.0f}s without a retention beat or chart "
                                  f"before {start / 60:.1f} min (limit {t['beat_gap_max']:g}s).",
                                  "Add a question, reveal, example or chart there."))
            last = start
    if total - last > t["beat_gap_max"]:
        out.append(_issue("pacing", "minor", f"{total - last:.0f}s without a beat at the end.", "Add a closing beat."))
    for w in pacing_warnings(segs):
        if "chart" in w:
            out.append(_issue("pacing", "minor", w, "Add a chart or number card."))
    return out


def check_visuals(pkg: dict, t: dict) -> list[dict]:
    segs = pkg.get("segments") or []
    if not any(g.get("visual") for g in segs):
        return [_issue("visuals", "minor", "Visuals have not been chosen yet, so they were not scored.",
                       "Run `visuals` and re-check before review.")]
    out = []
    cards = sum((g.get("visual") or {}).get("kind") == "card" for g in segs)
    if segs and cards / len(segs) > t["card_share_max"]:
        out.append(_issue("visuals", "major", f"{cards} of {len(segs)} segments are plain cards "
                          f"(limit {t['card_share_max'] * 100:.0f}%).",
                          "Add a free PIXABAY_API_KEY or use more concrete visual_keywords."))
    kinds = {(g.get("visual") or {}).get("kind") for g in segs} - {None}
    if len(segs) > 5 and len(kinds) < 2:
        out.append(_issue("visuals", "minor", "Every segment uses the same kind of picture.",
                          "Mix photos, clips, charts and diagrams."))
    flagged = 0
    for pos, seg in enumerate(segs, 1):
        flags = [f for f in segment_flags(pos, seg) if "plain title card" not in f]
        flagged += bool(flags)
        for f in flags[:1]:
            out.append(_issue("visuals", "minor", f"Segment {pos}: {f}", "Add keywords or split the segment."))
    if segs and flagged / len(segs) > 0.4:
        out.append(_issue("visuals", "major", f"{flagged} of {len(segs)} segments look repetitive or flat.",
                          "Broaden visual_keywords and re-run `visuals`."))
    for w in chart_gaps(segs):
        out.append(_issue("visuals", "minor", w, "Add a chart where the numbers are."))
    return out


def measure_audio(path: Path) -> dict | None:
    """Integrated loudness (LUFS) and true peak (dBTP) of a file via ffmpeg's ebur128, or None if unmeasurable."""
    exe = shutil.which("ffmpeg")
    if not exe or not path.exists():
        return None
    cmd = [exe, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    tail = r.stderr.split("Summary:")[-1]
    lufs = re.search(r"I:\s+(-?\d+\.?\d*)\s+LUFS", tail)
    peak = re.search(r"Peak:\s+(-?\d+\.?\d*)\s+dBFS", tail)
    if not lufs:
        return None
    return {"lufs": float(lufs.group(1)), "true_peak": float(peak.group(1)) if peak else None}


def check_audio(pkg: dict, t: dict, audio: dict | None) -> list[dict]:
    out = []
    build = pkg.get("build") or {}
    if audio is None:
        return [_issue("audio", "minor", "Audio was not measured (no built video or no ffmpeg).",
                       "Run `build`, then re-check.")]
    gap = audio["lufs"] - t["lufs_target"]
    if abs(gap) > t["lufs_tolerance"]:
        out.append(_issue("audio", "major", f"Loudness {audio['lufs']:.1f} LUFS is {abs(gap):.1f} from the "
                          f"{t['lufs_target']:g} target.", "Re-run `build --force` (it normalises loudness)."))
    if audio.get("true_peak") is not None and audio["true_peak"] > -1.0:
        out.append(_issue("audio", "major", f"True peak {audio['true_peak']:.1f} dB risks clipping.",
                          "Rebuild; lower the music or the limiter ceiling."))
    if build and not build.get("music") and t["needs_cta"] is False:
        out.append(_issue("audio", "minor", "No music bed in a kids video.", "Add a track to assets/music."))
    return out


def check_metadata(pkg: dict, t: dict, thumb: Path | None) -> list[dict]:
    out = []
    pick = next((x["text"] for x in pkg.get("titles", []) if x.get("is_pick")), "")
    for p in validate_title(pick):
        out.append(_issue("metadata", "critical", p, "Pick a different title."))
    if len(pkg.get("tags", [])) < t["min_tags"]:
        out.append(_issue("metadata", "minor", f"Only {len(pkg.get('tags', []))} tags (want {t['min_tags']}+).",
                          "Add topical tags."))
    if len((pkg.get("description_summary") or "").strip()) < 80:
        out.append(_issue("metadata", "major", "The description summary is missing or very short.",
                          "Write 2-3 sentences with the main keyword up front."))
    if not (pkg.get("thumbnail_texts") or []):
        out.append(_issue("metadata", "minor", "No thumbnail text options.", "Add 1-3 word thumbnail texts."))
    if thumb is not None and not thumb.exists():
        out.append(_issue("metadata", "major", f"Thumbnail {thumb.name} is missing.", "Run `thumbnail`."))
    named = sum(bool((g.get("chapter") or "").strip()) for g in pkg.get("segments", []))
    if named < 3:
        out.append(_issue("metadata", "minor", "Fewer than 3 named chapters.", "Name each part for YouTube chapters."))
    return out


def evaluate(pkg: dict, ctype: str = profiles.DEFAULT_TYPE, tuning: dict | None = None,
             audio: dict | None = None, thumb: Path | None = None, peers: list[tuple[str, dict]] | None = None,
             in_series: bool | None = None) -> dict:
    """Score a package. Returns {score, verdict (pass|warn|block), dimensions, issues, channel_type, thresholds}."""
    t = profiles.thresholds(ctype, tuning)
    checks = {"script": check_script(pkg, t), "hook": check_hook(pkg, t), "pacing": check_pacing(pkg, t),
              "visuals": check_visuals(pkg, t), "audio": check_audio(pkg, t, audio),
              "metadata": check_metadata(pkg, t, thumb), "fit": growth.check_fit(pkg, t),
              "packaging": growth.check_packaging(pkg, t, in_series),
              "originality": growth.check_originality(pkg, t, peers)}
    dims, issues = {}, []
    for name, found in checks.items():
        dims[name] = max(0, 100 - sum(PENALTY[i["severity"]] for i in found))
        issues += found
    weights = t["weights"]
    score = round(sum(dims[d] * weights[d] for d in dims) / sum(weights.values()))
    blocked = score < t["block_below"] or min(dims.values()) < LOCK_BELOW
    verdict = "block" if blocked else "pass" if score >= t["pass_at"] and not any(
        i["severity"] != "minor" for i in issues) else "warn"
    return {"score": score, "verdict": verdict, "dimensions": dims, "issues": issues, "channel_type": ctype,
            "tuning": {k: t[k] for k in profiles.TUNABLE}}


def blocking_reasons(report: dict) -> list[str]:
    """What to show when the verdict is block: critical issues first, then the major ones."""
    ranked = sorted(report["issues"], key=lambda i: list(PENALTY).index(i["severity"]))
    return [f"[{i['dimension']}] {i['text']}" + (f" Fix: {i['fix']}" if i["fix"] else "")
            for i in ranked if i["severity"] != "minor"][:8]


def _peers(ctx: Ctx, video_id: int, limit: int = 10) -> list[tuple[str, dict]]:
    """The channel's other recent scripted videos, for the originality check. Unreadable ones are skipped."""
    from studio import scope
    from studio.stages.script import load_package
    out = []
    for v in sorted(scope.videos(ctx.session).all(), key=lambda v: -v.id):
        if v.id == video_id:
            continue
        try:
            out.append((f"video #{v.id}", load_package(ctx, v.id)))
        except Exception:  # noqa: BLE001 - a video without a script just is not a peer
            continue
        if len(out) >= limit:
            break
    return out


def check_video(ctx: Ctx, video_id: int, thumb: int = 1) -> dict:
    """Evaluate a video against its channel's type and learned rules; writes projects/<id>/gate.json."""
    from studio.growth import channels, series
    from studio.stages.base import get_video
    from studio.stages.script import load_package
    get_video(ctx.session, video_id)
    root = ctx.settings.root
    out = ctx.settings.project_dir(video_id)
    ctype = profiles.channel_type(channels.get(root))
    report = evaluate(load_package(ctx, video_id), ctype, rules.tuning(rules.load(root)),
                      audio=measure_audio(out / "final.mp4"), thumb=out / "thumbs" / f"thumb_{thumb}.jpg",
                      peers=_peers(ctx, video_id), in_series=series.position(root, video_id) is not None)
    report["video_id"] = video_id
    (out / "gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def show(report: dict, echo=print) -> None:
    """Print a gate report."""
    echo(f"Quality gate ({profiles.TYPES[report['channel_type']]['label']}): "
         f"{report['score']}/100 -> {report['verdict'].upper()}")
    echo("  " + "  ".join(f"{d} {s}" for d, s in report["dimensions"].items()))
    for i in report["issues"]:
        echo(f"  - [{i['dimension']}/{i['severity']}] {i['text']}" + (f" Fix: {i['fix']}" if i["fix"] else ""))


def run(ctx: Ctx, video_id: int, thumb: int = 1, echo=print) -> dict:
    """`gate`: check a video and print the verdict."""
    report = check_video(ctx, video_id, thumb)
    show(report, echo)
    return report
