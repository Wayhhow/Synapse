/* Synapse chat frontend — SSE streaming against /chat/stream, zero deps. */
(() => {
    "use strict";

    const chatArea = document.getElementById("chatArea");
    const input = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const skillList = document.getElementById("skillList");
    const skillCount = document.getElementById("skillCount");
    const statsList = document.getElementById("statsList");
    const sessionIdEl = document.getElementById("sessionId");
    const clearBtn = document.getElementById("clearBtn");
    const menuBtn = document.getElementById("menuBtn");
    const sidebar = document.getElementById("sidebar");

    let sessionId = localStorage.getItem("synapse_session");
    let busy = false;

    // ---------------- utilities ----------------

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    // Minimal markdown: fenced code, inline code, bold, italics, links.
    function renderMarkdown(text) {
        const blocks = [];
        let src = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
            blocks.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
            return `\u0000BLOCK${blocks.length - 1}\u0000`;
        });
        src = escapeHtml(src);
        src = src.replace(/`([^`\n]+)`/g, "<code>$1</code>");
        src = src.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
        src = src.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
        src = src.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
        src = src.replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
        src = src.replace(/\u0000BLOCK(\d+)\u0000/g, (_, i) => blocks[Number(i)]);
        return src;
    }

    function addMessage(role, html) {
        const el = document.createElement("div");
        el.className = `message ${role}`;
        el.innerHTML = html;
        chatArea.appendChild(el);
        chatArea.scrollTop = chatArea.scrollHeight;
        return el;
    }

    function addStatus(text, isError) {
        const el = document.createElement("div");
        el.className = "status-line" + (isError ? " error" : "");
        el.innerHTML = (isError ? "" : '<span class="spinner"></span>') + escapeHtml(text);
        chatArea.appendChild(el);
        chatArea.scrollTop = chatArea.scrollHeight;
        return el;
    }

    function addChipRow(parent, chips) {
        const row = document.createElement("div");
        row.className = "meta-row";
        for (const chip of chips) {
            const c = document.createElement("span");
            c.className = `chip ${chip.kind || ""}`;
            c.textContent = chip.text;
            row.appendChild(c);
        }
        parent.appendChild(row);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // ---------------- sidebar data ----------------

    async function refreshSidebar() {
        try {
            const [skillsRes, statsRes] = await Promise.all([
                fetch("/skills"), fetch("/stats"),
            ]);
            const skills = await skillsRes.json();
            skillCount.textContent = skills.length;
            skillList.innerHTML = "";
            for (const s of skills) {
                const li = document.createElement("li");
                const desc = s.description.split("\n")[0];
                li.innerHTML = `<strong>${escapeHtml(s.name)}</strong><span class="desc" title="${escapeHtml(s.description)}">${escapeHtml(desc)}</span>`;
                skillList.appendChild(li);
            }
            const stats = await statsRes.json();
            statsList.innerHTML = "";
            const entries = Object.entries(stats).sort((a, b) => a[1].health_score - b[1].health_score);
            if (!entries.length) {
                statsList.innerHTML = '<li class="dim">no data yet</li>';
                return;
            }
            for (const [name, info] of entries) {
                const cls = info.health_score >= 70 ? "score-good" : info.health_score >= 50 ? "score-mid" : "score-bad";
                const li = document.createElement("li");
                li.innerHTML = `<span>${escapeHtml(name)}</span><span class="${cls}">${info.health_score.toFixed(1)}</span>`;
                statsList.appendChild(li);
            }
        } catch (e) {
            /* server not fully ready; ignore */
        }
    }

    // ---------------- chat flow (SSE) ----------------

    function setBusy(state) {
        busy = state;
        sendBtn.disabled = state;
        input.disabled = state;
    }

    async function sendMessage() {
        const text = input.value.trim();
        if (!text || busy) return;
        input.value = "";
        addMessage("user", renderMarkdown(text));
        setBusy(true);

        const usedChips = [];
        let statusEl = addStatus("thinking…");
        let assistantEl = null;
        let finalText = "";

        try {
            const resp = await fetch("/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_id: sessionId }),
            });
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split("\n\n");
                buffer = parts.pop();
                for (const part of parts) {
                    const line = part.split("\n").find((l) => l.startsWith("data: "));
                    if (!line) continue;
                    let event;
                    try { event = JSON.parse(line.slice(6)); } catch (e) { continue; }
                    handleEvent(event);
                }
            }
        } catch (e) {
            statusEl.remove();
            addMessage("assistant", `<span class="score-bad">Connection error: ${escapeHtml(String(e))}</span>`);
        }

        function handleEvent(event) {
            switch (event.type) {
                case "session":
                    sessionId = event.session_id;
                    localStorage.setItem("synapse_session", sessionId);
                    sessionIdEl.textContent = `session ${sessionId.slice(0, 8)}`;
                    break;
                case "llm":
                    statusEl.innerHTML = '<span class="spinner"></span>reasoning…';
                    break;
                case "tool_start":
                    statusEl.innerHTML = `<span class="spinner"></span>running skill “${escapeHtml(event.name)}”…`;
                    break;
                case "tool_result":
                    usedChips.push({
                        kind: event.success ? "tool" : "error",
                        text: event.success
                            ? `${event.name} · ${Math.round(event.duration_ms)}ms`
                            : `${event.name} failed`,
                    });
                    break;
                case "meta":
                    if (event.status === "generating") {
                        statusEl.innerHTML = `<span class="spinner"></span>🧬 writing a new skill for “${escapeHtml(event.intent)}”…`;
                    } else if (event.status === "ok") {
                        usedChips.push({ kind: "meta", text: "new skill learned" });
                        refreshSidebar();
                    } else {
                        usedChips.push({ kind: "error", text: "skill generation failed" });
                    }
                    break;
                case "final":
                    statusEl.remove();
                    finalText = event.text || "";
                    assistantEl = addMessage("assistant", renderMarkdown(finalText));
                    if (usedChips.length) addChipRow(assistantEl, usedChips);
                    break;
            }
        }

        setBusy(false);
        refreshSidebar();
    }

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    clearBtn.addEventListener("click", async () => {
        if (!sessionId) return;
        await fetch(`/history/${sessionId}`, { method: "DELETE" }).catch(() => {});
        localStorage.removeItem("synapse_session");
        sessionId = null;
        chatArea.innerHTML = "";
        addMessage("assistant", "Memory cleared. Fresh start!");
    });
    menuBtn.addEventListener("click", () => sidebar.classList.toggle("collapsed"));

    if (sessionId) sessionIdEl.textContent = `session ${sessionId.slice(0, 8)}`;
    refreshSidebar();
})();
