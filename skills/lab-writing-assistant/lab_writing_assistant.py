#!/usr/bin/env python3
"""
lab-writing-assistant — Draft writer for LabOS
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_memory, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, find_project, get_project_papers,
    get_project_hypotheses, get_project_experiments,
    upsert_node, now_iso, today_str, short_hash,
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



SECTION_TYPES = [
    "introduction", "abstract", "methods", "results",
    "discussion", "grant-aim", "cover-letter", "response-to-reviewers"
]


# ─── Context ──────────────────────────────────────────────────────────────────

def build_context(project: dict, nodes: list[dict], config: dict) -> dict:
    pid   = project.get("id", "")
    props = project.get("properties", project)

    papers      = get_project_papers(nodes, pid)
    hypotheses  = get_project_hypotheses(nodes, pid)
    experiments = get_project_experiments(nodes, pid)

    h1 = next((h for h in hypotheses if h.get("label") in ("H1", "alternative")), None)
    h0 = next((h for h in hypotheses if h.get("label") in ("H0", "null")), None)

    def pp(n): return n.get("properties", n)

    paper_list = [{
        "title":      pp(p).get("title", "Untitled"),
        "key":        pp(p).get("zotero_key", pp(p).get("doi", p.get("id", "unknown"))),
        "finding":    pp(p).get("key_finding", ""),
        "contradicts": pp(p).get("contradicts", False),
    } for p in papers]

    exp_list = [{
        "name":    pp(e).get("name", "Experiment"),
        "design":  pp(e).get("design", ""),
        "n":       pp(e).get("sample_size", "N=?"),
        "results": pp(e).get("results", "[RESULTS PENDING]"),
        "controls":pp(e).get("controls", ""),
    } for e in experiments]

    return {
        "project_id":    pid,
        "project_name":  props.get("name", pid),
        "description":   props.get("description", ""),
        "fields":        config.get("fields", []),
        "writing_style": config.get("writing_style", "clear, direct academic prose"),
        "citation_format": config.get("citation_format", "APA"),
        "h1":      h1.get("text", "") if h1 else "",
        "h0":      h0.get("text", "") if h0 else "",
        "papers":  paper_list,
        "experiments": exp_list,
        "sensitivity": props.get("sensitivity", "internal"),
    }


def fmt_papers(papers: list[dict]) -> str:
    if not papers:
        return "  (no papers linked — run lab-lit-scout first)"
    lines = []
    for p in papers:
        flag    = " [CONTRADICTS]" if p.get("contradicts") else ""
        finding = f' — "{p["finding"]}"' if p.get("finding") else ""
        lines.append(f'  - [CITE:{p["key"]}] {p["title"]}{finding}{flag}')
    return "\n".join(lines)


def fmt_experiments(experiments: list[dict]) -> str:
    if not experiments:
        return "  (no experiments logged)"
    return "\n".join(
        f'  - {e["name"]}: N={e["n"]}, design={e["design"] or "?"}, results={e["results"]}'
        for e in experiments
    )


# ─── Prompt builders ──────────────────────────────────────────────────────────

BASE = (
    "Writing style: {style}. "
    "Use [CITE:zotero_key] as citation placeholders. "
    "Mark any section needing real data as [RESULTS PENDING]. "
    "Mark anything requiring the researcher's input as [SPECIFY: ...].\n"
    "Add at top: <!-- Draft by lab-writing-assistant {date} — review before use -->\n\n"
)


def build_prompt(section: str, ctx: dict, journal: str | None,
                 aim_num: int, reviewer_comments: str, existing_draft: str) -> str:
    papers_str  = fmt_papers(ctx["papers"])
    exps_str    = fmt_experiments(ctx["experiments"])
    style       = ctx["writing_style"]
    fields      = ", ".join(ctx["fields"]) or "biomedical research"
    journal_str = journal or "general academic"
    date        = today_str()

    base = BASE.format(style=style, date=date)
    if existing_draft:
        base += f"Existing draft to extend/revise:\n---\n{existing_draft}\n---\n\n"

    prompts = {
        "introduction": f"""{base}Write an academic introduction.

