import re
from urllib.parse import parse_qs, urlparse

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
