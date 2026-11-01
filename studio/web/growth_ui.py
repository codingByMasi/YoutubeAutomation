"""Streamlit page "5. Grow the channel". Thin UI over studio.growth; all logic lives there and is tested."""

from __future__ import annotations

import streamlit as st

from studio.errors import StudioError
from studio.growth import factcheck as fc
from studio.growth import monetize, packs, perf, profile, series
from studio.web import growth_service as g
from studio.web import service as svc


def _try(fn, ok: str | None = None):
    """Run fn, show StudioErrors readably. Returns (True, result) or (False, None)."""
    try:
        res = fn()
    except StudioError as exc:
        st.error(str(exc))
        return False, None
    if ok:
        st.success(ok)
    return True, res


def page_grow_factory(ctx_for, video_picker, show):
    """Build the page function (needs the app's helpers, which live in app.py)."""

    def tab_profile(ctx):
        st.write("Tell the studio about the active channel (add or switch channels on the Channels page). "
                 "Every field has a default, so you can skip this and come back.")
        p = g.profile_for(ctx)
        with st.form("profile"):
            c1, c2 = st.columns(2)
            vals = {
                "name": c1.text_input("Channel name", p["name"]),
                "niche": c1.text_input("Niche", p["niche"]),
                "description": c1.text_area("Description", p["description"]),
                "language": c1.text_input("Language", p["language"]),
                "audience": c1.text_input("Target audience", p["audience"]),
                "posts_per_week": c2.number_input("Long videos per week", 1, 7, int(p["posts_per_week"])),
                "voice": c2.text_input("Voice (edge-tts name; blank = default)", p["voice"]),
                "brand_primary": c2.color_picker("Brand color", p["brand_primary"]),
                "brand_accent": c2.color_picker("Accent color", p["brand_accent"]),
                "newsletter_url": c1.text_input("Newsletter signup link (optional)", p["newsletter_url"]),
                "affiliate_note": c1.text_input("Affiliate link text (optional)", p["affiliate_note"]),
            }
            if st.form_submit_button("Save profile"):
                profile.save(ctx.settings.root, vals)
                st.success("Saved. Prompts and descriptions now use these answers.")

    def tab_series(ctx):
        root = ctx.settings.root
        st.write("A series is a playlist where each video leads into the next one, which keeps viewers watching.")
        with st.expander("Get series ideas from Claude (copy and paste)"):
            used = [i.topic for i in svc.used_topics(ctx)]
            st.code(series.prompt(profile.summary(g.profile_for(ctx)), used), language="markdown", wrap_lines=True)
            pasted = st.text_area("Paste Claude's JSON answer", key="series_paste")
            if st.button("Add these series"):
                ok, names = _try(lambda: series.import_series(root, pasted))
                if ok:
                    st.success(f"Added: {', '.join(names)}")
        with st.form("new_series"):
            name = st.text_input("New series name")
            topics = st.text_area("Video topics, one per line")
            if st.form_submit_button("Create series"):
                _try(lambda: series.create(root, name, "", topics.splitlines()), "Series created.")
        for s in series.load(root):
            with st.expander(f"{s['name']} ({len(s['entries'])} videos)"):
                for i, e in enumerate(s["entries"]):
                    st.write(f"{i + 1}. {e['topic']}" + (f"  · video #{e['video_id']}" if e.get("video_id") else ""))
                    with st.container():
                        st.caption("End-screen / outro line: " + series.end_screen(s, i)["spoken"])
                vids = svc.list_videos(ctx)
                if vids and s["entries"]:
                    c1, c2, c3 = st.columns(3)
                    idx = c1.number_input("Slot #", 1, len(s["entries"]), 1, key=f"slot{s['name']}") - 1
                    names = {v.id: f"#{v.id} {svc.video_title(ctx, v)[:40]}" for v in vids}
                    vid = c2.selectbox("Video", list(names), key=f"lv{s['name']}", format_func=names.get)
                    if c3.button("Link video to slot", key=f"link{s['name']}"):
                        series.link_video(root, s["name"], int(idx), vid,
                                          svc.video_title(ctx, next(v for v in vids if v.id == vid)))
                        st.rerun()
                if st.button("Delete series", key=f"del{s['name']}"):
                    series.remove(root, s["name"])
                    st.rerun()

    def tab_calendar(ctx):
        weeks = st.slider("Weeks", 2, 8, 4)
        rows = g.calendar_rows(ctx, weeks)
        st.table([{"Date": f"{d:%a %Y-%m-%d}", "Type": k, "Content": v} for d, k, v in rows])
        gaps = sum(1 for r in rows if r[2] == "GAP" and r[1] == "long")
        st.caption(f"{gaps} long-video slot(s) empty. Add topics (1. Topics) or series entries to fill them.")

    def tab_pack(ctx, v):
        pd = ctx.settings.project_dir(v.id)
        topic = svc.video_title(ctx, v)
        st.write("5 titles and 3 thumbnail concepts, scored by a checklist. The best-scoring ones are picked for you.")
        summary = ""
        try:
            summary = "; ".join(sorted({s.get("chapter", "") for s in g.video_package(ctx, v.id)["segments"]}))
        except StudioError:
            pass
        st.code(packs.prompt(topic, profile.summary(g.profile_for(ctx)), summary), language="markdown", wrap_lines=True)
        pasted = st.text_area("Paste Claude's JSON answer", key=f"pack{v.id}")
        if st.button("Score and save the pack", key=f"packbtn{v.id}"):
            ok, pack = _try(lambda: packs.parse(pasted))
            if ok:
                packs.save(pd, pack)
                st.success("Saved.")
        pack = packs.load(pd)
        if pack:
            st.subheader("Titles")
            for t in pack["titles"]:
                st.write(f"{'⭐ ' if t['text'] == pack['pick_title'] else ''}**{t['text']}**  ({t['score']}/6)"
                         + (f" · {'; '.join(t['notes'])}" if t["notes"] else ""))
            st.subheader("Thumbnail concepts")
            for h in pack["thumbnails"]:
                st.write(f"**{h.get('text', '')}** ({h['score']}/5) · focus: {h.get('focal_element', '')} · "
                         f"{h.get('colors', '')} · layout: {h.get('layout', '')}"
                         + (f" · {'; '.join(h['notes'])}" if h["notes"] else ""))

    def tab_seo(ctx, v):
        ok, out = _try(lambda: g.seo_for(ctx, v.id))
        if not ok:
            return
        st.text_input("Title", out["title"], key=f"seo_t{v.id}")
        st.text_area("Description (copy into YouTube Studio)", out["description"], height=360, key=f"seo_d{v.id}")
        st.text_area("Tags (comma separated)", ", ".join(out["tags"]), key=f"seo_g{v.id}")
        st.caption(f"{out['chars']} of 5000 description characters. Chapters: " + " | ".join(out["chapters"]))
        text = f"{out['title']}\n\n{out['description']}\n\nTags: {', '.join(out['tags'])}"
        st.download_button("Download as text", text, file_name=f"video{v.id}_seo.txt", key=f"seo_dl{v.id}")

    def tab_shorts(ctx, v):
        ok, plan = _try(lambda: g.shorts_for(ctx, v.id))
        if not ok:
            return
        if not plan:
            st.info("No 20-45 second moments found. Add chart or beat segments to the script.")
        for n, s in enumerate(plan, 1):
            with st.expander(f"Short {n}: {s['hook_line'][:60]} ({s['seconds']}s, {s['why']})", expanded=n == 1):
                st.write(f"**Post:** {s['post_day_offset']} day(s) after the long video  ·  **On-screen text:** "
                         f"{s['on_screen_text']}")
                st.write(s["narration"])
                st.caption(f"Pinned comment: {s['pinned_comment']}  ·  {s['tags']}")
        st.caption("Cut the clips with 'Also cut 2-3 Shorts' on page 3.")

    def tab_factcheck(ctx, v):
        pd = ctx.settings.project_dir(v.id)
        ok, stt = _try(lambda: g.factcheck_for(ctx, v.id))
        if not ok:
            return
        for p in stt["problems"]:
            st.error(p)
        for it in stt["items"]:
            on = st.checkbox(it["text"], it["id"] in stt["checked"], key=f"fc{v.id}{it['id']}")
            if on != (it["id"] in stt["checked"]):
                fc.toggle(pd, it["id"], on)
                st.rerun()
        if stt["passed"]:
            st.success("Fact check complete. You can approve this video on page 4.")
        else:
            st.info(f"{len(stt['remaining'])} item(s) left. Approval on page 4 stays locked until all are ticked.")

    def tab_perf(ctx):
        root = ctx.settings.root
        st.write("Paste the numbers from YouTube Studio (Analytics) after a video has had a few days. "
                 "You get next-script advice here, and a prompt for deeper advice from Claude.")
        vids = svc.list_videos(ctx)
        vid = st.selectbox("Video", [None] + [v.id for v in vids],
                           format_func=lambda i: "(not linked)" if i is None else
                           f"#{i} {svc.video_title(ctx, next(v for v in vids if v.id == i))[:50]}")
        mode = st.radio("Input", ["Quick form", "Paste CSV export"], horizontal=True)
        rec: dict = {}
        if mode == "Quick form":
            c = st.columns(4)
            rec = {"impressions": c[0].number_input("Impressions", 0, value=0),
                   "ctr": c[1].number_input("CTR %", 0.0, 100.0),
                   "avg_view_pct": c[2].number_input("Avg % viewed", 0.0, 100.0),
                   "views": c[3].number_input("Views", 0, value=0)}
            rec = {k: v_ for k, v_ in rec.items() if v_}
        else:
            csv_text = st.text_area("CSV (header line + a row per video)", height=140)
            up = st.file_uploader("...or upload the CSV", type="csv")
            if up:
                csv_text = up.getvalue().decode("utf-8", errors="replace")
            if csv_text.strip():
                ok, rows = _try(lambda: perf.parse_csv(csv_text))
                if ok:
                    rec = rows[0] if len(rows) == 1 else rows[st.selectbox(
                        "Row", range(len(rows)), format_func=lambda i: str(rows[i].get("title", i + 1))[:60])]
        curve = perf.parse_retention(st.text_area("Retention points (optional), one per line like `0:30 62%`"))
        if rec and st.button("Get advice", type="primary"):
            entry = perf.add(root, rec, curve, vid)
            for a in entry["advice"]:
                st.write("• " + a)
            topic = svc.video_title(ctx, next(v for v in vids if v.id == vid)) if vid else "(unspecified)"
            with st.expander("Want deeper advice? Copy this prompt into Claude"):
                st.code(perf.prompt(rec, curve, topic, profile.summary(g.profile_for(ctx))), language="markdown",
                        wrap_lines=True)
        hist = perf.load(root)
        if hist:
            with st.expander(f"Past entries ({len(hist)})"):
                for h in reversed(hist[-10:]):
                    st.write(f"Video {h['video_id'] or '-'}: {h['stats']}")
                    for a in h["advice"]:
                        st.caption("• " + a)

    def tab_money(ctx):
        root = ctx.settings.root
        p = g.profile_for(ctx)
        st.write("Partner Program (ads): 1,000 subscribers **and** 4,000 public watch hours in 12 months "
                 "(or 10 million Shorts views in 90 days). Check YouTube Studio > Earn for the live rules.")
        c = st.columns(3)
        subs = c[0].number_input("Subscribers now", 0, value=int(p["subscribers"]))
        hours = c[1].number_input("Watch hours (last 12 months)", 0.0, value=float(p["watch_hours"]))
        sv = c[2].number_input("Shorts views (last 90 days)", 0, value=0)
        if st.button("Log today's numbers"):
            monetize.log_progress(root, subs, hours, sv)
            st.rerun()
        pr = monetize.progress(root)
        st.progress(pr["subs_pct"] / 100, text=f"Subscribers {pr['subs']:,} / 1,000")
        st.progress(pr["hours_pct"] / 100, text=f"Watch hours {pr['hours']:,.0f} / 4,000")
        if pr["eligible_long_form"] or pr["eligible_shorts"]:
            st.success("Thresholds met. Apply in YouTube Studio > Earn.")
        elif pr["eta"]:
            st.info(f"At your current pace you reach both goals around **{pr['eta']:%d %b %Y}**.")
        else:
            st.caption("Log your numbers on two different days to see a projected date.")
        st.subheader("Monetization checklist")
        for key, text in monetize.CHECKLIST:
            on = st.checkbox(text, key in pr["checked"], key=f"mz{key}")
            if on != (key in pr["checked"]):
                monetize.toggle(root, key, on)
                st.rerun()

    def page_grow() -> None:
        ctx = ctx_for()
        st.header("5. Grow the channel")
        names = ["Channel profile", "Series", "Calendar", "Titles & thumbnails", "Description & tags", "Shorts plan",
                 "Fact check", "Performance", "Monetization"]
        tabs = st.tabs(names)
        with tabs[0]:
            tab_profile(ctx)
        with tabs[1]:
            tab_series(ctx)
        with tabs[2]:
            tab_calendar(ctx)
        with tabs[8]:
            tab_money(ctx)
        with tabs[7]:
            tab_perf(ctx)
        for i, fn in ((3, tab_pack), (4, tab_seo), (5, tab_shorts), (6, tab_factcheck)):
            with tabs[i]:
                v = video_picker(ctx, f"grow_video_{i}")
                if v is None:
                    st.info("Make a video first (topic, then script).")
                else:
                    fn(ctx, v)

    return page_grow
