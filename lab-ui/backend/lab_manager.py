"""
LabOS Lab Manager — OpenClaw-native agent orchestration.

The Lab Manager is the single entry point for all user interactions.
It delegates tasks to specialist subagents via OpenClaw sessions_spawn.

v2 Architecture: User → Lab Manager → Subagents (Scout, Stat, Quill, etc.)
"""

import json
import os
import time
import threading
from pathlib import Path
from datetime import datetime

# --- Config ---
DATA_DIR = Path(os.environ.get("LABOS_DATA_DIR", "/tmp/LabOS/data"))
LAB_DIR = Path(os.environ.get("LAB_DIR", str(Path.home() / ".openclaw/workspace/lab")))
AGENTS_DIR = DATA_DIR / "agents"
QUESTS_DIR = DATA_DIR / "quests"
AUDIT_FILE = DATA_DIR / "audit.jsonl"

# Ensure directories exist
for d in [AGENTS_DIR, QUESTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- Agent Registry ---
AGENT_REGISTRY = {
    "scout": {
        "name": "Scout",
        "specialty": "Literature search across PubMed, OpenAlex, and arXiv",
        "skills": ["lab-lit-scout"],
        "sprite": "sprite-scout.png",
    },
    "stat": {
        "name": "Stat",
        "specialty": "Statistical analysis, study design, power calculations",
        "skills": ["lab-stats-advisor"],
        "sprite": "sprite-stat.png",
    },
    "quill": {
        "name": "Quill",
        "specialty": "Scientific writing, drafting, and editing",
        "skills": ["lab-writing-assistant", "lab-publishing-assistant"],
        "sprite": "sprite-quill.png",
    },
    "critic": {
        "name": "Critic",
        "specialty": "Paper review, methodology critique, gap analysis",
        "skills": ["lab-review-assistant"],
        "sprite": "sprite-critic.png",
    },
    "sage": {
        "name": "Sage",
        "specialty": "Research strategy, career advice, grant planning",
        "skills": ["lab-research-advisor"],
        "sprite": "sprite-sage.png",
    },
    "trend": {
        "name": "Trend",
        "specialty": "Research trend analysis and field mapping",
        "skills": ["lab-trend-tracker"],
        "sprite": "sprite-trend.png",
    },
    "warden": {
        "name": "Warden",
        "specialty": "Reproducibility checks and methodology validation",
        "skills": ["lab-reproducibility-checker"],
        "sprite": "sprite-warden.png",
    },
}


def get_agent_config(agent_id: str) -> dict:
    """Get or create agent config."""
    config_file = AGENTS_DIR / agent_id / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text())
    
    # Create from registry
    registry = AGENT_REGISTRY.get(agent_id, {})
    config = {
        "id": agent_id,
        "name": registry.get("name", agent_id.title()),
        "sprite": registry.get("sprite", f"sprite-{agent_id}.png"),
        "specialty": registry.get("specialty", "General research assistance"),
        "skills": registry.get("skills", []),
        "status": "idle",
        "lifecycle": "ephemeral",
        "run_count": 0,
        "promotion_threshold": 3,
        "heartbeat_cron": None,
        "created_at": datetime.now().isoformat(),
        "last_active": None,
    }
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, indent=2))
    return config


def update_agent_config(agent_id: str, updates: dict):
    """Update agent config fields."""
    config = get_agent_config(agent_id)
    config.update(updates)
    config_file = AGENTS_DIR / agent_id / "config.json"
    config_file.write_text(json.dumps(config, indent=2))
    return config


def get_agent_usage(agent_id: str) -> dict:
    """Get agent usage stats."""
    usage_file = AGENTS_DIR / agent_id / "usage.json"
    if usage_file.exists():
        return json.loads(usage_file.read_text())
    return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "runs": 0, "last_active": None}


def record_agent_run(agent_id: str, tokens_in: int = 0, tokens_out: int = 0):
    """Record an agent run and check for promotion."""
    usage = get_agent_usage(agent_id)
    usage["runs"] += 1
    usage["tokens_in"] += tokens_in
    usage["tokens_out"] += tokens_out
    usage["last_active"] = datetime.now().isoformat()
    
    usage_file = AGENTS_DIR / agent_id / "usage.json"
    usage_file.parent.mkdir(parents=True, exist_ok=True)
    usage_file.write_text(json.dumps(usage, indent=2))
    
    # Check for auto-promotion
    config = get_agent_config(agent_id)
    if config["lifecycle"] == "ephemeral" and usage["runs"] >= config["promotion_threshold"]:
        update_agent_config(agent_id, {
            "lifecycle": "persistent",
            "status": "active",
        })
        audit_log("promotion", agent_id, f"Auto-promoted to persistent after {usage['runs']} runs")
    
    return usage


