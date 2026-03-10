# LabOS — Product Requirements Document

> **Version:** 2.0
> **Created:** 2026-03-03
> **Updated:** 2026-03-10 (v2 — Lab Manager architecture)
> **Author:** Cu + 醋の虾
> **Status:** Active development — Lab Manager v2 shipped

---

## 0. What Changed in v2 (2026-03-10)

### Lab Manager Architecture
- **Single entry point**: User talks to one Lab Manager agent. It delegates to specialists automatically.
- **No manual agent selection**: Regex-based intent detection routes tasks to Scout, Stat, Quill, etc.
- **Quest Board**: Every delegated task becomes a tracked quest with XP rewards.
- **Agent Lifecycle**: Ephemeral → Persistent (3+ runs) → Scheduled (cron) → Archived (7d idle).
- **Multi-agent Pipelines**: "Comprehensive lit review" triggers Scout → Critic → Quill chain.
- **Audit Log**: Immutable append-only log of all agent actions.
- **Night Shift**: Scheduled cron tasks for agents (e.g., weekly paper monitoring).

### LifeOS Vision
- LabOS is **Floor 1** of a pixel art building where each floor runs a part of your life.
- Users can build their own floors with custom skills and share them.
- See `docs/vision.md` for the full concept.

### Architecture Changes
- `lab_manager.py`: New orchestration engine with delegation, quest board, audit, scheduling.
- `app.py`: Lab Manager as default system prompt for main agent, pipeline detection.
- Frontend: Quest Board UI (📋), Team Roster, Night Shift tab, Coins counter.
- APIs: `/api/quests`, `/api/agents/roster`, `/api/lab/stats`, `/api/schedules`.

---

## 1. Vision

**LabOS** is an OpenClaw skill suite that gives any researcher a virtual AI-powered lab. The user is the PI. The AI agents are the lab team.

The core experience: a PhD student (or any researcher) can manage multiple research projects — literature, hypotheses, data analysis, writing, field trends — without doing everything manually. They delegate to agents the way a real PI delegates to lab members.

It is **not** end-to-end automation. The researcher stays in control and makes the key decisions. Agents handle execution, surfacing, and Socratic challenge.

---

## 2. Target Users

- **Primary:** PhD students (any field, any stage)
- **Secondary:** Postdocs, junior faculty, independent researchers
- **Not scoped (yet):** Research teams, labs with multiple human members

### User pain points addressed
- Drowning in papers — can't keep up with the field
- Managing multiple projects with no system
- No mentor feedback between advisor meetings
- Research milestones feel invisible — no positive reinforcement
- Context-switching overhead between tools (Zotero, Notion, Slack, PubMed)

---

## 3. Design Principles

1. **CLI-first.** All skills are shell/CLI-first, consistent with existing OpenClaw skill patterns.
2. **Modular, not end-to-end.** User can invoke any skill at any research stage independently.
3. **Field-agnostic.** Works for neuroscience, climate science, ML, economics — any academic field. Field is a config parameter.
4. **Memory compounds.** Agents get smarter the more you use them via a dedicated lab memory layer.
5. **Obsidian/Notion as primary knowledge store.** Obsidian preferred (CLI-friendly, offline, plain markdown). Notion supported as optional mirror.
6. **Subagent pattern.** Each skill spawns a focused subagent, does its job, writes results to the shared research graph, and exits.
7. **Research graph as connective tissue.** All skills read from and write to a shared `research-graph.jsonl`. No manual copy-pasting between tools.

---

## 4. Architecture

### Directory structure

```
~/.openclaw/workspace/lab/
├── PRD.md                        # this document
├── LAB_CONFIG.json               # static user preferences
├── LAB_MEMORY.md                 # evolving user profile (read at every session start)
├── research-graph.jsonl          # ontology: projects, hypotheses, papers, experiments
├── xp.json                       # gamification: XP, level, badges
└── sessions/
    └── YYYY-MM-DD-{skill}.md     # per-session raw logs

~/.openclaw/workspace/skills/
├── lab-init/                     # onboarding — scaffolds the entire lab setup
├── lab-field-trend/              # weekly field digest
├── lab-lit-scout/                # on-demand literature search + summarize
├── lab-research-advisor/         # Socratic mentor agent
├── lab-data-analyst/             # (future) stats + figures
├── lab-writing-assistant/        # (future) draft sections, abstracts
└── lab-project-standup/          # (future) daily cross-project status
```

