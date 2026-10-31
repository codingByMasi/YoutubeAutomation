"""Still-image search: Pixabay photos (key needed) and Wikimedia Commons (no key). Licence is recorded per image."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from studio.errors import StudioError
from studio.providers.footage import StockClip
from studio.util.logging import get_logger
from studio.util.retry import with_retry

log = get_logger("images")
UA = "yt-studio/0.1 (https://github.com/codingByMasi/YoutubeAutomation)"
PIXABAY_URL = "https://pixabay.com/api/"
COMMONS_URL = "https://commons.wikimedia.org/w/api.php"
PIXABAY_LICENCE = "Pixabay Content License (free for commercial use, no attribution required)"
CACHE_SECONDS = 24 * 3600
# Licences that allow commercial reuse and modification. NC / ND / unknown are rejected.
OK_LICENCE = re.compile(r"^(public domain|pd\b|cc0|cc[ -]by(?![ -](nc|nd))(?:[ -]sa)?\b)", re.I)
NEEDS_CREDIT = re.compile(r"^cc[ -]by", re.I)


STOP = {"a", "an", "the", "of", "in", "on", "at", "and", "or", "for", "to", "with", "view", "photo", "image", "stock"}
# Commons is full-text search: it returns maps, logos, scans and posters that look broken as video backgrounds.
JUNK_NAME = re.compile(r"\b(logo|map|flag|diagram|chart|icon|coat of arms|poster|scan|stamp|screenshot|"
                       r"signature|banner|infographic|template|svg|cover|portrait of)\b", re.I)


def words(text: str) -> set[str]:
    """Lower-case content words (3+ letters, light plural stemming) for relevance matching."""
    out = set()
    for w in re.findall(r"[a-z]{3,}", (text or "").lower()):
        if w not in STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return out


def relevance(keyword: str, candidate_text: str) -> float:
    """Share of the keyword's content words found in the candidate's tags/title (0..1)."""
    want = words(keyword)
    return len(want & words(candidate_text)) / len(want) if want else 0.0


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def commons_licence_ok(meta: dict) -> str | None:
    """Licence short name if this Commons file may be reused commercially, else None."""
    name = (meta.get("LicenseShortName") or {}).get("value", "").strip()
    if not name or not OK_LICENCE.match(name):
        return None
    if (meta.get("NonFree") or {}).get("value", "").lower() == "true":
        return None
    if (meta.get("Restrictions") or {}).get("value"):  # trademark / personality-rights notices
        return None
    return name


class _Base:
    def __init__(self, cache_dir: Path, opener=urllib.request.urlopen, now=time.time) -> None:
        self.cache, self.open, self.now = cache_dir, opener, now
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url: str, label: str, timeout: int = 30) -> bytes:
        def go() -> bytes:
            with self.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return r.read()
        return with_retry(go, label)

    def _cached_json(self, name: str, url: str, label: str):
        f = self.cache / f"search_{urllib.parse.quote(name.lower(), safe='')}.json"
        if f.exists() and self.now() - f.stat().st_mtime < CACHE_SECONDS:
            return json.loads(f.read_text(encoding="utf-8"))
        data = json.loads(self._fetch(url, label))
        f.write_text(json.dumps(data), encoding="utf-8")
        return data

    def _save(self, name: str, url: str, label: str) -> Path:
        path = self.cache / name
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(self._fetch(url, label, 120))
            tmp.rename(path)
        return path


class PixabayImages(_Base):
    """Pixabay photos at 1280 px wide (the API's `largeImageURL`)."""

    def __init__(self, api_key: str, cache_dir: Path, **kw) -> None:
        super().__init__(cache_dir, **kw)
        self.key = api_key

    def search(self, query: str, per_page: int = 15) -> list[dict]:
        qs = urllib.parse.urlencode({"key": self.key, "q": query[:100], "image_type": "photo",
                                     "orientation": "horizontal", "min_width": 1200,
                                     "safesearch": "true", "per_page": per_page})
        return self._cached_json(f"img_{query}", f"{PIXABAY_URL}?{qs}", "Pixabay image search").get("hits", [])

    def find(self, keywords: list[str], exclude: set | None = None) -> StockClip | None:
        exclude = exclude if exclude is not None else set()
        for kw in keywords:
            ranked = sorted(self.search(kw), key=lambda h: -relevance(kw, h.get("tags", "")))
            for h in ranked:
                key = ("pixabay", h["id"])
                if key in exclude or not h.get("largeImageURL") or relevance(kw, h.get("tags", "")) < MIN_RELEVANCE:
                    continue
                path = self._save(f"{h['id']}.jpg", h["largeImageURL"], "Pixabay image download")
                exclude.add(key)
                user = h.get("user", "")
                profile = f"https://pixabay.com/users/{user}-{h.get('user_id', '')}/"
                return StockClip(path, h.get("pageURL", ""), user, profile, PIXABAY_LICENCE, "Pixabay")
        return None


class Commons(_Base):
    """Wikimedia Commons bitmaps with an allow-listed licence (public domain, CC0, CC BY, CC BY-SA)."""

    def search(self, query: str, limit: int = 15) -> list[dict]:
        qs = urllib.parse.urlencode({
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": limit,
            "gsrsearch": f"{query[:100]} filetype:bitmap", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1920})
        pages = self._cached_json(f"commons_{query}", f"{COMMONS_URL}?{qs}", "Commons search")
        return sorted((pages.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))

    def find(self, keywords: list[str], exclude: set | None = None) -> StockClip | None:
        exclude = exclude if exclude is not None else set()
        for kw in keywords:
            for page in self.search(kw):
                info = (page.get("imageinfo") or [{}])[0]
                key = ("commons", page.get("pageid"))
                lic = commons_licence_ok(info.get("extmetadata") or {})
                title = page.get("title", "")
                w, h = info.get("width", 0), info.get("height", 0)
                if (key in exclude or not lic or info.get("mime") not in ("image/jpeg", "image/png")
                        or w < 1280 or h < 720 or not 1.25 <= w / max(h, 1) <= 2.4
                        or JUNK_NAME.search(title) or relevance(kw, title) < MIN_RELEVANCE):
                    continue
                url = info.get("thumburl") or info["url"]
                ext = ".png" if info["mime"] == "image/png" else ".jpg"
                path = self._save(f"{page['pageid']}{ext}", url, "Commons download")
                exclude.add(key)
                artist = _strip_html((info["extmetadata"].get("Artist") or {}).get("value", "")) or "Unknown author"
                return StockClip(path, info.get("descriptionurl", ""), artist, info.get("descriptionurl", ""),
                                 f"{lic} (Wikimedia Commons)", "Wikimedia Commons")
        return None


MIN_RELEVANCE = 0.34  # at least a third of the keyword's words must appear in the tags/title
MAX_SOURCE_FAILURES = 2


class ImageSearch:
    """Try each image source in order for each keyword."""

    def __init__(self, sources: list) -> None:
        self.sources = sources
        self.failures: dict[int, int] = {}

    def find(self, keywords: list[str], exclude: set | None = None) -> StockClip | None:
        exclude = exclude if exclude is not None else set()
        for kw in keywords:
            for src in self.sources:
                if self.failures.get(id(src), 0) >= MAX_SOURCE_FAILURES:
                    continue  # this source has been failing all run; retrying costs a minute per segment
                try:
                    clip = src.find([kw], exclude)
                except StudioError as e:  # one source being down must not stop the build
                    self.failures[id(src)] = self.failures.get(id(src), 0) + 1
                    log.warning("Image source %s skipped: %s", type(src).__name__, e)
                    continue
                if clip:
                    return clip
        return None


def make_images(settings) -> tuple[str, ImageSearch | None]:
    """(names, searcher). IMAGE_PROVIDER: auto (Pixabay if keyed, then Commons), pixabay, commons, none."""
    choice = settings.image_provider
    cache = settings.assets_dir / "cache"
    srcs, names = [], []
    if choice in ("auto", "pixabay") and settings.pixabay_api_key:
        srcs.append(PixabayImages(settings.pixabay_api_key, cache / "pixabay_img"))
        names.append("Pixabay images")
    if choice in ("auto", "commons"):
        srcs.append(Commons(cache / "commons"))
        names.append("Wikimedia Commons")
    return (", ".join(names) or "none"), (ImageSearch(srcs) if srcs else None)
