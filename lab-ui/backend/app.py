#!/usr/bin/env python3
"""
LabOS UI Backend
- Serves the pixel lab frontend
- WebSocket bridge: routes messages between UI and LabOS agents
- Reads LabOS state files for live agent status
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, send_from_directory, request
from flask_socketio import SocketIO, emit

# ─── Paths ────────────────────────────────────────────────────────────────────

ROOT_DIR     = Path(__file__).parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
LAB_DIR      = Path(os.environ.get("LAB_DIR", Path.home() / ".openclaw/workspace/lab"))
STATE_FILE   = ROOT_DIR / "state.json"
AGENTS_FILE  = ROOT_DIR / "agents-state.json"
XP_FILE      = LAB_DIR / "xp.json"
MEMORY_DIR   = Path.home() / ".openclaw/workspace/memory"

# ─── Agent roster ─────────────────────────────────────────────────────────────

AGENTS = {
    "main": {
        "id":       "main",
        "name":     "醋の虾",
        "role":     "Principal Investigator",
        "skill":    None,
        "emoji":    "🦞",
        "zone":     "pi-desk",
        "color":    "#e63946",
        "avatar":   "avatar-main.png",
        "greeting": "Hey! What are you working on today?",
    },
    "scout": {
        "id":       "scout",
        "name":     "Scout",
        "role":     "Literature Search",
        "skill":    "lab-lit-scout",
        "emoji":    "🔬",
        "zone":     "bookshelf",
        "color":    "#2a9d8f",
        "avatar":   "avatar-scout.png",
        "greeting": "Need me to dig into the literature? Just give me a query.",
    },
    "stat": {
        "id":       "stat",
        "name":     "Stat",
        "role":     "Biostatistician",
        "skill":    "lab-biostat",
        "emoji":    "📊",
        "zone":     "bench",
        "color":    "#457b9d",
        "avatar":   "avatar-stat.png",
        "greeting": "Got data to analyze? I'll run the numbers and show my work.",
    },
    "quill": {
        "id":       "quill",
        "name":     "Quill",
        "role":     "Writing Assistant",
        "skill":    "lab-writing-assistant",
        "emoji":    "✍️",
        "zone":     "desk",
        "color":    "#e9c46a",
        "avatar":   "avatar-quill.png",
        "greeting": "Ready to draft something? Tell me the section and project.",
    },
    "sage": {
        "id":       "sage",
        "name":     "Sage",
        "role":     "Research Advisor",
        "skill":    "lab-research-advisor",
        "emoji":    "🎓",
        "zone":     "advisor-chair",
        "color":    "#6d6875",
        "avatar":   "avatar-sage.png",
        "greeting": "Let's talk about your research. What's the current hypothesis?",
    },
    "critic": {
        "id":       "critic",
        "name":     "Critic",
        "role":     "Peer Reviewer",
        "skill":    "lab-peer-reviewer",
        "emoji":    "🤺",
        "zone":     "review-table",
        "color":    "#e76f51",
        "avatar":   "avatar-critic.png",
        "greeting": "Drop your draft. I'll tear it apart so reviewers don't have to.",
    },
    "trend": {
        "id":       "trend",
        "name":     "Trend",
        "role":     "Field Monitor",
        "skill":    "lab-field-trend",
        "emoji":    "📰",
        "zone":     "news-board",
        "color":    "#52b788",
        "avatar":   "avatar-trend.png",
        "greeting": "I monitor your field 24/7. Want the latest digest?",
    },
    "warden": {
        "id":       "warden",
        "name":     "Warden",
        "role":     "Security",
        "skill":    "lab-security",
        "emoji":    "🔒",
        "zone":     "security-console",
        "color":    "#333333",
        "avatar":   "avatar-warden.png",
        "greeting": "Everything looks secure. Want me to run an audit?",
    },
}

# ─── App setup ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("LABOS_SECRET", "labos-dev-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Active agent conversations: {agent_id: {"process": Popen, "thread": Thread}}
active_convos: dict = {}
# Message history per agent: {agent_id: [{"role": "user"|"agent", "text": str, "ts": str}]}
message_history: dict = {aid: [] for aid in AGENTS}


# ─── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"state": "idle", "detail": "Waiting...", "progress": 0}


def load_agents_state() -> dict:
    if AGENTS_FILE.exists():
        try:
            return json.loads(AGENTS_FILE.read_text())
        except Exception:
            pass
    return {}


def load_xp() -> dict:
    if XP_FILE.exists():
        try:
            return json.loads(XP_FILE.read_text())
        except Exception:
            pass
    return {"xp": 0, "level": 1, "level_title": "Confused First-Year", "badges": []}


def get_lab_status() -> dict:
    state      = load_state()
    agents_st  = load_agents_state()
    xp_data    = load_xp()
    agents_out = {}
    for aid, info in AGENTS.items():
        ast = agents_st.get(aid, {})
        agents_out[aid] = {
            **info,
            "status":  ast.get("status", "idle"),
            "detail":  ast.get("detail", ""),
            "working": ast.get("status") not in (None, "idle"),
        }
    return {
        "state":   state,
        "agents":  agents_out,
        "xp":      xp_data,
        "time":    datetime.now().strftime("%H:%M"),
        "date":    datetime.now().strftime("%a %b %d"),
    }


# ─── REST endpoints ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/api/status")
def api_status():
    return jsonify(get_lab_status())


@app.route("/api/agents")
def api_agents():
    return jsonify(AGENTS)


@app.route("/api/history/<agent_id>")
def api_history(agent_id):
    return jsonify(message_history.get(agent_id, []))


# ─── WebSocket: agent conversation ────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("lab_status", get_lab_status())


@socketio.on("send_message")
def on_message(data):
    """
    data = {"agent_id": "scout", "text": "find papers on speech"}
    """
    agent_id = data.get("agent_id", "main")
    text     = data.get("text", "").strip()
    if not text:
        return

    agent = AGENTS.get(agent_id)
    if not agent:
        emit("error", {"message": f"Unknown agent: {agent_id}"})
        return

    # Store user message
    ts = datetime.now().strftime("%H:%M")
    message_history[agent_id].append({"role": "user", "text": text, "ts": ts})
    emit("message_echo", {"agent_id": agent_id, "role": "user", "text": text, "ts": ts})

    # Mark agent as working
    _set_agent_status(agent_id, "working", f"Processing: {text[:40]}…")
    emit("agent_status", {"agent_id": agent_id, "status": "working", "detail": text[:60]})

    # Route message to agent in background thread
    sid = request.sid
    thread = threading.Thread(
        target=_route_to_agent,
        args=(agent_id, agent, text, sid),
        daemon=True,
    )
    thread.start()


def _route_to_agent(agent_id: str, agent: dict, text: str, sid: str):
    """
    Routes user message to the appropriate LabOS skill or main agent.
    Streams response back via WebSocket.
    """
    skill = agent.get("skill")

    if skill is None:
        # Main agent — call claude directly
        response = _call_main_agent(agent_id, text)
    else:
        # Skill agent — call the Python script with the message as context
        response = _call_skill_agent(agent_id, skill, text)

    ts = datetime.now().strftime("%H:%M")
    message_history[agent_id].append({"role": "agent", "text": response, "ts": ts,
                                       "agent_id": agent_id})

    # Emit response with typewriter trigger
    socketio.emit("agent_reply", {
        "agent_id":   agent_id,
        "agent_name": agent["name"],
        "avatar":     agent["avatar"],
        "emoji":      agent["emoji"],
        "color":      agent["color"],
        "text":       response,
        "ts":         ts,
    }, to=sid)

    _set_agent_status(agent_id, "idle", "")
    socketio.emit("agent_status", {"agent_id": agent_id, "status": "idle", "detail": ""},
                  to=sid)


def _call_main_agent(agent_id: str, text: str) -> str:
    """Call claude CLI as the main 醋の虾 agent."""
    history = message_history.get(agent_id, [])[-6:]  # last 3 exchanges
    history_text = "\n".join(
        f"{'User' if m['role']=='user' else '醋の虾'}: {m['text']}"
        for m in history[:-1]  # exclude current message
    )
    prompt = (
        "You are 醋の虾 (Cu's Lobster), the PI of a virtual research lab running LabOS. "
        "You are helpful, direct, and occasionally witty. "
        "You can answer research questions, coordinate other lab agents, and advise on projects. "
        "Keep responses concise (2-4 sentences max for dialogue).\n\n"
        + (f"Recent conversation:\n{history_text}\n\n" if history_text else "")
        + f"User: {text}\n醋の虾:"
    )
    return _run_llm(prompt)


def _call_skill_agent(agent_id: str, skill: str, text: str) -> str:
    """
    Route message to a LabOS skill agent.
    For now: uses LLM with skill context. 
    Full implementation: spawns skill script and feeds text via stdin.
    """
    agent = AGENTS[agent_id]
    history = message_history.get(agent_id, [])[-6:]
    history_text = "\n".join(
        f"{'User' if m['role']=='user' else agent['name']}: {m['text']}"
        for m in history[:-1]
    )

    prompt = (
        f"You are {agent['name']}, a {agent['role']} in a research lab AI system called LabOS. "
        f"Your skill is {skill}. You help researchers with {agent['role'].lower()} tasks. "
        f"Be helpful and specific. Keep responses concise for this dialogue interface (2-5 sentences). "
        f"If the task requires actual execution (running stats, searching papers etc.), "
        f"acknowledge what you would do and ask for any missing information.\n\n"
        + (f"Recent:\n{history_text}\n\n" if history_text else "")
        + f"User: {text}\n{agent['name']}:"
    )
    return _run_llm(prompt)


def _run_llm(prompt: str) -> str:
    """Call claude CLI. Falls back to placeholder if unavailable."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "I'm thinking... (LLM not available in this context)"


