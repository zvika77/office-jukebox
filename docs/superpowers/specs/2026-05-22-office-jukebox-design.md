# Office Jukebox — Design

**Date:** 2026-05-22
**Status:** Approved (pending implementation plan)

## Summary

A LAN-only web app that turns a shared office speaker setup into a vote-driven
"jukebox." Coworkers connect from their phones over the office WiFi, paste
YouTube links (or tap pre-seeded quick-add songs), and upvote each other's
submissions. One device — connected to the office speakers — runs the server
and displays a live leaderboard. When the host decides, they press a button
and the top 4 songs play in order via an embedded YouTube player.

## Goals

- Zero-friction submission and voting on a trusted office LAN.
- Live, social leaderboard visible to the room.
- Host-controlled play moment ("press play when it's time").
- Manual day reset, so the host stays in control of the cycle.
- Portable enough to later move from a laptop to a Raspberry Pi or hosted box.

## Non-goals (v1)

- Authentication or accounts (display name + browser-stored id is enough).
- Anti-abuse for hostile actors (LAN = trusted).
- Persistent history across days (manual reset wipes everything for now).
- Native mobile apps; browser only.
- Integration with the real YouTube Music service.

## Decisions

| Topic | Choice |
|---|---|
| Music source | Embedded YouTube videos via the IFrame Player API |
| Playback model | One central "jukebox" device hooked to speakers; phones for everyone else |
| Identity | Pick a display name on first visit; stored in browser |
| Voting | Upvote only, toggleable, one per song per browser |
| Daily cycle | Host manually clicks "Play top 4", then manually clicks "Reset for tomorrow" |
| Search | Paste YouTube link + curated decade-spanning quick-add chips |
| Hosting | User's laptop initially; designed to be portable |
| Stack | Python 3 + FastAPI + SQLite + plain HTML/JS |
| Realtime | Server-Sent Events (with a 10s polling fallback) |
| Jukebox screen | Live leaderboard (top-4 podium + rest of submissions), QR code + URL in a corner |

## Architecture

A single FastAPI process serves three surfaces, backed by one SQLite file.

```
                ┌───────────────────────────────────┐
                │       FastAPI server (laptop)     │
                │   ┌──────────────┐  ┌──────────┐  │
   phones  ───►│   │  REST + SSE  │──│ SQLite   │  │
   (browsers)  │   └──────────────┘  │ (file)   │  │
                │           ▲         └──────────┘  │
                │           │                       │
                │   ┌──────────────┐                │
                │   │ static HTML/JS│               │
                │   │  + YT IFrame  │               │
                │   └──────────────┘                │
                └──────────────────▲────────────────┘
                                   │
                            jukebox browser
                            (fullscreen on
                             same laptop)
```

### Surfaces

- **Phone view (`/`)** — coworkers' phones/laptops. Name prompt, paste/quick-add,
  live leaderboard, upvote button.
- **Jukebox view (`/jukebox`)** — fullscreen on the device hooked to the speakers.
  Big QR + URL, live top-4 podium, scrolling rest-of-list. "Play top 4" and
  "Reset" buttons appear only when an `?admin=…` query param matches the
  server's admin token. When a play session starts, the YouTube IFrame player
  fills the screen.
- **REST + SSE API** — small surface; phones and jukebox both use it.

### Realtime updates

A single `GET /api/events` Server-Sent Events stream pushes a tiny
`songs_changed` event after every add / vote / reset. Clients respond by
re-fetching `/api/songs`. SSE is one line of code in FastAPI, works through a
plain `<script>` tag with `EventSource`, and reconnects automatically on drop.
Phones additionally poll `/api/songs` every 10s as a belt-and-suspenders
fallback.

## Data model

Three SQLite tables.

