"""`publish`: upload as private or scheduled with full metadata. Needs `reviewed` and a typed 'yes'."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import StageError, StudioError
from studio.models import Idea
from studio.stages.base import advance, check_can_run, get_video
from studio.stages.review import file_fingerprint, require_yes
from studio.util.logging import get_logger

log = get_logger("publish")
AUDIT_NOTE = ("YouTube keeps videos uploaded by unaudited API projects private. Either apply for the "
              "YouTube API compliance audit (see the YouTube Data API docs, 'Audit and quota extension') "
              "or publish the video manually in YouTube Studio.")
EXTRA_STEPS = ("thumbnail", "captions", "playlist")


def parse_when(text: str | None, now: datetime | None = None) -> datetime | None:
    """Parse '--at' (local time unless an offset is given) to aware UTC; must be in the future."""
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M%z"):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            break
        except ValueError:
            continue
    else:
        raise StudioError(f"Could not read --at {text!r}.", "Expected a date and time.",
                          'Use the form --at "2026-11-05 18:00" (your local time).')
    dt = dt.astimezone() if dt.tzinfo is None else dt
    dt = dt.astimezone(UTC)
    if dt <= (now or datetime.now(UTC)):
        raise StudioError(f"--at {text!r} is in the past.", "YouTube needs a future publish time.",
                          "Pick a later time, or leave out --at to upload as private.")
    return dt


def upload_body(review: dict, publish_at: datetime | None) -> dict:
    """videos.insert body. Always private; publishAt schedules it. Field names per the Data API docs."""
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "embeddable": True,
              "license": "youtube", "containsSyntheticMedia": bool(review["synthetic_media"])}
    if publish_at:
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"snippet": {"title": review["title"], "description": review["description"], "tags": review["tags"],
                        "categoryId": review["category_id"], "defaultLanguage": "en",
                        "defaultAudioLanguage": "en"},
            "status": status}


def forced_private(requested_at: datetime | None, status: dict) -> bool:
    """True if a scheduled upload came back without its publishAt (unaudited-project restriction)."""
    return bool(requested_at) and not status.get("publishAt")


def _load_review(path: Path) -> dict:
    if not path.exists():
        raise StageError(f"{path} not found.", "Publishing needs the approved review record.",
                         "Run `review <video_id>` and type yes.")
    return json.loads(path.read_text(encoding="utf-8"))


def run(ctx: Ctx, video_id: int, at: str | None = None, playlist: str | None = None) -> None:
    s = ctx.session
    video = get_video(s, video_id)
    review_path = ctx.settings.project_dir(video_id) / "review.json"
    resuming = video.stage == "scheduled" and video.youtube_video_id
    if not resuming:
        if not check_can_run(video, "scheduled"):
            typer.echo(f"Video {video_id} is already '{video.stage}' on YouTube ({video.youtube_video_id}).")
            return
    review = _load_review(review_path)
    state = review.setdefault("publish_state", {})
    pending = [p for p in EXTRA_STEPS if not state.get(p) and (p != "playlist" or playlist)]
    if resuming and not pending:
        typer.echo(f"Video {video_id} is already scheduled ({video.youtube_video_id}); nothing left to do.")
        return

    if ctx.session.get(Idea, video.idea_id).seed.startswith("__"):
        raise StudioError(f"Video {video_id} is the demo video and cannot be published.",
                          "It uses sample figures that are not real data.", "Make a real video with `run-all`.")
    ctx.settings.require("publish")
    video_file = Path(review["files"]["video"])
    if not resuming and file_fingerprint(video_file) != review.get("video_sha256"):
        raise StudioError(f"{video_file} changed after it was reviewed.", "Only the reviewed file may be uploaded.",
                          f"Run `review {video_id} --force` to approve the new file.")
    publish_at = parse_when(at)
    plan = {"thumbnails.set": 1, "captions.insert": 1, "videos.list": 1}
    if not resuming:
        plan["videos.insert"] = 1
    if playlist:
        plan["playlistItems.insert"] = 1
    ctx.quota.check(plan)

    when = f"scheduled for {publish_at:%Y-%m-%d %H:%M} UTC" if publish_at else "PRIVATE (no publish time)"
    action = f"finish publishing steps ({', '.join(pending)})" if resuming else f"upload video {video_id} as {when}"
    typer.echo(f"\nTitle: {review['title']}\nFile: {video_file}\nSynthetic-content disclosure: "
               f"{review['synthetic_media']}\nPlaylist: {playlist or '-'}")
    require_yes(ctx.confirm, f"Type yes to {action}: ", "publish")

    data, _ = ctx.youtube("publish")
    if not resuming:
        resp = data.upload(video_file, upload_body(review, publish_at))
        video.youtube_video_id = resp["id"]
        video.publish_at = publish_at.replace(tzinfo=None) if publish_at else None
        advance(video, "scheduled")
        s.commit()
        typer.echo(f"Uploaded: https://youtu.be/{resp['id']}")
        live = data.videos([resp["id"]], part="status")
        st = (live[0] if live else resp).get("status", {})
        if forced_private(publish_at, st):
            state["forced_private"] = True
            typer.secho(f"Upload is locked to private: the schedule was not accepted.\n{AUDIT_NOTE}",
                        fg=typer.colors.YELLOW)
    yt_id = video.youtube_video_id
    for step in pending:
        try:
            if step == "thumbnail":
                data.set_thumbnail(yt_id, Path(review["thumbnail"]))
            elif step == "captions":
                data.insert_caption(yt_id, Path(review["files"]["captions"]))
            elif step == "playlist":
                data.add_to_playlist(playlist, yt_id)
            state[step] = True
        except StudioError as exc:
            hint = " Custom thumbnails need a phone-verified channel." if step == "thumbnail" else ""
            typer.secho(f"{step} failed: {exc.what}{hint} Re-run `publish {video_id}` to retry the rest.",
                        fg=typer.colors.RED)
            log.warning("publish step %s failed: %s", step, exc)
    review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    left = [p for p in EXTRA_STEPS if not state.get(p) and (p != "playlist" or playlist)]
    typer.echo(f"Video {video_id}: '{video.stage}'." + (f" Still to do: {', '.join(left)}." if left else " All done."))