def _set_agent_status(agent_id: str, status: str, detail: str):
    agents_st = load_agents_state()
    agents_st[agent_id] = {"status": status, "detail": detail,
                            "updated": datetime.now().isoformat()}
    AGENTS_FILE.write_text(json.dumps(agents_st, indent=2))


# ─── State push from LabOS skills ─────────────────────────────────────────────

@app.route("/api/push_state", methods=["POST"])
def push_state():
    """
    LabOS skills call this to update their state in the UI.
    Body: {"agent_id": "scout", "status": "working", "detail": "Searching PubMed..."}
    """
    data     = request.json or {}
    agent_id = data.get("agent_id", "main")
    status   = data.get("status", "idle")
    detail   = data.get("detail", "")

    _set_agent_status(agent_id, status, detail)
    socketio.emit("agent_status", {"agent_id": agent_id, "status": status, "detail": detail})

    # Also update main state file
    STATE_FILE.write_text(json.dumps({
        "state":      status,
        "detail":     detail,
        "agent_id":   agent_id,
        "progress":   data.get("progress", 0),
        "updated_at": datetime.now().isoformat(),
    }, indent=2))

    return jsonify({"ok": True})


# ─── Periodic status broadcast ────────────────────────────────────────────────

def _broadcast_status():
    while True:
        time.sleep(5)
        socketio.emit("lab_status", get_lab_status())


broadcast_thread = threading.Thread(target=_broadcast_status, daemon=True)
broadcast_thread.start()

# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("LABOS_UI_PORT", 18792))
    print(f"🔬 LabOS UI running at http://127.0.0.1:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
