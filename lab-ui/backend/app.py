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
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import uuid

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

# Filing Cabinet paths
DATA_DIR            = ROOT_DIR.parent / "data"
PROJECTS_DIR        = DATA_DIR / "projects"
AGENTS_MEM_DIR      = DATA_DIR / "agents"
SHARED_DIR          = DATA_DIR / "shared"
ACTIVE_PROJECT_FILE = DATA_DIR / "active_project.txt"



# ─── Agent System Prompts ─────────────────────────────────────────────────────

AGENT_PROMPTS = {
    "scout": """You are Scout, the Literature Search specialist in a research lab called LabOS.
You help researchers find, filter, and analyze scientific papers.

When the user asks you to search for papers, you should run the literature search skill.
When they ask about previous results, reference the conversation history — do NOT search again.
When they say "summarize the top 5" or similar, work with existing results from the conversation.

Be concise, use numbered lists for papers. You're a fellow researcher, not a search engine.
Always explain what you found and why it's relevant.""",

    "stat": """You are Stat, the Biostatistician in LabOS.
You help with statistical analysis, study design, power calculations, and methods review.

Ask clarifying questions before running complex analyses.
Explain statistical concepts in accessible terms.
When the user references previous analyses, use conversation history.""",

    "quill": """You are Quill, the Writing Assistant in LabOS.
You help draft, edit, and polish research papers, grants, and scientific writing.

Focus on clarity, structure, and scientific rigor.
When editing, explain your changes. When drafting, follow academic conventions.
Ask which section and what style/journal format they need.""",

    "sage": """You are Sage, the Research Advisor in LabOS.
You provide strategic research guidance — hypothesis refinement, methodology, career advice.

Think deeply before responding. Ask probing questions.
Challenge assumptions constructively. Help identify gaps and opportunities.
You're a senior mentor, not just an information source.""",

    "critic": """You are Critic, the Peer Reviewer in LabOS.
You review drafts and provide tough but constructive feedback.

Be specific about weaknesses. Suggest concrete improvements.
Check methodology, statistical claims, logical flow, and citation gaps.
You're preparing them for real peer review — be honest but helpful.""",

    "trend": """You are Trend, the Field Monitor in LabOS.
You track emerging trends, new papers, and developments in the researcher's fields.

Provide concise digests. Highlight what's genuinely new vs incremental.
Connect trends to the researcher's ongoing projects when relevant.""",

    "warden": """You are Warden, the Security & Compliance agent in LabOS.
You handle data security, IRB compliance, and research integrity.

Be thorough but not paranoid. Focus on actionable recommendations.
Check for common issues: data handling, consent, conflicts of interest.""",

    "main": """You are the Principal Investigator (PI) of this research lab.
You coordinate the team, set priorities, and make strategic decisions.
Help the researcher think about their overall research program.""",
}

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


# ─── Agent System Prompts (Intelligent Agent Loop) ───────────────────────────

