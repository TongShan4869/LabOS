# LabOS UI 🔬

Stardew Valley-style pixel lab dashboard for LabOS.

## Features
- Pixel lab top-down view with agent characters at their stations
- Click any agent → Stardew-style dialogue box slides up with portrait
- Typewriter text animation, full conversation history
- Real-time agent status (working/idle/error) via WebSocket
- XP bar + level display in HUD
- `lab_state.py` bridge — all LabOS skills push their status live

## Run

```bash
cd lab-ui
pip install -r backend/requirements.txt
python3 backend/app.py
# → open http://127.0.0.1:18792
```

## Agents in the lab

| Character | Skill | Zone |
|---|---|---|
| 🦞 醋の虾 | Main PI | PI Desk |
| 🔬 Scout | lab-lit-scout | Bookshelf |
| 📊 Stat | lab-biostat | Analysis Bench |
| ✍️ Quill | lab-writing-assistant | Writing Desk |
| 🎓 Sage | lab-research-advisor | Advisor Chair |
| 🤺 Critic | lab-peer-reviewer | Review Table |
| 📰 Trend | lab-field-trend | News Board |
| 🔒 Warden | lab-security | Security Console |

## Asset replacement

Put pixel art sprites in `frontend/assets/avatars/`:
- `avatar-main.png`, `avatar-scout.png`, `avatar-stat.png` etc.
- 110×110px recommended, pixel art style
- Placeholder: emoji avatars used when files not found

## State bridge

In any LabOS skill:

```python
from lab_ui.lab_state import AgentWorking

with AgentWorking("lab-lit-scout", "Searching PubMed..."):
    results = search_pubmed(query)
# → agent auto-returns to idle when done
```