Project: {ctx['project_name']}
Field: {fields} | Journal style: {journal_str}
Core gap: {ctx['description']}
Primary hypothesis: {ctx['h1'] or '[not yet defined]'}
Papers:
{papers_str}

Structure: (1) broad hook, (2) narrow to gap with citations, (3) state problem,
(4) what this paper does, (5) roadmap. Active voice. No filler phrases.
Target: 400–600 words.""",

        "abstract": f"""{base}Write a structured abstract.

Project: {ctx['project_name']}
Background/gap: {ctx['description']}
H1: {ctx['h1'] or '[not defined]'}
Experiments:
{exps_str}
Journal: {journal_str}

Format: IMRaD. Max 250 words. Use [RESULTS PENDING] where data is missing.""",

        "methods": f"""{base}Write a Methods section.

Project: {ctx['project_name']} | Field: {fields}
Experiments:
{exps_str}

Subsections: Participants/Samples, Materials/Measures, Procedure, Data Analysis.
Past tense, third person. Enough detail to replicate.
Cite methods references with [CITE:key]. Flag unknowns as [SPECIFY: ...].""",

        "results": f"""{base}Write a Results section.

Project: {ctx['project_name']}
Experiments:
{exps_str}
H1: {ctx['h1'] or '[not defined]'}

Report objectively. No interpretation. Past tense.
Reference figures as [FIGURE X]. Flag pending data as [RESULTS PENDING].""",

        "discussion": f"""{base}Write a Discussion section.

Project: {ctx['project_name']}
Findings:
{exps_str}
H1: {ctx['h1'] or '[not defined]'} — [supported/not/mixed — fill in]
Prior work:
{papers_str}

Structure: (1) restate finding, (2) compare to prior work (cite contradicting papers),
(3) mechanistic interpretation, (4) limitations, (5) future directions, (6) conclusion.
Do not overclaim. Target: 600–800 words.""",

        "grant-aim": f"""{base}Write Specific Aim {aim_num} for an NIH-style grant.

Project: {ctx['project_name']}
Goal: {ctx['description']}
This aim's hypothesis: {ctx['h1'] or '[define]'}
Approach:
{exps_str}
Literature:
{papers_str}

1 paragraph ~150 words. End with expected outcome. Strong active language. No hedging.""",

        "cover-letter": f"""{base}Write a journal cover letter.

Paper: {ctx['project_name']} | Journal: {journal_str} | Field: {fields}
Contribution: {ctx['description']}
Key finding:
{exps_str}

Structure: (1) paper title + submission type, (2) what it does and why it matters,
(3) why this journal specifically, (4) originality statement, (5) closing.
Professional, confident. ~250 words.""",

        "response-to-reviewers": f"""{base}Draft a response to reviewers.

Paper: {ctx['project_name']}
Reviewer comments:
{reviewer_comments or '[No comments provided — add via --reviewer-comments]'}

