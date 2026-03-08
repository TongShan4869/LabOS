# LabOS 🔬

> **Your AI-powered virtual research lab. You're the PI. The agents are your team.**

LabOS is an [OpenClaw](https://openclaw.ai) skill suite that gives any researcher a virtual AI-powered lab. Delegate literature search, statistical analysis, writing, peer review, and field monitoring to AI agents — the way a real PI delegates to lab members.

Built for PhD students. Works for any research field.

---

## ✨ What LabOS Does

- 📰 **Weekly field digest** — automatic Monday briefings on new papers in your field
- 🔍 **Literature search** — on-demand deep dives into PubMed, OpenAlex, arXiv
- 🎓 **Socratic advisor** — asks the hard questions a good PI would ask
- ✍️ **Writing assistant** — drafts introductions, methods, abstracts, grant aims in your voice
- 🤺 **Peer reviewer** — simulates rigorous anonymous peer review before you submit
- 📚 **Publishing assistant** — finds the right journal, reformats your manuscript, writes cover letters
- 📊 **Biostatistician** — advises on study design, runs stats (Python/R), interprets results
- 🔒 **Security warden** — protects your research IP and prevents accidental data leakage to LLMs

---

## 🏗️ Architecture

```
LabOS/
├── README.md
├── PRD.md                    ← Full product requirements document
├── LAB_CONFIG.json           ← Your preferences (populated by lab-init)
├── LAB_MEMORY.md             ← Evolving user profile (auto-updated)
├── research-graph.jsonl      ← Shared knowledge graph (all projects)
├── xp.json                   ← Gamification state
├── sessions/                 ← Per-session logs
└── skills/
    ├── lab-init/             ← Onboarding
    ├── lab-field-trend/      ← Weekly digest
    ├── lab-lit-scout/        ← Literature search
    ├── lab-research-advisor/ ← Socratic mentor
    ├── lab-writing-assistant/← Draft writer
    ├── lab-peer-reviewer/    ← Peer review simulator
    ├── lab-security/         ← Lab security warden
    ├── lab-publishing-assistant/ ← Journal selection + submission
    └── lab-biostat/          ← Biostatistician
```

### Two-Layer Knowledge Model

```
┌─────────────────────────────────────────┐
│         SHARED KNOWLEDGE LAYER          │
│  research-graph.jsonl · Obsidian · Zotero│
│  "What you know as a researcher"        │
└─────────────────────────────────────────┘
           ↑ all agents can query ↑
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Project A   │  │  Project B   │  │  Project C   │
│  hypotheses  │  │  hypotheses  │  │  hypotheses  │
│  experiments │  │  experiments │  │  experiments │
└──────────────┘  └──────────────┘  └──────────────┘
```

A paper found in Project A is immediately available to Project B. Agents reason across your full knowledge base.

---

## 💬 How to Interact with LabOS

LabOS is **natural language first**. You don't run commands — you just talk to OpenClaw, and it figures out which agent to call.

### Examples

| You say... | What runs |
|---|---|
| "Find me papers on speech-music coupling in ASD" | `lab-lit-scout` |
| "Draft my introduction for the neural coupling project" | `lab-writing-assistant --section introduction` |
| "Advise me on my infant hearing project" | `lab-research-advisor --project infant-hearing` |
| "What's new in my field this week?" | `lab-field-trend` |
| "Analyze this dataset — is there a group difference?" | `lab-biostat --mode analyze` |
| "Review my methods section" | `lab-peer-reviewer --mode methods-critique` |

**The SKILL.md** in each skill folder teaches OpenClaw when to activate it and how to translate your words into the right flags. **The Python script** does the actual work. You never need to touch either directly.

```
You (natural language)
    → OpenClaw matches intent to skill (via SKILL.md)
    → Subagent runs Python script with right flags
    → Results saved to Obsidian / Discord / research graph
    → XP awarded
```

---

## 🚀 Getting Started

### Prerequisites
- [OpenClaw](https://openclaw.ai) installed
- Python 3 with `scipy`, `statsmodels`, `pingouin`, `matplotlib` (for biostat)
- Obsidian vault (recommended), Zotero (recommended)

### Installation

```bash
# Clone into your OpenClaw skills directory
git clone https://github.com/TongShan4869/LabOS.git ~/.openclaw/workspace/LabOS

# Copy skills to OpenClaw skills directory
cp -r LabOS/skills/lab-* ~/.openclaw/workspace/skills/

# Copy lab state files
cp -r LabOS/{LAB_CONFIG.json,research-graph.jsonl,xp.json} ~/.openclaw/workspace/lab/
```

### Initialize your lab

```
# Tell OpenClaw:
"Set up my LabOS lab"
# or
openclaw lab-init
```

OpenClaw will walk you through a conversational setup to configure your fields, knowledge store, and preferences.

---

## 🛠️ Skills Reference

| Skill | Trigger | Description |
|---|---|---|
| `lab-init` | "set up my lab" | Onboarding — scaffolds everything |
| `lab-field-trend` | "what's new in my field" | Weekly digest of new papers |
| `lab-lit-scout` | "find papers on X" | On-demand literature search |
| `lab-research-advisor` | "advise me on my project" | Socratic mentor session |
| `lab-writing-assistant` | "draft my introduction" | Writes sections in your voice |
| `lab-peer-reviewer` | "review my paper" | Simulates peer review |
| `lab-security` | "security audit" | Protects research IP |
| `lab-publishing-assistant` | "find a journal" | Journal selection + submission prep |
| `lab-biostat` | "analyze my data" | Stats analysis and study design |

### Invocation flags (all skills)
- `--project "name"` — scope to a specific project
- `--scope global` — cross-project search (default when no --project)

---

## 🏆 Gamification

LabOS rewards research milestones with XP and badges:

| Milestone | XP | Badge |
|---|---|---|
| Lab initialized | +100 | 🧪 Lab Open |
| First paper saved | +50 | 📚 Collector |
| Hypothesis + 3 papers | +100 | 💡 Theorist |
| Weekly digest | +25 | 📰 Stayed Current |
| Lit dive | +50 | 🔬 Literature Dive |
| Analysis + results | +150 | 📊 Experimenter |
| Draft written | +200 | ✍️ Author |
| Submission prep | +300 | 🚀 Launcher |
| Paper accepted | +1000 | 🏅 Published |

**Levels:** Confused First-Year → Lab Gremlin → Professional Coffee Drinker → PhD Candidate → Doctor of Suffering → Postdoc (Indentured Servant Edition) → ... → Nobel Laureate → Cited More Than Darwin → The Field IS You → **The Omniscient and Omnipotent Being of the Universe** 🌌

*Level 20 unlocks badge 🌌 Beyond Peer Review. All agents address you as "Your Omniscience."*

---

## 🔒 Security

LabOS classifies all research data with sensitivity levels:

| Level | Meaning |
|---|---|
| `public` | Published papers, public methods |
| `internal` | Working notes, in-progress analysis |
| `sensitive` | Unpublished hypotheses, novel results |
| `confidential` | Human subjects data, NIH-restricted |

`lab-security` runs automatically before any skill sends content to an external LLM API. Human subjects projects are flagged automatically.

---

## 🖥️ Pixel Lab UI

LabOS includes an optional **Stardew Valley-style pixel art interface** — a browser-based virtual lab where your agents walk around as animated sprites.

### Features
- 🎮 **8 animated pixel agents** with idle/clicked/working animations
- 💬 **RPG-style dialogue system** — click an agent to chat, typewriter text, paginated responses
- 📂 **Filing Cabinet** — browse projects, reports, and agent memories
- 📜 **Chat Log** — session-based conversation history
- 🏆 **XP & Leveling** — 15 levels from "Confused First-Year" to "The Omniscient and Omnipotent Being of the Universe 🌌"
- 📋 **Report Panel** — slide-in panel for long outputs with full Markdown rendering
- 🔔 **Background notifications** — red badge on agent sprites when results are ready
- ✅ **Interactive checkpoints** — agents ask for confirmation before expensive operations

### How It Works

```
Browser (Pixel Lab)
  ↕ WebSocket (Socket.IO)
Flask Backend (app.py)
  ↕ OpenAI-compatible API
OpenClaw Gateway (Claude) ← primary
  or GMI Cloud (DeepSeek V3) ← fallback
```

**Agents are powered by Claude via the OpenClaw gateway** — when you talk to Scout or Sage in the pixel lab, you're talking to Claude (Haiku). The gateway handles auth, model routing, and rate limiting. If the gateway is unavailable, it falls back to DeepSeek V3 via direct API.

### Running the UI

```bash
cd lab-ui
pip install flask flask-socketio
python backend/app.py  # Starts on port 18792
```

Then open `http://localhost:18792` or tunnel with Cloudflare.

---

## 🗺️ Roadmap

**MVP (current):** All 9 skills above

**V2:**
- `lab-data-analyst` — broader data exploration and pipeline work
- `lab-project-standup` — daily cross-project status
- Notion sync
- Slack lab channel monitoring
- Star Office UI integration (pixel art virtual lab interface)
- Multi-user support

---

## 📄 Documentation

- [`PRD.md`](PRD.md) — Full product requirements document (living document)
- [`docs/lit-scout-architecture.md`](docs/lit-scout-architecture.md) — Literature Scout search pipeline, semantic scoring strategy, and report format
- Each skill has its own `SKILL.md` (activation) and `script.md` (execution logic)

---

## 🤝 Contributing

This is an early-stage project. PRD is in `PRD.md` — contributions welcome.

---

## License

MIT

---

*Built with [OpenClaw](https://openclaw.ai) · Created by Cu + 醋の虾 🦞*
