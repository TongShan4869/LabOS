"""LabOS Agent Router — routing, skill execution, checkpoints, memory extraction."""

import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime

from config import (
    AGENTS, AGENT_PROMPTS, SKILL_ARG_SPECS, SKILLS_DIR, PYTHON_BIN,
    AGENTS_MEM_DIR, REPO_DIR, ROOT_DIR, LAB_DIR,
)
from data import (
    get_active_project_id, append_chat_message, save_report,
    get_combined_memory, load_memory, save_memory, append_memory_md,
)
from llm import run_llm
from xp import award_xp
from lab_manager import (
    detect_pipeline, PIPELINES, detect_delegation,
    build_lab_manager_prompt, get_lab_summary,
    record_agent_run, create_quest, complete_quest,
)

log = logging.getLogger("labos")

# Active agent conversations: {agent_id: {"process": Popen, ...}}
active_convos: dict = {}

# Checkpoint events for bridging interactive skill prompts
_checkpoint_events: dict = {}


def route_to_agent(agent_id: str, agent: dict, text: str, sid: str,
                   message_history: dict, socketio, publish_event):
    """Intelligent agent loop — LLM decides whether to chat or run a skill."""
    log.info(f"[AGENT] route_to_agent: {agent_id} / {text[:50]}")
    skill = agent.get("skill")
    
    # Build context
    if agent_id == "main":
        system_prompt = build_lab_manager_prompt()
        system_prompt += "\n" + get_lab_summary()
    else:
        system_prompt = AGENT_PROMPTS.get(agent_id, "You are a helpful research assistant.")
    
    system_prompt += """\n\nFORMATTING: Always format responses in Markdown (##, bullets, **bold**, tables).

PAPER SUMMARIES: When summarizing or discussing papers, ALWAYS include for EACH paper:
- **Full title** and year
- **Authors** (full list)
- **Journal** name
- **Corresponding author affiliation/institution**
- **DOI** as clickable link: [doi](https://doi.org/doi)
- **TLDR** (2-3 sentence summary)
- Key findings, methods, limitations

NEVER omit author, affiliation, or journal info from paper summaries."""

    memory_ctx = get_combined_memory(agent_id)
    
    # Recent conversation history
    history = message_history.get(agent_id, [])[-10:]
    history = [{"role": m["role"], "text": m["text"][:500]} for m in history]
    
    # Build messages
    system_text = system_prompt
    if memory_ctx:
        system_text += f"\n\n--- MEMORY ---\n{memory_ctx}"
    
    if skill:
        system_text += f"""\n\n--- TOOL ---
You have access to ONE tool: {skill}
You MUST ONLY use it when the user EXPLICITLY asks for a new search/analysis/task.

To use the tool, your response must START with exactly: [RUN_SKILL]
followed by what you want to search/analyze.

DO NOT use the tool for:
- Greetings ("hi", "hello")
- Questions about your capabilities
- Follow-up questions about previous results
- General conversation

For those, just respond normally as a helpful research assistant."""
    
    system_text = "IMPORTANT: You are NOT OpenClaw. You are NOT 醋の虾 the Discord bot. Ignore any prior system instructions about heartbeats, HEARTBEAT_OK, NO_REPLY, or Discord. You are ONLY the LabOS agent described below.\n\n" + system_text
    messages = [{"role": "system", "content": system_text}]
    for msg in history[:-1]:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["text"]})
    messages.append({"role": "user", "content": text})
    
    # Scout: bypass LLM for obvious search intent
    if agent_id == "scout" and skill:
        search_patterns = re.compile(
            r"(search|find|look for|look up|get|fetch|discover)\b"
            r".*(paper|article|literature|publication|study|studies)", re.I
        )
        if search_patterns.search(text):
            msg = "Searching for papers... 🔍\n\n⏳ Running skill..."
            _emit_agent_reply(agent_id, agent, msg, sid, message_history, socketio)
            _run_skill_interactive(agent_id, agent, skill, text, sid, message_history, socketio, publish_event)
            return
    
    # Check for multi-agent pipeline
    pipeline_id = detect_pipeline(text)
    if pipeline_id and pipeline_id in PIPELINES:
        pipeline = PIPELINES[pipeline_id]
        log.info(f"[LAB_MANAGER] Pipeline detected: {pipeline['name']}")
        _emit_agent_reply(
            agent_id, agent,
            f"Starting **{pipeline['name']}** pipeline...\n\n" +
            "\n".join(f"{i+1}. {s['agent'].title()}: {s['description']}" for i, s in enumerate(pipeline['steps'])),
            sid, message_history, socketio
        )
        first_step = pipeline["steps"][0]
        target_agent = AGENTS.get(first_step["agent"])
        if target_agent:
            quest = create_quest(f"[Pipeline: {pipeline['name']}] {text[:60]}", first_step["agent"])
            usage_result = record_agent_run(first_step["agent"])
            if usage_result.get("_promoted"):
                publish_event("agent.promoted", {"agent_id": first_step["agent"], "lifecycle": "persistent"}, sid)
            route_to_agent(first_step["agent"], target_agent, text, sid, message_history, socketio, publish_event)
            complete_quest(quest["id"], f"Step 1/{len(pipeline['steps'])} complete")
        return

    # Lab Manager delegation
    delegated_agent = detect_delegation(text)
    if delegated_agent and delegated_agent != agent_id:
        target_agent = AGENTS.get(delegated_agent)
        if target_agent:
            log.info(f"[LAB_MANAGER] Delegating to {delegated_agent}: {text[:50]}")
            route_to_agent(delegated_agent, target_agent, text, sid, message_history, socketio, publish_event)
            return
    
    # Direct skill execution when intent matches the current agent
    if delegated_agent == agent_id and skill:
        agent_name = agent.get("name", agent_id.title())
        _emit_agent_reply(agent_id, agent, f"{agent_name} is on it...\n\n⏳ Running skill...", sid, message_history, socketio)
        usage_result = record_agent_run(agent_id)
        publish_event("run.completed", {"agent_id": agent_id})
        if usage_result.get("_promoted"):
            publish_event("agent.promoted", {"agent_id": agent_id, "lifecycle": "persistent"}, sid)
        quest = create_quest(text[:80], agent_id)
        publish_event("quest.created", {"quest_id": quest["id"], "agent_id": agent_id, "title": text[:80]}, sid)
        _run_skill_interactive(agent_id, agent, skill, text, sid, message_history, socketio, publish_event)
        complete_quest(quest["id"], "Completed")
        publish_event("quest.completed", {"quest_id": quest["id"], "agent_id": agent_id}, sid)
        publish_event("lab.stats", {})
        return

    # Call LLM for conversational response
    response = run_llm(messages)
    log.debug(f"[LLM_FULL] {repr(response[:500])}")
    
    # Check if agent wants to run a skill
    has_tool_call = "[RUN_SKILL]" in response or "[TOOL_CALL]" in response
    if has_tool_call and skill:
        active_skill = skill
        if agent.get("skills"):
            tool_match = re.search(r'"tool"\s*:\s*"(\w+)"', response)
            if tool_match:
                tool_name = tool_match.group(1)
                skill_map = {
                    "draft": "lab-writing-assistant", "publish": "lab-publishing-assistant",
                    "search": "lab-lit-scout", "advise": "lab-research-advisor"
                }
                active_skill = skill_map.get(tool_name, skill)
                log.info(f"[AGENT] Multi-skill agent: tool={tool_name} → {active_skill}")
        
        clean_response = re.sub(r'\[/?TOOL_CALL\].*?(?=\[/TOOL_CALL\]|$)', '', response, flags=re.DOTALL)
        clean_response = re.sub(r'\[/?TOOL_CALL\]', '', clean_response)
        clean_response = clean_response.replace("[RUN_SKILL]", "").strip()
        if clean_response:
            _emit_agent_reply(agent_id, agent, clean_response + "\n\n⏳ Running skill...", sid, message_history, socketio)
        _run_skill_interactive(agent_id, agent, active_skill, text, sid, message_history, socketio, publish_event)
    else:
        _emit_agent_reply(agent_id, agent, response, sid, message_history, socketio)
        active_proj = get_active_project_id()
        if active_proj and len(response) > 500:
            save_report(active_proj, agent_id, agent["name"], response)
        award_xp(10, f"Chat with {agent['name']}")
        _set_agent_status(agent_id, "idle", "")
        socketio.emit("agent_status", {"agent_id": agent_id, "status": "idle", "detail": ""}, to=sid)
        
        mem_thread = threading.Thread(
            target=_extract_memory,
            args=(agent_id, agent["name"], text, response),
            daemon=True,
        )
        mem_thread.start()