### Shared state flow

```
User invokes skill
    → Read LAB_CONFIG.json + LAB_MEMORY.md
    → Read relevant nodes from research-graph.jsonl
    → Execute task (search APIs / analyze / advise / write)
    → Write results to research-graph.jsonl
    → Append raw log to sessions/YYYY-MM-DD-{skill}.md
    → Update LAB_MEMORY.md if new preferences learned
    → Award XP if milestone hit
    → Push state to Star Office UI (if running)
```

---

## 5. Knowledge Architecture — Two-Layer Model

### Layer 1: Shared Knowledge (global, cross-project)
The researcher's accumulated knowledge base — everything learned across all projects.

- **`research-graph.jsonl`** — shared nodes: Papers, Methods, Concepts, Authors, Datasets
- **Obsidian vault** — all notes, summaries, literature reviews
- **Zotero library** — all saved papers and citations

A paper found during Project A is immediately available to Project B. A method used in one project surfaces as a suggestion in another. Agents can reason across the full knowledge base at any time.

### Layer 2: Project Context (scoped, per-project)
What's specific to each research project — goals, hypotheses, experiments, drafts, status.

- **Project nodes** in research graph: hypotheses, experiments, drafts, milestones, status
- **Project folders** in Obsidian: `/Research/Projects/{project-name}/`

### Graph node design
Shared nodes link to multiple projects. Project nodes are scoped containers.

```jsonl
{"type": "Paper", "id": "paper_abc", "title": "...", "projects": ["proj_A", "proj_B"]}
{"type": "Method", "id": "meth_eeg", "name": "EEG", "projects": ["proj_A", "proj_C"]}
{"type": "Concept", "id": "conc_coupling", "name": "neural coupling", "projects": ["proj_A"]}
{"type": "Project", "id": "proj_A", "name": "neural coupling ASD", "hypotheses": [...]}
```

### Skill invocation scope
All skills accept an optional `--project` flag:

```bash
# Scoped to one project (reads shared knowledge, writes to project context):
openclaw lab-lit-scout --project "neural-coupling" --query "speech ASD"

# Global view — sees all projects, finds cross-project connections:
openclaw lab-research-advisor

# Explicitly cross-project search:
openclaw lab-lit-scout --query "EEG methods" --scope global
```

No `--project` = global view. With `--project` = scoped context, but shared knowledge layer always readable.

### Cross-project intelligence (agent capabilities this enables)
- `lab-research-advisor`: *"You solved a similar problem in Project A with method X — worth trying here?"*
- `lab-peer-reviewer`: *"You made a contradictory claim in Project A's draft"*
- `lab-field-trend`: tag a new paper to multiple relevant projects simultaneously
- Cross-project gap detection: *"Both your projects assume X but nobody in your field has tested it — potential third paper?"*
- `lab-lit-scout`: a paper found for Project B auto-surfaces in Project A if relevant

---

## 6. Memory Layer

### `LAB_CONFIG.json` — static preferences
Set during `lab-init`, rarely changed manually.

```json
{
  "user": "",
  "fields": [],
  "disciplines": [],
  "knowledge_store": "obsidian",
  "obsidian_vault": "",
  "notion_db_id": "",
  "zotero_library_id": "",
  "databases": ["pubmed", "openalex", "arxiv"],
  "writing_style": "",
  "citation_format": "APA",
  "weekly_trend_day": "Monday",
  "weekly_trend_time": "08:00",
  "notify_channel": "discord"
}
```

