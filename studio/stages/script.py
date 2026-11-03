"""`script`: titles, full script and segment list via the LLM wrapper, validated against the style guide."""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StudioError
from studio.llm import ask_json
from studio.models import Idea, Script, Segment, Title, Video
from studio.stages.base import run_stage
from studio.story.banned import BANNED_PHRASES  # noqa: E402,F401  (re-exported: other modules import it here)
from studio.story.banned import banned_in as _banned_in  # noqa: E402
from studio.util.logging import get_logger

log = get_logger("script")

CHART_TYPES = {"bar", "pie", "line", "flow", "number"}
BEATS = {"question", "reveal", "example", "pattern_break"}
# Beats the model tends to invent -> the allowed beat they mean. None = plain explanation (no retention interrupt).
BEAT_ALIASES: dict[str, str | None] = {
    "explain": None, "explanation": None, "explainer": None, "exposition": None, "setup": None, "context": None,
    "recap": None, "summary": None, "transition": None, "cta": None, "outro": None, "intro": None,
    "story": "example", "anecdote": "example", "analogy": "example", "comparison": "example",
    "twist": "pattern_break", "reversal": "pattern_break", "catch": "pattern_break", "surprise": "reveal",
    "number": "reveal", "stat": "reveal", "hook": "question", "teaser": "question", "payoff": "reveal",
    "explains": None, "explaining": None, "explained": None, "tell": None, "telling": None, "narrate": None,
    "narration": None, "describe": None, "description": None, "detail": None, "details": None, "define": None,
    "definition": None, "background": None, "overview": None, "conclusion": None, "none": None, "null": None,
    "plain": None, "normal": None, "neutral": None, "step": None, "fact": "reveal", "facts": "reveal",
    "data": "reveal", "statistic": "reveal", "figure": "reveal", "insight": "reveal", "revelation": "reveal",
    "answer": "reveal", "ask": "question", "questions": "question", "cliffhanger": "question",
    "curiosity_gap": "question", "open_loop": "question", "case_study": "example", "examples": "example",
    "illustration": "example", "scenario": "example", "demo": "example", "interrupt": "pattern_break",
    "pattern_interrupt": "pattern_break", "patternbreak": "pattern_break", "break": "pattern_break",
    "contrast": "pattern_break", "turn": "pattern_break", "plot_twist": "pattern_break",
}
ILLUSTRATIVE_WORDS = ("made-up", "made up", "illustration", "illustrative", "hypothetical", "for example only")
TITLE_MAX = 70
TITLE_COUNT = 15
TITLE_MIN = 10  # a reply with 10-14 titles is usable; more than TITLE_COUNT is trimmed
HOOK_MAX_SECONDS = 15
BEAT_GAP_MAX = 40
CHART_GAP_MAX = 90
# Length numbers live in the channel's story profile (studio/story/profile.py). These are only fallbacks for
# callers that have no profile (older tests, the kids song path).
LENGTH_RANGE_MIN = (8, 12)
MIN_WARN_MINUTES = 6
DEFAULT_BRIEF = "Business-model and economics explainers, English, faceless narration with charts."
DEFAULT_STYLE = "Clear, curious, analytical, no hype. Show the money with a chart for every major figure."


# ---------- validation (pure functions, unit tested) ----------
def banned_in(text: str) -> list[str]:
    """Banned phrases in text (the shared list lives in studio/story/banned.py)."""
    return _banned_in(text)


def validate_title(text: str) -> list[str]:
    """Problems with one title: length, banned phrases, all-caps shouting."""
    problems = []
    if not text.strip():
        problems.append("title is empty")
    if len(text) >= TITLE_MAX:
        problems.append(f"title is {len(text)} chars (must be under {TITLE_MAX}): {text!r}")
    for p in banned_in(text):
        problems.append(f"title uses banned phrase {p!r}: {text!r}")
    if any(len(w) > 3 and w.isupper() for w in re.findall(r"[A-Za-z]+", text)):
        problems.append(f"title has an ALL-CAPS word: {text!r}")
    return problems


