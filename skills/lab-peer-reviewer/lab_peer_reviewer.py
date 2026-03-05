#!/usr/bin/env python3
"""
lab-peer-reviewer — Simulates rigorous peer review for LabOS
Modes: peer-review, methods-critique, pre-submission, devil's-advocate
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, find_project, get_project_hypotheses, get_project_papers,
    upsert_node, now_iso, today_str, short_hash, LAB_DIR,
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


MODES = ["peer-review", "methods-critique", "pre-submission", "devil's-advocate"]


def load_draft(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"❌ Draft file not found: {path}")
        sys.exit(1)
    return p.read_text()


def build_prompt(mode: str, content: str, ctx: dict) -> str:
    project_name = ctx.get("project_name", "")
    h1           = ctx.get("h1", "")
    papers_block = ctx.get("papers_block", "")

    base = (
        f"Project: {project_name}\n"
        f"H1: {h1 or '[not provided]'}\n"
        f"Key papers:\n{papers_block or '  (none linked)'}\n\n"
        f"---\n{content[:5000]}\n---\n\n"
    )

    if mode == "peer-review":
        return (
            "You are a rigorous but fair anonymous peer reviewer at a top journal. "
            "Review this manuscript section critically.\n\n"
            + base +
            "Structure your review exactly as:\n\n"
            "## Major Concerns (would block acceptance)\n"
            "  (numbered list — each with specific line/claim reference)\n\n"
            "## Minor Concerns (require revision)\n"
            "  (numbered list)\n\n"
            "## Strengths\n"
            "  (what's working — be specific, not generic)\n\n"
            "## Line-Level Comments\n"
            "  (specific passages that need attention)\n\n"
            "## Recommendation\n"
            "  Reject / Major Revision / Minor Revision / Accept (with justification)\n\n"
            "Be demanding. The goal is to catch every weakness before submission."
        )

    elif mode == "methods-critique":
        return (
            "You are a senior biostatistician and methodologist. "
            "Perform a deep critique of the methods in this text.\n\n"
            + base +
            "Evaluate:\n"
            "1. Study design validity (internal/external threats)\n"
            "2. Statistical test appropriateness — is it right for the data/question?\n"
            "3. Assumption checking — stated? tested?\n"
            "4. Sample size / power — justified?\n"
            "5. Multiple comparisons — addressed?\n"
            "6. Effect sizes — reported?\n"
            "7. Confounds — controlled?\n"
            "8. Blinding / randomization (if applicable)\n"
            "9. Missing data handling\n"
            "10. Any risk of p-hacking or HARKing\n\n"
            "Rate each: ✅ OK / ⚠️ Concern / ❌ Problem\n"
            "For each ⚠️ or ❌: exact fix required."
        )

    elif mode == "pre-submission":
        return (
            "You are checking this manuscript before journal submission. "
            "Run a complete pre-submission checklist.\n\n"
            + base +
            "Check and rate ✅/⚠️/❌:\n\n"
            "**Structure**\n"
            "- Title: informative, specific, not oversold?\n"
            "- Abstract: structured, within word limit, matches paper?\n"
            "- Introduction: clear gap, hypothesis stated?\n"
            "- Methods: reproducible, all details present?\n"
            "- Results: objective, no interpretation, figures/tables referenced?\n"
            "- Discussion: addresses H0, acknowledges limitations, no overclaiming?\n"
            "- Conclusion: matches data, no new claims?\n\n"
            "**References**\n"
            "- All in-text citations in reference list?\n"
            "- Format consistent?\n"
            "- Key papers in the field cited?\n\n"
            "**Ethics / Admin**\n"
            "- Ethics statement needed?\n"
            "- Data availability statement?\n"
            "- Conflict of interest?\n"
            "- Author contributions?\n\n"
            "**Final verdict:** Ready / Needs Work / Major Issues"
        )

    elif mode == "devil's-advocate":
        return (
            "You are a highly skeptical scientist who disagrees with this research. "
            "Steelman the opposing view. Find every weakness. Play devil's advocate.\n\n"
            + base +
            "Generate:\n\n"
            "## The Strongest Counterargument\n"
            "  (the best argument against the main claim)\n\n"
            "## Weakest Claims in This Work\n"
            "  (ranked from most to least vulnerable)\n\n"
            "## Alternative Explanations\n"
            "  (other ways to explain the findings)\n\n"
            "## What Would Genuinely Falsify This?\n"
            "  (the experiment that would kill the hypothesis)\n\n"
            "## The Reviewer Who Will Reject This\n"
            "  (what they'll say, verbatim, in 3-4 sentences)\n\n"
            "Be brutal. The author needs to know what they'll face."
        )

    return base


def save_review(review: str, project_name: str, mode: str, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        out_dir = Path(vault) / "Research" / "Projects" / project_name / "reviews"
    else:
        out_dir = LAB_DIR / "reviews" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today_str()}-{mode}.md"
    path.write_text(f"# Peer Review — {mode} — {today_str()}\n\n{review}")
    return path


def main():
    parser = argparse.ArgumentParser(description="LabOS Peer Reviewer")
    parser.add_argument("--mode", "-m", choices=MODES, default="peer-review")
    parser.add_argument("--draft",  "-d", help="Path to draft manuscript")
    parser.add_argument("--paper",  "-p", help="Zotero key or path to external paper")
    parser.add_argument("--project",      help="Project name (for context)")
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    # Load content
    if args.draft:
        content = load_draft(args.draft)
        content_label = f"draft ({args.draft})"
    elif args.paper:
        content = load_draft(args.paper)
        content_label = f"paper ({args.paper})"
    else:
        try:
            path = checkpoint("Path to draft or paper to review?", emoji="📄")
            content = load_draft(path)
            content_label = f"draft ({path})"
        except CheckpointAborted:
            print("❌ No content provided.")
            sys.exit(1)

    # Project context
    project    = find_project(nodes, args.project) if args.project else None
    hypotheses = get_project_hypotheses(nodes, project.get("id","")) if project else []
    papers     = get_project_papers(nodes, project.get("id","")) if project else []

    project_name = ""
    if project:
        props        = project.get("properties", project)
        project_name = props.get("name", "")

    papers_block = "\n".join(
        f"  - {p.get('title','?')[:60]} ({p.get('year','?')})"
        for p in papers[:5]
    )

    ctx = {
        "project_name": project_name,
        "h1": hypotheses[0].get("text","") if hypotheses else "",
        "papers_block": papers_block,
    }

    section_header(f"🤺 Peer Reviewer — {args.mode}")
    if project_name:
        print(f"   Project: {project_name}")
    print(f"   Content: {content_label}\n")

    prompt = build_prompt(args.mode, content, ctx)

    progress("Generating review…", "🤖")
    review = call_llm(prompt)

    print("\n" + "═"*60)
    print(review)
    print("═"*60)

    if not args.no_interactive:
        review = interactive_loop(
            content=review,
            content_type=f"{args.mode} review",
            config=config,
        )

    # Save
    if project_name:
        rev_path = save_review(review, project_name, args.mode, config)
        print(f"\n💾 Review saved: {rev_path}")

        # Add review node to graph
        review_node = {
            "type": "Review",
            "id": f"review_{short_hash(project_name + args.mode + today_str())}",
            "project": project.get("id","") if project else "",
            "mode": args.mode,
            "path": str(rev_path),
            "created": now_iso(),
        }
        nodes = upsert_node(nodes, review_node)
        save_graph(nodes)

    log_session("lab-peer-reviewer", project_name or "global",
                f"Mode: {args.mode}\n\n{review[:500]}…")

    xp_badges = {
        "peer-review":      (100, "🤺 Devil's Advocate"),
        "methods-critique": (75,  "🔬 Rigorous"),
        "pre-submission":   (50,  None),
        "devil's-advocate": (100, "🤺 Devil's Advocate"),
    }
    xp, badge = xp_badges.get(args.mode, (50, None))
    award_xp(xp, badge)
    print("\n✅ Review complete.\n")


if __name__ == "__main__":
    with AgentWorking("critic", "Reviewing..."):
        main()