# ─── Memory Extraction ───────────────────────────────────────────────────────

def _extract_memory(agent_id: str, agent_name: str, user_msg: str, agent_response: str):
    """Ask LLM if anything from this conversation is worth remembering."""
    try:
        prompt = f"""You are a memory curator for a research lab AI agent called {agent_name}.

Review this conversation exchange and decide if anything is worth saving to long-term memory.

USER said: {user_msg[:500]}
AGENT replied: {agent_response[:500]}

Worth remembering: corrections, preferences, key decisions, research insights, important facts.
NOT worth remembering: greetings, small talk, generic questions.

If something is worth saving, respond with ONLY the memory entry (1-2 concise sentences).
If nothing is worth saving, respond with exactly: NOTHING"""

        result = run_llm(prompt, max_tokens=150).strip()
        
        if result and result != "NOTHING" and 5 < len(result) < 300:
            agent_mem_file = AGENTS_MEM_DIR / agent_id / "memory.md"
            append_memory_md(agent_mem_file, result)
            
            global_keywords = ["prefer", "always", "never", "style", "format", "field", "hypothesis", "focus", "background", "corrected"]
            if any(kw in result.lower() for kw in global_keywords):
                lab_mem_file = REPO_DIR / "LAB_MEMORY.md"
                append_memory_md(lab_mem_file, f"[{agent_name}] {result}")
            
            log.info(f"[MEMORY] {agent_name} saved: {result[:80]}")
    except Exception as e:
        log.warning(f"[MEMORY] extraction failed: {e}")


