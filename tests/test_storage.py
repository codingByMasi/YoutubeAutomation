"""Storage: export/import, deletion with confirmation, autosave/restore, backends (no network)."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from studio.errors import StudioError
from studio.models import Idea, Title, Video
from studio.storage import data, sync


def seed(ctx, channel="default"):
    idea = Idea(seed="s", topic="t", channel_id=channel)
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id)
    ctx.session.add(v)
    ctx.session.flush()
    ctx.session.add(Title(video_id=v.id, text="hello", length=5))
    ctx.session.commit()
    p = ctx.settings.project_dir(v.id)
    (p / "script.json").write_text("{}")
    (p / "final.mp4").write_bytes(b"x" * 100)
    return v.id


def test_export_excludes_media_and_secrets(ctx, root):
    seed(ctx)
    (root / "token.json").write_text("{}")
    (root / "growth").mkdir()
    (root / "growth" / "channels.json").write_text("{}")
    names = zipfile.ZipFile(io.BytesIO(data.export_zip(root))).namelist()
    assert "studio.db" in names and "growth/channels.json" in names and "projects/1/script.json" in names
    assert "projects/1/final.mp4" not in names and "token.json" not in names
    full = zipfile.ZipFile(io.BytesIO(data.export_zip(root, include_media=True, include_secrets=True))).namelist()
    assert "projects/1/final.mp4" in full and "token.json" in full


def test_import_roundtrip_and_replace(ctx, root, tmp_path):
    seed(ctx)
    blob = data.export_zip(root)
    ctx.session.close()
    ctx.engine.dispose()
    data.wipe(root, "DELETE")
    assert not (root / "studio.db").exists()
    assert data.import_zip(root, blob) >= 3
    assert (root / "projects" / "1" / "script.json").exists()
    assert data.import_zip(root, blob, replace=True) >= 3


def test_import_rejects_unsafe_and_invalid(root):
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", "{}")
        z.writestr("../evil.txt", "x")
    with pytest.raises(StudioError, match="Unsafe"):
        data.import_zip(root, bad.getvalue())
    with pytest.raises(StudioError, match="valid backup"):
        data.import_zip(root, b"not a zip")
    other = io.BytesIO()
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("random.txt", "x")
    with pytest.raises(StudioError, match="does not look"):
        data.import_zip(root, other.getvalue())


def test_import_ignores_secrets_unless_allowed(root):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", "{}")
        z.writestr("token.json", "{}")
        z.writestr("other/file.txt", "x")
    data.import_zip(root, buf.getvalue())
    assert not (root / "token.json").exists() and not (root / "other").exists()
    data.import_zip(root, buf.getvalue(), allow_secrets=True)
    assert (root / "token.json").exists()


def test_deletes_require_exact_confirmation(ctx, root):
    vid = seed(ctx)
    with pytest.raises(StudioError, match="not confirmed"):
        data.delete_video(ctx.session, root, vid, "delete")
    with pytest.raises(StudioError):
        data.wipe(root, "yes")
    with pytest.raises(StudioError):
        data.delete_channel_data(ctx.session, root, "default", "")
    assert (root / "projects" / str(vid)).exists() and ctx.session.get(Video, vid)


def test_delete_video_removes_rows_and_folder(ctx, root):
    vid = seed(ctx)
    data.delete_video(ctx.session, root, vid, "DELETE")
    assert ctx.session.get(Video, vid) is None
    assert ctx.session.query(Title).count() == 0 and ctx.session.query(Idea).count() == 0
    assert not (root / "projects" / str(vid)).exists()


def test_delete_channel_data_only_that_channel(ctx, root):
    a, b = seed(ctx, "a"), seed(ctx, "b")
    (root / "growth" / "c" / "a").mkdir(parents=True)
    (root / "growth" / "c" / "a" / "x.json").write_text("{}")
    assert data.delete_channel_data(ctx.session, root, "a", "DELETE") == [a]
    assert ctx.session.get(Video, b) and not (root / "growth" / "c" / "a").exists()


def test_delete_media_and_cache(ctx, root):
    vid = seed(ctx)
    (root / "assets" / "cache").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "cache" / "a.mp4").write_bytes(b"123")
    assert data.delete_media(root, vid) == 100
    assert (root / "projects" / str(vid) / "script.json").exists()
    assert data.clear_cache(root) == 3


def test_usage_and_sizes(ctx, root):
    vid = seed(ctx)
    assert {a.name for a in data.usage(root)} >= {"Database", "Videos (projects)"}
    assert data.project_sizes(root)[vid] >= 100
    assert data.human(2048) == "2.0 KB"


class MemBackend:
    label = "mem"

    def __init__(self):
        self.blob = None
        self.puts = 0

    def put(self, blob):
        self.blob, self.puts = blob, self.puts + 1

    def get(self):
        return self.blob


def test_autosave_only_when_changed_and_throttled(ctx, root):
    seed(ctx)
    be = MemBackend()
    assert sync.autosave(root, None) == "off"
    assert sync.autosave(root, be, now=1000).startswith("saved")
    assert sync.autosave(root, be, now=2000) == "up to date"
    (root / "growth").mkdir(exist_ok=True)
    (root / "growth" / "n.json").write_text("{}")
    assert sync.autosave(root, be, now=1010) == "up to date"  # throttled
    assert sync.autosave(root, be, now=2000).startswith("saved") and be.puts == 2


def test_restore_on_fresh_disk(ctx, root, tmp_path):
    seed(ctx)
    be = MemBackend()
    sync.autosave(root, be, force=True)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert sync.restore_if_empty(fresh, be).startswith("restored")
    assert (fresh / "projects" / "1" / "script.json").exists()
    assert sync.restore_if_empty(fresh, be) == "skipped"  # DB exists now
    other = tmp_path / "o"
    other.mkdir()
    assert sync.restore_if_empty(other, MemBackend()) == "no backup found"


def test_autosave_reports_failure_without_raising(ctx, root):
    class Boom(MemBackend):
        def put(self, blob):
            raise StudioError("down", "why", "retry")

    seed(ctx)
    assert sync.autosave(root, Boom(), force=True).startswith("backup failed")


def test_folder_backend_roundtrip(tmp_path):
    fb = sync.FolderBackend(str(tmp_path / "bk"))
    assert fb.get() is None
    fb.put(b"abc")
    assert fb.get() == b"abc"


def test_backend_from_env():
    assert sync.backend_from_env({}) is None
    assert isinstance(sync.backend_from_env({"STORAGE_BACKEND": "folder", "BACKUP_FOLDER": "/tmp/x"}),
                      sync.FolderBackend)
    with pytest.raises(StudioError):
        sync.backend_from_env({"STORAGE_BACKEND": "github"})
    with pytest.raises(StudioError):
        sync.backend_from_env({"STORAGE_BACKEND": "s3"})
    with pytest.raises(StudioError):
        sync.backend_from_env({"STORAGE_BACKEND": "ftp"})
    assert isinstance(sync.backend_from_env({"STORAGE_BACKEND": "github", "GITHUB_BACKUP_REPO": "a/b",
                                             "GITHUB_BACKUP_TOKEN": "t"}), sync.GitHubBackend)


def test_github_refuses_public_repo_and_big_blob(monkeypatch):
    g = sync.GitHubBackend("a/b", "tok")
    calls = []

    def fake(method, url, body=None, raw=False):
        calls.append((method, url))
        return {"private": False}

    monkeypatch.setattr(g, "_call", fake)
    with pytest.raises(StudioError, match="public"):
        g.put(b"x")
    with pytest.raises(StudioError, match="too big"):
        g.put(b"x" * (sync.GITHUB_MAX_BYTES + 1))


def test_github_put_get(monkeypatch):
    g = sync.GitHubBackend("a/b", "tok", "main")
    sent = {}

    def fake(method, url, body=None, raw=False):
        if url == "/repos/a/b":
            return {"private": True}
        if method == "PUT":
            sent.update(body)
            return {}
        return b"data" if raw else {"sha": "abc"}

    monkeypatch.setattr(g, "_call", fake)
    g.put(b"hi")
    assert sent["sha"] == "abc" and sent["branch"] == "main"
    assert g.get() == b"data"


def test_materialize_secret_files(root):
    env = {"YOUTUBE_TOKEN_JSON": json.dumps({"a": 1})}
    assert sync.materialize_secret_files(root, env) == ["token.json"]
    assert sync.materialize_secret_files(root, env) == []  # never overwrites
    with pytest.raises(StudioError, match="valid JSON"):
        sync.materialize_secret_files(root, {"GOOGLE_CLIENT_SECRET_JSON": "{nope"})
