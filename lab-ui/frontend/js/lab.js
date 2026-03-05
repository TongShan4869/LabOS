/**
 * LabOS — Stardew-style research lab UI
 * Click agents to talk. Dialogue box slides up. Typewriter text.
 */

// ── Agent definitions (mirrors backend AGENTS dict) ──────────────────────────

const AGENTS = {
  main: {
    id: "main", name: "醋の虾", role: "Principal Investigator",
    emoji: "🦞", zone: "pi-desk", color: "#e63946",
    greeting: "Hey! What are you working on today?",
    pos: { left: "72%", top: "33%" },  // PI desk — in front of desk
  },
  scout: {
    id: "scout", name: "Scout", role: "Literature Search",
    emoji: "🔬", zone: "bookshelf", color: "#2a9d8f",
    greeting: "Need me to dig into the literature? Just give me a query.",
    pos: { left: "13%", top: "35%" },  // Bookshelf — right of shelf
  },
  stat: {
    id: "stat", name: "Stat", role: "Biostatistician",
    emoji: "📊", zone: "bench", color: "#457b9d",
    greeting: "Got data to analyze? I'll run the numbers and show my work.",
    pos: { left: "28%", top: "32%" },  // Analysis bench — microscope + computer
  },
  quill: {
    id: "quill", name: "Quill", role: "Writing Assistant",
    emoji: "✍️", zone: "desk", color: "#e9c46a",
    greeting: "Ready to draft something? Tell me the section and project.",
    pos: { left: "60%", top: "33%" },  // Writing desk — lamp + papers
  },
  sage: {
    id: "sage", name: "Sage", role: "Research Advisor",
    emoji: "🎓", zone: "advisor-chair", color: "#6d6875",
    greeting: "Let's talk about your research. What's the current hypothesis?",
    pos: { left: "14%", top: "72%" },  // Armchairs — sitting near sofa
  },
  critic: {
    id: "critic", name: "Critic", role: "Peer Reviewer",
    emoji: "🤺", zone: "review-table", color: "#e76f51",
    greeting: "Drop your draft. I'll tear it apart so reviewers don't have to.",
    pos: { left: "42%", top: "65%" },  // Review table — red-pen papers center
  },
  trend: {
    id: "trend", name: "Trend", role: "Field Monitor",
    emoji: "📰", zone: "news-board", color: "#52b788",
    greeting: "I monitor your field 24/7. Want the latest digest?",
    pos: { left: "51%", top: "18%" },  // Cork board — under TREVIRS
  },
  warden: {
    id: "warden", name: "Warden", role: "Security",
    emoji: "🔒", zone: "security-console", color: "#555577",
    greeting: "Everything looks secure. Want me to run an audit?",
    pos: { left: "78%", top: "65%" },  // Security console — green monitors bottom right
  },
};

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  activeAgent:    null,
  typewriterTimer: null,
  checkpointAgent: null,
  isTyping:       false,
  waitingReply:   false,
  socket:         null,
  reports:        [],  // stored report outputs
  pendingNotifs:  {},  // agent_id → {text, ts}
};

// ── DOM refs ──────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);
const scene          = $("lab-scene");
const dlgOverlay     = $("dialogue-overlay");
const dlgText        = $("dialogue-text");
const dlgCursor      = $("dialogue-cursor");
const dlgAvatar      = $("dialogue-avatar");
const dlgNameTag     = $("dialogue-name-tag");
const dlgInput       = $("dialogue-input");
const dlgSend        = $("dialogue-send");
const dlgClose       = $("dialogue-close");
const reportOverlay  = $("report-overlay");
const reportEmoji    = $("report-emoji");
const reportName     = $("report-agent-name");
const reportTs       = $("report-timestamp");
const reportBody     = $("report-body");
const reportClose    = $("report-close");
const hudReports     = $("hud-reports");
const hudReportsCount = $("hud-reports-count");
const dlgHistory     = $("dialogue-history");
const hudLevel       = $("hud-level");
const hudXp          = $("hud-xp");
const xpBar          = $("xp-bar");
const hudTime        = $("hud-time");
const hudDate        = $("hud-date");
const toastContainer = $("toast-container");

