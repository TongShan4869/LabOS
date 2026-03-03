#!/usr/bin/env python3
"""
LabOS → Star Office UI state bridge.
Called by lab-* skills to push their current state to the pixel office dashboard.

Usage:
    python3 lab_state_bridge.py <skill> <state> "<detail>"

States:
    idle / researching / writing / executing / syncing / error
"""

import json, datetime, subprocess, os, sys

STAR_OFFICE_DIR = os.path.expanduser("~/.openclaw/workspace/LabOS/star-office-ui")
STATE_FILE = os.path.join(STAR_OFFICE_DIR, "state.json")

# Map lab-* skill + action → Star Office state + zone hint
SKILL_STATE_MAP = {
    "lab-field-trend":          {"state": "researching", "zone": "bookshelf"},
    "lab-lit-scout":            {"state": "researching", "zone": "bookshelf"},
    "lab-research-advisor":     {"state": "writing",     "zone": "advisor_chair"},
    "lab-writing-assistant":    {"state": "writing",     "zone": "desk"},
    "lab-peer-reviewer":        {"state": "executing",   "zone": "desk"},
    "lab-publishing-assistant": {"state": "syncing",     "zone": "desk"},
    "lab-biostat":              {"state": "executing",   "zone": "bench"},
    "lab-security":             {"state": "syncing",     "zone": "server"},
    "lab-init":                 {"state": "writing",     "zone": "desk"},
}

LAB_ZONE_LABELS = {
    "bookshelf":    "📚 Library — searching literature",
    "advisor_chair":"🎓 Advisor Chair — Socratic session",
    "desk":         "🖊️ Desk — writing/reviewing",
    "bench":        "🔬 Bench — running analysis",
    "server":       "🔒 Server Room — security check",
}

def push_state(skill, state_override=None, detail=""):
    mapping = SKILL_STATE_MAP.get(skill, {"state": "idle", "zone": "lounge"})
    state = state_override or mapping["state"]
    zone = mapping["zone"]
    zone_label = LAB_ZONE_LABELS.get(zone, "")
    
    full_detail = f"[{skill}] {detail}" if detail else f"[{skill}] {zone_label}"
    
    state_data = {
        "state": state,
        "detail": full_detail,
        "progress": 0,
        "updated_at": datetime.datetime.now().isoformat(),
        "skill": skill,
        "zone": zone
    }
    
    # Write to state.json
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f, indent=2)
    
    # Try calling set_state.py if Star Office backend is running
    set_state_script = os.path.join(STAR_OFFICE_DIR, "set_state.py")
    if os.path.exists(set_state_script):
        try:
            subprocess.run(
                ["python3", set_state_script, state, full_detail],
                capture_output=True, timeout=3, cwd=STAR_OFFICE_DIR
            )
        except Exception:
            pass  # Star Office not running, state file updated anyway
    
    print(f"[Star Office] {skill} → {state}: {full_detail}")
    return state_data

def idle(skill=""):
    return push_state(skill or "lab", "idle", "Standing by...")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        skill = sys.argv[1]
        state = sys.argv[2]
        detail = sys.argv[3] if len(sys.argv) > 3 else ""
        push_state(skill, state, detail)
    elif len(sys.argv) == 2 and sys.argv[1] == "idle":
        idle()
    else:
        print("Usage: lab_state_bridge.py <skill> <state> [detail]")
        print("       lab_state_bridge.py idle")
