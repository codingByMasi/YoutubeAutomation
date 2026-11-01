"""Thin YouTube Data API v3 client: every call is quota-checked, logged, and retried."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio.errors import StudioError
from studio.util.retry import with_retry
from studio.youtube.quota import QuotaTracker


class YouTubeData:
    """Wraps a googleapiclient `youtube` service."""

    def __init__(self, service: Any, quota: QuotaTracker) -> None:
        self.yt = service
        self.quota = quota

    def _call(self, endpoint: str, make_request) -> dict:
        def attempt() -> dict:
            with self.quota.spend(endpoint):
                return make_request().execute()

        try:
            return with_retry(attempt, f"YouTube {endpoint}")
        except StudioError:
            raise
        except Exception as exc:  # googleapiclient.errors.HttpError and friends
            status = getattr(getattr(exc, "resp", None), "status", "?")
            hint = "Check the request fields against the YouTube Data API docs."
            if str(status) == "403":
                hint = "Check that the API is enabled and quota is available in Google Cloud Console."
            if str(status) == "401":
                hint = "Delete token.json and re-run to sign in again."
            raise StudioError(f"YouTube {endpoint} failed (HTTP {status}).", str(exc), hint) from exc

    # --- research ---
    def search_videos(self, query: str, published_after: str, max_results: int = 25) -> list[dict]:
        r = self._call("search.list", lambda: self.yt.search().list(
            part="snippet", q=query, type="video", order="viewCount",
            publishedAfter=published_after, maxResults=max_results, relevanceLanguage="en"))
        return r.get("items", [])

    def videos(self, ids: list[str], part: str = "snippet,statistics,contentDetails") -> list[dict]:
        if not ids:
            return []
        return self._call("videos.list", lambda: self.yt.videos().list(part=part, id=",".join(ids[:50]))).get(
            "items", [])

    def channels(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        return self._call("channels.list", lambda: self.yt.channels().list(
            part="statistics,snippet", id=",".join(ids[:50]))).get("items", [])

    def my_channel(self) -> dict:
        """The channel the signed-in account is working as (id, title, subscriber count), or {}."""
        items = self._call("channels.list", lambda: self.yt.channels().list(
            part="statistics,snippet", mine=True)).get("items", [])
        return items[0] if items else {}

    # --- publishing ---
    def upload(self, file: Path, body: dict) -> dict:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(file), chunksize=-1, resumable=True, mimetype="video/mp4")
        return self._call("videos.insert", lambda: self.yt.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media))

    def set_thumbnail(self, video_id: str, image: Path) -> dict:
        from googleapiclient.http import MediaFileUpload

        return self._call("thumbnails.set", lambda: self.yt.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(image))))

    def insert_caption(self, video_id: str, srt: Path, language: str = "en", name: str = "English") -> dict:
        from googleapiclient.http import MediaFileUpload

        body = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
        return self._call("captions.insert", lambda: self.yt.captions().insert(
            part="snippet", body=body, media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")))

    def add_to_playlist(self, playlist_id: str, video_id: str) -> dict:
        body = {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
        return self._call("playlistItems.insert", lambda: self.yt.playlistItems().insert(part="snippet", body=body))

    # --- comments ---
    def comment_threads(self, video_id: str, max_results: int = 50) -> list[dict]:
        return self._call("commentThreads.list", lambda: self.yt.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=max_results, order="time", textFormat="plainText")).get(
            "items", [])

    def reply_to_comment(self, parent_id: str, text: str) -> dict:
        body = {"snippet": {"parentId": parent_id, "textOriginal": text}}
        return self._call("comments.insert", lambda: self.yt.comments().insert(part="snippet", body=body))
