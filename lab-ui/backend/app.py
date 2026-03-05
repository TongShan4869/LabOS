#!/usr/bin/env python3
"""
LabOS UI Backend
- Serves the pixel lab frontend
- WebSocket bridge: routes messages between UI and LabOS agents
- Spawns real skill scripts with checkpoint bridging
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
SKILLS_DIR   = ROOT_DIR.parent / "skills"
LAB_DIR      = Path(os.environ.get("LAB_DIR", Path.home() / ".openclaw/workspace/lab"))
STATE_FILE   = ROOT_DIR / "state.json"
AGENTS_FILE  = ROOT_DIR / "agents-state.json"
XP_FILE      = LAB_DIR / "xp.json"
MEMORY_DIR   = Path.home() / ".openclaw/workspace/memory"

# Python binary — use the venv if available
PYTHON_BIN   = os.environ.get("LABOS_PYTHON", sys.executable)

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Active agent conversations: {agent_id: {"process": Popen, ...}}
active_convos: dict = {}
# Message history per agent
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
    agent_id = data.get("agent_id", "main")
    text     = data.get("text", "").strip()
    if not text:
        return

    agent = AGENTS.get(agent_id)
    if not agent:
        emit("error", {"message": f"Unknown agent: {agent_id}"})
        return

    ts = datetime.now().strftime("%H:%M")
    message_history[agent_id].append({"role": "user", "text": text, "ts": ts})
    emit("message_echo", {"agent_id": agent_id, "role": "user", "text": text, "ts": ts})

    _set_agent_status(agent_id, "working", f"Processing: {text[:40]}…")
    emit("agent_status", {"agent_id": agent_id, "status": "working", "detail": text[:60]})

    sid = request.sid
    thread = threading.Thread(
        target=_route_to_agent,
        args=(agent_id, agent, text, sid),
        daemon=True,
    )
    thread.start()


def _route_to_agent(agent_id: str, agent: dict, text: str, sid: str):
    skill = agent.get("skill")
    if skill is None:
        response = _call_main_agent(agent_id, text)
        _emit_agent_reply(agent_id, agent, response, sid)
    else:
        _run_skill_interactive(agent_id, agent, skill, text, sid)


# ─── Skill argument extraction ────────────────────────────────────────────────

SKILL_ARG_SPECS = {
    "lab-lit-scout": {
        "script": "lab-lit-scout/lab_lit_scout.py",
        "required": ["--query"],
        "extract_prompt": (
            "Extract arguments for a literature search CLI from this user message.\n"
            "Available flags: --query/-q (search terms, REQUIRED), --project/-p (project name), "
            "--limit/-l (max papers 1-20), --since/-s (date YYYY-MM-DD), "
            "--sort (relevance|citations|date)\n"
            "Return ONLY a JSON object with keys matching flag names (without --). "
            'Example: {"query": "speech perception fMRI", "limit": 5}\n'
            "User message: "
        ),
    },
    "lab-biostat": {
        "script": "lab-biostat/lab_biostat.py",
        "required": ["--mode"],
        "extract_prompt": (
            "Extract arguments for a biostatistics CLI from this user message.\n"
            "Available flags: --mode/-m (REQUIRED, one of: design|analyze|interpret|power|review-methods|assumption-check), "
            "--project/-p (project name), --data/-d (CSV path), --question/-q (research question)\n"
            'Return ONLY a JSON object. Example: {"mode": "analyze", "data": "/path/to/data.csv"}\n'
            "User message: "
        ),
    },
    "lab-writing-assistant": {
        "script": "lab-writing-assistant/lab_writing_assistant.py",
        "required": ["--section"],
        "extract_prompt": (
            "Extract arguments for a writing assistant CLI.\n"
            "Flags: --section/-s (REQUIRED: intro|abstract|methods|results|discussion|grant-aim|cover-letter|response-to-reviewers), "
            "--project/-p, --draft/-d, --notes/-n\n"
            'Return ONLY JSON. Example: {"section": "abstract", "project": "speech-ASD"}\n'
            "User message: "
        ),
    },
    "lab-research-advisor": {
        "script": "lab-research-advisor/lab_research_advisor.py",
        "required": ["--project"],
        "extract_prompt": (
            "Extract arguments for a research advisor CLI.\n"
            "Flags: --project/-p (REQUIRED), --focus/-f (hypothesis|gaps|methods|writing|next-steps)\n"
            'Return ONLY JSON. Example: {"project": "neural-coupling", "focus": "hypothesis"}\n'
            "User message: "
        ),
    },
    "lab-peer-reviewer": {
        "script": "lab-peer-reviewer/lab_peer_reviewer.py",
        "required": ["--mode"],
        "extract_prompt": (
            "Extract arguments for a peer review CLI.\n"
            "Flags: --mode/-m (REQUIRED: peer-review|methods-critique|pre-submission|devils-advocate), "
            "--draft/-d, --project/-p\n"
            'Return ONLY JSON. Example: {"mode": "pre-submission"}\n'
            "User message: "
        ),
    },
    "lab-field-trend": {
        "script": "lab-field-trend/lab_field_trend.py",
        "required": [],
        "extract_prompt": (
            "Extract arguments for a field trend CLI.\n"
            "Flags: --weeks/-w (default 1), --fields/-f (comma-sep)\n"
            'Return ONLY JSON. Example: {"weeks": 2}\n'
            "User message: "
        ),
    },
    "lab-security": {
        "script": "lab-security/lab_security.py",
        "required": ["--mode"],
        "extract_prompt": (
            "Extract arguments for a security audit CLI.\n"
            "Flags: --mode/-m (REQUIRED: audit|check|classify|preflight), --project/-p, --path\n"
            'Return ONLY JSON. Example: {"mode": "audit"}\n'
            "User message: "
        ),
    },
    "lab-publishing-assistant": {
        "script": "lab-publishing-assistant/lab_publishing_assistant.py",
        "required": ["--mode"],
        "extract_prompt": (
            "Extract arguments for a publishing assistant CLI.\n"
            "Flags: --mode/-m (REQUIRED: find-journal|reformat|checklist|references|cover-letter), "
            "--project/-p, --draft/-d, --target-journal/-j\n"
            'Return ONLY JSON. Example: {"mode": "find-journal", "project": "speech-ASD"}\n'
            "User message: "
        ),
    },
}


def _extract_skill_args(skill: str, user_text: str) -> list[str]:
    """Use LLM to extract CLI arguments from natural language."""
    spec = SKILL_ARG_SPECS.get(skill)
    if not spec:
        return []

    prompt = spec["extract_prompt"] + user_text + "\nJSON:"
    raw = _run_llm(prompt)

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        args_dict = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        args_dict = {}
        if spec["required"]:
            key = spec["required"][0].lstrip("-")
            args_dict[key] = user_text

    cli_args = []
    for key, val in args_dict.items():
        flag = f"--{key}"
        if isinstance(val, bool):
            if val:
                cli_args.append(flag)
        elif val is not None:
            cli_args.append(flag)
            cli_args.append(str(val))

    return cli_args


# ─── Checkpoint bridging ─────────────────────────────────────────────────────

_checkpoint_events: dict = {}


@socketio.on("checkpoint_reply")
def on_checkpoint_reply(data):
    """User replies to a checkpoint prompt in the UI."""
    agent_id = data.get("agent_id", "")
    text = data.get("text", "").strip()
    entry = _checkpoint_events.get(agent_id)
    if entry:
        entry["reply"] = text
        entry["event"].set()


def _run_skill_interactive(agent_id: str, agent: dict, skill: str, text: str, sid: str):
    """
    Spawn the real skill script, bridge [CHECKPOINT] prompts through WebSocket,
    and stream output back as agent replies.
    """
    spec = SKILL_ARG_SPECS.get(skill)
    if not spec:
        _emit_agent_reply(agent_id, agent,
                          f"⚠️ Skill `{skill}` not configured for direct execution.", sid)
        return

    socketio.emit("agent_status", {
        "agent_id": agent_id, "status": "working",
        "detail": "Parsing your request…"
    }, to=sid)

    cli_args = _extract_skill_args(skill, text)

    script_path = SKILLS_DIR / spec["script"]
    if not script_path.exists():
        _emit_agent_reply(agent_id, agent,
                          f"⚠️ Script not found: {script_path}", sid)
        return

    cmd = [PYTHON_BIN, str(script_path)] + cli_args
    env = os.environ.copy()
    env["LAB_DIR"] = str(LAB_DIR)
    env["LABOS_UI_URL"] = f"http://127.0.0.1:{os.environ.get('LABOS_UI_PORT', '18792')}"

    socketio.emit("agent_status", {
        "agent_id": agent_id, "status": "working",
        "detail": f"Running: {agent['name']}…"
    }, to=sid)

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env,
            cwd=str(ROOT_DIR.parent),
        )
    except Exception as e:
        _emit_agent_reply(agent_id, agent, f"⚠️ Failed to start: {e}", sid)
        return

    active_convos[agent_id] = {"process": proc}
    output_lines = []

    try:
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip("\n")

            if line.startswith("[CHECKPOINT]"):
                prompt_text = line[len("[CHECKPOINT]"):].strip()

                if output_lines:
                    _emit_agent_reply(agent_id, agent, "\n".join(output_lines), sid)
                    output_lines = []

                socketio.emit("checkpoint", {
                    "agent_id":   agent_id,
                    "agent_name": agent["name"],
                    "prompt":     prompt_text,
                    "ts":         datetime.now().strftime("%H:%M"),
                }, to=sid)

                event = threading.Event()
                _checkpoint_events[agent_id] = {"event": event, "reply": ""}
                event.wait(timeout=300)

                reply = _checkpoint_events.pop(agent_id, {}).get("reply", "")
                if not reply:
                    reply = "abort"

                ts = datetime.now().strftime("%H:%M")
                message_history[agent_id].append({"role": "agent", "text": f"🔀 {prompt_text}", "ts": ts})
                message_history[agent_id].append({"role": "user", "text": reply, "ts": ts})

                try:
                    proc.stdin.write(reply + "\n")
                    proc.stdin.flush()
                except BrokenPipeError:
                    break

            elif line.startswith("[NOTIFY:"):
                msg = line.split("]", 1)[-1].strip() if "]" in line else line
                _emit_agent_reply(agent_id, agent, msg, sid)

            elif line.strip():
                output_lines.append(line)

        proc.wait(timeout=120)
        stderr = proc.stderr.read()

        if output_lines:
            _emit_agent_reply(agent_id, agent, "\n".join(output_lines), sid)

        if proc.returncode != 0 and stderr.strip():
            _emit_agent_reply(agent_id, agent,
                              f"⚠️ Error (exit {proc.returncode}):\n```\n{stderr[:500]}\n```", sid)

    except Exception as e:
        _emit_agent_reply(agent_id, agent, f"⚠️ Error: {e}", sid)
        proc.kill()
    finally:
        active_convos.pop(agent_id, None)
        _set_agent_status(agent_id, "idle", "")
        socketio.emit("agent_status", {
            "agent_id": agent_id, "status": "idle", "detail": ""
        }, to=sid)


def _emit_agent_reply(agent_id: str, agent: dict, text: str, sid: str):
    """Emit an agent reply and store in history."""
    ts = datetime.now().strftime("%H:%M")
    message_history[agent_id].append({
        "role": "agent", "text": text, "ts": ts, "agent_id": agent_id
    })
    socketio.emit("agent_reply", {
        "agent_id":   agent_id,
        "agent_name": agent["name"],
        "avatar":     agent["avatar"],
        "emoji":      agent["emoji"],
        "color":      agent["color"],
        "text":       text,
        "ts":         ts,
    }, to=sid)


# ─── Main agent (PI) ─────────────────────────────────────────────────────────

def _call_main_agent(agent_id: str, text: str) -> str:
    """Call claude CLI as the main 醋の虾 agent."""
    history = message_history.get(agent_id, [])[-6:]
    history_text = "\n".join(
        f"{'User' if m['role']=='user' else '醋の虾'}: {m['text']}"
        for m in history[:-1]
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


def _load_llm_env():
    """Load LLM config from .env file."""
    if os.environ.get("LLM_API_KEY"):
        return
    env_path = ROOT_DIR.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _run_llm(prompt: str) -> str:
    """Call LLM via OpenAI-compatible API."""
    _load_llm_env()
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return "⚠️ LLM not configured. Set LLM_API_KEY in .env"

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("LLM_API_BASE", "") or None,
        )
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3-0324"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"⚠️ LLM error: {e}"


def _set_agent_status(agent_id: str, status: str, detail: str):
    agents_st = load_agents_state()
    agents_st[agent_id] = {"status": status, "detail": detail,
                            "updated": datetime.now().isoformat()}
    AGENTS_FILE.write_text(json.dumps(agents_st, indent=2))


# ─── State push from LabOS skills ─────────────────────────────────────────────

@app.route("/api/push_state", methods=["POST"])
def push_state():
    data     = request.json or {}
    agent_id = data.get("agent_id", "main")
    status   = data.get("status", "idle")
    detail   = data.get("detail", "")

    _set_agent_status(agent_id, status, detail)
    socketio.emit("agent_status", {"agent_id": agent_id, "status": status, "detail": detail})

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
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
