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
  state.waitingReply  = false;

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
  dlgOverlay.classList.add("hidden");
  clearTimeout(state.typewriterTimer);
  state.activeAgent   = null;
  state.waitingReply  = false;
}

// ── Send message ──────────────────────────────────────────────────────────────

function sendMessage() {
  const text = dlgInput.value.trim();
  if (!text || !state.activeAgent) return;

  const agentId = state.activeAgent;
  dlgInput.value = "";

  if (state.checkpointAgent === agentId) {
    // Checkpoint reply
    appendLocalHistory(agentId, "user", text);
    renderHistory(agentId);
    dlgInput.disabled = true;
    dlgInput.placeholder = "Type a message...";
    state.socket.emit("checkpoint_reply", { agent_id: agentId, text });
    state.checkpointAgent = null;
    typewrite(`${AGENTS[agentId].name} is processing...`);
    return;
  }

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

  // If this agent's dialogue is open, typewrite the reply
  if (state.activeAgent === agent_id) {
    renderHistory(agent_id);
    typewrite(text, () => {
      dlgInput.disabled = false;
      dlgInput.focus();
    });
  } else {
    // Agent is not in focus — show toast
    const agent = AGENTS[agent_id];
    showToast(`${agent.emoji} ${agent.name}: ${text.slice(0, 60)}${text.length > 60 ? "…" : ""}`);
  }
}

function handleCheckpoint(data) {
  const { agent_id, agent_name, prompt, ts } = data;

  appendLocalHistory(agent_id, "agent", `🔀 ${prompt}`, ts);

  if (state.activeAgent === agent_id) {
    renderHistory(agent_id);
    typewrite(`🔀 ${prompt}`, () => {
      dlgInput.disabled = false;
      dlgInput.placeholder = "Reply to checkpoint...";
      dlgInput.focus();
      state.checkpointAgent = agent_id;
    });
  } else {
    const agent = AGENTS[agent_id];
    showToast(`${agent.emoji} ${agent_name} needs input: ${prompt.slice(0, 80)}`);
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
