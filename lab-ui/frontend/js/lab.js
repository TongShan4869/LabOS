
// ── Day/Night background ────────────────────────────────────────────────────
let forceNight = null; // null = auto, true = night, false = day
function updateBackground() {
  const hour = new Date().getHours();
  const isNight = forceNight !== null ? forceNight : (hour >= 19 || hour < 7);
  const scene = document.getElementById('lab-scene');
  const btn = document.getElementById('hud-daynight');
  if (scene) {
    const bg = isNight ? 'lab-background-night.png' : 'lab-background-day.png';
    scene.style.backgroundImage = `url('assets/lab/${bg}')`;
  }
  if (btn) btn.textContent = isNight ? '☀️' : '🌙';
}
function toggleDayNight() {
  const hour = new Date().getHours();
  const autoNight = hour >= 19 || hour < 7;
  if (forceNight === null) forceNight = !autoNight;
  else forceNight = !forceNight;
  updateBackground();
}
updateBackground();
setInterval(updateBackground, 60000);
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
      if (id === "main") {
        openDialogue("main");
      } else {
        // Clicking a specialist opens dialogue with Lab Manager
        // but shows who you clicked
        openDialogue("main", id);
      }
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
      // Render markdown after typewriter finishes
      if (typeof marked !== 'undefined') {
        dlgText.innerHTML = marked.parse(text);
      }
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

