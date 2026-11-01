const params = new URLSearchParams(location.search);
const adminToken = params.get("admin");

// Keep the admin token out of the address bar and browser history once we've read it.
if (adminToken) {
    const cleaned = new URL(location.href);
    cleaned.searchParams.delete("admin");
    history.replaceState({}, "", cleaned);
}

let ytPlayer = null;
let queue = [];
let queueIndex = 0;

let _deadline = null;       // Date, or null when voting is open forever
let _serverOffsetMs = 0;    // server clock minus this device's clock

// The Tabata Pro timer embedded next to the video during playback. Any of these
// params can be overridden by adding them to the jukebox page URL, e.g.
// ?work=45&rest=15&cycles=8 — anything not supplied falls back to the default.
const TABATA_DEFAULTS = { name: "Tabata", prep: "10", work: "60", rest: "30", cycles: "5", tabatas: "1" };
const TABATA_DEFAULT_BASE = "https://simpletouchsoftware.com/timers/tabatapro";
const TABATA_STORAGE_KEY = "tabata_url";

function tabataSrc() {
    const stored = localStorage.getItem(TABATA_STORAGE_KEY);
    if (stored) return stored;
    const q = new URLSearchParams();
    for (const [key, fallback] of Object.entries(TABATA_DEFAULTS)) {
        q.set(key, params.get(key) ?? fallback);
    }
    // Note: no trailing slash before "?" — the trailing-slash variant 302-redirects
    // to the (http) homepage, which breaks the iframe embed.
    return `${TABATA_DEFAULT_BASE}?${q.toString()}`;
}

// Up to two intro songs that play before the top 3 each time Play is hit. The
// admin pastes a YouTube link into each box; like the timer URL, they're kept
// in this device's localStorage so they stick across sessions.
const INTRO_STORAGE_KEYS = ["intro_url_1", "intro_url_2"];

// Mirror of the backend's extract_video_id(): pull the 11-char id from a
// youtu.be or /watch?v= link so intros accept the same URL shapes as votes.
const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const YT_HOSTS = new Set([
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
]);

function extractVideoId(url) {
    if (!url) return null;
    let parsed;
    try {
        parsed = new URL(url.trim());
    } catch {
        return null;
    }
    const host = parsed.hostname.toLowerCase();
    if (!YT_HOSTS.has(host)) return null;
    let candidate;
    if (host === "youtu.be") {
        candidate = parsed.pathname.replace(/^\/+/, "").split("/")[0];
    } else {
        const path = parsed.pathname.replace(/\/+$/, "");
        if (path !== "/watch" && path !== "") return null;
        candidate = parsed.searchParams.get("v") ?? "";
    }
    return VIDEO_ID_RE.test(candidate) ? candidate : null;
}

// The saved intros as queue entries, in order, dropping empty/unrecognized boxes.
function introQueue() {
    return INTRO_STORAGE_KEYS
        .map((key) => extractVideoId(localStorage.getItem(key) ?? ""))
        .filter(Boolean)
        .map((youtube_id, i) => ({ youtube_id, title: `Intro ${i + 1}` }));
}

// The Tabata page won't reflow into a narrow column — it keeps its wide layout
// and clips. So render it at this fixed logical width and scale the whole frame
// down to fit the pane. Bump this down to make the timer appear larger.
const TABATA_LOGICAL_WIDTH = 1100;

function fitTabata() {
    const pane = document.getElementById("tabata-pane");
    const frame = document.getElementById("tabata-frame");
    if (!pane || !frame || pane.clientWidth === 0) return;
    const scale = pane.clientWidth / TABATA_LOGICAL_WIDTH;
    frame.style.width = `${TABATA_LOGICAL_WIDTH}px`;
    frame.style.height = `${pane.clientHeight / scale}px`;
    frame.style.transform = `scale(${scale})`;
}

async function fetchSongs() {
    const response = await fetch("/api/songs");
    return response.json();
}

function thumb(url) {
    const img = document.createElement("img");
    img.src = url;
    img.loading = "lazy";
    return img;
}

function renderPodium(songs) {
    const container = document.getElementById("podium");
    container.innerHTML = "";
    songs.slice(0, 3).forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "card";
        card.appendChild(thumb(song.thumbnail_url));
        const title = document.createElement("div");
        title.textContent = `#${i + 1} ${song.title}`;
        card.appendChild(title);
        const meta = document.createElement("div");
        meta.className = "muted";
        meta.textContent = `added by ${song.added_by_name}`;
        card.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        card.appendChild(votes);
        container.appendChild(card);
    });
}

