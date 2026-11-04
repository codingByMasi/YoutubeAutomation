"""The Voices page: hear each narration voice and OpenUtau voicebank, see licences, and pick the ones to use."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from studio.errors import StudioError
from studio.web import setup_service as setup
from studio.web import voices_service as vs


def _narration(ctx) -> None:
    s = ctx.settings
    st.subheader("Narration voice")
    st.caption("Free Microsoft Edge voices. Press **Hear it** (needs internet), then **Use this voice**. "
               "The choice is saved for every new video on this channel.")
    if s.tts_provider != "edge":
        st.warning(f"The voice service is set to {s.tts_provider}; choosing a voice here switches it to edge.")
    for v in vs.narration_voices(s):
        c1, c2, c3 = st.columns([4, 1.4, 1.6])
        c1.write(("✅ " if v["selected"] else "") + v["label"])
        if c2.button("🔊 Hear it", key=f"hear_{v['id']}"):
            try:
                with st.spinner("Making a sample..."):
                    path = setup.voice_sample(s, v["id"], Path(tempfile.mkdtemp(prefix="voice_")))
                st.audio(path.read_bytes(), format="audio/mp3")
            except Exception as exc:  # noqa: BLE001 - show network/TTS trouble plainly
                st.error(f"Could not make a sample: {exc}\nCheck your internet connection and try again.")
        if c3.button("Use this voice", key=f"use_{v['id']}", disabled=v["selected"], type="primary"):
            try:
                vs.select_narration(s.root, v["id"])
                st.success(f"Saved. New videos will use {v['label']}.")
            except StudioError as exc:
                st.error(str(exc))


def _voicebanks(ctx) -> None:
    s = ctx.settings
    st.subheader("Singing voices (OpenUtau, kids songs)")
    st.caption("Only voicebanks whose licence was checked for monetised videos are listed. Nothing else can be "
               "selected. OpenUtau runs on the CPU; no GPU needed.")
    info = vs.openutau_status(s)
    (st.success if info["found"] else st.warning)(info["note"])
    if info["found"] and st.button("Open OpenUtau", key="open_openutau"):
        try:
            st.info(vs.open_in_openutau(s))
        except StudioError as exc:
            st.error(str(exc))
    for card in vs.voicebank_cards(s):
        with st.container(border=True):
            st.markdown(f"**{card['name']}**" + ("  ✅ selected" if card["selected"] else ""))
            st.write(f"💰 {card['monetisation']}")
            st.write(card["licence"])
            if card["ai_warning"]:
                ai = next((w for w in card["warnings"] if "AI generated" in w), "Bans AI-generated content.")
                st.error("⚠️ " + ai)
            for w in card["warnings"]:
                if not (card["ai_warning"] and "AI generated" in w):
                    st.warning(w)
            st.caption(f"Terms: {card['source']} · checked {card['checked']} · Credit: {card['credit']}")
            st.caption("Installed in OpenUtau." if card["installed"] else
                       f"Not installed yet. Download: {card['download']} (then add it in OpenUtau).")
            if card["preview"]:
                st.audio(card["preview"].read_bytes())
            else:
                st.caption("No preview yet. In OpenUtau type a line, choose this singer, **File > Export Audio**, "
                           "then upload the .wav below.")
            up = st.file_uploader("Add or replace the preview clip", type=[e.lstrip(".") for e in vs.AUDIO_EXT],
                                  key=f"prev_{card['key']}")
            if up is not None and st.button("Save preview", key=f"saveprev_{card['key']}"):
                try:
                    vs.save_preview(s.root, card["key"], up.name, up.getvalue())
                    st.success("Preview saved.")
                    st.rerun()
                except StudioError as exc:
                    st.error(str(exc))
            ack = True
            if card["ai_warning"]:
                ack = st.checkbox("I asked the creator and they allow AI-assisted work, or I will not monetise.",
                                  key=f"ack_{card['key']}")
            if st.button("Use this singer", key=f"usevb_{card['key']}", disabled=card["selected"], type="primary"):
                try:
                    vs.select_voicebank(s.root, card["key"], acknowledged=ack)
                    st.success("Saved. `kids sing` will save its licence note and credit line.")
                    st.rerun()
                except StudioError as exc:
                    st.error(str(exc))
    if s.sing_voicebank and st.button("Clear singer choice", key="clear_vb"):
        vs.select_voicebank(s.root, "")
        st.rerun()


def render(ctx_for, show=None) -> None:
    ctx = ctx_for()
    st.header("Voices")
    _narration(ctx)
    st.divider()
    _voicebanks(ctx)
