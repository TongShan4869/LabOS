# lab-lit-scout — Execution Script

## Step 1: Parse inputs and load config

Load `LAB_CONFIG.json`. Extract: databases, obsidian_vault, zotero config.

If `--project` provided: load that project's node from research-graph.jsonl to get hypotheses + existing linked papers (for deduplication and contradiction checking).

---

## Step 2: Query APIs

Same API calls as `lab-field-trend` but without date filter (or use `--since` if provided).

Query all configured databases. Collect raw results, deduplicate by DOI.

---

## Step 3: Score relevance

Score each paper against the `--query` text:

| Signal | Weight |
|---|---|
| Title match | 35 |
| Abstract match | 35 |
| Method keyword match | 15 |
| Recency (last 2 years bonus) | 10 |
| Citation count | 5 |

Keep top `--limit` papers (default 5).

---

## Step 4: Summarize with LLM

For each paper, extract via LLM:

```
- **Key claim:** (1 sentence)
- **Method:** (study design, n, technique)
- **Key finding:** (1-2 sentences)
- **Limitation:** (1 sentence)
- **Relevance to query:** (1 sentence, why this matters for "{query}")
- **Contradicts hypothesis?** (yes/no — check against project hypotheses if --project provided)
```

---

## Step 5: Flag contradictions

If `--project` provided: for each paper marked "contradicts hypothesis", flag explicitly:

```
⚠️ CONTRADICTION: "{paper title}" challenges your hypothesis that "{hypothesis text}"
   Finding: {key finding}
   Suggest: Add to lit review and address directly.
```

Also surface cross-project: if a paper is highly relevant to another active project, note it.

---

## Step 6: Output to chat

```
🔍 **Lit Scout Results** — "{query}"
Found {n} papers | Showing top {limit}

**1. {Title}** ({year}, {journal})
Authors: {authors}
🔑 Claim: {key claim}
🧪 Method: {method}
📊 Finding: {finding}
⚠️ Limitation: {limitation}
🎯 Relevance: {relevance}
DOI: {doi}

---
[2. ...]

{contradiction warnings if any}

💾 Saved to Obsidian + Zotero | 🏆 +50 XP
```

---

## Step 7: Save to Obsidian

```markdown
# Lit Scout — {query}
*{date} | {n} papers found | Project: {project or "global"}*

## Papers

### 1. {Title}
...
```

Save to `{vault}/Research/Literature/{query-slug}-{date}.md`

---

## Step 8: Save to Zotero (if configured)

If `zotero_type: "web"` and `zotero_library_id` set:
```bash
# Use Zotero Web API to add items by DOI
curl -X POST "https://api.zotero.org/users/{id}/items" \
  -H "Zot-API-Key: {key}" \
  -d '[{"itemType":"journalArticle","DOI":"{doi}"}]'
```

If `zotero_type: "local"`:
- Output a `.bib` file the user can drag into Zotero
- Save to `~/.openclaw/workspace/lab/sessions/{date}-lit-scout.bib`

---

## Step 9: Append to research-graph.jsonl

For each new paper:
```jsonl
{"type":"Paper","id":"paper_{hash}","title":"...","doi":"...","authors":[...],"year":"...","journal":"...","abstract":"...","relevance_score":92,"query":"{query}","projects":["proj_X"],"contradicts_hypotheses":[],"added_by":"lab-lit-scout","added":"<ISO>"}
```

---

## Step 10: Award XP

+50 XP. Badge: "🔬 Literature Dive" (first time only).

---

## Step 11: Log session

Append to `~/.openclaw/workspace/lab/sessions/{date}-lab-lit-scout.md`:
- Query, parameters, papers found, papers saved, contradictions flagged
