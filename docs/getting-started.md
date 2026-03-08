# Getting Started with LabOS 🔬

> Set up your own AI-powered virtual research lab in under 10 minutes.

---

## Prerequisites

- **Python 3.9+**
- **Git**
- An **LLM API key** — one of:
  - [OpenClaw](https://openclaw.ai) gateway (recommended — agents become Claude)
  - [OpenAI-compatible API](https://platform.openai.com/) (OpenAI, DeepSeek, GMI Cloud, etc.)

---

## 1. Clone the Repository

```bash
git clone https://github.com/TongShan4869/LabOS.git
cd LabOS
```

---

## 2. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install flask flask-socketio openai requests
```

---

## 3. Configure Your LLM Backend

Create a `.env` file in the project root:

### Option A: OpenClaw Gateway (Recommended)

If you have [OpenClaw](https://openclaw.ai) running locally, agents are powered by Claude — they're intelligent, context-aware, and can decide when to run research tools vs. have a conversation.

```env
GATEWAY_URL=http://127.0.0.1:12286/v1
GATEWAY_TOKEN=your_openclaw_gateway_token
GATEWAY_MODEL=haiku

# Fallback (optional)
LLM_API_KEY=your_fallback_api_key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

To find your gateway token:
```bash
openclaw status
# Look for "Gateway token" in the output
```

### Option B: Direct OpenAI-Compatible API

Works with OpenAI, DeepSeek, GMI Cloud, Together AI, or any OpenAI-compatible provider.

```env
LLM_API_KEY=your_api_key_here
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

**Provider examples:**

| Provider | `LLM_API_BASE` | `LLM_MODEL` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| GMI Cloud | `https://api.gmi-serving.com/v1` | `deepseek-ai/DeepSeek-V3-0324` |
| Together AI | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b-chat-hf` |

---

## 4. Start the Server

```bash
cd lab-ui
python backend/app.py
```

You should see:
```
🔬 LabOS UI running at http://127.0.0.1:18792
```

Open **http://localhost:18792** in your browser.

---

## 5. First-Time Setup (Onboarding)

On first launch, LabOS walks you through a quick onboarding:

1. **Enter your name** — this becomes your lab name
2. **Pick your research fields** — e.g., neuroscience, machine learning, genomics
3. **Done!** — your lab is ready

Your config is saved to `LAB_CONFIG.json`. LabOS won't ask again unless you delete it.

---

## 6. Meet Your Agents

Click on any agent sprite in the lab to start chatting:

| Agent | Role | What They Do |
|---|---|---|
| 🔍 **Scout** | Literature Scout | Searches PubMed, OpenAlex, arXiv for papers |
| 🧠 **Sage** | Research Advisor | Socratic mentor — asks the hard questions |
| ✍️ **Quill** | Writing Assistant | Drafts intros, methods, abstracts |
| 📊 **Stat** | Biostatistician | Study design, stats analysis |
| 🔬 **Critic** | Peer Reviewer | Simulates rigorous peer review |
| 📰 **Trend** | Field Monitor | Weekly digest of new papers |
| 📚 **Main** | Publishing Assistant | Journal selection, submission prep |
| 🔒 **Warden** | Security | Protects research IP |

### Example Conversations

- Click **Scout** → *"Find me papers on neural coupling in speech perception"*
- Click **Sage** → *"What are the gaps in my hypothesis about subcortical encoding?"*
- Click **Quill** → *"Draft my introduction section"*
- Click **Stat** → *"Is a mixed-effects model appropriate for my repeated-measures design?"*

---

## 7. Key Features

### 📂 Filing Cabinet
Click the 📂 button (top-right) to browse:
- **Projects** — create and switch between research projects
- **Reports** — all generated reports with titles and timestamps
- **Agent Memory** — what each agent remembers about your work

### 📜 Chat Log
Click 📜 to see all conversations from the current session.

### 🌙 Day/Night Mode
Click the ☀️/🌙 button to toggle — or let it auto-switch based on your local time.

### 🏆 XP & Leveling
Earn XP by chatting with agents and running skills:
- Agent conversation: **+10 XP**
- Skill run (lit search, stats, etc.): **+50 XP**

Level up from *Confused First-Year* all the way to *The Omniscient and Omnipotent Being of the Universe* 🌌

Click the XP bar (top-left) to see your progress and level history.

### 📋 Reports
Long agent responses automatically become reports — viewable in a slide-in panel with full Markdown rendering (headings, tables, code blocks, links).

### ✅ Checkpoints
For expensive operations (like searching hundreds of papers), agents ask for confirmation before proceeding. You stay in control.

---

## 8. Expose to the Internet (Optional)

To access LabOS from anywhere, use a Cloudflare tunnel:

```bash
# Install cloudflared
# macOS: brew install cloudflared
# Linux: see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# Start a quick tunnel
cloudflared tunnel --url http://127.0.0.1:18792
```

This gives you a public URL like `https://random-words.trycloudflare.com`. Share it to access your lab from any device.

> **Note:** Quick tunnel URLs change on restart. For a permanent URL, set up a [named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-tunnel/).

---

## 9. Keep It Running

The server can get killed by OS signals. Use a watchdog script:

```bash
cat > run.sh << 'EOF'
#!/bin/bash
cd lab-ui
while true; do
  python backend/app.py
  echo "Server died, restarting in 2s..."
  sleep 2
done
EOF

chmod +x run.sh
nohup bash run.sh > server.log 2>&1 &
```

---

## Project Structure

```
LabOS/
├── .env                      ← Your API keys (gitignored)
├── LAB_CONFIG.json           ← Your research fields & preferences
├── xp.json                   ← Gamification state
├── data/
│   ├── projects/             ← Per-project data
│   │   └── {id}/
│   │       ├── meta.json     ← Project metadata
│   │       ├── memory.json   ← Project-specific memory
│   │       └── reports/      ← Generated reports
│   ├── agents/               ← Per-agent memory
│   └── shared/               ← Cross-project knowledge
├── lab-ui/
│   ├── backend/
│   │   └── app.py            ← Flask + SocketIO server
│   └── frontend/
│       ├── index.html         ← Main page
│       ├── css/lab.css        ← All styles
│       ├── js/lab.js          ← All client logic
│       └── assets/
│           ├── lab/           ← Background images (day/night)
│           ├── sprites/       ← Agent sprite sheets
│           └── avatars/       ← Agent portrait images
├── skills/                    ← Skill scripts (Python)
└── docs/                      ← Documentation
```

---

## Customization

### Add Your Own Research Fields

Edit `LAB_CONFIG.json`:

```json
{
  "lab_name": "Your Lab",
  "fields": ["your-field-1", "your-field-2", "your-field-3"],
  "user_name": "Your Name"
}
```

### Change the LLM Model

Edit `.env` and restart:
```env
GATEWAY_MODEL=sonnet          # Claude Sonnet (smarter, slower)
GATEWAY_MODEL=haiku           # Claude Haiku (fast, good enough)
LLM_MODEL=gpt-4o             # OpenAI GPT-4o
LLM_MODEL=deepseek-chat      # DeepSeek
```

### Customize Agent Sprites

Replace PNG files in `lab-ui/frontend/assets/sprites/`:
- Each sprite sheet is **384×144 px** (4 frames × 96×144 each)
- Frames: idle1, idle2, clicked, working
- Use transparent background (no green screen!)

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Blank screen on load | Check browser console (F12) for JS errors |
| Agents don't respond | Check `.env` — is your API key valid? |
| "LLM not configured" | Create `.env` with `LLM_API_KEY` |
| 502 Bad Gateway (tunnel) | Restart the Flask server, then the tunnel |
| Server keeps dying | Use the watchdog script (see above) |
| Stale UI after update | Hard refresh: `Ctrl+Shift+R` / `Cmd+Shift+R` |

---

## What's Next?

- **Run a literature search** — ask Scout to find papers in your field
- **Create a project** — open 📂, click "New Project"
- **Build your knowledge** — every conversation feeds into agent memory
- **Level up** — the more you use it, the more XP you earn 🎮

---

*Built with [OpenClaw](https://openclaw.ai) · Created by Cu + 醋の虾 🦞*
