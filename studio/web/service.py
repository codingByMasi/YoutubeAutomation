"""Glue between the Streamlit UI and the existing stages. No Streamlit imports, so it is unit-tested."""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from studio import scope
from studio.context import Ctx, build_ctx
from studio.errors import InvalidAnswer, PendingLLMResponse, StudioError
from studio.llm import prompt_paths
from studio.models import Idea, Title, Video
from studio.stages.base import STAGES
from studio.util.answer_json import normalize_answer

# Settings that may come from Streamlit secrets or the Settings page (names match .env).
SECRET_KEYS = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", "LLM_PROVIDER", "LLM_API_KEY",
               "LLM_MODEL", "CHANNEL_ID", "TTS_PROVIDER", "TTS_VOICE", "FOOTAGE_PROVIDER", "IMAGE_PROVIDER",
               "GOOGLE_CLIENT_SECRET_PATH")
PRODUCE_STAGES = ["voice", "visuals", "build", "thumbnail"]
STAGE_LABEL = {"voice": "Voiceover", "visuals": "Footage, photos and charts", "build": "Edit the video",
               "thumbnail": "Thumbnails"}
_ANSWER_MARK = "\n---\n\n## How to answer"


@dataclass
class Outcome:
    """Result of running a stage: what it printed and, if it failed, the readable error."""

    ok: bool
    log: str
    error: str = ""
    pending: bool = False  # True when a prompt file was written and an answer is awaited
    problems: list[str] = field(default_factory=list)  # individual validation problems of a pasted answer
    answer: str = ""  # the rejected answer text, kept so it is never lost
    summary: str = ""  # one friendly line saying what was saved (set on success by the paste-back helpers)


def apply_secrets(values: Mapping[str, object]) -> list[str]:
    """Copy known keys (e.g. from st.secrets) into os.environ. Returns the names applied."""
    applied = []
    for k in SECRET_KEYS:
        v = values.get(k)
        if v not in (None, ""):
            os.environ[k] = str(v)
            applied.append(k)
    return applied


def make_ctx(root: Path, confirm: Callable[[str], str] | None = None) -> Ctx:
    """Build a context rooted at `root`. `confirm` answers typed-yes gates from the UI."""
    ctx = build_ctx(root)
    ctx.confirm = confirm or (lambda _prompt: "")  # no answer means the gate refuses
    return ctx


