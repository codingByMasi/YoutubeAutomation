"""YouTube Channel Studio web app (Streamlit). Run: streamlit run app.py"""

from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path

import streamlit as st

from studio.errors import StudioError
from studio.stages import research, review
from studio.stages import script as script_stage
from studio.stages.base import STAGES
from studio.web import growth_service as gsvc
from studio.web import service as svc
from studio.web.growth_ui import page_grow_factory

ROOT = Path(os.getenv("STUDIO_HOME") or Path(__file__).parent).resolve()
PAGES = ["Home", "1. Topics", "2. Script", "3. Make the video", "4. Review and download",
         "5. Grow the channel", "Settings", "🧸 Kids mode"]

st.set_page_config(page_title="YouTube Channel Studio", page_icon="🎬", layout="wide")


def _secrets() -> dict:
    try:
        return dict(st.secrets)
    except Exception:  # noqa: BLE001 - no secrets file locally is normal
        return {}


def gate() -> None:
    """Optional password (APP_PASSWORD secret). Strongly advised on a public deployment."""
    pw = _secrets().get("APP_PASSWORD") or os.getenv("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    st.title("🎬 YouTube Channel Studio")
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.error("Wrong password.")
    st.stop()


def ctx_for(confirm=None):
    """Fresh context per call (cheap), with Streamlit secrets and in-session keys applied first."""
    svc.apply_secrets(_secrets())
    svc.apply_secrets(st.session_state.get("session_keys", {}))
    return svc.make_ctx(ROOT, confirm)


def show(res: svc.Outcome, success: str = "Done.") -> None:
    """Render a stage outcome: success or the CLI-style error, plus the log."""
    if res.ok:
        st.success(success)
    elif res.pending:
        st.info("Waiting for the script. Follow the steps below.")
    else:
        st.error(res.error)
    if res.log.strip():
        with st.expander("Details"):
            st.code(res.log)


def video_picker(ctx, key: str, stages: tuple[str, ...] | None = None):
    vids = [v for v in svc.list_videos(ctx) if not stages or v.stage in stages]
    if not vids:
        return None
    labels = {v.id: f"#{v.id} · {svc.video_title(ctx, v)[:70]} · {v.stage}" for v in vids}
    vid = st.selectbox("Video", list(labels), format_func=labels.get, key=key)
    return next(v for v in vids if v.id == vid)


# ---------------- pages ----------------
def page_home() -> None:
    ctx = ctx_for()
    st.title("🎬 YouTube Channel Studio")
    st.write("Work down the pages on the left: pick a topic, get the script written, let the studio make the "
             "video, then review and download it. Nothing is ever published without you typing `yes`.")
    vids = svc.list_videos(ctx)
    if not vids:
        st.info("No videos yet. Start at **1. Topics**. Want a quick test with no keys? Use the demo below.")
    for v in vids:
        c1, c2 = st.columns([3, 2])
        c1.write(f"**#{v.id}** {svc.video_title(ctx, v)}")
        c2.progress(svc.stage_progress(v.stage), text=v.stage)
    with st.expander("Dry run (no keys needed)"):
        st.caption("Builds a short sample video with generated cards and silent narration, to prove the "
                   "app works on this machine.")
        if st.button("Build the demo video"):
            from studio.manage import demo

            with st.spinner("Building the demo (about a minute)..."):
                show(svc.capture(demo.run, ctx), "Demo built. Find it under 4. Review and download.")


def page_topics() -> None:
    ctx = ctx_for()
    st.header("1. Pick a topic")
    st.write("Don't have an idea? Let the studio find some. It avoids topics you already saved or used.")
    if st.button("✨ Suggest topics for me", type="primary"):
        with st.spinner("Looking for fresh ideas..."):
            res = svc.auto_suggest_topics(ctx)
        show(res, "New ideas added below.")
        st.session_state["seed"] = "auto"
    with st.expander("Or ask Claude for ideas (no AI key needed)"):
        st.caption("Copy this into Claude (claude.ai or Claude Code), then paste its answer back here.")
        st.code(svc.ideas_prompt(ctx), language="text")
        answer = st.text_area("Claude's answer", key="claude_ideas")
        if st.button("Add these ideas", disabled=not answer.strip()):
            res = svc.import_claude_ideas(ctx, answer)
            show(res, "Ideas added below.")
            st.session_state["seed"] = "claude"
    st.divider()
    seed = st.text_input("Or expand your own seed idea", placeholder="how cruise lines make money")
    c1, c2 = st.columns(2)
    force = c2.checkbox("Fetch fresh results today")
    if c1.button("Suggest topics", type="primary", disabled=not seed.strip()):
        with st.spinner("Searching..."):
            res = svc.suggest_topics(ctx, seed.strip(), force=force)
        show(res, "Ideas saved below.")
        st.session_state["seed"] = seed.strip()
    has_data = svc.has_competitor_data(ctx)
    st.caption("On the hosted app, topics come from YouTube search suggestions. Run locally and sign in to Google "
               "to also see small-channel outlier signals.")
    with st.expander("What does the score mean?"):
        st.markdown(
            "- **Demand (0-10):** how high YouTube's own search box ranks this phrase, so people really type it. "
            "10 is the top suggestion. With Google sign-in it also uses the views of recent matching videos.\n"
            "- **Competition (0-10):** how big the channels already covering it are (median subscribers). "
            "Low means a small channel can win. Shown as *n/a* until you sign in to Google, because the hosted "
            "app cannot see competitors.\n"
            "- **Score** = demand - competition + outlier bonus (small channels whose video beat their size). "
            "Higher is better. Treat it as a rough guide, not a promise.")
    with st.expander("Or type your own topic"):
        own = st.text_input("Topic", key="own_topic")
        if st.button("Add topic", disabled=not own.strip()):
            svc.add_manual_topic(ctx, own)
            st.rerun()
    used = svc.used_topics(ctx)
    if used:
        with st.expander(f"Topics you already used ({len(used)})"):
            for u in used:
                st.write("✅ " + u.topic)
    ideas = svc.ideas_for(ctx, st.session_state.get("seed") or None) or svc.ideas_for(ctx)
    if not ideas:
        return
    st.subheader("Ideas, best first")
    for i in ideas[:30]:
        c1, c2, c3 = st.columns([6, 3, 2])
        c1.write(i.topic)
        comp = f"{i.competition_score:.0f}" if has_data else "n/a"
        c2.caption(f"score {i.rank_score:.1f} · demand {i.demand_score:.0f}/10 · competition {comp} · {i.status}")
        if i.status == "approved":
            c3.write("✅ approved")
        elif c3.button("Use this", key=f"use{i.id}"):
            research.approve(ctx, i.id)
            st.success("Approved. Continue to **2. Script**.")
            st.rerun()


def page_script() -> None:
    ctx = ctx_for()
    st.header("2. Script")
    st.write("No AI key needed. The studio writes a request; you paste it into Claude (claude.ai or Claude Code), "
             "then paste the answer back.")
    v = video_picker(ctx, "script_video", ("approved", "scripted"))
    if v is None:
        st.info("Approve a topic first on **1. Topics**.")
        return
    if v.stage == "scripted":
        st.success("This video already has a script. Move on to **3. Make the video**.")
        sd = ctx.settings.project_dir(v.id) / "script.md"
        if sd.exists():
            with st.expander("Read the script"):
                st.markdown(sd.read_text(encoding="utf-8"))
        return
    if st.button("Step 1: write the request for Claude"):
        show(svc.capture(script_stage.run, ctx, v.idea_id))
    prompt = svc.read_prompt(ctx, v.id)
    if prompt:
        st.markdown("**Step 2.** Copy this (use the copy icon at the top right of the box) and paste it into Claude.")
        st.code(prompt, language="markdown", wrap_lines=True)
        st.markdown("**Step 3.** Paste Claude's JSON answer here. Length is up to you; there is no maximum.")
        pasted = st.text_area("Claude's answer (JSON)", height=300, key=f"resp{v.id}")
        if st.button("Save script and check it", type="primary"):
            res = svc.submit_script(ctx, v.idea_id, v.id, pasted)
            show(res, "Script accepted.")
            if res.ok:
                st.rerun()


def page_make() -> None:
    ctx = ctx_for()
    st.header("3. Make the video")
    v = video_picker(ctx, "make_video", ("scripted", "voiced", "visuals_ready", "built", "thumbnailed", "reviewed"))
    if v is None:
        st.info("Finish a script first on **2. Script**.")
        return
    labels = [f"{'✅' if STAGES.index(v.stage) > STAGES.index(s_done) else '⬜'} {svc.STAGE_LABEL[s]}"
              for s, s_done in zip(svc.PRODUCE_STAGES, ["scripted", "voiced", "visuals_ready", "built"])]
    st.write("  →  ".join(labels))
    nxt = svc.next_produce_stage(v)
    if nxt is None:
        st.success("Production is finished. Go to **4. Review and download**.")
    draft = st.checkbox("Fast draft (720p, quicker encode): about 2-3x faster editing, for checking the story",
                        key="draft", help="For the final version, untick this and redo 'Edit the video'.")
    c1, c2 = st.columns(2)
    if nxt and c1.button(f"Run next step: {svc.STAGE_LABEL[nxt]}"):
        with st.spinner(f"{svc.STAGE_LABEL[nxt]}..."):
            show(svc.run_stage_by_name(ctx, nxt, v.id, draft=draft), f"{svc.STAGE_LABEL[nxt]} done.")
    if nxt and c2.button("Run everything to the end", type="primary"):
        bar = st.progress(0.0)
        todo = svc.PRODUCE_STAGES[svc.PRODUCE_STAGES.index(nxt):]
        for n, name in enumerate(todo):
            bar.progress(n / len(todo), text=f"{svc.STAGE_LABEL[name]}...")
            res = svc.run_stage_by_name(ctx, name, v.id, draft=draft)
            if not res.ok:
                show(res)
                break
        else:
            bar.progress(1.0, text="All done")
            st.success("Video made. Go to **4. Review and download**.")
    if STAGES.index(v.stage) >= STAGES.index("built") and st.button("Also cut 2-3 Shorts"):
        with st.spinner("Cutting Shorts..."):
            show(svc.run_stage_by_name(ctx, "shorts", v.id, draft=draft), "Shorts ready.")
    with st.expander("Redo a step"):
        redo = st.selectbox("Step", svc.PRODUCE_STAGES, format_func=svc.STAGE_LABEL.get)
        if st.button("Redo it (later steps must be re-run)"):
            with st.spinner("Working..."):
                show(svc.run_stage_by_name(ctx, redo, v.id, force=True, draft=draft))


def page_review() -> None:
    ctx = ctx_for()
    st.header("4. Review and download")
    v = video_picker(ctx, "rev_video")
    if v is None:
        st.info("No videos yet.")
        return
    files = svc.project_files(ctx, v.id)
    if files["video"]:
        st.video(str(files["video"][0]))
    else:
        st.info("The video is not built yet. See **3. Make the video**.")
    cols = st.columns(3)
    for idx, p in enumerate(files["thumbnails"]):
        cols[idx % 3].image(str(p), caption=p.name)
    st.subheader("Download")
    for group, paths in files.items():
        for p in paths:
            with open(p, "rb") as fh:
                st.download_button(f"{group}: {p.name}", fh.read(), file_name=f"video{v.id}_{p.name}", key=f"dl{p}")
    if any(files.values()):
        st.download_button("Everything as a .zip", svc.zip_outputs(ctx, v.id), file_name=f"video{v.id}.zip",
                           key=f"zip{v.id}")
    st.divider()
    st.subheader("Approve and publish (optional)")
    st.caption("You can simply download the video and upload it yourself. Publishing from here needs Google sign-in, "
               "which only works when the app runs on your own computer.")
    if v.stage not in ("thumbnailed", "reviewed", "scheduled", "live"):
        return
    fc_ok = v.stage in ("reviewed", "scheduled", "live") or gsvc.fact_check_passed(ctx, v.id)
    if not fc_ok:
        st.warning("Finish the **fact and source checklist** first (5. Grow the channel, Fact check tab). "
                   "It must be complete before you can approve.")
    thumb = st.radio("Thumbnail", [1, 2, 3], horizontal=True)
    typed = st.text_input("Type yes to approve this video for publishing", key=f"yes1{v.id}")
    if fc_ok and st.button("Run the pre-publish checklist"):
        res = svc.capture(review.run, svc.make_ctx(ROOT, lambda _p: typed), v.id, thumb=thumb)
        show(res, "Approved. You can now publish.")
    if v.stage == "reviewed":
        if not ctx.settings.client_secret.exists():
            st.warning("Publishing needs client_secret.json (README section 3). Download the video instead, or run "
                       "the app locally.")
            return
        when = st.date_input("Publish date", min_value=date.today())
        at_time = st.time_input("Publish time (local)", value=time(18, 0))
        typed2 = st.text_input("Type yes again to upload", key=f"yes2{v.id}")
        if st.button("Upload to YouTube (private, scheduled)"):
            from studio.stages import publish

            res = svc.capture(publish.run, svc.make_ctx(ROOT, lambda _p: typed2), v.id,
                              at=f"{when:%Y-%m-%d} {at_time:%H:%M}")
            show(res, "Uploaded.")


def page_settings() -> None:
    ctx = ctx_for()
    s = ctx.settings
    st.header("Settings")
    st.write("Keys come from Streamlit **secrets** when hosted (App settings → Secrets) or from `.env` locally. "
             "Values below show only whether each is set.")
    rows = {"Pexels (stock video)": s.pexels_api_key, "Pixabay (video and photos)": s.pixabay_api_key,
            "ElevenLabs (optional voice)": s.elevenlabs_api_key, "Channel ID": s.channel_id}
    for name, val in rows.items():
        st.write(f"{'✅' if val else '⬜'} {name}")
    st.write(f"Voice: `{s.tts_provider}` / `{s.tts_voice}` · Footage: `{s.footage_provider}` · "
             f"Photos: `{s.image_provider}` · Script writer: `{s.llm_provider}`")
    with st.expander("Try a key for this session only"):
        st.caption("Held in memory until you close the tab; never written to disk.")
        keys = st.session_state.setdefault("session_keys", {})
        for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY"):
            val = st.text_input(k, type="password", key=f"in_{k}")
            if val:
                keys[k] = val
        if keys:
            st.success(f"{len(keys)} key(s) active for this session.")
    with st.expander("Recent log"):
        st.code(svc.log_tail(ctx) or "No log yet.")
    st.write(f"Hosted storage is temporary: download videos from step 4 before the app sleeps. Quota today: "
             f"{ctx.quota.summary()['units']['used']} units.")


def page_kids() -> None:
    from studio.kids import page

    page.render(ctx_for, show)


page_grow = page_grow_factory(ctx_for, video_picker, show)


def main() -> None:
    gate()
    st.sidebar.title("🎬 Studio")
    page = st.sidebar.radio("Go to", PAGES, label_visibility="collapsed")
    try:
        {"Home": page_home, "1. Topics": page_topics, "2. Script": page_script, "3. Make the video": page_make,
         "4. Review and download": page_review, "5. Grow the channel": page_grow,
         "Settings": page_settings, "🧸 Kids mode": page_kids}[page]()
    except StudioError as exc:
        st.error(str(exc))


main()
