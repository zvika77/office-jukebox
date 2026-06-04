# Office Jukebox

Office jukebox for `nexite.io`. Coworkers paste YouTube links and upvote from their phones; one device (hooked to speakers) shows a live leaderboard and plays the top 3 on demand.

Deployed on **Vercel** (Python serverless) backed by **Supabase Postgres**.

## URLs

| Surface | Path | Notes |
|---|---|---|
| Phone view | `/` | What everyone scans from their phone. |
| Jukebox view | `/jukebox` | Open on the laptop hooked to speakers. |
| Jukebox view (admin) | `/jukebox?admin=<token>` | Adds Play / Reset / Skip / Stop / Set deadline buttons. |
| Health check | `/healthz` | |

## Deployment (Vercel)

1. **Create a Supabase project** (free tier). From Dashboard → Connect, copy:
   - **Session pooler URI** (port `5432`) — for local dev / tests
   - **Transaction pooler URI** (port `6543`) — for `DATABASE_URL` on Vercel

2. **Apply the schema** (run once against Supabase):
   ```sh
   DATABASE_URL=<session-pooler-uri> python scripts/init_db.py
   ```
   This creates the tables and seeds the curated quick-add list. Idempotent — safe to re-run.

3. **Set Vercel environment variables** (Dashboard → Project → Settings → Environment Variables):
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Supabase **transaction pooler** URI (port `6543`) |
   | `ADMIN_TOKEN` | A secret only you know |
   | `PUBLIC_URL` | The deployed Vercel URL (e.g. `https://office-jukebox.vercel.app`) |
   | `YOUTUBE_API_KEY` | YouTube Data API v3 key (enables "Refresh suggestions") |
   | `YOUTUBE_PLAYLIST_ID` | Optional — playlist source for quick-adds |

4. **Deploy:** Push to the Vercel-connected branch (or run `vercel --prod`).

## Local development

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set DATABASE_URL, ADMIN_TOKEN, etc.

source .env && uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
```

For local dev you can point `DATABASE_URL` at your Supabase session pooler, or run a local Postgres:

```sh
docker run -d --name jukebox-dev -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres python scripts/init_db.py
```

## Running tests

The test suite connects to a real Postgres database. Point `TEST_DATABASE_URL` at a test database (not your production database — tests truncate all tables on every run).

```sh
# Option A: local Docker Postgres (recommended for isolation)
docker run -d --name jukebox-test -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=jukebox_test -p 5432:5432 postgres:16

# Option B: Supabase (works fine since there's no data to preserve)
# Add TEST_DATABASE_URL=<session-pooler-uri> to .env

.venv/bin/pytest
```

DB-dependent tests skip gracefully when `TEST_DATABASE_URL` is unreachable. Pure unit tests (YouTube URL parser, identity, admin token) always run.

## Known behaviour

- **Supabase free tier pauses** the database after ~7 days of inactivity. The first request wakes it (a few seconds delay). Normal for weekly use.
- **Vercel cold starts** add ~1–3s to the first request after a long idle period. Acceptable for an office tool.
- Voting updates propagate via ~4s polling on both the phone and TV views.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | **Required.** Supabase transaction pooler URI (port `6543`) or any Postgres URI. |
| `ADMIN_TOKEN` | **Required.** Shared secret for admin endpoints and the jukebox admin view. |
| `PUBLIC_URL` | The URL the QR code encodes. Defaults to the detected LAN IP. |
| `PORT` | HTTP port for local dev. Defaults to 8000. |
| `YOUTUBE_API_KEY` | Enables `POST /api/quick-adds/refresh` and the "Refresh suggestions" button. |
| `YOUTUBE_PLAYLIST_ID` | Playlist to pull quick-adds from. If unset, falls back to curated decade search. |
| `TEST_DATABASE_URL` | Postgres URI for the test suite. Defaults to `postgresql://postgres:postgres@localhost:5432/jukebox_test`. |

## Authentication (Google sign-in)

Voters sign in with a Google `@nexite.io` account via Supabase Auth. Admin and
the TV kiosk are unaffected (they use `ADMIN_TOKEN` / no login). Reads are public;
all writes require a verified `@nexite.io` token.

### Environment variables

| Var | Where | Purpose |
|-----|-------|---------|
| `SUPABASE_URL` | Vercel | Supabase project URL — used for JWKS verification and exposed to the frontend via `/api/config`. |
| `SUPABASE_ANON_KEY` | Vercel | Public anon key — exposed to the frontend via `/api/config`. |
| `ALLOWED_EMAIL_DOMAIN` | Vercel (optional) | Allowed email domain. Defaults to `nexite.io`. |

There is **no** `SUPABASE_JWT_SECRET` — tokens are verified asymmetrically against
Supabase's published public keys (ES256 via the JWKS endpoint).

### One-time setup

**Google Cloud Console:**
1. Create an OAuth 2.0 Client ID (type: Web application).
2. Authorized redirect URI: `https://<project>.supabase.co/auth/v1/callback`.
3. Copy the Client ID and Client Secret.

**Supabase Console:**
1. Authentication → Providers → Google: enable, paste the Client ID + Secret.
2. Authentication → URL Configuration → Site URL: `https://office-jukebox.vercel.app`.

**Vercel:** add `SUPABASE_URL` and `SUPABASE_ANON_KEY` (and optionally
`ALLOWED_EMAIL_DOMAIN`) to the project's environment variables, then redeploy.
