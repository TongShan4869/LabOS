# LifeOS Vision

> One-person company that runs your life, gamified as a pixel art building.

## Core Concept

LabOS is not the product — it's the **template**.

The product is a pixel art building where each **floor** is a department staffed by AI agents with domain-specific skills. The entire building is your one-person company, running your life.

## The Building

| Floor | Domain | Agents | Status |
|-------|--------|--------|--------|
| 🔬 Lab | Research | Scout, Stat, Quill, Critic, Sage, Trend, Warden | ✅ Built |
| 💪 Health | Fitness & nutrition | Trainer, Dietitian, Tracker | 💭 Planned |
| 💰 Business | Startup ops | Strategist, Outreach, Analyst | 💭 Planned |
| 🎵 Music | Production & practice | Producer, Ear, Arranger | 💭 Planned |
| 📚 Learning | Skills & reading | Tutor, Librarian, Quiz | 💭 Planned |
| 🏠 Life | Calendar & habits | Planner, Butler, Social | 💭 Planned |

Each floor has:
- Its own **pixel art scene** (like Stardew Valley's different areas)
- Its own **specialized agents** (sprites with personalities)
- Its own **XP track** (domain-specific progression)
- A shared **building-wide level** (your overall life level)

## What Makes This Different

| | Paperclip | LifeOS |
|---|---|---|
| Metaphor | Company org chart | Building with floors |
| UI | React dashboard | Pixel art world |
| Feel | "Managing employees" | "Playing your life" |
| Customization | Plug in agents | Build entire floors + skills |
| Target | Devs/businesses | Anyone with ambition |

### Key Insight

**Makes the invisible visible.** When Scout bounces around with thought bubbles while searching papers — you *feel* the work happening. A progress bar doesn't do that. A little sprite grinding away does.

## Open-Source Strategy

- LabOS (Lab Floor) is the **reference implementation** — fully open-source
- The skill format is a standard: write a Python script, drop it in, agent learns a new ability
- Community builds floors, shares them (like Stardew mods)
- Pre-built floors available, but users can **build their own**

## Architecture (Inspired by Paperclip)

Steal the backend brain, keep the Stardew soul:

- **Agent heartbeat protocol** — sprites show real-time status (idle/working/sleeping)
- **Cost tracking** — coin counter in HUD, per-agent token usage
- **Goal decomposition** — building-wide goals broken into floor-level agent tasks
- **Governance** — which agents can act autonomously vs need approval (checkpoints)

## The Pitch

> "AI lets one person do what used to take a team."
> Everyone says that. We gave it a face — literally.
>
> Your AI team lives in a pixel art building. Each floor runs a part of your life.
> You level up by using them. They get smarter by knowing you.
>
> It's Stardew Valley meets the one-person company.

## Relationship to SciSpark

**Not a pivot.** Separate project. But LifeOS validates the thesis that AI orchestration + gamification + domain expertise = a product people actually *want* to use.

---

*Written 2026-03-10. Vision is alive — update as it evolves.*
