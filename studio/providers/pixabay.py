"""Pixabay stock video search and download (https://pixabay.com/api/docs/)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from studio.providers.footage import StockClip
from studio.util.retry import with_retry

SEARCH_URL = "https://pixabay.com/api/videos/"
LICENCE = "Pixabay Content License (free for commercial use, no attribution required)"
CACHE_SECONDS = 24 * 3600  # Pixabay asks API users to cache results for 24 hours
RENDITIONS = ("large", "medium", "small", "tiny")


def pick_file(video: dict, max_width: int = 2560) -> dict | None:
    """Best rendition: widest landscape file up to max_width, preferring >= 1920 (empty large URLs skipped)."""
    files = [f for f in (video.get("videos") or {}).values()
             if isinstance(f, dict) and f.get("url") and f.get("width")]
    files = [f for f in files if f["width"] >= f.get("height", 0) and f["width"] <= max_width]
    return max(files, key=lambda f: (f["width"] >= 1920, f["width"]), default=None)


class Pixabay:
    """Search with a 24 h cache under assets/cache/pixabay/. Same find() as Pexels."""

    def __init__(self, api_key: str, cache_dir: Path, opener=urllib.request.urlopen, now=time.time) -> None:
        self.key, self.cache, self.open, self.now = api_key, cache_dir, opener, now
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_json(self, url: str) -> dict:
        def go() -> dict:
            req = urllib.request.Request(url, headers={"User-Agent": "yt-studio/0.1"})
            with self.open(req, timeout=30) as r:
                return json.loads(r.read())
        return with_retry(go, "Pixabay search")

    def search(self, query: str, per_page: int = 12) -> list[dict]:
        cache_file = self.cache / f"search_{urllib.parse.quote(query.lower(), safe='')}.json"
        if cache_file.exists() and self.now() - cache_file.stat().st_mtime < CACHE_SECONDS:
            return json.loads(cache_file.read_text())
        qs = urllib.parse.urlencode({"key": self.key, "q": query[:100], "video_type": "film",
                                     "safesearch": "true", "per_page": per_page})
        hits = self._get_json(f"{SEARCH_URL}?{qs}").get("hits", [])
        cache_file.write_text(json.dumps(hits))
        return hits

    def download(self, video: dict) -> StockClip | None:
        f = pick_file(video)
        if not f:
            return None
        path = self.cache / f"{video['id']}_{f['width']}.mp4"
        if not path.exists():
            def go() -> bytes:
                req = urllib.request.Request(f["url"], headers={"User-Agent": "yt-studio/0.1"})
                with self.open(req, timeout=120) as r:
                    return r.read()
            tmp = path.with_suffix(".part")
            tmp.write_bytes(with_retry(go, "Pixabay download"))
            tmp.rename(path)
        user, uid = video.get("user", ""), video.get("user_id", "")
        return StockClip(path, video.get("pageURL", ""), user, f"https://pixabay.com/users/{user}-{uid}/",
                         LICENCE, "Pixabay")

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
