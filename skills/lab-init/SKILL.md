# lab-init

## Description
Onboard a new LabOS user. Scaffolds the entire virtual lab — config, memory, research graph, XP system, Obsidian vault folders, and weekly cron. Run once to get started; re-run to add projects or update settings.

## When to activate
- User says "set up my lab", "initialize LabOS", "lab init", "start my research lab"
- User wants to configure LabOS for the first time
- User wants to add a new project, update preferences, or check lab status

## How to use

### Interactive onboarding (first time)
```bash
python3 skills/lab-init/lab_init.py
```

### Common subcommands
```bash
python3 skills/lab-init/lab_init.py --status          # show current lab state + XP
python3 skills/lab-init/lab_init.py --add-project     # add a new research project
python3 skills/lab-init/lab_init.py --update-prefs    # change preferences
python3 skills/lab-init/lab_init.py --reset           # full reset (with confirmation)
```

## Files created / managed
| File | Purpose |
|------|---------|
| `LAB_CONFIG.json` | All user settings (fields, tools, preferences, notify channel) |
| `LAB_MEMORY.md` | Human-readable lab memory — updated by all skills |
| `research-graph.jsonl` | Structured graph of projects, papers, experiments |
| `xp.json` | Gamification: XP, level, badges, history |
| `sessions/` | Per-session logs |
| `obsidian-vault/Research/` | Folder scaffold (Projects, Literature, Methods, Digests) |

## What the script does
1. Checks if lab already exists (offers update/reset if so)
2. Collects identity, tools, preferences, notification settings interactively
3. Writes `LAB_CONFIG.json`, `LAB_MEMORY.md`, `research-graph.jsonl`, `xp.json`
4. Scaffolds Obsidian vault folder structure
5. Registers weekly `lab-trends` cron
6. Runs security baseline check
7. Awards 100 XP — Level 1 "Rookie" 🧪
8. Prints a clean summary with next steps

## Dependencies
- Python 3.8+
- No external packages required
- Obsidian vault, Notion DB, Zotero: all optional at init time

## XP awarded
| Event | XP |
|-------|----|
| Lab initialized | +100 |
| Project added | +50 |
