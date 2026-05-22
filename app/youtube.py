import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def extract_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video id from any common URL shape, or None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        return None

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
    else:
        if parsed.path.rstrip("/") not in ("/watch", ""):
            return None
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]

    return candidate if _VIDEO_ID_RE.match(candidate) else None


_OEMBED_URL = "https://www.youtube.com/oembed"
_DEFAULT_THUMB = "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    thumbnail_url: str


def fetch_video_metadata(video_id: str) -> VideoMetadata:
    """Look up title + thumbnail. Falls back to a default object on any failure."""
    fallback = VideoMetadata(
        title="Unknown title",
        thumbnail_url=_DEFAULT_THUMB.format(video_id=video_id),
    )
    target = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = httpx.get(
            _OEMBED_URL,
            params={"url": target, "format": "json"},
            timeout=5.0,
        )
        if response.status_code != 200:
            return fallback
        payload = response.json()
        return VideoMetadata(
            title=payload.get("title") or fallback.title,
            thumbnail_url=payload.get("thumbnail_url") or fallback.thumbnail_url,
        )
    except (httpx.HTTPError, ValueError):
        return fallback
