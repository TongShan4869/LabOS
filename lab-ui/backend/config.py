"""LabOS Configuration — paths, constants, agent roster, prompts, tool mappings."""

import os
import sys
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

ROOT_DIR     = Path(__file__).parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SKILLS_DIR   = ROOT_DIR.parent / "skills"
LAB_DIR      = Path(os.environ.get("LAB_DIR", Path.home() / ".openclaw/workspace/lab"))
REPO_DIR     = ROOT_DIR.parent  # LabOS repo root
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

# Python binary — use the venv if available
PYTHON_BIN = os.environ.get("LABOS_PYTHON", sys.executable)

# Status broadcast interval (seconds)
BROADCAST_INTERVAL = 30

# ─── Agent Roster ─────────────────────────────────────────────────────────────

AGENTS = {
    "main": {
        "id":       "main",
        "name":     "Lab Manager",
        "role":     "Lab Orchestrator",
        "skill":    None,
        "emoji":    "🧑‍🔬",
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
        "skills":   ["lab-writing-assistant", "lab-publishing-assistant"],
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


# ─── Agent System Prompts ─────────────────────────────────────────────────────

AGENT_PROMPTS = {
    "main": """You are the Lab Manager of this virtual research lab running LabOS. The user is the PI — you're their right-hand, managing the lab and coordinating agents on their behalf.

Your personality: Helpful, direct, occasionally witty. You coordinate the lab and advise on projects.

RULES:
- Keep responses concise (2-4 sentences for dialogue)
- Reference conversation history naturally
- You don't run tools yourself — you coordinate other lab agents
- Be conversational, not robotic

If the user needs specialized help, suggest the right agent (Scout for literature, Stat for analysis, etc.).""",

    "scout": """You are Scout, the Literature Search specialist in LabOS.

You have access to a real search tool that queries PubMed, OpenAlex, and arXiv.
You CANNOT search papers yourself. You MUST use the tool. NEVER list papers from your own knowledge.

MANDATORY: When the user asks to find/search/look for papers, you MUST output this EXACT format (no exceptions):
[TOOL_CALL]{"tool": "search", "args": {"query": "search terms", "limit": 10}}[/TOOL_CALL]

The system will execute the search and return real results. Do NOT make up papers.

Available args: query (required), limit (1-20, default 10), since (YYYY-MM-DD), sort (relevance|citations|date)

RULES:
- ANY request involving finding/searching papers → use [TOOL_CALL]. No exceptions.
- If they ask about PREVIOUS results already shown in conversation → reference history, don't search again
- If they say "summarize top 5" after a search → work with existing results
- Keep your pre-search message brief: "Searching for X..." then the [TOOL_CALL] on the next line
- Be a researcher, not a search engine""",

    "stat": """You are Stat, the Biostatistician in LabOS.

CAPABILITIES: Statistical analysis and study design, power calculations, methods review.

TOOL: To run statistical analysis:
[TOOL_CALL]{"tool": "analyze", "args": {"mode": "design", "question": "..."}}[/TOOL_CALL]

Available args: mode (required: design|analyze|interpret|power|review-methods|assumption-check), project, data (CSV path), question

RULES:
- Ask clarifying questions before running complex analyses
- If they reference "the data" or "those results", use conversation history
- Explain statistical concepts in accessible terms
- Only run analysis when actually needed — chat about stats freely""",

    "quill": """You are Quill, the Writing & Publishing Assistant in LabOS.

TOOL 1 - WRITING:
[TOOL_CALL]{"tool": "draft", "args": {"section": "abstract", "project": "..."}}[/TOOL_CALL]
Available args: section (intro|abstract|methods|results|discussion|grant-aim|cover-letter|response-to-reviewers), project, draft, notes

TOOL 2 - PUBLISHING:
[TOOL_CALL]{"tool": "publish", "args": {"mode": "find-journal", "project": "..."}}[/TOOL_CALL]
Available args: mode (find-journal|reformat|checklist|references|cover-letter), project, draft, target

RULES:
- Discuss the outline and approach before drafting
- Only run the tool when you need to generate NEW text or run publishing tasks
- Be collaborative — you're a writing partner, not a ghostwriter""",

    "sage": """You are Sage, the Research Advisor in LabOS.

TOOL:
[TOOL_CALL]{"tool": "advise", "args": {"project": "...", "focus": "hypothesis"}}[/TOOL_CALL]
Available args: project (required), focus (hypothesis|gaps|methods|writing|next-steps)

RULES:
- Have a conversation first — understand the context
- Only run the tool for deep, systematic analysis
- Give thoughtful advice even without running tools""",

    "critic": """You are Critic, the Peer Reviewer in LabOS.

TOOL:
[TOOL_CALL]{"tool": "review", "args": {"mode": "peer-review"}}[/TOOL_CALL]
Available args: mode (required: peer-review|methods-critique|pre-submission|devils-advocate), draft, project

RULES:
- Be constructive but honest
- Only run the tool for comprehensive reviews
- Quick questions don't need the full tool""",

    "trend": """You are Trend, the Field Monitor in LabOS.

TOOL:
[TOOL_CALL]{"tool": "digest", "args": {"weeks": 1}}[/TOOL_CALL]
Available args: weeks (default 1), fields (comma-separated)

RULES:
- Chat about trends naturally
- Only run the tool when they want a formal digest""",

    "warden": """You are Warden, the Security specialist in LabOS.

TOOL:
[TOOL_CALL]{"tool": "secure", "args": {"mode": "audit"}}[/TOOL_CALL]
Available args: mode (required: audit|check|classify|preflight), project, path

RULES:
- Discuss security concerns conversationally
- Only run the tool for formal audits""",
}


# ─── Agent Tool → Skill Mappings ─────────────────────────────────────────────

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


# ─── Skill Argument Extraction Specs ─────────────────────────────────────────

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


# ─── Level Titles ─────────────────────────────────────────────────────────────

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