AGENT_PROMPTS = {
    "main": """You are 醋の虾 (Cu's Lobster), the PI of this virtual research lab running LabOS.

Your personality: Helpful, direct, occasionally witty. You coordinate the lab and advise on projects.

RULES:
- Keep responses concise (2-4 sentences for dialogue)
- Reference conversation history naturally
- You don't run tools yourself — you coordinate other lab agents
- Be conversational, not robotic

If the user needs specialized help, suggest the right agent (Scout for literature, Stat for analysis, etc.).""",

    "scout": """You are Scout, the Literature Search specialist in LabOS.

CAPABILITIES:
- Run literature searches across PubMed, OpenAlex, and arXiv
- Summarize papers and assess relevance
- Track search history and learned preferences

TOOL: To run a NEW literature search, output exactly:
[TOOL_CALL]{"tool": "search", "args": {"query": "search terms", "limit": 10}}[/TOOL_CALL]

Available args: query (required), limit (1-20), since (YYYY-MM-DD), sort (relevance|citations|date), project

IMPORTANT RULES:
- Only search when the user wants NEW papers
- If they ask "where is the paper?" or "what did we find?", reference conversation history — don't search again
- If they say "summarize top 5" after a search, work with existing results — do NOT search again
- When you do search, explain what you're doing briefly
- Be concise but thorough — you're a researcher, not a search engine
- Always reference previous context when relevant""",

    "stat": """You are Stat, the Biostatistician in LabOS.

CAPABILITIES:
- Statistical analysis and study design
- Power calculations and assumption checking
- Methods review and interpretation

TOOL: To run statistical analysis:
[TOOL_CALL]{"tool": "analyze", "args": {"mode": "design", "question": "..."}}[/TOOL_CALL]

Available args: mode (required: design|analyze|interpret|power|review-methods|assumption-check), project, data (CSV path), question

RULES:
- Ask clarifying questions before running complex analyses
- If they reference "the data" or "those results", use conversation history
- Explain statistical concepts in accessible terms
- Only run analysis when actually needed — chat about stats freely""",

    "quill": """You are Quill, the Writing Assistant in LabOS.

CAPABILITIES:
- Draft academic sections (intro, methods, results, discussion, abstract)
- Grant proposals and cover letters
- Response to reviewers

TOOL: To generate a draft:
[TOOL_CALL]{"tool": "draft", "args": {"section": "abstract", "project": "..."}}[/TOOL_CALL]

Available args: section (required: intro|abstract|methods|results|discussion|grant-aim|cover-letter|response-to-reviewers), project, draft (path), notes

RULES:
- Discuss the outline and approach before drafting
- If they say "make it shorter" or "add more detail", work with existing draft from history
- Only run the tool when you need to generate NEW text
- Be collaborative — you're a writing partner, not a ghostwriter""",

    "sage": """You are Sage, the Research Advisor in LabOS.

CAPABILITIES:
- Research strategy and hypothesis refinement
- Literature gap analysis
- Methods consultation and next steps planning

TOOL: To run deep analysis:
[TOOL_CALL]{"tool": "advise", "args": {"project": "...", "focus": "hypothesis"}}[/TOOL_CALL]

Available args: project (required), focus (hypothesis|gaps|methods|writing|next-steps)

RULES:
- Have a conversation first — understand the context
- Only run the tool for deep, systematic analysis
- Reference conversation history for context
- Give thoughtful advice even without running tools""",

    "critic": """You are Critic, the Peer Reviewer in LabOS.

CAPABILITIES:
- Peer review simulation
- Methods critique and pre-submission checks
- Devil's advocate challenges

TOOL: To run a formal review:
[TOOL_CALL]{"tool": "review", "args": {"mode": "peer-review"}}[/TOOL_CALL]

Available args: mode (required: peer-review|methods-critique|pre-submission|devils-advocate), draft (path), project

RULES:
- Be constructive but honest
- Discuss concerns conversationally before running formal review
- Only run the tool for comprehensive reviews
- Quick questions don't need the full tool""",

    "trend": """You are Trend, the Field Monitor in LabOS.

CAPABILITIES:
- Monitor research trends in your configured fields
- Weekly digest generation
- Hot topic identification

TOOL: To generate a field digest:
[TOOL_CALL]{"tool": "digest", "args": {"weeks": 1}}[/TOOL_CALL]

Available args: weeks (default 1), fields (comma-separated)

RULES:
- Chat about trends naturally
- Only run the tool when they want a formal digest
- Reference previous digests from conversation history""",

    "warden": """You are Warden, the Security specialist in LabOS.

CAPABILITIES:
- Security audits and data classification
- Access control and compliance checks
- Pre-submission security review

TOOL: To run a security check:
[TOOL_CALL]{"tool": "secure", "args": {"mode": "audit"}}[/TOOL_CALL]

Available args: mode (required: audit|check|classify|preflight), project, path

RULES:
- Discuss security concerns conversationally
- Only run the tool for formal audits
- Be vigilant but not alarmist""",
}

# ─── Agent Tool Mappings ──────────────────────────────────────────────────────

AGENT_TOOLS = {
    "scout": {
        "search": {
            "script": "lab-lit-scout/lab_lit_scout.py",
            "arg_map": {"query": "--query", "limit": "--limit", "since": "--since", "sort": "--sort", "project": "--project"}
        }
    },
    "stat": {
        "analyze": {
            "script": "lab-biostat/lab_biostat.py",
            "arg_map": {"mode": "--mode", "project": "--project", "data": "--data", "question": "--question"}
        }
    },
    "quill": {
        "draft": {
            "script": "lab-writing-assistant/lab_writing_assistant.py",
            "arg_map": {"section": "--section", "project": "--project", "draft": "--draft", "notes": "--notes"}
        }
    },
    "sage": {
        "advise": {
            "script": "lab-research-advisor/lab_research_advisor.py",
            "arg_map": {"project": "--project", "focus": "--focus"}
        }
    },
    "critic": {
        "review": {
            "script": "lab-peer-reviewer/lab_peer_reviewer.py",
            "arg_map": {"mode": "--mode", "draft": "--draft", "project": "--project"}
        }
    },
    "trend": {
        "digest": {
            "script": "lab-field-trend/lab_field_trend.py",
            "arg_map": {"weeks": "--weeks", "fields": "--fields"}
        }
    },
    "warden": {
        "secure": {
            "script": "lab-security/lab_security.py",
            "arg_map": {"mode": "--mode", "project": "--project", "path": "--path"}
        }
    },
}


