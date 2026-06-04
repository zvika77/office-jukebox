def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def test_add_song_success(client, httpx_mock):
    httpx_mock.add_response(
        json={
            "title": "Hotel California",
            "thumbnail_url": "https://example.com/t.jpg",
        }
    )
    response = client.post(
        "/api/songs",
        json={"youtube_url": "https://www.youtube.com/watch?v=BciS5krYL80"},
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["youtube_id"] == "BciS5krYL80"
    assert body["title"] == "Hotel California"
    assert body["added_by_name"] == "Maya"


def test_add_song_invalid_url_returns_400(client):
    response = client.post(
        "/api/songs",
        json={"youtube_url": "https://example.com/foo"},
        headers=_headers(),
    )
    assert response.status_code == 400


def test_add_duplicate_upvotes_existing(client, httpx_mock):
    httpx_mock.add_response(
        json={"title": "Hotel California", "thumbnail_url": "https://example.com/t.jpg"}
    )
    url = "https://www.youtube.com/watch?v=BciS5krYL80"
    first = client.post("/api/songs", json={"youtube_url": url}, headers=_headers("v-1"))
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post(
        "/api/songs",
        json={"youtube_url": url},
        headers=_headers("v-2", "Dan"),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["id"] == first_id
    assert body["already_in_list"] is True

    listing = client.get("/api/songs", headers=_headers("v-2", "Dan")).json()
    matching = next(row for row in listing if row["id"] == first_id)
    assert matching["votes"] == 1
    assert matching["did_i_vote"] is True


def test_list_songs_sorted_by_votes_then_added_at(client, httpx_mock):
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"}, is_reusable=True)

    a = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/aaaaaaaaaaa"},
        headers=_headers("v-1", "Maya"),
    ).json()
    b = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/bbbbbbbbbbb"},
        headers=_headers("v-1", "Maya"),
    ).json()

    client.post(f"/api/songs/{b['id']}/vote", headers=_headers("v-2", "Dan"))

    listing = client.get("/api/songs", headers=_headers("v-9", "Sam")).json()
    assert listing[0]["id"] == b["id"]
    assert listing[0]["votes"] == 1
    assert listing[1]["id"] == a["id"]
    assert listing[1]["votes"] == 0
    assert all(row["did_i_vote"] is False for row in listing)


def test_list_songs_anonymous_read_is_public(client, httpx_mock):
    # The TV reads /api/songs without signing in: no auth headers at all.
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"})
    song = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/aaaaaaaaaaa"},
        headers=_headers("v-1", "Maya"),
    ).json()
    client.post(f"/api/songs/{song['id']}/vote", headers=_headers("v-2", "Dan"))

    response = client.get("/api/songs")  # no Authorization / voter headers
    assert response.status_code == 200
    listing = response.json()
    matching = next(row for row in listing if row["id"] == song["id"])
    assert matching["votes"] == 1
    # Anonymous reader has no voter_id, so did_i_vote is always False.
    assert matching["did_i_vote"] is False
