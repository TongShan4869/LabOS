#!/usr/bin/env python3
"""
lab-research-advisor — Socratic mentor agent for LabOS
Pulls project context from research graph and conducts a rigorous advisory session.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ─── Paths ────────────────────────────────────────────────────────────────────

LAB_DIR = Path(os.environ.get("LAB_DIR", Path.home() / ".openclaw/workspace/lab"))
CONFIG_FILE = LAB_DIR / "LAB_CONFIG.json"
MEMORY_FILE = LAB_DIR / "LAB_MEMORY.md"
GRAPH_FILE = LAB_DIR / "research-graph.jsonl"
XP_FILE = LAB_DIR / "xp.json"
SESSIONS_DIR = LAB_DIR / "sessions"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print("❌ LAB_CONFIG.json not found. Run lab-init first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text())


def load_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text()
    return ""


def load_graph() -> list[dict]:
    if not GRAPH_FILE.exists():
        return []
    nodes = []
    for line in GRAPH_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                nodes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return nodes


def save_graph(nodes: list[dict]):
    GRAPH_FILE.write_text("\n".join(json.dumps(n) for n in nodes) + "\n")


def load_xp() -> dict:
    if XP_FILE.exists():
        return json.loads(XP_FILE.read_text())
    return {"xp": 0, "level": 1, "badges": []}


def save_xp(xp_data: dict):
    XP_FILE.write_text(json.dumps(xp_data, indent=2))


def award_xp(amount: int, badge: str | None = None):
    xp_data = load_xp()
    xp_data["xp"] = xp_data.get("xp", 0) + amount
    if badge and badge not in xp_data.get("badges", []):
        xp_data.setdefault("badges", []).append(badge)
        print(f"\n🏅 Badge unlocked: {badge}")
    print(f"\n✨ +{amount} XP (total: {xp_data['xp']})")
    save_xp(xp_data)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def days_since(iso_str: str) -> int | None:
    try:
        then = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - then
        return delta.days
    except Exception:
        return None


# ─── Graph queries ─────────────────────────────────────────────────────────────

def get_projects(nodes: list[dict], project_name: str | None = None) -> list[dict]:
    projects = [n for n in nodes if n.get("type") == "Project"]
    if project_name:
        projects = [p for p in projects if project_name.lower() in p.get("name", "").lower()]
    return projects


def get_papers_for_project(nodes: list[dict], project_id: str) -> list[dict]:
    return [
        n for n in nodes
        if n.get("type") == "Paper" and project_id in n.get("projects", [])
    ]


def get_hypotheses_for_project(nodes: list[dict], project_id: str) -> list[dict]:
    return [
        n for n in nodes
        if n.get("type") == "Hypothesis" and n.get("project_id") == project_id
    ]


def get_experiments_for_project(nodes: list[dict], project_id: str) -> list[dict]:
    return [
        n for n in nodes
        if n.get("type") == "Experiment" and n.get("project_id") == project_id
    ]


# ─── Diagnostics ──────────────────────────────────────────────────────────────

def run_diagnostics(project: dict, nodes: list[dict]) -> list[str]:
    """Quietly scan for issues to surface in the session."""
    issues = []
    pid = project.get("id", "")
    props = project.get("properties", project)  # handle both flat and nested

    hypotheses = get_hypotheses_for_project(nodes, pid)
    papers = get_papers_for_project(nodes, pid)
    experiments = get_experiments_for_project(nodes, pid)

    # Hypothesis checks
    h1_list = [h for h in hypotheses if h.get("label") in ("H1", "alternative")]
    h0_list = [h for h in hypotheses if h.get("label") in ("H0", "null")]
    if not h1_list:
        issues.append("❓ No primary hypothesis (H1) logged for this project.")
    if not h0_list:
        issues.append("⚠️ No null hypothesis (H0) defined — what would falsify your H1?")

    contradicting = [p for p in papers if p.get("contradicts")]
    if contradicting:
        issues.append(
            f"🔴 {len(contradicting)} paper(s) flagged as contradicting your hypothesis — have you engaged with them?"
        )

    # Literature checks
    last_lit = props.get("last_lit_scout")
    if last_lit:
        d = days_since(last_lit)
        if d is not None and d > 21:
            issues.append(f"📚 Last literature search was {d} days ago — the field may have moved.")
    else:
        issues.append("📚 No literature search recorded for this project yet.")

    unsummarized = [p for p in papers if not p.get("summary")]
    if unsummarized:
        issues.append(f"📄 {len(unsummarized)} paper(s) linked but never summarized.")

    # Methods checks
    if not experiments:
        issues.append("🔬 No experiments logged — is your study design documented?")
    else:
        no_design = [e for e in experiments if not e.get("design")]
        if no_design:
            issues.append(f"🔬 {len(no_design)} experiment(s) have no design notes — controls? sample size?")
        power_done = any(e.get("power_analysis") for e in experiments)
        if not power_done:
            issues.append("📊 No power analysis on record — consider running lab-biostat --mode power.")

    # Staleness check
    last_updated = props.get("last_updated") or props.get("updated")
    if last_updated:
        d = days_since(last_updated)
        if d is not None and d > 14:
            issues.append(f"💤 Project hasn't been updated in {d} days — is it stalled?")

    return issues


# ─── Question banks ───────────────────────────────────────────────────────────

QUESTIONS = {
    "hypothesis": [
        "What would falsify your H1? Be specific — give me the data pattern that would kill it.",
        "If your H1 is true, what's the mechanism? Is that mechanism independently testable?",
        "What's the effect size you're expecting, and why that magnitude?",
        "You've cited some papers multiple times — have you directly engaged with the ones that challenge you?",
        "What's the single weakest link in your theoretical chain right now?",
    ],
    "gaps": [
        "What's the most important paper in your field you haven't read yet?",
        "Who are the 3 labs doing work closest to yours right now? What are *they* finding?",
        "What's a question in your field nobody is asking? Is that a gap or a dead end?",
        "Is your lit review broad enough to claim you know the landscape?",
        "What would change your mind about your core assumption?",
    ],
    "methods": [
        "Walk me through your study design. What are your controls?",
        "What's your N? Have you done a power analysis? If not — run lab-biostat --mode power.",
        "What are your top 3 confounds? How are you handling each one?",
        "If you ran this and got a null result, would it be informative? Or would it just be ambiguous?",
        "Is your outcome measure the *right* one, or the *available* one?",
    ],
    "writing": [
        "Who is your target reader — a generalist or a specialist in your subfield?",
        "Say in one sentence what this paper is about. No jargon.",
        "What's the gap in the literature your paper fills? One sentence.",
        "What's the strongest objection a reviewer will make? How do you answer it?",
        "If you had to cut 30% of this paper, what goes first?",
    ],
    "next-steps": [
        "What's the single thing that would move this project forward the most right now?",
        "What are you avoiding? Why?",
        "If you had to submit in 30 days, what would you cut and what would you keep?",
        "What's blocking you — resources, knowledge, motivation, or something else?",
        "What does 'done' look like for this project, concretely?",
    ],
}


def pick_questions(focus: str | None, diagnostics: list[str]) -> list[str]:
    """Pick relevant questions based on focus and diagnostic issues."""
    if focus and focus in QUESTIONS:
        return QUESTIONS[focus]
    # Auto-pick based on what diagnostics flagged
    if any("hypothesis" in d.lower() or "H1" in d or "H0" in d for d in diagnostics):
        return QUESTIONS["hypothesis"]
    if any("literature" in d.lower() or "paper" in d.lower() for d in diagnostics):
        return QUESTIONS["gaps"]
    if any("experiment" in d.lower() or "power" in d.lower() for d in diagnostics):
        return QUESTIONS["methods"]
    return QUESTIONS["hypothesis"]  # default


# ─── Session I/O ──────────────────────────────────────────────────────────────

def prompt(text: str) -> str:
    print(f"\n🎓 {text}")
    print("You: ", end="", flush=True)
    return input().strip()


def say(text: str):
    print(f"\n🎓 {text}")


# ─── Main session ─────────────────────────────────────────────────────────────

def run_session(project: dict, mode: str, focus: str | None, nodes: list[dict], config: dict, memory: str):
    pid = project.get("id", "")
    props = project.get("properties", project)
    project_name = props.get("name", project.get("name", pid))
    user = config.get("user", "researcher")
    today = datetime.now().strftime("%Y-%m-%d")

    diagnostics = run_diagnostics(project, nodes)
    questions = pick_questions(focus, diagnostics)

    # ── Opening ──
    print("\n" + "═" * 60)
    print(f"  🎓 Lab Research Advisor — {project_name}")
    print(f"  Mode: {'🔥 Hard' if mode == 'hard' else '💛 Supportive'}  |  {today}")
    print("═" * 60)

    last_session = props.get("last_advisor_session")
    days_ago = f"{days_since(last_session)} days ago" if last_session else "never"

    if mode == "hard":
        say(
            f"Alright {user}, let's talk about **{project_name}**. "
            f"Last advisor session: {days_ago}.\n"
        )
        if diagnostics:
            say("Here's what I'm seeing before we start:\n" + "\n".join(f"  • {d}" for d in diagnostics))
        say(f"\nLet's dig in. {questions[0]}")
    else:
        say(
            f"Hey {user}, good to check in on **{project_name}**. "
            f"Last session was {days_ago}.\n"
        )
        if diagnostics:
            say("A few things worth looking at:\n" + "\n".join(f"  • {d}" for d in diagnostics))
        say(f"\nLet's start somewhere manageable: {questions[0]}")

    # ── Session loop ──
    session_log = []
    q_index = 0
    exchange_count = 0
    EXIT_WORDS = {"done", "exit", "quit", "thanks", "thank you", "enough", "stop"}

    while True:
        response = input("You: ").strip()
        if not response:
            continue
        if response.lower() in EXIT_WORDS:
            say("Got it — let's wrap up.")
            break

        session_log.append({"q": questions[q_index % len(questions)], "a": response})
        exchange_count += 1

        # Acknowledgement + next question
        ack = "Okay." if mode == "hard" else "Good."
        q_index += 1

        if exchange_count >= 5 or q_index >= len(questions):
            say(f"{ack} We've covered a lot. Want to keep going or shall we summarize?")
            cont = input("You: ").strip().lower()
            if cont in EXIT_WORDS or cont in {"no", "summarize", "summary", "wrap", "wrap up"}:
                break
            # else continue with more questions from bank
            q_index = q_index % len(questions)

        next_q = questions[q_index % len(questions)]
        say(f"{ack} {next_q}")

    return session_log, diagnostics


# ─── Summary & persistence ────────────────────────────────────────────────────

def write_session_summary(project_name: str, session_log: list, diagnostics: list, action_items: list):
    today = datetime.now().strftime("%Y-%m-%d")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    fname = SESSIONS_DIR / f"{today}-lab-research-advisor.md"

    lines = [
        f"# Session Summary — {project_name} — {today}\n",
        "## Diagnostic issues flagged",
    ]
    for d in diagnostics:
        lines.append(f"- {d}")
    lines.append("\n## Questions & responses")
    for i, qa in enumerate(session_log, 1):
        lines.append(f"\n**Q{i}:** {qa['q']}")
        lines.append(f"**A:** {qa['a']}")
    lines.append("\n## Action items")
    for item in action_items:
        lines.append(f"- [ ] {item}")
    lines.append(f"\n*Next advisor check-in suggested: ~2 weeks*\n")

    fname.write_text("\n".join(lines))
    return fname


def update_project_timestamp(nodes: list[dict], project_id: str) -> list[dict]:
    updated = []
    for n in nodes:
        if n.get("id") == project_id:
            if "properties" in n:
                n["properties"]["last_advisor_session"] = now_iso()
            else:
                n["last_advisor_session"] = now_iso()
        updated.append(n)
    return updated


def extract_action_items(session_log: list) -> list[str]:
    """Simple heuristic — surface common action patterns from answers."""
    items = []
    keywords = {
        "power analysis": "Run lab-biostat --mode power",
        "lit-scout": "Run lab-lit-scout to update literature",
        "hypothesis": "Log H0 / falsification criteria in research graph",
        "paper": "Summarize and link flagged papers in research graph",
        "design": "Document study design and controls",
        "null": "Define null hypothesis (H0)",
    }
    full_text = " ".join(qa["a"].lower() for qa in session_log)
    for kw, action in keywords.items():
        if kw in full_text and action not in items:
            items.append(action)
    if not items:
        items.append("Review session notes and update research graph")
    return items


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS Research Advisor — Socratic mentor agent")
    parser.add_argument("--project", "-p", help="Project name to focus on")
    parser.add_argument("--mode", choices=["hard", "supportive"], default="hard",
                        help="Advisor mode (default: hard)")
    parser.add_argument("--focus", choices=["hypothesis", "gaps", "methods", "writing", "next-steps"],
                        help="Focus area for questions")
    args = parser.parse_args()

    config = load_config()
    memory = load_memory()
    nodes = load_graph()

    projects = get_projects(nodes, args.project)

    if not projects:
        if args.project:
            print(f"❌ No project found matching '{args.project}'. Check your research graph.")
        else:
            print("❌ No projects found in research graph. Run lab-init to set up a project.")
        sys.exit(1)

    if len(projects) > 1 and not args.project:
        print("📋 Multiple projects found. Pick one:")
        for i, p in enumerate(projects):
            props = p.get("properties", p)
            print(f"  [{i+1}] {props.get('name', p.get('id'))}")
        choice = input("Enter number: ").strip()
        try:
            project = projects[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid choice.")
            sys.exit(1)
    else:
        project = projects[0]

    # Run session
    session_log, diagnostics = run_session(
        project=project,
        mode=args.mode,
        focus=args.focus,
        nodes=nodes,
        config=config,
        memory=memory,
    )

    # Action items
    action_items = extract_action_items(session_log)

    # Print summary
    props = project.get("properties", project)
    project_name = props.get("name", project.get("id", "project"))
    today = datetime.now().strftime("%Y-%m-%d")

    print("\n" + "═" * 60)
    print(f"  📋 Session Summary — {project_name} — {today}")
    print("═" * 60)
    print("\n**Questions addressed:**")
    for i, qa in enumerate(session_log, 1):
        a_preview = qa["a"][:80] + "…" if len(qa["a"]) > 80 else qa["a"]
        print(f"  Q{i}: {qa['q'][:60]}…")
        print(f"      → {a_preview}")
    print("\n**Action items:**")
    for item in action_items:
        print(f"  [ ] {item}")
    print(f"\n**Next advisor check-in:** ~2 weeks or when action items are done")

    # Persist
    session_file = write_session_summary(project_name, session_log, diagnostics, action_items)
    print(f"\n💾 Session saved: {session_file}")

    nodes = update_project_timestamp(nodes, project.get("id", ""))
    save_graph(nodes)

    # XP
    xp_data = load_xp()
    is_first = "🎓 Mentored" not in xp_data.get("badges", [])
    award_xp(30, "🎓 Mentored" if is_first else None)

    print("\n✅ Advisor session complete.\n")


if __name__ == "__main__":
    main()
