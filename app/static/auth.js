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
