# Phase 2 — Google Sign-In (`@nexite.io`) — Design

**Goal:** Require voters to sign in with a Google `@nexite.io` account before they can add songs or vote. Admin and the TV kiosk are unaffected. Reads stay public.

**Status:** Approved design, ready for implementation planning.

**Supersedes:** the Phase 2 section of `2026-06-02-vercel-migration-design.md`. That section assumed a symmetric `SUPABASE_JWT_SECRET`; this design uses **asymmetric JWKS verification** instead (no shared secret), and makes `GET /api/songs` **public with optional auth**.

---

## Locked decisions

| Decision | Choice |
|---|---|
| Voter identity | Google sign-in via Supabase Auth, **`@nexite.io` only** |
| Admin + TV auth | Keep `ADMIN_TOKEN` — unchanged |
| TV leaderboard read | **Public, optional auth** — TV reads with no login; phone personalizes when signed in |
| JWT verification | **Asymmetric via JWKS** (ES256, Supabase published public key — no shared secret in env) |
| Realtime | Polling (~4s) — unchanged from Phase 1 |

---

## Section 1 — Auth model & scope

**Who authenticates how:**

| Actor | Auth mechanism | Changes? |
|---|---|---|
| Voter (phone) | Google sign-in via Supabase Auth, `@nexite.io` only | NEW — replaces name prompt |
| Admin | `ADMIN_TOKEN` (`?admin=` / header) | unchanged |
| TV kiosk | none (anonymous reads) | unchanged |

**Endpoint auth after Phase 2:**

| Endpoint | Before | After |
|---|---|---|
| `POST /api/songs` (add) | header identity | **Google JWT required** |
| `POST /api/songs/{id}/vote` | header identity | **Google JWT required** |
| `GET /api/songs` | header identity | **public, optional JWT** (personalizes `did_i_vote` when present) |
| `POST /api/play` | admin | unchanged |
| `POST /api/reset` | admin | unchanged |
| `POST /api/voting-deadline` | admin | unchanged |
| `GET /api/quick-adds` | public | unchanged |
| `GET /api/voting-deadline` | public | unchanged |
| `GET /api/config` | — | **NEW, public** (exposes Supabase URL + anon key) |
| `/`, `/jukebox`, `/healthz`, `/api/qrcode.png` | public | unchanged |

The key shift: **all writes require a verified `@nexite.io` Google token; reads stay open.** The TV keeps working with no login, and the phone leaderboard renders for anyone but only shows "you voted" hearts once you're signed in.

---

## Section 2 — Backend

**New file `app/auth.py`** replaces `app/identity.py`'s trust-the-header logic with real JWT verification.

Per-request verify flow:

```
1. read Authorization: Bearer <jwt>
2. fetch Supabase public keys from JWKS endpoint (cached in-process)
3. verify signature (ES256) + claims: aud="authenticated", iss, exp
4. extract sub → voter_id, email, user_metadata.name → display_name
5. enforce email endswith @<ALLOWED_EMAIL_DOMAIN>  → else 403
```

Three pieces, separated so the logic is testable without minting real tokens:

