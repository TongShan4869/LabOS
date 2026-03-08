# Literature Scout — Architecture & Search Strategy

> How `lab-lit-scout` finds, scores, and summarizes academic papers.

## Pipeline Overview

```
User Query ("neural coupling in speech processing")
    │
    ├─1─ Search 3 sources in parallel
    │    ├── PubMed (NCBI ESearch + EFetch XML)
    │    ├── OpenAlex (REST API, relevance-sorted)
    │    └── arXiv (Atom feed)
    │
    ├─2─ Deduplication (DOI + title similarity)
    │
    ├─3─ Semantic Scoring (LLM batch call)
    │    └── Single DeepSeek V3 call scores ALL papers 0-100
    │
    ├─4─ Sort & Limit (top N by relevance/citations/date)
    │
    ├─5─ Interactive Checkpoint
    │    └── User selects which papers to summarize
    │    └── Natural language → format translation via LLM
    │
    ├─6─ AI Summarization (per-paper LLM calls)
    │    └── Extracts: key claim, method, finding, limitation,
    │        relevance to query, hypothesis contradiction check
    │
    ├─7─ Rich Markdown Report
    │    └── Full title, all authors, institutions, journal,
    │        DOI link, TLDR, key findings
    │
    └─8─ Save & Export
         ├── Report saved to Filing Cabinet (project-scoped)
         ├── Obsidian vault (markdown note)
         └── BibTeX export (for Zotero)
```

## Data Sources

### PubMed (NCBI)
- **API:** EUtils (ESearch → EFetch)
- **Data:** Title, abstract, all authors + affiliations, journal, DOI, PMID
- **Strengths:** Gold standard for biomedical literature, MeSH indexing
- **Limitations:** No citation counts, biomedical focus only

### OpenAlex
- **API:** REST (`api.openalex.org/works`)
- **Data:** Title, abstract (inverted index → reconstructed), all authors + institution affiliations, journal, DOI, citation count, open access status
- **Strengths:** Broad coverage, citation data, institution metadata, free
- **Limitations:** Abstract reconstruction can be lossy

### arXiv
- **API:** Atom feed (`export.arxiv.org/api/query`)
- **Data:** Title, abstract, authors, categories
- **Strengths:** Preprints, CS/ML/physics coverage
- **Limitations:** No citation counts, no affiliations, preprints only

## Scoring Strategy

### Semantic Scoring (Primary — LLM-based)

A single LLM call (DeepSeek V3) receives all paper titles + abstract snippets (300 chars each) and the user's query, then returns a JSON array of relevance scores.

**Scoring criteria:**
| Score | Meaning |
|-------|---------|
| 80-100 | Directly addresses the query, high methodological relevance |
| 60-79 | Closely related, covers key aspects |
| 40-59 | Partially relevant, tangential concepts |
| 20-39 | Loosely related, different subfield |
| 0-19 | Not relevant |

**Why LLM scoring?**
- Understands synonyms and conceptual overlap (e.g., "speech perception" ≈ "auditory language processing")
- Weighs methodological relevance, not just keyword presence
- Considers the researcher's stated fields for contextual scoring
- One API call for all papers (efficient)

### Keyword Scoring (Fallback)

If the LLM call fails, falls back to a deterministic keyword scorer:

```
Score = title_hits (up to 35) + abstract_hits (up to 35) + field_hits (up to 15) + recency (up to 10) + citations (up to 5)
```

- **Title keyword hits:** 12 points per matching word (max 35)
- **Abstract keyword hits:** 3 points per matching word (max 35)
- **Field overlap:** 5 points per user-field word found in title/abstract (max 15)
- **Recency bonus:** 10 pts if ≥2022, 5 pts if ≥2019
- **Citation impact:** 1 pt per 20 citations (max 5)

## AI Summarization

After scoring & selection, each paper gets a per-paper LLM call that extracts structured metadata:

```json
{
  "key_claim": "one sentence main claim",
  "method": "study design, sample size, key technique",
  "key_finding": "1-2 sentence finding",
  "limitation": "one sentence main limitation",
  "relevance": "why this matters for the query",
  "contradicts_hypothesis": true/false,
  "contradiction_note": "which hypothesis and why"
}
```

Hypothesis contradiction checking uses the project's stored hypotheses from the Filing Cabinet memory system.

## Checkpoint Flow

When the skill finds papers, it pauses with an interactive checkpoint:

```
📋 Found 15 unique papers

### 1. [92%] Neural coupling during speech... (2024) 🔓
**Authors:** Smith, Jones, Lee...
**Journal:** Nature Neuroscience | **Citations:** 47
> TLDR: This study investigated...

Summarise all with AI, or select specific papers? [all/1,2,3.../done]
```

User replies in **natural language** (e.g., "summarize the first 5 relevant papers"), which gets translated by LLM to the expected format (`1,2,3,4,5`).

## Report Output

Reports are rendered in **Markdown** (via `marked.js`) in the LabOS UI report panel. Each paper includes:

- Full title + year + open access badge (🔓/🔒)
- Complete author list
- Corresponding author institutions (top 3)
- Journal name + citation count
- DOI as clickable link
- TLDR (abstract excerpt, 250-300 chars)
- AI-extracted: key claim, method, finding, limitation, relevance

## Storage

Reports are persisted in three locations:
1. **Filing Cabinet** — `/data/projects/{id}/reports/*.json` (project-scoped, viewable in UI)
2. **Obsidian** — `{vault}/Research/Literature/{date}-{query}.md` (if vault configured)
3. **BibTeX** — exportable for Zotero import

## Configuration

Via `.env`:
```
LLM_API_KEY=...          # API key for LLM calls (scoring + summarization)
LLM_API_BASE=...         # OpenAI-compatible base URL
LLM_MODEL=...            # Model for scoring/summarization
```

Via CLI flags:
```
--query/-q    Search terms (required)
--project/-p  Project name (scopes results)
--limit/-l    Max papers (1-20, default 10)
--since/-s    Date filter (YYYY-MM-DD)
--sort        relevance | citations | date
```
