let sessionId = null;
let polling = null;
let lastMessageCount = 0;

const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");

async function initSession() {
    // Check if URL matches /stories/<id>
    const match = window.location.pathname.match(/^\/stories\/(.+)/);
    if (match) {
        const id = match[1];
        sessionId = `story-${id}`;
        try {
            const res = await fetch(`/api/sessions/${sessionId}/state`);
            if (res.ok) {
                startPolling();
                return;
            }
        } catch (_) {
            // Session not found, fall through to create new one
        }
    }

    // Create a new session and redirect
    const res = await fetch("/api/sessions", { method: "POST" });
    const data = await res.json();
    sessionId = data.session_id;
    const shortId = sessionId.replace(/^story-/, "");
    window.history.replaceState(null, "", `/stories/${shortId}`);
    startPolling();
}

function startPolling() {
    pollState();
    polling = setInterval(pollState, 1000);
}

async function pollState() {
    if (!sessionId) return;

    try {
        const res = await fetch(`/api/sessions/${sessionId}/state`);
        const state = await res.json();
        renderChat(state.messages);
        renderStory(state.story);
        updateTypingIndicator(state.processing);

        if (state.finished) {
            document.getElementById("chat-panel").classList.add("finished");
            document.getElementById("story-panel").classList.remove("story-pending");

            // Keep polling until the illustration is ready, then stop.
            if (!state.story.illustration_loading) {
                clearInterval(polling);
            }
        } else if (!state.processing) {
            setInputEnabled(true);
        }
    } catch (e) {
        console.error("Polling error:", e);
    }
}

function renderChat(messages) {
    if (messages.length === lastMessageCount) return;
    lastMessageCount = messages.length;

    chatMessages.innerHTML = "";
    for (const msg of messages) {
        const div = document.createElement("div");
        div.className = `chat-msg ${msg.role}`;
        if (msg.role === "assistant") {
            div.innerHTML = marked.parse(msg.content);
        } else {
            div.textContent = msg.content;
        }
        chatMessages.appendChild(div);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderStory(story) {
    const placeholder = document.getElementById("story-placeholder");
    const content = document.getElementById("story-content");
    const titleEl = document.getElementById("story-title");
    const illustrationEl = document.getElementById("story-illustration");
    const textEl = document.getElementById("story-text");

    if (!story.title && !story.text && !story.illustration_url && !story.illustration_loading && !story.illustration_failed) {
        placeholder.style.display = "flex";
        content.style.display = "none";
        return;
    }

    placeholder.style.display = "none";
    content.style.display = "block";

    if (story.title && titleEl.textContent !== story.title) {
        titleEl.textContent = story.title;
        titleEl.classList.remove("story-hidden");
        titleEl.classList.add("story-reveal");
        document.title = story.title + " - Bedtime Story Agent";
    }

    const loaderEl = document.getElementById("illust-loader");
    const errorEl = document.getElementById("illust-error");
    const placeholderEl = document.getElementById("illust-placeholder");
    const illustrationWrapper = illustrationEl.parentElement;
    const existingImg = illustrationEl.querySelector("img");

    function revealIllustration(showPlaceholder, showLoader, showError) {
        placeholderEl.style.display = showPlaceholder ? "" : "none";
        loaderEl.style.display = showLoader ? "" : "none";
        errorEl.style.display = showError ? "" : "none";
        illustrationWrapper.classList.remove("story-hidden");
        illustrationWrapper.classList.add("story-reveal");
    }

    if (story.illustration_loading) {
        if (existingImg) existingImg.remove();
        revealIllustration(false, true, false);
    } else if (story.illustration_failed) {
        if (existingImg) existingImg.remove();
        revealIllustration(false, false, true);
    } else if (!existingImg && story.illustration_url) {
        const img = document.createElement("img");
        img.src = story.illustration_url;
        img.alt = "Story illustration";
        img.className = "w-full rounded-xl";
        illustrationEl.appendChild(img);
        revealIllustration(false, false, false);
    } else if (!existingImg && story.title) {
        revealIllustration(true, false, false);
    }

    if (story.text) {
        const parsed = marked.parse(story.text);
        if (textEl.innerHTML !== parsed) {
            textEl.innerHTML = parsed;
            textEl.classList.remove("story-hidden");
            textEl.classList.add("story-reveal");
        }

    }
}

function updateTypingIndicator(processing) {
    const existing = document.querySelector(".chat-msg.typing");
    if (processing && !existing) {
        const div = document.createElement("div");
        div.className = "chat-msg typing";
        div.innerHTML = 'Thinking<span class="dots"></span>';
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } else if (!processing && existing) {
        existing.remove();
    }
}

function setInputEnabled(enabled) {
    chatInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    if (enabled) chatInput.focus();
}

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || !sessionId) return;

    chatInput.value = "";
    setInputEnabled(false);

    // Optimistically render the user message before the server round-trip.
    // Increment lastMessageCount so pollState() won't duplicate it when the
    // server-side state catches up.
    const div = document.createElement("div");
    div.className = "chat-msg user";
    div.textContent = message;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    lastMessageCount++;

    await fetch(`/api/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
    });
}

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !chatInput.disabled) {
        sendMessage();
    }
});

// Keep input bar visible above the virtual keyboard on mobile
chatInput.addEventListener("focus", () => {
    setTimeout(() => {
        document.getElementById("chat-input-bar").scrollIntoView({ block: "end", behavior: "smooth" });
    }, 300);
});

// Start or resume session on load
initSession();
