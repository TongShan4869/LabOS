# LabOS Agent Architecture v2 — OpenClaw-Native Orchestration

> You talk to one agent. It runs the lab.

## Core Concept

**No manual hiring. No agent selection UI.** You talk to the Lab Manager — a persistent OpenClaw session that understands your research, delegates to specialist subagents, and manages the lab autonomously.

```
You (PI)
  ↓
Lab Manager (persistent OpenClaw session — your postdoc)
  ↓ spawns/delegates
Specialist Subagents (the RAs)
  ├── Scout — literature search
  ├── Stat — statistical analysis
  ├── Quill — writing assistance
  ├── Critic — paper review
  ├── Sage — research advisor
  ├── Trend — trend analysis
  ├── Warden — reproducibility
  └── [Custom] — user-defined specialists
```

## Agent Lifecycle

Agents earn their permanence through use:

```
1. SPAWNED    → First task, created as one-shot (mode="run")
2. PROMOTED   → Used 3+ times, auto-promoted to persistent (mode="session")  
3. SCHEDULED  → Given recurring work, gets a cron heartbeat
4. ARCHIVED   → Idle 7+ days, session killed, memory saved to disk
```

No manual hiring, no manual firing. The Lab Manager handles it all.

## How It Works

### User → Lab Manager (single entry point)

```
User: "Find me recent papers on neural coupling during music listening"

Lab Manager thinks:
  - This is a literature search task
  - Scout handles this
  - Scout has no active session → spawn one-shot

Lab Manager: sessions_spawn(
  task="Search PubMed, OpenAlex, arXiv for papers on neural coupling during music listening. Use the lit-scout skill.",
  label="scout-task-001",
  mode="run"
)

Scout subagent: runs lit-scout skill, returns results
Lab Manager: formats results, presents to user in pixel UI
```

### Follow-up → Reuse or escalate

```
User: "Now compare the sample sizes across those papers"

Lab Manager thinks:
  - This needs stats on the papers Scout just found
  - Need to pass Scout's results to Stat
  - Spawn Stat with context

Lab Manager: sessions_spawn(
  task="Analyze sample sizes across these papers: [results from Scout]. Compare distributions.",
  label="stat-task-001", 
  mode="run"
)
```

### Recurring work → Auto-schedule

```
User: "Check for new papers in my field every Monday"

Lab Manager thinks:
  - This is a recurring task for Scout
  - Promote Scout to persistent session
  - Create cron heartbeat

Lab Manager:
  1. sessions_spawn(task="...", label="scout-persistent", mode="session")
  2. cron.add(schedule={kind:"cron", expr:"0 9 * * 1"}, ...)
```

## Data Architecture

```
data/
  lab-manager/
    session.json          # Lab Manager session state
    memory.md             # Lab Manager's memory (what user cares about, preferences)
  
  agents/{id}/
    config.json           # Agent config: name, sprite, specialty, skills, status
    memory.md             # Agent's personal memory (persists across sessions)
    usage.json            # Token usage, run count, last active timestamp
    session-key.txt       # OpenClaw session key (if persistent)
  
  quests/
    {id}.json             # Task tracking: title, agent, status, xp_reward
  
  audit.jsonl             # Append-only log of all agent actions
```

### Agent Config Schema

```json
{
  "id": "scout",
  "name": "Scout",
  "sprite": "sprite-scout.png",
  "specialty": "Literature search and paper analysis",
  "skills": ["lab-lit-scout"],
  "status": "active",           // active | idle | archived
  "lifecycle": "ephemeral",     // ephemeral | persistent | scheduled
  "run_count": 0,
  "promotion_threshold": 3,     // auto-promote after N runs
  "heartbeat_cron": null,       // cron expression if scheduled
  "created_at": "2026-03-10T...",
  "last_active": null
}
```

## Lab Manager System Prompt

```
You are the Lab Manager of {lab_name}. You run this research lab.

Your PI is {user_name}. They tell you what they need. You figure out how to get it done.

You have a team of specialist agents. You delegate tasks to them by spawning subagent sessions.
You don't do the work yourself — you orchestrate.

TEAM:
{for each agent in agents}
- {name} ({specialty}) — Skills: {skills} — Status: {status}
{end}

ACTIVE PROJECT: {project_name} — {project_field}
MISSION: {lab_mission}

DELEGATION RULES:
1. Match task to the best specialist based on their specialty and skills
2. First-time tasks → spawn as one-shot (mode="run")
3. If an agent has been used 3+ times → promote to persistent session
4. For recurring requests → suggest scheduling via cron
5. Always report results back to the PI in a clear, formatted way
6. Track XP: +50 for skill runs, +10 for conversations

MEMORY:
{lab_memory}
{agent_memories}

When delegating, use sessions_spawn with:
- task: clear instructions including any context from previous results
- label: "{agent_id}-task-{counter}" or "{agent_id}-persistent"
- mode: "run" for one-shot, "session" for persistent agents
```

## Pixel UI Integration

The pixel UI reflects agent state in real-time:

| Agent State | Sprite Behavior |
|-------------|-----------------|
| No session  | Standing idle, occasional blink |
| Spawning    | Wake-up animation, stretch |
| Working     | Bouncy animation, thought bubbles, golden glow |
| Reporting   | Walking toward Lab Manager sprite |
| Idle (persistent) | Sitting at desk, reading, occasional fidget |
| Archived    | Sleeping / lights off at their station |

### Lab Manager sprite
- Always present, center of lab
- When delegating: turns to face the specialist agent
- When reporting to user: faces camera, speech bubble

## Migration from v1

Current v1 flow:
```
User clicks agent sprite → direct LLM call → response
```

New v2 flow:
```
User talks to Lab Manager → Manager spawns subagent → subagent works → Manager presents result
```

### Migration steps:
1. Lab Manager becomes the single chat entry point (dialogue box always talks to Manager)
2. Clicking specialist sprites shows their status/memory, not a chat
3. Backend routes all messages through Lab Manager session
4. Lab Manager delegates via OpenClaw sessions_spawn
5. Specialist agent sprites animate based on subagent session status

### Backwards compatibility:
- Direct agent chat still available via a "Direct Mode" toggle (debug/power-user feature)
- All existing skills work unchanged — subagents just call them
- Filing cabinet, reports, XP all work the same

## Cost & Budget

Each agent tracks:
```json
{
  "tokens_in": 0,
  "tokens_out": 0,
  "cost_usd": 0.0,
  "runs": 0,
  "last_active": null
}
```

- Displayed in HUD as 🪙 coin counter
- Lab Manager can see total lab spend
- Future: configurable budget caps per agent (auto-pause when exceeded)

## Quest Board (Task Tracking)

When the Lab Manager delegates, it creates a quest:
```json
{
  "id": "quest-001",
  "title": "Find papers on neural coupling in music",
  "assigned_to": "scout",
  "status": "active",
  "xp_reward": 50,
  "created_at": "2026-03-10T...",
  "completed_at": null,
  "result_summary": null
}
```

Quest board visible in pixel UI as a bulletin board on the lab wall.

---

*Architecture spec v2. Created 2026-03-10.*
*Previous: v1 = direct LLM calls per agent (no orchestration)*