def validate_titles(titles: list[dict]) -> list[str]:
    problems = []
    if not titles:
        problems.append("the reply has no titles; add at least one")
    for t in titles:
        problems += validate_title(str(t.get("text", "")))
    picks = sum(bool(t.get("is_pick")) for t in titles)
    if picks != 1:
        problems.append(f"exactly one title must have is_pick=true, got {picks}")
    return problems


def chart_needs_source(chart: dict) -> bool:
    """False for concept diagrams (a flow with no numbers) and charts labelled as made-up teaching examples."""
    if chart.get("type") == "flow" and not chart.get("values"):
        return False
    parts = [chart.get("title", ""), chart.get("unit", ""), *(chart.get("labels") or [])]
    text = " ".join(str(x) for x in parts).lower()
    return not any(w in text for w in ILLUSTRATIVE_WORDS)


def _beat_key(beat: str) -> str:
    return re.sub(r"[\s\-/]+", "_", beat.strip().lower()).strip("_.:")


def normalize_beat(beat: object) -> str | None:
    """Map any beat value to an allowed beat or None. Unknown words count as a plain explanation (None)."""
    if not isinstance(beat, str):
        return None
    key = _beat_key(beat)
    if key in BEATS:
        return key
    if key in BEAT_ALIASES:
        return BEAT_ALIASES[key]
    for part in key.split("_"):  # e.g. 'explain_question' / 'reveal+example': keep the first allowed word
        if part in BEATS:
            return part
    return None


def _fix_titles(d: dict) -> list[str]:
    """Trim extra titles and make exactly one title the pick."""
    titles = d.get("titles")
    if not isinstance(titles, list) or not all(isinstance(t, dict) for t in titles):
        return []
    notes = []
    picks = [i for i, t in enumerate(titles) if t.get("is_pick")]
    if len(titles) > TITLE_COUNT:
        keep = picks[0] if picks and picks[0] >= TITLE_COUNT else None
        notes.append(f"titles: kept {TITLE_COUNT} of {len(titles)}")
        titles[:] = titles[:TITLE_COUNT - 1] + [titles[keep]] if keep is not None else titles[:TITLE_COUNT]
        picks = [i for i, t in enumerate(titles) if t.get("is_pick")]
    if titles and len(picks) != 1:
        for t in titles:
            t["is_pick"] = False
        titles[picks[0] if picks else 0]["is_pick"] = True
        notes.append("titles: marked one title as the pick")
    return notes


def _fix_thumbnail_texts(d: dict) -> list[str]:
    """Keep at most 3 thumbnail texts of at most 5 words each."""
    texts = d.get("thumbnail_texts")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list):
        return []
    fixed = [" ".join(str(t).split()[:5]) for t in texts if str(t).strip()][:3]
    if fixed == texts:
        return []
    d["thumbnail_texts"] = fixed
    return ["thumbnail_texts: trimmed to 3 texts of at most 5 words"]


def _fix_est_seconds(d: dict, wps: float) -> list[str]:
    """Claude cannot count words, so est_seconds is recomputed from the narration whenever it is far off."""
    notes = []
    for i, seg in enumerate(d.get("segments") or [], 1):
        if not isinstance(seg, dict):
            continue
        n = len(str(seg.get("narration", "")).split())
        est = seg.get("est_seconds")
        if n < 3:
            continue
        right = round(n / wps, 1)
        if not isinstance(est, (int, float)) or est <= 0 or not 0.75 <= right / est <= 1.33:
            seg["est_seconds"] = right
            notes.append(f"segment {i}: est_seconds set to {right:g} to match its {n} words")
    return notes


