"""Streamlit pieces shared by pages: the paste-or-upload box for Claude's JSON answer."""

from __future__ import annotations

import streamlit as st


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


def apply_answer(ctx, video_id: int, task: str, pasted: str, fn, args: tuple, idea_id: int | None = None) -> bool:
    """Save a pasted answer and run its step, always telling the user what happened.

    `task` is script, outline or critique. Success is flashed (so it shows after the rerun) and True is returned;
    the caller then calls st.rerun(). A failure is shown right here with the reason and what to fix.
    """
    from studio.web import service as svc

    with st.spinner("Checking your answer..."):
        if task == "script":
            res = svc.submit_script(ctx, idea_id, video_id, pasted)
        else:
            res = svc.submit_task(ctx, video_id, task, pasted, fn, *args)
    if res.ok:
        st.session_state["flash_ok"] = {"summary": res.summary or "Saved and applied.", "log": res.log.strip()}
        return True
    st.error("❌ Could not apply this answer, so nothing was saved.\n\n" + (res.error or "Unknown problem."))
    if res.log.strip():
        with st.expander("Details"):
            st.code(res.log)
    return False