def get_agent_memory(agent_id: str) -> str:
    """Read agent's personal memory."""
    memory_file = AGENTS_DIR / agent_id / "memory.md"
    if memory_file.exists():
        return memory_file.read_text()
    return ""


def save_agent_memory(agent_id: str, content: str):
    """Save agent's personal memory."""
    memory_file = AGENTS_DIR / agent_id / "memory.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(content)


# --- Quest Board ---

def create_quest(title: str, agent_id: str, xp_reward: int = 50) -> dict:
    """Create a new quest on the quest board."""
    import uuid
    quest_id = str(uuid.uuid4())[:8]
    quest = {
        "id": quest_id,
        "title": title,
        "assigned_to": agent_id,
        "status": "active",
        "xp_reward": xp_reward,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "result_summary": None,
    }
    quest_file = QUESTS_DIR / f"{quest_id}.json"
    quest_file.write_text(json.dumps(quest, indent=2))
    audit_log("quest_created", agent_id, title)
    return quest


def complete_quest(quest_id: str, result_summary: str = None):
    """Mark a quest as completed."""
    quest_file = QUESTS_DIR / f"{quest_id}.json"
    if quest_file.exists():
        quest = json.loads(quest_file.read_text())
        quest["status"] = "done"
        quest["completed_at"] = datetime.now().isoformat()
        quest["result_summary"] = result_summary
        quest_file.write_text(json.dumps(quest, indent=2))
        audit_log("quest_completed", quest["assigned_to"], f"{quest['title']} (+{quest['xp_reward']} XP)")
        return quest
    return None


def get_active_quests() -> list:
    """Get all active quests."""
    quests = []
    for f in QUESTS_DIR.glob("*.json"):
        q = json.loads(f.read_text())
        if q["status"] == "active":
            quests.append(q)
    return sorted(quests, key=lambda q: q["created_at"], reverse=True)


def get_all_quests(limit: int = 20) -> list:
    """Get recent quests."""
    quests = []
    for f in QUESTS_DIR.glob("*.json"):
        quests.append(json.loads(f.read_text()))
    return sorted(quests, key=lambda q: q["created_at"], reverse=True)[:limit]


# --- Audit Log ---

def audit_log(action: str, agent_id: str, detail: str):
    """Append to immutable audit log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "agent_id": agent_id,
        "detail": detail,
    }
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# --- Lab Manager Prompt Builder ---

def build_lab_manager_prompt(lab_config: dict = None) -> str:
    """Build the Lab Manager system prompt with full context."""
    
    # Load lab config
    if lab_config is None:
        config_file = LAB_DIR / "LAB_CONFIG.json"
        if config_file.exists():
            lab_config = json.loads(config_file.read_text())
        else:
            lab_config = {}
    
    lab_name = lab_config.get("lab_name", "Research Lab")
    projects = lab_config.get("projects", [])
    active_project = projects[0] if projects else {"name": "General Research", "field": "Science"}
    
    # Build team roster
    team_lines = []
    for aid, reg in AGENT_REGISTRY.items():
        config = get_agent_config(aid)
        usage = get_agent_usage(aid)
        status = config.get("lifecycle", "ephemeral")
        runs = usage.get("runs", 0)
        team_lines.append(
            f"- **{reg['name']}** ({reg['specialty']}) — "
            f"Skills: {', '.join(reg['skills'])} — "
            f"Runs: {runs} — Status: {status}"
        )
    
    # Active quests
    active_quests = get_active_quests()
    quest_lines = []
    for q in active_quests[:5]:
        quest_lines.append(f"- [{q['status']}] {q['title']} → {q['assigned_to']}")
    
    # Lab memory
    lab_memory_file = Path("/tmp/LabOS/LAB_MEMORY.md")
    lab_memory = lab_memory_file.read_text() if lab_memory_file.exists() else ""
    
    prompt = f"""You are the Lab Manager of **{lab_name}**. You run this research lab.

Your PI talks to you. You figure out what needs to be done and delegate to your specialist team.

## YOUR TEAM
{chr(10).join(team_lines)}

## ACTIVE PROJECT
**{active_project['name']}** — Field: {active_project.get('field', 'Research')}

## ACTIVE QUESTS
{chr(10).join(quest_lines) if quest_lines else 'No active quests.'}

## HOW TO DELEGATE