def normalize_package(d: dict, wps: float = 2.5) -> list[str]:
    """Fix harmless near-misses in place (beats, titles, thumbnail texts, est_seconds). Returns a note per change."""
    notes = []
    for i, seg in enumerate(d.get("segments") or [], 1):
        if not isinstance(seg, dict) or "beat" not in seg:
            continue
        beat = seg["beat"]
        if beat is None or beat in BEATS:
            continue
        new = normalize_beat(beat)
        seg["beat"] = new
        notes.append(f"segment {i}: beat {beat!r} is not a retention beat; "
                     + (f"changed to {new!r}" if new else "treated as a plain explanation (no beat)"))
    return notes + _fix_titles(d) + _fix_thumbnail_texts(d) + _fix_est_seconds(d, wps)


def match_plan_hook(d: dict, outline: dict) -> list[str]:
    """Set hook_type to the plan's hook when it is missing or only differs in spelling (case, spaces, dashes)."""
    want = outline.get("hook_type")
    if not want:
        return []
    got = d.get("hook_type")
    key = lambda x: re.sub(r"[\s\-]+", "_", str(x).strip().lower())  # noqa: E731
    if got and key(got) != key(want):
        return []  # a genuinely different hook is reported by the caller
    if got == want:
        return []
    d["hook_type"] = want
    return [f"hook_type: set to the plan's hook {want!r}"]


def validate_chart(chart: dict, source_ids: set[str], where: str) -> list[str]:
    problems = []
    ctype = chart.get("type")
    labels, values = chart.get("labels") or [], chart.get("values") or []
    if ctype not in CHART_TYPES:
        problems.append(f"{where}: chart type {ctype!r} not in {sorted(CHART_TYPES)}")
    if ctype in {"bar", "pie", "line"} and (not labels or len(labels) != len(values)):
        problems.append(f"{where}: {ctype} chart needs equal-length labels and values")
    if ctype == "flow" and len(labels) < 2:
        problems.append(f"{where}: flow chart needs at least 2 labels")
    if ctype == "number" and (len(labels) != 1 or len(values) != 1):
        problems.append(f"{where}: number card needs one label and one value")
    if not all(isinstance(v, (int, float)) for v in values):
        problems.append(f"{where}: chart values must be numbers")
    return problems


def validate_package(d: dict, profile: dict | None = None, facts: list[dict] | None = None) -> list[str]:
    """Hard problems that make a script package unusable. Near-miss beats are fixed first, on every path.

    With a story `profile` the channel-type checks run too (word counts, sentence rules, open-loop ids); with
    `facts` (the verified ledger) every figure and chart value must trace to a fact id."""
    normalize_package(d)
    problems = validate_titles(d.get("titles") or [])
    sources = d.get("sources") or []
    source_ids = {str(s.get("id")) for s in sources}
    segs = d.get("segments") or []
    if len(segs) < 5:
        problems.append(f"need at least 5 segments, got {len(segs)}")
    for i, seg in enumerate(segs, 1):
        where = f"segment {i}"
        if not str(seg.get("narration", "")).strip():
            problems.append(f"{where}: narration is empty")
        if not seg.get("visual_keywords"):
            problems.append(f"{where}: visual_keywords is empty")
        if not isinstance(seg.get("est_seconds"), (int, float)) or seg["est_seconds"] <= 0:
            problems.append(f"{where}: est_seconds must be a positive number")
        if seg.get("beat") not in (None, *BEATS):
            problems.append(f"{where}: beat {seg.get('beat')!r} not in {sorted(BEATS)}")
        for p in banned_in(str(seg.get("narration", ""))):
            problems.append(f"{where}: narration uses banned phrase {p!r}")
        if seg.get("chart_data"):
            problems += validate_chart(seg["chart_data"], source_ids, where)
        if seg.get("scene"):
            from studio.scenes import validate_scene
            problems += validate_scene(seg["scene"], where, seg, source_ids)
    if segs and isinstance(segs[0].get("est_seconds"), (int, float)) and max(
            segs[0]["est_seconds"], len(str(segs[0].get("narration", "")).split()) / 2.5) > HOOK_MAX_SECONDS:
        problems.append(f"segment 1 is the hook and must be at most {HOOK_MAX_SECONDS}s")
    if not str(d.get("originality_note", "")).strip():
        problems.append("originality_note is empty: say what this video adds")
    if not str(d.get("cta", "")).strip():
        problems.append("cta is empty")
    texts = d.get("thumbnail_texts") or []
    if len(texts) != 3 or any(not 1 <= len(str(t).split()) <= 5 for t in texts):
        problems.append("thumbnail_texts must be 3 strings of 1-5 words")
    if profile is not None and segs:
        from studio.story import checks, loops
        from studio.story.profile import enabled
        problems += checks.profile_problems(d, profile)
        from studio.story import photo as story_photo
        problems += story_photo.photo_problems(segs)
        if enabled(profile, "visual_intent"):
            from studio.story import visuals as story_visuals
            problems += story_visuals.shot_problems(segs)
        if enabled(profile, "loop_ids"):
            problems += loops.loop_problems(d, profile)
    return problems