def capture(fn: Callable[..., object], *args, **kwargs) -> Outcome:
    """Run a stage, capturing everything it prints. StudioErrors become readable messages."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(*args, **kwargs)
        except PendingLLMResponse as exc:
            return Outcome(False, out.getvalue() + err.getvalue(), str(exc), pending=True)
        except InvalidAnswer as exc:
            return Outcome(False, out.getvalue() + err.getvalue(), str(exc), problems=list(exc.problems))
        except StudioError as exc:
            return Outcome(False, out.getvalue() + err.getvalue(), str(exc))
        except Exception as exc:  # noqa: BLE001 - the web app must show a message, never a traceback
            return Outcome(False, out.getvalue() + err.getvalue(),
                           f"Something unexpected went wrong: {type(exc).__name__}: {exc}\n"
                           "Why: the answer or the video files are not in the shape this step expects.\n"
                           "Next: check the pasted answer against the request (all keys present, nothing cut off), "
                           "then try again.")
    return Outcome(True, out.getvalue() + err.getvalue())


def outcome_from_process(returncode: int, output: str) -> Outcome:
    """Turn a finished CLI process into an Outcome with a readable error."""
    if returncode == 0:
        return Outcome(True, output)
    if returncode == 3:
        return Outcome(False, output, output.strip()[-800:], pending=True)
    if returncode in (-9, 137):
        return Outcome(False, output, "The step was killed because the host ran out of memory.\n"
                       "Why: free cloud hosting has about 1 GB of RAM and video editing needs more.\n"
                       "Next: run the app on your own computer (README, Web app), or make a shorter video.")
    tail = output.strip()[-1500:] or "no output"
    return Outcome(False, output, f"The step failed (exit code {returncode}).\n{tail}")


def run_cli(root: Path, args: list[str], draft: bool = False) -> Outcome:
    """Run `python -m studio.cli <args>` in a child process.

    A crash or out-of-memory kill then ends only the child, so the web app stays up and shows an error.
    """
    repo = Path(__file__).resolve().parents[2]
    env = {**os.environ, "STUDIO_HOME": str(root), "PYTHONPATH": str(repo)}
    if draft:
        env["STUDIO_DRAFT"] = "1"  # 720p, 24 fps, fastest encode
    p = subprocess.run([sys.executable, "-m", "studio.cli", *args], cwd=repo, env=env,
                       capture_output=True, text=True)
    return outcome_from_process(p.returncode, (p.stdout or "") + (p.stderr or ""))


def run_stage_by_name(ctx: Ctx, name: str, video_id: int, force: bool = False, draft: bool = False) -> Outcome:
    """Run one production stage (voice, visuals, build, thumbnail, shorts) in a child process."""
    return run_cli(ctx.settings.root, [name, str(video_id)] + (["--force"] if force else []), draft=draft)


def log_tail(ctx: Ctx, lines: int = 80) -> str:
    """Last lines of logs/studio.log for the Settings page."""
    f = ctx.settings.root / "logs" / "studio.log"
    return "\n".join(f.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]) if f.exists() else ""


def suggest_topics(ctx: Ctx, seed: str, force: bool = False) -> Outcome:
    """Topic research. Uses YouTube competitor stats only when Google sign-in is set up (local runs)."""
    from studio.stages import research

    kwargs = {}
    if not (ctx.settings.client_secret.exists() and ctx.settings.token_path.exists()):
        kwargs["competitors"] = lambda _ctx, _seed: []  # autocomplete-only; no OAuth available
    return capture(research.run, ctx, seed, force=force, limit=25, **kwargs)


def auto_suggest_topics(ctx: Ctx, count: int = 8) -> Outcome:
    """'Suggest topics for me': fresh channel-fit ideas with no seed typed."""
    from studio.stages import discover

    def go() -> None:
        ideas = discover.auto_suggest(ctx, count=count)
        print(f"Added {len(ideas)} new topic ideas.")

    return capture(go)


def ideas_prompt(ctx: Ctx) -> str:
    """Prompt to paste into Claude asking for new topics (avoids everything already saved)."""
    from studio.stages import discover

    return discover.ideas_prompt(ctx)


def import_claude_ideas(ctx: Ctx, text: str) -> Outcome:
    """Save topics pasted back from Claude."""
    from studio.stages import discover

    def go() -> None:
        print(f"Added {len(discover.import_ideas(ctx, text))} new topic ideas.")

    return capture(go)


def used_topics(ctx: Ctx) -> list[Idea]:
    """Topics already approved into videos, newest first."""
    return (scope.ideas(ctx.session).filter(Idea.status == "approved", Idea.seed != "__demo__")
            .order_by(Idea.id.desc()).all())


def has_competitor_data(ctx: Ctx) -> bool:
    """True when Google sign-in exists, so competition and outlier numbers are real."""
    return ctx.settings.client_secret.exists() and ctx.settings.token_path.exists()


def add_manual_topic(ctx: Ctx, topic: str) -> Idea:
    """Let the owner type their own topic instead of using a suggestion."""
    topic = topic.strip()
    if not topic:
        raise StudioError("The topic is empty.", "", "Type a topic such as 'how Costco makes money'.")
    idea = Idea(seed="manual", topic=topic)
    ctx.session.add(idea)
    ctx.session.commit()
    return idea


def ideas_for(ctx: Ctx, seed: str | None = None) -> list[Idea]:
    """Ideas ranked best first, optionally for one seed."""
    q = scope.ideas(ctx.session).filter(Idea.seed != "__demo__")
    if seed:
        q = q.filter(Idea.seed == seed)
    return sorted(q.all(), key=lambda i: i.rank_score, reverse=True)


def video_title(ctx: Ctx, v: Video) -> str:
    """Picked title if there is one, else the topic."""
    t = ctx.session.query(Title).filter_by(video_id=v.id, is_pick=True).first()
    return t.text if t else ctx.session.get(Idea, v.idea_id).topic


def list_videos(ctx: Ctx) -> list[Video]:
    return scope.videos(ctx.session).order_by(Video.id.desc()).all()


def read_prompt(ctx: Ctx, video_id: int, task: str = "script") -> str:
    """The prompt text to paste into Claude (the file-path footer meant for Claude Code is removed)."""
    pf, _ = prompt_paths(ctx.settings.project_dir(video_id), task)
    if not pf.exists():
        return ""
    text = pf.read_text(encoding="utf-8")
    text = text.split(_ANSWER_MARK)[0].rstrip()
    return text + "\n\n---\nReply with ONLY the JSON object described above, no other text."


def save_response(ctx: Ctx, video_id: int, text: str, task: str = "script") -> Path:
    """Write a pasted answer to the response file the CLI would read."""
    clean = normalize_answer(text)  # raises a StudioError saying what is wrong and where
    _, rf = prompt_paths(ctx.settings.project_dir(video_id), task)
    rf.write_text(clean, encoding="utf-8")
    return rf


_PLAIN = [
    (re.compile(r"beat '(.*?)' not in .*"), r"uses the beat '\1', which is not allowed "
     "(use question, reveal, example, pattern_break or null)"),
    (re.compile(r"chart has no source.*"), "has a chart with real figures but no source "
     "(add source_ids, or label it a made-up example)"),
    (re.compile(r"chart cites unknown source id '(.*?)'"), r"cites the source '\1', which is not in the sources list"),
    (re.compile(r"visual_keywords is empty"), "has no visual keywords"),
    (re.compile(r"narration is empty"), "has no narration"),
]


def plain_problems(problems: list[str]) -> list[str]:
    """Validation problems in plain language, e.g. 'Segment 15 uses the beat ...'."""
    out = []
    for p in problems:
        m = re.match(r"(segment \d+): (.*)", p)
        if not m:
            out.append(p[:1].upper() + p[1:])
            continue
        who, rest = m.group(1).capitalize(), m.group(2)
        for rx, repl in _PLAIN:
            if rx.fullmatch(rest):
                rest = rx.sub(repl, rest)
                break
        out.append(f"{who} {rest}" if rest != m.group(2) else f"{who}: {rest}")
    return out


def fix_request(problems: list[str], task: str = "script") -> str:
    """Text to paste to Claude asking it to repair its previous answer, with the exact errors."""
    bullets = "\n".join(f"- {p}" for p in problems)
    return (f"Your {task} JSON answer failed the studio's validation. Please send back the full corrected JSON "
            f"object (only the JSON, no other text), changing only what is needed to fix these errors:\n\n{bullets}\n\n"
            "Allowed `beat` values: question, reveal, example, pattern_break, or null. Charts with real figures need "
            "`source_ids` that exist in `sources`; a flow diagram with empty `values`, or a chart titled "
            "'made-up example', needs no source.")


def rejected_answer(ctx: Ctx, video_id: int, task: str = "script") -> str:
    """The last rejected pasted answer for a task ('' if none), so it can be shown again."""
    pf, _ = prompt_paths(ctx.settings.project_dir(video_id), task)
    f = pf.with_name(f"{task}.rejected.json")
    return f.read_text(encoding="utf-8") if f.exists() else ""


_TASK_NAME = {"script": "script", "outline": "story outline", "critique": "script review and rewrite"}


def _with_summary(res: Outcome, ctx: Ctx, video_id: int, task: str) -> Outcome:
    """On success add a line saying what was saved and where; on failure make clear nothing was kept."""
    if res.ok:
        name = _TASK_NAME.get(task, task)
        lines = [ln.strip() for ln in res.log.splitlines() if ln.strip()]
        facts = " ".join(lines[:2])[:300]
        res.summary = f"Saved your {name} answer for video #{video_id}. {facts}".strip()
    elif not res.pending and "nothing was saved" not in res.error.lower():
        res.error += "\n(Nothing was saved. Fix the points above and paste the answer again.)"
    return res


def _reject(rf: Path, res: Outcome) -> Outcome:
    """A bad answer is moved aside (never deleted) so a new one can be pasted."""
    if rf.exists():
        res.answer = rf.read_text(encoding="utf-8")
        rf.replace(rf.with_name(rf.name.replace(".response.json", ".rejected.json")))
    return res


def submit_script(ctx: Ctx, idea_id: int, video_id: int, pasted: str) -> Outcome:
    """Save a pasted script answer and run the script stage. A bad answer is removed so it can be re-pasted."""
    from studio.stages import script

    rf = None
    try:
        rf = save_response(ctx, video_id, pasted)
    except StudioError as exc:
        return Outcome(False, "", str(exc))
    res = capture(script.run, ctx, idea_id)
    return _with_summary(res if res.ok else _reject(rf, res), ctx, video_id, "script")


def submit_task(ctx: Ctx, video_id: int, task: str, pasted: str, fn: Callable[..., object], *args) -> Outcome:
    """Save a pasted answer for an optional task (outline, critique) and run it; a bad answer is removed."""
    try:
        rf = save_response(ctx, video_id, pasted, task)
    except StudioError as exc:
        return Outcome(False, "", str(exc))
    res = capture(fn, ctx, *args)
    return _with_summary(res if res.ok else _reject(rf, res), ctx, video_id, task)


def project_files(ctx: Ctx, video_id: int) -> dict[str, list[Path]]:
    """Downloadable outputs for a video, grouped."""
    d = ctx.settings.project_dir(video_id)

    def one(*names: str) -> list[Path]:
        return [d / n for n in names if (d / n).exists()]

    return {
        "video": one("final.mp4", "clean.mp4"),
        "captions": one("captions.srt"),
        "script": one("script.md"),
        "thumbnails": sorted((d / "thumbs").glob("thumb_*.jpg")) if (d / "thumbs").exists() else [],
        "shorts": sorted((d / "shorts").glob("*.mp4")) if (d / "shorts").exists() else [],
    }


def zip_outputs(ctx: Ctx, video_id: int) -> bytes:
    """Zip every deliverable of a video (no prompts, no caches)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for paths in project_files(ctx, video_id).values():
            for p in paths:
                z.write(p, p.relative_to(ctx.settings.project_dir(video_id)).as_posix())
    return buf.getvalue()


