import random
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

_DECADE_SONGS: dict[str, list[str]] = {
    "60s": [
        "Rolling Stones Satisfaction",
        "Aretha Franklin Respect",
        "James Brown I Feel Good",
        "Sam Dave Soul Man",
        "Wilson Pickett Mustang Sally",
        "The Kinks You Really Got Me",
        "The Who My Generation",
        "Martha Reeves Dancing in the Street",
        "Marvin Gaye I Heard It Through the Grapevine",
        "The Temptations Ain't Too Proud to Beg",
        "Tommy James Mony Mony",
        "The Troggs Wild Thing",
        "The Four Tops I Can't Help Myself",
        "Creedence Clearwater Revival Proud Mary",
        "The Monkees I'm a Believer",
        "The Beach Boys Good Vibrations",
        "Spencer Davis Group Gimme Some Lovin",
        "Sly and the Family Stone Dance to the Music",
        "Eddie Floyd Knock on Wood",
        "Wilson Pickett In the Midnight Hour",
    ],
    "70s": [
        "ABBA Dancing Queen",
        "Bee Gees Stayin Alive",
        "Stevie Wonder Superstition",
        "Earth Wind Fire September",
        "Chic Good Times",
        "KC and the Sunshine Band Get Down Tonight",
        "Donna Summer Hot Stuff",
        "Gloria Gaynor I Will Survive",
        "Queen We Will Rock You",
        "AC DC Highway to Hell",
        "Thin Lizzy The Boys Are Back in Town",
        "Aerosmith Walk This Way",
        "Kool and the Gang Jungle Boogie",
        "Jackson 5 ABC",
        "Wild Cherry Play That Funky Music",
        "Village People YMCA",
        "Sister Sledge We Are Family",
        "Blondie Heart of Glass",
        "Parliament Give Up the Funk",
        "Rose Royce Wishing on a Star",
    ],
    "80s": [
        "Survivor Eye of the Tiger",
        "Michael Jackson Beat It",
        "Journey Don't Stop Believin",
        "Bon Jovi Livin on a Prayer",
        "Kenny Loggins Footloose",
        "Van Halen Jump",
        "Cyndi Lauper Girls Just Want to Have Fun",
        "Twisted Sister We're Not Gonna Take It",
        "AC DC Back in Black",
        "Joan Jett I Love Rock and Roll",
        "Prince Let's Go Crazy",
        "Rick James Super Freak",
        "Pat Benatar Hit Me with Your Best Shot",
        "Europe The Final Countdown",
        "Bruce Springsteen Born in the USA",
        "Huey Lewis The Power of Love",
        "Tina Turner What's Love Got to Do with It",
        "A-ha Take On Me",
        "Queen Another One Bites the Dust",
        "Devo Whip It",
    ],
    "90s": [
        "Nirvana Smells Like Teen Spirit",
        "Spice Girls Wannabe",
        "The Proclaimers 500 Miles",
        "Daft Punk Around the World",
        "No Doubt Just a Girl",
        "Green Day Basket Case",
        "Red Hot Chili Peppers Give It Away",
        "Blur Song 2",
        "Backstreet Boys Everybody",
        "Destiny's Child Say My Name",
        "Fatboy Slim The Rockafeller Skank",
        "Reel 2 Real I Like to Move It",
        "Los Del Rio Macarena",
        "Aqua Barbie Girl",
        "2 Unlimited Get Ready for This",
        "Snap The Power",
        "Tag Team Whoomp There It Is",
        "Inner Circle Bad Boys",
        "Ace of Base The Sign",
        "Corona The Rhythm of the Night",
    ],
    "2000s": [
        "OutKast Hey Ya",
        "Darude Sandstorm",
        "Black Eyed Peas I Gotta Feeling",
        "Eminem Lose Yourself",
        "Daft Punk One More Time",
        "The White Stripes Seven Nation Army",
        "The Killers Mr Brightside",
        "Franz Ferdinand Take Me Out",
        "Nelly Hot in Herre",
        "Missy Elliott Work It",
        "50 Cent In Da Club",
        "Beyonce Crazy in Love",
        "Kelly Clarkson Since U Been Gone",
        "Gwen Stefani Hollaback Girl",
        "Usher Yeah",
        "Justin Timberlake Sexyback",
        "Gorillaz Feel Good Inc",
        "Yeah Yeah Yeahs Heads Will Roll",
        "Arctic Monkeys I Bet You Look Good on the Dancefloor",
        "Jay-Z 99 Problems",
    ],
    "2010s": [
        "Mark Ronson Uptown Funk",
        "PSY Gangnam Style",
        "Pharrell Williams Happy",
        "Avicii Wake Me Up",
        "Daft Punk Get Lucky",
        "LMFAO Party Rock Anthem",
        "Walk the Moon Shut Up and Dance",
        "Sia Chandelier",
        "Katy Perry Roar",
        "Bruno Mars Treasure",
        "Taylor Swift Shake It Off",
        "Imagine Dragons Radioactive",
        "Macklemore Can't Hold Us",
        "Dua Lipa New Rules",
        "Calvin Harris Summer",
        "Bastille Pompeii",
        "fun We Are Young",
        "Lady Gaga Born This Way",
        "Carly Rae Jepsen Call Me Maybe",
        "The Weeknd Cant Feel My Face",
    ],
}

