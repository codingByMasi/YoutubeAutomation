"""Story engine: story_plan -> script -> story_review, three handoff tasks, all checks in code.

Every task is resumable: re-running the same command reads its response file (or stops with the exact next
step). Progress lives in projects/<id>/story_state.json so a rerun skips finished tasks.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import InvalidAnswer, PendingLLMResponse, StageError, StudioError
from studio.llm import ask_json, pending_task, prompt_paths
from studio.models import Idea, Video
from studio.stages.base import get_video, stage_index
from studio.story import facts as facts_mod
from studio.story import hooks as hooks_mod
from studio.story import ledger, loops
from studio.story import models as M
from studio.story import profile as sp
from studio.story import prompts

STATE = "story_state.json"
PASS_AVG, PASS_MIN = 4.2, 3
MAX_REVIEW_ROUNDS = 2  # the first review plus at most one automatic repeat


# ---------- state ----------
def load_state(out: Path) -> dict:
    p = out / STATE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"plan": "todo", "script": "todo",
                                                                          "review": "todo", "rounds": []}


def save_state(out: Path, st: dict) -> None:
    (out / STATE).write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- task 1: story_plan ----------
def _outline_for_checks(plan: dict, prof: dict, ranked: list[dict]) -> dict:
    """The plan's outline in the shape the legacy outline validator checks (3 hooks, one picked; sources)."""
    o = dict(plan["outline"])
    top = ranked[:3]
    o["hooks"] = [{"formula": h["hook_type"], "line": h["line"], "why": h.get("why", ""), "pick": i == 0}
                  for i, h in enumerate(top)]
    o["sources"] = [{"id": f["id"], "title": f["claim"][:60], "url_or_note": f.get("source_url") or "estimate"}
                    for f in plan["facts"]]
    o["thumbnail_ideas"] = (o.get("thumbnail_ideas") or [])[:3]
    while len(o["thumbnail_ideas"]) < 3:
        o["thumbnail_ideas"].append(o.get("title_promise", "why")[:30])
    for lp in o.get("loops", []):
        lp.setdefault("question", lp.get("id", ""))
    return o


def validate_plan(d: dict, prof: dict, root: Path | None = None, video_id: int | None = None) -> list[str]:
    """Rules for the story_plan answer (shape is checked by Pydantic before this runs)."""
    from studio.stages.story import validate_outline
    problems: list[str] = []
    needs_facts = sp.enabled(prof, "fact_ledger")
    if needs_facts:
        problems += facts_mod.validate_facts(d.get("facts"))
        if len(d.get("facts") or []) < 4:
            problems.append("give at least 4 facts, each with source_url and quote_snippet (use web search)")
        ids = {str(f.get("id")) for f in d.get("facts") or []}
        for b in (d.get("outline") or {}).get("beats", []):
            for fid in b.get("fact_ids") or []:
                if fid not in ids:
                    problems.append(f"beat {b.get('n')}: fact id {fid!r} is not in facts")
    problems += hooks_mod.validate_variants(d.get("hooks"), prof)
    if problems:
        return problems
    recent = ledger.recent_hook_types(root, 3, video_id) if root and sp.enabled(prof, "hook_rotation") else []
    ranked = hooks_mod.rank(d["hooks"], recent, prof)
    if all(h["blocked"] for h in ranked):
        problems.append(f"every hook uses a formula from the channel's last videos ({', '.join(recent)}); "
                        f"add variants using: {', '.join(set(prof['hook_formulas']) - set(recent))}")
    o = d["outline"]
    ids = [lp.get("id") for lp in o.get("loops", [])]
    if len(ids) != len(set(ids)):
        problems.append("loop ids must be unique")
    problems += validate_outline(_outline_for_checks(d, prof, ranked), prof if prof.get("kids") else None)
    return problems


