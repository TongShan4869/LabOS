# lab-field-trend

## Description
Weekly passive intelligence digest. Scans PubMed, OpenAlex, and arXiv for papers published in the last 7 days matching the user's research fields. Clusters by theme, surfaces breakthroughs, flags papers that challenge existing hypotheses, and identifies underexplored gaps. Delivers to Obsidian + Discord/Slack.

## When to activate
- Cron trigger: every Monday 8am (registered by lab-init)
- User says "run field trend", "what's new in my field", "weekly digest", "lab-field-trend"
- User wants an on-demand field update

## How to use this skill

Read and follow `script.md` in this directory.

## Prerequisites
- `~/.openclaw/workspace/lab/LAB_CONFIG.json` must exist (run lab-init first)
- `~/.openclaw/workspace/lab/research-graph.jsonl` must exist

## Output
- Weekly briefing saved to Obsidian at `/Research/Weekly-Digests/YYYY-MM-DD.md`
- Notification sent to configured channel
- New papers appended to research-graph.jsonl as Paper nodes (tagged to relevant projects)
- XP awarded: +25