# ─── Clear stale agent state on startup ──────────────────────────────────────
for _f in [ROOT_DIR / "state.json", ROOT_DIR / "agents-state.json"]:
    if _f.exists():
        _f.unlink()


# ─── Filing Cabinet: Data migration & initialization ─────────────────────────

def _ensure_data_structure():
    """Create data directory structure and migrate from LAB_CONFIG.json if needed."""
    DATA_DIR.mkdir(exist_ok=True)
    PROJECTS_DIR.mkdir(exist_ok=True)
    AGENTS_MEM_DIR.mkdir(exist_ok=True)
    SHARED_DIR.mkdir(exist_ok=True)
    
    # Initialize shared memory (LAB_MEMORY.md)
    shared_mem_file = LAB_DIR / "LAB_MEMORY.md"
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
                _create_project_structure(
                    project_id,
                    proj.get("name", "Unnamed Project"),
                    proj.get("field", "Research"),
                    proj.get("created", datetime.now().isoformat())
                )
            # Set first project as active
            if projects:
                _set_active_project(list(PROJECTS_DIR.iterdir())[0].name)
        except Exception as e:
            print(f"Warning: Could not migrate projects: {e}")
    
    # Initialize active project if not set
    if not ACTIVE_PROJECT_FILE.exists():
        project_dirs = list(PROJECTS_DIR.iterdir())
        if project_dirs:
            _set_active_project(project_dirs[0].name)
        else:
            # Create default project
            default_id = str(uuid.uuid4())
            _create_project_structure(default_id, "Default Project", "Research", datetime.now().isoformat())
            _set_active_project(default_id)


def _create_project_structure(project_id: str, name: str, field: str, created: str, description: str = ""):
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


def _get_active_project_id() -> str:
    """Get the currently active project ID."""
    if ACTIVE_PROJECT_FILE.exists():
        return ACTIVE_PROJECT_FILE.read_text().strip()
    return ""


def _set_active_project(project_id: str):
    """Set the active project."""
    ACTIVE_PROJECT_FILE.write_text(project_id)


def _load_project_meta(project_id: str) -> dict:
    """Load project metadata."""
    meta_file = PROJECTS_DIR / project_id / "meta.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    return {}


def _save_project_meta(project_id: str, meta: dict):
    """Save project metadata."""
    meta_file = PROJECTS_DIR / project_id / "meta.json"
    meta_file.write_text(json.dumps(meta, indent=2))


def _load_memory(file_path: Path) -> list:
    """Load memory entries from a JSON file."""
    if file_path.exists():
        try:
            return json.loads(file_path.read_text())
        except Exception:
            return []
    return []


def _load_memory_md(file_path: Path) -> str:
    """Load memory from a markdown file."""
    if file_path.exists():
        try:
            return file_path.read_text().strip()
        except Exception:
            return ""
    return ""


def _append_memory_md(file_path: Path, entry: str):
    """Append a memory entry to a markdown file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(file_path, "a") as f:
        f.write(f"\n- [{timestamp}] {entry}\n")


def _save_memory(file_path: Path, entries: list):
    """Save memory entries to a JSON file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(entries, indent=2))


def _append_chat_message(project_id: str, agent_id: str, role: str, text: str, ts: str):
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


def _load_chat_history(project_id: str, agent_id: str) -> list:
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


def _save_report(project_id: str, agent_id: str, agent_name: str, text: str):
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


def _load_reports(project_id: str) -> list:
    """Load all reports for a project."""
    reports_dir = PROJECTS_DIR / project_id / "reports"
    if not reports_dir.exists():
        return []
    
    reports = []
    for report_file in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            report = json.loads(report_file.read_text())
            reports.append(report)
        except Exception:
            pass
    return reports