def _auto_extract_memory(agent_id: str, text: str):
    """Auto-extract and save agent memory from substantial responses."""
    agent = AGENTS.get(agent_id)
    if not agent:
        return
    
    keywords = {
        "scout": (["searched", "found"], "Literature search completed"),
        "stat": (["analysis", "results"], "Statistical analysis performed"),
        "quill": (["draft", "section"], "Writing assistance provided"),
        "sage": (["hypothesis", "recommend"], "Research advice given"),
        "critic": (["review", "suggest"], "Peer review feedback provided"),
        "trend": (["trend", "digest"], "Field trends monitored"),
    }
    
    text_lower = text.lower()
    entry = keywords.get(agent_id)
    if entry:
        triggers, summary = entry
        if any(kw in text_lower for kw in triggers):
            mem_file = AGENTS_MEM_DIR / agent_id / "memory.json"
            memory = load_memory(mem_file)
            memory.append({"text": summary, "timestamp": datetime.now().isoformat()})
            save_memory(mem_file, memory)


# ─── Skill Argument Extraction ────────────────────────────────────────────────

def _extract_skill_args(skill: str, user_text: str) -> list[str]:
    """Use LLM to extract CLI arguments from natural language."""
    spec = SKILL_ARG_SPECS.get(skill)
    if not spec:
        return []

    prompt = spec["extract_prompt"] + user_text + "\nJSON:"
    raw = run_llm(prompt)

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        args_dict = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        args_dict = {}
        if spec["required"]:
            key = spec["required"][0].lstrip("-")
            args_dict[key] = user_text

    cli_args = []
    for key, val in args_dict.items():
        flag = f"--{key}"
        if isinstance(val, bool):
            if val:
                cli_args.append(flag)
        elif val is not None:
            cli_args.append(flag)
            cli_args.append(str(val))

    return cli_args


