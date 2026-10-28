"""OAuth for YouTube Data and Analytics APIs with a cached token.json."""

from __future__ import annotations

from typing import Any

from studio.config import Settings
from studio.errors import StudioError
from studio.util.logging import get_logger

log = get_logger("auth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # captions, comments, video updates
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _run_flow(settings: Settings) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings.require("auth", "GOOGLE_CLIENT_SECRET_PATH")
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.client_secret), SCOPES)
    print("Opening a browser to sign in to the Google account that owns the channel...")
    return flow.run_local_server(port=0, open_browser=True)


def get_credentials(settings: Settings, run_flow=_run_flow) -> Any:
    """Load token.json, refresh it, or run the browser sign-in. A revoked token is deleted first."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    token = settings.token_path
    if token.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        except ValueError:
            log.warning("token.json is unreadable; deleting it and signing in again")
            token.unlink()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            print("Your YouTube sign-in expired or was revoked. Deleting token.json and signing in again.")
            token.unlink(missing_ok=True)
            creds = None
    if not creds or not creds.valid:
        try:
            creds = run_flow(settings)
        except StudioError:
            raise
        except Exception as exc:
            raise StudioError(
                "Google sign-in failed.",
                str(exc),
                "If you saw 'Access blocked', add your account as a test user on the OAuth consent screen.",
            ) from exc
    token.write_text(creds.to_json(), encoding="utf-8")
    try:
        token.chmod(0o600)
    except OSError:
        pass
    return creds


def build_services(settings: Settings) -> tuple[Any, Any]:
    """Return (youtube data service, youtube analytics service)."""
    from googleapiclient.discovery import build

    creds = get_credentials(settings)
    return (
        build("youtube", "v3", credentials=creds, cache_discovery=False),
        build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False),
    )
