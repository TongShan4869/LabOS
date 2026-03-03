# lab-init

## Description
Onboard a new LabOS user. Scaffolds the entire virtual lab — config, memory, research graph, XP system, and connections to Obsidian/Zotero. Run once to get started; re-run to update settings.

## When to activate
- User says "set up my lab", "initialize LabOS", "lab init", "start my research lab"
- User wants to configure LabOS for the first time
- User wants to add a new project to their lab

## How to use this skill

Read and follow `script.md` in this directory for the full step-by-step execution flow.

## Files created by this skill
- `~/.openclaw/workspace/lab/LAB_CONFIG.json`
- `~/.openclaw/workspace/lab/LAB_MEMORY.md`
- `~/.openclaw/workspace/lab/research-graph.jsonl`
- `~/.openclaw/workspace/lab/xp.json`
- `~/.openclaw/workspace/lab/sessions/` (directory)

## Dependencies
- None required. Obsidian vault path, Zotero library ID, and API keys are optional at init time.
