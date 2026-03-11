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
| **Real-time** | Request/response | WebSocket events | Live events + bidirectional chat |
| **Domain** | Generic | Generic business | Research-specific (extensible) |

---

## 🎮 How It Works

```
You: "Find me papers on neural coupling in music"
  ↓
Lab Manager (orchestrator):
  → Detects: literature search task
  → Delegates to Scout
  → Creates quest on Quest Board (+50 XP)
  → Scout sprite starts bouncing 🔬
  ↓
Scout (specialist agent):
  → Searches PubMed + OpenAlex + arXiv
  → Scores papers with AI semantic analysis
  → Returns results with full metadata
  ↓
Lab Manager:
  → Presents results in report panel
  → Awards XP, updates quest board
  → Live event updates dashboard in real-time
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

### Sprite Behavior

- **Lab Manager** — always visible and clickable, your single entry point
- **Idle specialists** — visible in the lab but non-interactive (part of the scenery)
- **Working specialists** — bounce animation, thought bubbles, clickable to check progress

---

## 📊 Dashboard

Click the 📊 button to open the **three-column dashboard** below the lab scene:

```
┌──────────────────┬──────────────┬────────────────────┐
│ 📋 Quests │ 🌙 │ 🤖 Team        │ 📁 Projects │ 📄  │
├──────────────────┼──────────────┼────────────────────┤
│ ⚡ Active         │ Scout 🟢     │ Neural Coupling    │
│  • find papers.. │  4 runs      │  created 3/9       │
│ ✅ Completed      │ Stat 💤      │                    │
│  • speech-in..   │  0 runs      │ + New Project      │
└──────────────────┴──────────────┴────────────────────┘
```

| Column | Content |
|---|---|
| **Left** | Quests (active + completed) / Night Shift schedules |
| **Center** | Team Roster — agent cards with lifecycle badges and usage stats |
| **Right** | Projects / Reports (switchable tabs) |

Dashboard updates in **real-time** via live events — no polling needed.

---

## 📡 Live Event System

Inspired by [Paperclip](https://github.com/paperclipai/paperclip)'s architecture. Hybrid approach:

- **Bidirectional chat** — client sends messages, server streams replies (Socket.IO)
- **State invalidation** — server pushes lightweight events, frontend refetches from REST

| Event | Triggers |
|---|---|
| `quest.created` | Dashboard quest list refresh + toast |
| `quest.completed` | Dashboard refresh + "✅ Quest completed!" toast |
| `agent.promoted` | "🎉 Scout promoted to persistent!" toast |
| `run.completed` | Coins counter update |
| `lab.stats` | Full stats refresh |

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

Stardew Valley-style browser interface:

- 🎮 **8 animated pixel agents** — idle/clicked/working animations with bouncy sprites and thought bubbles
- 💬 **RPG-style dialogue** — typewriter text, talk to Lab Manager who delegates to the team
- 📊 **3-column dashboard** — quests, team roster, projects & reports — all visible at once
- 🪙 **Coins counter** — total agent runs in HUD, updates in real-time
- 📜 **Chat Log** — session conversation history
- 🌙 **Day/Night cycle** — auto-switches or manual toggle
- ✅ **Interactive checkpoints** — confirm before expensive operations
- 📋 **Report Panel** — slide-in panel with full Markdown rendering
- 📡 **Live events** — dashboard updates instantly when agents complete work

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
│   ├── schedules.json            ← Night shift scheduled tasks
│   └── audit.jsonl               ← Immutable audit log
├── skills/                       ← 9 Python skill scripts
├── lab-ui/
│   ├── backend/
│   │   ├── app.py                ← Flask + SocketIO + agent routing + live events
│   │   └── lab_manager.py        ← Orchestration engine
│   └── frontend/
│       ├── index.html            ← Main page + dashboard panel
│       ├── css/lab.css           ← Styles (HUD, dashboard, sprites, dialogue)
│       ├── js/lab.js             ← Client logic (agents, dashboard, live events)
│       └── assets/               ← Backgrounds, sprites, avatars
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
| Lab Manager | `lab_manager.py` | Delegation engine, quest board, audit log, agent lifecycle, scheduling |
| Backend | `app.py` | Flask server, SocketIO, LLM calls, skill execution, live events |
| Frontend | `lab.js` + `lab.css` | Pixel art UI, 3-column dashboard, animations, live event handlers |
| Skills | `skills/*.py` | Python scripts for each research task |

### Data Flow

```
Browser (Pixel Lab)
  ↕ Socket.IO (bidirectional)
  │
  ├── Client → Server: send_message, checkpoint_reply
  │
  └── Server → Client:
      ├── agent_reply, checkpoint (chat data)
      └── live_event (state invalidation)
           ├── quest.created → refresh dashboard
           ├── quest.completed → refresh + toast
           ├── agent.promoted → toast notification
           └── run.completed → update coins
  │
  ↕ REST APIs
  │
  ├── /api/quests        ← Quest board data
  ├── /api/agents/roster ← Team roster + usage
  ├── /api/projects      ← Project management
  ├── /api/reports       ← Generated reports
  ├── /api/lab/stats     ← Lab-wide statistics
  ├── /api/lab/summary   ← Text summary for LLM context
  └── /api/schedules     ← Night shift CRUD
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
