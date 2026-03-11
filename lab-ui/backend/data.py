"""LabOS Data Layer — projects, memory, reports, chat history."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from config import (
    DATA_DIR, PROJECTS_DIR, AGENTS_MEM_DIR, SHARED_DIR,
    ACTIVE_PROJECT_FILE, REPO_DIR, ROOT_DIR, LAB_DIR,
)

log = logging.getLogger("labos")


# ─── Data structure initialization ────────────────────────────────────────────

def ensure_data_structure():
    """Create data directory structure and migrate from LAB_CONFIG.json if needed."""
    DATA_DIR.mkdir(exist_ok=True)
    PROJECTS_DIR.mkdir(exist_ok=True)
    AGENTS_MEM_DIR.mkdir(exist_ok=True)
    SHARED_DIR.mkdir(exist_ok=True)
    
    # Initialize shared memory (LAB_MEMORY.md)
    shared_mem_file = REPO_DIR / "LAB_MEMORY.md"
    if not shared_mem_file.exists():
        shared_mem_file.write_text(json.dumps([], indent=2))
    
    # Migrate projects from LAB_CONFIG.json if data is empty
    config_file = ROOT_DIR.parent / "LAB_CONFIG.json"
    if config_file.exists() and not list(PROJECTS_DIR.iterdir()):
        try:
            config = json.loads(config_file.read_text())
            projects = config.get("projects", [])
            for proj in projects:
                project_id = str(uuid.uuid4())
                create_project_structure(
                    project_id,
                    proj.get("name", "Unnamed Project"),
                    proj.get("field", "Research"),
                    proj.get("created", datetime.now().isoformat())
                )
            if projects:
                set_active_project(list(PROJECTS_DIR.iterdir())[0].name)
        except Exception as e:
            log.warning(f"Could not migrate projects: {e}")
    
    # Initialize active project if not set
    if not ACTIVE_PROJECT_FILE.exists():
        project_dirs = list(PROJECTS_DIR.iterdir())
        if project_dirs:
            set_active_project(project_dirs[0].name)


# ─── Project CRUD ─────────────────────────────────────────────────────────────

def create_project_structure(project_id: str, name: str, field: str, created: str, description: str = ""):
    """Create directory structure for a new project."""
    proj_dir = PROJECTS_DIR / project_id
    proj_dir.mkdir(exist_ok=True)
    (proj_dir / "reports").mkdir(exist_ok=True)
    (proj_dir / "chats").mkdir(exist_ok=True)
    
    meta_file = proj_dir / "meta.json"
    meta_file.write_text(json.dumps({
        "id": project_id,
        "name": name,
        "field": field,
        "created": created,
        "description": description
    }, indent=2))
    
    memory_file = proj_dir / "memory.json"
    if not memory_file.exists():
        memory_file.write_text(json.dumps([], indent=2))


def get_active_project_id() -> str:
    """Get the currently active project ID."""
    if ACTIVE_PROJECT_FILE.exists():
        return ACTIVE_PROJECT_FILE.read_text().strip()
    return ""


def set_active_project(project_id: str):
    """Set the active project."""
    ACTIVE_PROJECT_FILE.write_text(project_id)


def load_project_meta(project_id: str) -> dict:
    """Load project metadata."""
    meta_file = PROJECTS_DIR / project_id / "meta.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    return {}


def save_project_meta(project_id: str, meta: dict):
    """Save project metadata."""
    meta_file = PROJECTS_DIR / project_id / "meta.json"
    meta_file.write_text(json.dumps(meta, indent=2))


# ─── Memory ───────────────────────────────────────────────────────────────────

def load_memory(file_path: Path) -> list:
    """Load memory entries from a JSON file."""
    if file_path.exists():
        try:
            return json.loads(file_path.read_text())
        except Exception:
            return []
    return []


def load_memory_md(file_path: Path) -> str:
    """Load memory from a markdown file."""
    if file_path.exists():
        try:
            return file_path.read_text().strip()
        except Exception:
            return ""
    return ""


def append_memory_md(file_path: Path, entry: str):
    """Append a memory entry to a markdown file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(file_path, "a") as f:
        f.write(f"\n- [{timestamp}] {entry}\n")


def save_memory(file_path: Path, entries: list):
    """Save memory entries to a JSON file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(entries, indent=2))


# ─── Chat History ─────────────────────────────────────────────────────────────

def append_chat_message(project_id: str, agent_id: str, role: str, text: str, ts: str):
    """Append a chat message to the project's chat log for an agent."""
    chat_file = PROJECTS_DIR / project_id / "chats" / f"{agent_id}.jsonl"
    chat_file.parent.mkdir(parents=True, exist_ok=True)
    
    message = {
        "role": role,
        "text": text,
        "ts": ts,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(chat_file, "a") as f:
        f.write(json.dumps(message) + "\n")


def load_chat_history(project_id: str, agent_id: str) -> list:
    """Load chat history for an agent in a project."""
    chat_file = PROJECTS_DIR / project_id / "chats" / f"{agent_id}.jsonl"
    if not chat_file.exists():
        return []
    
    messages = []
    try:
        with open(chat_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
    except Exception:
        pass
    return messages


# ─── Reports ──────────────────────────────────────────────────────────────────

def save_report(project_id: str, agent_id: str, agent_name: str, text: str):
    """Save a report for a project."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = PROJECTS_DIR / project_id / "reports" / f"{timestamp}_{agent_id}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "project_id": project_id
    }
    
    report_file.write_text(json.dumps(report, indent=2))


def load_reports(project_id: str) -> list:
    """Load all reports for a project."""
    reports_dir = PROJECTS_DIR / project_id / "reports"
    if not reports_dir.exists():
        return []
    
    reports = []
    for report_file in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            report = json.loads(report_file.read_text())
            report["filename"] = report_file.name
            reports.append(report)
        except Exception:
            pass
    return reports


# ─── Combined Memory Context ─────────────────────────────────────────────────

def get_combined_memory(agent_id: str) -> str:
    """Get combined memory context for an agent: agent memory + project memory + shared memory."""
    active_project = get_active_project_id()
    
    parts = []
    
    # Agent memory
    agent_mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
    agent_mem = load_memory(agent_mem_file)
    if agent_mem:
        parts.append("## Agent Memory (Personal Context):\n" + "\n".join(f"- {e['text'][:200]}" for e in agent_mem[-5:]))
    
    # Project memory
    if active_project:
        proj_mem_file = PROJECTS_DIR / active_project / "memory.json"
        proj_mem = load_memory(proj_mem_file)
        if proj_mem:
            parts.append("## Project Memory (Current Project):\n" + "\n".join(f"- {e['text']}" for e in proj_mem[-5:]))
    
    # Shared lab memory (LAB_MEMORY.md)
    lab_memory_file = REPO_DIR / "LAB_MEMORY.md"
    lab_memory = load_memory_md(lab_memory_file)
    if lab_memory:
        parts.append("## Lab Memory (Cross-Project):\n" + lab_memory)
    
    return "\n\n".join(parts) if parts else ""
