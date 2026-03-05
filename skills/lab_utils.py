"""
lab_utils.py — Shared utilities for all LabOS skills

Provides:
- Config / graph / memory I/O
- checkpoint()       — pause, ask user, wait for reply
- interactive_loop() — post-output revision cycle
- notify()           — send message to configured channel
- progress()         — formatted progress output
- XP helpers
- Graph CRUD helpers
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─── Paths ────────────────────────────────────────────────────────────────────

LAB_DIR = Path(os.environ.get("LAB_DIR", Path.home() / ".openclaw/workspace/lab"))
CONFIG_FILE  = LAB_DIR / "LAB_CONFIG.json"
MEMORY_FILE  = LAB_DIR / "LAB_MEMORY.md"
GRAPH_FILE   = LAB_DIR / "research-graph.jsonl"
XP_FILE      = LAB_DIR / "xp.json"
SESSIONS_DIR = LAB_DIR / "sessions"


# ─── I/O helpers ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        _die("LAB_CONFIG.json not found. Run lab-init first.")
    return json.loads(CONFIG_FILE.read_text())


def load_memory() -> str:
    return MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""


def save_memory(content: str):
    MEMORY_FILE.write_text(content)


def load_graph() -> list[dict]:
    if not GRAPH_FILE.exists():
        return []
    nodes = []
    for line in GRAPH_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                nodes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return nodes


def save_graph(nodes: list[dict]):
    GRAPH_FILE.write_text("\n".join(json.dumps(n) for n in nodes) + "\n")


def append_graph_node(node: dict):
    with open(GRAPH_FILE, "a") as f:
        f.write(json.dumps(node) + "\n")


def load_xp() -> dict:
    if XP_FILE.exists():
        return json.loads(XP_FILE.read_text())
    return {"xp": 0, "level": 1, "badges": []}


def save_xp(data: dict):
    XP_FILE.write_text(json.dumps(data, indent=2))


# ─── Time helpers ─────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def days_since(iso_str: str) -> int | None:
    try:
        then = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - then).days
    except Exception:
        return None


def short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:8]


# ─── Output helpers ───────────────────────────────────────────────────────────

def progress(msg: str, emoji: str = "⏳"):
    """Print a progress update (always shown, not a checkpoint)."""
    print(f"\n{emoji} {msg}", flush=True)


def section_header(title: str, width: int = 60):
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def _die(msg: str):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


# ─── Notification ─────────────────────────────────────────────────────────────

def notify(message: str, config: dict | None = None):
    """
    Send a notification via the configured notify channel.

    In OpenClaw subagent context, stdout IS the channel —
    OpenClaw routes it to Discord automatically.
    A [NOTIFY:channel] prefix lets OpenClaw route to the right destination.
    In standalone terminal context, it just prints.
    """
    cfg = config or {}
    channel = cfg.get("notify_channel", "discord")
    print(f"[NOTIFY:{channel}] {message}", flush=True)


# ─── Checkpoint ───────────────────────────────────────────────────────────────

class CheckpointAborted(Exception):
    """Raised when user aborts at a checkpoint."""
    pass


def checkpoint(
    question: str,
    options: list[str] | None = None,
    default: str | None = None,
    allow_freetext: bool = True,
    emoji: str = "🔀",
) -> str:
    """
    Pause execution and ask the user a question.

    In OpenClaw subagent context: prints a [CHECKPOINT] marker that OpenClaw
    intercepts, posts to the user's channel (Discord etc.), and feeds the reply
    back via stdin.

    In standalone terminal context: behaves as a regular input() prompt.

    Returns the user's response (stripped string).
    Raises CheckpointAborted if user types 'abort', 'cancel', 'stop', or 'exit'.

    Args:
        question:       The question to ask.
        options:        If provided, list of valid shorthand choices (e.g. ["1","2","3","all"]).
                        Free text is still accepted unless allow_freetext=False.
        default:        Default answer if user just hits enter.
        allow_freetext: If False and options provided, loop until valid option given.
        emoji:          Leading emoji for the prompt.
    """
    ABORT_WORDS = {"abort", "cancel", "stop", "exit", "quit"}

    # Format the prompt
    prompt_lines = [f"{emoji} {question}"]
    if options:
        opts_str = " / ".join(f"[{o}]" for o in options)
        if default:
            opts_str += f"  (default: {default})"
        prompt_lines.append(f"   {opts_str}")
    elif default:
        prompt_lines.append(f"   (default: {default} — press Enter to confirm)")

    prompt_text = "\n".join(prompt_lines)

    # [CHECKPOINT] marker — OpenClaw intercepts this and routes to user's channel
    print(f"\n[CHECKPOINT] {prompt_text}", flush=True)

    while True:
        try:
            raw = input("→ ").strip()
        except EOFError:
            # Non-interactive (piped input) — use default or abort
            if default is not None:
                print(f"  (using default: {default})")
                return default
            raise CheckpointAborted("Non-interactive context, no default provided.")

        if not raw and default is not None:
            return default

        if raw.lower() in ABORT_WORDS:
            raise CheckpointAborted(f"User aborted at checkpoint: '{question}'")

        if options and not allow_freetext:
            if raw.lower() not in [o.lower() for o in options]:
                print(f"  Please choose one of: {', '.join(options)}")
                continue

        return raw


def confirm(question: str, default: bool = True) -> bool:
    """Yes/no checkpoint. Returns True for yes, False for no."""
    default_str = "yes" if default else "no"
    try:
        answer = checkpoint(
            question, options=["yes", "no"], default=default_str,
            allow_freetext=False, emoji="❓"
        )
        return answer.lower() in ("yes", "y")
    except CheckpointAborted:
        return False


# ─── Interactive loop ─────────────────────────────────────────────────────────

def interactive_loop(
    content: str,
    content_type: str,
    save_fn=None,
    config: dict | None = None,
) -> str:
    """
    Post-output interactive revision loop.

    After a skill generates content (draft, analysis, summary, etc.),
    this loop lets the user request revisions before the result is finalized.

    Args:
        content:      The generated content string.
        content_type: Human label (e.g. "introduction draft", "analysis results").
        save_fn:      Optional callable(content) → path — saves and returns path.
        config:       LAB_CONFIG dict (for LLM model preference).

    Returns the final (possibly revised) content string.
    """
    EXIT_WORDS = {"done", "looks good", "save", "finish", "exit", "ok", "okay",
                  "ship it", "lgtm", "good", "perfect", "yes"}

    print(f"\n[INTERACTIVE] Your {content_type} is ready.")
    print("  • Type a revision instruction  e.g. 'make the intro shorter'")
    print("  • Type 'show'                  to reprint the content")
    print("  • Type 'done' / 'looks good'   to finalize\n")

    cfg = config or {}
    llm_model = cfg.get("llm_model", None)

    while True:
        try:
            cmd = checkpoint(
                f"Any revisions to the {content_type}?",
                default="done",
                emoji="✏️",
            )
        except CheckpointAborted:
            break

        if cmd.lower() in EXIT_WORDS:
            break

        if cmd.lower() == "show":
            print("\n" + "─" * 60)
            print(content)
            print("─" * 60)
            continue

        # Treat as revision instruction
        progress(f"Applying: '{cmd}'", "🔄")
        revision_prompt = (
            f"Revise the following {content_type} based on this instruction:\n"
            f"Instruction: {cmd}\n\n"
            f"Current content:\n---\n{content}\n---\n\n"
            f"Return only the revised content, no commentary."
        )
        revised = call_llm(revision_prompt, llm_model)
        if revised.strip():
            content = revised
            print("\n" + "─" * 60)
            print(content)
            print("─" * 60)
            print("✅ Revision applied.")
        else:
            print("⚠️  Revision returned empty — keeping original.")

    if save_fn:
        path = save_fn(content)
        print(f"\n💾 Saved: {path}")

    return content


# ─── LLM call ─────────────────────────────────────────────────────────────────

def call_llm(prompt: str, model: str | None = None) -> str:
    """
    Call the LLM via claude CLI. Falls back to manual paste if unavailable.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    if model:
        cmd += ["--model", model]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: manual paste
    print("\n" + "─" * 60)
    print("📋 No LLM CLI found. Paste this prompt into your AI tool:\n")
    print(prompt)
    print("─" * 60)
    print("Paste the response below (end with a line containing only '---END---'):")
    lines = []
    while True:
        line = input()
        if line.strip() == "---END---":
            break
        lines.append(line)
    return "\n".join(lines)


