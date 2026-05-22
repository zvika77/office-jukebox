def test_quick_adds_returns_seeded_rows(client):
    response = client.get("/api/quick-adds")
    assert response.status_code == 200
    data = response.json()
    decades = {row["decade"] for row in data}
    assert decades == {"60s", "70s", "80s", "90s", "2000s", "2010s"}
    assert len(data) >= 30
    row = data[0]
    assert {"youtube_id", "title", "thumbnail_url", "decade"} <= row.keys()