def soft_warnings(d: dict, facts: list[dict] | None = None) -> list[str]:
    """Advice that never blocks a script (today: fewer than 15 titles).

    Scripts carry no sources or fact ids, so nothing is traced to facts.json; old fields are simply ignored."""
    out = []
    n = len(d.get("titles") or [])
    if 0 < n < TITLE_COUNT:
        out.append(f"only {n} titles (15 are recommended); the best one is used")
    return out


def timeline(segs: list[dict], key: str = "est_seconds") -> list[tuple[float, float]]:
    """(start, end) seconds for each segment, using real_seconds when present."""
    t, out = 0.0, []
    for s in segs:
        dur = float(s.get("real_seconds") or s.get(key) or 0)
        out.append((t, t + dur))
        t += dur
    return out


def pacing_warnings(segs: list[dict], key: str = "est_seconds", min_minutes: float | None = None) -> list[str]:
    """Soft checks: total length, gaps between retention beats and between charts."""
    min_minutes = MIN_WARN_MINUTES if min_minutes is None else min_minutes
    warns = []
    spans = timeline(segs, key)
    total = spans[-1][1] if spans else 0
    if total < min_minutes * 60:
        warns.append(f"total length {total / 60:.1f} min is under {min_minutes:g} min")
    for label, field, gap_max in (("retention beat", "beat", BEAT_GAP_MAX), ("chart", "chart_data", CHART_GAP_MAX)):
        last = 0.0
        for (start, _), seg in zip(spans, segs):
            if seg.get(field):
                if start - last > gap_max:
                    warns.append(f"{start - last:.0f}s without a {label} before {start / 60:.1f} min")
                last = start
        if total - last > gap_max:
            warns.append(f"{total - last:.0f}s without a {label} at the end")
    return warns


# ---------- prompt ----------
def _brief(root: Path) -> str:
    """The active channel's brief if the owner customised it, else SPEC section 1."""
    from studio.growth import channels
    from studio.quality import rules
    return (channels.brief(root) or _spec_section(root, 1, DEFAULT_BRIEF)) + rules.lessons_text(root)


def _style(root: Path, prof: dict) -> str:
    """Style guide for the channel's pack (SPEC section 9 only for the finance pack)."""
    from studio.story import style
    return style.for_profile(prof, _spec_section(root, 9, DEFAULT_STYLE))


