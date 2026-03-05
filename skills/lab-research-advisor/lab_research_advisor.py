#!/usr/bin/env python3
"""
lab-research-advisor — Socratic mentor agent for LabOS
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add skills dir to path so lab_utils is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_memory, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, CheckpointAborted,
    find_project, get_project_papers, get_project_hypotheses, get_project_experiments,
    days_since, now_iso, today_str,
)

# ── Lab UI state bridge (optional, silent if UI not running) ──────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "lab-ui"))
    from lab_state import AgentWorking, working, idle as idle_state, error as error_state
    _UI = True
except ImportError:
    class AgentWorking:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def update(self, *a): pass
        def __exit__(self, *a): return False
    def working(*a, **kw): pass
    def idle_state(*a): pass
    def error_state(*a): pass
    _UI = False



# ─── Diagnostics ──────────────────────────────────────────────────────────────

def run_diagnostics(project: dict, nodes: list[dict]) -> list[str]:
    pid = project.get("id", "")
    props = project.get("properties", project)
    issues = []

    hypotheses  = get_project_hypotheses(nodes, pid)
    papers      = get_project_papers(nodes, pid)
    experiments = get_project_experiments(nodes, pid)

    h1 = [h for h in hypotheses if h.get("label") in ("H1", "alternative")]
    h0 = [h for h in hypotheses if h.get("label") in ("H0", "null")]

    if not h1:
        issues.append("❓ No primary hypothesis (H1) logged.")
    if not h0:
        issues.append("⚠️  No null hypothesis (H0) — what would falsify your H1?")

    contradicting = [p for p in papers if p.get("contradicts") or p.get("properties", {}).get("contradicts")]
    if contradicting:
        issues.append(f"🔴 {len(contradicting)} paper(s) flagged as contradicting your hypothesis — engaged?")

    last_lit = props.get("last_lit_scout")
    if last_lit:
        d = days_since(last_lit)
        if d is not None and d > 21:
            issues.append(f"📚 Last literature search was {d} days ago — field may have moved.")
    else:
        issues.append("📚 No literature search recorded for this project yet.")

    unsummarized = [p for p in papers if not (p.get("summary") or p.get("properties", {}).get("summary"))]
    if unsummarized:
        issues.append(f"📄 {len(unsummarized)} paper(s) linked but never summarized.")

    if not experiments:
        issues.append("🔬 No experiments logged — is your study design documented?")
    else:
        no_design = [e for e in experiments if not (e.get("design") or e.get("properties", {}).get("design"))]
        if no_design:
            issues.append(f"🔬 {len(no_design)} experiment(s) have no design notes.")
        power_done = any(e.get("power_analysis") or e.get("properties", {}).get("power_analysis") for e in experiments)
        if not power_done:
            issues.append("📊 No power analysis on record — run lab-biostat --mode power.")

    last_updated = props.get("last_updated") or props.get("updated")
    if last_updated:
        d = days_since(last_updated)
        if d is not None and d > 14:
            issues.append(f"💤 Project hasn't been updated in {d} days — stalled?")

    return issues


# ─── Question banks ───────────────────────────────────────────────────────────

QUESTIONS = {
    "hypothesis": [
        "What would falsify your H1? Be specific — give me the data pattern that would kill it.",
        "If your H1 is true, what's the mechanism? Is that mechanism independently testable?",
        "What's the effect size you're expecting, and why that magnitude?",
        "Have you directly engaged with the papers that challenge your hypothesis?",
        "What's the single weakest link in your theoretical chain right now?",
    ],
    "gaps": [
        "What's the most important paper in your field you haven't read yet?",
        "Who are the 3 labs doing work closest to yours right now? What are they finding?",
        "What's a question in your field nobody is asking — gap or dead end?",
        "Is your lit review broad enough to claim you know the landscape?",
        "What would change your mind about your core assumption?",
    ],
    "methods": [
        "Walk me through your study design. What are your controls?",
        "What's your N? Have you done a power analysis? If not — run lab-biostat --mode power.",
        "What are your top 3 confounds? How are you handling each one?",
        "If you got a null result, would it be informative or just ambiguous?",
        "Is your outcome measure the right one, or just the available one?",
    ],
    "writing": [
        "Who is your target reader — generalist or specialist?",
        "Say in one sentence what this paper is about. No jargon.",
        "What gap in the literature does your paper fill? One sentence.",
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
    if focus and focus in QUESTIONS:
        return QUESTIONS[focus]
    if any("H1" in d or "H0" in d or "hypothesis" in d.lower() for d in diagnostics):
        return QUESTIONS["hypothesis"]
    if any("literature" in d.lower() or "paper" in d.lower() for d in diagnostics):
        return QUESTIONS["gaps"]
    if any("experiment" in d.lower() or "power" in d.lower() for d in diagnostics):
        return QUESTIONS["methods"]
    return QUESTIONS["hypothesis"]


# ─── Session ──────────────────────────────────────────────────────────────────

def run_session(project: dict, mode: str, focus: str | None, nodes: list[dict], config: dict):
    props = project.get("properties", project)
    project_name = props.get("name", project.get("id", "project"))
    user = config.get("user", "researcher")

    diagnostics = run_diagnostics(project, nodes)
    questions   = pick_questions(focus, diagnostics)

    section_header(f"🎓 Lab Research Advisor — {project_name}")

    last_session = props.get("last_advisor_session")
    days_ago = f"{days_since(last_session)} days ago" if last_session else "never"

    if mode == "hard":
        print(f"\n🎓 Alright {user}, let's talk about **{project_name}**.")
        print(f"   Last session: {days_ago}.\n")
        if diagnostics:
            print("🎓 Here's what I'm seeing:\n" + "\n".join(f"   • {d}" for d in diagnostics))
    else:
        print(f"\n🎓 Hey {user}, good to check in on **{project_name}**.")
        print(f"   Last session: {days_ago}.\n")
        if diagnostics:
            print("🎓 A few things worth looking at:\n" + "\n".join(f"   • {d}" for d in diagnostics))

    session_log = []
    q_index = 0
    EXIT_WORDS = {"done", "exit", "quit", "thanks", "thank you", "enough", "stop"}

    # First question
    try:
        answer = checkpoint(questions[0], emoji="🎓")
    except CheckpointAborted:
        answer = ""

    while answer and answer.lower() not in EXIT_WORDS:
        session_log.append({"q": questions[q_index % len(questions)], "a": answer})
        q_index += 1

        # After 5 exchanges, offer to wrap
        if len(session_log) >= 5:
            try:
                cont = checkpoint(
                    "We've covered a lot. Keep going or wrap up?",
                    options=["keep going", "wrap up"],
                    default="wrap up",
                    emoji="🎓",
                )
                if cont.lower() in ("wrap up", "wrap", "done", "stop"):
                    break
            except CheckpointAborted:
                break

        if q_index >= len(questions):
            q_index = 0  # cycle through

        ack = "Okay." if mode == "hard" else "Good."
        try:
            answer = checkpoint(f"{ack} {questions[q_index % len(questions)]}", emoji="🎓")
        except CheckpointAborted:
            break

    return session_log, diagnostics


# ─── Summary ──────────────────────────────────────────────────────────────────

def extract_action_items(session_log: list) -> list[str]:
    items = []
    keywords = {
        "power analysis": "Run lab-biostat --mode power",
        "lit-scout":      "Run lab-lit-scout to update literature",
        "hypothesis":     "Log H0 / falsification criteria in research graph",
        "paper":          "Summarize and link flagged papers in research graph",
        "design":         "Document study design and controls",
        "null":           "Define null hypothesis (H0)",
    }
    full_text = " ".join(qa["a"].lower() for qa in session_log)
    for kw, action in keywords.items():
        if kw in full_text and action not in items:
            items.append(action)
    return items or ["Review session notes and update research graph"]


def print_summary(project_name: str, session_log: list, action_items: list):
    section_header(f"📋 Session Summary — {project_name} — {today_str()}")
    print("\n**Questions addressed:**")
    for i, qa in enumerate(session_log, 1):
        preview = qa["a"][:80] + "…" if len(qa["a"]) > 80 else qa["a"]
        print(f"  Q{i}: {qa['q'][:70]}")
        print(f"      → {preview}")
    print("\n**Action items:**")
    for item in action_items:
        print(f"  [ ] {item}")
    print(f"\n**Next check-in:** ~2 weeks or when action items are done")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS Research Advisor")
    parser.add_argument("--project", "-p", help="Project name")
    parser.add_argument("--mode", choices=["hard", "supportive"], default="hard")
    parser.add_argument("--focus", choices=list(QUESTIONS.keys()))
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    # Pick project
    if args.project:
        project = find_project(nodes, args.project)
        if not project:
            print(f"❌ No project matching '{args.project}'.")
            sys.exit(1)
    else:
        projects = [n for n in nodes if n.get("type") == "Project"]
        if not projects:
            print("❌ No projects found. Run lab-init first.")
            sys.exit(1)
        if len(projects) == 1:
            project = projects[0]
        else:
            print("📋 Multiple projects — pick one:")
            for i, p in enumerate(projects):
                props = p.get("properties", p)
                print(f"  [{i+1}] {props.get('name', p.get('id'))}")
            try:
                choice = checkpoint("Enter number:", emoji="📋")
                project = projects[int(choice) - 1]
            except (CheckpointAborted, ValueError, IndexError):
                sys.exit(1)

    # Run
    session_log, diagnostics = run_session(project, args.mode, args.focus, nodes, config)

    action_items = extract_action_items(session_log)
    props = project.get("properties", project)
    project_name = props.get("name", project.get("id", "project"))

    print_summary(project_name, session_log, action_items)

    # Persist
    SESSIONS_DIR_path = Path(__file__).parent.parent / "sessions"
    session_content = "\n".join(
        f"**Q:** {qa['q']}\n**A:** {qa['a']}" for qa in session_log
    )
    session_file = log_session("lab-research-advisor", project_name, session_content)
    print(f"\n💾 Session saved: {session_file}")

    nodes = save_graph(
        [{**n, "properties": {**n.get("properties", n), "last_advisor_session": now_iso()}}
         if n.get("id") == project.get("id") else n
         for n in nodes]
    ) or nodes
    # Direct update
    from lab_utils import update_node, save_graph as sg
    nodes_updated = update_node(nodes, project.get("id", ""), {"last_advisor_session": now_iso()})
    sg(nodes_updated)

    award_xp(30, "🎓 Mentored")
    print("\n✅ Advisor session complete.\n")


if __name__ == "__main__":
    with AgentWorking("sage", "Advising..."):
        main()
