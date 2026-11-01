"""Which step of the one-page "Make a video" wizard a video is on. No Streamlit imports, so it is unit-tested."""

from __future__ import annotations

from studio.context import Ctx
from studio.models import Video
from studio.stages.base import STAGES
from studio.web import service as svc

# (id, short label shown in the progress bar)
STEPS = [("topic", "Topic"), ("script", "Script"), ("make", "Make"), ("review", "Review"), ("publish", "Publish")]
STEP_IDS = [s for s, _ in STEPS]


def step_for(video: Video | None) -> str:
    """The wizard step a video belongs on. No video yet means the topic step."""
    if video is None:
        return "topic"
    i = STAGES.index(video.stage)
    if i <= STAGES.index("approved"):
        return "script"
    if i < STAGES.index("thumbnailed"):
        return "make"
    if video.stage == "thumbnailed":
        return "review"
    return "publish"


def step_number(step: str) -> int:
    """1-based position of a step."""
    return STEP_IDS.index(step) + 1


def resume_video(ctx: Ctx) -> Video | None:
    """The newest video of the active channel that is not live yet (what 'continue where I left off' opens)."""
    for v in svc.list_videos(ctx):
        if v.stage != "live":
            return v
    return None


def finished(video: Video) -> bool:
    """True once the video is scheduled or live (nothing left for the wizard to do)."""
    return STAGES.index(video.stage) >= STAGES.index("scheduled")
