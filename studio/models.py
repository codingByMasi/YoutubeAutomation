"""SQLAlchemy models for every table in SPEC Section 5."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(primary_key=True)
    seed: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(300))
    demand_score: Mapped[float] = mapped_column(Float, default=0)
    competition_score: Mapped[float] = mapped_column(Float, default=0)
    outlier_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="idea")  # idea | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def rank_score(self) -> float:
        return self.demand_score - self.competition_score + self.outlier_score


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"))
    stage: Mapped[str] = mapped_column(String(20), default="approved")
    youtube_video_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Title(Base):
    __tablename__ = "titles"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    text: Mapped[str] = mapped_column(String(200))
    style: Mapped[str] = mapped_column(String(50), default="")
    length: Mapped[int] = mapped_column(Integer)
    is_pick: Mapped[bool] = mapped_column(Boolean, default=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)


class Script(Base):
    __tablename__ = "scripts"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    markdown_path: Mapped[str] = mapped_column(String(500))
    json_path: Mapped[str] = mapped_column(String(500))
    word_count: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    position: Mapped[int] = mapped_column(Integer)
    narration: Mapped[str] = mapped_column(Text)
    visual_keywords: Mapped[str] = mapped_column(String(300), default="")  # comma separated
    est_seconds: Mapped[float] = mapped_column(Float)
    real_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    kind: Mapped[str] = mapped_column(String(30))  # clip | card | chart | music | font | intro | outro
    path: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(300), default="")
    licence: Mapped[str] = mapped_column(String(200), default="unknown")
    attribution_url: Mapped[str] = mapped_column(String(500), default="")


class MetricDaily(Base):
    __tablename__ = "metrics_daily"
    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[datetime] = mapped_column(Date)
    views: Mapped[int] = mapped_column(Integer, default=0)
    watch_minutes: Mapped[float] = mapped_column(Float, default=0)
    avg_view_duration: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    traffic_json: Mapped[str] = mapped_column(Text, default="{}")


class ABTest(Base):
    __tablename__ = "ab_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    field: Mapped[str] = mapped_column(String(20))  # title | thumbnail
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    metrics_before_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_after_json: Mapped[str] = mapped_column(Text, default="{}")


class CommentDraft(Base):
    __tablename__ = "comments_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    youtube_comment_id: Mapped[str] = mapped_column(String(64), unique=True)
    comment_text: Mapped[str] = mapped_column(Text)
    draft_reply: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | drafted | posted | skipped


class QuotaLog(Base):
    __tablename__ = "quota_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)  # Pacific-time quota day
    endpoint: Mapped[str] = mapped_column(String(60))
    units: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