**`songs`** — submissions for the current day.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT (uuid) | primary key |
| `youtube_id` | TEXT | 11-char video id, extracted from the pasted URL |
| `title` | TEXT | from YouTube oEmbed |
| `thumbnail_url` | TEXT | from YouTube oEmbed |
| `duration_seconds` | INTEGER NULL | from YouTube oEmbed when available |
| `added_by_name` | TEXT | display name from browser cookie |
| `added_at` | TIMESTAMP | server time |

Unique index on `youtube_id` so the same video can't appear twice in one day —
a re-add becomes an upvote instead.

**`votes`** — one row per (song, voter) upvote.

| Column | Type | Notes |
|---|---|---|
| `song_id` | TEXT | FK → `songs.id`, ON DELETE CASCADE |
| `voter_id` | TEXT | uuid stored in caller's browser localStorage |
| `created_at` | TIMESTAMP | |

Unique index on `(song_id, voter_id)` — second vote from the same browser is a
no-op (or a toggle-off, depending on endpoint semantics).

**`quick_adds`** — curated seed list, editable later.

| Column | Type | Notes |
|---|---|---|
| `youtube_id` | TEXT | primary key |
| `title` | TEXT | |
| `thumbnail_url` | TEXT | |
| `decade` | TEXT | "60s", "70s", "80s", "90s", "2000s", "2010s" |

Shipped pre-populated with ~5 songs per decade (60s through 2010s).

### Identity

Two values stored in the caller's browser `localStorage`, sent on every
request as custom headers (`X-Voter-Id`, `X-Display-Name`):

- `voter_id` — random uuid, generated on first visit; used solely for vote
  uniqueness. Persists even if the user changes their display name.
- `display_name` — what the user typed in the name prompt. Editable later
  from a settings menu. Used purely for display (e.g., "added by Maya").

Duplicate display names across coworkers are allowed; uniqueness is by
`voter_id`.

## API

All JSON. All authenticated only when noted.

### Reads

| Method + Path | Description |
|---|---|
| `GET /api/songs` | Today's submissions, sorted by `votes DESC, added_at ASC`. Each row includes `did_i_vote` based on caller's `voter_id`. |
| `GET /api/quick-adds` | Curated decade list for the phone UI's chips. |
| `GET /api/events` | SSE stream. Emits `songs_changed` after add/vote/reset. |

### Writes

| Method + Path | Description |
|---|---|
| `POST /api/songs` | Body: `{ youtube_url }`. Caller identity (`voter_id`, `display_name`) comes from request headers. Extracts video id, fetches title/thumbnail via YouTube oEmbed, inserts row. If `youtube_id` already exists today, upvotes the existing one for the caller instead and returns a friendly "already in the list — upvoted" message. |
| `POST /api/songs/{id}/vote` | Toggles the caller's vote (based on the `X-Voter-Id` header). Idempotent in effect. |
| `POST /api/play` | Admin-only. Returns the top-4 song ids in order. The jukebox view uses this to seed the IFrame player. |
| `POST /api/reset` | Admin-only. Wipes `songs` and `votes`. Confirmation handled in the UI. |

### Admin auth

A single shared admin token, stored in a `.env` file on the server. The host
opens the jukebox view as `/jukebox?admin=<token>`. The page stores the token
in `sessionStorage` and includes it in `POST /api/play` and `POST /api/reset`
calls. Phones never receive or send it.

## UI flows

### Phone view

1. **First visit** — modal prompts for display name; stored in browser.
2. **Header** — single text input "Paste a YouTube link" + submit button.
3. **Quick-add row** — horizontal scrollable chips: 60s, 70s, 80s, 90s, 2000s,
   2010s. Tapping a decade reveals ~5 song cards with thumbnails for one-tap add.
4. **Today's list** — sorted by votes desc. Each row: thumbnail, title,
   "added by <name>", vote count, heart/upvote button. Top 4 rows have a subtle
   "🏆 in the top 4" highlight. Tapping the heart toggles the vote.

### Jukebox view (idle)

- Header: "🎵 Office Jukebox" + QR code + the human-readable URL
  (`http://<laptop-hostname>.local:<port>`).