def _get_combined_memory(agent_id: str) -> str:
    """Get combined memory context for an agent: agent memory + project memory + shared memory."""
    active_project = _get_active_project_id()
    
    parts = []
    
    # Agent memory
    agent_mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
    agent_mem = _load_memory(agent_mem_file)
    if agent_mem:
        parts.append("## Agent Memory (Personal Context):\n" + "\n".join(f"- {e['text'][:200]}" for e in agent_mem[-5:]))
    
    # Project memory
    if active_project:
        proj_mem_file = PROJECTS_DIR / active_project / "memory.json"
        proj_mem = _load_memory(proj_mem_file)
        if proj_mem:
            parts.append("## Project Memory (Current Project):\n" + "\n".join(f"- {e['text']}" for e in proj_mem[-5:]))
    
    # Shared lab memory (LAB_MEMORY.md)
    lab_memory_file = LAB_DIR / "LAB_MEMORY.md"
    lab_memory = _load_memory_md(lab_memory_file)
    if lab_memory:
        # Inject full lab memory (markdown is compact enough)
        recent = lab_memory
        parts.append("## Lab Memory (Cross-Project):\n" + recent)
    
    return "\n\n".join(parts) if parts else ""


# Initialize data structure on startup
_ensure_data_structure()

# ─── App setup ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("LABOS_SECRET", "labos-dev-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Active agent conversations: {agent_id: {"process": Popen, ...}}
active_convos: dict = {}
# Message history per agent (in-memory, now also persisted to disk)
message_history: dict = {aid: [] for aid in AGENTS}

# Load chat history for active project on startup
active_proj = _get_active_project_id()
if active_proj:
    for agent_id in AGENTS:
        message_history[agent_id] = _load_chat_history(active_proj, agent_id)


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


LEVEL_TITLES = {
    1: "Confused First-Year",
    2: "Lab Gremlin",
    3: "Professional Coffee Drinker",
    4: "PhD Candidate",
    5: "Doctor of Suffering",
    6: "Postdoc (Indentured Servant Edition)",
    7: "Assistant Prof (Tenure Clock Ticking)",
    8: "Peer Review Survivor",
    9: "Grant Guru",
    10: "Manuscript Maestro",
    11: "Tenured Legend",
    12: "Nobel Laureate",
    13: "Cited More Than Darwin",
    14: "The Field IS You",
    15: "The Omniscient and Omnipotent Being of the Universe 🌌",
}

def _calc_level(xp: int) -> tuple:
    level = 1
    cumulative = 0
    while True:
        needed = level * 150
        if cumulative + needed > xp:
            return level, LEVEL_TITLES.get(level, f"Level {level}"), needed, cumulative
        cumulative += needed
        level += 1

def _award_xp_backend(amount: int, event: str, badge: str = None):
    """Award XP from the backend (for agent interactions)."""
    try:
        data = json.loads(XP_FILE.read_text()) if XP_FILE.exists() else {"xp": 0, "badges": [], "history": []}
        data["xp"] = data.get("xp", 0) + amount
        if badge and badge not in data.get("badges", []):
            data.setdefault("badges", []).append(badge)
        data.setdefault("history", []).append({
            "event": event,
            "xp": amount,
            "timestamp": datetime.now().isoformat()
        })
        # Recalculate level
        level, title, xp_next, _ = _calc_level(data["xp"])
        data["level"] = level
        data["level_title"] = title
        data["xp_to_next"] = xp_next
        XP_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"[XP] Error: {e}")


