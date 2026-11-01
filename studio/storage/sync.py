"""Optional durable backup for hosts whose disk is wiped on restart.

Backend is chosen with STORAGE_BACKEND = none (default) | folder | github | s3. The snapshot is the zip from
`data.export_zip` (no media, no secrets). Autosave pushes it when data changed; restore pulls it when the
local database is missing (a fresh container). Failures are reported, never raised into the app.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

from studio.errors import StudioError
from studio.storage import data

SNAPSHOT_NAME = "studio-data.zip"
STATE_FILE = ".sync_state.json"
MIN_INTERVAL = 30  # seconds between uploads
GITHUB_MAX_BYTES = 90 * 1024 * 1024


class Backend(Protocol):
    """Where snapshots are kept."""

    label: str

    def put(self, blob: bytes) -> None: ...
    def get(self) -> bytes | None: ...


class FolderBackend:
    """A plain folder, e.g. one synced by Google Drive/Dropbox desktop, or an external disk."""

    def __init__(self, folder: str) -> None:
        self.folder = Path(folder).expanduser()
        self.label = f"folder {self.folder}"

    def put(self, blob: bytes) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (SNAPSHOT_NAME + ".part")
        tmp.write_bytes(blob)
        tmp.replace(self.folder / SNAPSHOT_NAME)

    def get(self) -> bytes | None:
        f = self.folder / SNAPSHOT_NAME
        return f.read_bytes() if f.exists() else None


class GitHubBackend:
    """A file in a PRIVATE GitHub repo (contents API). Refuses public repos so data never leaks."""

    def __init__(self, repo: str, token: str, branch: str = "", path: str = SNAPSHOT_NAME) -> None:
        self.repo, self.token, self.branch, self.path = repo, token, branch, path
        self.label = f"GitHub repo {repo}"
        self._checked = False

    def _call(self, method: str, url: str, body: dict | None = None, raw: bool = False):
        req = urllib.request.Request(
            f"https://api.github.com{url}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "User-Agent": "yt-studio",
                     "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https host
            payload = r.read()
        return payload if raw else json.loads(payload or b"{}")

    def _ensure_private(self) -> None:
        if self._checked:
            return
        try:
            info = self._call("GET", f"/repos/{self.repo}")
        except urllib.error.HTTPError as exc:
            raise StudioError(f"Cannot open GitHub repo {self.repo} (HTTP {exc.code}).",
                              "The repo name or token is wrong, or the token lacks Contents read/write.",
                              "Check GITHUB_BACKUP_REPO and GITHUB_BACKUP_TOKEN.") from exc
        if not info.get("private"):
            raise StudioError(f"{self.repo} is a public repo.", "Backups hold your scripts and channel data.",
                              "Create a PRIVATE repo for backups and point GITHUB_BACKUP_REPO at it.")
        self._checked = True

    def _sha(self) -> str | None:
        q = f"?ref={self.branch}" if self.branch else ""
        try:
            return self._call("GET", f"/repos/{self.repo}/contents/{self.path}{q}")["sha"]
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def put(self, blob: bytes) -> None:
        if len(blob) > GITHUB_MAX_BYTES:
            raise StudioError("Backup is too big for GitHub (over 90 MB).", f"It is {data.human(len(blob))}.",
                              "Delete old videos on the Data page, or use STORAGE_BACKEND=s3.")
        self._ensure_private()
        body: dict = {"message": "studio data backup", "content": base64.b64encode(blob).decode()}
        if self.branch:
            body["branch"] = self.branch
        sha = self._sha()
        if sha:
            body["sha"] = sha
        self._call("PUT", f"/repos/{self.repo}/contents/{self.path}", body)

    def get(self) -> bytes | None:
        self._ensure_private()
        q = f"?ref={self.branch}" if self.branch else ""
        try:
            return self._call("GET", f"/repos/{self.repo}/contents/{self.path}{q}", raw=True)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise


class S3Backend:
    """Any S3-compatible bucket (Cloudflare R2, Backblaze B2, AWS S3). Needs `pip install boto3`."""

    def __init__(self, bucket: str, key: str, endpoint: str, access: str, secret: str, region: str = "auto") -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StudioError("boto3 is not installed.", "STORAGE_BACKEND=s3 needs it.",
                              "Run: pip install boto3") from exc
        self.bucket, self.key = bucket, key
        self.label = f"bucket {bucket}"
        self.client = boto3.client("s3", endpoint_url=endpoint or None, aws_access_key_id=access,
                                   aws_secret_access_key=secret, region_name=region)

    def put(self, blob: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.key, Body=blob)

    def get(self) -> bytes | None:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self.key)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None


def backend_from_env(env: dict | None = None) -> Backend | None:
    """Build the configured backend, or None when STORAGE_BACKEND is unset/none."""
    e = os.environ if env is None else env
    kind = (e.get("STORAGE_BACKEND") or "none").strip().lower()
    if kind in ("", "none"):
        return None
    if kind == "folder":
        if not e.get("BACKUP_FOLDER"):
            raise StudioError("BACKUP_FOLDER is not set.", "STORAGE_BACKEND=folder needs a folder.",
                              "Set BACKUP_FOLDER=/path/to/folder.")
        return FolderBackend(e["BACKUP_FOLDER"])
    if kind == "github":
        if not (e.get("GITHUB_BACKUP_REPO") and e.get("GITHUB_BACKUP_TOKEN")):
            raise StudioError("GitHub backup is not fully configured.",
                              "GITHUB_BACKUP_REPO and GITHUB_BACKUP_TOKEN are both needed.",
                              "Set both (see README, Hosting and data).")
        return GitHubBackend(e["GITHUB_BACKUP_REPO"], e["GITHUB_BACKUP_TOKEN"], e.get("GITHUB_BACKUP_BRANCH", ""))
    if kind == "s3":
        need = ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
        miss = [n for n in need if not e.get(n)]
        if miss:
            raise StudioError(f"Missing {', '.join(miss)}.", "STORAGE_BACKEND=s3 needs them.", "Set them as secrets.")
        return S3Backend(e["S3_BUCKET"], e.get("S3_KEY", SNAPSHOT_NAME), e.get("S3_ENDPOINT_URL", ""),
                         e["S3_ACCESS_KEY_ID"], e["S3_SECRET_ACCESS_KEY"], e.get("S3_REGION", "auto"))
    raise StudioError(f"STORAGE_BACKEND={kind!r} is not supported.", "Supported: none, folder, github, s3.",
                      "Fix STORAGE_BACKEND.")


def _state(root: Path) -> dict:
    try:
        return json.loads((root / STATE_FILE).read_text())
    except (OSError, ValueError):
        return {}


def autosave(root: Path, backend: Backend | None, force: bool = False, now: float | None = None) -> str:
    """Upload a snapshot if data changed since the last upload. Returns a short status line; never raises."""
    if backend is None:
        return "off"
    t = time.time() if now is None else now
    st = _state(root)
    fp = data.fingerprint(root)
    if not force and (fp == st.get("fp") or t - st.get("t", 0) < MIN_INTERVAL):
        return "up to date"
    try:
        backend.put(data.export_zip(root))
    except (StudioError, OSError, urllib.error.URLError) as exc:
        return f"backup failed: {exc}"
    (root / STATE_FILE).write_text(json.dumps({"fp": fp, "t": t}))
    return f"saved to {backend.label}"


def restore_if_empty(root: Path, backend: Backend | None) -> str:
    """On a fresh disk (no database), pull the last snapshot. Returns a status line; never raises."""
    if backend is None or (root / data.DB_NAME).exists():
        return "skipped"
    try:
        blob = backend.get()
        if not blob:
            return "no backup found"
        n = data.import_zip(root, blob)
    except (StudioError, OSError, urllib.error.URLError) as exc:
        return f"restore failed: {exc}"
    (root / STATE_FILE).write_text(json.dumps({"fp": data.fingerprint(root), "t": time.time()}))
    return f"restored {n} files from {backend.label}"


def materialize_secret_files(root: Path, env: dict | None = None) -> list[str]:
    """Write secret JSON files from env vars (hosted secrets) so they never live in git or a backup.

    YOUTUBE_TOKEN_JSON -> token.json, GOOGLE_CLIENT_SECRET_JSON -> client_secret.json (only if absent).
    """
    e = os.environ if env is None else env
    wrote = []
    for var, name in (("YOUTUBE_TOKEN_JSON", "token.json"), ("GOOGLE_CLIENT_SECRET_JSON", "client_secret.json")):
        val = e.get(var, "").strip()
        if val and not (root / name).exists():
            try:
                json.loads(val)
            except ValueError as exc:
                raise StudioError(f"{var} is not valid JSON.", str(exc),
                                  f"Paste the whole {name} file content.") from exc
            (root / name).write_text(val, encoding="utf-8")
            (root / name).chmod(0o600)
            wrote.append(name)
    return wrote


STORAGE_KEYS = ("STORAGE_BACKEND", "BACKUP_FOLDER", "GITHUB_BACKUP_REPO", "GITHUB_BACKUP_TOKEN",
                "GITHUB_BACKUP_BRANCH", "S3_BUCKET", "S3_KEY", "S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY", "S3_REGION", "YOUTUBE_TOKEN_JSON", "GOOGLE_CLIENT_SECRET_JSON")


def apply_storage_secrets(values: dict) -> None:
    """Copy storage-related hosted secrets (e.g. from st.secrets) into os.environ."""
    for k in STORAGE_KEYS:
        v = values.get(k)
        if v not in (None, ""):
            os.environ[k] = str(v)