// ── Build agent sprites ───────────────────────────────────────────────────────

function buildAgentSprites() {
  for (const [id, agent] of Object.entries(AGENTS)) {
    const el = document.createElement("div");
    el.className = "agent-sprite";
    el.id = `agent-${id}`;
    el.style.left = agent.pos.left;
    el.style.top  = agent.pos.top;
    el.title = `${agent.name} — ${agent.role}`;

    el.innerHTML = `
      <div class="agent-status-bubble" id="bubble-${id}"></div>
      <div class="agent-name">${agent.name}</div>
      <div class="agent-sprite-img" id="sprite-img-${id}"
           style="width:96px;height:144px;background-image:url('assets/sprites/sprite-${id}.png');background-repeat:no-repeat;background-size:384px 144px;background-position:0 0;image-rendering:auto;"
           data-frame="0">
      </div>
    `;

    // Start idle animation
    let frame = 0;
    const spriteEl = el.querySelector('.agent-sprite-img');
    setInterval(() => {
      frame = (frame + 1) % 4;
      spriteEl.style.backgroundPositionX = `${-frame * 96}px`;
    }, 400);

    el.addEventListener("click", () => openDialogue(id));
    scene.appendChild(el);
  }
}

// ── Typewriter effect ─────────────────────────────────────────────────────────

function typewrite(text, onDone) {
  clearTimeout(state.typewriterTimer);
  state.isTyping = true;
  dlgText.textContent = "";
  dlgCursor.style.display = "block";

  let i = 0;
  const chars = Array.from(text); // handle emoji properly
  const speed = 22; // ms per character

  function tick() {
    if (i < chars.length) {
      dlgText.textContent += chars[i++];
      state.typewriterTimer = setTimeout(tick, speed);
    } else {
      state.isTyping = false;
      if (onDone) onDone();
    }
  }
  tick();
}

function skipTypewriter() {
  if (state.isTyping) {
    clearTimeout(state.typewriterTimer);
    state.isTyping = false;
    // Show full text immediately
    const agent = AGENTS[state.activeAgent];
    // (text is already partially shown; clicking advances)
  }
}

// ── Open dialogue ─────────────────────────────────────────────────────────────

function openDialogue(agentId) {
  const agent = AGENTS[agentId];
  if (!agent) return;

  state.activeAgent = agentId;

  // Clear notification badge if any
  clearAgentNotification(agentId);

  // If this agent has a pending checkpoint, restore checkpoint mode
  if (state.checkpointAgent === agentId) {
    setTimeout(() => {
      dlgInput.placeholder = "Reply to checkpoint...";
      dlgInput.disabled = false;
      dlgInput.focus();
    }, 100);
  }

  // Set portrait — PNG avatar with emoji fallback
  dlgAvatar.style.borderColor = agent.color;
  dlgAvatar.innerHTML = "";
  const avatarImg = new Image();
  avatarImg.src = "assets/avatars/avatar-" + agentId + ".png";
  avatarImg.alt = agent.name;
  avatarImg.style.cssText = "width:100%;height:100%;object-fit:contain;image-rendering:pixelated;border-radius:2px";
  avatarImg.onerror = function() { dlgAvatar.textContent = agent.emoji; };
  dlgAvatar.appendChild(avatarImg);
  dlgNameTag.textContent = agent.name;
  dlgNameTag.style.background = agent.color;
  dlgNameTag.style.color = "#fff";

  // Load history
  renderHistory(agentId);

  // Greeting
  dlgOverlay.classList.remove("hidden");
  dlgInput.disabled   = false;
  dlgInput.value      = "";
  // Don't reset waitingReply — agent may still be processing

  // Play greeting or last message
  const history = getLocalHistory(agentId);
  const lastAgentMsg = [...history].reverse().find(m => m.role === "agent");
  const greetText = lastAgentMsg
    ? `[${agent.name}]: ${lastAgentMsg.text}`
    : agent.greeting;

  typewrite(greetText, () => {
    dlgInput.focus();
  });

  // Scroll history to bottom
  setTimeout(() => { dlgHistory.scrollTop = dlgHistory.scrollHeight; }, 50);
}