def load_xp() -> dict:
    data = {"xp": 0, "level": 1, "level_title": "Confused First-Year", "badges": []}
    if XP_FILE.exists():
        try:
            data = json.loads(XP_FILE.read_text())
        except Exception:
            pass
    # Always recalculate level from total XP
    level, title, xp_next, xp_cumulative = _calc_level(data.get("xp", 0))
    data["level"] = level
    data["level_title"] = title
    data["xp_to_next"] = xp_next
    data["xp_in_level"] = data.get("xp", 0) - xp_cumulative
    data["levels"] = {str(k): v for k, v in LEVEL_TITLES.items()}
    return data


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
    # Include active project info
    active_proj_id = _get_active_project_id()
    active_proj_name = ""
    if active_proj_id:
        meta = _load_project_meta(active_proj_id)
        active_proj_name = meta.get("name", "")
    
    return {
        "state":          state,
        "agents":         agents_out,
        "xp":             xp_data,
        "time":           datetime.now().strftime("%H:%M"),
        "date":           datetime.now().strftime("%a %b %d"),
        "active_project": active_proj_name,
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




# ─── Filing Cabinet API endpoints ────────────────────────────────────────────

@app.route("/api/projects", methods=["GET"])
def api_projects_list():
    """List all projects with metadata and counts."""
    projects = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if proj_dir.is_dir():
            meta = _load_project_meta(proj_dir.name)
            reports_count = len(list((proj_dir / "reports").glob("*.json")))
            chats_count = len(list((proj_dir / "chats").glob("*.jsonl")))
            
            projects.append({
                **meta,
                "reports_count": reports_count,
                "conversations_count": chats_count,
            })
    
    # Sort by creation date (newest first)
    projects.sort(key=lambda p: p.get("created", ""), reverse=True)
    
    active_id = _get_active_project_id()
    return jsonify({
        "projects": projects,
        "active_project_id": active_id
    })


@app.route("/api/projects", methods=["POST"])
def api_projects_create():
    """Create a new project."""
    data = request.json or {}
    name = data.get("name", "New Project")
    field = data.get("field", "Research")
    description = data.get("description", "")
    
    project_id = str(uuid.uuid4())
    _create_project_structure(project_id, name, field, datetime.now().isoformat(), description)
    
    meta = _load_project_meta(project_id)
    return jsonify({"ok": True, "project": meta})


@app.route("/api/projects/<project_id>/activate", methods=["PUT"])
def api_projects_activate(project_id):
    """Set the active project."""
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        return jsonify({"ok": False, "error": "Project not found"}), 404
    
    _set_active_project(project_id)
    
    # Reload chat history for all agents
    global message_history
    for agent_id in AGENTS:
        message_history[agent_id] = _load_chat_history(project_id, agent_id)
    
    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>/reports", methods=["GET"])
def api_projects_reports(project_id):
    """Get all reports for a project."""
    reports = _load_reports(project_id)
    return jsonify({"reports": reports})


@app.route("/api/projects/<project_id>/chats/<agent_id>", methods=["GET"])
def api_projects_chats(project_id, agent_id):
    """Get chat history for an agent in a project."""
    history = _load_chat_history(project_id, agent_id)
    return jsonify({"messages": history})


@app.route("/api/agents/<agent_id>/memory", methods=["GET"])
def api_agents_memory_get(agent_id):
    """Get agent memory."""
    mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
    memory = _load_memory(mem_file)
    return jsonify({"memory": memory})


@app.route("/api/agents/<agent_id>/memory", methods=["POST"])
def api_agents_memory_add(agent_id):
    """Add entry to agent memory."""
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    
    mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
    memory = _load_memory(mem_file)
    memory.append({
        "text": text,
        "timestamp": datetime.now().isoformat()
    })
    _save_memory(mem_file, memory)
    
    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>/memory", methods=["GET"])
def api_projects_memory_get(project_id):
    """Get project memory."""
    mem_file = PROJECTS_DIR / project_id / "memory.json"
    memory = _load_memory(mem_file)
    return jsonify({"memory": memory})


@app.route("/api/projects/<project_id>/memory", methods=["POST"])
def api_projects_memory_add(project_id):
    """Add entry to project memory."""
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    
    mem_file = PROJECTS_DIR / project_id / "memory.json"
    memory = _load_memory(mem_file)
    memory.append({
        "text": text,
        "timestamp": datetime.now().isoformat()
    })
    _save_memory(mem_file, memory)
    
    return jsonify({"ok": True})


@app.route("/api/memory", methods=["GET"])
def api_memory_get():
    """Get shared lab memory."""
    mem_file = SHARED_DIR / "memory.json"
    memory = _load_memory(mem_file)
    return jsonify({"memory": memory})


@app.route("/api/memory", methods=["POST"])
def api_memory_add():
    """Add entry to shared lab memory."""
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Empty text"}), 400
    
    mem_file = SHARED_DIR / "memory.json"
    memory = _load_memory(mem_file)
    memory.append({
        "text": text,
        "timestamp": datetime.now().isoformat()
    })
    _save_memory(mem_file, memory)
    
    return jsonify({"ok": True})


# ─── WebSocket: agent conversation ────────────────────────────────────────────


@app.route("/api/config")
def api_config():
    config_file = ROOT_DIR.parent / "LAB_CONFIG.json"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            return jsonify(config)
        except Exception:
            pass
    return jsonify({})


@app.route("/api/init", methods=["POST"])
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
            "obsidian": obsidian_path if obsidian_path else None,
            "notion": notion_db if notion_db else None,
            "zotero": zotero,
        },
        "projects": [
            {
                "name": project_name,
                "field": field,
                "created": datetime.now().isoformat(),
            }
        ],
        "created_at": datetime.now().isoformat(),
    }
    
    config_file = ROOT_DIR.parent / "LAB_CONFIG.json"
    try:
        config_file.write_text(json.dumps(config, indent=2))
        return jsonify({"ok": True, "config": config})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
    
    # Store in memory and persist to disk
    message_history[agent_id].append({"role": "user", "text": text, "ts": ts})
    active_proj = _get_active_project_id()
    if active_proj:
        _append_chat_message(active_proj, agent_id, "user", text, ts)
    
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
    """Intelligent agent loop — LLM decides whether to chat or run a skill."""
    skill = agent.get("skill")
    
    # Build context: system prompt + memory + conversation history
    system_prompt = AGENT_PROMPTS.get(agent_id, "You are a helpful research assistant.")
    system_prompt += """\n\nFORMATTING: Always format responses in Markdown (##, bullets, **bold**, tables).

PAPER SUMMARIES: When summarizing or discussing papers, ALWAYS include for EACH paper:
- **Full title** and year
- **Authors** (full list)
- **Journal** name
- **Corresponding author affiliation/institution**
- **DOI** as clickable link: [doi](https://doi.org/doi)
- **TLDR** (2-3 sentence summary)
- Key findings, methods, limitations

NEVER omit author, affiliation, or journal info from paper summaries. This metadata is critical for researchers."""
    memory_ctx = _get_combined_memory(agent_id)
    
    # Get recent conversation history (limited to avoid token overflow)
    history = message_history.get(agent_id, [])[-10:]
    # Truncate long messages to keep context manageable
    history = [{"role": m["role"], "text": m["text"][:500]} for m in history]
    
    # Build messages for LLM
    system_text = system_prompt
    if memory_ctx:
        system_text += f"\n\n--- MEMORY ---\n{memory_ctx}"
    
    if skill:
        system_text += f"""\n\n--- TOOL ---
You have access to ONE tool: {skill}
You MUST ONLY use it when the user EXPLICITLY asks for a new search/analysis/task.

To use the tool, your response must START with exactly: [RUN_SKILL]
followed by what you want to search/analyze.

DO NOT use the tool for:
- Greetings ("hi", "hello")
- Questions about your capabilities ("what can you do?")
- Follow-up questions about previous results
- General conversation
- Anything that is NOT a direct request for new work

For those, just respond normally as a helpful research assistant.
When asked "what can you do?", explain your role and capabilities in plain text."""
    
    messages = [{"role": "system", "content": system_text}]
    for msg in history[:-1]:  # exclude the current message (already in history)
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["text"]})
    messages.append({"role": "user", "content": text})
    
    # Call LLM
    response = _run_llm(messages)
    
    # Check if agent wants to run a skill
    has_tool_call = "[RUN_SKILL]" in response or "[TOOL_CALL]" in response
    if has_tool_call and skill:
        # Agent decided to use its skill — run it
        import re
        # Strip tool call markers and JSON
        clean_response = re.sub(r'\[/?TOOL_CALL\].*?(?=\[/TOOL_CALL\]|$)', '', response, flags=re.DOTALL)
        clean_response = re.sub(r'\[/?TOOL_CALL\]', '', clean_response)
        clean_response = clean_response.replace("[RUN_SKILL]", "").strip()
        if clean_response:
            _emit_agent_reply(agent_id, agent, clean_response + "\n\n⏳ Running skill...", sid)
        _run_skill_interactive(agent_id, agent, skill, text, sid)
    else:
        # Pure conversational response
        _emit_agent_reply(agent_id, agent, response, sid)
        # Save long conversational responses as reports too
        active_proj = _get_active_project_id()
        if active_proj and len(response) > 500:
            _save_report(active_proj, agent_id, agent["name"], response)
        # Award XP for agent conversation
        _award_xp_backend(10, f"Chat with {agent['name']}")
        _set_agent_status(agent_id, "idle", "")
        socketio.emit("agent_status", {"agent_id": agent_id, "status": "idle", "detail": ""}, to=sid)
        
        # Smart memory extraction (async — don't block the reply)
        mem_thread = threading.Thread(
            target=_extract_memory,
            args=(agent_id, agent["name"], text, response),
            daemon=True,
        )
        mem_thread.start()



