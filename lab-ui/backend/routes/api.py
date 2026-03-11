"""LabOS REST API routes — Flask Blueprint."""

import json
import uuid
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, send_from_directory

from config import AGENTS, FRONTEND_DIR, PROJECTS_DIR, AGENTS_MEM_DIR, SHARED_DIR, ROOT_DIR
from security import safe_path_component
from data import (
    get_active_project_id, set_active_project,
    load_project_meta, create_project_structure,
    load_reports, load_memory, save_memory, load_chat_history,
)
from xp import load_xp
from lab_manager import (
    get_active_quests, get_all_quests, get_agent_usage, get_agent_config,
    AGENT_REGISTRY, get_schedules, add_schedule, get_lab_summary,
)

log = logging.getLogger("labos")

api = Blueprint("api", __name__)


# ─── Static / Status ─────────────────────────────────────────────────────────

@api.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@api.route("/api/status")
def api_status():
    from app import get_lab_status
    return jsonify(get_lab_status())


@api.route("/api/agents")
def api_agents():
    return jsonify(AGENTS)


@api.route("/api/history/<agent_id>")
def api_history(agent_id):
    try:
        safe_path_component(agent_id)
    except ValueError:
        return jsonify({"error": "Invalid agent_id"}), 400
    from app import message_history
    return jsonify(message_history.get(agent_id, []))


# ─── Config / Init ────────────────────────────────────────────────────────────

@api.route("/api/config")
def api_config():
    config_file = ROOT_DIR.parent / "LAB_CONFIG.json"
    if config_file.exists():
        try:
            return jsonify(json.loads(config_file.read_text()))
        except Exception:
            pass
    return jsonify({})


@api.route("/api/init", methods=["POST"])
def api_init():
    data = request.json or {}
    lab_name = data.get("lab_name", "My Lab")
    obsidian_path = data.get("obsidian_path", "")
    notion_db = data.get("notion_db", "")
    zotero = data.get("zotero", False)
    project_name = data.get("project_name", "First Project")
    field = data.get("field", "Research")
    
    config = {
        "lab_name": lab_name,
        "integrations": {
            "obsidian": obsidian_path or None,
            "notion": notion_db or None,
            "zotero": zotero,
        },
        "projects": [{"name": project_name, "field": field, "created": datetime.now().isoformat()}],
        "created_at": datetime.now().isoformat(),
    }
    
    config_file = ROOT_DIR.parent / "LAB_CONFIG.json"
    try:
        config_file.write_text(json.dumps(config, indent=2))
        return jsonify({"ok": True, "config": config})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Projects ─────────────────────────────────────────────────────────────────

@api.route("/api/projects", methods=["GET"])
def api_projects_list():
    projects = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if proj_dir.is_dir():
            meta = load_project_meta(proj_dir.name)
            reports_count = len(list((proj_dir / "reports").glob("*.json")))
            chats_count = len(list((proj_dir / "chats").glob("*.jsonl")))
            projects.append({**meta, "reports_count": reports_count, "conversations_count": chats_count})
    projects.sort(key=lambda p: p.get("created", ""), reverse=True)
    return jsonify({"projects": projects, "active_project_id": get_active_project_id()})


@api.route("/api/projects", methods=["POST"])
def api_projects_create():
    data = request.json or {}
    name = data.get("name", "New Project")
    field = data.get("field", "Research")
    description = data.get("description", "")
    project_id = str(uuid.uuid4())
    create_project_structure(project_id, name, field, datetime.now().isoformat(), description)
    return jsonify({"ok": True, "project": load_project_meta(project_id)})


