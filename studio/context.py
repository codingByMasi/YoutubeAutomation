"""Shared runtime context: settings, database, and lazily built YouTube clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from studio.config import Settings, load_settings
from studio.db import init_db, make_engine
from studio.util.logging import setup_logging
from studio.youtube.quota import QuotaTracker


def default_confirm(prompt: str) -> str:
    """Ask the owner a question on the terminal."""
    return input(prompt)


@dataclass
class Ctx:
    """Everything a command needs. Tests build one with fakes."""

    settings: Settings
    engine: Engine
    session: Session
    confirm: Callable[[str], str] = default_confirm
    youtube_factory: Callable[[], tuple[Any, Any]] | None = None
    _yt: tuple[Any, Any] | None = field(default=None, repr=False)

    @property
    def quota(self) -> QuotaTracker:
        return QuotaTracker(self.session, self.settings.daily_quota_limit, self.settings.quota_safety_margin)

    def youtube(self, command: str):
        """(YouTubeData, YouTubeAnalytics) clients, signing in on first use."""
        from studio.youtube.analytics_api import YouTubeAnalytics
        from studio.youtube.data_api import YouTubeData

        if self._yt is None:
            if self.youtube_factory is None:
                from studio.youtube.auth import build_services

                self.settings.require(command, "GOOGLE_CLIENT_SECRET_PATH")
                data, analytics = build_services(self.settings)
            else:
                data, analytics = self.youtube_factory()
            self._yt = (YouTubeData(data, self.quota), YouTubeAnalytics(analytics, self.quota))
        return self._yt


def build_ctx(root: Path | None = None, verbose: bool = False) -> Ctx:
    """Load settings, set up logging, open and initialise the database."""
    settings = load_settings(root)
    setup_logging(settings.root / "logs", settings.secrets, verbose)
    engine = make_engine(settings.db_path)
    init_db(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    from studio.growth import channels
    session.info["channel_id"] = channels.active_id(settings.root)
    return Ctx(settings=settings, engine=engine, session=session)