- **`identity_from_claims(claims) -> Identity`** — pure function. Takes a decoded JWT payload, applies the domain rule, builds the `Identity`. No network, no FastAPI. The domain check lives here; most unit tests point here.
- **`require_identity`** — FastAPI dependency for **writes**. Missing / invalid / foreign-domain token → 401/403.
- **`optional_identity`** — FastAPI dependency for **`GET /api/songs`**. Returns `Identity | None`: no token → `None` (anonymous read); invalid/expired token → also `None` (don't break the TV over a stale token).

**JWKS handling:** fetch public keys from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` via PyJWT's `PyJWKClient`, which caches keys in-process so we don't refetch every request. No shared secret in env — verification uses Supabase's published public key.

**`Identity` shape is unchanged** (`voter_id`, `display_name`), so `add_song`, `toggle_vote`, and `list_songs` bodies barely change. `list_songs` switches to `optional_identity` and handles `identity is None` by skipping the `did_i_vote` personalization (treat as not-voted).

**New `GET /api/config`** returns `{ "supabase_url": ..., "supabase_anon_key": ... }` so the static frontend can boot supabase-js without hardcoded values. The anon key is public by design.

**Dependency:** add `PyJWT[crypto]` to `requirements.txt` (the `[crypto]` extra provides ES256 verification).

**`app/identity.py`** is removed (its `require_identity` is replaced by `app/auth.py`).

---

## Section 3 — Frontend

**New file `app/static/auth.js`** — thin wrapper around supabase-js (loaded via CDN `<script>`).

```
initAuth()    → fetch /api/config, create supabase client, restore session
signIn()      → supabase.auth.signInWithOAuth({
                   provider: 'google',
                   options: { queryParams: { hd: 'nexite.io' } }
                })
signOut()     → supabase.auth.signOut()
getToken()    → current session's access_token (or null)
currentUser() → { name, email } or null
```

The `hd=nexite.io` hint nudges Google's account picker toward work accounts — but it's only a hint; the real enforcement is the server-side `@nexite.io` check in Section 2.

**`phone.js` changes:**
- On load: `initAuth()`. If no session → show a **"Sign in with Google"** gate instead of the playlist. After the OAuth redirect returns → show the playlist.
- Every write `fetch` (add, vote) attaches `Authorization: Bearer <getToken()>`. Drop `X-Voter-Id` / `X-Display-Name`.
- Reads (`GET /api/songs`) attach the Bearer token **when signed in** so hearts personalize; they work fine without it.
- Header shows **"You are \<name\> · Sign out"** replacing the old "change name" link.

**`jukebox.js` (TV):** no auth change needed — it already reads `/api/songs` without real identity and keeps polling anonymously. The now-meaningless `X-Voter-Id: jukebox-screen` header is dropped (cosmetic, since reads are public).

**OAuth redirect:** Supabase handles the Google round-trip and returns to the app with the session in the URL hash; supabase-js picks it up automatically on `initAuth()`. No extra callback page needed.

---

## Section 4 — One-time setup & env vars

**Google Cloud Console (one-time):**
- Create an OAuth 2.0 Client ID (type: Web application).
- Authorized redirect URI: `{SUPABASE_URL}/auth/v1/callback`.
- Copy the Client ID + Client Secret.

**Supabase Console (one-time):**
- Auth → Providers → Google: enable, paste Client ID + Secret.
- Auth → URL Configuration: Site URL = `https://office-jukebox.vercel.app` (so the post-login redirect lands back on the app).

**Vercel env vars (added):**

| Var | Value | Used by |
|---|---|---|
| `SUPABASE_URL` | `https://<project>.supabase.co` | backend (JWKS) + frontend (via `/api/config`) |
| `SUPABASE_ANON_KEY` | the public anon key | frontend (via `/api/config`) |
| `ALLOWED_EMAIL_DOMAIN` | `nexite.io` (default if unset) | backend domain check |

**No `SUPABASE_JWT_SECRET`** — the asymmetric/JWKS path uses Supabase's published public key, so there is no shared secret to store. This is the main payoff of the asymmetric decision: one less secret in env.

---

## Section 5 — Testing

**Unit tests (no network, no real tokens) — point at `identity_from_claims()`:**
- valid `@nexite.io` claims → correct `Identity` (`voter_id` from `sub`, `display_name` from name/email).
- foreign domain (e.g. `someone@gmail.com`) → raises 403.
- missing email / missing sub → rejected.
- case-insensitivity (`Someone@Nexite.IO` still passes).

**Endpoint tests (FastAPI `dependency_overrides`):**
- Override `require_identity` / `optional_identity` to inject a fake `@nexite.io` user — existing add/vote/list tests carry over with the new dependency, no JWT minting needed.
- One test overrides `optional_identity` to return `None` and asserts `GET /api/songs` still returns the leaderboard (TV path) with `did_i_vote` absent/false.

**One real-crypto test for the domain gate:**
- Generate an ES256 keypair in-test, mint a token with a foreign-domain email, point the verifier at the test public key, assert **403**. Proves the end-to-end verify+reject path, not just the pure function.

**Existing Phase 1 tests** (voting deadline, admin, play order, reset) are unaffected — they don't touch identity.

---

## Out of scope
- Preserving any existing songs/votes.
- Migrating admin to Google emails (admin stays on `ADMIN_TOKEN`).
- Supabase Realtime / websockets (polling kept from Phase 1).
- Any UI redesign beyond the sign-in gate and the "You are \<name\> · Sign out" header.

## Risks & assumptions
- **supabase-js Google provider** requires the one-time Google Cloud OAuth client + Supabase redirect-URL config (Section 4).
- **JWKS endpoint shape:** assumes Supabase serves ES256 public keys at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Verify the algorithm and `aud`/`iss` claim values against a real token during implementation.
- **Optional-auth reads must never 500 on a bad token** — `optional_identity` swallows verification errors and returns `None`, so a stale phone token can't break the TV.