### `LAB_MEMORY.md` — evolving user profile
Read by every agent at session start. Updated after sessions when new preferences or patterns are observed. Curated (not raw logs).

Sections:
- Research Identity (fields, methods, comfort zones, weak spots)
- Preferences Learned (summary style, paper batch size, writing voice)
- Active Projects (brief status of each)
- Interaction Patterns (working hours, feedback style, common blind spots)
- Last Updated (by which skill, when)

### `sessions/YYYY-MM-DD-{skill}.md` — raw session logs
Never read by agents directly. Used for debugging and manual review. Periodically summarized into `LAB_MEMORY.md`.

---

## 7. Skill Specs (MVP)

### 7.1 `lab-init`
**Purpose:** Onboard a new user. Scaffold the entire lab setup.

**Flow:**
1. Interactive CLI questionnaire (field, disciplines, tools, preferences)
2. Generate `LAB_CONFIG.json` and starter `LAB_MEMORY.md`
3. Create `research-graph.jsonl` with empty schema
4. Create `xp.json` with Level 1 / 0 XP
5. Scaffold first project if user provides one
6. Optionally connect Obsidian vault, Notion, Zotero
7. Register `lab-field-trend` cron job

---

### 7.2 `lab-field-trend`
**Purpose:** Weekly passive digest of new developments in the user's field.

**Trigger:** Cron, every Monday 8am (configurable). Also callable on demand.

**Flow:**
1. Read field keywords from `LAB_CONFIG.json`
2. Query PubMed + OpenAlex + arXiv: papers from past 7 days
3. Score papers by citation velocity, novelty signals, method keywords
4. LLM cluster into themes
5. Generate "Weekly Lab Briefing":
   - 🔥 Top 3 breakthroughs
   - 📈 Emerging methods
   - ⚠️ Papers that challenge current hypotheses (cross-ref research graph)
   - 💡 Gap spotted: underexplored angles
6. Save to Obsidian/Notion + notify via Discord/Slack
7. Push state to Star Office UI: `researching "Weekly briefing ready"`
8. Award XP: +25, badge: "Stayed Current"

---

### 7.3 `lab-lit-scout`
**Purpose:** On-demand deep literature search for a specific question or hypothesis.

**Invocation:**
```bash
openclaw lab-lit-scout --query "speech-music coupling in ASD" --project "neural-coupling"
```

**Flow:**
1. Search PubMed + OpenAlex + arXiv
2. Score relevance to query
3. Summarize top N papers (configurable, default 5)
4. Extract: methods, key findings, limitations, gaps
5. Save papers to Zotero + Obsidian
6. Link papers to project + hypothesis nodes in research graph
7. Flag any paper that contradicts existing hypotheses
8. Award XP: +50, badge: "Literature Dive"

---

### 7.4 `lab-research-advisor`
**Purpose:** Socratic mentor agent. Pushes the researcher to think like a PI. Not a yes-machine.

**Invocation:**
```bash
openclaw lab-research-advisor --project "neural-coupling"
# or open-ended:
openclaw lab-research-advisor
```

**Flow:**
1. Pull project context from research graph (hypotheses, papers, experiments, last session)
2. Read `LAB_MEMORY.md` for interaction preferences
3. Ask hard questions:
   - "What would falsify your H1?"
   - "You haven't logged a null hypothesis. What's your H0?"
   - "It's been 3 weeks since lit-scout on this project. Want me to check what's new?"
   - "You've cited [paper X] three times but never engaged with [paper Y] that contradicts it."
4. Surface gaps, stale nodes, missing links in research graph
5. Log conversation to session file
6. Update `LAB_MEMORY.md` if new patterns observed
7. Award XP for engaging: +30

**Design note:** This agent should be configurable in intensity. Default: push back hard. Option: supportive mode for low-confidence moments.

---

### 7.5 `lab-writing-assistant`
**Purpose:** Draft paper sections, abstracts, grant language, and structured notes from research graph context and user's writing preferences.

