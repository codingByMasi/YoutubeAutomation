"""Approve-and-publish section, shared by "4. Review and download" and the "Make a video" wizard."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import streamlit as st

from studio.stages import review
from studio.web import growth_service as gsvc
from studio.web import service as svc
from studio.web import setup_service as setup


def render(ctx, root: Path, v, show, key: str = "") -> None:
    """Pre-publish checklist (typed yes), then a scheduled private upload (second typed yes)."""
    from studio.stages import publish

    if v.stage not in ("thumbnailed", "reviewed", "scheduled", "live"):
        st.info("Finish making the video first (thumbnails are the last step).")
        return
    if v.stage in ("scheduled", "live"):
        st.success(f"This video is {v.stage}. Nothing more to do here.")
        return
    fc_ok = v.stage == "reviewed" or gsvc.fact_check_passed(ctx, v.id)
    if not fc_ok:
        st.warning("Finish the **fact and source checklist** first (page *5. Grow the channel*, Fact check tab). "
                   "It must be complete before you can approve.")
    thumb = st.radio("Thumbnail", [1, 2, 3], horizontal=True, key=f"thumb{key}{v.id}")
    typed = st.text_input("Type yes to approve this video for publishing", key=f"yes1{key}{v.id}")
    if fc_ok and v.stage == "thumbnailed" and st.button("Run the pre-publish checklist", key=f"rv{key}{v.id}"):
        res = svc.capture(review.run, svc.make_ctx(root, lambda _p: typed), v.id, thumb=thumb)
        show(res, "Approved. You can now publish.")
        if res.ok:
            st.rerun()
    if v.stage != "reviewed":
        return
    st.success("Approved. Choose when it goes out.")
    if not ctx.settings.client_secret.exists():
        st.warning("Uploading needs the Google client file. Open **Setup** to add it, or download the video and "
                   "upload it yourself.")
        return
    if not setup.signed_in(ctx.settings):
        st.warning("Sign in to Google for this channel first (Setup page, *Sign in to Google*).")
        return
    when = st.date_input("Publish date", min_value=date.today(), key=f"d{key}{v.id}")
    at_time = st.time_input("Publish time (local)", value=time(18, 0), key=f"t{key}{v.id}")
    typed2 = st.text_input("Type yes again to upload", key=f"yes2{key}{v.id}")
    if st.button("Upload to YouTube (private, scheduled)", key=f"up{key}{v.id}"):
        res = svc.capture(publish.run, svc.make_ctx(root, lambda _p: typed2), v.id,
                          at=f"{when:%Y-%m-%d} {at_time:%H:%M}")
        show(res, "Uploaded.")
        if res.ok:
            st.rerun()
