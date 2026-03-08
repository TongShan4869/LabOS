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

    // Sprite animation system
    const spriteEl = el.querySelector('.agent-sprite-img');
    const agentAnim = {
      el: spriteEl,
      mode: 'idle',        // idle | clicked | working
      frameIdx: 0,
      timer: null
    };

    // Different idle speeds per agent (ms) — staggered so they don't sync
    const idleSpeeds = {
      scout: 700, stat: 850, quill: 600, sage: 1000,
      critic: 750, trend: 550, warden: 900, main: 800
    };

    const frameSequences = {
      idle:    [0, 2],      // frames 1 & 3: gentle breathing/sway
      clicked: [0, 1],      // frames 1 & 2: excited jump
      working: [0, 2, 3]    // frames 1, 3, 4: active thinking
    };

    function animateAgent() {
      const seq = frameSequences[agentAnim.mode] || frameSequences.idle;
      agentAnim.frameIdx = (agentAnim.frameIdx + 1) % seq.length;
      const frame = seq[agentAnim.frameIdx];
      agentAnim.el.style.backgroundPositionX = `${-frame * 96}px`;
    }

    // Start with random offset so agents don't all tick together
    const speed = idleSpeeds[id] || 700;
    setTimeout(() => {
      agentAnim.timer = setInterval(animateAgent, speed);
    }, Math.random() * speed);

    // Store animation state on the element for external control
    el._anim = agentAnim;
    el._animSpeeds = idleSpeeds;
    el._animSeqs = frameSequences;

    el.addEventListener("click", () => {
      // Switch to clicked animation briefly
      setAgentAnimMode(id, 'clicked', 300);
      openDialogue(id);
    });
    scene.appendChild(el);
  }
}

// ── Typewriter effect ─────────────────────────────────────────────────────────

function typewrite(text, onDone) {
  clearTimeout(state.typewriterTimer);
  
  // Split long text into pages (~4 lines worth, ~280 chars)
  const PAGE_SIZE = 280;
  const pages = [];
  const lines = text.split('\n');
  let currentPage = '';
  
  for (const line of lines) {
    if (currentPage.length + line.length + 1 > PAGE_SIZE && currentPage.length > 0) {
      pages.push(currentPage.trim());
      currentPage = line;
    } else {
      currentPage += (currentPage ? '\n' : '') + line;
    }
  }
  if (currentPage.trim()) pages.push(currentPage.trim());
  
  // If only one page, no pagination needed
  if (pages.length <= 1) {
    _typewritePage(text, onDone);
    return;
  }
  
  // Store pages for pagination
  state.pages = pages;
  state.currentPage = 0;
  state.pagesDone = onDone;
  _typewritePage(pages[0], () => {
    // Show ▼ cursor to indicate more pages
    dlgCursor.style.display = "block";
    dlgCursor.textContent = `▼ ${state.currentPage + 1}/${pages.length}`;
    dlgCursor.classList.add("page-prompt");
  });
}

