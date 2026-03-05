#!/usr/bin/env python3
"""
lab-publishing-assistant — Journal selection and submission prep for LabOS
Modes: find-journal, reformat, checklist, references, cover-letter
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, find_project, get_project_hypotheses,
    get_project_papers, get_project_experiments,
    now_iso, today_str, short_hash, LAB_DIR,
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


MODES = ["find-journal", "reformat", "checklist", "references", "cover-letter"]

# ─── Known journal families (for formatting guidance) ──────────────────────────

JOURNAL_FAMILIES = {
    "nature": {
        "style": "Nature family",
        "abstract": "unstructured, ≤150 words",
        "word_limit": "varies by journal (Nature: ~3000 main text)",
        "figure_format": "TIFF/EPS, 300 dpi min",
        "references": "numbered superscripts",
        "oa_option": "Nature Portfolio OA available",
        "notes": "Requires significance/impact statement. Very competitive.",
    },
    "plos": {
        "style": "PLOS ONE family",
        "abstract": "structured (Background/Methods/Results/Conclusions), ≤300 words",
        "word_limit": "no strict limit",
        "figure_format": "TIFF/EPS, 300 dpi, max 10 MB",
        "references": "numbered [1], [2]...",
        "oa_option": "Fully open access (APC required)",
        "notes": "Focus on scientific rigor, not perceived impact.",
    },
    "elsevier": {
        "style": "Elsevier",
        "abstract": "structured, ≤250 words, with highlights (3-5 bullet points)",
        "word_limit": "varies by journal",
        "figure_format": "TIFF/EPS/PDF, 300-600 dpi",
        "references": "numbered or author-year (journal-specific)",
        "oa_option": "Optional OA (hybrid)",
        "notes": "Requires graphical abstract. Check journal-specific guide.",
    },
    "apa": {
        "style": "APA journals",
        "abstract": "unstructured, ≤250 words",
        "word_limit": "varies",
        "figure_format": "TIFF, 300 dpi",
        "references": "APA 7th edition author-year",
        "oa_option": "Varies by journal",
        "notes": "Statistical reporting: include effect sizes and CIs.",
    },
    "frontiers": {
        "style": "Frontiers",
        "abstract": "structured, ≤350 words",
        "word_limit": "Original Research: ≤12,000 words",
        "figure_format": "TIFF/JPEG, 300 dpi",
        "references": "numbered",
        "oa_option": "Fully open access (APC required)",
        "notes": "Interactive review process. Fast turnaround.",
    },
}


def detect_journal_family(journal_name: str) -> dict:
    name = journal_name.lower()
    for key, info in JOURNAL_FAMILIES.items():
        if key in name:
            return info
    return {}


# ─── Mode: find-journal ───────────────────────────────────────────────────────

def mode_find_journal(project: dict | None, hypotheses: list, papers: list,
                      experiments: list, config: dict) -> str:
    section_header("📚 Journal Finder")

    fields      = config.get("fields", [])
    pref_oa     = config.get("prefer_open_access", False)
    project_desc = ""
    if project:
        props        = project.get("properties", project)
        project_desc = props.get("description", props.get("name", ""))

    h1_text = hypotheses[0].get("text", "") if hypotheses else ""

    # Gather preferences interactively
    try:
        impact_pref = checkpoint(
            "Priority: impact factor, open access, fast turnaround, or field fit?",
            options=["impact", "open-access", "speed", "fit"],
            default="fit",
            emoji="🎯",
        )
    except CheckpointAborted:
        impact_pref = "fit"

    try:
        paper_type = checkpoint(
            "Paper type?",
            options=["original-research", "review", "methods", "brief-report", "case-study"],
            default="original-research",
            allow_freetext=False,
            emoji="📄",
        )
    except CheckpointAborted:
        paper_type = "original-research"

    prompt = (
        f"You are a publishing advisor helping a researcher choose the right journal.\n\n"
        f"Research summary:\n"
        f"- Fields: {', '.join(fields)}\n"
        f"- Hypothesis: {h1_text or '[not provided]'}\n"
        f"- Project: {project_desc or '[not provided]'}\n"
        f"- Paper type: {paper_type}\n"
        f"- Priority: {impact_pref}\n"
        f"- Open access preference: {'yes' if pref_oa else 'flexible'}\n"
        f"- Key papers already in the literature: {len(papers)} references\n\n"
        f"Recommend 5 journals/conferences ranked by fit. For each:\n"
        f"1. Journal name\n"
        f"2. Publisher & impact factor (approximate)\n"
        f"3. Why it fits this work specifically\n"
        f"4. Open access option and approximate APC\n"
        f"5. Typical review time\n"
        f"6. One risk or consideration\n\n"
        f"After the list, flag any predatory journal risks to avoid in this field.\n"
        f"Format as a clear ranked list."
    )

    progress("Searching for best journal matches…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)
    return result


# ─── Mode: reformat ───────────────────────────────────────────────────────────

def mode_reformat(draft_path: str, target_journal: str, config: dict) -> str:
    section_header(f"📐 Reformat — {target_journal}")

    content     = Path(draft_path).read_text() if Path(draft_path).exists() else ""
    word_count  = len(content.split())
    family_info = detect_journal_family(target_journal)

    if family_info:
        print(f"\n📋 Detected journal family: {family_info['style']}")
        print(f"   Abstract: {family_info['abstract']}")
        print(f"   Word limit: {family_info['word_limit']}")
        print(f"   References: {family_info['references']}")
        print(f"   Figures: {family_info['figure_format']}")
        if family_info.get("notes"):
            print(f"   📌 {family_info['notes']}")

    prompt = (
        f"Reformat this manuscript for submission to {target_journal}.\n\n"
        f"Current word count: {word_count}\n"
        + (f"Journal requirements:\n{json.dumps(family_info, indent=2)}\n\n" if family_info else "")
        + f"Manuscript:\n---\n{content[:5000]}\n---\n\n"
        "Provide:\n"
        "1. **Diff list** — specific changes required (section order, word limits, abstract format, etc.)\n"
        "2. **Abstract** — reformatted to journal spec (if needed)\n"
        "3. **Figure checklist** — required format, resolution, caption style\n"
        "4. **Submission folder structure** — what files to prepare\n"
        "5. **Manual attention items** — ethics statement, data availability, COI, author contributions\n\n"
        "Be specific and actionable. Flag anything that needs the researcher's input as [ACTION REQUIRED: ...]."
    )

    progress("Generating reformat guide…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)
    return result


# ─── Mode: checklist ──────────────────────────────────────────────────────────

def mode_checklist(draft_path: str, target_journal: str) -> str:
    section_header(f"✅ Pre-Submission Checklist — {target_journal or 'General'}")

    content    = Path(draft_path).read_text() if Path(draft_path).exists() else ""
    word_count = len(content.split())

    prompt = (
        f"Run a pre-submission checklist for this manuscript"
        + (f" targeting {target_journal}" if target_journal else "")
        + f". Current word count: {word_count}.\n\n"
        f"Manuscript:\n---\n{content[:4000]}\n---\n\n"
        "Check each item and rate ✅ / ⚠️ / ❌ / ❓ (cannot verify):\n\n"
        "**Manuscript Structure**\n"
        "- [ ] Title: informative, not oversold, within character limit\n"
        "- [ ] Abstract: structured correctly, within word limit, matches paper\n"
        "- [ ] Keywords: 5-8 relevant terms\n"
        "- [ ] Introduction: clear gap, hypothesis stated explicitly\n"
        "- [ ] Methods: reproducible, ethical approval mentioned if needed\n"
        "- [ ] Results: objective, figures/tables all referenced in text\n"
        "- [ ] Discussion: addresses H0, acknowledges limitations, no new data\n"
        "- [ ] Conclusion: concise, matches data, no overclaiming\n\n"
        "**References**\n"
        "- [ ] All in-text citations present in reference list\n"
        "- [ ] Format consistent throughout\n"
        "- [ ] Seminal papers in the field cited\n"
        "- [ ] No self-citation bias\n\n"
        "**Figures & Tables**\n"
        "- [ ] All figures/tables mentioned in text\n"
        "- [ ] Captions self-explanatory\n"
        "- [ ] Resolution meets requirements\n\n"
        "**Ethics & Admin**\n"
        "- [ ] Ethics approval statement (if human/animal subjects)\n"
        "- [ ] Data availability statement\n"
        "- [ ] Conflict of interest statement\n"
        "- [ ] Author contributions (CRediT taxonomy)\n"
        "- [ ] Funding acknowledgement\n\n"
        "End with: **Overall verdict** (Ready / Needs Work / Major Issues) and top 3 priority fixes."
    )

    progress("Running pre-submission checklist…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)
    return result


# ─── Mode: references ─────────────────────────────────────────────────────────

def mode_references(draft_path: str, target_journal: str, config: dict) -> str:
    section_header(f"📚 Reference Formatter — {target_journal or 'APA'}")

    citation_format = config.get("citation_format", "APA")
    family_info     = detect_journal_family(target_journal) if target_journal else {}
    ref_style       = family_info.get("references", citation_format)
    content         = Path(draft_path).read_text() if Path(draft_path).exists() else ""

    prompt = (
        f"Reformat all references in this document to {ref_style} style for {target_journal or 'general submission'}.\n\n"
        f"Document:\n---\n{content[:6000]}\n---\n\n"
        "Output:\n"
        "1. **Reformatted reference list** — all references in correct format\n"
        "2. **Inconsistencies found** — any references that couldn't be fully reformatted\n"
        "3. **Missing information** — DOIs, page numbers, etc. that need to be filled in\n"
        "4. **In-text citation style** — confirm format matches (numbered vs author-year)"
    )

    progress("Reformatting references…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)
    return result


# ─── Mode: cover-letter ───────────────────────────────────────────────────────

def mode_cover_letter(project: dict | None, hypotheses: list, experiments: list,
                      target_journal: str, config: dict) -> str:
    section_header(f"✉️  Cover Letter — {target_journal}")

    fields       = config.get("fields", [])
    project_desc = ""
    project_name = ""
    if project:
        props        = project.get("properties", project)
        project_desc = props.get("description", "")
        project_name = props.get("name", "")

    h1_text = hypotheses[0].get("text", "") if hypotheses else ""
    finding = experiments[0].get("results", "[RESULTS PENDING]") if experiments else ""

    prompt = (
        f"Write a professional cover letter for journal submission.\n\n"
        f"Paper: {project_name or '[title]'}\n"
        f"Journal: {target_journal}\n"
        f"Field: {', '.join(fields)}\n"
        f"Core contribution: {project_desc or h1_text or '[describe the paper]'}\n"
        f"Key finding: {finding or '[key finding]'}\n\n"
        "Cover letter structure:\n"
        "1. Opening: paper title, submission type (Original Research), target journal\n"
        "2. What the paper does and why it matters (2-3 sentences, specific to this journal's scope)\n"
        "3. Why this journal specifically — reference their recent publications or stated scope\n"
        "4. Statement: original work, not under review elsewhere, all authors approved\n"
        "5. Optional: suggest or exclude specific reviewers\n"
        "6. Closing\n\n"
        "Tone: professional, confident, not overselling. ~300 words.\n"
        "Mark any field needing researcher input as [INSERT: ...]."
    )

    progress("Drafting cover letter…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)
    return result


# ─── Save ─────────────────────────────────────────────────────────────────────

def save_output(content: str, project_name: str, mode: str, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        out_dir = Path(vault) / "Research" / "Projects" / project_name / "publishing"
    else:
        out_dir = LAB_DIR / "publishing" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today_str()}-{mode}.md"
    path.write_text(f"# Publishing Assistant — {mode} — {today_str()}\n\n{content}")
    return path


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS Publishing Assistant")
    parser.add_argument("--mode",    "-m", choices=MODES, required=True)
    parser.add_argument("--project", "-p", help="Project name")
    parser.add_argument("--draft",   "-d", help="Path to manuscript draft")
    parser.add_argument("--target",  "-t", help="Target journal name")
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    project     = find_project(nodes, args.project) if args.project else None
    project_id  = project.get("id","") if project else ""
    hypotheses  = get_project_hypotheses(nodes, project_id) if project else []
    papers      = get_project_papers(nodes, project_id) if project else []
    experiments = get_project_experiments(nodes, project_id) if project else []
    project_name = ""
    if project:
        props        = project.get("properties", project)
        project_name = props.get("name", "")

    # Auto-prompt for missing args
    if args.mode in ("reformat", "checklist", "references") and not args.draft:
        try:
            args.draft = checkpoint("Path to manuscript draft?", emoji="📄")
        except CheckpointAborted:
            print("❌ Draft path required.")
            sys.exit(1)

    if args.mode in ("reformat", "checklist", "cover-letter", "references") and not args.target:
        try:
            args.target = checkpoint("Target journal?", emoji="📰")
        except CheckpointAborted:
            args.target = ""

    # Dispatch
    if args.mode == "find-journal":
        result = mode_find_journal(project, hypotheses, papers, experiments, config)

    elif args.mode == "reformat":
        result = mode_reformat(args.draft, args.target or "", config)

    elif args.mode == "checklist":
        result = mode_checklist(args.draft, args.target or "")

    elif args.mode == "references":
        result = mode_references(args.draft, args.target or "", config)

    elif args.mode == "cover-letter":
        result = mode_cover_letter(project, hypotheses, experiments, args.target or "", config)

    else:
        print(f"❌ Unknown mode: {args.mode}")
        sys.exit(1)

    # Interactive revision
    if not args.no_interactive:
        result = interactive_loop(
            content=result,
            content_type=f"{args.mode} output",
            config=config,
        )

    # Save
    if project_name and result:
        out_path = save_output(result, project_name, args.mode, config)
        print(f"\n💾 Saved: {out_path}")

    log_session("lab-publishing-assistant", project_name or "global",
                f"Mode: {args.mode}\n\n{result[:400]}…")

    xp_map = {
        "find-journal": (50, None),
        "reformat":     (100, None),
        "checklist":    (50, None),
        "references":   (30, None),
        "cover-letter": (75, "🚀 Launcher"),
    }
    xp, badge = xp_map.get(args.mode, (50, None))
    award_xp(xp, badge)
    print("\n✅ Done.\n")


if __name__ == "__main__":
    with AgentWorking("quill", "Publishing tasks..."):
        main()
