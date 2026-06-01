def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def _add(client, httpx_mock, vid: str):
    httpx_mock.add_response(json={"title": vid, "thumbnail_url": "x"})
    return client.post(
        "/api/songs",
        json={"youtube_url": f"https://youtu.be/{vid}"},
        headers=_headers(),
    ).json()["id"]


def test_play_returns_top3_in_vote_order(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    vids = [f"vid{i:08d}aa"[:11] for i in range(5)]
    ids = [_add(client, httpx_mock, v) for v in vids]
    # Give them descending votes: ids[0]=4, [1]=3, [2]=2, [3]=1, [4]=0
    for i, sid in enumerate(ids):
        for v in range(4 - i):
            client.post(
                f"/api/songs/{sid}/vote",
                headers={"X-Voter-Id": f"voter-{i}-{v}", "X-Display-Name": "X"},
            )

    response = client.post("/api/play", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["queue"]] == ids[:3]
    assert body["queue"][0]["youtube_id"]


def test_play_requires_admin(client):
    response = client.post("/api/play")
    assert response.status_code in (403, 500)


def test_play_empty_returns_empty_queue(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    response = client.post("/api/play", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert response.json() == {"queue": []}


def test_reset_wipes_songs_and_votes(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    sid = _add(client, httpx_mock, "vid00000000")
    client.post(
        f"/api/songs/{sid}/vote",
        headers={"X-Voter-Id": "v-x", "X-Display-Name": "X"},
    )

    response = client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert response.json() == {"deleted_songs": 1, "deleted_votes": 1}

    listing = client.get("/api/songs", headers=_headers()).json()
    assert listing == []


def test_reset_requires_admin(client):
    response = client.post("/api/reset")
    assert response.status_code in (403, 500)
