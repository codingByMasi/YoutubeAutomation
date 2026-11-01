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
IMAGE_PROVIDERS = {"auto", "pixabay", "commons", "none"}
RENDERERS = {"2d", "blender"}

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
    image_provider: str = "auto"
    elevenlabs_api_key: str = ""
    tts_provider: str = "edge"
    renderer: str = "2d"  # kids mode picture renderer: 2d (default, works anywhere) or blender (PC only)
    blender_path: str = ""
    openutau_path: str = ""
    tts_voice: str = "en-US-AndrewNeural"
    daily_quota_limit: int = 10000
    quota_safety_margin: int = 500
    secrets: list[str] = field(default_factory=list)
    channel_key: str = "default"  # which channel profile this context is for (picks the token file)
    made_for_kids: bool = False  # set from the active channel's type

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
        """Each channel has its own sign-in; the "default" channel keeps the original token.json."""
        if self.channel_key == "default":
            return self.root / "token.json"
        return self.root / "tokens" / f"{self.channel_key}.json"

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


def _apply_active_channel(s: Settings) -> None:
    """The active channel profile's voice and YouTube channel id override the defaults in `.env`."""
    from studio.growth import channels

    p = channels.get(s.root)
    if p["voice"]:
        s.tts_voice = p["voice"]
    if p["youtube_channel_id"]:
        s.channel_id = p["youtube_channel_id"]
    s.channel_key = channels.active_id(s.root)
    s.made_for_kids = channels.type_info(s.root)["made_for_kids"]


def clean_secret(value: str | None) -> str:
    """Strip whitespace, surrounding quotes and a stray `KEY=` prefix from a value read from .env."""
    v = (value or "").strip()
    while len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'`":
        v = v[1:-1].strip()
    v = v.strip("\"'`\u200b\ufeff ")
    return "".join(v.split())  # keys never contain spaces; pasted ones sometimes do


def _env_key(name: str, *aliases: str) -> str:
    """Cleaned key from `name`, or from a common misspelling of it (PIXABAY_KEY, PIXABAY_APIKEY...)."""
    for n in (name, *aliases):
        v = clean_secret(os.getenv(n))
        if v:
            return v
    return ""


def load_settings(root: Path | None = None) -> Settings:
    """Load `.env` from the project root and validate values that are always required."""
    root = Path(root or os.getenv("STUDIO_HOME") or Path.cwd()).resolve()
    load_dotenv(root / ".env", override=False, encoding="utf-8-sig")
    s = Settings(
        root=root,
        llm_provider=(os.getenv("LLM_PROVIDER") or "claude_code").strip().lower(),
        llm_api_key=clean_secret(os.getenv("LLM_API_KEY")),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        channel_id=os.getenv("CHANNEL_ID", "").strip(),
        google_client_secret_path=os.getenv("GOOGLE_CLIENT_SECRET_PATH", "./client_secret.json").strip(),
        pexels_api_key=_env_key("PEXELS_API_KEY", "PEXELS_KEY", "PEXELS_APIKEY", "PEXELS"),
        pixabay_api_key=_env_key("PIXABAY_API_KEY", "PIXABAY_KEY", "PIXABAY_APIKEY", "PIXABAY"),
        footage_provider=(os.getenv("FOOTAGE_PROVIDER") or "auto").strip().lower(),
        image_provider=(os.getenv("IMAGE_PROVIDER") or "auto").strip().lower(),
        elevenlabs_api_key=clean_secret(os.getenv("ELEVENLABS_API_KEY")),
        tts_provider=(os.getenv("TTS_PROVIDER") or "edge").strip().lower(),
        renderer=(os.getenv("RENDERER") or "2d").strip().lower(),
        blender_path=os.getenv("BLENDER_PATH", "").strip(),
        openutau_path=os.getenv("OPENUTAU_PATH", "").strip(),
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
    if s.renderer not in RENDERERS:
        raise ConfigError(
            f"RENDERER={s.renderer!r} is not supported.",
            f"Supported: {', '.join(sorted(RENDERERS))}.",
            "Set RENDERER=2d (works anywhere) or RENDERER=blender (needs Blender on your PC) in .env.",
        )
    if s.footage_provider not in FOOTAGE_PROVIDERS:
        raise ConfigError(
            f"FOOTAGE_PROVIDER={s.footage_provider!r} is not supported.",
            f"Supported: {', '.join(sorted(FOOTAGE_PROVIDERS))}.",
            "Set FOOTAGE_PROVIDER=auto (use whichever key is set) or none (generated cards only) in .env.",
        )
    if s.image_provider not in IMAGE_PROVIDERS:
        raise ConfigError(
            f"IMAGE_PROVIDER={s.image_provider!r} is not supported.",
            f"Supported: {', '.join(sorted(IMAGE_PROVIDERS))}.",
            "Set IMAGE_PROVIDER=auto (Pixabay if keyed, then Wikimedia Commons) or none in .env.",
        )
    if s.quota_safety_margin >= s.daily_quota_limit:
        raise ConfigError(
            "QUOTA_SAFETY_MARGIN must be smaller than DAILY_QUOTA_LIMIT.",
            f"Got margin {s.quota_safety_margin} and limit {s.daily_quota_limit}.",
            "Lower QUOTA_SAFETY_MARGIN in .env.",
        )
    _apply_active_channel(s)
    s.secrets = [v for v in (s.llm_api_key, s.pexels_api_key, s.pixabay_api_key, s.elevenlabs_api_key) if v]
    return s
