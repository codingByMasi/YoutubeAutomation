"""Streamlit page: per-channel analytics, all-channels overview and side-by-side comparison."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from studio.config import load_settings
from studio.errors import StudioError
from studio.growth import channels
from studio.manage import multi_analytics as m


def render(root) -> None:
    st.header("📊 Channel analytics")
    rows = channels.list_channels(root)
    settings = load_settings(root)
    c1, c2 = st.columns([2, 3])
    preset = c1.selectbox("Date range", ["Last 7 days", "Last 28 days", "Last 90 days", "Custom"], index=1)
    days = {"Last 7 days": 7, "Last 28 days": 28, "Last 90 days": 90}.get(preset)
    if days:
        start, end = m.date_range(days)
    else:
        yesterday = date.today() - timedelta(days=1)
        picked = c2.date_input("From - to", (yesterday - timedelta(days=27), yesterday))
        if len(picked) != 2:
            st.info("Pick both a start and an end date.")
            return
        try:
            start, end = m.date_range(1, picked[0], picked[1])
        except StudioError as exc:
            st.error(str(exc))
            return
    demo = st.checkbox("Show clearly labelled SAMPLE data for channels that are not signed in", value=False,
                       help="Sample numbers are made up. They only show how the page looks.")
    names = {c["id"]: c["name"] for c in rows}
    chosen = st.multiselect("Channels", list(names), default=list(names), format_func=names.get)
    if not chosen:
        st.info("Pick at least one channel.")
        return
    try:
        reports = m.overview(root, start, end, m.default_services(settings), demo, chosen)
    except StudioError as exc:
        st.error(str(exc))
        return
    overview, *pages = st.tabs(["All channels"] + [names[r["channel_id"]] for r in reports])
    with overview:
        _overview(reports)
    for tab, r in zip(pages, reports):
        with tab:
            _page(r)


def _badge(r: dict) -> None:
    if r["source"] == "demo":
        st.warning("SAMPLE DATA: made-up numbers. Sign this channel in to see real ones.")
    elif r["source"] != "live":
        st.info(r["message"])


def _overview(reports: list[dict]) -> None:
    table = m.comparison_rows(reports)
    st.dataframe(table, use_container_width=True, hide_index=True)
    live = [r for r in reports if r["daily"]]
    if live:
        st.subheader("Views per day")
        st.line_chart({r["name"]: {d["day"]: d["views"] for d in r["daily"]} for r in live})
        st.subheader("Net subscribers")
        st.bar_chart({r["name"]: r["totals"]["net_subs"] for r in live})
    for r in reports:
        if r["source"] == "demo":
            st.caption(f"{r['name']}: sample data.")
        elif r["source"] != "live":
            st.caption(f"{r['name']}: {r['message']}")


def _page(r: dict) -> None:
    _badge(r)
    if not r["daily"]:
        return
    t, p = r["totals"], r["previous"]
    a, b, c, d = st.columns(4)
    a.metric("Views", f"{t['views']:,}", f"{t['views'] - p['views']:+,}")
    b.metric("Watch hours", f"{t['watch_hours']:,}", f"{t['watch_hours'] - p['watch_hours']:+,.1f}")
    c.metric("Net subscribers", f"{t['net_subs']:+,}", f"{t['net_subs'] - p['net_subs']:+,}")
    d.metric("Avg % of video watched", f"{t['avg_view_pct']}%", f"{t['avg_view_pct'] - p['avg_view_pct']:+.1f}")
    if r["subscribers_total"]:
        st.caption(f"{r['subscribers_total']:,} subscribers in total. Arrows compare with the previous period.")
    st.line_chart({"Views": {x["day"]: x["views"] for x in r["daily"]}})
    st.subheader("Top videos")
    st.dataframe([{"Video": v["title"], "Views": v["views"], "Watch hours": v["watch_hours"],
                   "Retention %": v["retention_pct"]} for v in r["top_videos"]], hide_index=True,
                 use_container_width=True)
    st.caption(r["hint"])
