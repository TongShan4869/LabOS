# LabOS Evolution Plan — Adapted from Paperclip Architecture

> Steal the backend brain, keep the Stardew soul.

## What Paperclip Does Well (and we should adapt)

### Phase 1: Foundation (This Week) ⚡

**1. Goal Hierarchy — "Why am I doing this?"**
- Paperclip: Company Mission → Project Goal → Agent Goal → Task
- LabOS version: **Lab Mission → Project → Agent Task → Skill Run**
- Currently we have projects but no explicit goal chain
- **Adapt:** Add `mission` field to lab config, `goal` field to each project, inject into agent system prompts
- Gamification: mission displays on the building facade, goals show on floor signage

**2. Cost Tracking per Agent**
- Paperclip: monthly budgets per agent, auto-pause at limit
- LabOS version: **Token counter per agent** shown in HUD as coins 🪙
- Track `tokens_used` per agent per session in `data/agents/{id}/usage.json`
- Show in filing cabinet under each agent's profile
- Gamification: agents with high cost/value ratio get a "💸" badge, efficient ones get "⚡"

**3. Persistent Agent State Across Sessions**
- Paperclip: agents resume same task context across heartbeats
- We already have `data/agents/{id}/memory.md` — but it's barely used
- **Adapt:** After each conversation, smart-save key context to agent memory (already partially built)
- On next session, agent sees its own memory + project memory + lab memory
- Gamification: agents "level up" independently — Scout Level 3 finds better papers than Scout Level 1

### Phase 2: Orchestration (Next Week) 🔧

**4. Ticket/Task System**
- Paperclip: structured tickets with owner, status, thread
- LabOS version: **Quest Board** 📋
- Tasks are "quests" displayed on a board in the lab scene
- Each quest has: title, description, assigned agent, status (open/active/done), XP reward
- Agents can be assigned quests, or pick them up automatically
- Quest completion → XP + report + memory update
- Data: `data/quests/{id}.json` with status tracking

**5. Agent Delegation / Cross-Agent Requests**
- Paperclip: delegation flows up and down org chart
- LabOS version: agents can **tag-team**
- Scout finds papers → auto-delegates to Critic for review → Quill drafts summary
- Implement via `[DELEGATE:agent_id]` marker in agent responses
- Gamification: "Teamwork" XP bonus when multiple agents collaborate on one quest

**6. Heartbeat / Scheduled Agent Work**
- Paperclip: agents wake on schedule, check work, act
- LabOS version: **Night Shift** 🌙
- Scheduled tasks that agents do while you're away (lit monitoring, trend alerts)
- Uses existing cron system — agents check for new papers in your field weekly
- Morning briefing: "Scout found 3 new papers overnight, Trend spotted a hot topic"
- Gamification: "While you were sleeping..." notification with overnight XP gains

### Phase 3: Governance & Scale (Week 3+) 🏗️

**7. Approval Gates / Checkpoints**
- Already built! Our checkpoint system is governance
- **Enhance:** configurable per-agent autonomy levels
  - Level 0: Ask before everything (current default)
  - Level 1: Auto-proceed for routine tasks, ask for new/expensive ones
  - Level 2: Full autonomy with audit log
- Gamification: trust level unlocked by XP — earn agent autonomy

**8. Audit Log**
- Paperclip: immutable append-only log of all decisions
- LabOS version: **Lab Notebook** 📓
- Every skill run, every agent decision, every checkpoint response → logged
- Browsable in filing cabinet under "Lab Notebook" tab
- Data: `data/audit.jsonl` — append-only

**9. Multi-Floor (Multi-Company equivalent)**
- Paperclip: one deployment, many companies with data isolation
- LabOS version: **Building with Floors** 🏢
- Each floor is a self-contained domain with its own agents, skills, XP
- Floor switching in UI (elevator animation?)
- Shared building-level XP aggregates from all floors
- Floor template format: exportable/importable (like Paperclip's company templates)

## What We Do Better Than Paperclip

| Feature | Paperclip | LabOS |
|---------|-----------|-------|
| UI | React tables/cards | Pixel art sprites with personality |
| Agent presence | Status text | Bouncing sprites, thought bubbles, sleeping animations |
| Progress | Progress bars | XP, levels, badges, quests |
| Onboarding | CLI wizard | Pixel art intro sequence |
| Emotional connection | None (it's a dashboard) | Characters you grow attached to |
| Domain focus | Generic business | Research-specific (extensible to any domain) |

## What NOT to Adapt

- ❌ PostgreSQL — overkill for single-user. Keep JSON files.
- ❌ Org chart hierarchy — our agents are peers, not a corporate ladder. Flat is fine.
- ❌ Multi-company isolation — not needed until multi-floor. Keep simple.
- ❌ HTTP webhook agent protocol — our agents run locally, no need for network protocol yet.
- ❌ Ticket-as-communication — we have chat, which is more natural for researchers.

## Implementation Priority

```
Week 1: Goal hierarchy + cost tracking + quest board UI placeholder
Week 2: Quest board functional + agent delegation + audit log  
Week 3: Night shift (scheduled work) + autonomy levels
Week 4: Multi-floor architecture + floor templates
```

## New Data Structures

```
data/
  quests/                    # Quest board
    {id}.json                # {title, desc, agent, status, xp_reward, created, completed}
  audit.jsonl                # Append-only audit log
  agents/{id}/
    usage.json               # {tokens_in, tokens_out, cost_usd, runs, last_active}
    memory.md                # Agent's personal memory (already exists)
  lab-config.json            # Add: mission, agent_autonomy_levels
```

---

*Plan created 2026-03-10. Living document — update as we build.*
