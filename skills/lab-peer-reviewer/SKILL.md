# lab-peer-reviewer

## Description
Simulates rigorous peer review of your manuscript or any paper. Acts like a tough but fair anonymous reviewer or thesis committee member. Finds major concerns, minor issues, strengths, and line-level problems. Deliberately critical — the goal is to catch weaknesses before real reviewers do.

## When to activate
- User says "review my paper", "peer review this", "critique my draft", "lab-peer-reviewer"
- User wants pre-submission review
- User wants to stress-test a manuscript

## Usage
```bash
# Review your own draft:
openclaw lab-peer-reviewer --draft "path/to/draft.md" --mode "peer-review"

# Review an external paper:
openclaw lab-peer-reviewer --paper "zotero:key123" --mode "methods-critique"

# Pre-submission check:
openclaw lab-peer-reviewer --draft "path/to/draft.md" --mode "pre-submission" --journal "Nature Neuroscience"

# Devil's advocate:
openclaw lab-peer-reviewer --draft "path/to/draft.md" --mode "devil's-advocate"
```

## Modes
- `peer-review` (default): full anonymous reviewer simulation
- `methods-critique`: deep statistical and experimental design audit
- `pre-submission`: checklist against journal requirements
- `devil's-advocate`: steelman the opposing view, find the weakest claims

## Flags
- `--draft`: path to your manuscript (markdown or text)
- `--paper`: Zotero key or DOI of a paper to review
- `--mode`: review mode (default: peer-review)
- `--journal`: target journal for pre-submission mode
- `--project`: link review to a project in the graph

## Output
- Structured review report saved to Obsidian
- Review linked to draft node in research graph
- XP: +100
