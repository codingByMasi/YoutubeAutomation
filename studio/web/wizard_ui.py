"""One-page guided "Make a video" wizard: topic, script, make, review, publish. One clear next action at a time."""

from __future__ import annotations

import json

import streamlit as st

from studio.growth import channels
from studio.stages import qa, research
from studio.stages import script as script_stage
from studio.stages import story as story_stage
from studio.stages.base import STAGES
from studio.web import handoff_ui, publish_ui
from studio.web import service as svc
from studio.web import setup_service as setup
from studio.web import wizard_service as wiz


def _progress(step: str) -> None:
    labels = [f"{'✅' if wiz.step_number(s) < wiz.step_number(step) else '👉' if s == step else '⬜'} {n}"
              for s, n in wiz.STEPS]
    st.progress(wiz.step_number(step) / len(wiz.STEPS))
    st.write("  →  ".join(labels))


def _set_video(video_id: int | None) -> None:
    st.session_state["wiz_vid"] = video_id


def step_topic(ctx, show) -> None:
    st.subheader("Step 1 · Pick a topic")
    if st.button("✨ Suggest topics for me", type="primary", key="wz_suggest"):
        with st.spinner("Looking for fresh ideas..."):
            show(svc.auto_suggest_topics(ctx), "New ideas added below.")
    ideas = [i for i in svc.ideas_for(ctx) if i.status != "approved"][:6]
    for i in ideas:
        c1, c2 = st.columns([6, 2])
        c1.write(i.topic)
        if c2.button("Use this", key=f"wz_use{i.id}"):
            _set_video(research.approve(ctx, i.id).id)
            st.rerun()
    st.markdown("**Or type your own topic**")
    own = st.text_input("Topic", placeholder="how Costco makes money", key="wz_own", label_visibility="collapsed")
    if st.button("Use my topic", disabled=not own.strip(), key="wz_own_btn"):
        _set_video(research.approve(ctx, svc.add_manual_topic(ctx, own).id).id)
        st.rerun()


def _critique_box(ctx, v) -> None:
    prompt = svc.read_prompt(ctx, v.id, "critique")
    if st.button("Write the review request", key=f"wz_creq{v.id}"):
        show_local = svc.capture(story_stage.run_critique, ctx, v.id)
        if show_local.error and not show_local.pending:
            st.error(show_local.error)
        prompt = svc.read_prompt(ctx, v.id, "critique")
    if prompt:
        st.code(prompt, language="markdown", wrap_lines=True)
        pasted = handoff_ui.answer_box(f"wz_cans{v.id}", height=200)
        if st.button("Apply the rewrite", key=f"wz_capply{v.id}", disabled=not pasted.strip()):
            res = svc.submit_task(ctx, v.id, "critique", pasted, story_stage.run_critique, v.id)
            if res.ok:
                st.success("Script improved.")
                st.rerun()
            else:
                st.error(res.error)


def step_script(ctx, v, show) -> None:
    st.subheader("Step 2 · Get the script written")
    st.write("No AI key needed. The studio prepares a request; Claude writes the script; you bring the answer back.")
    prompt = svc.read_prompt(ctx, v.id)
    if st.button("1. Write the request for Claude", type="primary" if not prompt else "secondary", key="wz_sreq"):
        show(svc.capture(script_stage.run, ctx, v.idea_id))
        prompt = svc.read_prompt(ctx, v.id)
    if prompt:
        st.markdown("**2.** Copy this (copy icon, top right of the box) into Claude on claude.ai or Claude Code.")
        st.code(prompt, language="markdown", wrap_lines=True)
        st.markdown("**3.** Paste Claude's JSON answer here, or upload the file.")
        pasted = handoff_ui.answer_box(f"wz_sans{v.id}")
        if st.button("Save script and check it", type="primary", key="wz_ssave", disabled=not pasted.strip()):
            res = svc.submit_script(ctx, v.idea_id, v.id, pasted)
            show(res, "Script accepted.")
            if res.ok:
                st.rerun()


def _qa_panel(ctx, v) -> None:
    f = ctx.settings.project_dir(v.id) / "qa.json"
    if st.button("Check script quality", key=f"wz_qa{v.id}"):
        res = svc.capture(qa.run, ctx, v.id)
        if not res.ok:
            st.error(res.error)
    if f.exists():
        rep = json.loads(f.read_text(encoding="utf-8"))
        msg = f"Quality score {rep['score']}/100 for {rep['minutes']} min."
        (st.success if rep["score"] >= 80 else st.warning)(msg)
        for w in rep.get("warnings", [])[:8]:
            st.caption(f"• {w}")