def _extract_memory(agent_id: str, agent_name: str, user_msg: str, agent_response: str):
    """Ask LLM if anything from this conversation is worth remembering."""
    try:
        prompt = f"""You are a memory curator for a research lab AI agent called {agent_name}.

Review this conversation exchange and decide if anything is worth saving to long-term memory.

USER said: {user_msg[:500]}
AGENT replied: {agent_response[:500]}

Worth remembering: corrections, preferences, key decisions, research insights, important facts about the user or their work. 

NOT worth remembering: greetings, small talk, generic questions, things already known.

If something is worth saving, respond with ONLY the memory entry (1-2 concise sentences, no quotes).
If nothing is worth saving, respond with exactly: NOTHING

Examples of good memory entries:
- User prefers APA citation style over MLA
- User's current hypothesis: subcortical encoding is modality-general
- User corrected: Martinez-Molina 2024 is about music training, not ASD
- User wants to focus on papers from 2020 onwards for the neural coupling project"""

        result = _run_llm(prompt, max_tokens=150)
        result = result.strip()
        
        if result and result != "NOTHING" and len(result) > 5 and len(result) < 300:
            # Save to agent memory (markdown)
            agent_mem_file = AGENTS_MEM_DIR / agent_id / "memory.md"
            _append_memory_md(agent_mem_file, result)
            
            # Also save to LAB_MEMORY.md if it seems globally relevant
            global_keywords = ["prefer", "always", "never", "style", "format", "field", "hypothesis", "focus", "background", "corrected"]
            if any(kw in result.lower() for kw in global_keywords):
                lab_mem_file = LAB_DIR / "LAB_MEMORY.md"
                _append_memory_md(lab_mem_file, f"[{agent_name}] {result}")
            
            print(f"[MEMORY] {agent_name} saved: {result[:80]}")
    except Exception as e:
        print(f"[MEMORY] extraction failed: {e}")

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
    """User replies to a checkpoint prompt in the UI. Translates natural language to script format."""
    agent_id = data.get("agent_id", "")
    text = data.get("text", "").strip()
    entry = _checkpoint_events.get(agent_id)
    if entry:
        # Use LLM to translate natural language to the format the script expects
        checkpoint_prompt = entry.get("prompt", "")
        translated = _translate_checkpoint_reply(text, checkpoint_prompt)
        entry["reply"] = translated
        entry["event"].set()


