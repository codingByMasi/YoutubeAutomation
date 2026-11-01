"""Per-channel views of the database: ideas and videos belong to the session's active channel."""

from __future__ import annotations

from sqlalchemy.orm import Query, Session

from studio.models import Idea, Video


def channel_of(session: Session) -> str:
    """Active channel id tied to this session (set by build_ctx)."""
    return session.info.get("channel_id", "default")


def ideas(session: Session) -> Query:
    """Ideas of the active channel."""
    return session.query(Idea).filter(Idea.channel_id == channel_of(session))


def videos(session: Session) -> Query:
    """Videos whose idea belongs to the active channel."""
    ids = session.query(Idea.id).filter(Idea.channel_id == channel_of(session))
    return session.query(Video).filter(Video.idea_id.in_(ids.scalar_subquery()))
