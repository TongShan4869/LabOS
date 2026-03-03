# lab-lit-scout

## Description
On-demand deep literature search. Given a query or hypothesis, searches PubMed, OpenAlex, and arXiv, scores relevance, summarizes top papers, saves to Zotero and Obsidian, and links results to the research graph. Flags any papers that contradict existing hypotheses.

## When to activate
- User says "search for papers on X", "lit scout", "find literature about X", "what papers exist on X"
- User wants to build the evidence base for a hypothesis
- User says "lab-lit-scout"

## Usage
```bash
openclaw lab-lit-scout --query "speech-music coupling in ASD" --project "neural-coupling"
openclaw lab-lit-scout --query "EEG preprocessing methods" --scope global
openclaw lab-lit-scout --query "infant hearing assessment" --limit 10
```

## Flags
- `--query` (required): search query or hypothesis text
- `--project` (optional): scope results to a project context; links papers to that project in graph
- `--scope global` (optional): explicitly cross-project search
- `--limit N` (optional): number of papers to return (default 5, max 20)
- `--since YYYY-MM-DD` (optional): filter by publication date

## Prerequisites
- `LAB_CONFIG.json` must exist

## Output
- Papers summarized in chat
- Saved to Obsidian at `/Research/Literature/{query-slug}.md`
- Saved to Zotero (if configured)
- Appended to research-graph.jsonl
- XP: +50
