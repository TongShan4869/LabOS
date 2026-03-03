# lab-publishing-assistant — Execution Script

## Mode: `find-journal`

### Step 1: Load project context
From research-graph.jsonl: field, methods, key findings, novelty claims, hypothesis outcome.

### Step 2: Generate journal candidates via LLM
```
Given this paper:
- Field: {fields}
- Methods: {methods}
- Key finding: {main result}
- Novelty: {what's new}
- Open access preferred: {yes/no from config}

Suggest 5-8 appropriate journals ranked by fit. For each include:
- Journal name and publisher
- Scope fit (1-5)
- Typical impact factor range
- Open access options and APC cost
- Average time to first decision
- Acceptance rate (if known)
- Why it's a good fit
- One reason it might not be the right fit
```

### Step 3: Predatory journal check
Cross-check candidates against known predatory journal indicators:
- Not indexed in PubMed/Scopus/Web of Science
- Unusually fast peer review (<1 week)
- Requests payment before review
- Known predatory publisher names

Flag any matches clearly: ⚠️ POTENTIAL PREDATORY JOURNAL

### Step 4: Output ranked list
```
📚 Journal Recommendations — {project}

🥇 **Nature Neuroscience** (Nature Portfolio)
   Fit: 5/5 | IF: ~24 | OA: Yes (APC: $4,380) | Avg decision: 4-6 weeks
   ✅ Why: Strong fit for speech/neural coupling findings with clinical relevance
   ⚠️ Risk: Highly competitive, ~8% acceptance rate

🥈 **NeuroImage** (Elsevier)
   Fit: 4/5 | IF: ~7 | OA: Optional | Avg decision: 6-8 weeks
   ✅ Why: Strongest neuroimaging methods audience, good match for EEG work
   ⚠️ Risk: Elsevier subscription model limits readership

[...]

💾 Saved to: Research/Projects/{project}/journal-recommendations-{date}.md
```

---

## Mode: `reformat`

### Step 1: Fetch journal requirements
```bash
# Scrape or use known templates for major journals
# Known templates stored locally in skills/lab-publishing-assistant/journal-templates/
ls ~/.openclaw/workspace/skills/lab-publishing-assistant/journal-templates/{journal-slug}.json
```

If not in local templates: web_fetch the journal's "Instructions for Authors" page.

### Step 2: Diff manuscript vs requirements
Check:
- [ ] Word count (abstract, main text, total)
- [ ] Section order and required sections
- [ ] Heading format
- [ ] Abstract structure (structured vs unstructured)
- [ ] Figure count limits
- [ ] Supplemental material rules
- [ ] Required statements (ethics, data availability, conflict of interest, author contributions)

### Step 3: Reformat
- Restructure sections to match journal order
- Trim/flag sections exceeding word limits
- Add template text for missing required statements (user fills in details)
- Generate submission folder:
  ```
  submission-{journal}-{date}/
  ├── manuscript.md
  ├── figures/
  │   ├── figure-checklist.md
  │   └── (user places figure files here)
  ├── supplemental/
  ├── cover-letter.md
  └── submission-checklist.md
  ```

---

## Mode: `checklist`

Generate a ✅/❌/⚠️ checklist:

```
📋 Pre-Submission Checklist — {journal} — {date}

MANUSCRIPT
✅ Word count: 4,823 / 5,000 limit
✅ Abstract: 248 / 250 words — structured (Background/Methods/Results/Conclusions)
⚠️ Introduction: references 45 papers — journal recommends max 40 in intro

REQUIRED SECTIONS
✅ Methods
✅ Results
✅ Discussion
❌ Data Availability Statement — MISSING (required by {journal})
❌ Author Contributions (CRediT format) — MISSING
⚠️ Ethics Statement — present but IRB number not included

FIGURES
✅ 5 figures (limit: 8)
⚠️ Figure 3: likely < 300 DPI — check before upload
❌ Figure legends: missing for Figure 4

REFERENCES
✅ Format matches {citation style}
⚠️ 3 references are preprints — {journal} may require published versions

ACTION ITEMS (fix before submitting):
1. Add Data Availability Statement
2. Add CRediT Author Contributions
3. Add IRB number to Ethics Statement
4. Check Figure 3 resolution
5. Add Figure 4 legend
```

---

## Mode: `references`

Fetch Zotero library for cited keys. Reformat to target journal style via CSL (Citation Style Language):

```bash
# Use pandoc + CSL for reformatting
pandoc --citeproc --bibliography={zotero.bib} --csl={journal-style.csl} {draft.md} -o {output.md}
```

If pandoc not available: LLM-reformat the reference list.

---

## Mode: `figure-spec`

Output figure requirements for target journal:
```
🖼️ Figure Requirements — {journal}

Format: TIFF or EPS (no JPEG for line art)
Resolution: 300 DPI minimum (600 DPI for line art)
Color mode: RGB (CMYK if print)
Max file size: 10MB per figure
Dimensions: max 89mm (1 column) or 183mm (2 column) wide
Font: min 6pt in figure, Arial or Helvetica preferred
Figure legends: separate from figure file, in manuscript

Check your figures:
```bash
file figure*.tiff | grep -v "300 dpi"   # flag low-res files
identify -format "%f: %wx%h, %x DPI\n" figure*.tiff
```
```

---

## Mode: `cover-letter`

```
Draft a cover letter for submitting to {journal}.

Paper: {title}
Key finding: {main result in 1 sentence}
Novelty: {what's new}
Significance: {why it matters for the field}
Journal fit: {why this journal specifically}

Format:
- Addressed to Editor-in-Chief
- Para 1: What we're submitting and the key finding
- Para 2: Why it's significant and novel
- Para 3: Why {journal} specifically
- Para 4: Confirmations (no prior submission, all authors approved, data availability)
- Sign-off

Tone: Professional, confident, not sycophantic. Do not start with "We are pleased to submit..."
```

---

## XP and logging

Award +300 XP on first complete submission prep (reformat or checklist mode).
Badge: 🚀 Launcher

Save all outputs to Obsidian and log session.