@api.route("/api/projects/<project_id>/activate", methods=["PUT"])
def api_projects_activate(project_id):
    try:
        safe_path_component(project_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid project_id"}), 400
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        return jsonify({"ok": False, "error": "Project not found"}), 404
    set_active_project(project_id)
    from app import message_history
    for agent_id in AGENTS:
        message_history[agent_id] = load_chat_history(project_id, agent_id)
    return jsonify({"ok": True})


# ─── Reports ──────────────────────────────────────────────────────────────────

@api.route("/api/projects/<project_id>/reports", methods=["GET"])
def api_projects_reports(project_id):
    try:
        safe_path_component(project_id)
    except ValueError:
        return jsonify({"error": "Invalid project_id"}), 400
    return jsonify({"reports": load_reports(project_id)})


@api.route("/api/reports", methods=["GET"])
def api_reports():
    project_id = get_active_project_id()
    if not project_id:
        return jsonify([])
    reports = load_reports(project_id)
    result = []
    for r in reports:
        title = "Untitled Report"
        for line in r.get("text", "").split("\n"):
            line = line.strip().lstrip("#").strip()
            if line:
                title = line[:80]
                break
        result.append({
            "filename": r.get("filename", ""),
            "title": title,
            "agent_id": r.get("agent_id", "unknown"),
            "timestamp": r.get("timestamp", ""),
        })
    return jsonify(result)


@api.route("/api/report/<filename>", methods=["GET"])
def api_report_detail(filename):
    try:
        safe_path_component(filename)
    except ValueError:
        return jsonify({"error": "Invalid filename"}), 400
    project_id = get_active_project_id()
    if not project_id:
        return jsonify({"error": "No active project"}), 404
    report_file = PROJECTS_DIR / project_id / "reports" / filename
    if not report_file.exists():
        return jsonify({"error": "Report not found"}), 404
    try:
        return jsonify(json.loads(report_file.read_text()))
    except Exception:
        return jsonify({"error": "Failed to read report"}), 500


# ─── Chat History ─────────────────────────────────────────────────────────────

@api.route("/api/projects/<project_id>/chats/<agent_id>", methods=["GET"])
def api_projects_chats(project_id, agent_id):
    try:
        safe_path_component(project_id)
        safe_path_component(agent_id)
    except ValueError:
        return jsonify({"error": "Invalid parameters"}), 400
    return jsonify({"messages": load_chat_history(project_id, agent_id)})


# ─── Memory ───────────────────────────────────────────────────────────────────

@api.route("/api/agents/<agent_id>/memory", methods=["GET"])
def api_agents_memory_get(agent_id):
    try:
        safe_path_component(agent_id)
    except ValueError:
        return jsonify({"error": "Invalid agent_id"}), 400
    return jsonify({"memory": load_memory(AGENTS_MEM_DIR / agent_id / "memory.json")})


@api.route("/api/agents/<agent_id>/memory", methods=["POST"])
def api_agents_memory_add(agent_id):
    try:
        safe_path_component(agent_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid agent_id"}), 400
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
    memory = load_memory(mem_file)
    memory.append({"text": text, "timestamp": datetime.now().isoformat()})
    save_memory(mem_file, memory)
    return jsonify({"ok": True})


@api.route("/api/projects/<project_id>/memory", methods=["GET"])
def api_projects_memory_get(project_id):
    try:
        safe_path_component(project_id)
    except ValueError:
        return jsonify({"error": "Invalid project_id"}), 400
    return jsonify({"memory": load_memory(PROJECTS_DIR / project_id / "memory.json")})


@api.route("/api/projects/<project_id>/memory", methods=["POST"])
def api_projects_memory_add(project_id):
    try:
        safe_path_component(project_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid project_id"}), 400
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    mem_file = PROJECTS_DIR / project_id / "memory.json"
    memory = load_memory(mem_file)
    memory.append({"text": text, "timestamp": datetime.now().isoformat()})
    save_memory(mem_file, memory)
    return jsonify({"ok": True})


@api.route("/api/memory", methods=["GET"])
def api_memory_get():
    return jsonify({"memory": load_memory(SHARED_DIR / "memory.json")})


@api.route("/api/memory", methods=["POST"])
def api_memory_add():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    mem_file = SHARED_DIR / "memory.json"
    memory = load_memory(mem_file)
    memory.append({"text": text, "timestamp": datetime.now().isoformat()})
    save_memory(mem_file, memory)
    return jsonify({"ok": True})


# ─── Quest Board & Lab Stats ─────────────────────────────────────────────────

@api.route("/api/quests", methods=["GET"])
def api_quests():
    show_all = request.args.get("all", "false") == "true"
    return jsonify(get_all_quests() if show_all else get_active_quests())


@api.route("/api/agents/<agent_id>/usage", methods=["GET"])
def api_agent_usage(agent_id):
    try:
        safe_path_component(agent_id)
    except ValueError:
        return jsonify({"error": "Invalid agent_id"}), 400
    return jsonify(get_agent_usage(agent_id))


@api.route("/api/agents/roster", methods=["GET"])
def api_agent_roster():
    roster = []
    for aid, reg in AGENT_REGISTRY.items():
        config = get_agent_config(aid)
        usage = get_agent_usage(aid)
        roster.append({**reg, **config, "usage": usage})
    return jsonify(roster)


@api.route("/api/lab/stats", methods=["GET"])
def api_lab_stats():
    roster_stats = []
    total_runs = 0
    total_cost = 0.0
    for aid in AGENT_REGISTRY:
        usage = get_agent_usage(aid)
        config = get_agent_config(aid)
        total_runs += usage.get("runs", 0)
        total_cost += usage.get("cost_usd", 0.0)
        roster_stats.append({
            "id": aid,
            "name": config.get("name", aid),
            "runs": usage.get("runs", 0),
            "lifecycle": config.get("lifecycle", "ephemeral"),
        })
    quests = get_all_quests(50)
    active = [q for q in quests if q["status"] == "active"]
    done = [q for q in quests if q["status"] == "done"]
    return jsonify({
        "total_runs": total_runs,
        "total_cost": total_cost,
        "active_quests": len(active),
        "completed_quests": len(done),
        "agents": roster_stats,
        "most_active": max(roster_stats, key=lambda a: a["runs"])["name"] if roster_stats else None,
    })


@api.route("/api/schedules", methods=["GET"])
def api_schedules():
    return jsonify(get_schedules())


@api.route("/api/schedules", methods=["POST"])
def api_add_schedule():
    data = request.json
    schedule = add_schedule(
        data.get("agent_id", "scout"),
        data.get("task", ""),
        data.get("cron_expr", "0 9 * * 1"),
        data.get("description", "")
    )
    return jsonify(schedule)


@api.route("/api/lab/summary", methods=["GET"])
def api_lab_summary():
    return jsonify({"summary": get_lab_summary()})


# ─── State Push ───────────────────────────────────────────────────────────────

@api.route("/api/push_state", methods=["POST"])
def push_state():
    from app import socketio
    from agents import _set_agent_status
    from config import STATE_FILE
    
    data = request.json or {}
    agent_id = data.get("agent_id", "main")
    status = data.get("status", "idle")
    detail = data.get("detail", "")

    _set_agent_status(agent_id, status, detail)
    socketio.emit("agent_status", {"agent_id": agent_id, "status": status, "detail": detail})

    STATE_FILE.write_text(json.dumps({
        "state": status, "detail": detail, "agent_id": agent_id,
        "progress": data.get("progress", 0),
        "updated_at": datetime.now().isoformat(),
    }, indent=2))

    return jsonify({"ok": True})