For each comment: (1) brief thanks, (2) summarize concern, (3) substantive response,
(4) state manuscript change. Tone: professional, confident, not defensive.
Format: **Reviewer X, Comment Y:** / **Response:** / **Manuscript change:**""",
    }

    return prompts.get(section, f"{base}Write a {section} section for: {ctx['project_name']}.\n{ctx['description']}")


# ─── Save ─────────────────────────────────────────────────────────────────────

def save_draft(draft: str, project_name: str, section: str, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        draft_dir = Path(vault) / "Research" / "Projects" / project_name / "drafts"
    else:
        from lab_utils import LAB_DIR
        draft_dir = LAB_DIR / "drafts" / project_name
    draft_dir.mkdir(parents=True, exist_ok=True)
    path = draft_dir / f"{section}-{today_str()}.md"
    path.write_text(draft)
    return path


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS Writing Assistant")
    parser.add_argument("--project",  "-p", required=True)
    parser.add_argument("--section",  "--type", "-s", choices=SECTION_TYPES, required=True)
    parser.add_argument("--journal",  "-j")
    parser.add_argument("--aim",      type=int, default=1)
    parser.add_argument("--draft",    "-d", help="Existing draft to extend/revise")
    parser.add_argument("--reviewer-comments", "-r")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Skip interactive revision loop")
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    project = find_project(nodes, args.project)
    if not project:
        print(f"❌ No project matching '{args.project}'.")
        sys.exit(1)

    props        = project.get("properties", project)
    project_name = props.get("name", project.get("id", args.project))
    project_id   = project.get("id", "")

    section_header(f"✍️  Lab Writing Assistant — {project_name} — {args.section}")

    # Security pre-flight
    sensitivity = props.get("sensitivity", "internal")
    if sensitivity in ("sensitive", "confidential"):
        if not confirm(
            f"Project is [{sensitivity.upper()}]. Send content to LLM API?",
            default=False
        ):
            print("❌ Aborted.")
            sys.exit(0)

    # Load existing draft
    existing_draft = ""
    if args.draft:
        p = Path(args.draft)
        if p.exists():
            existing_draft = p.read_text()
            progress(f"Extending existing draft: {p}", "📄")
        else:
            print(f"⚠️  Draft file not found: {p} — starting fresh.")

    # Build and show outline checkpoint for long sections
    ctx = build_context(project, nodes, config)

    if args.section in ("introduction", "discussion", "methods") and not args.no_interactive:
        try:
            choice = checkpoint(
                f"Ready to draft the {args.section}. Want to review the context first?",
                options=["yes", "no"],
                default="no",
                emoji="📋",
            )
            if choice.lower() in ("yes", "y"):
                print(f"\n📋 Context loaded for **{project_name}**:")
                print(f"   H1: {ctx['h1'] or '[not defined]'}")
                print(f"   Papers: {len(ctx['papers'])}")
                print(f"   Experiments: {len(ctx['experiments'])}")
                if ctx["papers"]:
                    print(f"   First paper: {ctx['papers'][0]['title'][:60]}")
                confirm("Proceed with draft?", default=True)
        except CheckpointAborted:
            print("❌ Aborted.")
            sys.exit(0)

    # Generate
    prompt = build_prompt(
        section=args.section, ctx=ctx, journal=args.journal,
        aim_num=args.aim, reviewer_comments=args.reviewer_comments or "",
        existing_draft=existing_draft,
    )
    progress(f"Generating {args.section} draft…", "🤖")
    draft = call_llm(prompt, config.get("llm_model"))

    if not draft.strip():
        print("❌ No draft generated.")
        sys.exit(1)

    # Show draft
    print("\n" + "═" * 60)
    print(f"  📝 {args.section.upper()} — {project_name}")
    print("═" * 60 + "\n")
    print(draft)
    print("\n" + "═" * 60)

    # Interactive revision loop
    if not args.no_interactive:
        def _save(content: str) -> Path:
            return save_draft(content, project_name, args.section, config)

        draft = interactive_loop(
            content=draft,
            content_type=f"{args.section} draft",
            save_fn=_save,
            config=config,
        )
    else:
        path = save_draft(draft, project_name, args.section, config)
        print(f"\n💾 Draft saved: {path}")

    # Flags summary
    word_count = len(draft.split())
    print(f"\n📊 Word count: {word_count}")
    if "[CITE:" in draft:
        print(f"📚 {draft.count('[CITE:')} citation placeholder(s) — replace before submission")
    if "[RESULTS PENDING]" in draft:
        print("⚠️  [RESULTS PENDING] sections need your actual data")
    if "[SPECIFY:" in draft:
        print("🔧 [SPECIFY: ...] sections need your input")
    print("\n⚠️  First draft — review carefully before use.")

    # Update graph
    draft_node = {
        "type": "Draft", "id": f"draft_{short_hash(project_id + args.section + today_str())}",
        "project": project_id, "section": args.section,
        "status": "first-draft", "created": now_iso(), "word_count": word_count,
    }
    nodes = upsert_node(nodes, draft_node)
    save_graph(nodes)

    # Session log
    log_session("lab-writing-assistant", project_name,
                f"Section: {args.section}\nWords: {word_count}\n\n{draft[:500]}…")

    # XP
    badge = "✍️ Author" if not any("✍️ Author" in b for b in load_config().get("badges", [])) else None
    award_xp(200, "✍️ Author")

    print("\n✅ Done.\n")


if __name__ == "__main__":
    with AgentWorking("quill", "Writing..."):
        main()