**Invocation:**
```bash
openclaw lab-writing-assistant --project "neural-coupling" --section "introduction"
openclaw lab-writing-assistant --type "abstract" --project "neural-coupling"
openclaw lab-writing-assistant --type "grant-aim" --project "neural-coupling"
```

**Flow:**
1. Read project context from research graph (hypotheses, key papers, experiment results)
2. Read user writing preferences from `LAB_MEMORY.md` (style, voice, citation format)
3. Draft requested section with inline citation placeholders linked to Zotero keys
4. Save draft to Obsidian/Notion under project folder
5. Log to session file
6. Award XP: +200, badge: ✍️ Author (on first draft per paper)

**Design note:** Does not polish or finalize — produces a working draft the researcher edits. Agent writes in the user's voice, not generic academic prose.

---

### 7.6 `lab-peer-reviewer`
**Purpose:** Critical review agent. Reviews your own drafts or any paper with structured, rigorous feedback — like a tough peer reviewer or thesis committee member.

**Invocation:**
```bash
# Review your own draft:
openclaw lab-peer-reviewer --draft "path/to/draft.md" --mode "peer-review"
# Review an external paper:
openclaw lab-peer-reviewer --paper "zotero:key123" --mode "methods-critique"
# Pre-submission check:
openclaw lab-peer-reviewer --draft "path/to/draft.md" --mode "pre-submission"
```

**Modes:**
- `peer-review` — simulates anonymous peer reviewer: logic, evidence gaps, clarity, novelty
- `methods-critique` — deep dive on statistical/experimental design validity
- `pre-submission` — checklist: structure, abstract, figures, references, journal fit
- `devil's-advocate` — steelmans the opposing view, finds weakest claims

**Flow:**
1. Read draft or paper content
2. Pull project context from research graph for grounding
3. Generate structured review:
   - **Major concerns** (would block acceptance)
   - **Minor concerns** (would require revision)
   - **Strengths** (what's working — don't skip this)
   - **Specific line-level comments** (flagged passages)
4. Save review to Obsidian/Notion alongside draft
5. Link review to draft node in research graph
6. Award XP: +100, badge: 🤺 Devil's Advocate

**Design note:** Deliberately critical. Catching your own weak points before submission is the whole value. Should feel like a hard but fair committee member, not a cheerleader.

---

### 7.7 `lab-security`
**Purpose:** Protect research IP, credentials, and sensitive data. A quiet warden — runs automatically before risky operations, auditable on demand.

**What it guards:**
- Research IP — unpublished hypotheses, experimental results, grant ideas
- Personal/participant data — HIPAA territory for clinical/human subjects research
- API credentials — keys in `LAB_CONFIG.json` and environment
- Knowledge store integrity — Obsidian vault, research graph
- LLM data leakage — what gets sent to external APIs

**Sensitivity classification system:**

| Level | Meaning | Example |
|---|---|---|
| `public` | Safe to share anywhere | published papers, public methods |
| `internal` | Lab-only | working notes, in-progress analysis |
| `sensitive` | Pre-publication IP | unpublished hypotheses, novel results |
| `confidential` | Human subjects / grant-restricted | participant data, NIH-restricted data |

**Core capabilities:**
- **Credential audit** — scan for exposed keys, flag plaintext secrets in config/env
- **Data classification** — tag research graph nodes and Obsidian files with sensitivity level
- **LLM leakage pre-flight** — before any agent sends content to external API, check for `confidential` or `sensitive` content → block or warn
- **Access log** — log which skill accessed what data and when
- **Vault integrity check** — detect unexpected changes to Obsidian vault or research graph
- **HIPAA mode** — if project involves human subjects, auto-elevate sensitivity and enforce pre-flight on all external calls

**Invocation:**
```bash
# Full audit:
openclaw lab-security --audit

# Check a draft before sharing externally:
openclaw lab-security --check "path/to/draft.md"

# Classify a project:
openclaw lab-security --classify --project "infant-hearing" --level confidential
```

