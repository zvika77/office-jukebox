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

CREATE INDEX IF NOT EXISTS idx_votes_song_id ON votes(song_id);