def ensure_preview(ctx: Ctx, video_id: int) -> Path | None:
    """Small browser-safe preview next to final.mp4 (built once, rebuilt if the video changed)."""
    from studio.util import ffmpeg as ff

    d = ctx.settings.project_dir(video_id)
    final, prev = d / "final.mp4", d / "preview.mp4"
    if not final.exists():
        return None
    if not prev.exists() or prev.stat().st_mtime < final.stat().st_mtime:
        ff.ensure_ffmpeg()
        tmp = d / "preview.part.mp4"
        ff.run(ff.preview_cmd(final, tmp), "making the preview")
        tmp.replace(prev)
    return prev


def playback_issues(path: Path) -> list[str]:
    """Why the browser may not play `path`; empty if it looks fine."""
    from studio.util import ffmpeg as ff

    return ff.browser_issues(ff.stream_info(path))


def stage_progress(stage: str) -> float:
    """0..1 position of a stage in the pipeline."""
    return STAGES.index(stage) / (len(STAGES) - 1)


def next_produce_stage(video: Video) -> str | None:
    """Which production stage is due next, or None if production is finished."""
    order = {"approved": None, "scripted": "voice", "voiced": "visuals", "visuals_ready": "build",
             "built": "thumbnail"}
    return order.get(video.stage)
