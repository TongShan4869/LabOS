# lab-peer-reviewer — Execution Script

## Step 1: Load inputs

- Read `--draft` file or fetch paper via Zotero key/DOI
- Read `LAB_CONFIG.json` → fields, citation_format
- If `--project`: load project hypotheses + results from research-graph.jsonl for grounding
- If `--journal`: load journal's known standards (scope, acceptance criteria, formatting expectations)

---

## Step 2: Security pre-flight

If draft contains project marked `sensitive` or `confidential`:
> "⚠️ This draft contains content from a {level} project. Confirm sending to LLM API? (yes/no)"

---

## Step 3: LLM review prompt by mode

### `peer-review` (default)

```
You are a senior academic reviewer in {fields}. Review this manuscript rigorously.

Structure your review as follows:

**SUMMARY** (3-4 sentences): What is this paper about? What is the main claim?

**MAJOR CONCERNS** (must be addressed before acceptance):
- List each as a numbered point. Be specific. Reference line numbers or sections where possible.
- Focus on: logical gaps, unsupported claims, methodological flaws, overstated conclusions, missing controls, statistics issues.

**MINOR CONCERNS** (should be addressed):
- Clarity issues, missing citations, presentation problems, minor logical gaps.

**STRENGTHS** (don't skip this):
- What's genuinely good about this paper? Be specific.

**LINE-LEVEL COMMENTS**:
- Flag specific passages that are unclear, overclaiming, or poorly written.
- Format: [Section, ~paragraph N]: "quoted text" → problem/suggestion

**RECOMMENDATION**: Accept / Minor revision / Major revision / Reject
Brief justification (2-3 sentences).

Be rigorous. Do not be kind for kindness's sake. A weak review helps no one.

Manuscript:
{draft content}
```

### `methods-critique`

```
You are a methodologist and statistician reviewing this paper's methods section.

Evaluate:
1. **Study design validity** — is the design appropriate for the research question?
2. **Sample** — adequate N? Power analysis? Inclusion/exclusion criteria justified?
3. **Controls** — appropriate controls? Confounds addressed?
4. **Measures** — valid and reliable instruments? Operational definitions clear?
5. **Statistical analysis** — correct tests? Assumptions checked? Multiple comparisons corrected?
6. **Replicability** — could another lab replicate this from the methods description?
7. **Causal claims** — does the design support causal language used in the paper?

Flag each issue as: CRITICAL / MODERATE / MINOR

Manuscript:
{draft content}
```

### `pre-submission`

```
Review this manuscript for submission to {journal}.

Check against these requirements:
- Word count: {journal limit}
- Abstract format: {journal format}
- Section structure: {journal requirements}
- Figure requirements: {journal specs}
- Reference format: {citation style}
- Required sections: {ethics statement, data availability, conflict of interest, etc.}

Generate a checklist:
✅ PASS / ❌ FAIL / ⚠️ NEEDS ATTENTION

For each FAIL or WARNING: explain what needs to change.

Manuscript:
{draft content}
```

### `devil's-advocate`

```
Your job is to argue AGAINST this paper as strongly as possible.

1. **Steelman the null hypothesis** — make the best case that the effect doesn't exist.
2. **Attack the weakest claim** — find the most overclaimed statement and dismantle it.
3. **Alternative explanations** — offer 3 alternative interpretations of the main finding.
4. **Replication concern** — identify the single most likely reason this wouldn't replicate.
5. **So what?** — challenge the significance. Why does this finding matter?

Be adversarial. This is meant to prepare the authors for the hardest possible reviewer.

Manuscript:
{draft content}
```

---

## Step 4: Format and output review

Print review to chat. Then:

```
📋 **Peer Review Report**
Mode: {mode} | Date: {date}
{journal if pre-submission}

{full review content}

---
Review saved to: Research/Projects/{project}/reviews/{date}-{mode}.md
🏆 +100 XP | Badge: 🤺 Devil's Advocate
```

---

## Step 5: Save to Obsidian

Save full review to `{vault}/Research/Projects/{project}/reviews/{date}-{mode}.md`

---

## Step 6: Update research graph

Link review to draft node:
```jsonl
{"type":"Review","id":"review_{hash}","project":"proj_X","draft_id":"draft_{hash}","mode":"{mode}","recommendation":"{accept/revise/reject}","major_concerns":3,"minor_concerns":5,"date":"<ISO>","path":"{obsidian path}"}
```

---

## Step 7: Award XP + log

+100 XP. Badge: "🤺 Devil's Advocate" (first time). Log session.
