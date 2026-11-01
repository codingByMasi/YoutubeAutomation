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