function _typewritePage(text, onDone) {
  state.isTyping = true;
  dlgText.textContent = "";
  dlgCursor.style.display = "block";
  dlgCursor.textContent = "▼";
  dlgCursor.classList.remove("page-prompt");

  let i = 0;
  const chars = Array.from(text);
  const speed = 18;

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

function advancePage() {
  if (!state.pages || state.pages.length === 0) return false;
  
  state.currentPage++;
  if (state.currentPage < state.pages.length) {
    _typewritePage(state.pages[state.currentPage], () => {
      if (state.currentPage < state.pages.length - 1) {
        dlgCursor.style.display = "block";
        dlgCursor.textContent = `▼ ${state.currentPage + 1}/${state.pages.length}`;
        dlgCursor.classList.add("page-prompt");
      } else {
        // Last page done
        dlgCursor.style.display = "none";
        state.pages = null;
        if (state.pagesDone) state.pagesDone();
      }
    });
    return true;
  }
  state.pages = null;
  return false;
}

function skipTypewriter() {
  if (state.isTyping) {
    // Skip to end of current page
    clearTimeout(state.typewriterTimer);
    state.isTyping = false;
    if (state.pages && state.currentPage < state.pages.length) {
      dlgText.textContent = state.pages[state.currentPage];
      if (state.currentPage < state.pages.length - 1) {
        dlgCursor.textContent = `▼ ${state.currentPage + 1}/${state.pages.length}`;
        dlgCursor.classList.add("page-prompt");
      } else {
        dlgCursor.style.display = "none";
        state.pages = null;
        if (state.pagesDone) state.pagesDone();
      }
    }
    return;
  }
  // Not typing — try to advance page
  if (state.pages && advancePage()) return;
}

// ── Open dialogue ─────────────────────────────────────────────────────────────


// ── Agent animation mode control ──────────────────────────────────────────────

function setAgentAnimMode(agentId, mode, revertMs) {
  const el = document.getElementById(`agent-${agentId}`);
  if (!el || !el._anim) return;
  const anim = el._anim;
  const prevMode = anim.mode;
  if (anim.timer) clearInterval(anim.timer);
  anim.mode = mode;
  anim.frameIdx = 0;
  const speeds = { idle: el._animSpeeds[agentId] || 700, clicked: 150, working: 500 };
  const speed = speeds[mode] || 700;
  const seqs = el._animSeqs;
  anim.timer = setInterval(() => {
    const seq = seqs[mode] || seqs.idle;
    anim.frameIdx = (anim.frameIdx + 1) % seq.length;
    anim.el.style.backgroundPositionX = `${-seq[anim.frameIdx] * 96}px`;
  }, speed);
  if (revertMs) {
    setTimeout(() => setAgentAnimMode(agentId, prevMode), revertMs);
  }
}

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

  const LONG_THRESHOLD = 1500;
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
    addToChatLog(who, msg.text);
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

  // XP bar fill — use backend-calculated values
  const inLevel = xp.xp_in_level || 0;
  const toNext = xp.xp_to_next || 150;
  const pct = Math.min(100, Math.round((inLevel / toNext) * 100));
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
    setAgentAnimMode(agentId, "working");
    bubble.textContent = detail ? detail.slice(0, 30) + (detail.length > 30 ? "…" : "") : "working…";
  } else {
    sprite.classList.remove("working");
    setAgentAnimMode(agentId, "idle");
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
  dlgOverlay.classList.add("shifted");
}

function closeReportPanel() {
  reportOverlay.classList.add("hidden");
  dlgOverlay.classList.remove("shifted");
}

function formatReport(text) {
  // Render markdown if marked.js is available
  if (typeof marked !== 'undefined') {
    return marked.parse(text);
  }
  // Fallback: basic formatting
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
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
dlgCursor.addEventListener("click", skipTypewriter);



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

// ── Onboarding & Loading Logic ────────────────────────────────────────────

function checkOnboardingNeeded() {
  // Check backend first — if config exists, skip onboarding regardless of localStorage
  fetch('/api/config')
    .then(r => r.json())
    .then(data => {
      if (data.lab_name) {
        // Config exists — skip onboarding, update HUD
        localStorage.setItem('labos_onboarding_complete', 'true');
        $('hud-title').textContent = `${data.lab_name} — LabOS`;
      } else if (!localStorage.getItem('labos_onboarding_complete')) {
        showOnboarding();
      }
    })
    .catch(() => {
      if (!localStorage.getItem('labos_onboarding_complete')) {
        showOnboarding();
      }
    });
}

function showOnboarding() {
  $('onboarding-overlay').classList.remove('hidden');
  $('onboard-step-1').classList.remove('hidden');
}

function nextOnboardStep(step) {
  // Hide all steps
  for (let i = 1; i <= 5; i++) {
    $(`onboard-step-${i}`).classList.add('hidden');
  }
  // Show target step
  $(`onboard-step-${step}`).classList.remove('hidden');
}

function finishOnboarding() {
  const labName = $('onboard-lab-name').value.trim() || 'My Lab';
  const obsidianPath = $('onboard-obsidian').checked ? $('onboard-obsidian-path').value.trim() : '';
  const notionDb = $('onboard-notion').checked ? $('onboard-notion-db').value.trim() : '';
  const zotero = $('onboard-zotero').checked;
  const projectName = $('onboard-project-name').value.trim() || 'First Project';
  const projectField = $('onboard-project-field').value.trim() || 'Research';

  // Show finalizing step
  nextOnboardStep(5);

  // Send to backend
  fetch('/api/init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lab_name: labName,
      obsidian_path: obsidianPath,
      notion_db: notionDb,
      zotero: zotero,
      project_name: projectName,
      field: projectField,
    })
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) {
      localStorage.setItem('labos_onboarding_complete', 'true');
      // Hide onboarding, show loading screen
      setTimeout(() => {
        $('onboarding-overlay').classList.add('hidden');
        showLoadingScreen(labName);
      }, 1000);
    } else {
      alert('Failed to initialize lab. Please try again.');
      nextOnboardStep(1);
    }
  })
  .catch(err => {
    console.error('Onboarding error:', err);
    alert('Network error. Please check the server.');
    nextOnboardStep(1);
  });
}

