"""YouTube Channel Studio web app (Streamlit). Run: streamlit run app.py"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from studio.errors import StudioError
from studio.stages import research
from studio.stages import script as script_stage
from studio.stages import story as story_stage
from studio.stages.base import STAGES
from studio.web import handoff_ui, publish_ui, setup_ui, wizard_ui
from studio.web import service as svc
from studio.web.growth_ui import page_grow_factory

ROOT = Path(os.getenv("STUDIO_HOME") or Path(__file__).parent).resolve()
PAGES = ["🎬 Make a video", "Setup", "Home", "1. Topics", "2. Script", "3. Make the video", "4. Review and download",
         "5. Grow the channel", "📊 Analytics", "Channels", "Settings", "Data", "🧸 Kids mode"]

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
    elif res.problems:
        st.error("Claude's answer has a few problems. Nothing was lost: your answer is kept below.")
        for line in svc.plain_problems(res.problems):
            st.markdown(f"- {line}")
        st.markdown("**Fix it:** copy this (copy icon, top right of the box) and send it to Claude, "
                    "then paste the corrected answer back.")
        st.code(svc.fix_request(res.problems), language="markdown", wrap_lines=True)
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
    st.button("🎬 Make a video (guided, one page)", type="primary", on_click=handoff_ui.goto,
              args=("🎬 Make a video",))
    from studio.growth import channels
    if channels.type_info(ROOT)["mode"] == "kids":
        st.info("This is a **kids channel**. Make its videos on the **🧸 Kids mode** page, and set every upload to "
                "Made for Kids in YouTube Studio. The pages below are for narrated explainer channels.")
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
    from studio.growth import channel_types, channels
    prof = channels.get(ROOT)
    st.info(f"Topics for channel **{prof['name']}** · type: {channel_types.TYPES[prof['type']]['label']} · "
            f"niche: {prof['niche']}. Wrong channel? Switch it in the sidebar, or fix the type and niche on the "
            f"**Channels** page.")
    if st.session_state.get("seed_channel") != channels.active_id(ROOT):  # never carry one channel's seed to another
        st.session_state["seed"] = None
        st.session_state["seed_channel"] = channels.active_id(ROOT)
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


def task_block(ctx, v, title: str, help_text: str, task: str, fn, arg: int) -> None:
    """Request-for-Claude / paste-answer-back block for an optional story step (outline, critique)."""
    with st.expander(title):
        st.write(help_text)
        if st.button("Write the request", key=f"req_{task}{v.id}"):
            show(svc.capture(fn, ctx, arg))
        prompt = svc.read_prompt(ctx, v.id, task)
        if prompt:
            st.code(prompt, language="markdown", wrap_lines=True)
            pasted = handoff_ui.answer_box(f"ans_{task}{v.id}", height=240)
            if st.button("Save and apply", key=f"save_{task}{v.id}"):
                res = svc.submit_task(ctx, v.id, task, pasted, fn, arg)
                show(res, "Done.")
                if res.ok:
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
        task_block(ctx, v, "Improve the story: scored review and rewrite (recommended)",
                   "Claude scores the script on hook, stakes, open loops, pacing, concreteness, clarity, arc and "
                   "ending, then rewrites it. Do this before the voiceover.", "critique", story_stage.run_critique,
                   v.id)
        return
    task_block(ctx, v, "Step 0 (recommended): plan the story first",
               "A retention outline: hook options, open loops, beat sheet and ending. It is added to the script "
               "request automatically.", "outline", story_stage.run_outline, v.idea_id)
    if st.button("Step 1: write the request for Claude"):
        show(svc.capture(script_stage.run, ctx, v.idea_id))
    prompt = svc.read_prompt(ctx, v.id)
    if prompt:
        st.markdown("**Step 2.** Copy this (use the copy icon at the top right of the box) and paste it into Claude.")
        st.code(prompt, language="markdown", wrap_lines=True)
        st.markdown("**Step 3.** Paste Claude's JSON answer here. Length is up to you; there is no maximum.")
        pasted = handoff_ui.answer_box(f"resp{v.id}", height=300)
        if st.button("Save script and check it", type="primary"):
            res = svc.submit_script(ctx, v.idea_id, v.id, pasted)
            show(res, "Script accepted.")
            if res.ok:
                st.rerun()


SCENE_LABELS = {"": "(follow channel)", "2d": "2D motion graphics", "3d": "3D (Blender)",
                "mixed": "Mixed (3D scenes, 2D charts)"}


def _segment_style_inputs(ctx, video_id: int) -> dict[int, str]:
    """One 2D/3D picker per segment that has a scene or a bar/line chart; returns {position: choice}."""
    from studio import production, scenes
    from studio.stages.script import load_package

    try:
        segs = load_package(ctx, video_id)["segments"]
    except Exception:
        return {}
    cur, out = production.segment_styles(ctx.settings, video_id), {}
    rows = [(i, g) for i, g in enumerate(segs, 1) if g.get("scene") or scenes.chart_items(g)]
    if rows:
        st.caption("Per scene: 2D or 3D for just that part of the video (blank follows the video's setting).")
    for pos, g in rows:
        kind = (g.get("scene") or {}).get("kind", "chart3d")
        out[pos] = st.selectbox(f"Segment {pos}: {kind} ({g.get('chapter') or 'no chapter'})", ["", "2d", "3d"],
                                index=["", "2d", "3d"].index(cur.get(pos, "")), key=f"seg_style_{video_id}_{pos}",
                                format_func=lambda x: x.upper() if x else "(follow video)")
    return out


def _production_box(ctx, video_id: int) -> None:
    """Per-video renderer, voice and music (blank = follow the channel and its type)."""
    from studio import production
    from studio.growth import channel_types

    with st.expander("Look and sound for this video (3D, voice, music)"):
        st.code(production.describe(ctx.settings, video_id))
        cur = production.video_overrides(ctx.settings, video_id)
        with st.form(f"prod_{video_id}"):
            vals = {"renderer": st.selectbox("Picture renderer", channel_types.CHOICES["renderer"],
                                             index=channel_types.CHOICES["renderer"].index(cur.get("renderer", "")),
                                             format_func=lambda x: x or "(follow channel)",
                                             help="blender adds a 3D title intro (and 3D scenes in kids mode); "
                                                  "falls back to 2D if Blender is missing."),
                    "scene_style": st.selectbox(
                        "Scenes: 3D or 2D", channel_types.CHOICES["scene_style"],
                        index=channel_types.CHOICES["scene_style"].index(cur.get("scene_style", "")),
                        format_func=lambda x: SCENE_LABELS.get(x, x or "(follow channel)"),
                        help="3D = animated Blender scenes (timelines, maps, artifacts, 3D charts); 2D = motion "
                             "graphics; mixed = 3D scenes, plain 2D charts. Falls back to 2D if Blender is missing."),
                    "voice": st.text_input("Voice (edge-tts name)", cur.get("voice", "")),
                    "music": st.selectbox("Music", channel_types.CHOICES["music"],
                                          index=channel_types.CHOICES["music"].index(cur.get("music", "")),
                                          format_func=lambda x: x or "(follow channel)"),
                    "music_mood": st.selectbox("Music mood", channel_types.CHOICES["music_mood"],
                                               index=channel_types.CHOICES["music_mood"].index(
                                                   cur.get("music_mood", "")),
                                               format_func=lambda x: x or "(follow channel)")}
            seg_vals = _segment_style_inputs(ctx, video_id)
            if st.form_submit_button("Save for this video"):
                production.set_video(ctx.settings, video_id, **vals)
                for pos, style in seg_vals.items():
                    production.set_segment_style(ctx.settings, video_id, pos, style)
                st.rerun()
        if cur and st.button("Follow the channel again"):
            production.clear_video(ctx.settings, video_id)
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
    _production_box(ctx, v.id)
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


def show_player(ctx, video_id: int, final: Path) -> None:
    """Play a small 480p browser-safe preview; if that fails, say why and point to the download."""
    try:
        issues = svc.playback_issues(final)
        if issues:
            st.warning("The full-quality file may not play in a browser (" + "; ".join(issues) + "). "
                       "The preview below is converted so it plays; the download is unchanged.")
        with st.spinner("Preparing a preview (a short wait the first time)..."):
            prev = svc.ensure_preview(ctx, video_id)
        if prev is not None:
            st.video(str(prev))
            st.caption("This is a small 480p preview. Download below for full quality.")
    except StudioError as exc:
        st.error(f"Preview failed. You can still download the video below.\n\n{exc}")
    except Exception as exc:  # noqa: BLE001 - never let a preview problem hide the downloads
        st.error(f"The preview player could not start ({type(exc).__name__}: {exc}). "
                 "Download the video below and play it on your computer.")


def page_review() -> None:
    ctx = ctx_for()
    st.header("4. Review and download")
    v = video_picker(ctx, "rev_video")
    if v is None:
        st.info("No videos yet.")
        return
    files = svc.project_files(ctx, v.id)
    if files["video"]:
        show_player(ctx, v.id, files["video"][0])
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
    st.caption("You can simply download the video and upload it yourself. Publishing from here needs Google sign-in "
               "(Setup page), which only works when the app runs on your own computer.")
    publish_ui.render(ctx, ROOT, v, show)


def _signin_row(c: dict) -> None:
    """Show whether this channel has its own YouTube sign-in, with a Sign in button (works when run locally)."""
    from studio.config import load_settings
    from studio.manage import multi_analytics as ma
    from studio.youtube import auth

    s = load_settings(ROOT)
    cs = auth.settings_for(s, c["id"])
    st.caption(("✅ Signed in" if auth.is_signed_in(cs) else "⚪ Not signed in")
               + f" · own token: {cs.token_path.name} · YouTube channel: {c['youtube_channel_id'] or 'not set yet'}")
    if st.button("Sign in / switch account", key=f"signin_{c['id']}",
                 help="Opens Google sign-in on the computer running the app. On a hosted app use "
                      "`python -m studio.cli channels sign-in " + c["id"] + "` on your own computer."):
        try:
            r = ma.sign_in(s, c["id"])
            st.success(f"Signed in as {r['title'] or r['youtube_channel_id']}.")
            st.rerun()
        except StudioError as exc:
            st.error(str(exc))


def page_analytics() -> None:
    from studio.web import analytics_ui

    analytics_ui.render(ROOT)


def page_channels() -> None:
    from studio.growth import channel_types, channels

    st.header("Channels")
    st.write("Add as many channels as you like and switch any time. Everything (prompts, voice, posting plan) "
             "uses the active channel chosen in the sidebar.")
    rows = channels.list_channels(ROOT)
    for c in rows:
        with st.expander(f"{'⭐ ' if c['active'] else ''}{c['name']} · {c['niche']}", expanded=c["active"]):
            with st.form(f"edit_{c['id']}"):
                a, b = st.columns(2)
                vals = {
                    "name": a.text_input("Channel name", c["name"]),
                    "niche": a.text_input("Niche", c["niche"]),
                    "description": a.text_area("Description", c["description"]),
                    "audience": a.text_input("Target audience", c["audience"]),
                    "type": a.selectbox("Channel type", list(channel_types.TYPES),
                                        index=list(channel_types.TYPES).index(c["type"]),
                                        format_func=lambda k: channel_types.TYPES[k]["label"],
                                        help="Kids channels use Kids mode and Made for Kids. Others use the "
                                             "narrated explainer pipeline."),
                    "language": b.text_input("Language", c["language"]),
                    "posts_per_week": b.number_input("Posting frequency (long videos per week)", 1, 14,
                                                     int(c["posts_per_week"])),
                    "voice": b.text_input("Voice (blank = default from settings)", c["voice"]),
                    "youtube_channel_id": b.text_input("YouTube channel ID (optional)", c["youtube_channel_id"]),
                    "renderer": b.selectbox("Picture renderer", channel_types.CHOICES["renderer"],
                                            index=channel_types.CHOICES["renderer"].index(c["renderer"]),
                                            format_func=lambda x: x or "(default from settings)", key=f"r_{c['id']}"),
                    "scene_style": b.selectbox("Scenes: 3D or 2D", channel_types.CHOICES["scene_style"],
                                               index=channel_types.CHOICES["scene_style"].index(c["scene_style"]),
                                               format_func=lambda x: SCENE_LABELS.get(x, x or "(type default)"),
                                               key=f"ss_{c['id']}",
                                               help="History and business default to Mixed; kids and general to 2D. "
                                                    "Needs Blender 4.2+ for 3D, otherwise 2D is used."),
                    "music": b.selectbox("Music", channel_types.CHOICES["music"],
                                         index=channel_types.CHOICES["music"].index(c["music"]),
                                         format_func=lambda x: x or "(automatic)", key=f"m_{c['id']}"),
                    "music_mood": b.selectbox("Music mood", channel_types.CHOICES["music_mood"],
                                              index=channel_types.CHOICES["music_mood"].index(c["music_mood"]),
                                              format_func=lambda x: x or "(type default)", key=f"mm_{c['id']}"),
                }
                if st.form_submit_button("Save"):
                    channels.update(ROOT, c["id"], **vals)
                    st.rerun()
            _signin_row(c)
            b1, b2 = st.columns(2)
            if not c["active"] and b1.button("Make active", key=f"use_{c['id']}"):
                channels.switch(ROOT, c["id"])
                st.rerun()
            if len(rows) > 1 and b2.button("Delete", key=f"del_{c['id']}"):
                channels.remove(ROOT, c["id"])
                st.rerun()
    with st.form("add_channel"):
        st.subheader("Add a channel")
        name = st.text_input("Channel name")
        ctype = st.selectbox("Channel type", list(channel_types.TYPES),
                             format_func=lambda k: channel_types.TYPES[k]["label"])
        niche = st.text_input("Niche (blank = the type's default)", placeholder="e.g. personal finance for students")
        desc = st.text_area("Description")
        freq = st.number_input("Posting frequency (long videos per week)", 1, 14, 2)
        voice = st.text_input("Voice (edge-tts name, optional)", placeholder="en-US-AndrewNeural")
        if st.form_submit_button("Add and switch to it") and name.strip():
            channels.add(ROOT, name, type=ctype, niche=niche or None, description=desc,
                         posts_per_week=int(freq), voice=voice.strip())
            st.rerun()
    st.divider()
    st.write("Hosted storage is temporary. Download your channels now and then, and upload them again after a restart.")
    st.download_button("⬇️ Download channels.json", channels.export_json(ROOT), "channels.json", "application/json")
    up = st.file_uploader("Restore channels.json", type="json")
    if up is not None and st.button("Import"):
        try:
            done = channels.import_json(ROOT, up.getvalue().decode("utf-8"))
            st.success(f"Imported {len(done)} new channel(s).")
        except StudioError as exc:
            st.error(str(exc))


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


def page_wizard() -> None:
    wizard_ui.render(ctx_for, show, show_player, _production_box)


def page_setup() -> None:
    setup_ui.render(ctx_for, show)


def page_kids() -> None:
    from studio.kids import page

    page.render(ctx_for, show)


page_grow = page_grow_factory(ctx_for, video_picker, show)


def page_data() -> None:
    from studio.web import data_ui

    data_ui.render(ctx_for, ROOT)


def main() -> None:
    gate()
    from studio.web import data_ui

    data_ui.boot(ROOT, _secrets())
    st.sidebar.title("🎬 Studio")
    from studio.growth import channels

    rows = channels.list_channels(ROOT)
    ids = [c["id"] for c in rows]
    names = {c["id"]: c["name"] for c in rows}
    active = channels.active_id(ROOT)
    chosen = st.sidebar.selectbox("Channel", ids, index=ids.index(active), format_func=names.get)
    if chosen != active:
        channels.switch(ROOT, chosen)
        st.rerun()
    page = st.sidebar.radio("Go to", PAGES, key="nav", label_visibility="collapsed")
    try:
        {"🎬 Make a video": page_wizard, "Setup": page_setup,
         "Home": page_home, "1. Topics": page_topics, "2. Script": page_script, "3. Make the video": page_make,
         "4. Review and download": page_review, "5. Grow the channel": page_grow,
         "📊 Analytics": page_analytics,
         "Channels": page_channels, "Settings": page_settings, "Data": page_data,
         "🧸 Kids mode": page_kids}[page]()
    except StudioError as exc:
        st.error(str(exc))
    data_ui.tick(ROOT)


main()
