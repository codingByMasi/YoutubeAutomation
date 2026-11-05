"""Streamlit pieces shared by pages: the paste-or-upload box for Claude's JSON answer."""

from __future__ import annotations

import streamlit as st

from studio.web import service as svc


def answer_box(key: str, label: str = "Claude's answer (JSON)", height: int = 280) -> str:
    """A paste box with an 'or upload the .json file' option. Returns the answer text ('' if none yet)."""
    pasted = st.text_area(label, height=height, key=f"{key}_text",
                          help="Paste exactly what Claude replied. If Claude gave you a .json file, upload it instead.")
    up = st.file_uploader("...or upload the answer as a file", type=["json", "txt"], key=f"{key}_file")
    if up is not None:
        return up.getvalue().decode("utf-8", errors="replace")
    return pasted


def goto(page: str) -> None:
    """Button callback: jump to another page of the app (the sidebar radio is keyed 'nav')."""
    st.session_state["nav"] = page


def show_flash() -> None:
    """Show (once) the message left by the last successful 'Save and apply'; it survives the st.rerun()."""
    msg = st.session_state.pop("flash_ok", None)
    if msg:
        st.success("✅ " + msg["summary"])
        if msg.get("log"):
            with st.expander("What the studio did"):
                st.code(msg["log"])


def show_problems(res) -> None:
    """Validation problems in plain words, with a copy-able request asking Claude to fix exactly those points."""

    st.error("❌ Claude's answer has a few problems, so it was not applied. Your answer is not lost: "
             "it stays in the box and is kept in 'Your last answer' below.")
    for line in svc.plain_problems(res.problems):
        st.markdown(f"- {line}")
    st.markdown("**Fix it:** copy this (copy icon, top right of the box), send it to Claude, "
                "then paste the corrected answer back.")
    st.code(svc.fix_request(res.problems), language="markdown", wrap_lines=True)


def apply_answer(ctx, video_id: int, task: str, pasted: str, fn, args: tuple, idea_id: int | None = None) -> bool:
    """Save a pasted answer and run its step, always telling the user what happened.

    `task` is script, outline or critique. Success is flashed (so it shows after the rerun) and True is returned;
    the caller then calls st.rerun(). A failure is shown right here with the reason and what to fix.
    """

    with st.spinner("Checking your answer..."):
        if task == "script" and fn is None:
            res = svc.submit_script(ctx, idea_id, video_id, pasted)
        else:
            res = svc.submit_task(ctx, video_id, task, pasted, fn, *args)
    if res.ok:
        st.session_state["flash_ok"] = {"summary": res.summary or "Saved and applied.", "log": res.log.strip()}
        return True
    if res.problems:
        show_problems(res)
        return False
    if res.pending:  # an answer was saved but another request is now waiting
        st.info(svc.plain_pending(res.error))
        return False
    if not res.problems and res.error:
        st.error("❌ Could not read or apply this answer, so nothing was saved.\n\n"
                 + svc.plain_pending(res.error).split("\n(Nothing")[0])
        st.markdown("**Fix it:** copy this, send it to Claude, then paste the new reply back.")
        st.code(svc.reply_again_request(res.error), language="markdown", wrap_lines=True)
        return False
    return False


def no_request_panel(ctx, video_id: int, task: str, run_fn, key: str, error: str = "") -> None:
    """Shown when a step is pending but its request file is missing. Never says 'nothing to answer'."""
    st.warning("The request for Claude is not written yet. Press the button to write it.")
    if error:
        st.caption(svc.plain_pending(error))
    if st.button("Write the request for Claude", type="primary", key=f"{key}_mk_{task}{video_id}"):
        res = svc.capture(run_fn, ctx)
        if res.error and not res.pending:
            st.error(svc.plain_pending(res.error))
        else:
            st.rerun()


def characters_waiting(ctx, video) -> bool:
    """True while the character-description request is written and not yet answered."""
    from studio import llm

    return llm.pending_task(ctx.settings.project_dir(video.id), "characters") == "waiting"


def characters_panel(ctx, video) -> None:
    """Character descriptions asked for by the picture step: copy the request, paste the answer, all in the app.

    Shown only while a request is written and unanswered; the next press of the step button then continues."""
    from studio import llm
    from studio.history import scene_plan

    work_dir = ctx.settings.project_dir(video.id)
    if not characters_waiting(ctx, video):
        return

    def check(c) -> None:
        llm._load_response(llm.prompt_paths(work_dir, "characters")[1], scene_plan.validate_characters)

    st.warning("The script names characters without a description. Ask Claude to describe them, then press the "
               "step button again to continue.")
    task_panel(ctx, video, "characters", check, "chr", primary_label="Save the descriptions")


def task_panel(ctx, video, task: str, run_fn, key: str, idea_id: int | None = None,
               primary_label: str = "Apply answer", plain_script: bool = False) -> None:
    """One LLM step fully in the app: Copy prompt, paste box, Apply button and status.

    `run_fn(ctx)` runs the stage that consumes the answer (it writes the request when none is waiting)."""
    prompt = svc.read_prompt(ctx, video.id, task)
    if not prompt:
        res = svc.capture(run_fn, ctx)
        if res.error and not res.pending:
            st.error(svc.plain_pending(res.error))
        prompt = svc.read_prompt(ctx, video.id, task, fresh=True)
    if not prompt:
        no_request_panel(ctx, video.id, task, run_fn, key)
        return
    st.markdown("**1.** Copy this request (copy icon, top right of the box) into Claude.")
    st.code(prompt, language="markdown", wrap_lines=True)
    st.markdown("**2.** Paste Claude's reply here. Fences or extra words around the JSON are fine.")
    pasted = answer_box(f"{key}_{task}{video.id}", height=220)
    if st.button(primary_label, type="primary", key=f"{key}_apply_{task}{video.id}"):
        if apply_answer(ctx, video.id, task, pasted, None if plain_script else run_fn, (), idea_id=idea_id):
            st.rerun()
    kept = svc.rejected_answer(ctx, video.id, task)
    if kept:
        with st.expander("Your last answer is kept here (not lost)"):
            st.code(kept, language="json", wrap_lines=True)
