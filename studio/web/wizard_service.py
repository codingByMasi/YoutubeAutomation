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


FLOW_LABELS = {"plan": "Plan story", "script": "Write script", "review": "Review"}
_FLOW_TASK = {"plan": "story_plan", "script": "script"}
_FLOW_INSTRUCTION = {
    "plan": "Claude finds real facts with sources and plans the hook and open loops. This is what makes the "
            "script accurate and worth watching.",
    "script": "Claude now writes the full script from your plan.",
    "review": "Claude scores the script, finds where viewers would leave, and rewrites it stronger.",
}


def script_flow(ctx: Ctx, video: Video) -> dict:
    """The Script screen as one path: {steps: [(id, label, state)], current, task, instruction, legacy, done_count}.

    state is 'done', 'skipped', 'now' or 'todo'. `current` is None when the script is approved. The plan always
    comes first, so a script is never requested without facts and open loops. A script written before the story
    plan existed (`legacy`) shows the plan as skipped and goes straight to the review."""
    from studio.story import engine as eng
    from studio.story import profile as sp

    st = eng.load_state(ctx.settings.project_dir(video.id))
    review_on = sp.enabled(sp.for_channel(ctx.settings.root), "story_review")
    scripted = STAGES.index(video.stage) >= STAGES.index("scripted")
    legacy = scripted and st["plan"] != "done" and st["script"] != "done"
    keys = ["plan", "script"] + (["review"] if review_on else [])
    done = {k: st[k] == "done" or (k == "script" and scripted) for k in keys}
    if legacy:
        done["plan"] = True
    current = next((k for k in keys if not done[k]), None)
    steps = [(k, FLOW_LABELS[k], "skipped" if legacy and k == "plan" else "done" if done[k]
              else "now" if k == current else "todo") for k in keys]
    task = None
    if current == "review":
        task = "story_review" if legacy else eng.pending_task_name(ctx, video.id)
    elif current:
        task = _FLOW_TASK[current]
    return {"steps": steps, "current": current, "task": task, "legacy": legacy,
            "instruction": _FLOW_INSTRUCTION.get(current or "", ""), "done_count": sum(done.values())}


def skip_review(ctx: Ctx, video: Video) -> None:
    """Mark the review done without running it (the owner chose to move on)."""
    from studio.story import engine as eng

    out = ctx.settings.project_dir(video.id)
    st = eng.load_state(out)
    st["plan"] = st["plan"] if st["plan"] == "done" else "done"
    st["script"], st["review"] = "done", "done"
    eng.save_state(out, st)
