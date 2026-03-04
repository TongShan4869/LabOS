# lab-lit-scout

## Description
On-demand deep literature search. Given a query or hypothesis, searches PubMed, OpenAlex, arXiv, and Semantic Scholar, scores relevance, generates summaries, saves to Obsidian, exports RIS for Zotero, links to the research graph, and flags papers that challenge your stored hypotheses.

## When to activate
- User says "search for papers on X", "find literature about X", "lit scout", "what papers exist on X"
- User wants to build the evidence base for a hypothesis
- User says "lab-lit-scout"

## How to use

```bash
# Basic search
python3 skills/lab-lit-scout/lab_lit_scout.py --query "speech-music neural coupling"

# Scoped to a project (links papers to project in research graph)
python3 skills/lab-lit-scout/lab_lit_scout.py \
  --query "EEG infant speech" \
  --project "infant-hearing-assessment"

# Filter by date, sort by citations
python3 skills/lab-lit-scout/lab_lit_scout.py \
  --query "auditory brainstem response ASD" \
  --since 2022-01-01 --sort citations --limit 15

# Preview without saving
python3 skills/lab-lit-scout/lab_lit_scout.py \
  --query "subcortical encoding music" --dry-run
```

## Flags
| Flag | Default | Description |
|------|---------|-------------|
| `--query` | required | Search query or hypothesis text |
| `--project` | None | Project slug to link results to |
| `--limit` | 10 | Max papers returned (1–20) |
| `--since` | None | Filter from date YYYY-MM-DD |
| `--sort` | relevance | Sort by: `relevance`, `citations`, `date` |
| `--dry-run` | False | Print without saving |

## What it does
1. Searches PubMed (E-utilities), OpenAlex, arXiv, Semantic Scholar — no API keys needed
2. Deduplicates across sources
3. Scores each paper by relevance to query + user fields + recency + open access
4. Prints ranked list with relevance bar + citation count + TL;DR (Semantic Scholar)
5. Flags papers that contradict stored project hypotheses
6. Saves full structured report to `Obsidian/Research/Literature/YYYY-MM-DD-{query}.md`
7. Exports `.ris` file for Zotero import (if Zotero configured)
8. Appends papers to `research-graph.jsonl` as Paper nodes
9. Creates PaperLink nodes linking papers to the specified project
10. Awards +50 XP

## Output
- Terminal: ranked paper list with relevance scores, TL;DRs, contradiction flags
- Obsidian: `Research/Literature/YYYY-MM-DD-{query-slug}.md`
- Zotero: `.ris` file in `sessions/` for manual import
- research-graph.jsonl: Paper + PaperLink nodes

## Prerequisites
- `LAB_CONFIG.json` must exist (run `lab-init` first)
- No API keys required

## XP
+50 XP per search run