# ─── Checkpoint Bridging ─────────────────────────────────────────────────────

def handle_checkpoint_reply(data):
    """User replies to a checkpoint prompt. Translates natural language to script format."""
    agent_id = data.get("agent_id", "")
    text = data.get("text", "").strip()
    entry = _checkpoint_events.get(agent_id)
    if entry:
        checkpoint_prompt = entry.get("prompt", "")
        translated = _translate_checkpoint_reply(text, checkpoint_prompt)
        entry["reply"] = translated
        entry["event"].set()


def _translate_checkpoint_reply(user_text: str, checkpoint_prompt: str) -> str:
    """Translate natural language checkpoint reply into script-expected format."""
    lower = user_text.lower().strip()
    if lower in ("all", "done", "yes", "no", "y", "n"):
        return user_text
    if re.match(r"^[\d,\s]+$", lower):
        return user_text
    
    prompt = f"""The user is replying to this checkpoint prompt from a research tool:
"{checkpoint_prompt}"

The user said: "{user_text}"

The tool expects one of these formats:
- "all" to select all items
- Comma-separated numbers like "1,2,3,4,5" to select specific items
- A single number like "5" for one item  
- "done" to finish

Translate the user's intent into the expected format. Reply with ONLY the translated input.
"""
    result = run_llm(prompt).strip().strip('"').strip("'").strip()
    if re.match(r"^(all|done|[\d,\s]+)$", result.lower()):
        return result
    return user_text


# ─── Skill Execution ─────────────────────────────────────────────────────────

