#!/usr/bin/env python3
"""
lab_state.py — State bridge between LabOS skills and the UI

Import this in any LabOS skill to push live status to the frontend:

    from lab_state import push_state, working, idle

Usage:
    working("scout", "Searching PubMed for speech-music coupling...")
    # ... do work ...
    idle("scout")
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

UI_URL = os.environ.get("LABOS_UI_URL", "http://127.0.0.1:18792")

AGENT_MAP = {
    "lab-lit-scout":             "scout",
    "lab-biostat":               "stat",
    "lab-writing-assistant":     "quill",
    "lab-research-advisor":      "sage",
    "lab-peer-reviewer":         "critic",
    "lab-field-trend":           "trend",
    "lab-security":              "warden",
    "lab-publishing-assistant":  "quill",  # shares desk
    "main":                      "main",
}

# State names recognized by the UI
STATES = {
    "idle":        "idle",
    "working":     "working",
    "researching": "researching",
    "executing":   "executing",
    "writing":     "writing",
    "analyzing":   "analyzing",
    "error":       "error",
}


def push_state(agent_id: str, status: str, detail: str = "", progress: int = 0) -> bool:
    """
    Push agent state to the LabOS UI backend via HTTP POST.
    Returns True on success, False if UI is not running (silent fail).
    """
    payload = json.dumps({
        "agent_id": agent_id,
        "status":   status,
        "detail":   detail,
        "progress": progress,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{UI_URL}/api/push_state",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False  # UI not running — silent fail, don't break the skill


def working(skill_or_agent: str, detail: str = "", progress: int = 0) -> bool:
    """Mark an agent as working."""
    agent_id = AGENT_MAP.get(skill_or_agent, skill_or_agent)
    return push_state(agent_id, "working", detail, progress)


def idle(skill_or_agent: str) -> bool:
    """Mark an agent as idle."""
    agent_id = AGENT_MAP.get(skill_or_agent, skill_or_agent)
    return push_state(agent_id, "idle", "")


def error(skill_or_agent: str, detail: str = "") -> bool:
    """Mark an agent as errored."""
    agent_id = AGENT_MAP.get(skill_or_agent, skill_or_agent)
    return push_state(agent_id, "error", detail)


# ── Context manager for clean state transitions ────────────────────────────────

class AgentWorking:
    """
    Context manager: marks agent working on entry, idle on exit.

    Usage:
        with AgentWorking("scout", "Searching PubMed..."):
            results = search_pubmed(query)
    """
    def __init__(self, skill_or_agent: str, detail: str = "", progress: int = 0):
        self.agent_id = AGENT_MAP.get(skill_or_agent, skill_or_agent)
        self.detail   = detail
        self.progress = progress

    def __enter__(self):
        push_state(self.agent_id, "working", self.detail, self.progress)
        return self

    def update(self, detail: str, progress: int = 0):
        push_state(self.agent_id, "working", detail, progress)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            push_state(self.agent_id, "error", str(exc_val)[:80] if exc_val else "Error")
        else:
            push_state(self.agent_id, "idle", "")
        return False  # don't suppress exceptions


if __name__ == "__main__":
    import sys
    # CLI usage: python3 lab_state.py scout working "Searching PubMed..."
    args = sys.argv[1:]
    if len(args) >= 2:
        ok = push_state(
            agent_id=AGENT_MAP.get(args[0], args[0]),
            status=args[1],
            detail=args[2] if len(args) > 2 else "",
        )
        print("✅ State pushed" if ok else "⚠️  UI not running (state not pushed)")
    else:
        print("Usage: python3 lab_state.py <agent_id> <status> [detail]")
        print(f"Agent IDs: {', '.join(AGENT_MAP.values())}")
        print(f"Statuses: {', '.join(STATES.keys())}")
