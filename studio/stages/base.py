"""Stage ordering and idempotency rules (SPEC 2.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from studio.errors import StageError
from studio.models import Video, utcnow

STAGES = [
    "idea", "approved", "scripted", "voiced", "visuals_ready",
    "built", "thumbnailed", "reviewed", "scheduled", "live",
]
STAGE_COMMAND = {
    "approved": "approve-idea", "scripted": "script", "voiced": "voice", "visuals_ready": "visuals",
    "built": "build", "thumbnailed": "thumbnail", "reviewed": "review", "scheduled": "publish",
    "live": "status --sync",
}


def stage_index(stage: str) -> int:
    try:
        return STAGES.index(stage)
    except ValueError as exc:
        raise StageError(f"Unknown stage {stage!r}.", f"Valid stages: {', '.join(STAGES)}.") from exc


@dataclass
class StageResult:
    """What happened when a stage was asked to run."""

    ran: bool
    message: str


def get_video(s: Session, video_id: int) -> Video:
    v = s.get(Video, video_id)
    if v is None:
        raise StageError(f"Video {video_id} not found.", "", "Run `status` to list videos.")
    return v


def check_can_run(video: Video, target: str, force: bool = False) -> bool:
    """Return True if the stage should run, False if already done. Raise if out of order.

    A stage can run only when the video sits exactly one step before it. A finished stage is
    skipped unless force=True; once a video is scheduled or live, earlier stages are locked.
    """
    cur, tgt = stage_index(video.stage), stage_index(target)
    if cur < tgt - 1:
        needed = STAGES[tgt - 1]
        raise StageError(
            f"Cannot run `{STAGE_COMMAND[target]}` on video {video.id}: it is at stage '{video.stage}'.",
            f"Stages advance in order; '{target}' needs the video to be '{needed}' first.",
            f"Run `{STAGE_COMMAND[needed]} {video.id}` first.",
        )
    if cur >= tgt:
        if not force:
            return False
        if cur >= stage_index("scheduled") and target != "live":
            raise StageError(
                f"Video {video.id} is already '{video.stage}' on YouTube; earlier stages are locked.",
                "Re-running would make local files disagree with the uploaded video.",
                "Change the live video in YouTube Studio, and record it with `ab-log`.",
            )
    return True


def advance(video: Video, target: str) -> None:
    """Set the stage. Allowed: the next stage, or rolling back to `target` on a forced re-run."""
    cur, tgt = stage_index(video.stage), stage_index(target)
    if tgt > cur + 1:
        raise StageError(f"Cannot jump video {video.id} from '{video.stage}' to '{target}'.")
    video.stage = target
    video.updated_at = utcnow()


def run_stage(s: Session, video: Video, target: str, work: Callable[[], None], force: bool = False) -> StageResult:
    """Run `work` if the stage is due, then advance. Re-running a finished stage is a no-op."""
    if not check_can_run(video, target, force):
        return StageResult(False, f"Video {video.id}: '{target}' already done. Use --force to redo it.")
    work()
    advance(video, target)
    s.commit()
    note = " Later stages must be re-run." if force else ""
    return StageResult(True, f"Video {video.id}: now '{target}'.{note}")