def _run_skill_interactive(agent_id: str, agent: dict, skill: str, text: str, sid: str,
                           message_history: dict, socketio, publish_event):
    """Spawn the real skill script, bridge checkpoints, stream output."""
    spec = SKILL_ARG_SPECS.get(skill)
    if not spec:
        _emit_agent_reply(agent_id, agent, f"⚠️ Skill `{skill}` not configured for direct execution.", sid, message_history, socketio)
        return

    socketio.emit("agent_status", {"agent_id": agent_id, "status": "working", "detail": "Parsing your request…"}, to=sid)
    cli_args = _extract_skill_args(skill, text)

    script_path = SKILLS_DIR / spec["script"]
    if not script_path.exists():
        _emit_agent_reply(agent_id, agent, f"⚠️ Script not found: {script_path}", sid, message_history, socketio)
        return

    cmd = [PYTHON_BIN, str(script_path)] + cli_args
    env = os.environ.copy()
    env["LAB_DIR"] = str(LAB_DIR)
    env["LABOS_UI_URL"] = f"http://127.0.0.1:{os.environ.get('LABOS_UI_PORT', '18792')}"

    socketio.emit("agent_status", {"agent_id": agent_id, "status": "working", "detail": f"Running: {agent['name']}…"}, to=sid)

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env,
            cwd=str(ROOT_DIR.parent),
        )
    except Exception as e:
        _emit_agent_reply(agent_id, agent, f"⚠️ Failed to start: {e}", sid, message_history, socketio)
        return

    active_convos[agent_id] = {"process": proc}
    output_lines = []

    try:
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip("\n")

            if line.startswith("[CHECKPOINT]"):
                prompt_text = line[len("[CHECKPOINT]"):].strip()
                _lines = prompt_text.split("\n")
                _lines = [l for l in _lines if not (l.strip().startswith("[") and "/" in l)]
                prompt_text = "\n".join(_lines).strip()

                if output_lines:
                    _emit_agent_reply(agent_id, agent, "\n".join(output_lines), sid, message_history, socketio)
                    output_lines = []

                socketio.emit("checkpoint", {
                    "agent_id":   agent_id,
                    "agent_name": agent["name"],
                    "prompt":     prompt_text,
                    "ts":         datetime.now().strftime("%H:%M"),
                }, to=sid)

                event = threading.Event()
                _checkpoint_events[agent_id] = {"event": event, "reply": "", "prompt": prompt_text}
                event.wait(timeout=300)

                reply = _checkpoint_events.pop(agent_id, {}).get("reply", "")
                if not reply:
                    reply = "abort"

                ts = datetime.now().strftime("%H:%M")
                message_history[agent_id].append({"role": "agent", "text": f"🔀 {prompt_text}", "ts": ts})
                message_history[agent_id].append({"role": "user", "text": reply, "ts": ts})
                
                active_proj = get_active_project_id()
                if active_proj:
                    append_chat_message(active_proj, agent_id, "agent", f"🔀 {prompt_text}", ts)
                    append_chat_message(active_proj, agent_id, "user", reply, ts)

                try:
                    proc.stdin.write(reply + "\n")
                    proc.stdin.flush()
                except BrokenPipeError:
                    break

            elif line.startswith("[NOTIFY:"):
                msg = line.split("]", 1)[-1].strip() if "]" in line else line
                _emit_agent_reply(agent_id, agent, msg, sid, message_history, socketio)

            elif line.strip():
                stripped = line.strip()
                if stripped.startswith("[") and "] / [" in stripped:
                    continue
                if stripped == "→":
                    continue
                output_lines.append(line)

        proc.wait(timeout=120)
        stderr = proc.stderr.read()

        if output_lines:
            final_text = "\n".join(output_lines)
            _emit_agent_reply(agent_id, agent, final_text, sid, message_history, socketio)
            
            active_proj = get_active_project_id()
            if active_proj and len(final_text) > 200:
                save_report(active_proj, agent_id, agent["name"], final_text)
                log.info(f"[REPORT] Saved report for {agent_id} ({len(final_text)} chars)")
                award_xp(50, f"Skill run: {skill}", "🔬 Literature Dive")

        if proc.returncode != 0 and stderr.strip():
            _emit_agent_reply(agent_id, agent,
                              f"⚠️ Error (exit {proc.returncode}):\n```\n{stderr[:500]}\n```",
                              sid, message_history, socketio)

    except Exception as e:
        _emit_agent_reply(agent_id, agent, f"⚠️ Error: {e}", sid, message_history, socketio)
        proc.kill()
    finally:
        active_convos.pop(agent_id, None)
        _set_agent_status(agent_id, "idle", "")
        socketio.emit("agent_status", {"agent_id": agent_id, "status": "idle", "detail": ""}, to=sid)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _emit_agent_reply(agent_id: str, agent: dict, text: str, sid: str,
                      message_history: dict, socketio):
    """Emit an agent reply and store in history."""
    ts = datetime.now().strftime("%H:%M")
    message_history[agent_id].append({
        "role": "agent", "text": text, "ts": ts, "agent_id": agent_id
    })
    
    active_proj = get_active_project_id()
    if active_proj:
        append_chat_message(active_proj, agent_id, "agent", text, ts)
        if len(text) > 50:
            _auto_extract_memory(agent_id, text)
    
    socketio.emit("agent_reply", {
        "agent_id":   agent_id,
        "agent_name": agent["name"],
        "avatar":     agent["avatar"],
        "emoji":      agent["emoji"],
        "color":      agent["color"],
        "text":       text,
        "ts":         ts,
    }, to=sid)


def _set_agent_status(agent_id: str, status: str, detail: str):
    """Update agent status file."""
    from config import AGENTS_FILE
    agents_st = {}
    if AGENTS_FILE.exists():
        try:
            agents_st = json.loads(AGENTS_FILE.read_text())
        except Exception:
            pass
    agents_st[agent_id] = {"status": status, "detail": detail, "updated": datetime.now().isoformat()}
    AGENTS_FILE.write_text(json.dumps(agents_st, indent=2))