def _translate_checkpoint_reply(user_text: str, checkpoint_prompt: str) -> str:
    """Translate natural language checkpoint reply into script-expected format."""
    # Quick pass-through for simple inputs
    lower = user_text.lower().strip()
    if lower in ("all", "done", "yes", "no", "y", "n"):
        return user_text
    # If it's already just numbers/commas, pass through
    import re
    if re.match(r"^[\d,\s]+$", lower):
        return user_text
    
    # Use LLM to translate
    prompt = f"""The user is replying to this checkpoint prompt from a research tool:
"{checkpoint_prompt}"

The user said: "{user_text}"

The tool expects one of these formats:
- "all" to select all items
- Comma-separated numbers like "1,2,3,4,5" to select specific items
- A single number like "5" for one item  
- "done" to finish

Translate the user's intent into the expected format. Reply with ONLY the translated input, nothing else.
Examples:
- "summarize the first 5 relevant papers" → "1,2,3,4,5"
- "give me all of them" → "all"
- "papers 3, 7, and 10" → "3,7,10"
- "the top 3" → "1,2,3"
- "I'm done" → "done"
"""
    result = _run_llm(prompt)
    # Clean up LLM response — extract just the command
    result = result.strip().strip('"').strip("'").strip()
    # Validate: if it looks reasonable, use it; otherwise fall back to original
    if re.match(r"^(all|done|[\d,\s]+)$", result.lower()):
        return result
    return user_text


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
                _checkpoint_events[agent_id] = {"event": event, "reply": "", "prompt": prompt_text}
                event.wait(timeout=300)

                reply = _checkpoint_events.pop(agent_id, {}).get("reply", "")
                if not reply:
                    reply = "abort"

                ts = datetime.now().strftime("%H:%M")
                message_history[agent_id].append({"role": "agent", "text": f"🔀 {prompt_text}", "ts": ts})
                message_history[agent_id].append({"role": "user", "text": reply, "ts": ts})
                
                # Persist checkpoint messages
                active_proj = _get_active_project_id()
                if active_proj:
                    _append_chat_message(active_proj, agent_id, "agent", f"🔀 {prompt_text}", ts)
                    _append_chat_message(active_proj, agent_id, "user", reply, ts)

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
            final_text = "\n".join(output_lines)
            _emit_agent_reply(agent_id, agent, final_text, sid)
            
            # Auto-save as report if long enough
            active_proj = _get_active_project_id()
            if active_proj and len(final_text) > 200:
                _save_report(active_proj, agent_id, agent["name"], final_text)
                print(f"[REPORT] Saved report for {agent_id} ({len(final_text)} chars)")
                # Award XP for skill completion
                _award_xp_backend(50, f"Skill run: {skill}", f"🔬 Literature Dive")

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
    
    # Persist to disk
    active_proj = _get_active_project_id()
    if active_proj:
        _append_chat_message(active_proj, agent_id, "agent", text, ts)
        
        # Auto-save agent memory for key findings
        if len(text) > 50:  # Only for substantial responses
            _auto_extract_memory(agent_id, text)
    
    socketio.emit("agent_reply", {
        "agent_id":   agent_id,
        "agent_name": agent["name"],
        "avatar":     agent["avatar"],
        "emoji":      agent["emoji"],
        "color":      agent["color"],
        "text":       text,
        "ts":         ts,
    }, to=sid)