**Runs automatically:**
- On `lab-init` — baseline credential + vault scan
- Weekly alongside `lab-field-trend` cron — integrity check
- Pre-flight before any skill sends data to external LLM/API — silent check, warns on risk

---

### 7.8 `lab-publishing-assistant`
**Purpose:** Help researchers choose the right journal/conference and reformat the entire manuscript — text, figures, supplementals, references — to match submission requirements.

**Invocation:**
```bash
# Get journal recommendations:
openclaw lab-publishing-assistant --mode "find-journal" --project "neural-coupling" --type "journal"

# Reformat manuscript for a specific journal:
openclaw lab-publishing-assistant --mode "reformat" --draft "path/to/manuscript.md" --target "Nature Neuroscience"

# Pre-submission checklist:
openclaw lab-publishing-assistant --mode "checklist" --draft "path/to/manuscript.md" --target "Journal of Neuroscience"

# Format references:
openclaw lab-publishing-assistant --mode "references" --draft "path/to/manuscript.md" --target "PLOS ONE"
```

**Modes:**

| Mode | What it does |
|---|---|
| `find-journal` | Recommends journals/conferences by fit, impact factor, open access, turnaround time |
| `reformat` | Restructures manuscript sections, word limits, abstract format to journal spec |
| `checklist` | Pre-submission checklist: figures, file formats, cover letter, author list, ethics statement |
| `references` | Reformats Zotero citations to journal's required style |
| `figure-spec` | Checks figure resolution, format (TIFF/EPS/PDF), sizing against journal requirements |
| `cover-letter` | Drafts a cover letter tailored to the target journal's scope and editor focus |