def _spec_section(root: Path, number: int, default: str) -> str:
    spec = root / "SPEC.md"
    if not spec.exists():
        return default
    text = spec.read_text(encoding="utf-8")
    m = re.search(rf"^## {number}\..*?$(.*?)(?=^## \d+\.|\Z)", text, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else default


NO_OUTLINE = "(No outline was made for this video: design the hook, open loops and beat order yourself.)"


def prompt_text(name: str, pack: str = "explainer") -> str:
    """Text of studio/prompts/<pack>/<name>.md; a pack without that file falls back to studio/prompts/<name>.md."""
    from studio.story import prompts
    return prompts.read(name, pack)


def build_prompt(root: Path, topic: str, outline: dict | None = None, facts: list[dict] | None = None) -> str:
    """Script prompt for the active channel's pack. `outline` is the plan (outline + chosen hook) when given."""
    from studio.story import ledger, prompts
    from studio.story import profile as sp
    prof = sp.for_channel(root)
    return prompts.compose(
        "script", prof, topic=topic, brief=_brief(root), style=_style(root, prof),
        outline=prompts.j(outline) if outline else NO_OUTLINE,
        facts_block="(not used)", facts="(not used)",
        recent=ledger.prompt_text(root) if sp.enabled(prof, "repetition_ledger") else "(not tracked)",
        plan=prompts.j(outline) if outline else NO_OUTLINE)


# ---------- outputs ----------
def render_markdown(d: dict) -> str:
    """Human-readable script.md from the package."""
    lines = [f"# {next(t['text'] for t in d['titles'] if t.get('is_pick'))}", "", f"Topic: {d.get('topic', '')}",
             "", f"Originality: {d.get('originality_note', '')}", "", "## Title options", ""]
    lines += [f"- {'**PICK** ' if t.get('is_pick') else ''}{t['text']} ({len(t['text'])} chars, {t.get('style', '')})"
              for t in d["titles"]]
    lines += ["", "## Script", ""]
    for (start, _), seg in zip(timeline(d["segments"]), d["segments"]):
        lines.append(f"### [{int(start // 60)}:{int(start % 60):02d}] {seg.get('chapter', '')}")
        if seg.get("beat"):
            lines.append(f"_Beat: {seg['beat']}_")
        lines += ["", seg["narration"], "", f"Visuals: {', '.join(seg['visual_keywords'])}"]
        if seg.get("chart_data"):
            c = seg["chart_data"]
            lines.append(f"Chart ({c['type']}): {c.get('title', '')}")
        lines.append("")
    if d.get("sources"):  # old scripts only; new ones carry no sources
        lines += ["## Sources", ""] + [f"- [{s.get('id', '')}] {s.get('title', '')}: {s.get('url_or_note', '')}"
                                      for s in d["sources"]]
    return "\n".join(lines) + "\n"


def save_package(ctx: Ctx, video: Video, d: dict) -> None:
    """Write script.md/script.json and replace titles, script and segment rows for the video."""
    s, out = ctx.session, ctx.settings.project_dir(video.id)
    json_path, md_path = out / "script.json", out / "script.md"
    json_path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(d), encoding="utf-8")
    prev = s.query(Script).filter(Script.video_id == video.id).count()
    for model in (Title, Segment):
        s.query(model).filter(model.video_id == video.id).delete()
    for t in d["titles"]:
        s.add(Title(video_id=video.id, text=t["text"], style=t.get("style", ""), length=len(t["text"]),
                    is_pick=bool(t.get("is_pick"))))
    words = sum(len(seg["narration"].split()) for seg in d["segments"])
    s.add(Script(video_id=video.id, markdown_path=str(md_path), json_path=str(json_path), word_count=words,
                 version=prev + 1))
    for i, seg in enumerate(d["segments"], 1):
        s.add(Segment(video_id=video.id, position=i, narration=seg["narration"],
                      visual_keywords=", ".join(seg["visual_keywords"]), est_seconds=float(seg["est_seconds"])))


