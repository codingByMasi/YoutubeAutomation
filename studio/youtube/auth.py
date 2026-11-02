"""OAuth for YouTube Data and Analytics APIs with a cached token.json."""

from __future__ import annotations

import json
from pathlib import Path
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
    print(f"Opening a browser to sign in for channel '{settings.channel_key}'. Pick that YouTube channel "
          "if Google asks which one...")
    # prompt=consent makes Google always return a refresh token, so the sign-in lasts across restarts.
    return flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline")


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
        except RefreshError as exc:
            if not _is_dead_grant(exc):
                raise StudioError("Could not refresh the YouTube sign-in.", str(exc)[:200],
                                  "Check your internet connection and try again. Your saved sign-in was kept.") from exc
            print("Your YouTube sign-in expired or was revoked (Google Testing-mode sign-ins last 7 days). "
                  "Signing in again; the old token is replaced only after the new one works.")
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
    _save_token(token, creds)
    return creds


def _save_token(token: Path, creds: Any) -> None:
    """Write the token atomically (a crash mid-write must never leave a half file that forces a new sign-in)."""
    token.parent.mkdir(parents=True, exist_ok=True)
    tmp = token.with_suffix(token.suffix + ".tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(token)


def _is_dead_grant(exc: Exception) -> bool:
    """True when Google refused the refresh token itself (expired/revoked), not a temporary or network problem."""
    if getattr(exc, "retryable", False):
        return False
    t = str(exc).lower()
    return not any(k in t for k in ("connection", "timed out", "timeout", "temporarily", "unavailable", "dns"))


def settings_for(settings: Settings, channel_id: str) -> Settings:
    """Copy of `settings` for one channel profile: its own token file, YouTube channel id and kids flag."""
    from dataclasses import replace

    from studio.growth import channels

    p = channels.get(settings.root, channel_id)
    return replace(settings, channel_key=channel_id, channel_id=p["youtube_channel_id"] or settings.channel_id,
                   made_for_kids=channels.type_info(settings.root, channel_id)["made_for_kids"])


def is_signed_in(settings: Settings) -> bool:
    """True if this channel has a saved sign-in (token file). It may still need a refresh."""
    return settings.token_path.exists()


def load_credentials(settings: Settings) -> Any:
    """Saved credentials for this channel, refreshed if needed. Never opens a browser; None if not signed in."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = settings.token_path
    if not token.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(token, creds)
    except (ValueError, RefreshError):
        return None  # token file is kept; `youtube-status` says why and the app offers a Fix button
    except Exception:  # noqa: BLE001 - offline etc.: not signed out, just unreachable right now
        return None
    return creds if creds.valid else None


def build_services(settings: Settings, credentials: Any = None) -> tuple[Any, Any]:
    """Return (youtube data service, youtube analytics service)."""
    from googleapiclient.discovery import build

    creds = credentials or get_credentials(settings)
    return (
        build("youtube", "v3", credentials=creds, cache_discovery=False),
        build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False),
    )


LEGACY_TOKEN = "token.json"


def status(settings: Settings, check: bool = False, adopt: bool = False) -> dict:
    """Sign-in state of one channel: connected | expired | missing | no_client. Never returns secrets.

    Without `check` nothing touches the network, so a token that only *looks* fine is reported as connected
    (access tokens renew by themselves while the refresh token lives). `check=True` tries a refresh to
    find out if Google still accepts it. `adopt=True` copies the old shared token.json into this channel's token
    slot when that slot is empty (it only happens on request, because the old token belongs to one Google login).
    """
    token = settings.token_path
    out = {"channel_id": settings.channel_key, "token": str(token), "state": "missing", "message": "", "fix": "",
           "client_secret": str(settings.client_secret)}
    if not settings.client_secret.exists():
        out.update(state="no_client", message="The Google client file (client_secret.json) is missing.",
                   fix=f"Upload it on the Setup page, or save it at {settings.client_secret}.")
        return out
    sign_fix = ("Press 'Sign in to Google' on the Setup page, or run: "
                f"python -m studio.cli channels sign-in {settings.channel_key}")
    legacy = settings.root / LEGACY_TOKEN
    if not token.exists():
        if legacy.exists() and token != legacy:
            if adopt:
                token.parent.mkdir(parents=True, exist_ok=True)
                token.write_bytes(legacy.read_bytes())
            else:
                out.update(message="No sign-in saved for this channel, but an old shared token.json exists.",
                           fix="Run: python -m studio.cli youtube-status --fix  (adopts it for this channel if it is "
                               "the right Google account), or sign in again.")
                return out
        else:
            out.update(message="Not signed in yet.", fix=sign_fix)
            return out
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    except (ValueError, OSError, KeyError) as exc:
        out.update(state="expired", message=f"The token file is unreadable or lacks a refresh token ({str(exc)[:80]}).",
                   fix=sign_fix)
        return out
    if not creds.refresh_token:
        out.update(state="expired", message="The saved sign-in has no refresh token, so it cannot renew itself.",
                   fix=sign_fix)
        return out
    try:
        granted = set(json.loads(token.read_text(encoding="utf-8")).get("scopes") or [])
    except (ValueError, OSError):
        granted = set()
    if granted and not set(SCOPES) <= granted:
        out.update(state="expired", message="The saved sign-in was made with fewer permissions than the app needs now.",
                   fix=sign_fix)
        return out
    if check:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        try:
            creds.refresh(Request())
            _save_token(token, creds)
        except RefreshError as exc:
            if _is_dead_grant(exc):
                out.update(state="expired", message="Google no longer accepts this sign-in (revoked, or "
                           "Testing-mode and older than 7 days).",
                           fix=sign_fix + ". To stop this recurring, set the OAuth consent screen to 'In production'.")
            else:
                out.update(state="connected", message=f"Could not verify right now ({str(exc)[:80]}); token kept.")
            return out
        except Exception as exc:  # noqa: BLE001 - offline
            out.update(state="connected", message=f"Saved sign-in found; Google not reachable ({type(exc).__name__}).")
            return out
    out.update(state="connected", message="Signed in." + (" Verified with Google." if check else ""))
    return out


def status_all(settings: Settings, check: bool = False, adopt: bool = False) -> list[dict]:
    """`status` for every channel profile."""
    from studio.growth import channels
    return [status(settings_for(settings, c["id"]), check=check, adopt=adopt)
            for c in channels.list_channels(settings.root)]
