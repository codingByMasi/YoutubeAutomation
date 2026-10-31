"""Pexels stock video search and download (https://www.pexels.com/api/documentation/)."""

from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from studio.providers.footage import StockClip
from studio.util.retry import with_retry

SEARCH_URL = "https://api.pexels.com/v1/videos/search"
LICENCE = "Pexels License (free for commercial use, no attribution required)"


def pick_file(video: dict, max_width: int = 1920) -> dict | None:
    """Best landscape mp4 rendition, widest up to max_width (1920: the video is 1080p)."""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
    files = [f for f in files if f["width"] >= f.get("height", 0) and f["width"] <= max_width]
    return max(files, key=lambda f: (f["width"] >= 1920, f["width"]), default=None)


class Pexels:
    """Search with caching under assets/cache/pexels/."""

    def __init__(self, api_key: str, cache_dir: Path, opener=urllib.request.urlopen) -> None:
        self.key, self.cache, self.open = api_key, cache_dir, opener
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_json(self, url: str) -> dict:
        def go() -> dict:
            req = urllib.request.Request(url, headers={"Authorization": self.key, "User-Agent": "yt-studio/0.1"})
            with self.open(req, timeout=30) as r:
                return json.loads(r.read())
        return with_retry(go, "Pexels search")

    def search(self, query: str, per_page: int = 8) -> list[dict]:
        cache_file = self.cache / f"search_{urllib.parse.quote(query.lower(), safe='')}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        qs = urllib.parse.urlencode({"query": query, "orientation": "landscape", "size": "medium",
                                     "per_page": per_page})
        videos = self._get_json(f"{SEARCH_URL}?{qs}").get("videos", [])
        cache_file.write_text(json.dumps(videos))
        return videos

    def download(self, video: dict) -> StockClip | None:
        f = pick_file(video)
        if not f:
            return None
        path = self.cache / f"{video['id']}_{f['width']}.mp4"
        if not path.exists():
            tmp = path.with_suffix(".part")

            def go() -> None:  # stream to disk: clips can be 100 MB and must not sit in memory
                req = urllib.request.Request(f["link"], headers={"User-Agent": "yt-studio/0.1"})
                with self.open(req, timeout=120) as r, tmp.open("wb") as out:
                    shutil.copyfileobj(r, out, 1 << 20)
            with_retry(go, "Pexels download")
            tmp.rename(path)
        user = video.get("user") or {}
        return StockClip(path, video.get("url", ""), user.get("name", ""), user.get("url", ""), LICENCE, "Pexels")

    def find(self, keywords: list[str], exclude: set[int] | None = None) -> StockClip | None:
        """First unused clip for the first keyword that returns results."""
        exclude = exclude if exclude is not None else set()
        for kw in keywords:
            for v in self.search(kw):
                if v["id"] in exclude:
                    continue
                clip = self.download(v)
                if clip:
                    exclude.add(v["id"])
                    return clip
        return None
