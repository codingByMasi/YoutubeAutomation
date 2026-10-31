"""Glue between the growth tools and the studio database/projects. No Streamlit imports."""

from __future__ import annotations

from datetime import date

from studio.context import Ctx
from studio.growth import factcheck, packs, profile, seo, shorts_plan
from studio.growth import series as series_mod
from studio.manage import calendar
from studio.models import Asset, Idea, Video
from studio.stages.base import stage_index
from studio.stages.script import load_package
from studio.web import service as svc


def video_package(ctx: Ctx, video_id: int) -> dict:
    """The video's script.json (raises a readable error if there is no script yet)."""
    return load_package(ctx, video_id)


def current_title(ctx: Ctx, video_id: int) -> str:
    """The saved pack pick, else the script's picked title, else the topic."""
    pack = packs.load(ctx.settings.project_dir(video_id))
    if pack:
        return pack["pick_title"]
    return svc.video_title(ctx, ctx.session.get(Video, video_id))


def seo_for(ctx: Ctx, video_id: int) -> dict:
    """Description, tags and chapters for a scripted video, with source lines and photo credits."""
    pkg = video_package(ctx, video_id)
    licences = [{"kind": a.kind, "path": a.path, "licence": a.licence, "source": a.source,
                 "attribution_url": a.attribution_url}
                for a in ctx.session.query(Asset).filter_by(video_id=video_id).all()]
    return seo.build(ctx.settings.root, pkg, current_title(ctx, video_id), licences, video_id)


def shorts_for(ctx: Ctx, video_id: int) -> list[dict]:
    return shorts_plan.plan(video_package(ctx, video_id), long_video_title=current_title(ctx, video_id))


def factcheck_for(ctx: Ctx, video_id: int) -> dict:
    return factcheck.status(ctx.settings.project_dir(video_id), video_package(ctx, video_id))


def fact_check_passed(ctx: Ctx, video_id: int) -> bool:
    """True when the fact/source checklist is complete. False if there is no script yet."""
    try:
        return factcheck_for(ctx, video_id)["passed"]
    except Exception:  # noqa: BLE001 - no script means not checked
        return False


def calendar_rows(ctx: Ctx, weeks: int = 4, today: date | None = None) -> list[tuple[date, str, str]]:
    """Calendar rows: scheduled videos, made videos, then planned series topics fill the long slots."""
    start = today or date.today()
    vids = [v for v in svc.list_videos(ctx) if not ctx.session.get(Idea, v.idea_id).seed.startswith("__")]
    scheduled = [(v.publish_at.date(), f"#{v.id} {svc.video_title(ctx, v)}") for v in vids
                 if v.publish_at and v.publish_at.date() >= start]
    made = [f"#{v.id} {svc.video_title(ctx, v)}" for v in sorted(
        (v for v in vids if not v.youtube_video_id and not v.publish_at), key=lambda v: (-stage_index(v.stage), v.id))]
    planned = [f"(planned) {e['topic']} [{s['name']}]" for s in series_mod.load(ctx.settings.root)
               for e in s["entries"] if e.get("video_id") is None]
    return calendar.plan(start, weeks, scheduled, made + planned)


def profile_for(ctx: Ctx) -> dict:
    return profile.load(ctx.settings.root)