function showLoadingScreen(labName) {
  const loadingScreen = $('loading-screen');
  const loadingBar = $('loading-bar');
  const loadingMessage = $('loading-message');

  const messages = [
    "Calibrating microscopes...",
    "Brewing coffee for agents...",
    "Loading research papers...",
    "Waking up the lab crew...",
    "Organizing the bench...",
    "Updating citations...",
    "Almost there...",
  ];

  loadingScreen.classList.remove('hidden');
  
  let progress = 0;
  let msgIndex = 0;
  
  const interval = setInterval(() => {
    progress += Math.random() * 15 + 5; // 5-20% increments
    if (progress > 100) progress = 100;
    
    loadingBar.style.width = progress + '%';
    
    if (msgIndex < messages.length - 1 && progress > (msgIndex + 1) * (100 / messages.length)) {
      msgIndex++;
      loadingMessage.textContent = messages[msgIndex];
    }
    
    if (progress >= 100) {
      clearInterval(interval);
      setTimeout(() => {
        loadingScreen.classList.add('hidden');
        $('hud-title').textContent = `${labName} — LabOS`;
      }, 500);
    }
  }, 200);
}

// ── XP Info Modal ──────────────────────────────────────────────────────────

function showXpModal() {
  const overlay = $('xp-modal-overlay');
  overlay.classList.remove('hidden');
  
  // Load XP data from state
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      const xp = data.xp || { xp: 0, level: 1, level_title: 'Confused First-Year', badges: [] };
      
      $('xp-current-level').textContent = xp.level;
      $('xp-current-title').textContent = xp.level_title;
      $('xp-current').textContent = xp.xp_in_level || xp.xp;
      
      const nextLevelXp = xp.xp_to_next || (xp.level * 150);
      $('xp-next-level').textContent = nextLevelXp;
      
      const inLevel = xp.xp_in_level || xp.xp;
      const progress = Math.min((inLevel / nextLevelXp) * 100, 100);
      $('xp-modal-bar').style.width = progress + '%';
      
      // Show all level titles
      const levelsEl = $('xp-levels-list');
      if (levelsEl && xp.levels) {
        levelsEl.innerHTML = Object.entries(xp.levels)
          .sort(([a], [b]) => Number(a) - Number(b))
          .map(([lvl, title]) => {
            const current = Number(lvl) === xp.level;
            return `<div class="xp-level-row ${current ? 'xp-level-current' : ''} ${Number(lvl) < xp.level ? 'xp-level-past' : ''}">` +
              `Level ${lvl}: ${title}</div>`;
          }).join('');
      }
      
      // Update badges
      const badgesContainer = $('xp-badges');
      badgesContainer.innerHTML = '';
      if (xp.badges && xp.badges.length > 0) {
        xp.badges.forEach(badge => {
          const el = document.createElement('span');
          el.className = 'xp-badge';
          el.textContent = badge;
          badgesContainer.appendChild(el);
        });
      } else {
        badgesContainer.innerHTML = '<span class="xp-badge">🎯 First Steps</span>';
      }
      // Populate recent XP history
      const histEl = $('xp-history');
      if (histEl && xp.history && xp.history.length > 0) {
        histEl.innerHTML = xp.history.slice(-10).reverse()
          .map(h => `<div class="xp-history-item">+${h.xp} XP — ${h.event}</div>`)
          .join('');
      }
    })
    .catch(err => console.error('Failed to load XP data:', err));
}

function closeXpModal() {
  $('xp-modal-overlay').classList.add('hidden');
}