def replace_package(ctx: Ctx, video: Video, revised: dict) -> int:
    """Atomically swap a video's script for `revised`: one DB transaction, files restored on any failure.

    Keeps `script.original.json` (first draft, written once) and a numbered history `script.v1.json`, `v2`...
    holding each package that was replaced. Returns the history number written."""
    out = ctx.settings.project_dir(video.id)
    old = json.loads((out / "script.json").read_text(encoding="utf-8"))
    old_md = (out / "script.md").read_text(encoding="utf-8") if (out / "script.md").exists() else None
    if not (out / "script.original.json").exists():
        (out / "script.original.json").write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")
    n = 1
    while (out / f"script.v{n}.json").exists():
        n += 1
    (out / f"script.v{n}.json").write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        save_package(ctx, video, revised)
        ctx.session.flush()
        ctx.session.commit()
    except Exception:
        ctx.session.rollback()
        (out / "script.json").write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")
        if old_md is not None:
            (out / "script.md").write_text(old_md, encoding="utf-8")
        raise
    return n


def load_package(ctx: Ctx, video_id: int) -> dict:
    p = ctx.settings.project_dir(video_id) / "script.json"
    if not p.exists():
        raise StudioError(f"{p} not found.", "The script stage has not produced it.", "Run `script <idea_id>` first.")
    return tolerant_package(json.loads(p.read_text(encoding="utf-8")))


def tolerant_package(pkg: dict) -> dict:
    """Make an old or hand-pasted script.json safe to use without losing anything.

    Segments become dicts (bare text becomes its narration); a segment missing `est_seconds` or `visual_keywords`
    gets them from its words and chapter; chart_data/visual must be dicts and scene a dict or a cast-scene name.
    A value of the wrong type is moved to the segment's `_unreadable` map (kept in the file, a warning is logged)
    instead of being deleted, so saving the package back never destroys what the owner pasted."""
    if not isinstance(pkg, dict):
        return {"segments": []}
    segs = pkg.get("segments")
    out = []
    for i, g in enumerate(segs if isinstance(segs, list) else [], 1):
        if isinstance(g, str):
            g = {"narration": g}
        if not isinstance(g, dict):
            log.warning("script.json: segment %d is not text or an object; it was ignored", i)
            continue
        g = dict(g)
        for k in ("chart_data", "visual", "scene"):
            ok = (dict, str) if k == "scene" else dict
            if k in g and g[k] is not None and not isinstance(g[k], ok):
                g.setdefault("_unreadable", {})[k] = g.pop(k)
                log.warning("script.json: segment %d has an unreadable %s; kept aside under _unreadable", i, k)
            elif k in g and g[k] is None and k != "scene":
                g.pop(k)
        words = str(g.get("narration", "")).split()
        if not isinstance(g.get("est_seconds"), (int, float)) or g["est_seconds"] <= 0:
            if words:
                g["est_seconds"] = round(max(len(words) / 2.5, 1.0), 1)
        if not g.get("visual_keywords") and (g.get("chapter") or words):
            g["visual_keywords"] = [str(g.get("chapter") or " ".join(words[:3]))]
        out.append(g)
    return {**pkg, "segments": out}