function closeDialogue() {
  dlgOverlay.classList.remove("shifted");
  dlgOverlay.classList.add("hidden");
  clearTimeout(state.typewriterTimer);
  state.activeAgent   = null;
  // Don't reset waitingReply — agent may still be processing in background
}

// ── Send message ──────────────────────────────────────────────────────────────

function sendMessage() {
  const text = dlgInput.value.trim();
  if (!text || !state.activeAgent) return;

  const agentId = state.activeAgent;
  dlgInput.value = "";

  if (state.checkpointAgent === agentId) {
    // Checkpoint reply — feed to running skill's stdin
    appendLocalHistory(agentId, "user", text);
    renderHistory(agentId);
    dlgInput.disabled = true;
    dlgInput.placeholder = "Type a message...";
    state.socket.emit("checkpoint_reply", { agent_id: agentId, text });
    state.checkpointAgent = null;
    state.waitingReply = true;
    typewrite(`${AGENTS[agentId].name} is processing your reply...`);
    return;
  }

  // Don't allow new messages while agent is working (unless it's a checkpoint)
  if (state.waitingReply) return;
  state.waitingReply = true;

  appendLocalHistory(agentId, "user", text);
  renderHistory(agentId);
  typewrite(`${AGENTS[agentId].name} is thinking...`);
  state.socket.emit("send_message", { agent_id: agentId, text });
}

// ── Handle agent reply ────────────────────────────────────────────────────────

function handleAgentReply(data) {
  const { agent_id, text, ts } = data;

  appendLocalHistory(agent_id, "agent", text, ts);
  state.waitingReply = false;

  const LONG_THRESHOLD = 200;
  const isLong = text.length > LONG_THRESHOLD;

  // Store report if long
  if (isLong) {
    storeReport(agent_id, text, ts);
  }

  if (state.activeAgent === agent_id) {
    // Dialogue is open for this agent
    if (isLong) {
      openReportPanel(agent_id, text, ts);
      dlgOverlay.classList.add("shifted");
      const summary = text.split("\n").filter(l => l.trim()).slice(0, 2).join(" ").slice(0, 100);
      typewrite(`📋 Report ready — see panel →`, () => {
        dlgInput.disabled = false;
        dlgInput.focus();
      });
    } else {
      renderHistory(agent_id);
      typewrite(text, () => {
        dlgInput.disabled = false;
        dlgInput.focus();
      });
    }
  } else {
    // Agent not in focus — show notification on sprite
    addAgentNotification(agent_id, text, ts);
    const agent = AGENTS[agent_id];
    const label = isLong ? "📋 Report ready" : text.slice(0, 60);
    showToast(`${agent.emoji} ${agent.name}: ${label}`);
  }
}

function handleCheckpoint(data) {
  const { agent_id, agent_name, prompt, ts } = data;

  appendLocalHistory(agent_id, "agent", `🔀 ${prompt}`, ts);

  // ALWAYS set checkpointAgent — even if dialogue is closed
  state.checkpointAgent = agent_id;
  state.waitingReply = false;  // Allow input

  if (state.activeAgent === agent_id) {
    renderHistory(agent_id);
    typewrite(`🔀 ${prompt}`, () => {
      dlgInput.disabled = false;
      dlgInput.placeholder = "Reply to checkpoint...";
      dlgInput.focus();
    });
  } else {
    // Show notification — user needs to click the agent
    addAgentNotification(agent_id, `🔀 ${prompt}`, ts);
    const agent = AGENTS[agent_id];
    showToast(`${agent.emoji} ${agent_name} needs your input!`);
  }
}

