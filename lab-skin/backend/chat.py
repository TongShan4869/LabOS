"""
LabOS Chat Backend — routes chat messages to the appropriate lab-* skill.
Handles project context, clarifying questions, and streaming responses.
"""

import json, os, subprocess, datetime, re, threading
from pathlib import Path

LAB_DIR = Path.home() / ".openclaw/workspace/lab"
SKILLS_DIR = Path.home() / ".openclaw/workspace/skills"

# Agent routing: which skill handles each agent
AGENT_SKILL_MAP = {
    "lab-field-trend":         "lab-field-trend",
    "lab-lit-scout":           "lab-lit-scout",
    "lab-biostat":             "lab-biostat",
    "lab-writing-assistant":   "lab-writing-assistant",
    "lab-peer-reviewer":       "lab-peer-reviewer",
    "lab-research-advisor":    "lab-research-advisor",
    "lab-security":            "lab-security",
    "lab-publishing-assistant":"lab-publishing-assistant",
    "orchestrator":            None,  # routes to best agent
}

# What each agent does (for orchestrator routing)
AGENT_DESCRIPTIONS = {
    "lab-field-trend":         ["field", "trend", "weekly", "new papers", "what's new", "digest", "recent"],
    "lab-lit-scout":           ["search", "find papers", "literature", "papers on", "lit", "pubmed"],
    "lab-biostat":             ["stats", "analysis", "analyze", "t-test", "power", "data", "significance", "p-value"],
    "lab-writing-assistant":   ["draft", "write", "introduction", "methods", "abstract", "grant", "writing"],
    "lab-peer-reviewer":       ["review", "critique", "feedback", "peer", "devil", "check my"],
    "lab-research-advisor":    ["advise", "hypothesis", "question", "stuck", "think", "falsify", "advisor"],
    "lab-security":            ["security", "audit", "classify", "sensitive", "protect"],
    "lab-publishing-assistant":["journal", "submit", "publish", "where to submit", "reformat", "cover letter"],
}

def get_projects():
    """Load projects from research-graph.jsonl"""
    graph_file = LAB_DIR / "research-graph.jsonl"
    projects = []
    if graph_file.exists():
        for line in graph_file.read_text().strip().split("\n"):
            try:
                node = json.loads(line)
                if node.get("type") == "Project":
                    projects.append({
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "description": node.get("description",""),
                        "status": node.get("status","active"),
                        "hypotheses": node.get("hypotheses",[]),
                    })
            except: pass
    return projects

def get_lab_config():
    config_file = LAB_DIR / "LAB_CONFIG.json"
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}

def route_to_agent(message: str) -> str:
    """Auto-detect which agent should handle this message."""
    msg_lower = message.lower()
    scores = {}
    for agent, keywords in AGENT_DESCRIPTIONS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[agent] = score
    if scores:
        return max(scores, key=scores.get)
    return "lab-research-advisor"  # default to advisor

def needs_project_clarification(message: str, project: str) -> bool:
    """Check if this message needs a project to be specified."""
    if project and project != "global":
        return False
    # These skills don't need a project
    no_project_needed = ["field", "trend", "weekly", "security", "audit"]
    if any(kw in message.lower() for kw in no_project_needed):
        return False
    return True

def generate_clarifying_question(agent: str, message: str, projects: list) -> str:
    """Generate a clarifying question when project context is missing."""
    project_list = "\n".join([f"• **{p['name']}** — {p['description'][:60]}" for p in projects])
    
    agent_context = {
        "lab-lit-scout": "I'll search for literature relevant to your project's hypothesis and link papers to it.",
        "lab-biostat": "I'll cross-reference your analysis with your project's hypothesis.",
        "lab-writing-assistant": "I'll draft in context of your project's goals and existing notes.",
        "lab-peer-reviewer": "I'll review against your project's research question.",
        "lab-research-advisor": "I'll pull your full project context to give targeted advice.",
        "lab-publishing-assistant": "I'll tailor journal recommendations to your project's field and findings.",
    }
    
    ctx = agent_context.get(agent, "I'll use your project context to give a better response.")
    
    return f"""To give you the best response, I need to know which project this is for.

{ctx}

Your active projects:
{project_list}

**Reply with the project name**, or say **"general"** if this isn't project-specific."""

