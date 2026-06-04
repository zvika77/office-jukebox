# Google Sign-In (`@nexite.io`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require voters to sign in with a Google `@nexite.io` account before adding songs or voting; admin and the TV kiosk are unchanged; reads stay public.

**Architecture:** A new `app/auth.py` verifies Supabase-issued JWTs asymmetrically (ES256 via the Supabase JWKS endpoint — no shared secret), enforces the `@nexite.io` domain, and exposes `require_identity` (writes) + `optional_identity` (reads). The frontend gains `auth.js` (supabase-js) with a "Sign in with Google" gate; the phone attaches `Authorization: Bearer <jwt>` to writes. The `Identity` shape (`voter_id`, `display_name`) is unchanged so route bodies barely move.

**Tech Stack:** FastAPI (Vercel Python serverless), psycopg3 + Supabase Postgres, PyJWT[crypto] (ES256 + PyJWKClient), supabase-js v2 (CDN), pytest + pytest-httpx.

**Spec:** `docs/superpowers/specs/2026-06-03-google-auth-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `app/auth.py` | JWT verify, domain enforcement, `Identity`, `identity_from_claims`, `require_identity`, `optional_identity` | Create |
| `app/identity.py` | old header-trust identity | Delete |
| `app/main.py` | route wiring: writes→`require_identity`, `GET /api/songs`→`optional_identity`, new `GET /api/config` | Modify |
| `requirements.txt` | add `PyJWT[crypto]` | Modify |
| `tests/conftest.py` | `dependency_overrides` shim so header-based endpoint tests stay green | Modify |
| `tests/test_auth.py` | pure-function + ES256 keypair verification tests | Create |
| `tests/test_identity.py` | tests for deleted module | Delete |
| `tests/test_config_api.py` | `GET /api/config` test | Create |
| `app/static/auth.js` | supabase-js wrapper: init/signIn/signOut/getToken/currentUser | Create |
| `app/static/index.html` | sign-in gate markup + supabase-js + auth.js script tags | Modify |
| `app/static/phone.js` | boot gate, Bearer headers, sign-out (drop name prompt/rename) | Modify |
| `app/static/jukebox.js` | drop stale `X-Voter-Id` header on the public read | Modify |
| `README.md` | env vars + one-time Google/Supabase setup checklist | Modify |

---

## Task 1: Auth module — `Identity` + `identity_from_claims` (pure)

Establish the dependency and the pure, network-free core of the domain check. Nothing is wired into routes yet — the app still uses `app/identity.py`, so the full suite stays green.

**Files:**
- Modify: `requirements.txt`
- Create: `app/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Add the PyJWT dependency**

Edit `requirements.txt` — add this line after the `psycopg[binary]>=3.1` line:

```
PyJWT[crypto]>=2.8
```

- [ ] **Step 2: Install it**

Run: `pip install 'PyJWT[crypto]>=2.8'`
Expected: installs `PyJWT` and `cryptography` (or reports already satisfied).

- [ ] **Step 3: Write the failing tests for `identity_from_claims`**

Create `tests/test_auth.py`:

```python
import pytest
from fastapi import HTTPException

from app.auth import Identity, identity_from_claims


def _claims(**over) -> dict:
    base = {
        "sub": "user-abc",
        "email": "maya@nexite.io",
        "user_metadata": {"name": "Maya"},
    }
    base.update(over)
    return base


def test_identity_from_valid_nexite_claims():
    ident = identity_from_claims(_claims(), "nexite.io")
    assert ident == Identity(voter_id="user-abc", display_name="Maya")


def test_display_name_falls_back_to_email_when_no_name():
    ident = identity_from_claims(
        _claims(user_metadata={}), "nexite.io"
    )
    assert ident.display_name == "maya@nexite.io"


def test_foreign_domain_is_rejected_403():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(email="someone@gmail.com"), "nexite.io")
    assert exc.value.status_code == 403


def test_missing_email_is_rejected_403():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(email=None), "nexite.io")
    assert exc.value.status_code == 403


def test_missing_sub_is_rejected_401():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(sub=None), "nexite.io")
    assert exc.value.status_code == 401


def test_domain_check_is_case_insensitive():
    ident = identity_from_claims(_claims(email="Maya@Nexite.IO"), "nexite.io")
    assert ident.voter_id == "user-abc"
    assert ident.display_name == "Maya"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'` (or import error for `identity_from_claims`).