def _voice_picker(ctx, v) -> None:
    s = ctx.settings
    if s.tts_provider != "edge":
        st.caption(f"Voice: {s.tts_provider} / {s.tts_voice} (change on the Setup page).")
        return
    voices = dict(setup.VOICES)
    if s.tts_voice not in voices:
        voices[s.tts_voice] = s.tts_voice
    choice = st.selectbox("Narration voice", list(voices), index=list(voices).index(s.tts_voice),
                          format_func=voices.get, key="wz_voice")
    if choice != s.tts_voice:
        channels.update(s.root, voice=choice)
        st.rerun()
    st.caption("Hear samples on the Setup page. Saved for this channel.")


def step_make(ctx, v, show) -> None:
    st.subheader("Step 3 · Make the video")
    nxt = svc.next_produce_stage(v)
    if v.stage == "scripted":
        with st.expander("Optional but recommended: have Claude score and rewrite the script first"):
            st.write("Claude scores hook, stakes, pacing and ending, then returns a stronger script.")
            _critique_box(ctx, v)
        with st.expander("Optional: read the script"):
            sd = ctx.settings.project_dir(v.id) / "script.md"
            if sd.exists():
                st.markdown(sd.read_text(encoding="utf-8"))
        _voice_picker(ctx, v)
        _qa_panel(ctx, v)
    draft = st.checkbox("Fast draft (720p, quicker) to check the story first", key="wz_draft")
    labels = [f"{'✅' if STAGES.index(v.stage) > STAGES.index(d) else '⬜'} {svc.STAGE_LABEL[s]}"
              for s, d in zip(svc.PRODUCE_STAGES, ["scripted", "voiced", "visuals_ready", "built"])]
    st.write("  →  ".join(labels))
    if nxt and st.button("🎬 Make my video", type="primary", key="wz_make"):
        bar = st.progress(0.0)
        todo = svc.PRODUCE_STAGES[svc.PRODUCE_STAGES.index(nxt):]
        for n, name in enumerate(todo):
            bar.progress(n / len(todo), text=f"{svc.STAGE_LABEL[name]}... (this can take a few minutes)")
            res = svc.run_stage_by_name(ctx, name, v.id, draft=draft)
            if not res.ok:
                show(res)
                break
        else:
            st.rerun()


def step_review(ctx, v, show, show_player) -> None:
    st.subheader("Step 4 · Watch it and choose a thumbnail")
    files = svc.project_files(ctx, v.id)
    if files["video"]:
        show_player(ctx, v.id, files["video"][0])
    cols = st.columns(3)
    for idx, p in enumerate(files["thumbnails"]):
        cols[idx % 3].image(str(p), caption=f"Thumbnail {idx + 1}")
    root = ctx.settings.root
    publish_ui.render(ctx, root, v, show, key="wz")
    st.download_button("⬇️ Or download everything (.zip)", svc.zip_outputs(ctx, v.id), file_name=f"video{v.id}.zip",
                       key=f"wz_zip{v.id}")


def step_publish(ctx, v, show) -> None:
    st.subheader("Step 5 · Schedule and publish")
    publish_ui.render(ctx, ctx.settings.root, v, show, key="wzp")
    st.download_button("⬇️ Download everything (.zip)", svc.zip_outputs(ctx, v.id), file_name=f"video{v.id}.zip",
                       key=f"wz_zipp{v.id}")
    if wiz.finished(v):
        st.button("Start another video", on_click=_set_video, args=(None,), key="wz_again")


def render(ctx_for, show, show_player) -> None:
    """Draw the wizard page."""
    ctx = ctx_for()
    prof = channels.get(ctx.settings.root)
    st.header("🎬 Make a video")
    tinfo = channels.type_info(ctx.settings.root)
    st.caption(f"Channel: **{prof['name']}** · {tinfo['label']}")
    if tinfo["mode"] == "kids":
        st.info("This is a kids channel, so the wizard is the Kids mode builder below. It never uploads anything.")
        from studio.kids import page

        page.render(ctx_for, show)
        return
    blockers = setup.blocking(ctx.settings)
    if blockers:
        st.warning("Before you start: " + "; ".join(c.message for c in blockers[:2]))
        st.button("Open Setup to fix this", on_click=handoff_ui.goto, args=("Setup",), key="wz_setup")
    if "wiz_vid" not in st.session_state:
        st.session_state["wiz_vid"] = getattr(wiz.resume_video(ctx), "id", None)
    vids = {x.id: x for x in svc.list_videos(ctx)}
    v = vids.get(st.session_state["wiz_vid"])
    step = wiz.step_for(v)
    _progress(step)
    if v is not None:
        c1, c2 = st.columns([5, 2])
        c1.write(f"**#{v.id}** {svc.video_title(ctx, v)}")
        c2.button("Start a different video", on_click=_set_video, args=(None,), key="wz_new")
    {"topic": lambda: step_topic(ctx, show), "script": lambda: step_script(ctx, v, show),
     "make": lambda: step_make(ctx, v, show), "review": lambda: step_review(ctx, v, show, show_player),
     "publish": lambda: step_publish(ctx, v, show)}[step]()
