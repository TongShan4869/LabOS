# LabOS Changelog

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
