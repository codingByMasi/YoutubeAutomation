"""Streamlit "Data" page and the boot/autosave hooks. Logic lives in studio.storage (unit-tested)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from studio.errors import StudioError
from studio.storage import data, sync


def boot(root: Path, secrets: dict) -> None:
    """Once per session: apply storage secrets, write secret files, restore a backup onto a fresh disk."""
    if st.session_state.get("storage_booted"):
        return
    sync.apply_storage_secrets(secrets)
    try:
        sync.materialize_secret_files(root)
        st.session_state["storage_status"] = sync.restore_if_empty(root, sync.backend_from_env())
    except StudioError as exc:
        st.session_state["storage_status"] = f"storage error: {exc}"
    st.session_state["storage_booted"] = True


def tick(root: Path) -> None:
    """After every page run: push a backup if data changed (throttled, never raises)."""
    try:
        st.session_state["storage_status"] = sync.autosave(root, sync.backend_from_env())
    except StudioError as exc:
        st.session_state["storage_status"] = f"storage error: {exc}"


def _typed_confirm(label: str, key: str) -> bool:
    return st.text_input(f"Type {data.CONFIRM_WORD} to confirm {label}", key=key) == data.CONFIRM_WORD


def render(ctx_for, root: Path) -> None:
    """The Data page: where data lives, backup status, export/import, and deletion with confirmation."""
    ctx = ctx_for()
    st.header("Data")
    st.write(f"Everything is stored in one folder on this machine: `{root}`. It survives restarts and reboots "
             "when the app runs on your own computer or a host with a persistent disk. On free cloud hosts the "
             "disk is wiped on restart, so turn on a backup below.")
    rows = data.usage(root)
    st.table({"Area": [a.name for a in rows], "Size": [data.human(a.bytes) for a in rows]})

    st.subheader("Backup")
    status = st.session_state.get("storage_status", "off")
    try:
        be = sync.backend_from_env()
        st.write(f"Backend: **{be.label if be else 'none (local disk only)'}** · last status: {status}")
        if be and st.button("Back up now"):
            st.info(sync.autosave(root, be, force=True))
    except StudioError as exc:
        st.error(str(exc))
    st.caption("Auto-save runs after each action when STORAGE_BACKEND is set. Videos (mp4/mp3) and secrets are "
               "not backed up; download videos from step 4.")

    st.subheader("Export and import")
    c1, c2 = st.columns(2)
    media = c1.checkbox("Include video and audio files (large)")
    c1.download_button("⬇️ Export data (zip)", data.export_zip(root, include_media=media), "studio-data.zip",
                       "application/zip")
    up = c2.file_uploader("Import a zip", type="zip")
    replace = c2.checkbox("Replace everything (otherwise merge)")
    if up is not None and c2.button("Import"):
        try:
            n = data.import_zip(root, up.getvalue(), replace=replace)
            st.success(f"Imported {n} files.")
        except StudioError as exc:
            st.error(str(exc))

    st.subheader("Delete")
    st.warning("Deleting cannot be undone. Export first if unsure.")
    sizes = data.project_sizes(root)
    vids = {v.id: f"#{v.id} · {v.stage} · {data.human(sizes.get(v.id, 0))}" for v in _all_videos(ctx)}
    if vids:
        vid = st.selectbox("Video", list(vids), format_func=vids.get)
        d1, d2 = st.columns(2)
        if d1.button("Delete only its video/audio files"):
            st.success(f"Freed {data.human(data.delete_media(root, vid))}.")
        if _typed_confirm("deleting this whole video", "cf_vid") and d2.button("Delete video and its data"):
            data.delete_video(ctx.session, root, vid, data.CONFIRM_WORD)
            st.success("Deleted.")
            st.rerun()
    if st.button("Clear download cache (stock footage and photos)"):
        st.success(f"Freed {data.human(data.clear_cache(root))}.")
    from studio.growth import channels

    chans = {c["id"]: c["name"] for c in channels.list_channels(root)}
    ch = st.selectbox("Channel", list(chans), format_func=chans.get, key="del_ch")
    if _typed_confirm(f"deleting all topics, videos and plans of '{chans[ch]}'", "cf_ch") \
            and st.button("Delete this channel's data"):
        data.delete_channel_data(ctx.session, root, ch, data.CONFIRM_WORD)
        st.success("Deleted.")
        st.rerun()
    keep = st.checkbox("Keep YouTube sign-in files (token.json, client_secret.json)", value=True)
    if _typed_confirm("deleting EVERYTHING", "cf_all") and st.button("Delete everything"):
        ctx.session.close()
        ctx.engine.dispose()
        data.wipe(root, data.CONFIRM_WORD, keep_secrets=keep)
        st.success("All data deleted.")
        st.rerun()


def _all_videos(ctx) -> list:
    from studio.models import Video

    return ctx.session.query(Video).order_by(Video.id.desc()).all()
