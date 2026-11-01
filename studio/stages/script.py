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

BANNED_PHRASES = ["you won't believe", "shocking", "guaranteed", "secret they don't want you to know", "get rich"]
CHART_TYPES = {"bar", "pie", "line", "flow", "number"}
BEATS = {"question", "reveal", "example", "pattern_break"}
TITLE_MAX = 70
TITLE_COUNT = 15
HOOK_MAX_SECONDS = 15
BEAT_GAP_MAX = 40
CHART_GAP_MAX = 90
LENGTH_RANGE_MIN = (10, 15)  # typical range for the prompt; only a too-short video is warned about
MIN_WARN_MINUTES = 5          # no maximum length
DEFAULT_BRIEF = "Business-model and economics explainers, English, faceless narration with charts."
DEFAULT_STYLE = "Clear, curious, analytical, no hype. Show the money with a chart for every major figure."


# ---------- validation (pure functions, unit tested) ----------
def banned_in(text: str) -> list[str]:
    low = text.lower().replace("’", "'")
    return [p for p in BANNED_PHRASES if p in low]


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
    if len(titles) != TITLE_COUNT:
        problems.append(f"need exactly {TITLE_COUNT} titles, got {len(titles)}")
    for t in titles:
        problems += validate_title(str(t.get("text", "")))
    picks = sum(bool(t.get("is_pick")) for t in titles)
    if picks != 1:
        problems.append(f"exactly one title must have is_pick=true, got {picks}")
    return problems


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
    refs = chart.get("source_ids") or []
    if not refs:
        problems.append(f"{where}: chart has no source (every figure needs a source)")
    for r in refs:
        if r not in source_ids:
            problems.append(f"{where}: chart cites unknown source id {r!r}")
    return problems


def validate_package(d: dict) -> list[str]:
    """Hard problems that make a script package unusable."""
    problems = validate_titles(d.get("titles") or [])
    sources = d.get("sources") or []
    source_ids = {str(s.get("id")) for s in sources}
    for s in sources:
        if not s.get("url_or_note"):
            problems.append(f"source {s.get('id')!r} has no url_or_note")
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
    if segs and isinstance(segs[0].get("est_seconds"), (int, float)) and segs[0]["est_seconds"] > HOOK_MAX_SECONDS:
        problems.append(f"segment 1 is the hook and must be at most {HOOK_MAX_SECONDS}s")
    if d.get("sensitive_topic") and not sources:
        problems.append("finance/health/legal/news topics must list sources")
    if not str(d.get("originality_note", "")).strip():
        problems.append("originality_note is empty: say what this video adds")
    if not str(d.get("cta", "")).strip():
        problems.append("cta is empty")
    texts = d.get("thumbnail_texts") or []
    if len(texts) != 3 or any(not 1 <= len(str(t).split()) <= 5 for t in texts):
        problems.append("thumbnail_texts must be 3 strings of 1-5 words")
    return problems


def timeline(segs: list[dict], key: str = "est_seconds") -> list[tuple[float, float]]:
    """(start, end) seconds for each segment, using real_seconds when present."""
    t, out = 0.0, []
    for s in segs:
        dur = float(s.get("real_seconds") or s.get(key) or 0)
        out.append((t, t + dur))
        t += dur
    return out


def pacing_warnings(segs: list[dict], key: str = "est_seconds") -> list[str]:
    """Soft checks: total length, gaps between retention beats and between charts."""
    warns = []
    spans = timeline(segs, key)
    total = spans[-1][1] if spans else 0
    if total < MIN_WARN_MINUTES * 60:
        warns.append(f"total length {total / 60:.1f} min is under {MIN_WARN_MINUTES} min (no maximum is enforced)")
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


def _spec_section(root: Path, number: int, default: str) -> str:
    spec = root / "SPEC.md"
    if not spec.exists():
        return default
    text = spec.read_text(encoding="utf-8")
    m = re.search(rf"^## {number}\..*?$(.*?)(?=^## \d+\.|\Z)", text, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else default


NO_OUTLINE = "(No outline was made for this video: design the hook, open loops and beat order yourself.)"


def prompt_text(name: str) -> str:
    """Text of studio/prompts/<name>.md."""
    return (Path(__file__).parent.parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def build_prompt(root: Path, topic: str, outline: dict | None = None) -> str:
    lo, hi = LENGTH_RANGE_MIN
    return prompt_text("script").format(
        topic=topic, brief=_brief(root), style=_spec_section(root, 9, DEFAULT_STYLE),
        banned=", ".join(f'"{p}"' for p in BANNED_PHRASES), min_minutes=lo, max_minutes=hi,
        hooks=prompt_text("hooks"),
        outline=json.dumps(outline, indent=2, ensure_ascii=False) if outline else NO_OUTLINE)


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
            lines.append(f"Chart ({c['type']}): {c.get('title', '')} [{', '.join(c['source_ids'])}]")
        lines.append("")
    lines += ["## Sources", ""] + [f"- [{s['id']}] {s.get('title', '')}: {s['url_or_note']}" for s in d["sources"]]
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


def load_package(ctx: Ctx, video_id: int) -> dict:
    p = ctx.settings.project_dir(video_id) / "script.json"
    if not p.exists():
        raise StudioError(f"{p} not found.", "The script stage has not produced it.", "Run `script <idea_id>` first.")
    return json.loads(p.read_text(encoding="utf-8"))


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


def run(ctx: Ctx, idea_id: int, force: bool = False) -> Video:
    video = video_for_idea(ctx, idea_id)
    topic = ctx.session.get(Idea, idea_id).topic

    def work() -> None:
        from studio.stages.qa import quality_report
        from studio.stages.story import load_outline
        out_dir = ctx.settings.project_dir(video.id)
        d = ask_json(ctx.settings, out_dir, "script",
                     build_prompt(ctx.settings.root, topic, load_outline(out_dir)),
                     validate=validate_package, force=False)
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
