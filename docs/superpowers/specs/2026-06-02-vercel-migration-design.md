# Vercel + Supabase Migration — Design

**Goal:** Move the Office Jukebox off Railway onto Vercel (free Hobby tier) with Supabase Postgres as the database, and add required Google sign-in (restricted to `@nexite.io`) for voters. No existing data is preserved.

**Status:** Approved design, ready for implementation planning.

---

## Locked decisions

| Decision | Choice |
|---|---|
| Backend runtime | **Keep FastAPI**, adapted to Vercel's Python serverless runtime |
| Database | **Supabase Postgres** (via transaction-mode pooler) |
| Voter identity | **Google sign-in required, `@nexite.io` only**, via Supabase Auth |
| Admin + TV auth | **Keep `ADMIN_TOKEN`** (header / `?admin=` query param) — unchanged |
| Live updates | **Polling (~4s)** — SSE removed |
| Data migration | **None** — fresh database, define final schema directly |
| Sequencing | **Two phases** — platform port first, then Google auth |

---

## Target architecture

```
Browser (phone)            Vercel CDN              Vercel Python Function        Supabase
─────────────────          ──────────              ──────────────────────        ────────
Sign in w/ Google  ──────▶ index.html / phone.js                                 Auth (Google,
  (supabase-js)            jukebox.html/jukebox.js                                 nexite.io)
  gets JWT                 styles.css
fetch + Bearer JWT ───────────────────────────────▶ FastAPI /api/*  ──psycopg──▶ Postgres
poll every ~4s                                       verifies JWT,                (songs, votes,
                                                     checks @nexite.io,           quick_adds,
                                                     ADMIN_TOKEN for admin        settings)
```

- **Static assets** (HTML/JS/CSS) served from Vercel's CDN.
- **FastAPI** runs as a single Python serverless function handling `/api/*`, the page routes, and `/api/qrcode.png`.
- **Supabase** provides both Postgres and (Phase 2) Google OAuth.

---

## Phase 1 — Platform port (anonymous identity kept)

**Outcome:** the *exact same app* — anonymous name-prompt identity, voting, deadline, quick-adds, play queue — running on Vercel + Supabase Postgres with polling instead of SSE. Independently shippable.

### 1.1 Database layer (`app/db.py`)
- Replace the `sqlite3` singleton with **psycopg (psycopg3)** connecting per-request to the Supabase **transaction-mode pooler** (`DATABASE_URL`, port `6543`). Transaction mode is required because serverless invocations are short-lived and numerous.
- Translate the schema to Postgres types: `TEXT`→`text`, `TIMESTAMP`→`timestamptz`, `INTEGER`→`integer`. `id TEXT PRIMARY KEY` stays `text` (UUID strings). `ON CONFLICT ... DO UPDATE` syntax is identical.
- **Drop** the SQLite-specific `_migrate()` rebuild logic (no data to preserve). Define the final schema in a checked-in `schema.sql`.
- Schema is applied **once** by running `schema.sql` in the Supabase SQL editor (or a one-shot `scripts/migrate.py`). No DDL runs on cold start.
- `transaction()` and `get_connection()` keep the same call signatures so route code barely changes; only the driver underneath differs.

### 1.2 Realtime → polling
- Remove `/api/events`, the `app/events.py` broker, and every `publish_sync(...)` call in `app/main.py`.
- **Phone (`phone.js`):** keep the existing `setInterval(loadSongs, …)` but tighten to ~4s. Poll `/api/voting-deadline` on the same cadence (reuse the existing endpoint — least change). The 1-second countdown tick stays (local, no network).
- **TV (`jukebox.js`):** remove `setupSSE`; add `setInterval(refresh, 4000)` plus the deadline poll. Local 1s countdown tick stays.

### 1.3 Deployment
- `api/index.py` exports the FastAPI `app` object for Vercel's Python runtime.
- `vercel.json` routes `/api/*`, `/`, `/jukebox`, and `/api/qrcode.png` to the function; serves `/static/*` from the CDN.
- `requirements.txt` updated: add `psycopg[binary]`, remove anything SSE-specific that's now unused.
- **Vercel env vars:** `DATABASE_URL`, `ADMIN_TOKEN`, `YOUTUBE_API_KEY`, `YOUTUBE_PLAYLIST_ID`.
- The QR code endpoint now encodes the Vercel domain.

### 1.4 Tests
- Swap the in-memory SQLite fixture in `tests/conftest.py` for a **Postgres test database** (local Docker Postgres, or Supabase local dev). Fixture creates a fresh schema per test session and truncates between tests.
- All existing logic tests (voting deadline, admin, play order, reset) carry over unchanged in intent.

---

## Phase 2 — Google auth (replace anonymous identity)

**Outcome:** voters must sign in with an `@nexite.io` Google account. Admin and the TV kiosk are unaffected.

### 2.1 Supabase Auth setup (one-time, console)
- Enable the **Google provider** in Supabase Auth.
- Configure the Google OAuth client (client ID/secret) and redirect URLs (the Vercel domain).
- Pass Google's `hd=nexite.io` hint to nudge the account picker; **the real enforcement is server-side** (below).

### 2.2 Backend identity (`app/auth.py`)
- New `require_identity` dependency: read `Authorization: Bearer <jwt>`, verify the Supabase-issued JWT (HS256 via `SUPABASE_JWT_SECRET`, or JWKS), and extract:
  - `voter_id` = JWT `sub` (stable Supabase user id)
  - `display_name` = `user_metadata.name` / `email`
  - `email` — **reject with 401/403 if it does not end in `@nexite.io`**.
- Replaces the current header-trusting `require_identity`. `add_song` / `toggle_vote` / `list_songs` keep using the same `Identity` shape, so route bodies are nearly untouched.

### 2.3 Frontend sign-in (`phone.js` + new `auth.js`)
- Load `supabase-js`; configure with `SUPABASE_URL` + `SUPABASE_ANON_KEY` (anon key is public by design).
- Replace the name-prompt screen with a **"Sign in with Google"** gate. On load, if no session → show sign-in; after sign-in → show the playlist.
- Attach the session JWT as `Authorization: Bearer` on every `fetch`. Drop `X-Voter-Id` / `X-Display-Name`.
- "change name" link is removed (identity now comes from Google).

### 2.4 Env vars added
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` (public, injected into the page), `SUPABASE_JWT_SECRET` (backend only).

### 2.5 Tests
- Override `require_identity` via FastAPI `dependency_overrides` to inject a fake `@nexite.io` user — no real JWT minting needed in unit tests.
- Add a focused test that a non-`nexite.io` email is rejected (mint/stub a token with a foreign domain, assert 403).

---

## Risks & assumptions to validate during implementation

- **Vercel Python cold starts** (~1–3s on first hit) — acceptable for an office tool.
- **psycopg + Supabase pooler:** use transaction mode; avoid server-side prepared statements that don't survive pooled connections (psycopg3 handles this, but verify).
- **Supabase free tier pauses** the DB after ~7 days idle; the first request wakes it (a few seconds). Fine for weekly use; note it to users.
- **supabase-js Google provider** requires a one-time Google Cloud OAuth client + Supabase redirect-URL config.
- **Static vs function routing** on Vercel: confirm the `vercel.json` rewrite order serves `index.html`/`jukebox.html` from CDN while `/api/*` hits the function.

## Out of scope
- Preserving any existing songs/votes (explicitly not needed).
- Migrating admin to Google emails (admin stays on `ADMIN_TOKEN`).
- Supabase Realtime / websockets (polling chosen instead).
- Any UI redesign — the phone and TV layouts stay as they are today.