function renderRest(songs) {
    const container = document.getElementById("rest");
    container.innerHTML = "";
    songs.slice(3).forEach((song) => {
        const row = document.createElement("div");
        row.className = "row";
        row.appendChild(thumb(song.thumbnail_url));
        const meta = document.createElement("div");
        meta.className = "meta";
        const titleDiv = document.createElement("div");
        titleDiv.textContent = song.title;
        const byDiv = document.createElement("div");
        byDiv.className = "muted";
        byDiv.textContent = `added by ${song.added_by_name}`;
        meta.appendChild(titleDiv);
        meta.appendChild(byDiv);
        row.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        row.appendChild(votes);
        container.appendChild(row);
    });
}

async function refresh() {
    const songs = await fetchSongs();
    renderPodium(songs);
    renderRest(songs);
}

function serverNow() {
    return new Date(Date.now() + _serverOffsetMs);
}

function formatRemaining(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

// Format a Date as a value the <input type="datetime-local"> understands (local time).
function toLocalInput(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
        `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function updateCountdown() {
    const banner = document.getElementById("countdown-banner");
    if (_deadline === null) {
        banner.hidden = true;
        return;
    }
    const remaining = _deadline.getTime() - serverNow().getTime();
    banner.hidden = false;
    if (remaining <= 0) {
        banner.className = "countdown-banner closed";
        banner.textContent = "🔒 Voting has closed";
    } else {
        banner.className = "countdown-banner open";
        banner.innerHTML = `⏳ Voting closes in <span class="time">${formatRemaining(remaining)}</span>`;
    }
}

async function loadDeadline() {
    try {
        const response = await fetch("/api/voting-deadline");
        if (!response.ok) return;
        const body = await response.json();
        _deadline = body.deadline ? new Date(body.deadline) : null;
        if (body.server_now) {
            _serverOffsetMs = new Date(body.server_now).getTime() - Date.now();
        }
        // Keep the admin's input box in sync with the stored deadline, but
        // never while it's focused — otherwise the 4s poll clobbers whatever
        // time the admin is currently picking and it snaps back every tick.
        const input = document.getElementById("deadline-input");
        if (input && _deadline && document.activeElement !== input) {
            input.value = toLocalInput(_deadline);
        }
        updateCountdown();
    } catch {
        /* ignore network hiccups; the ticker keeps the last known state */
    }
}

function showPlayer(on) {
    document.getElementById("player").classList.toggle("active", on);
    document.getElementById("player-actions").hidden = !on || !adminToken;
    // (Re)load a fresh Tabata timer beside the video each session; blank it out
    // on stop so its countdown beeps don't keep running in the background.
    const frame = document.getElementById("tabata-frame");
    frame.src = on ? tabataSrc() : "about:blank";
    if (on) fitTabata();
}

function playCurrent() {
    if (queueIndex >= queue.length) {
        finishSongs();
        return;
    }
    const song = queue[queueIndex];
    document.getElementById("now-playing").textContent =
        `▶ ${song.title}  (${queueIndex + 1}/${queue.length})`;
    if (ytPlayer && ytPlayer.loadVideoById) {
        ytPlayer.loadVideoById(song.youtube_id);
    }
}

function advance() {
    queueIndex += 1;
    playCurrent();
}

// The song queue is done, but the Tabata may still be running. Keep the player
// and the timer on screen so everyone can finish the workout — only the explicit
// Stop button tears things down. Just idle the video and note the songs are done.
function finishSongs() {
    if (ytPlayer && ytPlayer.stopVideo) ytPlayer.stopVideo();
    document.getElementById("now-playing").textContent =
        "✔ All songs played — finish your Tabata! 💪";
}

function stopPlayback() {
    if (ytPlayer && ytPlayer.stopVideo) ytPlayer.stopVideo();
    showPlayer(false);
    queue = [];
    queueIndex = 0;
}

function togglePause() {
    if (!ytPlayer || !ytPlayer.getPlayerState) return;
    if (ytPlayer.getPlayerState() === YT.PlayerState.PLAYING) {
        ytPlayer.pauseVideo();
    } else {
        ytPlayer.playVideo();
    }
}

// Reflect whatever the player is actually doing on the Pause/Resume button,
// whether it was toggled here or changed on its own.
function syncPauseButton(state) {
    const btn = document.getElementById("btn-pause");
    if (!btn) return;
    if (state === YT.PlayerState.PAUSED) {
        btn.innerHTML = "&#9654; Resume";
    } else if (state === YT.PlayerState.PLAYING) {
        btn.innerHTML = "&#9208; Pause";
    }
}

function showToast(message) {
    const toast = document.createElement("div");
    toast.textContent = message;
    toast.style.cssText =
        "position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#c9302c;color:white;padding:12px 24px;border-radius:8px;z-index:200;";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

window.onYouTubeIframeAPIReady = function () {
    ytPlayer = new YT.Player("yt-target", {
        width: "100%",
        height: "100%",
        playerVars: { autoplay: 1, controls: 0, modestbranding: 1 },
        events: {
            onStateChange: (e) => {
                if (e.data === YT.PlayerState.ENDED) advance();
                syncPauseButton(e.data);
            },
            onError: () => {
                showToast("⚠️ couldn't play that one — skipping");
                advance();
            },
        },
    });
};

async function startPlayback() {
    if (!adminToken) return;
    const response = await fetch("/api/play", {
        method: "POST",
        headers: { "X-Admin-Token": adminToken },
    });
    if (!response.ok) return;
    const body = await response.json();
    // No top songs yet means no session — don't play intros on their own.
    if (body.queue.length === 0) return;
    queue = [...introQueue(), ...body.queue];
    queueIndex = 0;
    showPlayer(true);
    playCurrent();
}

async function setDeadline() {
    if (!adminToken) return;
    const input = document.getElementById("deadline-input");
    const value = input.value;
    if (!value) {
        showToast("Pick a date and time first");
        return;
    }
    // datetime-local is local time; toISOString() converts it to UTC for the server.
    const iso = new Date(value).toISOString();
    const response = await fetch("/api/voting-deadline", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ deadline: iso }),
    });
    if (!response.ok) {
        showToast("Couldn't set the deadline");
        return;
    }
    await loadDeadline();
}

function setupAdmin() {
    if (!adminToken) return;
    document.getElementById("admin-actions").hidden = false;
    document.getElementById("btn-play").addEventListener("click", startPlayback);
    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (!confirm("Wipe all songs and votes for today?")) return;
        await fetch("/api/reset", { method: "POST", headers: { "X-Admin-Token": adminToken } });
    });
    document.getElementById("btn-set-deadline").addEventListener("click", setDeadline);
    document.getElementById("btn-pause").addEventListener("click", togglePause);
    document.getElementById("btn-skip").addEventListener("click", advance);
    document.getElementById("btn-stop").addEventListener("click", stopPlayback);

    const tabataInput = document.getElementById("tabata-url-input");
    tabataInput.value = localStorage.getItem(TABATA_STORAGE_KEY) ?? tabataSrc();
    document.getElementById("btn-save-tabata-url").addEventListener("click", () => {
        const url = tabataInput.value.trim();
        if (!url) return;
        localStorage.setItem(TABATA_STORAGE_KEY, url);
        showToast("Timer URL saved");
    });

    // Prefill the intro boxes with whatever's saved, and persist on Save.
    INTRO_STORAGE_KEYS.forEach((key, i) => {
        document.getElementById(`intro-url-${i + 1}`).value = localStorage.getItem(key) ?? "";
    });
    document.getElementById("btn-save-intros").addEventListener("click", () => {
        let unrecognized = false;
        INTRO_STORAGE_KEYS.forEach((key, i) => {
            const url = document.getElementById(`intro-url-${i + 1}`).value.trim();
            if (url) {
                localStorage.setItem(key, url);
                if (!extractVideoId(url)) unrecognized = true;
            } else {
                localStorage.removeItem(key);
            }
        });
        showToast(unrecognized ? "Saved, but a link isn't a recognized YouTube URL" : "Intro songs saved");
    });
}

document.getElementById("public-url").textContent = location.origin;
setupAdmin();
refresh();
loadDeadline();
setInterval(refresh, 4000);
setInterval(loadDeadline, 4000);
setInterval(updateCountdown, 1000);
window.addEventListener("resize", fitTabata);
