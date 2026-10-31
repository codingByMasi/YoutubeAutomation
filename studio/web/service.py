"""Glue between the Streamlit UI and the existing stages. No Streamlit imports, so it is unit-tested."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from studio.context import Ctx, build_ctx
from studio.errors import PendingLLMResponse, StudioError
from studio.llm import prompt_paths
from studio.models import Idea, Title, Video
from studio.stages.base import STAGES

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
        except StudioError as exc:
            return Outcome(False, out.getvalue() + err.getvalue(), str(exc))
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
    q = ctx.session.query(Idea).filter(Idea.seed != "__demo__")
    if seed:
        q = q.filter(Idea.seed == seed)
    return sorted(q.all(), key=lambda i: i.rank_score, reverse=True)


def video_title(ctx: Ctx, v: Video) -> str:
    """Picked title if there is one, else the topic."""
    t = ctx.session.query(Title).filter_by(video_id=v.id, is_pick=True).first()
    return t.text if t else ctx.session.get(Idea, v.idea_id).topic


def list_videos(ctx: Ctx) -> list[Video]:
    return ctx.session.query(Video).order_by(Video.id.desc()).all()


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
    if not text.strip():
        raise StudioError("The pasted answer is empty.", "", "Paste the JSON that Claude wrote, then save.")
    _, rf = prompt_paths(ctx.settings.project_dir(video_id), task)
    rf.write_text(text, encoding="utf-8")
    return rf


def submit_script(ctx: Ctx, idea_id: int, video_id: int, pasted: str) -> Outcome:
    """Save a pasted script answer and run the script stage. A bad answer is removed so it can be re-pasted."""
    from studio.stages import script

    rf = None
    try:
        rf = save_response(ctx, video_id, pasted)
    except StudioError as exc:
        return Outcome(False, "", str(exc))
    res = capture(script.run, ctx, idea_id)
    if not res.ok and rf.exists():
        rf.unlink()
    return res


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


def stage_progress(stage: str) -> float:
    """0..1 position of a stage in the pipeline."""
    return STAGES.index(stage) / (len(STAGES) - 1)


def next_produce_stage(video: Video) -> str | None:
    """Which production stage is due next, or None if production is finished."""
    order = {"approved": None, "scripted": "voice", "voiced": "visuals", "visuals_ready": "build",
             "built": "thumbnail"}
    return order.get(video.stage)
