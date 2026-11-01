"""Story-side steps around the script: a retention outline before it, a scored critique and rewrite after it.

Both are optional and are not pipeline stages (they never block `voice`). They use the same prompt-file handoff
as `script`: the command writes `prompts/<task>.prompt.md`, Claude answers in `<task>.response.json`, re-run to apply.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StageError, StudioError
from studio.llm import ask_json, prompt_paths
from studio.models import Idea
from studio.stages.base import get_video, stage_index
from studio.stages.script import (
    BANNED_PHRASES,
    DEFAULT_STYLE,
    _brief,
    _spec_section,
    load_package,
    normalize_package,
    prompt_text,
    save_package,
    validate_package,
    write_package,
)
from studio.util.answer_json import parse_answer

CRITERIA = ["hook", "stakes", "curiosity_loops", "pacing", "concreteness", "clarity", "story_arc",
            "payoff_ending", "originality", "trust"]
PASS_SCORE = 4
DEVICES = {"question", "reveal", "example", "pattern_break", "explain"}
HOOK_FORMULAS = {"number_stakes", "contradiction", "hidden_answer", "cold_open", "villain_system", "before_after",
                 "insider_view", "challenge_guess"}


# ---------- outline ----------
def validate_outline(d: dict) -> list[str]:
    """Problems that make a retention outline unusable."""
    problems = []
    for key in ("audience_question", "big_idea", "promise", "title_promise"):
        if not str(d.get(key, "")).strip():
            problems.append(f"{key} is empty")
    hooks = d.get("hooks") or []
    if len(hooks) != 3 or sum(bool(h.get("pick")) for h in hooks) != 1:
        problems.append("need exactly 3 hooks with exactly one pick=true")
    for h in hooks:
        if h.get("formula") not in HOOK_FORMULAS:
            problems.append(f"hook formula {h.get('formula')!r} not in {sorted(HOOK_FORMULAS)}")
        first = str(h.get("line", "")).replace("?", ".").replace("!", ".").split(".")[0]
        if len(first.split()) > 14:
            problems.append(f"hook first sentence is {len(first.split())} words (12 or fewer): {first[:50]!r}")
    beats = d.get("beats") or []
    if not 10 <= len(beats) <= 18:
        problems.append(f"need 10-18 beats, got {len(beats)}")
    flat = 0
    clock, last_interrupt = 0.0, 0.0
    for b in beats:
        if b.get("device") not in DEVICES:
            problems.append(f"beat {b.get('n')}: device {b.get('device')!r} not in {sorted(DEVICES)}")
        if not isinstance(b.get("seconds"), (int, float)) or not 8 <= b["seconds"] <= 30:
            problems.append(f"beat {b.get('n')}: seconds must be 8-30")
            continue
        if not str(b.get("key_fact", "")).strip():
            problems.append(f"beat {b.get('n')}: key_fact is empty (every beat needs a number or example)")
        flat = flat + 1 if b.get("device") == "explain" else 0
        if flat > 2:
            problems.append(f"beat {b.get('n')}: more than two explain beats in a row")
        if b.get("device") != "explain":
            last_interrupt = clock
        elif clock - last_interrupt > 40:
            problems.append(f"beat {b.get('n')}: {clock - last_interrupt:.0f}s since the last interrupt (max 40)")
        clock += b["seconds"]
    if beats and isinstance(beats[0].get("seconds"), (int, float)) and beats[0]["seconds"] > 15:
        problems.append("beat 1 is the hook: at most 15 seconds")
    loops = d.get("loops") or []
    if len(loops) < 3:
        problems.append("need at least 3 open loops")
    early = 0.0
    starts = {}
    for b in beats:
        starts[b.get("n")] = early
        early += b["seconds"] if isinstance(b.get("seconds"), (int, float)) else 0
    if sum(starts.get(lp.get("plant"), 1e9) <= 60 for lp in loops) < 2:
        problems.append("plant at least two open loops in the first 60 seconds")
    for lp in loops:
        if not (isinstance(lp.get("payoff"), int) and isinstance(lp.get("plant"), int) and lp["payoff"] > lp["plant"]):
            problems.append(f"loop {lp.get('question', '')[:40]!r}: payoff must come after plant")
    end = d.get("ending") or {}
    for key in ("callback", "takeaway", "cta_question", "next_video"):
        if not str(end.get(key, "")).strip():
            problems.append(f"ending.{key} is empty")
    if not d.get("sources"):
        problems.append("sources is empty")
    if len(d.get("thumbnail_ideas") or []) != 3:
        problems.append("need 3 thumbnail_ideas")
    return problems


def load_outline(work_dir: Path) -> dict | None:
    """The saved outline for a video, or None."""
    _, rf = prompt_paths(work_dir, "outline")
    if not rf.exists():
        return None
    try:
        return parse_answer(rf.read_text(encoding="utf-8"))
    except StudioError:
        return None


def run_outline(ctx: Ctx, idea_id: int, force: bool = False) -> dict:
    """Write the outline prompt (or validate its answer). Run before `script`."""
    from studio.stages.script import video_for_idea
    video = video_for_idea(ctx, idea_id)
    if stage_index(video.stage) > stage_index("approved") and not force:
        raise StageError(f"Video {video.id} already has a script (stage '{video.stage}').",
                         "The outline shapes the script, so it must come first.",
                         f"Use `critique {video.id}` to improve the existing script instead.")
    topic = ctx.session.get(Idea, idea_id).topic
    prompt = prompt_text("outline").format(
        topic=topic, brief=_brief(ctx.settings.root),
        style=_spec_section(ctx.settings.root, 9, DEFAULT_STYLE), hooks=prompt_text("hooks"))
    d = ask_json(ctx.settings, ctx.settings.project_dir(video.id), "outline", prompt,
                 validate=validate_outline, force=force)
    pick = next(h for h in d["hooks"] if h.get("pick"))
    typer.echo(f"Outline OK: {len(d['beats'])} beats, {len(d['loops'])} open loops. Hook ({pick['formula']}): "
               f"{pick['line']}")
    typer.echo(f"Next: script {idea_id} (the outline is added to the script prompt automatically).")
    return d


# ---------- critique and rewrite ----------
def validate_critique(d: dict) -> list[str]:
    problems = []
    scores = d.get("scores") or {}
    for c in CRITERIA:
        if not isinstance(scores.get(c), int) or not 0 <= scores[c] <= 5:
            problems.append(f"scores.{c} must be an integer 0-5")
    if not str(d.get("verdict", "")).strip():
        problems.append("verdict is empty")
    if not d.get("fixes"):
        problems.append("fixes is empty")
    revised = d.get("revised")
    if not isinstance(revised, dict):
        problems.append("revised must be the complete script package")
    else:
        normalize_package(revised)
        problems += [f"revised script: {p}" for p in validate_package(revised)]
    return problems


def run_critique(ctx: Ctx, video_id: int, force: bool = False) -> dict:
    """Write the critique prompt for the current script; on re-run print the scores and apply the rewrite."""
    video = get_video(ctx.session, video_id)
    if stage_index(video.stage) < stage_index("scripted"):
        raise StageError(f"Video {video_id} has no script yet (stage '{video.stage}').", "",
                         "Run `script <idea_id>` first.")
    if stage_index(video.stage) > stage_index("scripted"):
        raise StageError(f"Video {video_id} is already voiced (stage '{video.stage}').",
                         "A rewrite changes the narration, so the voice and everything after it would be stale.",
                         f"Re-run `script {video.idea_id} --force` then `critique {video_id}`, "
                         "or accept the current script.")
    out = ctx.settings.project_dir(video_id)
    if (out / "critique.json").exists() and not force:
        typer.echo(f"Video {video_id}: the critique rewrite is already applied. Use --force for another round.")
        return json.loads((out / "critique.json").read_text(encoding="utf-8"))
    pkg = load_package(ctx, video_id)
    topic = pkg.get("topic") or ctx.session.get(Idea, video.idea_id).topic
    clean = {k: v for k, v in pkg.items() if k not in ("build", "shorts", "visual_rejects")}
    for seg in clean["segments"]:
        seg.pop("visual", None)
    prompt = prompt_text("critique").format(
        topic=topic, hooks=prompt_text("hooks"), banned=", ".join(f'"{p}"' for p in BANNED_PHRASES),
        package=json.dumps(clean, indent=2, ensure_ascii=False))
    if force:
        (out / "critique.json").unlink(missing_ok=True)
    d = ask_json(ctx.settings, out, "critique", prompt, validate=validate_critique, force=force)
    scores = d["scores"]
    weak = [c for c in CRITERIA if scores[c] < PASS_SCORE]
    total = sum(scores.values())
    typer.secho(f"Critique of the first draft: {total}/{5 * len(CRITERIA)}. Weakest: "
                f"{', '.join(f'{c} {scores[c]}' for c in sorted(weak, key=scores.get)[:4]) or 'none'}.",
                fg=typer.colors.YELLOW if weak else typer.colors.GREEN)
    typer.echo(f"Verdict: {d['verdict']}")
    for f in d["fixes"][:10]:
        typer.echo(f"  - {f}")
    (out / "script.original.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")
    save_package(ctx, video, d["revised"])
    ctx.session.commit()
    write_package(ctx, video_id, d["revised"])
    (out / "critique.json").write_text(json.dumps({k: d[k] for k in ("scores", "verdict", "fixes")}, indent=2),
                                       encoding="utf-8")
    from studio.stages.qa import quality_report
    rep = quality_report(d["revised"])
    typer.echo(f"Rewrite applied (original kept as script.original.json). Quality score now {rep['score']}/100.")
    for w in rep["warnings"]:
        typer.secho(f"  - {w}", fg=typer.colors.YELLOW)
    typer.echo(f"Next: voice {video_id}")
    return d