def write_package(ctx: Ctx, video_id: int, d: dict) -> None:
    (ctx.settings.project_dir(video_id) / "script.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def video_for_idea(ctx: Ctx, idea_id: int) -> Video:
    idea = ctx.session.get(Idea, idea_id)
    if idea is None:
        raise StudioError(f"Idea {idea_id} not found.", "", "Run `research` and use an ID from the table.")
    v = ctx.session.query(Video).filter(Video.idea_id == idea_id).first()
    if v is None:
        raise StudioError(f"Idea {idea_id} is not approved yet.", "", f"Run `approve-idea {idea_id}` first.")
    return v


def run_engine_script(ctx: Ctx, video: Video, outline: dict, force: bool = False) -> Video:
    """Task 2 of the story engine: the script, written to the plan and checked against facts, loops and rotation."""
    from studio.stages.qa import quality_report
    from studio.story import facts as facts_mod
    from studio.story import hooks as hooks_mod
    from studio.story import models as M
    from studio.story import profile as sp
    topic = ctx.session.get(Idea, video.idea_id).topic
    out_dir = ctx.settings.project_dir(video.id)
    prof = sp.for_channel(ctx.settings.root)
    facts = facts_mod.load_facts(out_dir) or None
    loop_ids = {str(lp.get("id")) for lp in outline.get("loops", [])}
    notes: list[str] = []

    def check(data: dict) -> list[str]:
        notes.clear()
        notes.extend(normalize_package(data, float(prof["wps"])))
        notes.extend(match_plan_hook(data, outline))
        problems = validate_package(data, prof, facts)
        if data.get("hook_type") and data["hook_type"] != outline.get("hook_type"):
            problems.append(f"hook_type must be {outline.get('hook_type')!r} (the plan's chosen hook), "
                            f"got {data.get('hook_type')!r}")
        if sp.enabled(prof, "hook_rotation"):
            msg = hooks_mod.rotation_problem(str(data.get("hook_type", "")), ctx.settings.root, 3, video.id)
            if msg:
                problems.append(msg)
        for i, seg in enumerate(data.get("segments") or [], 1):
            for key in ("plants_loop", "pays_loop"):
                v = seg.get(key)
                for lid in ([] if not v else v if isinstance(v, list) else [v]):
                    if loop_ids and str(lid) not in loop_ids:
                        problems.append(f"segment {i}: {key} {lid!r} is not a loop id in the plan {sorted(loop_ids)}")
        return problems

    def work() -> None:
        d = ask_json(ctx.settings, out_dir, "script", build_prompt(ctx.settings.root, topic, outline, facts),
                     validate=check, model=M.ScriptModel, force=False)
        d["engine"] = True  # marks a story-engine script (the gate applies the strict story checks)
        d.setdefault("hook_type", outline.get("hook_type", ""))
        d.setdefault("arc", outline.get("arc") if isinstance(outline.get("arc"), str) else "")
        for n in notes:
            typer.secho(f"auto-fixed: {n}", fg=typer.colors.YELLOW)
        save_package(ctx, video, d)
        from studio.story import checks as story_checks
        for w in soft_warnings(d, facts) + story_checks.style_notes(d, prof) + quality_report(d)["warnings"]:
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)

    r = run_stage(ctx.session, video, "scripted", work, force)
    typer.echo(r.message)
    return video


def run(ctx: Ctx, idea_id: int, force: bool = False, auto: bool = False, fetch=None) -> Video:
    """`script`. With auto=True runs the story engine (story_plan -> script -> story_review)."""
    video = video_for_idea(ctx, idea_id)
    if auto:
        from studio.story import engine
        engine.auto(ctx, video, force=force, fetch=fetch)
        return video
    topic = ctx.session.get(Idea, idea_id).topic

    def work() -> None:
        from studio.stages.qa import quality_report
        from studio.stages.story import load_outline
        out_dir = ctx.settings.project_dir(video.id)
        notes: list[str] = []

        def check(data: dict) -> list[str]:
            notes.clear()
            notes.extend(normalize_package(data))
            return validate_package(data)

        d = ask_json(ctx.settings, out_dir, "script",
                     build_prompt(ctx.settings.root, topic, load_outline(out_dir)),
                     validate=check, force=False)
        for n in notes:
            typer.secho(f"auto-fixed: {n}", fg=typer.colors.YELLOW)
        save_package(ctx, video, d)
        for w in quality_report(d)["warnings"]:
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)
        typer.echo(f"Tip: run `critique {video.id}` for a scored review and rewrite before voicing.")

    if force:
        # A forced re-run asks for a fresh answer: archive the old one so it is not silently reused.
        resp = ctx.settings.project_dir(video.id) / "prompts" / "script.response.json"
        if resp.exists() and video.stage != "approved":
            resp.rename(resp.with_suffix(f".v{ctx.session.query(Script).filter_by(video_id=video.id).count()}.json"))
    r = run_stage(ctx.session, video, "scripted", work, force)
    typer.echo(r.message + (f" Next: voice {video.id}" if r.ran else ""))
    return video