- [ ] **Step 5: Create `app/auth.py` with the pure core**

Create `app/auth.py`:

```python
"""Google sign-in identity for voters.

Voters authenticate with Supabase Auth (Google provider, @nexite.io only).
Every request carrying `Authorization: Bearer <jwt>` is verified against
Supabase's published public keys (ES256, fetched from the JWKS endpoint) —
there is no shared secret to store. The domain rule is enforced server-side:
the Google `hd` hint on the frontend is only a nudge, not a guarantee.

`identity_from_claims` is a pure function (no network, no FastAPI) so the
domain logic is unit-testable without minting real tokens.
"""

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Identity:
    voter_id: str
    display_name: str


def _allowed_domain() -> str:
    return os.environ.get("ALLOWED_EMAIL_DOMAIN", "nexite.io")


def identity_from_claims(claims: dict, allowed_domain: str) -> Identity:
    """Build an Identity from decoded JWT claims, enforcing the email domain.

    Raises HTTPException(403) for a missing/foreign-domain email and
    HTTPException(401) when the subject (`sub`) is absent.
    """
    email_raw = (claims.get("email") or "").strip()
    email = email_raw.lower()
    domain = "@" + allowed_domain.lower().lstrip("@")
    if not email or not email.endswith(domain):
        raise HTTPException(status_code=403, detail="sign in with a nexite.io account")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token has no subject")

    meta = claims.get("user_metadata") or {}
    name = (meta.get("name") or meta.get("full_name") or email_raw).strip()
    return Identity(voter_id=str(sub), display_name=name[:80])
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/auth.py tests/test_auth.py
git commit -m "feat: add auth module with pure identity_from_claims domain check"
```

---

## Task 2: JWKS verification + `require_identity` / `optional_identity`

Add the real token-verification path and the two FastAPI dependencies. A test seam (`_signing_key_for`) lets the test mint an ES256 token and verify it end-to-end without hitting Supabase.

**Files:**
- Modify: `app/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Write the failing dependency tests**

Append to `tests/test_auth.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.auth as auth_module
from app.auth import optional_identity, require_identity


@pytest.fixture
def es256_keys():
    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, priv.public_key()