**Flow (find-journal mode):**
1. Read project context — field, methods, key findings, novelty claims
2. Query journal databases (Scimago, PubMed journal list, DOAJ for OA)
3. Score journals by: field fit, impact factor range, open access option, avg review time, acceptance rate
4. Present ranked shortlist with trade-offs explained
5. Flag predatory journals (cross-check against Beall's list)
6. Save recommendation to project folder in Obsidian

**Flow (reformat mode):**
1. Fetch target journal's author guidelines (web scrape or known template)
2. Diff manuscript against requirements: word count, section order, abstract structure, heading style
3. Reformat draft to comply — restructure sections, trim/expand where needed
4. Flag items that need manual attention (ethics statement, data availability, conflict of interest)
5. Generate figure checklist: required format, max file size, caption style
6. Output submission-ready folder: `manuscript.md`, `figures/`, `supplemental/`, `cover-letter.md`

**Design note:** Knows the difference between journal families — Nature vs PLOS vs Elsevier vs conference proceedings each have very different formatting cultures. Should also know open access implications and cost.

Award XP: +300, badge: 🚀 Launcher (on first submission prep completed)

---

### 7.9 `lab-biostat`
**Purpose:** A biostatistician-in-residence. Advises on study design, runs statistical analysis, interprets results, flags methodological issues — like having a stats collaborator on call.

**Invocation:**
```bash
# Get stats advice before collecting data:
openclaw lab-biostat --mode "design" --project "infant-hearing"

# Run analysis on a dataset:
openclaw lab-biostat --mode "analyze" --data "path/to/data.csv" --question "Is there a significant difference between groups?"

# Interpret existing results:
openclaw lab-biostat --mode "interpret" --results "path/to/results.md" --project "neural-coupling"

# Power analysis:
openclaw lab-biostat --mode "power" --effect-size 0.5 --alpha 0.05 --power 0.8

# Flag issues in a methods section:
openclaw lab-biostat --mode "review-methods" --draft "path/to/methods.md"
```

**Modes:**

| Mode | What it does |
|---|---|
| `design` | Advises on study design — sample size, controls, confounds, blinding |
| `analyze` | Runs stats via Python (scipy, statsmodels, pingouin) or R — outputs results + figures |
| `interpret` | Reads results, explains what they mean, flags over-interpretation |
| `power` | Power analysis — tells you if your N is enough |
| `review-methods` | Audits a methods section for statistical validity issues |
| `assumption-check` | Checks normality, homoscedasticity, independence before you run parametric tests |

**Flow (analyze mode):**
1. Read data file + research question
2. Suggest appropriate statistical test and justify why
3. Check assumptions first — warn if violated, suggest non-parametric alternatives
4. Execute analysis (Python/R via exec)
5. Generate figures (matplotlib / ggplot)
6. Write plain-English interpretation of results
7. Flag common mistakes: p-hacking, multiple comparisons, underpowered design
8. Save results + figures + interpretation to Obsidian project folder
9. Link results to hypothesis node in research graph — mark hypothesis as supported / not supported / inconclusive
10. Award XP: +150, badge: 📊 Experimenter

**Design note:** Always shows its work — which test, why, what assumptions were checked. A black-box stats tool is dangerous. This agent teaches as it does.

---

### 7.9 `lab-data-analyst` *(future)*
**Purpose:** Broader data exploration, visualization, and pipeline work beyond statistical testing.

---

### 7.10 `lab-project-standup` *(future)*
**Purpose:** Daily cross-project status — what's pending, stale, needs attention.

---

## 8. Gamification System

### XP Events

| Milestone | XP | Badge |
|---|---|---|
| Lab initialized | +100 | 🧪 Lab Open |
| First paper saved to Zotero | +50 | 📚 Collector |
| Hypothesis logged + linked to 3 papers | +100 | 💡 Theorist |
| Weekly trend digest read | +25 | 📰 Stayed Current |
| Literature dive completed | +50 | 🔬 Literature Dive |
| Data analysis run + result saved | +150 | 📊 Experimenter |
| Draft section written | +200 | ✍️ Author |
| Manuscript submitted | +500 | 🚀 Launcher |
| Paper accepted | +1000 | 🏅 Published |
| Grant proposal submitted | +300 | 💰 Fundraiser |
| Null hypothesis logged | +30 | ⚖️ Rigorous |
| Advisor session completed | +30 | 🎓 Mentored |
| Contradicting paper engaged | +75 | 🤺 Devil's Advocate |

### Levels

| Level | Title | XP Required |
|---|---|---|
| 1 | Confused First-Year | 0 |
| 2 | Lab Gremlin | 300 |
| 3 | Professional Coffee Drinker | 800 |
| 4 | PhD Candidate *(ABD, technically)* | 2,000 |
| 5 | Doctor of Suffering | 4,000 |
| 6 | Postdoc (Indentured Servant Edition) | 7,500 |
| 7 | Assistant Professor (Broke but Hopeful) | 12,000 |
| 8 | Associate Professor (Tenure Track Anxiety) | 20,000 |
| 9 | Tenured Professor (Finally Relaxed) | 30,000 |
| 10 | Distinguished Chair of Something Important | 45,000 |
| 11 | PI with a Waiting List | 65,000 |
| 12 | Nature/Science Regular | 90,000 |
| 13 | Nobel Shortlist Gossip | 120,000 |
| 14 | Nobel Laureate | 160,000 |
| 15 | Cited More Than Darwin | 210,000 |
| 16 | Textbook Namesake | 270,000 |
| 17 | The Field IS You | 340,000 |
| 18 | Retired Legend Still Getting Awards | 420,000 |
| 19 | Transcended Peer Review | 510,000 |
| 20 | The Omniscient and Omnipotent Being of the Universe | ∞ |

*Level 20 unlocks badge 🌌 Beyond Peer Review. All agents address you as "Your Omniscience."*

### Visual progression
As XP increases, the Star Office UI lab space upgrades — more equipment, more agent slots unlocked, new pixel art zones appear.

---

## 9. Visual Interface — Star Office UI Integration

Built on [Star Office UI](https://github.com/ringhyacinth/Star-Office-UI) — pixel office dashboard for multi-agent state visualization.

### Lab skin concept
- 🔬 **Bench zone** → data-analyst agent working
- 📚 **Bookshelf zone** → lit-scout / field-trend researching
- 🖊️ **Desk zone** → writing-assistant drafting
- 🎓 **Advisor chair** → research-advisor in session
- ☕ **Lounge** → all agents idle

### Agent states pushed to UI
Each skill calls `set_state.py` at key moments:
- `researching "Scanning PubMed for neural coupling papers"`
- `executing "Running weekly trend analysis"`
- `writing "Drafting lit review summary"`
- `idle "Waiting for next task"`
- `syncing "Saving to Obsidian"`
- `error "PubMed API timeout — retrying"`

### XP/Level display
User's current level and XP shown in the office UI header. Level-up triggers a visual celebration in the pixel space.

---

## 10. External Integrations

| Service | Purpose | Priority |
|---|---|---|
| PubMed API | Literature search | MVP |
| OpenAlex API | Literature search + citation data | MVP |
| arXiv API | Preprints, CS/physics heavy | MVP |
| Obsidian (local) | Primary knowledge store | MVP |
| Zotero (local/API) | Citation management | MVP |
| Discord | Notifications, digest delivery | MVP |
| Notion API | Optional mirror/dashboard | V2 |
| Slack | Lab Slack monitoring | V2 |
| Semantic Scholar | Citation velocity scoring | V2 |

---

## 11. MVP Scope

**Goal:** Something working and genuinely useful within a few weeks.

### MVP includes:
- `lab-init` — full onboarding
- `lab-field-trend` — weekly cron digest
- `lab-lit-scout` — on-demand search
- `lab-research-advisor` — Socratic mentor
- `lab-writing-assistant` — draft sections, abstracts, grant language
- `lab-peer-reviewer` — critical peer review of drafts and papers
- `lab-security` — credential audit, data classification, LLM leakage pre-flight
- `lab-publishing-assistant` — journal selection, manuscript reformat, submission checklist
- `lab-biostat` — statistical analysis, study design, power analysis, results interpretation
- Memory layer (`LAB_CONFIG.json` + `LAB_MEMORY.md` + sessions)
- Research graph (`research-graph.jsonl`)
- XP system (`xp.json`)
- Star Office UI base integration

### MVP excludes (post-MVP):
- `lab-data-analyst`
- `lab-project-standup`
- Notion sync
- Slack monitor
- Multi-user support

---

## 12. Open Questions

- [ ] Name: `LabOS` vs `lab-agent` vs something else?
- [ ] Zotero integration: local Better BibTeX plugin vs Zotero Web API?
- [ ] Star Office UI: fork and skin as lab, or contribute lab theme upstream?
- [ ] `research-advisor` intensity: always hard mode or user-configurable?
- [ ] Should `lab-field-trend` support multiple fields separately or merged digest?
- [ ] Multi-project XP: per-project levels or global researcher level?
- [ ] Publishing path: personal OpenClaw skill → ClawHub release someday?

---

## 13. Change Log

| Date | Version | Notes |
|---|---|---|
| 2026-03-03 | 0.1 | Initial brainstorm draft |
| 2026-03-03 | 0.2 | Added `lab-writing-assistant` and `lab-peer-reviewer` to MVP scope |
| 2026-03-03 | 0.3 | Added two-layer knowledge architecture — shared knowledge vs project context |
| 2026-03-03 | 0.4 | Added `lab-security` to MVP — credential audit, data classification, LLM leakage pre-flight |
| 2026-03-03 | 0.5 | Added `lab-biostat` to MVP — full biostatistician agent with 6 modes |
| 2026-03-03 | 0.6 | Renamed `lab-reviewer` → `lab-peer-reviewer`; added `lab-publishing-assistant` to MVP |
| 2026-03-03 | 0.7 | Redesigned level system — 20 levels from Confused First-Year to The Omniscient and Omnipotent Being of the Universe |

---

*Next step: draft `lab-init` SKILL.md — the foundation everything else builds on.*

| 2026-03-10 | 2.0 | Lab Manager v2: single entry point, auto-delegation, quest board, agent lifecycle, multi-agent pipelines, night shift, audit log, LifeOS vision |