# ─── XP ───────────────────────────────────────────────────────────────────────

def award_xp(amount: int, badge: str | None = None) -> dict:
    """Award XP and optionally a one-time badge. Returns updated xp_data."""
    xp_data = load_xp()
    xp_data["xp"] = xp_data.get("xp", 0) + amount
    if badge and badge not in xp_data.get("badges", []):
        xp_data.setdefault("badges", []).append(badge)
        print(f"🏅 Badge unlocked: {badge}")
    save_xp(xp_data)
    print(f"✨ +{amount} XP  (total: {xp_data['xp']})")
    return xp_data


# ─── Graph helpers ─────────────────────────────────────────────────────────────

def find_nodes(nodes: list[dict], node_type: str, **filters) -> list[dict]:
    """Filter graph nodes by type and optional property key=value pairs."""
    results = []
    for n in nodes:
        if n.get("type") != node_type:
            continue
        props = n.get("properties", n)
        match = all(
            str(props.get(k, n.get(k, ""))).lower() == str(v).lower()
            for k, v in filters.items()
        )
        if match:
            results.append(n)
    return results


def find_project(nodes: list[dict], name: str) -> dict | None:
    """Case-insensitive project name search."""
    for n in nodes:
        if n.get("type") == "Project":
            props = n.get("properties", n)
            if name.lower() in props.get("name", "").lower():
                return n
    return None


