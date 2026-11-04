"""The Script screen as one path: Plan story, Write script, Review. One action at a time, finished steps collapse."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from studio.stages import script as script_stage
from studio.stages import story as story_stage
from studio.web import handoff_ui, remedy_ui
from studio.web import service as svc
from studio.web import wizard_service as wiz

_ICON = {"done": "✅", "skipped": "➖", "now": "👉", "todo": "⬜"}


def _progress(flow: dict) -> None:
    total = len(flow["steps"])
    st.progress(flow["done_count"] / total, text=f"Script: {flow['done_count']} of {total} steps done")
    st.write("  →  ".join(f"{_ICON[s]} {label}" for _, label, s in flow["steps"]))


def copy_button(text: str, label: str = "📋 Copy the request", key: str = "copy") -> None:
    """A real copy-to-clipboard button (the request itself stays hidden)."""
    payload = json.dumps(text).replace("<", "\\u003c")
    html = f"""
<button id="b" style="font:600 15px sans-serif;padding:9px 18px;border-radius:8px;border:1px solid #ff4b4b;
background:#ff4b4b;color:#fff;cursor:pointer">{label}</button>
<script>
const t = {payload};
document.getElementById('b').onclick = async () => {{
  try {{ await navigator.clipboard.writeText(t); }}
  catch (e) {{ const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a);
    a.select(); document.execCommand('copy'); a.remove(); }}
  document.getElementById('b').textContent = '✅ Copied. Now paste it into Claude';
}};
</script>"""
    if hasattr(st, "iframe"):
        st.iframe(html, height=52)
    else:  # older Streamlit
        components.html(html, height=52)


def _step_panel(ctx, v, flow: dict, run) -> None:
    """Instruction, Copy button, collapsed request, one paste box, one Apply button."""
    task = flow["task"]
    prompt = svc.read_prompt(ctx, v.id, task)
    if not prompt:
        res = svc.capture(run, ctx)
        if res.error and not res.pending:
            remedy_ui.error_panel(res.error, key=f"scr_err{v.id}{task}", ctx=ctx, retry=lambda: svc.capture(run, ctx))
            return
        prompt = svc.read_prompt(ctx, v.id, task, fresh=True)
    if not prompt:
        handoff_ui.no_request_panel(ctx, v.id, task, run, "scr")
        return
    label = dict((k, n) for k, n, _ in flow["steps"])[flow["current"]]
    st.subheader(f"Now: {label}")
    st.write(flow["instruction"])
    st.markdown("**1.** Copy the request and paste it into Claude (claude.ai or Claude Code).")
    copy_button(prompt, key=task)
    with st.expander("Look at the request"):
        st.code(prompt, language="markdown", wrap_lines=True)
    st.markdown("**2.** Paste Claude's reply here.")
    key = f"scr_{task}{v.id}"
    pasted = st.text_area("Claude's reply", height=170, key=f"{key}_text", label_visibility="collapsed",
                          placeholder="Paste Claude's whole reply here. Extra words around it are fine.")
    with st.expander("Or upload the reply as a file"):
        up = st.file_uploader("Reply file", type=["json", "txt"], key=f"{key}_file")
        if up is not None:
            pasted = up.getvalue().decode("utf-8", errors="replace")
    if st.button("Apply Claude's reply", type="primary", key=f"{key}_apply"):
        if handoff_ui.apply_answer(ctx, v.id, task, pasted, run, ()):
            st.rerun()
    kept = svc.rejected_answer(ctx, v.id, task)
    if kept:
        with st.expander("Your last reply is kept here (not lost)"):
            st.code(kept, language="json", wrap_lines=True)


def _advanced(ctx, v, flow: dict) -> None:
    """Everything optional, in one place: nothing was removed, it is just out of the way."""
    with st.expander("Advanced (optional extras)"):
        sd = ctx.settings.project_dir(v.id) / "script.md"
        if sd.exists():
            with st.expander("Read the script so far"):
                st.markdown(sd.read_text(encoding="utf-8"))
        st.markdown("**Extra story tools**")
        _extra_task(ctx, v, "outline", "Extra story outline (hook options, open loops, beats)",
                    story_stage.run_outline, v.idea_id)
        if v.stage == "scripted":
            _extra_task(ctx, v, "critique", "Extra scored review and rewrite (older single-step version)",
                        story_stage.run_critique, v.id)
        if flow["current"] == "review" and st.button("Skip the review and approve the script", key=f"scr_skip{v.id}"):
            wiz.skip_review(ctx, v)
            st.rerun()
        if flow["current"] == "plan":
            st.caption("Not recommended: write the script without the story plan (no facts or open loops).")
            if st.button("Write the script without a plan", key=f"scr_noplan{v.id}"):
                res = svc.capture(script_stage.run, ctx, v.idea_id)
                if res.error and not res.pending:
                    st.error(svc.plain_pending(res.error))
                st.session_state[f"scr_plain{v.id}"] = True
        if st.session_state.get(f"scr_plain{v.id}") and v.stage != "scripted":
            prompt = svc.read_prompt(ctx, v.id)
            if prompt:
                copy_button(prompt, key="plain")
                pasted = st.text_area("Claude's reply (script)", height=150, key=f"scr_plain_text{v.id}")
                if st.button("Save script and check it", key=f"scr_plain_go{v.id}"):
                    if handoff_ui.apply_answer(ctx, v.id, "script", pasted, None, (), idea_id=v.idea_id):
                        st.rerun()
        if st.button("Run the next step automatically", key=f"scr_auto{v.id}"):
            res = svc.capture(script_stage.run, ctx, v.idea_id, auto=True)
            st.caption(svc.plain_pending(res.error) if res.error else "Done.")


def _extra_task(ctx, v, task: str, title: str, fn, arg: int) -> None:
    """Request / paste / apply for an optional extra task (outline, critique)."""
    with st.expander(title):
        if st.button("Write the request", key=f"req_{task}{v.id}"):
            res = svc.capture(fn, ctx, arg)
            if res.error and not res.pending:
                st.error(svc.plain_pending(res.error))
        prompt = svc.read_prompt(ctx, v.id, task)
        if prompt:
            copy_button(prompt, key=task)
            pasted = st.text_area("Reply", height=150, key=f"ans_{task}{v.id}")
            if st.button("Save and apply", key=f"save_{task}{v.id}"):
                if handoff_ui.apply_answer(ctx, v.id, task, pasted, fn, (arg,)):
                    st.rerun()


def render(ctx, v, on_continue, continue_label: str = "Continue to voice ➜", key: str = "scr") -> None:
    """Draw the whole Script path for video `v`. `on_continue` runs when the owner approves and moves on."""
    from studio.story import engine

    flow = wiz.script_flow(ctx, v)
    _progress(flow)
    if flow["current"] is None:
        st.success("✅ Your script is ready and approved.")
        st.button(continue_label, type="primary", on_click=on_continue, key=f"{key}_continue{v.id}")
        sd = ctx.settings.project_dir(v.id) / "script.md"
        if sd.exists():
            with st.expander("Read the script"):
                st.markdown(sd.read_text(encoding="utf-8"))
        _advanced(ctx, v, flow)
        return
    st.session_state[f"scr_active{v.id}"] = True
    run = (lambda c: engine.run_review(c, v)) if flow["legacy"] else (lambda c: engine.auto(c, v))
    _step_panel(ctx, v, flow, run)
    for _sid, label, state in flow["steps"]:
        if state in ("done", "skipped"):
            note = " (skipped, script came first)" if state == "skipped" else ""
            with st.expander(f"{_ICON[state]} {label}{note}"):
                st.caption("Finished." if state == "done" else "This script was written before the story plan.")
    _advanced(ctx, v, flow)