// ── Event Listeners ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Check if onboarding needed
  checkOnboardingNeeded();
  
  // XP modal listeners
  $('hud-left').addEventListener('click', showXpModal);
  $('xp-modal-close').addEventListener('click', closeXpModal);
  $('xp-modal-overlay').addEventListener('click', (e) => {
    if (e.target === $('xp-modal-overlay')) {
      closeXpModal();
    }
  });
});

// ─── Filing Cabinet ─────────────────────────────────────────────────────────

const filingState = { open: false, memoryType: null, activeProjectId: null };

// ─── Chat Log Panel ─────────────────────────────────────────────────────────

const chatLogMessages = [];

function openChatLog() {
  const overlay = $('chatlog-overlay');
  const msgs = $('chatlog-messages');
  overlay.classList.remove('hidden');
  msgs.innerHTML = chatLogMessages.length === 0
    ? '<div class="filing-empty">No messages yet. Talk to an agent!</div>'
    : chatLogMessages.map(m =>
        `<div class="chatlog-msg"><span class="chatlog-who">${m.who}</span> <span class="chatlog-time">${m.ts}</span><br>${m.text}</div>`
      ).join('');
  msgs.scrollTop = msgs.scrollHeight;
}

function closeChatLog() {
  $('chatlog-overlay').classList.add('hidden');
}

function addToChatLog(who, text) {
  chatLogMessages.push({ who, text, ts: new Date().toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit'}) });
}

$('hud-chatlog')?.addEventListener('click', openChatLog);
$('chatlog-close')?.addEventListener('click', closeChatLog);
$('chatlog-overlay')?.addEventListener('click', (e) => {
  if (e.target.id === 'chatlog-overlay') closeChatLog();
});

function initFilingCabinet() {
  const el = (id) => document.getElementById(id);
  
  el('hud-filing')?.addEventListener('click', showFilingCabinet);
  el('filing-close')?.addEventListener('click', closeFilingCabinet);
  el('filing-overlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'filing-overlay') closeFilingCabinet();
  });

  document.querySelectorAll('.filing-tab').forEach(btn => {
    btn.addEventListener('click', () => switchFilingTab(btn.dataset.tab));
  });

  el('new-project-btn')?.addEventListener('click', showNewProjectModal);
  el('new-project-cancel')?.addEventListener('click', closeNewProjectModal);
  el('new-project-confirm')?.addEventListener('click', createNewProject);

  document.querySelectorAll('.add-memory-btn').forEach(btn => {
    btn.addEventListener('click', () => showAddMemoryModal(btn.dataset.type));
  });
  el('memory-note-cancel')?.addEventListener('click', closeAddMemoryModal);
  el('memory-note-confirm')?.addEventListener('click', saveMemoryNote);

  el('memory-agent-select')?.addEventListener('change', (e) => {
    loadAgentMemory(e.target.value);
  });
}

function showFilingCabinet() {
  const overlay = document.getElementById('filing-overlay');
  overlay.classList.remove('hidden');
  overlay.style.display = 'flex';
  filingState.open = true;
  // Always fetch active project first
  fetch('/api/projects')
    .then(r => r.json())
    .then(data => {
      filingState.activeProjectId = data.active_project_id;
      // Load whichever tab is active
      const activeTab = document.querySelector('.filing-tab.active');
      const tabName = activeTab ? activeTab.dataset.tab : 'projects';
      switchFilingTab(tabName);
    })
    .catch(() => loadProjects());
}

function closeFilingCabinet() {
  const overlay = document.getElementById('filing-overlay');
  if (overlay) { overlay.classList.add('hidden'); filingState.open = false; }
}

function switchFilingTab(tabName) {
  document.querySelectorAll('.filing-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.filing-tab-content').forEach(c => {
    c.classList.remove('active');
    c.style.display = 'none';
  });
  const tab = document.querySelector(`.filing-tab[data-tab="${tabName}"]`);
  const content = document.getElementById(`filing-tab-${tabName}`);
  if (tab) tab.classList.add('active');
  if (content) { content.classList.add('active'); content.style.display = 'block'; }

  console.log('[FILING] switchTab:', tabName, 'content element:', content?.id);
  if (tabName === 'projects') loadProjects();
  else if (tabName === 'reports') loadReports();
  else if (tabName === 'memory') loadMemory();
}

function loadProjects() {
  fetch('/api/projects')
    .then(r => r.json())
    .then(data => {
      filingState.activeProjectId = data.active_project_id;
      const container = document.getElementById('projects-list');
      if (!container) return;
      
      if (!data.projects || data.projects.length === 0) {
        container.innerHTML = '<div class="filing-empty">No projects yet. Create one!</div>';
        return;
      }
      
      container.innerHTML = data.projects.map(p => {
        const isActive = p.id === data.active_project_id;
        return `<div class="project-card ${isActive ? 'active' : ''}" onclick="activateProject('${p.id}')">
          <div class="project-card-header">
            ${isActive ? '⭐ ' : ''}${esc(p.name)}
          </div>
          <div class="project-card-meta">${esc(p.field)} · ${new Date(p.created).toLocaleDateString()}</div>
          <div class="project-card-stats">${p.reports_count || 0} reports · ${p.conversations_count || 0} chats</div>
          ${p.description ? `<div class="project-card-desc">${esc(p.description)}</div>` : ''}
        </div>`;
      }).join('');
    })
    .catch(err => console.error('loadProjects error:', err));
}

function activateProject(projectId) {
  fetch(`/api/projects/${projectId}/activate`, { method: 'PUT' })
    .then(r => r.json())
    .then(() => {
      filingState.activeProjectId = projectId;
      loadProjects();
      showToast('Project activated!');
    })
    .catch(err => console.error('activateProject error:', err));
}

function showNewProjectModal() {
  document.getElementById('new-project-modal')?.classList.remove('hidden');
}
function closeNewProjectModal() {
  document.getElementById('new-project-modal')?.classList.add('hidden');
}

function createNewProject() {
  const name = document.getElementById('new-project-name')?.value.trim();
  const field = document.getElementById('new-project-field')?.value.trim();
  const desc = document.getElementById('new-project-desc')?.value.trim();
  if (!name) { showToast('Please enter a project name', 'error'); return; }

  fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, field, description: desc })
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) { showToast(data.error, 'error'); return; }
      closeNewProjectModal();
      document.getElementById('new-project-name').value = '';
      document.getElementById('new-project-field').value = '';
      document.getElementById('new-project-desc').value = '';
      showToast(`Project "${name}" created!`);
      loadProjects();
    })
    .catch(err => console.error('createNewProject error:', err));
}

