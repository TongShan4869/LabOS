# lab-research-advisor

## Description
Socratic mentor agent. Pulls your project context from the research graph and asks the hard questions a good PI would ask — challenging assumptions, surfacing gaps, pushing you to think more rigorously. Not a yes-machine. Configurable between hard mode (default) and supportive mode.

## When to activate
- User says "advise me on my project", "research advisor", "lab-research-advisor", "review my thinking"
- User wants a Socratic session on their research
- User seems stuck or wants to stress-test a hypothesis

## Usage
```bash
openclaw lab-research-advisor --project "neural-coupling"
openclaw lab-research-advisor                          # global view, all projects
openclaw lab-research-advisor --mode supportive        # gentler feedback
openclaw lab-research-advisor --focus "hypothesis"     # focus on hypothesis critique
openclaw lab-research-advisor --focus "gaps"           # focus on literature gaps
openclaw lab-research-advisor --focus "methods"        # focus on methodology
```

## Flags
- `--project` (optional): focus on a specific project
- `--mode` (optional): `hard` (default) or `supportive`
- `--focus` (optional): `hypothesis` / `gaps` / `methods` / `writing` / `next-steps`

## Prerequisites
- `LAB_CONFIG.json` must exist
- At least one Project node in research-graph.jsonl

## Output
- Interactive conversational session
- Session log saved to `sessions/`
- LAB_MEMORY.md updated if new patterns observed
- XP: +30
