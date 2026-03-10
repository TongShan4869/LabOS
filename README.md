# LabOS 🔬

> **Your AI-powered virtual research lab — gamified, orchestrated, open source.**
> 
> Talk to one Lab Manager. It runs the whole team.

LabOS is a **gamified AI agent orchestration system** with a Stardew Valley-style pixel art UI. You're the PI. One Lab Manager delegates to specialist agents — literature search, stats, writing, peer review — automatically.

**LabOS is Floor 1 of [LifeOS](#-lifeos-vision)** — a building where each floor runs a different part of your life with AI agents.

Built with [OpenClaw](https://openclaw.ai). Open source under MIT.

---

## ✨ What Makes LabOS Different

| | Traditional AI Tools | Paperclip | LabOS |
|---|---|---|---|
| **UI** | Chat windows | React dashboard | Pixel art world |
| **Feel** | Talking to a bot | Managing employees | Playing your life |
| **Agents** | One at a time | Manual hire & assign | Auto-delegated by Lab Manager |
| **Progress** | Invisible | Cost metrics | XP, levels, quests |
| **Domain** | Generic | Generic business | Research-specific (extensible) |

---

## 🎮 How It Works

```
You: "Find me papers on neural coupling in music"
  ↓
Lab Manager (your postdoc):
  → Detects: literature search task
  → Delegates to Scout
  → Creates quest on Quest Board (+50 XP)
  ↓
Scout (specialist agent):
  → Searches PubMed + OpenAlex + arXiv
  → Scores papers with AI semantic analysis
  → Returns results with full metadata
  ↓
Lab Manager:
  → Presents results in report panel
  → Awards XP, updates quest board
  → Scout earns run count toward promotion
```

**No manual agent selection.** Talk to the Lab Manager, it figures out who does what.

---

## 🤖 Your Team

| Agent | Role | Skill |
|---|---|---|
| 🧑‍🔬 **Lab Manager** | Orchestrator — delegates everything | All routing |
| 🔍 **Scout** | Literature search | PubMed, OpenAlex, arXiv |
| 📊 **Stat** | Biostatistician | Study design, power analysis |
| ✍️ **Quill** | Writing assistant | Drafts, abstracts, grants |
| 🔬 **Critic** | Peer reviewer | Methods critique, gap analysis |
| 🧠 **Sage** | Research advisor | Strategy, Socratic mentoring |
| 📰 **Trend** | Trend analyst | Field monitoring, emerging topics |
| 🔒 **Warden** | Security | IP protection, data classification |

### Agent Lifecycle

Agents earn their permanence through use:

```
SPAWNED (first task) → ephemeral
  ↓ used 3+ times
PROMOTED → persistent (keeps memory between sessions)
  ↓ given recurring work
SCHEDULED → gets cron heartbeat (e.g., weekly paper check)
  ↓ idle 7+ days
ARCHIVED → session killed, memory saved to disk
```

No manual hiring, no manual firing. The Lab Manager handles it all.

---

## 📋 Quest Board

Every delegated task becomes a **quest** with XP rewards:

- **Active quests** — what's being worked on now
- **Completed quests** — history with results
- **Team Roster** — agent stats, lifecycle status, usage
- **Night Shift** — scheduled recurring tasks

---

## 🔗 Multi-Agent Pipelines

Complex tasks trigger multi-agent chains:

| Pipeline | Steps | Trigger |
|---|---|---|
| **Literature Review** | Scout → Critic → Quill | "comprehensive literature review on X" |
| **Study Design** | Sage → Stat | "design a study on X" |

---

## 🏆 Gamification

| Level | Title | XP |
|---|---|---|
| 1 | Confused First-Year | 0 |
| 2 | Lab Gremlin | 150 |
| 3 | Professional Coffee Drinker | 300 |
| 4 | PhD Candidate | 450 |
| 5 | Doctor of Suffering | 600 |
| ... | ... | ... |
| 15 | Cited More Than Darwin | 2100 |
| 20 | The Omniscient and Omnipotent Being of the Universe 🌌 | ∞ |

**XP sources:** +50 per skill run, +10 per agent conversation, quest completion bonuses.

---

## 🖥️ Pixel Lab UI

Stardew Valley-style browser interface with:

- 🎮 **8 animated pixel agents** — idle/clicked/working animations with bouncy sprites and thought bubbles
- 💬 **RPG-style dialogue** — typewriter text, click any agent to talk through Lab Manager
- 📂 **Filing Cabinet** — projects, reports, agent memories
- 📋 **Quest Board** — active/completed quests, team roster, night shift schedules
- 🪙 **Coins Counter** — total agent runs displayed in HUD
- 📜 **Chat Log** — session conversation history
- 🌙 **Day/Night cycle** — auto-switches or manual toggle
- ✅ **Interactive checkpoints** — confirm before expensive operations
- 📋 **Report Panel** — slide-in panel with full Markdown rendering

---

## 🚀 Getting Started

### Quick Start

```bash
git clone https://github.com/TongShan4869/LabOS.git
cd LabOS
python3 -m venv venv && source venv/bin/activate
pip install flask flask-socketio openai requests
```

Create `.env`:
```env
# Option A: OpenClaw Gateway (recommended)
GATEWAY_URL=http://127.0.0.1:12286/v1
GATEWAY_TOKEN=your_token
GATEWAY_MODEL=haiku

# Option B: Any OpenAI-compatible API
LLM_API_KEY=your_key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Run:
```bash
cd lab-ui && python backend/app.py
# Open http://localhost:18792
```

See [**docs/getting-started.md**](docs/getting-started.md) for the full setup guide.

---

## 🏗️ Architecture

```
LabOS/
├── .env                          ← API keys (gitignored)
├── LAB_CONFIG.json               ← Research fields & preferences
├── LAB_MEMORY.md                 ← Evolving shared memory
├── data/
│   ├── agents/{id}/              ← Per-agent config, memory, usage
│   ├── projects/{uuid}/          ← Per-project data, reports, chats
│   ├── quests/                   ← Quest board (task tracking)
│   └── audit.jsonl               ← Immutable audit log
├── skills/                       ← 9 Python skill scripts
├── lab-ui/
│   ├── backend/
│   │   ├── app.py                ← Flask + SocketIO + agent routing
│   │   └── lab_manager.py        ← Orchestration engine
│   └── frontend/                 ← Pixel art UI (HTML/CSS/JS)
└── docs/
    ├── getting-started.md
    ├── vision.md                 ← LifeOS building concept
    ├── agent-architecture-v2.md  ← Lab Manager orchestration spec
    ├── paperclip-adaptation-plan.md
    └── lit-scout-architecture.md
```

### Core Components

| Component | File | Purpose |
|---|---|---|
| Lab Manager | `lab_manager.py` | Delegation engine, quest board, audit log, agent lifecycle |
| Backend | `app.py` | Flask server, SocketIO, LLM calls, skill execution |
| Frontend | `lab.js` + `lab.css` | Pixel art UI, animations, quest board, filing cabinet |
| Skills | `skills/*.py` | Python scripts for each research task |

### Data Flow

```
User message → Lab Manager (delegation engine)
  ├── General chat → LLM response (Claude via OpenClaw)
  └── Task detected → Route to specialist agent
        ├── Create quest (+XP)
        ├── Run skill script (Python subprocess)
        ├── Stream results via SocketIO
        ├── Save report to filing cabinet
        └── Complete quest, record agent usage
```

---

## 🌆 LifeOS Vision

LabOS is **Floor 1** of a bigger idea: a pixel art building where each floor runs a different part of your life with AI agents.

| Floor | Domain | Agents |
|---|---|---|
| 🔬 **Lab** | Research | Scout, Stat, Quill, Critic, Sage, Trend, Warden |
| 💪 **Health** | Fitness & nutrition | *(planned)* |
| 💰 **Business** | Startup ops | *(planned)* |
| 🎵 **Music** | Production & practice | *(planned)* |
| 📚 **Learning** | Skills & reading | *(planned)* |
| 🏠 **Life** | Calendar & habits | *(planned)* |

**The concept:** One-person company that runs your life, gamified as a pixel art building. Each floor is a department. Users can build their own floors with custom skills and share them with the community — like Stardew Valley mods.

See [docs/vision.md](docs/vision.md) for the full vision.

---

## 📄 Documentation

- [**Getting Started**](docs/getting-started.md) — Setup in 10 minutes
- [**LifeOS Vision**](docs/vision.md) — The building concept
- [**Agent Architecture v2**](docs/agent-architecture-v2.md) — Lab Manager orchestration spec
- [**Paperclip Adaptation Plan**](docs/paperclip-adaptation-plan.md) — What we adapted from Paperclip
- [**Lit Scout Architecture**](docs/lit-scout-architecture.md) — Search pipeline & scoring

---

## 🤝 Contributing

LabOS is open source under MIT. PRD is in [`PRD.md`](PRD.md).

**Want to build a new floor?** Each floor is just:
- A set of agent configs (name, sprite, specialty)
- Python skill scripts
- A pixel art background

The skill format is a standard: write a Python script, drop it in, your agent learns a new ability.

---

## License

MIT

---

*Built with [OpenClaw](https://openclaw.ai) · Created by Cu + 醋の虾 🦞*
