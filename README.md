# Office Jukebox

LAN-only office jukebox. Coworkers paste YouTube links and upvote from their
phones; one device (hooked to speakers) shows a live leaderboard and plays the
top 4 on demand.

## Quick start

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set ADMIN_TOKEN to a value only you know,
# and set PUBLIC_URL to whatever your coworkers will type/scan
# (e.g. http://my-laptop.local:8000 or http://192.168.1.42:8000)

export $(grep -v '^#' .env | xargs) && \
  uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

## URLs

| Surface | Path | Notes |
|---|---|---|
| Phone view | `/` | What everyone scans from their phone. |
| Jukebox view | `/jukebox` | Open on the laptop hooked to speakers. |
| Jukebox view (admin) | `/jukebox?admin=<token>` | Adds Play / Reset / Skip / Stop buttons. |
| Health check | `/healthz` | |

## Finding the right URL on your network

On macOS / most modern Linux, your hostname is reachable as
`<hostname>.local` (mDNS). Set `PUBLIC_URL` in `.env` to e.g.
`http://my-laptop.local:8000` and that's what the QR code will encode.

If `.local` doesn't work on your network, use your machine's LAN IP
(`ipconfig getifaddr en0` on macOS).

## Manual smoke test

1. Start the server. Open `/jukebox` on the laptop and confirm the QR code
   appears.
2. From a phone on the same WiFi, scan the QR. Confirm the phone view loads
   and the name prompt shows.
3. Pick a name, paste a YouTube link. Confirm the song appears on the
   jukebox screen within ~1s.
4. Tap a decade chip and pick a quick-add. Confirm it appears.
5. Add the same link again. Confirm the "already in the list — upvoted"
   message and that the heart is filled.
6. From a second phone, upvote a song. Confirm the count updates on both
   screens.
7. On the laptop, open `/jukebox?admin=<token>` and click "Play top 4".
   Confirm each video plays in sequence and auto-advances when it ends.
8. Click Skip mid-song. Confirm the next video starts.
9. Click Stop. Confirm return to idle.
10. Click "Reset for tomorrow". Confirm both screens empty out.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `ADMIN_TOKEN` | Required. Shared secret for `/api/play`, `/api/reset`, `/jukebox?admin=…`. |
| `PUBLIC_URL` | The URL the QR code encodes. Defaults to `http://localhost:8000`. |
| `PORT` | Defaults to 8000. |
| `DB_PATH` | SQLite file path. Defaults to `jukebox.db`. |

## Running tests

```sh
.venv/bin/pytest
```

## Portability

The whole app is one FastAPI process + one SQLite file. To move to a
Raspberry Pi or a small cloud box later, copy the project, install the
deps, set `.env`, and run the same `uvicorn` command. No other
infrastructure changes.
