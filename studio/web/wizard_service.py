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


SCRIPT_STEPS = ["Get the request", "Copy it to Claude", "Paste Claude's reply"]
_ENGINE_LABEL = {"story_plan": "the story plan (facts, outline, hooks)", "script": "the script",
                 "story_review": "the script review and rewrite"}


def script_next_step(ctx: Ctx, video: Video, engine: bool = False) -> dict:
    """What the Script screen should show now: {step (1-3), task, headline, rejected, done}.

    One state at a time: no request yet (1), request ready and waiting for the reply (2 then 3), or a reply that
    was rejected (3, with `rejected` True). `done` is True when nothing is left to answer."""
    from studio.story import engine as eng

    if engine:
        task = eng.pending_task_name(ctx, video.id)
        if task is None:
            return {"step": 3, "task": None, "headline": "The story engine is finished for this video.",
                    "rejected": False, "done": True}
    else:
        task = "script"
    label = _ENGINE_LABEL.get(task.split("_r")[0] if task.startswith("story_review") else task, "the script")
    has_prompt = bool(svc.read_prompt(ctx, video.id, task))
    rejected = bool(svc.rejected_answer(ctx, video.id, task))
    if not has_prompt:
        return {"step": 1, "task": task, "rejected": False, "done": False,
                "headline": f"Next: get the request for Claude that asks for {label}."}
    if rejected:
        return {"step": 3, "task": task, "rejected": True, "done": False,
                "headline": f"Your last reply for {label} was not accepted. Fix it with Claude, "
                            "then paste the new reply."}
    return {"step": 2, "task": task, "rejected": False, "done": False,
            "headline": f"Next: copy the request into Claude, then paste its reply for {label} below."}