def _auto_extract_memory(agent_id: str, text: str):
    """Auto-extract and save agent memory from substantial responses."""
    # Simple extraction: save a summary line based on agent type
    agent = AGENTS.get(agent_id)
    if not agent:
        return
    
    summary = ""
    if agent_id == "scout":
        if "searched" in text.lower() or "found" in text.lower():
            summary = f"Literature search completed"
    elif agent_id == "stat":
        if "analysis" in text.lower() or "results" in text.lower():
            summary = f"Statistical analysis performed"
    elif agent_id == "quill":
        if "draft" in text.lower() or "section" in text.lower():
            summary = f"Writing assistance provided"
    elif agent_id == "sage":
        if "hypothesis" in text.lower() or "recommend" in text.lower():
            summary = f"Research advice given"
    elif agent_id == "critic":
        if "review" in text.lower() or "suggest" in text.lower():
            summary = f"Peer review feedback provided"
    elif agent_id == "trend":
        if "trend" in text.lower() or "digest" in text.lower():
            summary = f"Field trends monitored"
    
    if summary:
        mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
        memory = _load_memory(mem_file)
        memory.append({
            "text": summary,
            "timestamp": datetime.now().isoformat()
        })
        _save_memory(mem_file, memory)


# ─── Main agent (PI) ─────────────────────────────────────────────────────────

def _call_main_agent(agent_id: str, text: str) -> str:
    """Call claude CLI as the main 醋の虾 agent."""
    history = message_history.get(agent_id, [])[-6:]
    history_text = "\n".join(
        f"{'User' if m['role']=='user' else '醋の虾'}: {m['text']}"
        for m in history[:-1]
    )
    
    # Include memory context
    memory_context = _get_combined_memory(agent_id)
    
    prompt = (
        "You are 醋の虾 (Cu's Lobster), the PI of a virtual research lab running LabOS. "
        "You are helpful, direct, and occasionally witty. "
        "You can answer research questions, coordinate other lab agents, and advise on projects. "
        "Keep responses concise (2-4 sentences max for dialogue).\n\n"
    )
    
    if memory_context:
        prompt += f"Context from memory:\n{memory_context}\n\n"
    
    if history_text:
        prompt += f"Recent conversation:\n{history_text}\n\n"
    
    prompt += f"User: {text}\n醋の虾:"
    
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


def _run_llm(messages, max_tokens: int = 4096) -> str:
    """Call LLM via gateway (preferred) or direct API (fallback)."""
    _load_llm_env()
    
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    # Try gateway first (OpenClaw → Claude)
    gateway_url = os.environ.get("GATEWAY_URL", "")
    gateway_token = os.environ.get("GATEWAY_TOKEN", "")
    gateway_model = os.environ.get("GATEWAY_MODEL", "")
    
    if gateway_url and gateway_token:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=gateway_token, base_url=gateway_url)
            resp = client.chat.completions.create(
                model=gateway_model or "haiku",
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[LLM] Gateway failed ({e}), falling back to direct API")

    # Fallback to direct API
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return "⚠️ LLM not configured."

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("LLM_API_BASE", "") or None,
        )
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3-0324"),
            messages=messages,
            max_tokens=max_tokens,
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