When the PI asks for something that matches a specialist's skills, delegate by describing:
1. Which agent should handle it
2. What exactly they should do
3. Any context from previous conversations

For literature searches → delegate to **Scout**
For statistical analysis → delegate to **Stat**
For writing/drafting → delegate to **Quill**
For paper review/critique → delegate to **Critic**
For research strategy → delegate to **Sage**
For trend analysis → delegate to **Trend**
For reproducibility → delegate to **Warden**

## RULES
- You are the orchestrator. You don't search papers yourself — Scout does.
- You don't run stats yourself — Stat does.
- You DO handle: greetings, general questions, lab status, project management, memory.
- Always be brief when delegating. The PI doesn't need to know the plumbing.
- Format responses in Markdown.
- When reporting subagent results, present them clearly with full paper metadata if applicable.

## FORMATTING
When presenting paper results, ALWAYS include: title, authors, journal, DOI, TLDR.
Never omit metadata — the PI is a researcher, they need it.
"""
    
    if lab_memory:
        prompt += f"\n## LAB MEMORY\n{lab_memory}\n"
    
    return prompt


# --- Delegation Engine ---

# Map of task intent → agent
DELEGATION_PATTERNS = {
    "scout": [
        r"(search|find|look for|look up|get|fetch|discover)\b.*(paper|article|literature|publication|study|studies)",
        r"(lit|literature)\s*(search|review|scout|scan)",
        r"(pubmed|arxiv|openalex|scholar)",
        r"what('s| is) (new|recent|latest)\b.*(paper|research|field)",
    ],
    "stat": [
        r"(statistic|stats|analysis|analyze|power|sample size|p-value|regression|anova|t-test)",
        r"(study design|experimental design|randomiz)",
    ],
    "quill": [
        r"(write|draft|edit|polish|proofread|abstract|introduction|manuscript)",
        r"(grant|proposal)\b.*(write|draft)",
    ],
    "critic": [
        r"(review|critique|evaluate|assess)\b.*(paper|method|study|article)",
        r"(strength|weakness|limitation|gap)\b.*(paper|study|research)",
    ],
    "sage": [
        r"(research|career)\b.*(advice|strategy|plan|direction)",
        r"(grant|funding|fellowship)\b.*(plan|apply|strategy)",
    ],
    "trend": [
        r"(trend|emerging|hot topic|field map|landscape)",
        r"what('s| is) (trending|hot|emerging)",
    ],
    "warden": [
        r"(reproducib|replicat|method check|validate)",
    ],
}


def detect_delegation(text: str) -> str | None:
    """Detect which agent should handle this task. Returns agent_id or None."""
    import re
    text_lower = text.lower()
    
    for agent_id, patterns in DELEGATION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return agent_id
    
    return None  # Lab Manager handles it directly


if __name__ == "__main__":
    # Test
    print("=== Lab Manager Prompt ===")
    print(build_lab_manager_prompt()[:500])
    print("\n=== Delegation Tests ===")
    tests = [
        "find papers about neural coupling",
        "what's the p-value for this?",
        "draft an abstract for my paper",
        "review this methodology",
        "what's trending in neuroscience?",
        "hello, how are you?",
        "what's the status of my lab?",
    ]
    for t in tests:
        agent = detect_delegation(t)
        print(f"  '{t}' → {agent or 'Lab Manager (direct)'}")


# --- Agent Pipelines ---

PIPELINES = {
    "lit_review": {
        "name": "Literature Review Pipeline",
        "steps": [
            {"agent": "scout", "action": "search", "description": "Find relevant papers"},
            {"agent": "critic", "action": "review", "description": "Review and critique findings"},
            {"agent": "quill", "action": "summarize", "description": "Write synthesis report"},
        ],
    },
    "study_design": {
        "name": "Study Design Pipeline", 
        "steps": [
            {"agent": "sage", "action": "advise", "description": "Research strategy"},
            {"agent": "stat", "action": "design", "description": "Statistical design + power analysis"},
        ],
    },
}


def detect_pipeline(text: str) -> str | None:
    """Detect if a request needs a multi-agent pipeline."""
    import re
    text_lower = text.lower()
    
    # Lit review pipeline triggers
    if re.search(r"(full|comprehensive|systematic)\\s*(lit|literature)\s*(review|search|survey)", text_lower):
        return "lit_review"
    
    # Study design pipeline triggers
    if re.search(r"(design|plan)\\s*(a|my|the)?\s*(study|experiment|trial)", text_lower):
        return "study_design"
    
    return None