// ── Local history (session storage) ──────────────────────────────────────────

function getLocalHistory(agentId) {
  try {
    return JSON.parse(sessionStorage.getItem(`history-${agentId}`) || "[]");
  } catch { return []; }
}

function appendLocalHistory(agentId, role, text, ts) {
  const hist = getLocalHistory(agentId);
  hist.push({ role, text, ts: ts || new Date().toLocaleTimeString("en", {hour:"2-digit",minute:"2-digit"}) });
  // Keep last 40 messages
  if (hist.length > 40) hist.splice(0, hist.length - 40);
  sessionStorage.setItem(`history-${agentId}`, JSON.stringify(hist));
}

function renderHistory(agentId) {
  const hist = getLocalHistory(agentId);
  dlgHistory.innerHTML = "";
  const agent = AGENTS[agentId];
  for (const msg of hist) {
    const div = document.createElement("div");
    div.className = `history-msg ${msg.role}`;
    const who = msg.role === "user" ? "You" : agent.name;
    div.innerHTML = `<span class="msg-who">${who} [${msg.ts}]</span>${escapeHtml(msg.text)}`;
    dlgHistory.appendChild(div);
  }
  dlgHistory.scrollTop = dlgHistory.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── HUD updates ───────────────────────────────────────────────────────────────

function updateHud(status) {
  const xp = status.xp || {};
  const total = xp.xp || 0;
  const title = xp.level_title || "Confused First-Year";

  hudLevel.textContent = `Lv${xp.level || 1} — ${title}`;
  hudXp.textContent    = `${total} XP`;

  // XP bar fill — approximate next threshold
  const thresholds = [0,300,800,2000,4000,7500,12000,20000,30000,45000];
  const lvl = (xp.level || 1) - 1;
  const lo  = thresholds[lvl] || 0;
  const hi  = thresholds[lvl + 1] || lo + 500;
  const pct = Math.min(100, Math.round(((total - lo) / (hi - lo)) * 100));
  xpBar.style.width = `${pct}%`;

  hudTime.textContent = status.time || "--:--";
  hudDate.textContent = status.date || "";
}

// ── Agent status bubbles ──────────────────────────────────────────────────────

function updateAgentStatus(agentId, status, detail) {
  const sprite = document.getElementById(`agent-${agentId}`);
  const bubble = document.getElementById(`bubble-${agentId}`);
  if (!sprite || !bubble) return;

  if (status === "working" || status === "researching" || status === "executing") {
    sprite.classList.add("working");
    bubble.textContent = detail ? detail.slice(0, 30) + (detail.length > 30 ? "…" : "") : "working…";
  } else {
    sprite.classList.remove("working");
    bubble.textContent = "";
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectSocket() {
  const origin = window.location.origin;
  const socket = io(origin, { transports: ["websocket", "polling"] });
  state.socket = socket;

  socket.on("connect", () => {
    console.log("🔬 LabOS connected");
  });

  socket.on("lab_status", (data) => {
    updateHud(data);
    if (data.agents) {
      for (const [id, agentData] of Object.entries(data.agents)) {
        updateAgentStatus(id, agentData.status, agentData.detail);
      }
    }
  });

  socket.on("agent_reply", (data) => {
    handleAgentReply(data);
  });

  socket.on("checkpoint", (data) => {
    handleCheckpoint(data);
  });

  socket.on("agent_status", (data) => {
    updateAgentStatus(data.agent_id, data.status, data.detail);
  });

  socket.on("message_echo", (data) => {
    // User message confirmed by server — already handled locally
  });

  socket.on("disconnect", () => {
    showToast("⚠️ Disconnected from lab server");
  });

  socket.on("connect_error", () => {
    showToast("⚠️ Cannot reach lab server");
  });
}


// ── Notifications on agent sprites ────────────────────────────────────────────

function addAgentNotification(agentId, text, ts) {
  const spriteEl = document.getElementById(`agent-${agentId}`);
  if (!spriteEl) return;

  // Remove existing notification
  const existing = spriteEl.querySelector(".agent-notification");
  if (existing) existing.remove();

  const badge = document.createElement("div");
  badge.className = "agent-notification";
  badge.textContent = "!";
  badge.title = "New message — click to view";
  spriteEl.appendChild(badge);

  // Store pending notification
  state.pendingNotifs[agentId] = { text, ts };
}

function clearAgentNotification(agentId) {
  const spriteEl = document.getElementById(`agent-${agentId}`);
  if (!spriteEl) return;
  const badge = spriteEl.querySelector(".agent-notification");
  if (badge) badge.remove();
  delete state.pendingNotifs[agentId];
}

// ── Report storage ────────────────────────────────────────────────────────────

function storeReport(agentId, text, ts) {
  const agent = AGENTS[agentId];
  state.reports.push({
    agentId,
    agentName: agent.name,
    emoji: agent.emoji,
    text,
    ts: ts || new Date().toLocaleTimeString("en", {hour:"2-digit", minute:"2-digit"}),
    time: Date.now(),
  });
  updateReportsButton();
}

function updateReportsButton() {
  if (state.reports.length > 0) {
    hudReports.classList.remove("hidden");
    hudReportsCount.textContent = state.reports.length;
  } else {
    hudReports.classList.add("hidden");
  }
}

// Reports list dropdown
let reportsListEl = null;

function toggleReportsList() {
  if (reportsListEl && reportsListEl.classList.contains("open")) {
    reportsListEl.classList.remove("open");
    return;
  }

  if (!reportsListEl) {
    reportsListEl = document.createElement("div");
    reportsListEl.id = "reports-list";
    document.body.appendChild(reportsListEl);
  }

  let html = '<div class="reports-list-header">📋 Session Reports</div>';
  for (let i = state.reports.length - 1; i >= 0; i--) {
    const r = state.reports[i];
    html += `<div class="report-list-item" data-idx="${i}">
      <span class="rli-emoji">${r.emoji}</span>${r.agentName}
      <span class="rli-time">${r.ts}</span>
    </div>`;
  }

  reportsListEl.innerHTML = html;
  reportsListEl.classList.add("open");

  // Click handlers
  reportsListEl.querySelectorAll(".report-list-item").forEach(el => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.idx);
      const r = state.reports[idx];
      openReportPanel(r.agentId, r.text, r.ts);
      reportsListEl.classList.remove("open");
    });
  });

  // Close on outside click
  setTimeout(() => {
    document.addEventListener("click", function closeList(e) {
      if (!reportsListEl.contains(e.target) && e.target !== hudReports) {
        reportsListEl.classList.remove("open");
        document.removeEventListener("click", closeList);
      }
    });
  }, 10);
}

