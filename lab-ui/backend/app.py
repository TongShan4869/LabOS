#!/usr/bin/env python3
"""
LabOS UI Backend — Entry Point

Thin app setup: Flask + SocketIO init, blueprint registration, broadcast loop.
All business logic lives in separate modules:
  - config.py    — paths, constants, agent roster, prompts
  - security.py  — path validation helpers
  - llm.py       — LLM gateway/fallback calls
  - xp.py        — XP & leveling system
  - data.py      — project/memory/report/chat persistence
  - agents.py    — agent routing, skill execution, checkpoints
  - lab_manager.py — orchestration engine, quest board, scheduling
  - routes/api.py — REST API endpoints (Blueprint)
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

# Ensure backend dir is on path for local imports
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

from config import (
    AGENTS, FRONTEND_DIR, STATE_FILE, AGENTS_FILE, XP_FILE,
    BROADCAST_INTERVAL,
)
from data import (
    ensure_data_structure, get_active_project_id, load_project_meta,
    load_chat_history, append_chat_message,
)
from xp import load_xp
from agents import route_to_agent, handle_checkpoint_reply

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s %(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("labos")

# ─── App setup ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("LABOS_SECRET", os.urandom(32).hex())

# CORS: allow localhost + tunnel URLs; override with LABOS_CORS_ORIGINS env var
_cors_origins = os.environ.get("LABOS_CORS_ORIGINS", "")
_allowed_origins = (
    [o.strip() for o in _cors_origins.split(",") if o.strip()]
    if _cors_origins
    else ["http://127.0.0.1:*", "http://localhost:*", "https://*.trycloudflare.com"]
)
socketio = SocketIO(app, cors_allowed_origins=_allowed_origins, async_mode="threading")

# ─── Live Event System ────────────────────────────────────────────────────────

def publish_event(event_type: str, payload: dict = None, sid: str = None):
    """Publish a live event to connected clients."""
    event = {
        "type": event_type,
        "payload": payload or {},
        "ts": datetime.now().isoformat()
    }
    if sid:
        socketio.emit("live_event", event, to=sid)
    else:
        socketio.emit("live_event", event)

# ─── Message History ──────────────────────────────────────────────────────────

message_history: dict = {aid: [] for aid in AGENTS}

# ─── Initialize ──────────────────────────────────────────────────────────────

# Clear stale agent state on startup
for _f in [STATE_FILE, AGENTS_FILE]:
    if _f.exists():
        _f.unlink()

ensure_data_structure()

# Load chat history for active project
active_proj = get_active_project_id()
if active_proj:
    for agent_id in AGENTS:
        message_history[agent_id] = load_chat_history(active_proj, agent_id)

# ─── Register Blueprints ─────────────────────────────────────────────────────

from routes.api import api
app.register_blueprint(api)

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


def get_lab_status() -> dict:
    state = load_state()
    agents_st = load_agents_state()
    xp_data = load_xp()
    agents_out = {}
    for aid, info in AGENTS.items():
        ast = agents_st.get(aid, {})
        agents_out[aid] = {
            **info,
            "status": ast.get("status", "idle"),
            "detail": ast.get("detail", ""),
            "working": ast.get("status") not in (None, "idle"),
        }
    active_proj_id = get_active_project_id()
    active_proj_name = ""
    if active_proj_id:
        meta = load_project_meta(active_proj_id)
        active_proj_name = meta.get("name", "")
    
    return {
        "state": state,
        "agents": agents_out,
        "xp": xp_data,
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%a %b %d"),
        "active_project": active_proj_name,
    }


# ─── WebSocket Events ────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    start_broadcast()
    emit("lab_status", get_lab_status())


@socketio.on("disconnect")
def on_disconnect():
    log.info(f"Client disconnected: {request.sid}")


@socketio.on("send_message")
def on_message(data):
    agent_id = data.get("agent_id", "main")
    text = data.get("text", "").strip()
    if not text:
        return

    agent = AGENTS.get(agent_id)
    if not agent:
        emit("error", {"message": f"Unknown agent: {agent_id}"})
        return

    ts = datetime.now().strftime("%H:%M")
    
    message_history[agent_id].append({"role": "user", "text": text, "ts": ts})
    active_proj = get_active_project_id()
    if active_proj:
        append_chat_message(active_proj, agent_id, "user", text, ts)
    
    emit("message_echo", {"agent_id": agent_id, "role": "user", "text": text, "ts": ts})

    from agents import _set_agent_status
    _set_agent_status(agent_id, "working", f"Processing: {text[:40]}…")
    emit("agent_status", {"agent_id": agent_id, "status": "working", "detail": text[:60]})

    sid = request.sid
    thread = threading.Thread(
        target=route_to_agent,
        args=(agent_id, agent, text, sid, message_history, socketio, publish_event),
        daemon=True,
    )
    thread.start()


@socketio.on("checkpoint_reply")
def on_checkpoint_reply(data):
    handle_checkpoint_reply(data)


# ─── Periodic Status Broadcast ────────────────────────────────────────────────

def _broadcast_status():
    while True:
        time.sleep(BROADCAST_INTERVAL)
        socketio.emit("lab_status", get_lab_status())


_broadcast_started = False


def start_broadcast():
    global _broadcast_started
    if _broadcast_started:
        return
    _broadcast_started = True
    threading.Thread(target=_broadcast_status, daemon=True).start()


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("LABOS_UI_PORT", 18792))
    log.info(f"🔬 LabOS UI running at http://127.0.0.1:{port}")
    start_broadcast()
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
