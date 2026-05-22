"""Curated quick-add YouTube songs grouped by decade."""

QUICK_ADDS: list[dict[str, str]] = [
    # 60s
    {"youtube_id": "naQr0uTrH_s", "title": "The Beatles - Hey Jude", "decade": "60s"},
    {"youtube_id": "PGNiXGX2nLU", "title": "Rolling Stones - Satisfaction", "decade": "60s"},
    {"youtube_id": "iYYRH4apXDo", "title": "Aretha Franklin - Respect", "decade": "60s"},
    {"youtube_id": "Mb3iPP-tHdA", "title": "The Doors - Light My Fire", "decade": "60s"},
    {"youtube_id": "Q3dvbM6Pias", "title": "Sam & Dave - Soul Man", "decade": "60s"},
    # 70s
    {"youtube_id": "fJ9rUzIMcZQ", "title": "Queen - Bohemian Rhapsody", "decade": "70s"},
    {"youtube_id": "iPwM_kLJqLY", "title": "Stevie Wonder - Superstition", "decade": "70s"},
    {"youtube_id": "BciS5krYL80", "title": "Eagles - Hotel California", "decade": "70s"},
    {"youtube_id": "9EcjWd-O4jI", "title": "Earth, Wind & Fire - September", "decade": "70s"},
    {"youtube_id": "I_izvAbhExY", "title": "Bee Gees - Stayin' Alive", "decade": "70s"},
    # 80s
    {"youtube_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "decade": "80s"},
    {"youtube_id": "btPJPFnesV4", "title": "Survivor - Eye of the Tiger", "decade": "80s"},
    {"youtube_id": "PIb6AZdTr-A", "title": "Toto - Africa", "decade": "80s"},
    {"youtube_id": "djV11Xbc914", "title": "a-ha - Take On Me", "decade": "80s"},
    {"youtube_id": "9jK-NcRmVcw", "title": "Journey - Don't Stop Believin'", "decade": "80s"},
    # 90s
    {"youtube_id": "hTWKbfoikeg", "title": "Nirvana - Smells Like Teen Spirit", "decade": "90s"},
    {"youtube_id": "fregObNcHC8", "title": "Backstreet Boys - I Want It That Way", "decade": "90s"},
    {"youtube_id": "gJLIiF15wjQ", "title": "Spice Girls - Wannabe", "decade": "90s"},
    {"youtube_id": "L_jWHffIx5E", "title": "Smash Mouth - All Star", "decade": "90s"},
    {"youtube_id": "K2cYWfq--Nw", "title": "Daft Punk - Around the World", "decade": "90s"},
    # 2000s
    {"youtube_id": "fLexgOxsZu0", "title": "OutKast - Hey Ya!", "decade": "2000s"},
    {"youtube_id": "y6120QOlsfU", "title": "Darude - Sandstorm", "decade": "2000s"},
    {"youtube_id": "-N4jf6rtyuw", "title": "Gnarls Barkley - Crazy", "decade": "2000s"},
    {"youtube_id": "60ItHLz5WEA", "title": "Coldplay - Viva La Vida", "decade": "2000s"},
    {"youtube_id": "fWNaR-rxAic", "title": "Black Eyed Peas - I Gotta Feeling", "decade": "2000s"},
    # 2010s
    {"youtube_id": "RgKAFK5djSk", "title": "Wiz Khalifa - See You Again", "decade": "2010s"},
    {"youtube_id": "kJQP7kiw5Fk", "title": "Luis Fonsi - Despacito", "decade": "2010s"},
    {"youtube_id": "JGwWNGJdvx8", "title": "Ed Sheeran - Shape of You", "decade": "2010s"},
    {"youtube_id": "OPf0YbXqDm0", "title": "Mark Ronson - Uptown Funk", "decade": "2010s"},
    {"youtube_id": "9bZkp7q19f0", "title": "PSY - Gangnam Style", "decade": "2010s"},
]


def thumbnail_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
