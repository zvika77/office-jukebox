const VOTER_KEY = "jukebox.voter_id";
const NAME_KEY = "jukebox.display_name";

function uuid() {
    return crypto.randomUUID();
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
    const container = document.getElementById("song-list");
    container.innerHTML = "";
    songs.forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "song-card" + (i < 4 ? " top4" : "");
        const img = document.createElement("img");
        img.src = song.thumbnail_url;
        img.loading = "lazy";
        card.appendChild(img);
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerHTML = `
            <div class="title">${escapeHtml(song.title)}</div>
            <div class="added-by">added by ${escapeHtml(song.added_by_name)} &middot; ${song.votes} ❤</div>
            ${i < 4 ? '<div class="muted">🏆 in the top 4</div>' : ""}
        `;
        card.appendChild(meta);
        const btn = document.createElement("button");
        btn.className = "vote-btn" + (song.did_i_vote ? " voted" : "");
        btn.textContent = song.did_i_vote ? "❤" : "🤍";
        btn.addEventListener("click", () => toggleVote(song.id));
        card.appendChild(btn);
        container.appendChild(card);
    });
}

async function toggleVote(songId) {
    const response = await fetch(`/api/songs/${songId}/vote`, {
        method: "POST",
        headers: identityHeaders(),
    });
    if (!response.ok) return;
    await loadSongs();
}

async function addByUrl(url) {
    const response = await fetch("/api/songs", {
        method: "POST",
        headers: identityHeaders(),
        body: JSON.stringify({ youtube_url: url }),
    });
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

async function loadQuickAdds() {
    const response = await fetch("/api/quick-adds");
    if (!response.ok) return;
    const rows = await response.json();
    const decades = ["60s", "70s", "80s", "90s", "2000s", "2010s"];
    const byDecade = {};
    decades.forEach((d) => (byDecade[d] = []));
    rows.forEach((row) => byDecade[row.decade]?.push(row));

    const decadeRow = document.getElementById("decade-row");
    const quickList = document.getElementById("quick-list");
    let activeDecade = decades[0];

    function renderDecade() {
        decadeRow.innerHTML = "";
        decades.forEach((d) => {
            const chip = document.createElement("div");
            chip.className = "chip" + (d === activeDecade ? " active" : "");
            chip.textContent = d;
            chip.addEventListener("click", () => {
                activeDecade = d;
                renderDecade();
            });
            decadeRow.appendChild(chip);
        });
        quickList.innerHTML = "";
        byDecade[activeDecade].forEach((row) => {
            const card = document.createElement("div");
            card.className = "card";
            const img = document.createElement("img");
            img.src = row.thumbnail_url;
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
    renderDecade();
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

function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", loadSongs);
}

function startApp() {
    document.getElementById("name-prompt").hidden = true;
    document.getElementById("app").hidden = false;
    document.getElementById("who-am-i").textContent = getDisplayName();
    setupAddRow();
    setupRename();
    setupSSE();
    loadQuickAdds();
    loadSongs();
    setInterval(loadSongs, 10000);
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
