"""`comments`: draft replies to a file (never posts). `comments post <file>` posts only with a per-reply 'yes'."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StudioError
from studio.llm import ask_json
from studio.models import CommentDraft
from studio.stages.base import get_video
from studio.stages.review import require_yes
from studio.stages.script import BANNED_PHRASES, banned_in

REPLY_MAX = 500
PROMPT = """You are drafting replies to YouTube comments for a business-economics explainer channel.
Video: {title}

Tone: friendly, brief (1-3 sentences), factual, no hype, no financial advice, never argue.
Skip (empty reply) spam, abuse, and comments that need no answer. Thank people for corrections and
say you'll check the source. Never promise future videos on specific dates. Banned phrases: {banned}.

Comments (id: text):
{comments}

Output JSON: {{"replies": [{{"comment_id": "<id>", "reply": "<text or empty to skip>"}}]}}
Include every comment id exactly once."""


def validate_replies(ids: set[str]):
    def check(d: dict) -> list[str]:
        problems, seen = [], set()
        for r in d.get("replies", []):
            cid = str(r.get("comment_id"))
            if cid not in ids:
                problems.append(f"unknown comment_id {cid!r}")
            seen.add(cid)
            reply = str(r.get("reply", ""))
            if len(reply) > REPLY_MAX:
                problems.append(f"reply to {cid} is over {REPLY_MAX} characters")
            problems += [f"reply to {cid} uses banned phrase {p!r}" for p in banned_in(reply)]
        problems += [f"missing reply entry for {cid}" for cid in sorted(ids - seen)]
        return problems
    return check


def drafts_file(ctx: Ctx, video_id: int) -> Path:
    return ctx.settings.project_dir(video_id) / "comments_drafts.json"


def draft(ctx: Ctx, video_id: int) -> Path:
    """Fetch recent comments, get draft replies, write them to a file. Never posts anything."""
    s = ctx.session
    video = get_video(s, video_id)
    if not video.youtube_video_id:
        raise StudioError(f"Video {video_id} is not on YouTube yet.", "",
                          f"Publish it first with `publish {video_id}`.")
    data, _ = ctx.youtube("comments")
    for item in data.comment_threads(video.youtube_video_id):
        top = item["snippet"]["topLevelComment"]
        if not s.query(CommentDraft).filter_by(youtube_comment_id=top["id"]).first():
            s.add(CommentDraft(video_id=video_id, youtube_comment_id=top["id"],
                               comment_text=top["snippet"].get("textDisplay", "")[:2000]))
    s.commit()
    pending = s.query(CommentDraft).filter_by(video_id=video_id, status="new").all()
    if pending:
        ids = sorted(c.youtube_comment_id for c in pending)
        review = ctx.settings.project_dir(video_id) / "review.json"
        title = json.loads(review.read_text()).get("title", "") if review.exists() else ""
        task = "comments_" + hashlib.sha1(",".join(ids).encode()).hexdigest()[:10]
        prompt = PROMPT.format(title=title, banned=", ".join(f'"{p}"' for p in BANNED_PHRASES),
                               comments="\n".join(f"{c.youtube_comment_id}: {c.comment_text}" for c in pending))
        answer = ask_json(ctx.settings, ctx.settings.project_dir(video_id), task, prompt,
                          validate=validate_replies(set(ids)))
        by_id = {str(r["comment_id"]): str(r.get("reply", "")).strip() for r in answer["replies"]}
        for c in pending:
            c.draft_reply = by_id.get(c.youtube_comment_id, "")
            c.status = "drafted" if c.draft_reply else "skipped"
        s.commit()
    rows = s.query(CommentDraft).filter(CommentDraft.video_id == video_id, CommentDraft.status == "drafted").all()
    out = drafts_file(ctx, video_id)
    out.write_text(json.dumps([{"id": c.id, "youtube_comment_id": c.youtube_comment_id, "comment": c.comment_text,
                                "reply": c.draft_reply} for c in rows], indent=2, ensure_ascii=False),
                   encoding="utf-8")
    typer.echo(f"{len(rows)} draft replies written to {out}. Nothing was posted.\n"
               f"Edit the file, then post with: comments post {out}")
    return out


def post(ctx: Ctx, file: str) -> int:
    """Post replies from a drafts file, asking for a typed 'yes' before each one."""
    path = Path(file)
    if not path.exists():
        raise StudioError(f"{path} not found.", "", "Run `comments <video_id>` to create a drafts file.")
    items = json.loads(path.read_text(encoding="utf-8"))
    s = ctx.session
    data = None
    posted = 0
    for it in items:
        row = s.get(CommentDraft, it["id"])
        reply = str(it.get("reply", "")).strip()
        if not row or row.status == "posted" or not reply:
            continue
        problems = [f"banned phrase {p!r}" for p in banned_in(reply)] + \
            ([f"over {REPLY_MAX} characters"] if len(reply) > REPLY_MAX else [])
        if problems:
            typer.secho(f"Skipping reply to {row.youtube_comment_id}: {', '.join(problems)}", fg=typer.colors.RED)
            continue
        typer.echo(f"\nComment: {row.comment_text}\nReply:   {reply}")
        try:
            require_yes(ctx.confirm, "Type yes to post this reply (anything else skips): ", "reply")
        except StudioError:
            typer.echo("Skipped.")
            continue
        if data is None:
            data, _ = ctx.youtube("comments")
        data.reply_to_comment(row.youtube_comment_id, reply)
        row.draft_reply, row.status = reply, "posted"
        s.commit()
        posted += 1
    typer.echo(f"Posted {posted} repl{'y' if posted == 1 else 'ies'}.")
    return posted
