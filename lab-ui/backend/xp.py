"""LabOS XP & Leveling System."""

import json
import logging
import threading
from datetime import datetime

from config import XP_FILE, LEVEL_TITLES

log = logging.getLogger("labos")

_xp_lock = threading.Lock()


def calc_level(xp: int) -> tuple:
    """Calculate level from total XP. Returns (level, title, xp_needed_for_level, cumulative_xp_at_level_start)."""
    level = 1
    cumulative = 0
    while True:
        needed = level * 150
        if cumulative + needed > xp:
            return level, LEVEL_TITLES.get(level, f"Level {level}"), needed, cumulative
        cumulative += needed
        level += 1


def award_xp(amount: int, event: str, badge: str = None):
    """Award XP from the backend (for agent interactions). Thread-safe."""
    with _xp_lock:
        try:
            data = json.loads(XP_FILE.read_text()) if XP_FILE.exists() else {"xp": 0, "badges": [], "history": []}
            data["xp"] = data.get("xp", 0) + amount
            if badge and badge not in data.get("badges", []):
                data.setdefault("badges", []).append(badge)
            data.setdefault("history", []).append({
                "event": event,
                "xp": amount,
                "timestamp": datetime.now().isoformat()
            })
            level, title, xp_next, _ = calc_level(data["xp"])
            data["level"] = level
            data["level_title"] = title
            data["xp_to_next"] = xp_next
            XP_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"XP award failed: {e}")


def load_xp() -> dict:
    """Load and recalculate XP data."""
    data = {"xp": 0, "level": 1, "level_title": "Confused First-Year", "badges": []}
    if XP_FILE.exists():
        try:
            data = json.loads(XP_FILE.read_text())
        except Exception:
            pass
    level, title, xp_next, xp_cumulative = calc_level(data.get("xp", 0))
    data["level"] = level
    data["level_title"] = title
    data["xp_to_next"] = xp_next
    data["xp_in_level"] = data.get("xp", 0) - xp_cumulative
    data["levels"] = {str(k): v for k, v in LEVEL_TITLES.items()}
    return data