- Middle: top-4 podium — large thumbnails, vote counts, "added by" line.
  Updates live as people vote.
- Bottom: scrolling list of remaining submissions with vote counts.
- Floating "▶ Play top 4" button — visible only with valid `?admin=…`.

### Jukebox view (playing)

- YouTube IFrame player goes fullscreen, with title overlay.
- IFrame API's `onStateChange` listens for `ENDED` → auto-advances to next of 4.
- Small admin-only "⏭ Skip" and "■ Stop" controls.
- IFrame API's `onError` (e.g., embed-blocked video) → skip to next + show a
  small "⚠️ couldn't play that one" toast for ~3s.
- After the 4th song ends (or stop is pressed), returns to idle state.

### Reset flow

- Admin clicks "Reset for tomorrow" on jukebox view → confirmation dialog →
  `POST /api/reset` → both tables wiped → SSE event flushes all clients.

## Error handling & edge cases

- **Unparseable YouTube link** — server tries common shapes
  (`youtube.com/watch?v=…`, `youtu.be/…`, `music.youtube.com/watch?v=…`, with
  extra query params or timestamps). On failure, returns 400 with a friendly
  message that the phone displays inline.
- **YouTube oEmbed unreachable** — fallback to `title = "Unknown title"` and a
  default thumbnail; song is still added.
- **Duplicate submission** — server upvotes the existing row for the caller
  and returns a "already in the list — upvoted for you" message.
- **Empty playlist at play time** — button disabled with 0 songs; with 1–3
  songs, plays whatever's there.
- **Embed-blocked video** — IFrame `onError` triggers; jukebox skips +
  shows toast.
- **SSE drops** — `EventSource` auto-reconnects; phones also poll every 10s.
- **Concurrent votes** — handled by the unique index; conflicting inserts
  become no-ops.
- **Display-name collisions** — allowed; voter uniqueness is by `voter_id`.

## Testing strategy

Proportional to a v1 LAN app — focus on logic that's easy to get wrong, skip
heavyweight browser E2E.

**Unit tests (pytest):**
- YouTube URL → video id extraction across all known URL shapes.
- Add-song flow including the "already exists → upvote" branch.
- Vote toggle: add, double-vote no-op, un-vote.
- Top-4 selection order, tie-break by `added_at` ascending.
- Reset wipes both tables.
- Admin token check on `/api/play` and `/api/reset`.

**Integration tests (FastAPI `TestClient` + in-memory SQLite):**
- End-to-end: add → vote from two different `voter_id`s → list → confirm
  ordering and counts.
- SSE stream emits `songs_changed` after add/vote/reset.

**Manual smoke test** (documented in README):
1. Start server, open jukebox view on the laptop, open phone view on a phone —
   confirm QR works.
2. Add 5 songs from the phone, upvote a few.
3. Confirm leaderboard updates within ~1s on the jukebox.
4. Hit "Play top 4", confirm auto-advance through all four.
5. Hit "Reset for tomorrow", confirm everything clears.

No frontend unit tests in v1 — the JS is thin enough that manual smoke covers
it. Playwright can be added later if the frontend grows.

## Portability

- **Single FastAPI process + SQLite file** — moves to a Raspberry Pi or hosted
  box with no architectural changes; only the `.env` and the way the URL is
  surfaced (mDNS hostname vs. public domain) change.
- **No build step** — plain HTML/JS served as static files. `pip install` +
  `uvicorn main:app` is the whole launch story.
- **Config via `.env`** — admin token, port, public URL hint (used for QR
  generation) all live there.

## Open questions for the plan stage

- Exact list of seed quick-add songs per decade (can be filled in during
  implementation; the schema doesn't depend on it).
- Whether to surface the local hostname as `<hostname>.local` (mDNS, works on
  Apple and most modern OSes) vs. raw IP. Both are easy; we'll pick during
  implementation based on what the laptop OS makes painless.
