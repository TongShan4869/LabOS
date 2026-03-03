# lab-field-trend

## Description
Weekly passive intelligence digest. Scans PubMed, OpenAlex, and arXiv for papers published in the last 7 days matching the user's research fields. Clusters results by theme, surfaces new findings, and delivers to Obsidian + Discord.

## When to activate
- Cron trigger: every Monday 8am (registered by lab-init)
- User says "run field trend", "what's new in my field", "weekly digest", "lab-field-trend"
- User wants an on-demand field update for a custom topic

## How to use

```bash
python3 skills/lab-field-trend/lab_field_trend.py              # run with config fields
python3 skills/lab-field-trend/lab_field_trend.py --query "auditory cortex EEG"  # custom query
python3 skills/lab-field-trend/lab_field_trend.py --days 14    # expand to 14-day window
python3 skills/lab-field-trend/lab_field_trend.py --dry-run    # preview without saving
python3 skills/lab-field-trend/lab_field_trend.py --no-notify  # save to Obsidian, skip Discord
```

## What it does
1. Reads user fields from `LAB_CONFIG.json`
2. Searches PubMed (via E-utilities), OpenAlex, and arXiv — no API keys needed
3. Deduplicates results across sources
4. Clusters papers by research theme (keyword matching against user fields)
5. Saves full digest to `Obsidian/Research/Weekly-Digests/YYYY-MM-DD.md`
6. Appends new papers to `research-graph.jsonl` as Paper nodes
7. Sends compact summary to Discord
8. Awards +25 XP

## Output
- Markdown digest in Obsidian
- Paper nodes in research-graph.jsonl
- Discord notification with top findings per theme

## Prerequisites
- `LAB_CONFIG.json` must exist (run `lab-init` first)
- No API keys needed (uses free public APIs)

## XP
+25 XP per digest run
