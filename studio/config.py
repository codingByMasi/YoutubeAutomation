"""Environment loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from studio.errors import ConfigError

API_LLM_PROVIDERS = {"anthropic", "openai", "gemini"}
LLM_PROVIDERS = {"claude_code"} | API_LLM_PROVIDERS
TTS_PROVIDERS = {"edge", "eleven", "silent"}
FOOTAGE_PROVIDERS = {"auto", "pexels", "pixabay", "none"}

# Which settings each command needs. Used to name the command in missing-key messages.
COMMAND_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "research": ("GOOGLE_CLIENT_SECRET_PATH",),
    "publish": ("CHANNEL_ID", "GOOGLE_CLIENT_SECRET_PATH"),
    "analytics": ("CHANNEL_ID", "GOOGLE_CLIENT_SECRET_PATH"),
    "comments": ("GOOGLE_CLIENT_SECRET_PATH",),
}


@dataclass
class Settings:
    """All runtime settings. Paths are resolved against `root`."""

    root: Path
    llm_provider: str = "claude_code"
    llm_api_key: str = ""
    llm_model: str = ""
    channel_id: str = ""
    google_client_secret_path: str = "./client_secret.json"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    footage_provider: str = "auto"
    elevenlabs_api_key: str = ""
    tts_provider: str = "edge"
    tts_voice: str = "en-US-AndrewNeural"
    daily_quota_limit: int = 10000
    quota_safety_margin: int = 500
    secrets: list[str] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.root / "studio.db"

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def token_path(self) -> Path:
        return self.root / "token.json"

    @property
    def client_secret(self) -> Path:
        p = Path(self.google_client_secret_path)
        return p if p.is_absolute() else self.root / p

    def project_dir(self, video_id: int) -> Path:
        """Folder holding every file for one video."""
        d = self.projects_dir / str(video_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def require(self, command: str, *names: str) -> None:
        """Raise ConfigError naming the first missing variable and the command that needs it."""
        for name in names or COMMAND_REQUIREMENTS.get(command, ()):
            value = getattr(self, name.lower(), "")
            if not value:
                raise ConfigError(
                    f"Missing {name} in .env.",
                    f"The `{command}` command needs it.",
                    f"Add {name}=... to .env (see .env.example and README section 5).",
                )
            if name == "GOOGLE_CLIENT_SECRET_PATH" and not self.client_secret.exists():
                raise ConfigError(
                    f"Google client secret file not found at {self.client_secret}.",
                    f"The `{command}` command talks to YouTube and needs OAuth credentials.",
                    "Download the Desktop-app OAuth client JSON (README section 3) and save it there.",
                )


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}.", "", f"Fix {name} in .env.") from exc


def load_settings(root: Path | None = None) -> Settings:
    """Load `.env` from the project root and validate values that are always required."""
    root = Path(root or os.getenv("STUDIO_HOME") or Path.cwd()).resolve()
    load_dotenv(root / ".env", override=False)
    s = Settings(
        root=root,
        llm_provider=(os.getenv("LLM_PROVIDER") or "claude_code").strip().lower(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        channel_id=os.getenv("CHANNEL_ID", "").strip(),
        google_client_secret_path=os.getenv("GOOGLE_CLIENT_SECRET_PATH", "./client_secret.json").strip(),
        pexels_api_key=os.getenv("PEXELS_API_KEY", "").strip(),
        pixabay_api_key=os.getenv("PIXABAY_API_KEY", "").strip(),
        footage_provider=(os.getenv("FOOTAGE_PROVIDER") or "auto").strip().lower(),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
        tts_provider=(os.getenv("TTS_PROVIDER") or "edge").strip().lower(),
        tts_voice=(os.getenv("TTS_VOICE") or "en-US-AndrewNeural").strip(),
        daily_quota_limit=_int("DAILY_QUOTA_LIMIT", 10000),
        quota_safety_margin=_int("QUOTA_SAFETY_MARGIN", 500),
    )
    if s.llm_provider not in LLM_PROVIDERS:
        raise ConfigError(
            f"LLM_PROVIDER={s.llm_provider!r} is not supported.",
            f"Supported: {', '.join(sorted(LLM_PROVIDERS))}.",
            "Set LLM_PROVIDER=claude_code to have Claude Code answer prompt files (no key needed).",
        )
    if s.tts_provider not in TTS_PROVIDERS:
        raise ConfigError(
            f"TTS_PROVIDER={s.tts_provider!r} is not supported.",
            f"Supported: {', '.join(sorted(TTS_PROVIDERS))}.",
            "Set TTS_PROVIDER=edge in .env.",
        )
    if s.footage_provider not in FOOTAGE_PROVIDERS:
        raise ConfigError(
            f"FOOTAGE_PROVIDER={s.footage_provider!r} is not supported.",
            f"Supported: {', '.join(sorted(FOOTAGE_PROVIDERS))}.",
            "Set FOOTAGE_PROVIDER=auto (use whichever key is set) or none (generated cards only) in .env.",
        )
    if s.quota_safety_margin >= s.daily_quota_limit:
        raise ConfigError(
            "QUOTA_SAFETY_MARGIN must be smaller than DAILY_QUOTA_LIMIT.",
            f"Got margin {s.quota_safety_margin} and limit {s.daily_quota_limit}.",
            "Lower QUOTA_SAFETY_MARGIN in .env.",
        )
    s.secrets = [v for v in (s.llm_api_key, s.pexels_api_key, s.pixabay_api_key, s.elevenlabs_api_key) if v]
    return s
