"""Curated quick-add YouTube songs grouped by decade — energetic, pump-up tracks."""

QUICK_ADDS: list[dict[str, str]] = [
    # 60s
    {"youtube_id": "PGNiXGX2nLU", "title": "Rolling Stones - Satisfaction", "decade": "60s"},
    {"youtube_id": "iYYRH4apXDo", "title": "Aretha Franklin - Respect", "decade": "60s"},
    {"youtube_id": "Q3dvbM6Pias", "title": "Sam & Dave - Soul Man", "decade": "60s"},
    {"youtube_id": "I_kivACUFXw", "title": "James Brown - I Got You (I Feel Good)", "decade": "60s"},
    {"youtube_id": "B0MHE5MvMpg", "title": "The Monkees - I'm a Believer", "decade": "60s"},
    # 70s
    {"youtube_id": "iPwM_kLJqLY", "title": "Stevie Wonder - Superstition", "decade": "70s"},
    {"youtube_id": "9EcjWd-O4jI", "title": "Earth, Wind & Fire - September", "decade": "70s"},
    {"youtube_id": "I_izvAbhExY", "title": "Bee Gees - Stayin' Alive", "decade": "70s"},
    {"youtube_id": "xFrGuyw1V8s", "title": "ABBA - Dancing Queen", "decade": "70s"},
    {"youtube_id": "3mE-CjSHBSA", "title": "Chic - Good Times", "decade": "70s"},
    # 80s
    {"youtube_id": "btPJPFnesV4", "title": "Survivor - Eye of the Tiger", "decade": "80s"},
    {"youtube_id": "djV11Xbc914", "title": "a-ha - Take On Me", "decade": "80s"},
    {"youtube_id": "9jK-NcRmVcw", "title": "Journey - Don't Stop Believin'", "decade": "80s"},
    {"youtube_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "decade": "80s"},
    {"youtube_id": "zNGp-44BEsE", "title": "Kenny Loggins - Footloose", "decade": "80s"},
    # 90s
    {"youtube_id": "hTWKbfoikeg", "title": "Nirvana - Smells Like Teen Spirit", "decade": "90s"},
    {"youtube_id": "gJLIiF15wjQ", "title": "Spice Girls - Wannabe", "decade": "90s"},
    {"youtube_id": "L_jWHffIx5E", "title": "Smash Mouth - All Star", "decade": "90s"},
    {"youtube_id": "K2cYWfq--Nw", "title": "Daft Punk - Around the World", "decade": "90s"},
    {"youtube_id": "tbNlMtqrYS0", "title": "The Proclaimers - 500 Miles", "decade": "90s"},
    # 2000s
    {"youtube_id": "fLexgOxsZu0", "title": "OutKast - Hey Ya!", "decade": "2000s"},
    {"youtube_id": "y6120QOlsfU", "title": "Darude - Sandstorm", "decade": "2000s"},
    {"youtube_id": "fWNaR-rxAic", "title": "Black Eyed Peas - I Gotta Feeling", "decade": "2000s"},
    {"youtube_id": "_Yhyp-_hX2s", "title": "Eminem - Lose Yourself", "decade": "2000s"},
    {"youtube_id": "KQ6zr6kCPj8", "title": "LMFAO - Party Rock Anthem", "decade": "2000s"},
    # 2010s
    {"youtube_id": "OPf0YbXqDm0", "title": "Mark Ronson - Uptown Funk", "decade": "2010s"},
    {"youtube_id": "9bZkp7q19f0", "title": "PSY - Gangnam Style", "decade": "2010s"},
    {"youtube_id": "y6Sxv-sUYtM", "title": "Pharrell Williams - Happy", "decade": "2010s"},
    {"youtube_id": "IcrbM1l_BoI", "title": "Avicii - Wake Me Up", "decade": "2010s"},
    {"youtube_id": "5NV6Rdv1h3Q", "title": "Daft Punk - Get Lucky", "decade": "2010s"},
]


def thumbnail_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