function openDialogue(agentId, clickedSpecialist) {
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
  // Show greeting if no history, or if last message was garbage (heartbeat etc)
  const isGarbage = lastAgentMsg && /^(HEARTBEAT_OK|NO_REPLY)$/i.test(lastAgentMsg.text.trim());
  const greetText = (lastAgentMsg && !isGarbage)
    ? lastAgentMsg.text
    : agent.greeting;

  // If specialist was clicked, show a contextual greeting
  if (clickedSpecialist && AGENTS[clickedSpecialist]) {
    const spec = AGENTS[clickedSpecialist];
    typewrite(`You clicked on ${spec.name}. Want me to assign them a task? Just tell me what you need!`, () => {
      dlgInput.focus();
      dlgInput.placeholder = `Ask Lab Manager to use ${spec.name}...`;
    });
  } else {
    typewrite(greetText, () => {
      dlgInput.focus();
    });
  }

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
  updateAgentStatus(agent_id, "idle", "");
  const agentName = AGENTS[agent_id]?.name || agent_id;
  addToChatLog(agentName, text.length > 200 ? text.substring(0, 200) + '...' : text);

  const LONG_THRESHOLD = 1500;
  const isLong = text.length > LONG_THRESHOLD;

  // Store report if long
  // If agent is still working (skill running), this is a preview, not final report
  const isPreview = state.waitingReply;

  if (isLong && !isPreview) {
    storeReport(agent_id, text, ts);
  }

  if (isPreview && isLong) {
    // Stash as pending preview — checkpoint handler will show it
    state._pendingPreview = text;
    if (state.activeAgent === agent_id) {
      renderHistory(agent_id);
      typewrite(`📋 Found results — reviewing...`, () => {});
    }
    return;
  }

  if (state.activeAgent === agent_id) {
    // Dialogue is open for this agent
    if (isLong) {
      openReportPanel(agent_id, text, ts);
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
  const { agent_id, agent_name, prompt, ts, preview } = data;

  appendLocalHistory(agent_id, "agent", `🔀 ${prompt}`, ts);

  // ALWAYS set checkpointAgent — even if dialogue is closed
  state.checkpointAgent = agent_id;
  state.waitingReply = false;  // Allow input

  // If there's a preview (e.g. paper list), show in report panel
  if (state._pendingPreview) {
    openReportPanel(agent_id, state._pendingPreview, ts);
    state._pendingPreview = null;
  }

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
  if (!dlgHistory) return;
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

  // Clock handled by updateClock() — using client local time
}

// ── Agent status bubbles ──────────────────────────────────────────────────────

function updateAgentStatus(agentId, status, detail) {
  const sprite = document.getElementById(`agent-${agentId}`);
  const bubble = document.getElementById(`bubble-${agentId}`);
  if (!sprite || !bubble) return;

  if (status === "working" || status === "researching" || status === "executing") {
    sprite.classList.add("working");
    setAgentAnimMode(agentId, "working");
    // Cute rotating status messages
    const workPhrases = ["thinking hard", "crunching data", "reading papers", "brewing ideas", "on it!", "almost there"];
    const phrase = detail || workPhrases[Math.floor(Math.random() * workPhrases.length)];
    bubble.textContent = phrase.slice(0, 30) + (phrase.length > 30 ? "…" : "");
    // Start cycling phrases
    if (!sprite._phraseTimer) {
      sprite._phraseTimer = setInterval(() => {
        if (!sprite.classList.contains("working")) return;
        bubble.textContent = workPhrases[Math.floor(Math.random() * workPhrases.length)];
      }, 3000);
    }
  } else {
    sprite.classList.remove("working");
    setAgentAnimMode(agentId, "idle");
    bubble.textContent = "";
    if (sprite._phraseTimer) { clearInterval(sprite._phraseTimer); sprite._phraseTimer = null; }
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
  const socket = io(origin, { transports: ["polling"], reconnection: true, reconnectionDelay: 500 });
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

  // ── Live Events (Paperclip-inspired invalidation) ────────────────────────
  // Server pushes lightweight events; frontend refetches from REST APIs.
  socket.on("live_event", (event) => {
    console.log("📡 Live event:", event.type, event.payload);
    
    const handlers = {
      "quest.created": () => {
        updateCoins();
        // If dashboard is open on quests tab, refresh
        const panel = document.getElementById("dashboard-panel");
        if (panel && !panel.classList.contains("hidden")) {
          const activeTab = document.querySelector(".dash-tab.active");
          if (activeTab?.dataset.tab === "quests") dashLoadTab("quests");
        }
        const p = event.payload;
        if (p.agent_id && p.title) {
          showToast(`📋 New quest: ${p.title} → ${p.agent_id}`);
        }
      },
      "quest.completed": () => {
        updateCoins();
        const panel = document.getElementById("dashboard-panel");
        if (panel && !panel.classList.contains("hidden")) {
          const activeTab = document.querySelector(".dash-tab.active");
          if (activeTab?.dataset.tab === "quests") dashLoadTab("quests");
        }
        showToast("✅ Quest completed!");
      },
      "agent.status": () => {
        const p = event.payload;
        if (p.agent_id) {
          updateAgentStatus(p.agent_id, p.status, p.detail || "");
        }
      },
      "agent.promoted": () => {
        const p = event.payload;
        showToast(`🎉 ${p.agent_id} promoted to ${p.lifecycle}!`);
        updateCoins();
      },
      "lab.stats": () => {
        updateCoins();
      },
      "run.completed": () => {
        updateCoins();
      }
    };
    
    const handler = handlers[event.type];
    if (handler) handler();
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
    hudReports?.classList.remove("hidden");
    if (hudReportsCount) hudReportsCount.textContent = state.reports.length;
  } else {
    hudReports?.classList.add("hidden");
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

hudReports?.addEventListener("click", toggleReportsList);

// ── Report panel ──────────────────────────────────────────────────────────────

function openReportPanel(agentIdOrObj, text, ts) {
  let agentId, reportText, reportTime;
  if (typeof agentIdOrObj === 'object') {
    // Called from filing cabinet with report object
    agentId = agentIdOrObj.agent_id;
    reportText = agentIdOrObj.text;
    reportTime = agentIdOrObj.timestamp;
  } else {
    agentId = agentIdOrObj;
    reportText = text;
    reportTime = ts;
  }
  const agent = AGENTS[agentId] || { emoji: '❓', name: 'Unknown', role: 'Agent' };
  reportEmoji.textContent = agent.emoji;
  reportName.textContent = agent.name + " — " + agent.role;
  reportTs.textContent = reportTime || new Date().toLocaleTimeString("en", {hour:"2-digit", minute:"2-digit"});
  reportBody.innerHTML = formatReport(reportText);
  reportOverlay.classList.remove('hidden');
  reportOverlay.style.display = 'flex';
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
  // ?reset in URL forces fresh onboarding
  if (window.location.search.includes("reset")) {
    localStorage.clear();
    sessionStorage.clear();
  }
  
  // Hide lab + HUD until onboarding check completes
  const labEl = document.getElementById("lab-scene");
  const hudEl = document.getElementById("hud");
  if (labEl) labEl.style.display = "none";
  if (hudEl) hudEl.style.display = "none";
  
  buildAgentSprites();
  connectSocket();
  updateClock();
  setInterval(updateClock, 10000);

  // Check onboarding FIRST, then show lab
  checkOnboardingNeeded(() => {
    if (labEl) labEl.style.display = "";
    if (hudEl) hudEl.style.display = "";
    // Initial status fetch
    fetch("/api/status")
      .then(r => r.json())
      .then(data => updateHud(data))
      .catch(() => {});
    showToast("🔬 LabOS ready! Click an agent to talk.");
  });
}

document.addEventListener("DOMContentLoaded", init);

// ── Onboarding & Loading Logic ────────────────────────────────────────────

function checkOnboardingNeeded(onReady) {
  fetch('/api/config')
    .then(r => {
      if (!r.ok) throw new Error('config fetch failed');
      return r.json();
    })
    .then(data => {
      console.log('[ONBOARD] config:', data);
      if (data && data.lab_name) {
        localStorage.setItem('labos_onboarding_complete', 'true');
        $('hud-title').textContent = `${data.lab_name} — LabOS`;
        if (onReady) onReady();
      } else {
        localStorage.removeItem('labos_onboarding_complete');
        showOnboarding(onReady);
      }
    })
    .catch(err => {
      console.error('[ONBOARD] fetch error:', err);
      if (!localStorage.getItem('labos_onboarding_complete')) {
        showOnboarding(onReady);
      } else {
        if (onReady) onReady();
      }
    });
}

function showOnboarding(onReady) {
  window._onboardingReady = onReady;
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
        if (window._onboardingReady) window._onboardingReady();
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
  overlay.style.display = 'flex';
  
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
  $('xp-modal-overlay').style.display = 'none';
}

// ── Event Listeners ────────────────────────────────────────────────────────

// XP/Filing/Chatlog listeners moved to consolidated DOMContentLoaded below

// ─── Filing Cabinet ─────────────────────────────────────────────────────────

const filingState = { open: false, memoryType: null, activeProjectId: null };

// ─── Chat Log Panel ─────────────────────────────────────────────────────────

const chatLogMessages = [];

function openChatLog() {
  const overlay = $('chatlog-overlay');
  const msgs = $('chatlog-messages');
  overlay.classList.remove('hidden');
  overlay.style.display = 'flex';
  msgs.innerHTML = chatLogMessages.length === 0
    ? '<div class="filing-empty">No messages yet. Talk to an agent!</div>'
    : chatLogMessages.map(m =>
        `<div class="chatlog-msg"><span class="chatlog-who">${m.who}</span> <span class="chatlog-time">${m.ts}</span><br>${m.text}</div>`
      ).join('');
  msgs.scrollTop = msgs.scrollHeight;
}

function closeChatLog() {
  $('chatlog-overlay').style.display = 'none';
}

function addToChatLog(who, text) {
  chatLogMessages.push({ who, text, ts: new Date().toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit'}) });
}



// Filing cabinet replaced by unified dashboard
function initFilingCabinet() {
  // Legacy — filing cabinet is now part of the dashboard panel
  const el = (id) => document.getElementById(id);
  el('new-project-cancel')?.addEventListener('click', closeNewProjectModal);
  el('new-project-confirm')?.addEventListener('click', createNewProject);
  el('memory-note-cancel')?.addEventListener('click', closeAddMemoryModal);
  el('memory-note-confirm')?.addEventListener('click', saveMemoryNote);
}

function showFilingCabinet() {
  // Redirect to dashboard projects tab
  const panel = document.getElementById("dashboard-panel");
  const btn = document.getElementById("hud-dashboard");
  if (panel) { panel.classList.remove("hidden"); btn?.classList.add("active"); }
  document.querySelectorAll(".dash-tab").forEach(t => t.classList.remove("active"));
  const projTab = document.querySelector('.dash-tab[data-tab="projects"]');
  if (projTab) projTab.classList.add("active");
  dashLoadTab("projects");
}

function closeFilingCabinet() { /* no-op — dashboard handles this */ }

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
  const pid = filingState.activeProjectId;
  const container = document.getElementById('reports-list');
  if (!container) { console.error('[REPORTS] NO CONTAINER'); return; }
  if (!pid) { container.innerHTML = '<div class="filing-empty">No active project. Select one first.</div>'; return; }
  
  container.innerHTML = '<div class="filing-empty">Loading...</div>';
  
  const url = `/api/projects/${pid}/reports`;
  fetch(url)
    .then(r => { console.log('[REPORTS] response status:', r.status); return r.json(); })
    .then(data => {
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
document.addEventListener('DOMContentLoaded', () => {
  try {
    // checkOnboardingNeeded moved to init()
    $('hud-left')?.addEventListener('click', showXpModal);
    $('xp-modal-close')?.addEventListener('click', closeXpModal);
    $('xp-modal-overlay')?.addEventListener('click', (e) => {
      if (e.target === $('xp-modal-overlay')) closeXpModal();
    });
    initFilingCabinet();
    $('hud-chatlog')?.addEventListener('click', openChatLog);
    $('chatlog-close')?.addEventListener('click', closeChatLog);
    $('chatlog-overlay')?.addEventListener('click', (e) => {
      if (e.target.id === 'chatlog-overlay') closeChatLog();
    });
    $('hud-daynight')?.addEventListener('click', toggleDayNight);
    console.log('[INIT] All UI listeners registered');
  } catch(e) { console.error('[INIT] Error:', e); }
});

// ── Unified Dashboard (below lab scene) ──────

document.getElementById("hud-dashboard")?.addEventListener("click", () => {
  const panel = document.getElementById("dashboard-panel");
  const btn = document.getElementById("hud-dashboard");
  if (panel.classList.contains("hidden")) {
    panel.classList.remove("hidden");
    btn.classList.add("active");
    // Load default tab
    dashLoadTab("quests");
  } else {
    panel.classList.add("hidden");
    btn.classList.remove("active");
  }
});

document.querySelectorAll(".dash-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".dash-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    dashLoadTab(tab.dataset.tab);
  });
});

async function dashLoadTab(tabName) {
  const content = document.getElementById("dashboard-content");
  content.innerHTML = '<div class="dash-loading">Loading...</div>';

  try {
    switch (tabName) {
      case "quests": return await dashLoadQuests(content);
      case "roster": return await dashLoadRoster(content);
      case "projects": return await dashLoadProjects(content);
      case "reports": return await dashLoadReports(content);
      case "memory": return await dashLoadMemory(content);
      case "schedules": return await dashLoadSchedules(content);
    }
  } catch (e) {
    content.innerHTML = `<div class="dash-loading">Failed to load ${tabName}.</div>`;
    console.error("Dashboard error:", e);
  }
}

async function dashLoadQuests(content) {
  const res = await fetch(origin + "/api/quests?all=true");
  const quests = await res.json();
  const active = quests.filter(q => q.status === "active");
  const done = quests.filter(q => q.status === "done");

  if (quests.length === 0) {
    content.innerHTML = '<div class="dash-loading">No quests yet. Talk to the Lab Manager to get started!</div>';
    return;
  }

  let html = "";
  if (active.length > 0) {
    html += '<h3 style="color:#8888ff;margin:0 0 8px">⚡ Active</h3>';
    html += active.map(q => renderQuestCard(q)).join("");
  }
  if (done.length > 0) {
    html += '<h3 style="color:#6a6;margin:12px 0 8px">✅ Completed</h3>';
    html += done.map(q => renderQuestCard(q)).join("");
  }
  content.innerHTML = html;
}

function renderQuestCard(q) {
  return `
    <div class="quest-card ${q.status}">
      <div class="quest-title">${q.title}</div>
      <div class="quest-meta">
        <span class="quest-agent">🤖 ${q.assigned_to}</span>
        <span class="quest-xp">✨ ${q.xp_reward} XP</span>
        <span>${q.status === "done" ? "✅ " + new Date(q.completed_at).toLocaleDateString() : "⏳ " + new Date(q.created_at).toLocaleDateString()}</span>
      </div>
      ${q.result_summary ? `<div style="font-size:12px;color:#aaa;margin-top:6px">${q.result_summary}</div>` : ""}
    </div>`;
}

async function dashLoadRoster(content) {
  const res = await fetch(origin + "/api/agents/roster");
  const roster = await res.json();

  content.innerHTML = roster.map(a => `
    <div class="roster-card">
      <img class="roster-avatar" src="${origin}/assets/avatars/avatar-${a.id}.png" onerror="this.style.display='none'">
      <div class="roster-info">
        <div class="roster-name">${a.name}</div>
        <div class="roster-specialty">${a.specialty}</div>
        <div class="roster-stats">
          🏃 ${a.usage.runs} runs · 
          🪙 $${a.usage.cost_usd.toFixed(2)} ·
          ${a.usage.last_active ? "Last: " + new Date(a.usage.last_active).toLocaleDateString() : "Never used"}
        </div>
      </div>
      <span class="roster-lifecycle ${a.lifecycle}">${a.lifecycle}</span>
    </div>
  `).join("");
}

async function dashLoadProjects(content) {
  const res = await fetch(origin + "/api/projects");
  const data = await res.json();
  const projects = data.projects || [];
  const activeId = data.active_project_id;

  let html = projects.map(p => `
    <div class="quest-card ${p.id === activeId ? '' : 'done'}" style="cursor:pointer" onclick="switchProject('${p.id}')">
      <div class="quest-title">${p.id === activeId ? '🟢 ' : ''}${p.name || 'Untitled Project'}</div>
      <div class="quest-meta">
        <span>${(p.fields || []).join(', ') || 'No fields set'}</span>
        <span>Created ${new Date(p.created_at).toLocaleDateString()}</span>
      </div>
    </div>
  `).join("");
  html += '<button class="filing-action-btn" onclick="showNewProjectModal()" style="margin-top:8px;width:100%;padding:8px;background:#2a4a6a;color:#fff;border:1px solid #3a6a9a;border-radius:6px;cursor:pointer">+ New Project</button>';
  content.innerHTML = html;
}

async function dashLoadReports(content) {
  const res = await fetch(origin + "/api/reports");
  const reports = await res.json();

  if (!reports.length) {
    content.innerHTML = '<div class="dash-loading">No reports yet. Run a literature search to generate one!</div>';
    return;
  }

  content.innerHTML = reports.map(r => `
    <div class="quest-card" style="cursor:pointer" onclick="openReportById('${r.filename}')">
      <div class="quest-title">📄 ${r.title || r.filename}</div>
      <div class="quest-meta">
        <span>🤖 ${r.agent_id || 'unknown'}</span>
        <span>${new Date(r.timestamp).toLocaleDateString()}</span>
      </div>
    </div>
  `).join("");
}

async function dashLoadMemory(content) {
  const agents = ["main", "scout", "stat", "quill", "sage", "critic", "trend", "warden"];
  
  let html = '<div style="margin-bottom:12px"><label style="color:#aaa;font-size:12px">Agent: </label>';
  html += `<select id="dash-memory-agent" onchange="dashRefreshMemory()" style="background:#1e1e3a;color:#fff;border:1px solid #3a3a5c;padding:4px 8px;border-radius:4px">`;
  html += agents.map(a => `<option value="${a}">${a}</option>`).join("");
  html += '</select></div>';
  html += '<div id="dash-memory-content"></div>';
  content.innerHTML = html;
  dashRefreshMemory();
}

async function dashRefreshMemory() {
  const agent = document.getElementById("dash-memory-agent")?.value || "main";
  const el = document.getElementById("dash-memory-content");
  if (!el) return;
  
  try {
    const res = await fetch(origin + `/api/agents/${agent}/memory`);
    const data = await res.json();
    const entries = data.memory || [];
    if (!entries.length) {
      el.innerHTML = '<div class="dash-loading">No memory recorded yet.</div>';
      return;
    }
    el.innerHTML = entries.map(e => `
      <div style="background:#12122a;border:1px solid #2a2a4a;border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:13px">
        <span style="color:#ccc">${e.text}</span>
        <span style="color:#555;font-size:11px;float:right">${new Date(e.timestamp).toLocaleDateString()}</span>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="dash-loading">Could not load memory.</div>';
  }
}

async function dashLoadSchedules(content) {
  const res = await fetch(origin + "/api/schedules");
  const schedules = await res.json();

  if (!schedules.length) {
    content.innerHTML = `
      <div class="dash-loading">
        <p>🌙 No scheduled tasks yet.</p>
        <p style="font-size:12px;color:#888">Tell the Lab Manager to schedule recurring work, like:<br>
        "Check for new papers in my field every Monday"</p>
      </div>`;
    return;
  }

  content.innerHTML = schedules.map(s => `
    <div class="quest-card ${s.enabled ? '' : 'done'}">
      <div class="quest-title">🌙 ${s.description || s.task}</div>
      <div class="quest-meta">
        <span class="quest-agent">🤖 ${s.agent_id}</span>
        <span>⏰ ${s.cron_expr}</span>
        <span>${s.run_count} runs</span>
      </div>
      ${s.last_run ? `<div style="font-size:11px;color:#666;margin-top:4px">Last run: ${new Date(s.last_run).toLocaleString()}</div>` : ''}
    </div>
  `).join("");
}

// Helper for opening reports from dashboard
function openReportById(filename) {
  // Reuse existing report panel logic
  fetch(origin + `/api/report/${filename}`)
    .then(r => r.json())
    .then(report => {
      if (report.text) {
        const rp = document.getElementById("report-panel");
        const rb = document.getElementById("report-body");
        if (rp && rb) {
          rb.innerHTML = marked.parse(report.text);
          rp.classList.remove("hidden");
        }
      }
    })
    .catch(() => showToast("⚠️ Could not load report"));
}

// Helper for switching projects from dashboard
function switchProject(projectId) {
  fetch(origin + "/api/projects/switch", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({project_id: projectId})
  }).then(() => {
    showToast("🔬 Switched project!");
    dashLoadTab("projects");
  }).catch(() => showToast("⚠️ Failed to switch project"));
}

// ── Coins Counter ────────────────────────────

async function updateCoins() {
  try {
    const res = await fetch(origin + "/api/agents/roster");
    const roster = await res.json();
    const totalCost = roster.reduce((sum, a) => sum + (a.usage?.cost_usd || 0), 0);
    const totalRuns = roster.reduce((sum, a) => sum + (a.usage?.runs || 0), 0);
    const el = document.getElementById("hud-coins");
    if (el) {
      el.textContent = `🪙 ${totalRuns} runs`;
      el.title = `Total cost: $${totalCost.toFixed(2)} | ${totalRuns} agent runs`;
    }
  } catch(e) {}
}

updateCoins();
setInterval(updateCoins, 30000);
