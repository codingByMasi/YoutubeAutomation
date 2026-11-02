"""Runtime issue log, plain-language diagnosis and in-system fixes; plus a generic fallback chain.

Anything that fails while the studio runs is recorded in logs/issues.json with a cause in plain words and, when
there is one, a fix the owner can run from the app (a button) or the CLI (`python -m studio.cli fix <id>`).
No code editing is ever needed. Fix actions only change settings, clear caches, or pip-install an optional package.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from studio.errors import PendingLLMResponse, StudioError

KEEP = 60

# (regex on the error text, plain cause, fix id). First match wins. Fix ids with ':' carry an argument.
RULES: list[tuple[str, str, str | None]] = [
    (r"youtube sign-in|invalid_grant|expired or revoked|google sign-in failed|token\.json",
     "The YouTube sign-in is missing, expired or revoked for a channel.", "youtube_signin"),
    (r"ffmpeg.*(not found|no such file)|ensure_ffmpeg", "ffmpeg is not installed or not on PATH.", "help:ffmpeg"),
    (r"edge[-_ ]?tts|speech\.platform\.bing|wss?://", "The free Edge voice service could not be reached "
     "(offline, blocked, or the service changed).", "tts_fallback"),
    (r"no module named '?(faster_whisper|faster-whisper)", "faster-whisper (word-accurate captions) is not installed.",
     "pip:faster-whisper"),
    (r"no module named '?(trafilatura|rapidfuzz|textstat|pyloudnorm|sentence_transformers|open_clip)",
     "An optional helper package is not installed; the studio uses a built-in fallback until it is.", "pip_from_error"),
    (r"pexels.*(401|403)|pixabay.*(401|403)|api key.*(invalid|rejected)", "A stock-footage API key was rejected.",
     "stock_fallback"),
    (r"database is locked|database is busy", "Another Studio window or step is using the database.", "unlock_db"),
    (r"quota", "The YouTube API daily quota budget is used up.", "help:quota"),
    (r"blender", "Blender could not be started; the 2D renderer is used instead.", "renderer_2d"),
    (r"cut off|max_tokens|truncat", "The model answer was cut off.", "retry"),
    (r"facts?.*(unverified|unfetchable)|could not read the source", "Some facts could not be verified automatically.",
     "help:facts"),
    (r"timed? ?out|connection|network|dns|ssl", "A network request failed (offline or the site is slow).", "retry"),
]
HELP = {
    "ffmpeg": "Install ffmpeg (Windows: `winget install Gyan.FFmpeg`; Linux: `apt install ffmpeg`), then press Retry.",
    "quota": "Wait until the quota resets (midnight Pacific) or lower DAILY_QUOTA_LIMIT; nothing was lost.",
    "facts": "Open the Facts list: open each source yourself, then accept it with `facts <video> --accept <id>`.",
}


def _path(root: Path) -> Path:
    return root / "logs" / "issues.json"


def load(root: Path) -> list[dict]:
    p = _path(root)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (ValueError, OSError):
        return []


def _save(root: Path, items: list[dict]) -> None:
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items[-KEEP:], indent=2, ensure_ascii=False), encoding="utf-8")


def diagnose(component: str, text: str) -> tuple[str, str | None]:
    """(plain cause, fix id) for an error text."""
    low = text.lower()
    for pat, cause, fix in RULES:
        if re.search(pat, low):
            return cause, fix
    return f"{component} failed in a way the studio does not recognise yet.", "retry"


def fix_label(fix: str | None) -> str:
    if not fix:
        return ""
    kind, _, arg = fix.partition(":")
    return {"retry": "Retry the step", "tts_fallback": "Use the offline voice fallback",
            "pip": f"Install {arg}", "pip_from_error": "Install the missing package",
            "stock_fallback": "Switch stock footage source", "unlock_db": "Clear leftover database files",
            "renderer_2d": "Use the 2D renderer", "help": "Show me how",
            "youtube_signin": "Sign in to YouTube again"}.get(kind, fix)


def record(root: Path, component: str, error: BaseException | str, context: str = "") -> dict | None:
    """Log a failure (deduplicated by component + cause text). Pending/answer handoffs are not failures."""
    if isinstance(error, PendingLLMResponse):
        return None
    text = str(error)
    cause, fix = diagnose(component, text + " " + type(error).__name__ if not isinstance(error, str) else text)
    if fix == "pip_from_error":
        m = re.search(r"no module named '?([\w\-\.]+)", text.lower())
        fix = f"pip:{m.group(1).replace('_', '-')}" if m else "retry"
    iid = hashlib.sha1(f"{component}|{cause}|{text[:120]}".encode()).hexdigest()[:8]
    items = load(root)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for it in items:
        if it["id"] == iid:
            it.update(last_seen=now, count=it.get("count", 1) + 1, status="open")
            _save(root, items)
            return it
    it = {"id": iid, "component": component, "cause": cause, "detail": text[:600], "context": context,
          "fix": fix, "fix_label": fix_label(fix), "status": "open", "count": 1, "first_seen": now, "last_seen": now}
    _save(root, [*items, it])
    return it


def open_issues(root: Path) -> list[dict]:
    return [i for i in load(root) if i.get("status") == "open"]


def issue_for_text(root: Path, text: str) -> dict | None:
    """The logged open issue whose detail matches an error shown on screen."""
    snippet = text[:120]
    return next((i for i in reversed(open_issues(root)) if i["detail"][:120] == snippet), None)


def resolve(root: Path, issue_id: str, note: str = "") -> None:
    items = load(root)
    for it in items:
        if it["id"] == issue_id:
            it.update(status="resolved", resolved_note=note)
    _save(root, items)


def run_fix(root: Path, issue_id: str) -> str:
    """Run the issue's fix. Returns a message for the owner. Never edits code."""
    it = next((i for i in load(root) if i["id"] == issue_id), None)
    if it is None:
        raise StudioError(f"No issue {issue_id!r}.", "", "Run `issues` to list them.")
    fix = it.get("fix") or "retry"
    kind, _, arg = fix.partition(":")
    if kind == "pip":
        r = subprocess.run([sys.executable, "-m", "pip", "install", arg], capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return f"Install of {arg} failed: {r.stderr.strip().splitlines()[-1] if r.stderr else 'unknown'}. " \
                   "The studio keeps using its built-in fallback."
        msg = f"Installed {arg}. Run the step again."
    elif kind == "tts_fallback":
        msg = _set_channel(root, {"tts_provider": ""}) + " Voice now tries Kokoro, Edge, then Piper in that order."
    elif kind == "renderer_2d":
        msg = _set_channel(root, {"renderer": "2d"}) + " Blender scenes will be drawn in 2D."
    elif kind == "stock_fallback":
        msg = "Footage falls back to the other stock source automatically; check the key in Setup if both fail."
    elif kind == "youtube_signin":
        from studio.config import load_settings
        from studio.growth import channels
        from studio.manage import multi_analytics as ma
        from studio.youtube import auth
        s = load_settings(root)
        cid = channels.active_id(root)
        st = auth.status(auth.settings_for(s, cid), check=True, adopt=True)
        if st["state"] != "connected":
            ma.sign_in(s, cid)  # opens a browser on this computer; raises a clear error if it cannot
        msg = f"YouTube sign-in for '{cid}' is working."
    elif kind == "unlock_db":
        from studio.config import load_settings
        from studio.util import dblock
        s = load_settings(root)
        dblock.clear_stale(s.db_path, root)
        msg = "Cleared leftover database files. Run the step again."
    elif kind == "help":
        msg = HELP.get(arg, "See the README.")
        return msg  # help text keeps the issue open
    else:
        msg = "Nothing to change; run the step again (finished work is reused, so it resumes where it stopped)."
    resolve(root, issue_id, msg)
    return msg


def _set_channel(root: Path, values: dict) -> str:
    from studio.growth import channels
    channels.update(root, channels.active_id(root), **values)
    return "Channel settings updated."


def disable_flag(root: Path, flag: str) -> str:
    """Switch one story feature off for the active channel (the safe fallback is the older behaviour)."""
    from studio.growth import channels
    cur = dict(channels.get(root).get("story") or {})
    flags = dict(cur.get("flags") or {})
    flags[flag] = False
    cur["flags"] = flags
    channels.update(root, channels.active_id(root), story=cur)
    return f"Turned off '{flag}' for this channel."


def with_fallback(root: Path | None, component: str, steps: list[tuple[str, Callable[[], object]]],
                  log: Callable[[str], None] | None = None) -> tuple[str, object]:
    """Try each (name, fn) in order; record each failure as an issue; return (name, result) of the first success.

    If every step fails, raise one StudioError that lists all causes."""
    errors: list[str] = []
    for name, fn in steps:
        try:
            return name, fn()
        except PendingLLMResponse:
            raise
        except Exception as exc:  # noqa: BLE001 - the point is to continue with the next option
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:160]}")
            if root is not None:
                record(root, f"{component} ({name})", exc)
            if log:
                log(f"{component}: {name} failed ({type(exc).__name__}); trying the next option")
    raise StudioError(f"Every option for {component} failed.", " | ".join(errors),
                      "Open the Issues panel (or run `issues`) for fixes, then run the step again.")


def record_signin_problems(root: Path, rows: list[dict]) -> None:
    """Log one open issue (with a Fix button) per channel whose YouTube sign-in is expired or missing."""
    for r in rows:
        if r["state"] in ("expired", "missing"):
            record(root, "YouTube", f"YouTube sign-in for channel {r['channel_id']}: {r['message']}")
