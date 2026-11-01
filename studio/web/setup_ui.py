"""The Setup page: a friendly readiness checklist with a control and guided steps for each item."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from studio.errors import StudioError
from studio.growth import channels
from studio.manage import doctor
from studio.web import handoff_ui
from studio.web import setup_service as setup

ICON = {doctor.OK: "✅", doctor.WARN: "🟡", doctor.FAIL: "🔴"}
SECTIONS = [("ffmpeg", "Video tools (ffmpeg)"), ("llm", "Script writer"), ("voice", "Narration voice"),
            ("footage", "Footage and photos (optional)"), ("client_secret", "Google client file (for uploading)"),
            ("channel_id", "YouTube channel ID"), ("signin", "Sign in to Google")]


def _save(root: Path, values: dict, ok: str = "Saved.") -> None:
    try:
        setup.save_env(root, values)
        st.success(ok)
    except StudioError as exc:
        st.error(str(exc))


def _ffmpeg(ctx) -> None:
    st.markdown(setup.HOWTO["ffmpeg"])
    st.button("Check again", key="recheck_ffmpeg")


def _llm(ctx) -> None:
    s = ctx.settings
    st.markdown(setup.HOWTO["llm"])
    opts = ["claude_code", "anthropic", "openai", "gemini"]
    prov = st.selectbox("Who writes the scripts?", opts, index=opts.index(s.llm_provider) if s.llm_provider in opts
                        else 0, format_func=lambda p: "Claude Code / paste-in (no key needed)"
                        if p == "claude_code" else p, key="set_llm")
    key = st.text_input("API key (only for the API providers)", type="password", key="set_llm_key") \
        if prov != "claude_code" else ""
    if st.button("Save script writer", key="save_llm"):
        _save(ctx.settings.root, {"LLM_PROVIDER": prov, **({"LLM_API_KEY": key} if key else {})})


def _voice(ctx) -> None:
    s = ctx.settings
    st.markdown(setup.HOWTO["voice"])
    provs = ["edge", "eleven", "silent"]
    prov = st.selectbox("Voice service", provs, index=provs.index(s.tts_provider) if s.tts_provider in provs else 0,
                        format_func={"edge": "edge (free, recommended)", "eleven": "ElevenLabs (needs a key)",
                                     "silent": "silent (test videos only)"}.get, key="set_tts")
    voices = dict(setup.VOICES)
    if s.tts_voice not in voices:
        voices[s.tts_voice] = s.tts_voice
    voice = st.selectbox("Voice", list(voices), index=list(voices).index(s.tts_voice), format_func=voices.get,
                         key="set_voice", disabled=prov == "silent")
    key = st.text_input("ElevenLabs key", type="password", key="set_eleven") if prov == "eleven" else ""
    c1, c2 = st.columns(2)
    if c1.button("Save voice", key="save_voice"):
        _save(s.root, {"TTS_PROVIDER": prov, "TTS_VOICE": voice, **({"ELEVENLABS_API_KEY": key} if key else {})},
              "Saved. Channels with their own voice (Channels page) keep it.")
    if c2.button("🔊 Hear a sample", key="voice_sample", disabled=prov != "edge"):
        try:
            with st.spinner("Making a sample (needs internet)..."):
                path = setup.voice_sample(s, voice, Path(tempfile.mkdtemp(prefix="voice_")))
            st.audio(path.read_bytes(), format="audio/mp3")
        except Exception as exc:  # noqa: BLE001 - show any network/TTS problem plainly
            st.error(f"Could not make a sample: {exc}\nCheck your internet connection and try again.")


def _footage(ctx) -> None:
    st.markdown(setup.HOWTO["footage"])
    pix = st.text_input("Pixabay key", type="password", key="set_pix")
    pex = st.text_input("Pexels key (only if you already have one)", type="password", key="set_pex")
    if st.button("Save footage keys", key="save_footage") and (pix or pex):
        _save(ctx.settings.root, {**({"PIXABAY_API_KEY": pix} if pix else {}),
                                  **({"PEXELS_API_KEY": pex} if pex else {})})
    st.caption("In .env the line must be exactly `PIXABAY_API_KEY=yourkey` (no quotes, no spaces).")
    if st.button("Test my footage key", key="test_footage"):
        from studio.config import load_settings
        with st.spinner("Testing..."):
            results = setup.test_footage_keys(load_settings(ctx.settings.root))
        for c in results:
            msg = c.message + (f" {c.fix}" if c.fix else "")
            (st.success if c.level == "ok" else st.warning if c.level == "warn" else st.error)(msg)


def _client_secret(ctx) -> None:
    st.markdown(setup.HOWTO["client_secret"])
    up = st.file_uploader("client_secret.json", type="json", key="set_cs")
    if up is not None and st.button("Save client file", key="save_cs"):
        try:
            path = setup.save_client_secret(ctx.settings, up.getvalue())
            st.success(f"Saved to {path.name}.")
        except StudioError as exc:
            st.error(str(exc))


def _channel_id(ctx) -> None:
    st.markdown(setup.HOWTO["channel_id"])
    cur = ctx.settings.channel_id
    val = st.text_input("Channel ID for the active channel", value=cur, placeholder="UC...", key="set_cid")
    if st.button("Save channel ID", key="save_cid"):
        channels.update(ctx.settings.root, youtube_channel_id=val.strip())
        st.success("Saved on the active channel.")
        st.rerun()


def _signin(ctx, show) -> None:
    s = ctx.settings
    prof = channels.get(s.root)
    st.markdown(setup.HOWTO["signin"])
    st.caption(f"Signing in for channel **{prof['name']}**. Each channel keeps its own Google sign-in, so you can "
               "use a different Google account per channel. This works when the app runs on your own computer.")
    if setup.signed_in(s):
        st.success("Signed in.")
        if st.button("Sign out of this channel", key="signout"):
            setup.sign_out(s)
            st.rerun()
        return
    if not setup.can_sign_in(s):
        st.info("Add the Google client file first (section above).")
        return
    if st.button("Sign in to Google", type="primary", key="signin_btn"):
        with st.spinner("A browser window should open. Finish the sign-in there..."):
            res = setup.sign_in(ctx)
        show(res, "Signed in.")
        if res.ok:
            st.rerun()


def _renderer(ctx) -> None:
    s = ctx.settings
    info = setup.renderer_info(s)
    st.caption("Used by Kids mode. 2D works everywhere. 3D needs Blender 4.2+ installed on this computer.")
    choice = st.radio("Pictures", ["2d", "blender"], index=1 if s.renderer == "blender" else 0, horizontal=True,
                      format_func={"2d": "2D (works anywhere)", "blender": "3D (Blender, this PC only)"}.get,
                      key="set_renderer")
    (st.success if info["blender_ok"] else st.info)(info["note"] + ("" if info["blender_ok"]
                                                                    else " Falls back to 2D."))
    path = st.text_input("Blender location (blank = find it automatically)", value=s.blender_path, key="set_blender")
    if st.button("Save picture style", key="save_renderer"):
        _save(s.root, {"RENDERER": choice, "BLENDER_PATH": path})


def render(ctx_for, show) -> None:
    """Draw the Setup page."""
    ctx = ctx_for()
    st.header("Setup")
    all_checks = doctor.run_checks(ctx.settings)
    blocking = setup.blocking(ctx.settings)
    if blocking:
        st.error(f"{len(blocking)} thing(s) must be fixed before you can make videos. They are marked 🔴.")
    elif doctor.verdict(all_checks) == "GO":
        st.success("Everything is ready, including uploading. Go to **Make a video**.")
    else:
        st.success("You can make videos now. Uploading to YouTube still needs the items marked 🔴 below "
                   "(optional: you can also download and upload by hand).")
    st.caption("Open any item for guided steps. Keys you save here are written to your local `.env` file and "
               "never shown again.")
    handlers = {"ffmpeg": _ffmpeg, "llm": _llm, "voice": _voice, "footage": _footage,
                "client_secret": _client_secret, "channel_id": _channel_id}
    for action, title in SECTIONS:
        lvl = setup.section_level(all_checks, action)
        msgs = [c for c in all_checks if c.action == action]
        with st.expander(f"{ICON[lvl]} {title}", expanded=lvl != doctor.OK):
            for c in msgs:
                st.write(c.message)
            if action == "signin":
                _signin(ctx, show)
            else:
                handlers[action](ctx)
    with st.expander("🎨 Picture style (2D or 3D)"):
        _renderer(ctx)
    st.caption("Back up or restore your channels and videos on the **Data** page.")
    st.button("Open the Data page", on_click=handoff_ui.goto, args=("Data",), key="setup_data")
    with st.expander("Plain-text report"):
        st.code(doctor.render(all_checks))