def run_plan(ctx: Ctx, video: Video, force: bool = False, fetch=None) -> dict:
    """Task 1. On success writes facts.json (verified), hooks.json (ranked), outline.json (with the chosen hook)."""
    from studio.stages.script import _brief, _spec_section, DEFAULT_STYLE
    root, out = ctx.settings.root, ctx.settings.project_dir(video.id)
    topic = ctx.session.get(Idea, video.idea_id).topic
    prof = sp.for_channel(root)
    prompt = prompts.compose(
        "story_plan", prof, topic=topic, brief=_brief(root), style=_spec_section(root, 9, DEFAULT_STYLE),
        audience=prof["audience"], language=prof["language"], region=prof["region"],
        beat_sheet=" > ".join(prof["beat_sheet"]), hook_formulas=", ".join(prof["hook_formulas"]),
        hook_words=8 if prof.get("kids") else 12, fact_count="2-4 counting facts at most" if prof.get("kids") else "8-14",
        facts_note=("Kids: facts are optional; use counting numbers only and leave `source_url` empty with "
                    "`is_estimate` true." if not sp.enabled(prof, "fact_ledger") else ""),
        recent=ledger.prompt_text(root, exclude_video=video.id) if sp.enabled(prof, "repetition_ledger")
        else "(not tracked)", learned=_learned(ctx), competitors=_competitors(ctx))
    d = ask_json(ctx.settings, out, "story_plan", prompt, model=M.StoryPlan,
                 validate=lambda x: validate_plan(x, prof, root, video.id), force=force, handoff_only=True)
    recent = ledger.recent_hook_types(root, 3, video.id) if sp.enabled(prof, "hook_rotation") else []
    best, ranked = hooks_mod.pick_best(d["hooks"], recent, prof)
    (out / "hooks.json").write_text(json.dumps({"chosen": best, "variants": ranked, "avoided": recent}, indent=2,
                                               ensure_ascii=False), encoding="utf-8")
    facts = facts_mod.verify_all(d["facts"], fetch or facts_mod.default_fetcher, out / "facts_cache")
    old = {f["id"]: f for f in facts_mod.load_facts(out)}
    for f in facts:  # an owner's manual accept survives a re-verify
        if old.get(f["id"], {}).get("status") == "manual":
            f["status"] = "manual"
    facts_mod.save_facts(out, facts)
    outline = dict(d["outline"], chosen_hook=best, hook_type=best["hook_type"])
    (out / "outline.json").write_text(json.dumps(outline, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Plan OK: {facts_mod.summary(facts)}. Hook ({best['hook_type']}, score {best['total']}): "
               f"{best['line']}")
    if recent:
        typer.echo(f"Hook rotation: avoided {', '.join(recent)} (the channel's last videos).")
    for f in facts:
        if f["status"] != "verified" and f["status"] != "manual":
            typer.secho(f"  {f['id']} {f['status']}: {f.get('note', '')} -- {f['claim'][:60]}",
                        fg=typer.colors.YELLOW)
    if any(f["status"] in ("unverified", "unfetchable") for f in facts):
        typer.echo(f"Fix a fact: open its source and fix the answer, or accept it yourself with "
                   f"`facts {video.id} --accept <id>` (Facts page in the app).")
    return outline


def _learned(ctx: Ctx) -> str:
    try:
        from studio.story import feedback_loop
        return feedback_loop.prompt_text(ctx.settings.root)
    except Exception:  # noqa: BLE001 - optional context, never blocks the plan
        return "(not enough real videos yet)"


def _competitors(ctx: Ctx) -> str:
    try:
        from studio.story import feedback_loop
        return feedback_loop.competitor_text(ctx.settings.root)
    except Exception:  # noqa: BLE001
        return "(none)"


def accept_fact(ctx: Ctx, video_id: int, fact_id: str) -> None:
    """Owner vouches for a fact the code could not verify (paywall, PDF): status becomes 'manual'."""
    out = ctx.settings.project_dir(video_id)
    facts = facts_mod.load_facts(out)
    hit = [f for f in facts if str(f["id"]) == fact_id]
    if not hit:
        raise StudioError(f"No fact {fact_id!r} for video {video_id}.", "", f"Known ids: {[f['id'] for f in facts]}")
    hit[0]["status"], hit[0]["note"] = "manual", "accepted by the owner"
    facts_mod.save_facts(out, facts)


# ---------- task 3: story_review ----------
def swipe_seconds(pkg: dict, segment: int) -> int:
    return round(loops.starts(pkg.get("segments") or [])[max(0, min(segment, len(pkg["segments"])) - 1)])


def validate_review(d: dict, pkg: dict, prof: dict, facts: list[dict] | None, criteria: list[str],
                    must_fix: list[str] | None = None) -> list[str]:
    from studio.stages.script import normalize_package, validate_package
    problems: list[str] = []
    for c in criteria:
        if not isinstance(d["scores"].get(c), int) or not 0 <= d["scores"][c] <= 5:
            problems.append(f"scores.{c} must be an integer 0-5")
    sw = d["swipe_points"]
    if not 3 <= len(sw) <= 5:
        problems.append(f"swipe_points needs 3-5 moments, got {len(sw)}")
    segs = pkg.get("segments") or []
    revised = d["revised"]
    normalize_package(revised)
    rsegs = revised.get("segments") or []
    for i, s in enumerate(sw, 1):
        n = s["segment"]
        if not 1 <= n <= len(segs):
            problems.append(f"swipe_points[{i}].segment {n} is not a segment of the draft (1-{len(segs)})")
            continue
        text = str(segs[n - 1].get("narration", ""))
        if s["quote"].strip().lower() not in text.lower():
            problems.append(f"swipe_points[{i}].quote is not word-for-word in segment {n}: {s['quote'][:50]!r}")
        elif any(s["quote"].strip().lower() in str(r.get("narration", "")).lower() for r in rsegs):
            problems.append(f"swipe_points[{i}]: the quoted line is still in the rewrite ({s['quote'][:50]!r}); "
                            "the rewrite must fix every swipe-away moment")
    problems += [f"revised package: {p}" for p in validate_package(revised, prof, facts)]
    return problems + [f"still failing from round 1: {m}" for m in (must_fix or [])
                       if m in "\n".join(problems)]


def deterministic_issues(pkg: dict, ctx: Ctx, video_id: int) -> list[dict]:
    """Major/critical gate issues in script, hook, pacing and originality for the (revised) package."""
    from studio.quality import gate, profiles
    from studio.growth import channels
    root = ctx.settings.root
    ctype = profiles.channel_type(channels.get(root))
    rep = gate.evaluate(pkg, ctype, peers=gate._peers(ctx, video_id), story_profile=sp.for_channel(root))
    return [i for i in rep["issues"] if i["dimension"] in ("script", "hook", "pacing", "originality")
            and i["severity"] in ("major", "critical")]


def run_review(ctx: Ctx, video: Video, force: bool = False) -> dict:
    """Task 3 (+ at most one automatic repeat when deterministic checks still fail)."""
    from studio.stages.script import load_package, replace_package
    from studio.stages.story import criteria_for, score_skeleton
    out = ctx.settings.project_dir(video.id)
    prof = sp.for_channel(ctx.settings.root)
    crit = criteria_for(prof["pack"])
    st = load_state(out)
    if st["review"] == "done" and not force:
        typer.echo(f"Video {video.id}: story review already applied ({len(st['rounds'])} round(s)).")
        return st
    facts = facts_mod.load_facts(out) or None
    api = ctx.settings.llm_critic_provider  # optional: only this task may use an API provider
    rnd = len(st["rounds"]) + 1
    while rnd <= MAX_REVIEW_ROUNDS:
        pkg = load_package(ctx, video.id)
        clean = {k: v for k, v in pkg.items() if k not in ("build", "shorts", "visual_rejects")}
        for s in clean["segments"]:
            s.pop("visual", None)
        prior = st["rounds"][-1]["remaining"] if st["rounds"] else []
        det = ("\nThe previous rewrite STILL fails these automatic checks; fix them all:\n- " + "\n- ".join(prior)
               if prior else "")
        prompt = prompts.compose(
            "story_review", prof, topic=pkg.get("topic", ""), hook_words=8 if prof.get("kids") else 12,
            sentence_cap=prof["sentence_max_words"], wps=prof["wps"],
            extra_criteria="\n".join(f"- `{c}`: {CRITERIA_HELP.get(c, c)}" for c in crit[10:]),
            facts=prompts.j(facts_mod.prompt_view(facts or [])), package=prompts.j(clean),
            score_skeleton=score_skeleton(prof["pack"]), deterministic=det)
        task = "story_review" if rnd == 1 else f"story_review_r{rnd}"
        d = ask_json(ctx.settings, out, task, prompt, model=M.StoryReview, force=force and rnd == 1,
                     validate=lambda x, pkg=pkg: validate_review(x, pkg, prof, facts, crit, prior),
                     api_provider=api or None)
        scores = {c: d["scores"][c] for c in crit}
        avg = sum(scores.values()) / len(scores)
        swipes = [{**s, "at_seconds": swipe_seconds(pkg, s["segment"])} for s in d["swipe_points"]]
        replace_package(ctx, video, d["revised"])
        remaining = [f"[{i['dimension']}] {i['text']}" for i in deterministic_issues(d["revised"], ctx, video.id)]
        passed = avg >= PASS_AVG and min(scores.values()) >= PASS_MIN and not remaining
        st["rounds"].append({"round": rnd, "avg": round(avg, 2), "min": min(scores.values()), "scores": scores,
                             "swipe_points": swipes, "verdict": d["verdict"], "fixes": d.get("fixes", []),
                             "remaining": remaining, "draft_passed": passed})
        typer.secho(f"Story review round {rnd}: average {avg:.1f}/5, lowest {min(scores.values())}. "
                    f"{d['verdict']}", fg=typer.colors.GREEN if passed else typer.colors.YELLOW)
        for s in swipes:
            typer.echo(f"  swipe-away at {s['at_seconds'] // 60}:{s['at_seconds'] % 60:02d}  \"{s['quote'][:70]}\"")
        if remaining:
            typer.secho("  checks still failing after the rewrite:", fg=typer.colors.YELLOW)
            for r in remaining[:6]:
                typer.echo(f"    - {r}")
        if not remaining or rnd >= MAX_REVIEW_ROUNDS:
            break
        save_state(out, st)
        rnd += 1
    st["review"] = "done"
    save_state(out, st)
    (out / "story_review.json").write_text(json.dumps(st["rounds"], indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        record_ledger(ctx, video)
    except Exception:  # noqa: BLE001 - the ledger must never break the pipeline
        pass
    return st


CRITERIA_HELP = {
    "number_accuracy": "every figure traces to a fact id and is worded as the fact says; estimates sound like estimates",
    "actionability": "the viewer leaves with one thing to check, compare or do; not-financial-advice in plain words",
    "accuracy": "dates, names and numbers match the facts; disputed points marked; graphic events wordsafe",
    "dread": "tension builds slowly, reveals land suddenly, chapters end on cliffhangers",
    "simplicity": "tiny vocabulary, repetition, call-and-response, a counting moment",
    "safety": "nothing scary, violent or unsafe to imitate; no links, brands or personal-info asks",
}


def record_ledger(ctx: Ctx, video: Video) -> None:
    from studio.stages.script import load_package
    out = ctx.settings.project_dir(video.id)
    pkg = load_package(ctx, video.id)
    outline = json.loads((out / "outline.json").read_text(encoding="utf-8")) if (out / "outline.json").exists() else None
    ledger.record(ctx.settings.root, ledger.entry_from_package(pkg, outline, video.id))


# ---------- orchestration ----------
def command_for(task: str, video: Video) -> str:
    return {"story_plan": f"script {video.idea_id} --auto", "script": f"script {video.idea_id} --auto",
            "story_review": f"script {video.idea_id} --auto"}.get(task, f"script {video.idea_id} --auto")


def auto(ctx: Ctx, video: Video, force: bool = False, fetch=None) -> None:
    """Run story_plan -> script -> story_review. Raises PendingLLMResponse at each handoff (re-run to continue)."""
    from studio.stages import script as script_stage
    out = ctx.settings.project_dir(video.id)
    st = load_state(out)
    if force:
        st = {"plan": "todo", "script": "todo", "review": "todo", "rounds": []}
    if st["plan"] != "done":
        run_plan(ctx, video, force=force, fetch=fetch)
        st["plan"] = "done"
        save_state(out, st)
    outline = json.loads((out / "outline.json").read_text(encoding="utf-8"))
    if st["script"] != "done":
        script_stage.run_engine_script(ctx, video, outline, force=force)
        st["script"] = "done"
        save_state(out, st)
    if sp.enabled(sp.for_channel(ctx.settings.root), "story_review"):
        if st["review"] != "done":
            run_review(ctx, video, force=force)
    else:
        st["review"] = "done"
        save_state(out, st)
    typer.echo(f"Story engine done for video {video.id}. Next: voice {video.id}")


def next_step(ctx: Ctx, video_id: int) -> tuple[str, str]:
    """(what is pending, exact command to run) for a video."""
    video = get_video(ctx.session, video_id)
    out = ctx.settings.project_dir(video_id)
    st = load_state(out)
    prof = sp.for_channel(ctx.settings.root)
    if stage_index(video.stage) >= stage_index("scripted") and st["review"] == "done":
        from studio.stages.base import STAGES, STAGE_COMMAND
        nxt = STAGES[stage_index(video.stage) + 1] if stage_index(video.stage) + 1 < len(STAGES) else None
        return ("nothing pending in the story engine",
                f"{STAGE_COMMAND.get(nxt, 'status')} {video_id}" if nxt else "status")
    for task, key in (("story_plan", "plan"), ("script", "script"), ("story_review", "review")):
        if st[key] == "done" or (key == "review" and not sp.enabled(prof, "story_review")):
            continue
        name = task
        if task == "story_review" and st["rounds"]:
            name = f"story_review_r{len(st['rounds']) + 1}"
        state = pending_task(out, name)
        pf, rf = prompt_paths(out, name)
        if state == "waiting":
            return (f"{task}: answer {pf.as_posix()} and write {rf.as_posix()}",
                    f"then run: script {video.idea_id} --auto")
        return (f"{task}: not started", f"script {video.idea_id} --auto")
    return ("nothing pending", f"voice {video_id}")
