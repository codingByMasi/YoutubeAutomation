"""Streamlit page for kids mode. Imported lazily by app.py so the main pages stay untouched."""

from __future__ import annotations

import json

import streamlit as st

from studio.kids import build as kbuild
from studio.kids import checklist, spec
from studio.kids import script as kscript
from studio.llm import prompt_paths
from studio.web import service as svc


def render(ctx_for, show) -> None:
    """Draw the kids page. `ctx_for` and `show` are the app's helpers (passed in to avoid a circular import)."""
    ctx = ctx_for()
    st.header("🧸 Kids mode (nursery rhymes and learning songs)")
    st.write("Original sing-along videos with simple animated characters. This is a separate mode: it does not "
             "touch the long-form pipeline and it never uploads anything.")
    topic = st.text_input("Song topic", placeholder="counting five little ducks")
    if not topic.strip():
        return
    slug = kscript.slugify(topic)
    d = kscript.project_dir(ctx, slug)
    if st.button("Step 1: write the request for Claude"):
        show(svc.capture(kscript.run, ctx, topic))
    prompt_file, resp_file = prompt_paths(d, "kids_script")
    if prompt_file.exists() and not resp_file.exists():
        st.code(prompt_file.read_text(encoding="utf-8"), language="markdown", wrap_lines=True)
        pasted = st.text_area("Claude's answer (JSON)", height=300, key=f"kidsresp_{slug}")
        if st.button("Save script and check it", type="primary"):
            try:
                problems = spec.validate(llm_json(pasted))
            except ValueError as exc:
                problems = [f"Not valid JSON: {exc}"]
            if problems:
                st.error("\n".join(f"- {p}" for p in problems))
            else:
                resp_file.write_text(json.dumps(llm_json(pasted), indent=2, ensure_ascii=False), encoding="utf-8")
                show(svc.capture(kscript.run, ctx, topic), "Script accepted.")
                st.rerun()
    if (d / "script.json").exists():
        from studio.web import setup_service as setup

        info = setup.renderer_info(ctx.settings)
        choice = st.radio("Pictures", ["2d", "blender"], index=1 if ctx.settings.renderer == "blender" else 0,
                          horizontal=True, key=f"kids_renderer_{slug}",
                          format_func={"2d": "2D (works anywhere)", "blender": "3D (Blender, this PC only)"}.get)
        if choice == "blender" and not info["blender_ok"]:
            st.info(info["note"] + " The video will be made in 2D instead.")
        if st.button("Step 2: make the video"):
            with st.spinner("Drawing scenes (a few minutes)..."):
                show(svc.capture(kbuild.run, ctx, slug, renderer=choice), "Video ready.")
        if (d / "final.mp4").exists():
            st.video((d / "final.mp4").read_bytes())
            st.download_button("Download MP4", (d / "final.mp4").read_bytes(), f"{slug}.mp4", "video/mp4")
            st.text(checklist.render_text(checklist.run(d)))


def llm_json(text: str) -> dict:
    """Parse pasted JSON (tolerates code fences)."""
    from studio.errors import StudioError
    from studio.llm import _extract_json

    try:
        return _extract_json(text)
    except StudioError as exc:
        raise ValueError(f"{exc.what} {exc.why}".strip()) from exc
