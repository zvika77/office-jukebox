const VOTER_KEY = "jukebox.voter_id";
const NAME_KEY = "jukebox.display_name";

let _deadline = null;        // Date, or null when voting is open forever
let _serverOffsetMs = 0;     // server clock minus this device's clock
let _votingOpen = true;      // false once the deadline passes
let _latestSongs = [];       // last songs payload, for re-render on tick/state flip

function uuid() {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
}

function getVoterId() {
    let id = localStorage.getItem(VOTER_KEY);
    if (!id) {
        id = uuid();
        localStorage.setItem(VOTER_KEY, id);
    }
    return id;
}

function getDisplayName() {
    return localStorage.getItem(NAME_KEY) || "";
}

function setDisplayName(name) {
    localStorage.setItem(NAME_KEY, name);
}

function identityHeaders() {
    return {
        "X-Voter-Id": getVoterId(),
        "X-Display-Name": getDisplayName(),
        "Content-Type": "application/json",
    };
}

function showMessage(text, kind = "info") {
    const area = document.getElementById("message-area");
    const el = document.createElement("div");
    el.className = `message ${kind}`;
    el.textContent = text;
    area.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

async function loadSongs() {
    const response = await fetch("/api/songs", { headers: identityHeaders() });
    if (!response.ok) return;
    const songs = await response.json();
    renderSongs(songs);
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

// Toggle the add/quick-add UI and re-render the song list when the
// open/closed state flips. Safe to call every tick — only re-renders on change.
function setVotingOpen(open) {
    const changed = open !== _votingOpen;
    _votingOpen = open;
    const section = document.getElementById("voting-section");
    if (section) section.hidden = !open;
    if (changed) renderSongs(_latestSongs);
}

function updateCountdown() {
    const banner = document.getElementById("countdown-banner");
    if (_deadline === null) {
        banner.hidden = true;
        setVotingOpen(true);
        return;
    }
    const remaining = _deadline.getTime() - serverNow().getTime();
    banner.hidden = false;
    if (remaining <= 0) {
        banner.className = "countdown-banner closed";
        banner.textContent = "🔒 Voting has closed — here's the lineup";
        setVotingOpen(false);
    } else {
        banner.className = "countdown-banner open";
        banner.innerHTML = `⏳ Voting closes in <span class="time">${formatRemaining(remaining)}</span>`;
        setVotingOpen(true);
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
        updateCountdown();
    } catch {
        /* ignore network hiccups; the ticker keeps the last known state */
    }
}

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[c]));
}

function renderSongs(songs) {
    _latestSongs = songs;
    const container = document.getElementById("song-list");
    container.innerHTML = "";
    // Once voting closes, collapse to just the top 3 that will play.
    const list = _votingOpen ? songs : songs.slice(0, 3);
    list.forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "song-card" + (i < 3 ? " top3" : "");
        const img = document.createElement("img");
        img.src = song.thumbnail_url;
        img.loading = "lazy";
        card.appendChild(img);
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerHTML = `
            <div class="title">${escapeHtml(song.title)}</div>
            <div class="added-by">added by ${escapeHtml(song.added_by_name)} &middot; ${song.votes} ❤</div>
            ${i < 3 ? '<div class="muted">🏆 in the top 3</div>' : ""}
        `;
        card.appendChild(meta);
        if (_votingOpen) {
            const btn = document.createElement("button");
            btn.className = "vote-btn" + (song.did_i_vote ? " voted" : "");
            btn.textContent = song.did_i_vote ? "❤" : "🤍";
            btn.addEventListener("click", () => toggleVote(song.id));
            card.appendChild(btn);
        }
        container.appendChild(card);
    });
}

async function toggleVote(songId) {
    const response = await fetch(`/api/songs/${songId}/vote`, {
        method: "POST",
        headers: identityHeaders(),
    });
    if (response.status === 403) {
        showMessage("Voting has closed", "error");
        await loadDeadline();
        return;
    }
    if (!response.ok) return;
    await loadSongs();
}

async function addByUrl(url) {
    const response = await fetch("/api/songs", {
        method: "POST",
        headers: identityHeaders(),
        body: JSON.stringify({ youtube_url: url }),
    });
    if (response.status === 403) {
        showMessage("Voting has closed", "error");
        await loadDeadline();
        return;
    }
    if (response.status === 400) {
        const body = await response.json();
        showMessage(body.detail || "couldn't add that link", "error");
        return;
    }
    if (response.status === 200) {
        showMessage("already in the list — upvoted for you", "info");
    } else if (response.status === 201) {
        showMessage("added!", "info");
    }
    await loadSongs();
}

async function refreshQuickAdds() {
    const btn = document.getElementById("btn-refresh-suggestions");
    btn.textContent = "↻ Refreshing…";
    btn.disabled = true;
    try {
        const response = await fetch("/api/quick-adds/refresh", { method: "POST" });
        if (response.ok) {
            const rows = await response.json();
            renderQuickAdds(rows);
            showMessage("Suggestions refreshed!", "info");
            return;
        }
        let detail = "Couldn't refresh suggestions";
        try {
            const body = await response.json();
            if (body.detail) detail = body.detail;
        } catch { /* ignore parse errors */ }
        showMessage(detail, "error");
    } catch {
        showMessage("Couldn't reach the server", "error");
    } finally {
        btn.textContent = "↻ Refresh";
        btn.disabled = false;
    }
}

function renderQuickAdds(rows) {
    const quickList = document.getElementById("quick-list");
    quickList.innerHTML = "";
    rows.forEach((row) => {
        const card = document.createElement("div");
        card.className = "card";
        const img = document.createElement("img");
        img.src = row.thumbnail_url;
        img.loading = "lazy";
        card.appendChild(img);
        const title = document.createElement("div");
        title.textContent = row.title;
        card.appendChild(title);
        card.addEventListener("click", () =>
            addByUrl(`https://www.youtube.com/watch?v=${row.youtube_id}`)
        );
        quickList.appendChild(card);
    });
}

async function loadQuickAdds() {
    const response = await fetch("/api/quick-adds");
    if (!response.ok) return;
    const rows = await response.json();
    renderQuickAdds(rows);
}

function setupAddRow() {
    const input = document.getElementById("url-input");
    document.getElementById("url-submit").addEventListener("click", () => {
        const url = input.value.trim();
        if (url) {
            addByUrl(url);
            input.value = "";
        }
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("url-submit").click();
    });
}

function setupRename() {
    document.getElementById("rename").addEventListener("click", (e) => {
        e.preventDefault();
        const name = prompt("New display name:", getDisplayName());
        if (name && name.trim()) {
            setDisplayName(name.trim());
            document.getElementById("who-am-i").textContent = name.trim();
        }
    });
}

function startApp() {
    document.getElementById("name-prompt").hidden = true;
    document.getElementById("app").hidden = false;
    document.getElementById("who-am-i").textContent = getDisplayName();
    setupAddRow();
    setupRename();
    loadQuickAdds();
    loadSongs();
    loadDeadline();
    setInterval(loadSongs, 4000);
    setInterval(loadDeadline, 4000);
    setInterval(updateCountdown, 1000);
    document.getElementById("btn-refresh-suggestions").addEventListener("click", refreshQuickAdds);
}

function setupNamePrompt() {
    const submit = document.getElementById("name-submit");
    const input = document.getElementById("name-input");
    submit.addEventListener("click", () => {
        const name = input.value.trim();
        if (!name) return;
        setDisplayName(name);
        startApp();
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") submit.click();
    });
}

if (getDisplayName()) {
    startApp();
} else {
    document.getElementById("name-prompt").hidden = false;
    setupNamePrompt();
}
