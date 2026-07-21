CREATE TABLE IF NOT EXISTS songs (
    id text PRIMARY KEY,
    youtube_id text NOT NULL UNIQUE,
    title text NOT NULL,
    thumbnail_url text NOT NULL,
    duration_seconds integer,
    added_by_name text NOT NULL,
    added_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    song_id text NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    voter_id text NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (song_id, voter_id)
);

CREATE TABLE IF NOT EXISTS quick_adds (
    seq bigint GENERATED ALWAYS AS IDENTITY,
    youtube_id text PRIMARY KEY,
    title text NOT NULL,
    thumbnail_url text NOT NULL,
    decade text
);

CREATE TABLE IF NOT EXISTS settings (
    key text PRIMARY KEY,
    value text
);

-- The "Hall of Fame": songs accumulate love across days. On each reset the day's
-- songs + vote counts are rolled up here (love_score += that day's votes,
-- times_added += 1), so the list organically reflects what the office keeps
-- voting up. Seeded once with a curated starter set at love_score 0 so the
-- section isn't empty on day one, and real votes overtake those placeholders.
CREATE TABLE IF NOT EXISTS favorites (
    youtube_id text PRIMARY KEY,
    title text NOT NULL,
    thumbnail_url text NOT NULL,
    love_score integer NOT NULL DEFAULT 0,
    times_added integer NOT NULL DEFAULT 0,
    last_loved timestamptz
);

CREATE INDEX IF NOT EXISTS idx_votes_song_id ON votes(song_id);

-- Lock the auto-generated Supabase REST API (PostgREST) out of these tables.
-- The app connects directly as the `postgres` owner, which bypasses RLS, so this
-- only blocks the public anon/authenticated roles. With RLS enabled and no
-- policies, those roles get zero access — closing the anon-key REST back door.
ALTER TABLE songs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE votes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE quick_adds ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorites  ENABLE ROW LEVEL SECURITY;