def build_skill_prompt(agent: str, message: str, project: str, projects: list, config: dict) -> str:
    """Build a rich prompt for the skill, injecting project context."""
    
    # Get project details
    project_ctx = ""
    if project and project != "global" and project != "general":
        proj = next((p for p in projects if p['name'] == project or p['id'] == project), None)
        if proj:
            project_ctx = f"""
## Active Project Context
- **Project:** {proj['name']}
- **Description:** {proj['description']}
- **Status:** {proj['status']}
- **Hypotheses:** {json.dumps(proj['hypotheses'])}
"""

    user = config.get("user", "Researcher")
    fields = ", ".join(config.get("fields", []))
    writing_style = config.get("writing_style", "")
    
    SKILL_PROMPTS = {
        "lab-field-trend": f"""You are the lab-field-trend agent for LabOS. Your job is to find and summarize recent papers in the user's field.

User: {user} | Fields: {fields}

User's request: {message}

Search PubMed and OpenAlex for relevant papers from the past 7-14 days. If the user asks for a specific topic, focus on that. Provide:
1. A list of the most relevant recent papers (title, journal, year, 1-sentence summary)
2. Any emerging trends or methods
3. Gaps you notice

Be concise. Use bullet points. Max 5 papers unless asked for more.""",

        "lab-lit-scout": f"""You are the lab-lit-scout agent for LabOS. You search and summarize academic literature.

User: {user} | Fields: {fields}
{project_ctx}
User's request: {message}

Search for papers relevant to this request. For each paper provide:
- Title, Authors, Journal, Year
- Key claim (1 sentence)
- Method (1 sentence)  
- Main finding (1-2 sentences)
- Relevance to the request

Flag any paper that might contradict the project hypothesis if one is provided.
Return top 5 papers unless asked for more.""",

        "lab-biostat": f"""You are the lab-biostat agent — a biostatistician for LabOS.

User: {user} | Fields: {fields}
{project_ctx}
User's request: {message}

Provide statistical guidance. Always:
1. State which test you recommend and WHY
2. List assumptions to check first
3. Explain the result in plain English
4. Flag any red flags (underpowered, multiple comparisons, etc.)
5. Show your work — no black boxes

If the user provides data, analyze it. If they describe a design, advise on it.""",

        "lab-writing-assistant": f"""You are the lab-writing-assistant agent for LabOS. You draft academic writing.

User: {user} | Writing style: {writing_style} | Fields: {fields}
{project_ctx}
User's request: {message}

Draft the requested section. Important rules:
- Write in the user's voice: {writing_style}
- Use [CITE:key] as citation placeholders
- Mark [DATA PENDING] where results are needed
- Be direct — no filler phrases
- Start writing immediately, don't explain what you're about to do""",

        "lab-peer-reviewer": f"""You are the lab-peer-reviewer agent for LabOS. You simulate rigorous peer review.

User: {user} | Fields: {fields}
{project_ctx}
User's request: {message}

Provide structured review:
**MAJOR CONCERNS** (numbered, specific)
**MINOR CONCERNS** (numbered, specific)
**STRENGTHS** (what's genuinely good)
**LINE-LEVEL COMMENTS** (quote the passage, state the issue)
**RECOMMENDATION:** Accept / Minor revision / Major revision / Reject

Be rigorous. Be specific. A weak review helps no one.""",

        "lab-research-advisor": f"""You are the lab-research-advisor agent for LabOS — a Socratic mentor.

User: {user} | Fields: {fields}
{project_ctx}
User's request: {message}

Your role: Ask hard questions. Push back. Surface gaps. Don't validate blindly.

Approach:
1. If a hypothesis is present: challenge it ("What would falsify this?")
2. If a method is described: question assumptions
3. If they seem stuck: ask what they've tried, what they're avoiding
4. If they ask for advice: give a direct opinion, then explain why

Be direct but not cruel. You're a good advisor, not a hazing machine.
End every response with ONE follow-up question.""",

        "lab-security": f"""You are the lab-security agent for LabOS — a quiet security warden.

User: {user}
User's request: {message}

If asked to audit: check for exposed credentials, unclassified sensitive projects, recent external API calls.
If asked to classify: confirm the sensitivity level and explain implications.
If asked about a file: assess its sensitivity based on content description.

Be concise. Use ✅/⚠️/❌ indicators.""",

        "lab-publishing-assistant": f"""You are the lab-publishing-assistant agent for LabOS.

User: {user} | Fields: {fields}
{project_ctx}
User's request: {message}

Help with journal selection or manuscript preparation:
- For journal recommendations: rank by fit, impact, open access, turnaround time. Flag predatory journals.
- For reformatting: list specific changes needed for the target journal.
- For cover letters: draft professionally, not sycophantically.
- For checklists: use ✅/⚠️/❌ for each item.""",
    }
    
    return SKILL_PROMPTS.get(agent, SKILL_PROMPTS["lab-research-advisor"])