def get_project_papers(nodes: list[dict], project_id: str) -> list[dict]:
    return [n for n in nodes if n.get("type") == "Paper"
            and project_id in n.get("projects", [])]


def get_project_hypotheses(nodes: list[dict], project_id: str) -> list[dict]:
    return [n for n in nodes if n.get("type") == "Hypothesis"
            and n.get("project_id") == project_id]


def get_project_experiments(nodes: list[dict], project_id: str) -> list[dict]:
    return [n for n in nodes if n.get("type") == "Experiment"
            and n.get("project_id") == project_id]


def update_node(nodes: list[dict], node_id: str, updates: dict) -> list[dict]:
    """Update properties of a node by ID in-place. Returns the list."""
    for n in nodes:
        if n.get("id") == node_id:
            if "properties" in n:
                n["properties"].update(updates)
            else:
                n.update(updates)
    return nodes


def upsert_node(nodes: list[dict], node: dict) -> list[dict]:
    """Insert node if ID not present, else update it."""
    node_id = node.get("id")
    if any(n.get("id") == node_id for n in nodes):
        return update_node(nodes, node_id, node.get("properties", node))
    nodes.append(node)
    return nodes


# ─── Session logging ──────────────────────────────────────────────────────────

def log_session(skill_name: str, project_name: str, content: str) -> Path:
    """Append a timestamped entry to the daily session log."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    fname = SESSIONS_DIR / f"{today_str()}-{skill_name}.md"
    ts = datetime.now().strftime("%H:%M")
    entry = f"\n## {project_name} — {ts}\n\n{content}\n"
    with open(fname, "a") as f:
        f.write(entry)
    return fname
