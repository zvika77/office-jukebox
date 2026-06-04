def test_config_exposes_supabase_public_values(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-public-key")
    body = client.get("/api/config").json()
    assert body == {
        "supabase_url": "https://proj.supabase.co",
        "supabase_anon_key": "anon-public-key",
    }


def test_config_defaults_to_empty_strings_when_unset(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    body = client.get("/api/config").json()
    assert body == {"supabase_url": "", "supabase_anon_key": ""}
