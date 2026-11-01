"""Analytics page: pull numbers from YouTube (local, signed in) or paste them in; read the latest report."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from studio import scope
from studio.manage import analytics_report
from studio.web import service as svc
from studio.web import setup_service as setup


def latest_report(root: Path, channel_slug: str) -> Path | None:
    """Newest saved analytics report for the channel."""
    tag = "" if channel_slug == "default" else f"_{channel_slug}"
    files = sorted((root / "reports").glob(f"analytics{tag}_[0-9]*.md")) if (root / "reports").exists() else []
    return files[-1] if files else None


def render(ctx_for, show) -> None:
    """Draw the Analytics page."""
    ctx = ctx_for()
    s = ctx.settings
    st.header("📈 Analytics")
    st.write(f"Channel **{scope.channel_of(ctx.session)}**. The report explains in plain English what worked, "
             "where viewers left, and what to make next.")
    ready = setup.can_sign_in(s) and setup.signed_in(s) and bool(s.channel_id)
    if ready:
        days = st.slider("Days of history", 7, 90, 28)
        if st.button("Pull the latest from YouTube", type="primary"):
            with st.spinner("Asking YouTube (uses a little of your daily quota)..."):
                show(svc.capture(analytics_report.run, ctx, days), "Report ready below.")
    else:
        st.info("Pulling numbers from YouTube needs the Google client file, a channel ID and a sign-in for this "
                "channel (**Setup** page). Until then, paste numbers from YouTube Studio into "
                "*5. Grow the channel > Performance*.")
    rep = latest_report(s.root, scope.channel_of(ctx.session))
    if rep:
        st.caption(rep.name)
        st.markdown(rep.read_text(encoding="utf-8"))
    else:
        st.caption("No report yet.")