function loadReports() {
  console.log('[REPORTS] loadReports called');
  const pid = filingState.activeProjectId;
  console.log('[REPORTS] pid:', pid);
  const container = document.getElementById('reports-list');
  console.log('[REPORTS] container:', container);
  if (!container) { console.error('[REPORTS] NO CONTAINER'); return; }
  if (!pid) { container.innerHTML = '<div class="filing-empty">No active project. Select one first.</div>'; return; }
  
  container.innerHTML = '<div class="filing-empty">Loading...</div>';
  
  const url = `/api/projects/${pid}/reports`;
  console.log('[REPORTS] fetching:', url);
  fetch(url)
    .then(r => { console.log('[REPORTS] response status:', r.status); return r.json(); })
    .then(data => {
      console.log('[REPORTS] data received, reports:', data.reports?.length);
      const reports = data.reports || [];
      if (reports.length === 0) {
        container.innerHTML = '<div class="filing-empty">No reports yet. Talk to an agent!</div>';
        return;
      }
      
      container.innerHTML = reports
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
        .map(r => {
          const agent = AGENTS[r.agent_id] || { emoji: '❓', name: 'Unknown' };
          const text = r.text || '';
          // Extract title: first markdown heading, or first bold text, or first line
          let title = '';
          const headingMatch = text.match(/^#{1,3}\s+(.+)/m);
          const boldMatch = text.match(/\*\*([^*]{10,80})\*\*/);
          if (headingMatch) title = headingMatch[1].replace(/[*#]/g, '').trim();
          else if (boldMatch) title = boldMatch[1].trim();
          else title = text.substring(0, 60).split('\n')[0];
          if (title.length > 70) title = title.substring(0, 67) + '...';
          
          const preview = text.substring(0, 100).replace(/[<>&*#]/g, '').trim() + '...';
          const time = new Date(r.timestamp).toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit'});
          const date = new Date(r.timestamp).toLocaleDateString('en-US', {month:'short', day:'numeric'});
          return `<div class="report-card" onclick="openReportFromFiling('${r.agent_id}','${r.timestamp}')">
            <div class="report-card-header">${agent.emoji} ${agent.name} · ${date} ${time}</div>
            <div class="report-card-title">${title}</div>
            <div class="report-card-preview">${preview}</div>
          </div>`;
        }).join('');
      console.log('[REPORTS] rendered', reports.length, 'cards, container innerHTML length:', container.innerHTML.length);
      // Force visibility
      container.style.display = 'block';
      container.parentElement.style.display = 'block';
    })
    .catch(err => { container.innerHTML = '<div class="filing-empty">Error loading reports.</div>'; console.error(err); });
}

function openReportFromFiling(agentId, timestamp) {
  // Check in-memory first
  const report = state.reports.find(r => r.agent_id === agentId && r.timestamp === timestamp);
  if (report) {
    openReportPanel(report);
    return;
  }
  // Fetch from backend
  fetch(`/api/projects/${filingState.activeProjectId}/reports`)
    .then(r => r.json())
    .then(data => {
      const r = (data.reports || []).find(r => r.timestamp === timestamp);
      if (r) {
        const agent = AGENTS[r.agent_id] || { emoji: "❓", name: "Unknown" };
        openReportPanel({ agent_id: r.agent_id, text: r.text, name: agent.name, emoji: agent.emoji });
      }
    });
}

function loadMemory() {
  loadAgentMemory(document.getElementById('memory-agent-select')?.value || 'scout');
  loadProjectMemory();
  loadLabMemory();
}

function loadAgentMemory(agentId) {
  fetch(`/api/agents/${agentId}/memory`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById('agent-memory-list');
      if (!container) return;
      const entries = data.entries || [];
      container.innerHTML = entries.length === 0
        ? '<div class="filing-empty">No agent memory yet.</div>'
        : entries.map(e => `<div class="memory-entry"><span class="memory-ts">${new Date(e.timestamp).toLocaleString()}</span> ${esc(e.text)}</div>`).join('');
    })
    .catch(err => console.error('loadAgentMemory error:', err));
}

function loadProjectMemory() {
  if (!filingState.activeProjectId) return;
  fetch(`/api/projects/${filingState.activeProjectId}/memory`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById('project-memory-list');
      if (!container) return;
      const entries = data.entries || [];
      container.innerHTML = entries.length === 0
        ? '<div class="filing-empty">No project memory yet.</div>'
        : entries.map(e => `<div class="memory-entry"><span class="memory-ts">${new Date(e.timestamp).toLocaleString()}</span> ${esc(e.text)}</div>`).join('');
    })
    .catch(err => console.error('loadProjectMemory error:', err));
}

function loadLabMemory() {
  fetch('/api/memory')
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById('lab-memory-list');
      if (!container) return;
      const entries = data.entries || [];
      container.innerHTML = entries.length === 0
        ? '<div class="filing-empty">No lab memory yet.</div>'
        : entries.map(e => `<div class="memory-entry"><span class="memory-ts">${new Date(e.timestamp).toLocaleString()}</span> ${esc(e.text)}</div>`).join('');
    })
    .catch(err => console.error('loadLabMemory error:', err));
}

function showAddMemoryModal(type) {
  filingState.memoryType = type;
  document.getElementById('add-memory-modal')?.classList.remove('hidden');
  document.getElementById('memory-note-text').value = '';
}
function closeAddMemoryModal() {
  document.getElementById('add-memory-modal')?.classList.add('hidden');
}

function saveMemoryNote() {
  const text = document.getElementById('memory-note-text')?.value.trim();
  if (!text) { showToast('Please enter a note', 'error'); return; }

  const type = filingState.memoryType;
  let url, body;

  if (type === 'agent') {
    const agentId = document.getElementById('memory-agent-select')?.value || 'scout';
    url = `/api/agents/${agentId}/memory`;
    body = { text };
  } else if (type === 'project') {
    url = `/api/projects/${filingState.activeProjectId}/memory`;
    body = { text };
  } else {
    url = '/api/memory';
    body = { text };
  }

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
    .then(r => r.json())
    .then(() => {
      closeAddMemoryModal();
      showToast('Memory saved!');
      loadMemory();
    })
    .catch(err => console.error('saveMemoryNote error:', err));
}

function esc(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// Initialize filing cabinet on DOM ready
document.addEventListener('DOMContentLoaded', initFilingCabinet);
