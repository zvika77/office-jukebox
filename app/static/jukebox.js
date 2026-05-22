const params = new URLSearchParams(location.search);
const adminToken = params.get("admin");

const identityHeaders = {
    "X-Voter-Id": "jukebox-screen",
    "X-Display-Name": "Jukebox",
};

let ytPlayer = null;
let queue = [];
let queueIndex = 0;

async function fetchSongs() {
    const response = await fetch("/api/songs", { headers: identityHeaders });
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
    songs.slice(0, 4).forEach((song, i) => {
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
    songs.slice(4).forEach((song) => {
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

function showPlayer(on) {
    document.getElementById("player").classList.toggle("active", on);
    document.getElementById("player-actions").hidden = !on || !adminToken;
}

function playCurrent() {
    if (queueIndex >= queue.length) {
        stopPlayback();
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

function stopPlayback() {
    if (ytPlayer && ytPlayer.stopVideo) ytPlayer.stopVideo();
    showPlayer(false);
    queue = [];
    queueIndex = 0;
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
    const response = await fetch(`/api/play?admin=${encodeURIComponent(adminToken)}`, {
        method: "POST",
    });
    if (!response.ok) return;
    const body = await response.json();
    if (body.queue.length === 0) return;
    queue = body.queue;
    queueIndex = 0;
    showPlayer(true);
    playCurrent();
}

function setupAdmin() {
    if (!adminToken) return;
    document.getElementById("admin-actions").hidden = false;
    document.getElementById("btn-play").addEventListener("click", startPlayback);
    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (!confirm("Wipe all songs and votes for today?")) return;
        await fetch(`/api/reset?admin=${encodeURIComponent(adminToken)}`, { method: "POST" });
    });
    document.getElementById("btn-skip").addEventListener("click", advance);
    document.getElementById("btn-stop").addEventListener("click", stopPlayback);
}

function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", refresh);
}

document.getElementById("public-url").textContent = location.origin;
setupAdmin();
setupSSE();
refresh();
