"""Shared fixtures: an isolated studio root with an in-memory-style SQLite DB and no real APIs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

import studio.util.retry as retry
from studio.config import Settings
from studio.context import Ctx
from studio.db import init_db, make_engine

ENV_KEYS = ["LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "CHANNEL_ID", "GOOGLE_CLIENT_SECRET_PATH",
            "PEXELS_API_KEY", "ELEVENLABS_API_KEY", "TTS_PROVIDER", "TTS_VOICE", "DAILY_QUOTA_LIMIT",
            "QUOTA_SAFETY_MARGIN", "STUDIO_HOME"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(retry, "BASE_DELAY", 0)
    yield


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "assets" / "music").mkdir(parents=True)
    return tmp_path


class Answers:
    """Scripted terminal answers for confirm prompts; records every question asked."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.answers.pop(0) if self.answers else ""


@pytest.fixture
def make_ctx(root: Path):
    def _make(**settings_kw) -> Ctx:
        settings = Settings(root=root, tts_provider="silent", **settings_kw)
        engine = make_engine(root / "studio.db")
        init_db(engine)
        session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
        return Ctx(settings=settings, engine=engine, session=session, confirm=Answers())
    return _make


@pytest.fixture
def ctx(make_ctx) -> Ctx:
    return make_ctx()


os.environ.setdefault("MPLBACKEND", "Agg")