def call_openclaw_llm(prompt: str) -> str:
    """Call the LLM via OpenClaw's configured model."""
    try:
        result = subprocess.run(
            ["openclaw", "ask", "--no-context", prompt],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    
    # Fallback: try claude CLI directly
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    
    return None

def process_chat(agent: str, message: str, project: str, history: list) -> dict:
    """
    Main chat processing function.
    Returns: {response, needs_clarification, clarification_question, agent_used, suggested_agent}
    """
    projects = get_projects()
    config = get_lab_config()
    
    # Auto-route if orchestrator
    agent_used = agent
    if agent == "orchestrator":
        agent_used = route_to_agent(message)
    
    # Check if we need project clarification
    if needs_project_clarification(message, project) and len(projects) > 0:
        # Check history — if last message was a clarification Q, parse the answer
        if history and len(history) >= 2:
            last_bot = next((h['content'] for h in reversed(history) if h['role'] == 'assistant'), None)
            if last_bot and "which project" in last_bot.lower():
                # User just answered the clarification — extract project from message
                for p in projects:
                    if p['name'].lower() in message.lower() or p['id'].lower() in message.lower():
                        project = p['name']
                        break
                if "general" in message.lower() or "global" in message.lower():
                    project = "global"
                # If still no match, proceed with global
                if not project:
                    project = "global"
        else:
            # First message, needs clarification
            return {
                "response": generate_clarifying_question(agent_used, message, projects),
                "needs_clarification": True,
                "agent_used": agent_used,
                "project": project,
            }
    
    # Build the full prompt with context
    prompt = build_skill_prompt(agent_used, message, project, projects, config)
    
    # Try to get LLM response
    response = call_openclaw_llm(prompt)
    
    if response is None:
        # Return a helpful fallback that shows what would be executed
        skill_file = SKILLS_DIR / agent_used / "script.md"
        response = f"""**[{agent_used}]** Ready to process your request.

**Your request:** {message}
**Project context:** {project or 'global'}

*Note: LLM backend not connected yet. To enable live responses, connect via `openclaw` CLI or configure an API key.*

**What I would do:**
- Read your LAB_CONFIG.json and LAB_MEMORY.md for context
- {['Search PubMed + OpenAlex for relevant papers', 'Run statistical analysis on your data', 'Draft the requested section in your writing style', 'Simulate peer review of your manuscript', 'Ask Socratic questions about your hypothesis', 'Check for security issues in your lab setup', 'Recommend journals and prepare submission'][list(AGENT_SKILL_MAP.keys()).index(agent_used) if agent_used in AGENT_SKILL_MAP else 5]}
- Save results to your Obsidian vault and update the research graph
- Award XP on completion"""
    
    # Update agent state
    state_map = {
        "lab-field-trend": "researching",
        "lab-lit-scout": "researching", 
        "lab-biostat": "executing",
        "lab-writing-assistant": "writing",
        "lab-peer-reviewer": "writing",
        "lab-research-advisor": "writing",
        "lab-security": "syncing",
        "lab-publishing-assistant": "writing",
    }
    
    return {
        "response": response,
        "needs_clarification": False,
        "agent_used": agent_used,
        "project": project,
        "state": state_map.get(agent_used, "executing"),
    }
