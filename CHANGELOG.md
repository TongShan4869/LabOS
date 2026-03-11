# LabOS Changelog

## 2026-03-11 — Live Events + Unified Dashboard

### Live Event System
- Paperclip-inspired hybrid architecture: bidirectional chat + event-driven state invalidation
- Server publishes lightweight `live_event` messages over Socket.IO
- Frontend refetches from REST APIs on invalidation (no stale data)
- Events: `quest.created`, `quest.completed`, `agent.promoted`, `run.completed`, `lab.stats`
- Toast notifications for quest lifecycle and agent promotions

### Unified Dashboard
- Merged quest board + filing cabinet into single 📊 Dashboard button
- Three-column layout below lab scene (fixed height, no floating overlays):
  - Left: Quests (active + completed) / Night Shift schedules
  - Center: Team Roster with lifecycle badges and usage stats
  - Right: Projects / Reports (switchable tabs)
- Dashboard auto-refreshes via live events
- New `/api/reports` and `/api/report/<filename>` endpoints

### UI Polish
- Lab Manager renamed (was 醋の虾) — role: Lab Orchestrator
- Idle specialists: fully visible but non-interactive (`pointer-events: none`)
- Working specialists: bounce animation, thought bubbles, clickable
- Lab Manager always clickable as single entry point
- Fixed New Project modal display
- Removed memory tab from dashboard (not needed)

## 2026-03-10 — Lab Manager v2 Architecture

### Lab Manager Orchestration
- Single entry point: user talks to Lab Manager, it auto-delegates to specialists
- `lab_manager.py`: delegation engine, agent registry, quest board, audit log
- Regex-based intent detection routes tasks to Scout/Stat/Quill/etc
- Lab Manager system prompt includes live team/quest/memory context

### Quest Board & Agent Lifecycle
- Every delegated task becomes a tracked quest with XP rewards
- Agent lifecycle: ephemeral → persistent (3+ runs) → scheduled → archived (7d idle)
- Auto-promotion after 3 runs, auto-archive after 7 days idle
- Immutable audit log (`data/audit.jsonl`)

### Multi-Agent Pipelines
- Pipeline definitions: lit_review (Scout→Critic→Quill), study_design (Sage→Stat)
- First step runs automatically, subsequent steps require manual trigger

### Night Shift & Stats
- Scheduled cron tasks for agents (`/api/schedules`)
- Lab stats API (`/api/lab/stats`, `/api/lab/summary`)
- Coins counter (🪙) in HUD showing total agent runs

### LifeOS Vision
- LabOS is Floor 1 of a pixel art building (each floor = department with AI agents)
- Vision doc: `docs/vision.md`
- Paperclip adaptation plan: `docs/paperclip-adaptation-plan.md`
- Agent architecture v2 spec: `docs/agent-architecture-v2.md`

### Documentation
- Complete README rewrite — Lab Manager pattern, LifeOS vision, architecture diagrams
- PRD bumped to v2.0
- Getting started guide updated

## 2026-03-06 — E2E Wiring + UI Overhaul

### Real Skill Execution
- Backend spawns actual Python skill scripts (not LLM chat stubs)
- DeepSeek V3 (via GMI Cloud) extracts CLI args from natural language
- `[CHECKPOINT]` markers bridged through WebSocket for interactive flow
- `[NOTIFY:]` markers displayed as agent messages

### Report Panel
- Slide-in panel for long agent outputs (>200 chars)
- Readable system font, scrollable, papers auto-formatted as styled cards
- 📋 button in HUD shows all session reports, reopen any

### Notifications
- Red ! badge on agent sprite when reply arrives while dialogue closed
- Toast notifications for background replies
- Dialogue shifts left when report panel open

### Onboarding
- 5-step wizard: welcome → lab name → integrations → first project → loading
- Loading screen with animated progress bar and fun messages
- Lab name shown in HUD title

### XP Info Popup
- Click level/XP bar to see level titles, badges, XP history
- 10 level tiers from "Confused First-Year" to "Nobel-Bound"

### Visual
- Silhouette-following glow (drop-shadow, not box-shadow)
- Stale agent state cleared on server restart

### Architecture
- Switched from eventlet to threading (eventlet breaks subprocess pipes)
- LLM via OpenAI-compatible API (configurable via .env)
- `/api/init`, `/api/config` endpoints

## 2026-03-05 — Initial MVP

- 9 skills, shared lab_utils.py, Stardew Valley pixel UI
- 8 agent characters with sprites and avatars
- Flask + Flask-SocketIO backend
- XP/level system, research graph, Obsidian integration