def _mint(priv, **over) -> str:
    payload = {
        "sub": "user-abc",
        "email": "maya@nexite.io",
        "user_metadata": {"name": "Maya"},
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    payload.update(over)
    return jwt.encode(payload, priv, algorithm="ES256")


def _verify_app() -> FastAPI:
    api = FastAPI()

    @api.get("/required")
    def required(identity: Identity = Depends(require_identity)) -> dict:
        return {"voter_id": identity.voter_id, "display_name": identity.display_name}

    @api.get("/optional")
    def optional(identity: Identity | None = Depends(optional_identity)) -> dict:
        return {"signed_in": identity is not None}

    return api


def test_required_accepts_valid_nexite_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    resp = client.get("/required", headers={"Authorization": f"Bearer {_mint(priv)}"})
    assert resp.status_code == 200
    assert resp.json() == {"voter_id": "user-abc", "display_name": "Maya"}


def test_required_rejects_foreign_domain_403(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(priv, email="someone@gmail.com")
    resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_required_without_token_is_401():
    client = TestClient(_verify_app())
    assert client.get("/required").status_code == 401


def test_required_with_bad_signature_is_401(monkeypatch, es256_keys):
    priv, pub = es256_keys
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(other)  # signed with a key the verifier won't accept
    resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_optional_returns_signed_out_without_token():
    client = TestClient(_verify_app())
    resp = client.get("/optional")
    assert resp.status_code == 200
    assert resp.json() == {"signed_in": False}


def test_optional_swallows_bad_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(other)  # invalid signature must not 500 the read path
    resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"signed_in": False}


def test_optional_personalizes_with_valid_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    resp = client.get("/optional", headers={"Authorization": f"Bearer {_mint(priv)}"})
    assert resp.json() == {"signed_in": True}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_auth.py -k "required or optional" -v`
Expected: FAIL — `ImportError: cannot import name 'require_identity'` / `'optional_identity'`.

- [ ] **Step 3: Add the verification path and dependencies to `app/auth.py`**

First restore the `Header` import the dependencies need — change the existing fastapi import line from `from fastapi import HTTPException` to:

```python
from fastapi import Header, HTTPException
```

Then add these imports at the top of `app/auth.py` (below that fastapi import line):

```python
from functools import lru_cache

import jwt
from jwt import PyJWKClient
```

Then append to `app/auth.py`:

```python
def _jwks_url() -> str:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    # PyJWKClient caches fetched keys in-process, so cold starts pay one fetch.
    return PyJWKClient(_jwks_url())


def _signing_key_for(token: str):
    """Return the public key that signed `token` (test seam — monkeypatched in tests)."""
    return _jwk_client().get_signing_key_from_jwt(token).key


def _decode(token: str) -> dict:
    key = _signing_key_for(token)
    return jwt.decode(
        token,
        key,
        algorithms=["ES256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]},
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_identity(authorization: str | None = Header(default=None)) -> Identity:
    """Verified @nexite.io identity for write endpoints. 401/403 when absent or foreign."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="sign in required")
    try:
        claims = _decode(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return identity_from_claims(claims, _allowed_domain())


def optional_identity(authorization: str | None = Header(default=None)) -> Identity | None:
    """Identity for public reads. None when no/invalid token — never raises, so a
    stale phone token can't break the anonymous TV read path."""
    token = _bearer_token(authorization)
    if not token:
        return None
    try:
        claims = _decode(token)
        return identity_from_claims(claims, _allowed_domain())
    except (jwt.PyJWTError, HTTPException):
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS — all 13 tests (6 from Task 1 + 7 here).

- [ ] **Step 5: Commit**

```bash
git add app/auth.py tests/test_auth.py
git commit -m "feat: verify Supabase JWTs via JWKS with require/optional identity deps"
```

---

## Task 3: Wire auth into routes + delete the old identity module

Switch `app/main.py` to the new dependencies and add the conftest shim in the same commit so the header-based endpoint tests keep passing. Then delete `app/identity.py` and its test.

**Files:**
- Modify: `app/main.py` (imports line 13; `add_song` 169-173; `list_songs` 221-222 + 229,235; `toggle_vote` 252-256)
- Modify: `tests/conftest.py`
- Delete: `app/identity.py`
- Delete: `tests/test_identity.py`

- [ ] **Step 1: Add the conftest dependency-override shim**

In `tests/conftest.py`, change the app-import line (currently line 18):

```python
from app.main import app, seed_quick_adds  # noqa: E402
```

to also import the new deps and Header/HTTPException, and register overrides. Replace lines 1-18 region's import block so the file's import section reads:

```python
import os

from dotenv import load_dotenv

load_dotenv()  # loads TEST_DATABASE_URL from .env

import psycopg
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jukebox_test"
)
# Point the app at the test database before importing app code
os.environ["DATABASE_URL"] = TEST_DSN

from app.auth import Identity, optional_identity, require_identity  # noqa: E402
from app.db import apply_schema  # noqa: E402
from app.main import app, seed_quick_adds  # noqa: E402


# Endpoint tests inject identity through X-Voter-Id / X-Display-Name headers
# instead of minting real Google JWTs. These overrides preserve that behavior;
# the real JWT verification path is covered directly in tests/test_auth.py.
def _fake_required(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity:
    if not x_voter_id:
        raise HTTPException(status_code=401, detail="sign in required")
    return Identity(voter_id=x_voter_id, display_name=(x_display_name or x_voter_id))


def _fake_optional(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity | None:
    if not x_voter_id:
        return None
    return Identity(voter_id=x_voter_id, display_name=(x_display_name or x_voter_id))


app.dependency_overrides[require_identity] = _fake_required
app.dependency_overrides[optional_identity] = _fake_optional
```

(Leave the `_TABLES`, `_connect_or_skip`, and the three fixtures below unchanged.)

- [ ] **Step 2: Point `app/main.py` at the new dependencies**

In `app/main.py`, change the import on line 13 from:

```python
from app.identity import Identity, require_identity
```

to:

```python
from app.auth import Identity, optional_identity, require_identity
```

- [ ] **Step 3: Switch `GET /api/songs` to optional auth**

In `app/main.py`, change the `list_songs` signature (line 222) from:

```python
def list_songs(identity: Identity = Depends(require_identity)) -> list[dict]:
```

to:

```python
def list_songs(identity: Identity | None = Depends(optional_identity)) -> list[dict]:
    voter_id = identity.voter_id if identity else None
```

Then in the same function change the query parameter (currently `(identity.voter_id,)` on line 235) to:

```python
            (voter_id,),
```

(No other change needed: `add_song` and `toggle_vote` already depend on `require_identity`, which now resolves to the JWT version. When `voter_id` is `None`, `v.voter_id = NULL` is never true in Postgres, so `did_i_vote` is correctly `False` for anonymous TV reads.)

- [ ] **Step 4: Run the full suite to verify it stays green**

Run: `pytest -q`
Expected: PASS for everything except `tests/test_identity.py`, which now fails to import `app.identity` (deleted next). If `test_identity.py` still references the old module, that's expected — proceed to Step 5.

- [ ] **Step 5: Delete the old identity module and its test**

```bash
git rm app/identity.py tests/test_identity.py
```

- [ ] **Step 6: Run the full suite again**

Run: `pytest -q`
Expected: PASS — all tests green (Supabase free-tier may occasionally drop one connection; re-run once if a single network timeout appears).

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/conftest.py
git commit -m "feat: require Google JWT for writes, optional auth for song reads"
```

---

## Task 4: `GET /api/config` endpoint

Expose the public Supabase URL + anon key so the static frontend can boot supabase-js without hardcoded values.

**Files:**
- Modify: `app/main.py` (add endpoint near the other `/api` routes)
- Create: `tests/test_config_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_api.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config_api.py -v`
Expected: FAIL — 404 Not Found (route does not exist).

- [ ] **Step 3: Add the endpoint**

In `app/main.py`, add this route immediately after the `list_quick_adds` function (after line 90):

```python
@app.get("/api/config")
def get_config() -> dict[str, str]:
    """Public Supabase values the frontend needs to boot supabase-js."""
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config_api.py -v`
Expected: PASS — both tests.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_config_api.py
git commit -m "feat: add GET /api/config exposing public Supabase values"
```

---

## Task 5: Frontend auth wrapper (`auth.js`)

A thin supabase-js wrapper the phone uses to sign in, sign out, and fetch the current token. No JS test runner exists in this repo, so this task is edit + manual smoke.

**Files:**
- Create: `app/static/auth.js`
- Modify: `app/static/index.html`

- [ ] **Step 1: Create `app/static/auth.js`**

```javascript
// Thin wrapper over supabase-js. Boots from /api/config so no keys are
// hardcoded. The @nexite.io rule is enforced server-side; the hd hint here
// only nudges Google's account picker.

let _sb = null;
let _user = null;

function _sessionUser(session) {
    if (!session || !session.user) return null;
    const u = session.user;
    const meta = u.user_metadata || {};
    return { name: meta.name || meta.full_name || u.email, email: u.email };
}

// `onChange(user)` fires on every auth state change. This matters after the
// Google redirect: getSession() can resolve before supabase-js finishes
// parsing the URL hash, so the SIGNED_IN event is what reliably flips the UI.
async function initAuth(onChange) {
    const cfg = await (await fetch("/api/config")).json();
    if (!cfg.supabase_url || !cfg.supabase_anon_key) {
        throw new Error("Supabase config missing on the server");
    }
    // `supabase` is the global from the supabase-js CDN script.
    _sb = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
    const { data } = await _sb.auth.getSession();
    _user = _sessionUser(data.session);
    _sb.auth.onAuthStateChange((_event, session) => {
        _user = _sessionUser(session);
        if (typeof onChange === "function") onChange(_user);
    });
    return _user;
}

async function signIn() {
    await _sb.auth.signInWithOAuth({
        provider: "google",
        options: { queryParams: { hd: "nexite.io" }, redirectTo: location.origin },
    });
}

async function signOut() {
    if (_sb) await _sb.auth.signOut();
    _user = null;
}

async function getToken() {
    if (!_sb) return null;
    const { data } = await _sb.auth.getSession();
    return data.session ? data.session.access_token : null;
}

function currentUser() {
    return _user;
}
```

- [ ] **Step 2: Update `index.html` — markup + scripts**

In `app/static/index.html`, replace the name-prompt block (lines 37-41):

```html
    <div id="name-prompt" class="name-prompt" hidden>
        <h2>What's your name?</h2>
        <input id="name-input" placeholder="Maya">
        <button id="name-submit">Join</button>
    </div>
```

with a sign-in gate:

```html
    <div id="signin-gate" class="name-prompt" hidden>
        <h2>&#127925; Office Jukebox</h2>
        <p class="muted">Sign in with your nexite.io Google account to add songs and vote.</p>
        <button id="google-signin">Sign in with Google</button>
    </div>
```

Then replace the identity line (line 45):

```html
        <div class="muted">You are <span id="who-am-i"></span> &middot; <a href="#" id="rename">change</a></div>
```

with:

```html
        <div class="muted">You are <span id="who-am-i"></span> &middot; <a href="#" id="signout">sign out</a></div>
```

Finally, replace the single script tag (line 67):

```html
    <script src="/static/phone.js"></script>
```

with the supabase-js CDN, the auth wrapper, then the app:

```html
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <script src="/static/auth.js"></script>
    <script src="/static/phone.js"></script>
```

- [ ] **Step 3: Commit**

```bash
git add app/static/auth.js app/static/index.html
git commit -m "feat: add supabase-js auth wrapper and sign-in gate markup"
```

---

## Task 6: Phone sign-in gate + Bearer headers (`phone.js`)

Replace the localStorage name identity with the Google session: gate the app behind sign-in, attach `Authorization: Bearer` to writes (and to reads when signed in), and wire sign-out. This rewrites the header helper and the boot block.

**Files:**
- Modify: `app/static/phone.js`

- [ ] **Step 1: Remove the localStorage identity helpers**

In `app/static/phone.js`, delete lines 1-2 and lines 9-40 — i.e. remove `VOTER_KEY`, `NAME_KEY`, `uuid()`, `getVoterId()`, `getDisplayName()`, `setDisplayName()`, and the old `identityHeaders()`. Replace that whole removed region (the top of the file, above `let _deadline`) so the file begins:

```javascript
let _deadline = null;        // Date, or null when voting is open forever
let _serverOffsetMs = 0;     // server clock minus this device's clock
let _votingOpen = true;      // false once the deadline passes
let _latestSongs = [];       // last songs payload, for re-render on tick/state flip

// Headers for write requests: attach the Google session JWT as a Bearer token.
async function authHeaders() {
    const headers = { "Content-Type": "application/json" };
    const token = await getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

// Headers for the song read: include the token when signed in so the
// did_i_vote hearts personalize; the read works fine without it.
async function readHeaders() {
    const token = await getToken();
    return token ? { "Authorization": `Bearer ${token}` } : {};
}
```

- [ ] **Step 2: Use `readHeaders()` in `loadSongs`**

Change `loadSongs` (was lines 51-56) to await the read headers:

```javascript
async function loadSongs() {
    const response = await fetch("/api/songs", { headers: await readHeaders() });
    if (!response.ok) return;
    const songs = await response.json();
    renderSongs(songs);
}
```

- [ ] **Step 3: Use `authHeaders()` in the write paths**

In `toggleVote` (was lines 158-170), change the fetch options to:

```javascript
async function toggleVote(songId) {
    const response = await fetch(`/api/songs/${songId}/vote`, {
        method: "POST",
        headers: await authHeaders(),
    });
```

(leave the rest of the function unchanged.)

In `addByUrl` (was lines 172-194), change the fetch options to:

```javascript
async function addByUrl(url) {
    const response = await fetch("/api/songs", {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({ youtube_url: url }),
    });
```

(leave the rest of the function unchanged.)

- [ ] **Step 4: Replace `setupRename` with `setupSignOut`**

Replace `setupRename()` (was lines 263-272) with:

```javascript
function setupSignOut() {
    document.getElementById("signout").addEventListener("click", async (e) => {
        e.preventDefault();
        await signOut();
        location.reload();
    });
}
```

- [ ] **Step 5: Rewrite `startApp` and the boot block**

Replace `startApp` (was lines 274-287) with a version that shows the signed-in user and wires sign-out:

```javascript
function startApp() {
    document.getElementById("signin-gate").hidden = true;
    document.getElementById("app").hidden = false;
    const user = currentUser();
    document.getElementById("who-am-i").textContent = user ? user.name : "";
    setupAddRow();
    setupSignOut();
    loadQuickAdds();
    loadSongs();
    loadDeadline();
    setInterval(loadSongs, 4000);
    setInterval(loadDeadline, 4000);
    setInterval(updateCountdown, 1000);
    document.getElementById("btn-refresh-suggestions").addEventListener("click", refreshQuickAdds);
}
```

Then replace `setupNamePrompt()` and the trailing boot conditional (was lines 289-308) with a sign-in gate boot. The guards keep `startApp`/`showSignInGate` idempotent, since both `getSession()` and the `onAuthStateChange` callback can fire:

```javascript
let _appStarted = false;
let _gateShown = false;

function showSignInGate() {
    if (_gateShown) return;
    _gateShown = true;
    const gate = document.getElementById("signin-gate");
    gate.hidden = false;
    document.getElementById("google-signin").addEventListener("click", () => signIn());
}

function renderForUser(user) {
    if (user && !_appStarted) {
        _appStarted = true;
        startApp();
    } else if (!user) {
        showSignInGate();
    }
}

async function boot() {
    let user = null;
    try {
        user = await initAuth(renderForUser);
    } catch (e) {
        showMessage("Sign-in is unavailable right now", "error");
    }
    renderForUser(user);
}

boot();
```

- [ ] **Step 6: Manual smoke test**

Run locally with the real Supabase env vars set (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `ADMIN_TOKEN`):

```bash
uvicorn app.main:app --reload
```

Then in a browser at `http://localhost:8000/`:
1. The sign-in gate shows; the playlist is hidden.
2. Click "Sign in with Google", complete the `@nexite.io` flow → redirected back, playlist shows, header reads "You are \<your name\>".
3. Add a song / vote → succeeds (Network tab shows `Authorization: Bearer …` on the POST).
4. Click "sign out" → page reloads to the sign-in gate.

Expected: all four behaviors hold. (If sign-in fails, confirm the Supabase Google provider + redirect URLs from Task 8 are configured.)

- [ ] **Step 7: Commit**

```bash
git add app/static/phone.js
git commit -m "feat: gate phone behind Google sign-in with Bearer-token writes"
```

---

## Task 7: TV kiosk — drop the stale identity header (`jukebox.js`)

The TV now reads the public `GET /api/songs` with optional auth. The placeholder `X-Voter-Id: jukebox-screen` header is meaningless; remove it so the read is cleanly anonymous.

**Files:**
- Modify: `app/static/jukebox.js` (lines 4-7 and 17)

- [ ] **Step 1: Remove the `identityHeaders` constant**

In `app/static/jukebox.js`, delete the `identityHeaders` object (lines 4-7):

```javascript
const identityHeaders = {
    "X-Voter-Id": "jukebox-screen",
    "X-Display-Name": "Jukebox",
};
```

- [ ] **Step 2: Drop the header from the fetch**

Change `fetchSongs` (was line 17) from:

```javascript
    const response = await fetch("/api/songs", { headers: identityHeaders });
```

to:

```javascript
    const response = await fetch("/api/songs");
```

- [ ] **Step 3: Manual smoke test**

With the server running, open `http://localhost:8000/jukebox`.
Expected: the leaderboard (podium + rest) renders with no console errors and no auth header on the `/api/songs` request.

- [ ] **Step 4: Commit**

```bash
git add app/static/jukebox.js
git commit -m "refactor: drop stale identity header from TV song read"
```

---

## Task 8: Docs — env vars + one-time Google/Supabase setup

Document the new env vars and the one-time console setup so the deployment is reproducible.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add an "Authentication" section to `README.md`**

Append this section to `README.md` (place it after the existing environment/deployment section):

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Google sign-in env vars and one-time setup"
```

---

## Final verification

- [ ] **Run the whole suite**

Run: `pytest -q`
Expected: PASS (re-run once if a single Supabase free-tier connection timeout appears — that's network flakiness, not a code failure).

- [ ] **Confirm no stale references to the deleted module**

Run: `grep -rn "app.identity\|X-Voter-Id\|X-Display-Name" app/ tests/`
Expected: only matches are the `_fake_required`/`_fake_optional` test header names in `tests/conftest.py`. No references in `app/`.
```