_PICKS_PER_DECADE = 5

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_TITLE_NOISE_RE = re.compile(
    r"\s*[\(\[]\s*("
    r"official\s*(music\s*)?video|official\s*audio|official\s*lyric\s*video|"
    r"lyric\s*video|lyrics?|audio|4k|hd|hq|remaster(?:ed)?|"
    r"\d{4}\s*remaster(?:ed)?|vevo|full\s*video|explicit"
    r")\s*[\)\]]"
    r"|\s*[-–|]\s*(official\s*(music\s*)?video|official\s*audio|lyrics?)$",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Strip YouTube noise suffixes like (Official Video), [4K], etc."""
    return _TITLE_NOISE_RE.sub("", title).strip()
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


class YouTubeAPIError(Exception):
    """Raised when the YouTube Data API returns an error response."""


def _search_one(query: str, api_key: str) -> dict | None:
    """Search YouTube for a single song; return the top result or None."""
    try:
        resp = httpx.get(
            _SEARCH_URL,
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "videoCategoryId": "10",
                "videoEmbeddable": "true",
                "maxResults": "1",
                "key": api_key,
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    if resp.status_code != 200:
        error = data.get("error", {})
        message = error.get("message") or f"HTTP {resp.status_code}"
        raise YouTubeAPIError(message)

    items = data.get("items", [])
    if not items:
        return None

    item = items[0]
    video_id = item.get("id", {}).get("videoId")
    if not video_id:
        return None

    snippet = item.get("snippet", {})
    thumbs = snippet.get("thumbnails", {})
    thumb = (
        thumbs.get("high", thumbs.get("medium", thumbs.get("default", {})))
    ).get("url", f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
    raw_title = (snippet.get("title", "Unknown")
                 .replace("&amp;", "&")
                 .replace("&#39;", "'")
                 .replace("&quot;", '"')
                 .replace("&lt;", "<")
                 .replace("&gt;", ">"))
    return {"youtube_id": video_id, "title": clean_title(raw_title), "thumbnail_url": thumb}


def search_songs_for_decade(decade: str, api_key: str) -> list[dict]:
    """Search YouTube for a random sample of curated songs in the decade.

    Picks _PICKS_PER_DECADE songs at random so each Refresh shows a fresh set.
    Raises YouTubeAPIError on API-level errors (bad key, quota exceeded).
    """
    pool = _DECADE_SONGS.get(decade, [])
    sample = random.sample(pool, min(_PICKS_PER_DECADE, len(pool)))
    results = []
    for song in sample:
        entry = _search_one(f"{song} official music video", api_key)
        if entry:
            results.append({**entry, "decade": decade})
    return results


def extract_playlist_id(value: str) -> str | None:
    """Return the playlist ID from a full URL or a bare ID string, or None if unrecognisable."""
    value = value.strip()
    if not value:
        return None
    # Bare ID (no slashes or query chars) — accept as-is
    if "/" not in value and "?" not in value:
        return value
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    return (parse_qs(parsed.query).get("list") or [""])[0] or None


def fetch_playlist_songs(playlist_id: str, api_key: str) -> list[dict]:
    """Fetch all videos from a YouTube playlist (up to 50) and return them shuffled.

    Raises YouTubeAPIError on API-level errors (bad key, quota exceeded, private playlist).
    """
    try:
        resp = httpx.get(
            _PLAYLIST_ITEMS_URL,
            params={
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": "50",
                "key": api_key,
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        return []

    try:
        data = resp.json()
    except ValueError:
        return []

    if resp.status_code != 200:
        error = data.get("error", {})
        message = error.get("message") or f"HTTP {resp.status_code}"
        raise YouTubeAPIError(message)

    results = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId")
        if not video_id:
            continue
        raw_title = snippet.get("title", "")
        if raw_title in ("Deleted video", "Private video", ""):
            continue
        raw_title = (raw_title
                     .replace("&amp;", "&")
                     .replace("&#39;", "'")
                     .replace("&quot;", '"')
                     .replace("&lt;", "<")
                     .replace("&gt;", ">"))
        thumbs = snippet.get("thumbnails", {})
        thumb = (
            thumbs.get("high", thumbs.get("medium", thumbs.get("default", {})))
        ).get("url", f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
        results.append({
            "youtube_id": video_id,
            "title": clean_title(raw_title),
            "thumbnail_url": thumb,
        })

    random.shuffle(results)
    return results


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
            title=clean_title(payload.get("title") or fallback.title),
            thumbnail_url=payload.get("thumbnail_url") or fallback.thumbnail_url,
        )
    except (httpx.HTTPError, ValueError):
        return fallback
