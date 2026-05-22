import pytest

from app.youtube import VideoMetadata, extract_video_id, fetch_video_metadata


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


def test_fetch_video_metadata_success(httpx_mock):
    httpx_mock.add_response(
        json={
            "title": "Rick Astley - Never Gonna Give You Up",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        }
    )
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta == VideoMetadata(
        title="Rick Astley - Never Gonna Give You Up",
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    )


def test_fetch_video_metadata_network_error_falls_back(httpx_mock):
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("boom"))
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta.title == "Unknown title"
    assert meta.thumbnail_url.endswith("/hqdefault.jpg")


def test_fetch_video_metadata_404_falls_back(httpx_mock):
    httpx_mock.add_response(status_code=404)
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta.title == "Unknown title"