hudReports.addEventListener("click", toggleReportsList);

// ── Report panel ──────────────────────────────────────────────────────────────

function openReportPanel(agentId, text, ts) {
  const agent = AGENTS[agentId];
  reportEmoji.textContent = agent.emoji;
  reportName.textContent = agent.name + " — " + agent.role;
  reportTs.textContent = ts || new Date().toLocaleTimeString("en", {hour:"2-digit", minute:"2-digit"});
  reportBody.innerHTML = formatReport(text);
  reportOverlay.classList.remove("hidden");
}

function closeReportPanel() {
  reportOverlay.classList.add("hidden");
  dlgOverlay.classList.remove("shifted");
}

function formatReport(text) {
  // Parse the output into structured HTML
  const lines = text.split("\n");
  let html = "";
  let inPaper = false;
  let paperHtml = "";

  for (const line of lines) {
    const trimmed = line.trim();

    // Section headers (═══ lines or lines with lots of ═)
    if (trimmed.includes("════") || trimmed.includes("────")) {
      if (inPaper) { html += paperHtml + "</div>"; inPaper = false; paperHtml = ""; }
      continue;
    }

    // Title lines (centered, with emoji)
    if (trimmed.startsWith("🔍") || trimmed.startsWith("📋") || trimmed.startsWith("🤖") ||
        trimmed.startsWith("📊") || trimmed.startsWith("✍️") || trimmed.startsWith("🎓")) {
      if (inPaper) { html += paperHtml + "</div>"; inPaper = false; paperHtml = ""; }
      html += `<div class="report-header-line">${escHtml(trimmed)}</div>`;
      continue;
    }

    // Paper entries (numbered: "1. [72%] Title...")
    const paperMatch = trimmed.match(/^(\d+)\.\s*\[\s*(\d+)%\]\s*(.+)/);
    if (paperMatch) {
      if (inPaper) { html += paperHtml + "</div>"; }
      inPaper = true;
      paperHtml = `<div class="report-paper">`;
      paperHtml += `<div class="report-paper-title">${paperMatch[1]}. ${escHtml(paperMatch[3])}</div>`;
      paperHtml += `<span class="report-stat">Relevance: ${paperMatch[2]}%</span>`;
      continue;
    }

    // Progress lines (🔬 Searching..., 📖 Searching...)
    if (trimmed.startsWith("🔬") || trimmed.startsWith("📖") || trimmed.startsWith("📄") ||
        trimmed.startsWith("🔀") || trimmed.startsWith("🤖")) {
      if (inPaper) { html += paperHtml + "</div>"; inPaper = false; paperHtml = ""; }
      html += `<div class="report-progress">${escHtml(trimmed)}</div>`;
      continue;
    }

    // Summary text inside a paper
    if (inPaper) {
      if (trimmed.startsWith("Summary:") || trimmed.startsWith("→")) {
        paperHtml += `<div class="report-paper-summary">${escHtml(trimmed)}</div>`;
      } else if (trimmed.startsWith("Authors:") || trimmed.startsWith("Year:") ||
                 trimmed.startsWith("Source:") || trimmed.startsWith("Citations:") ||
                 trimmed.startsWith("DOI:") || trimmed.startsWith("PMID:")) {
        paperHtml += `<div class="report-paper-meta">${escHtml(trimmed)}</div>`;
      } else if (trimmed) {
        paperHtml += `<div>${escHtml(trimmed)}</div>`;
      }
      continue;
    }

    // Default: plain text line
    if (trimmed) {
      html += `<div>${escHtml(trimmed)}</div>`;
    }
  }

  if (inPaper) { html += paperHtml + "</div>"; }

  return html || `<div>${escHtml(text)}</div>`;
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

reportClose.addEventListener("click", closeReportPanel);

// Click outside report to close
reportOverlay.addEventListener("click", (e) => {
  if (e.target === reportOverlay) closeReportPanel();
});

// ── Clock ─────────────────────────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  hudTime.textContent = now.toLocaleTimeString("en", {hour:"2-digit", minute:"2-digit"});
  hudDate.textContent = now.toLocaleDateString("en", {weekday:"short", month:"short", day:"numeric"});
}

// ── Event listeners ───────────────────────────────────────────────────────────

dlgSend.addEventListener("click", sendMessage);

dlgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
  if (e.key === "Escape") closeDialogue();
});

dlgClose.addEventListener("click", closeDialogue);

// Click dialogue text area to skip typewriter
dlgText.addEventListener("click", skipTypewriter);

// Click outside dialogue to close
dlgOverlay.addEventListener("click", (e) => {
  if (e.target === dlgOverlay) closeDialogue();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDialogue();
});

// ── Init ──────────────────────────────────────────────────────────────────────

function init() {
  buildAgentSprites();
  connectSocket();
  updateClock();
  setInterval(updateClock, 10000);

  // Initial status fetch
  fetch("/api/status")
    .then(r => r.json())
    .then(data => updateHud(data))
    .catch(() => {});

  // Keyboard shortcut hints
  showToast("🔬 LabOS ready! Click an agent to talk.");
}

document.addEventListener("DOMContentLoaded", init);
