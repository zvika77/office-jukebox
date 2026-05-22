import pytest

from app.youtube import extract_video_id


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
            "dQw4w9WgXcQ",
        ),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        (
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
        ),
    ],
)
def test_extract_video_id_valid(url, expected):
    assert extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/",
        "https://youtu.be/",
        "https://www.youtube.com/playlist?list=PL123",
    ],
)
def test_extract_video_id_invalid(url):
    assert extract_video_id(url) is None
