#!/usr/bin/env python3
"""
lab-init — LabOS onboarding CLI
Usage:
  lab-init                        # full interactive onboarding
  lab-init --add-project          # add a new project to existing lab
  lab-init --update-prefs         # update preferences only
  lab-init --status               # show current lab config
  lab-init --reset                # full reset (with confirmation)
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE = Path(os.environ.get("LABOS_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
LAB_DIR = WORKSPACE / "LabOS"
LAB_CONFIG = LAB_DIR / "LAB_CONFIG.json"
LAB_MEMORY = LAB_DIR / "LAB_MEMORY.md"
RESEARCH_GRAPH = LAB_DIR / "research-graph.jsonl"
XP_FILE = LAB_DIR / "xp.json"
SESSIONS_DIR = LAB_DIR / "sessions"

GAMIFICATION_DIR = LAB_DIR / "gamification"
XP_ENGINE = GAMIFICATION_DIR / "xp_engine.py"

LEVELS = [
    (0,    "Rookie",       "🧪"),
    (300,  "Apprentice",   "🔬"),
    (800,  "Researcher",   "📊"),
    (1800, "Senior Res.",  "📝"),
    (3500, "Lead Sci.",    "🏆"),
    (6000, "Lab Director", "🎓"),
]

def level_from_xp(xp):
    level, title, badge = 1, "Rookie", "🧪"
    for i, (threshold, t, b) in enumerate(LEVELS):
        if xp >= threshold:
            level, title, badge = i + 1, t, b
    return level, title, badge

NOW = datetime.now(timezone.utc).isoformat()

# ── Helpers ────────────────────────────────────────────────────────────────────
def bold(s): return f"\033[1m{s}\033[0m"
def green(s): return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s): return f"\033[31m{s}\033[0m"
def cyan(s): return f"\033[36m{s}\033[0m"

def ask(prompt, default=None, choices=None):
    hint = ""
    if default:
        hint += f" [{default}]"
    if choices:
        hint += f" ({'/'.join(choices)})"
    while True:
        raw = input(f"{cyan('?')} {prompt}{hint}: ").strip()
        if not raw and default is not None:
            return default
        if choices and raw.lower() not in [c.lower() for c in choices]:
            print(f"  {red('Choose one of:')} {', '.join(choices)}")
            continue
        if raw:
            return raw
        print(f"  {red('Required field.')}")

def ask_list(prompt, default=None):
    hint = f" [{default}]" if default else " (comma-separated)"
    raw = input(f"{cyan('?')} {prompt}{hint}: ").strip()
    if not raw and default:
        raw = default
    return [x.strip() for x in raw.split(",") if x.strip()]

def confirm(prompt, default="y"):
    ans = input(f"{cyan('?')} {prompt} [{'Y/n' if default=='y' else 'y/N'}]: ").strip().lower()
    if not ans:
        return default == "y"
    return ans in ("y", "yes")

def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

def slugify(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def award_xp(event, points):
    """Call the XP engine to award XP."""
    if XP_ENGINE.exists():
        try:
            subprocess.run(
                [sys.executable, str(XP_ENGINE), "--event", event, "--xp", str(points)],
                check=True, capture_output=True
            )
        except Exception:
            # Fallback: update xp.json directly
            _award_xp_direct(event, points)
    else:
        _award_xp_direct(event, points)

def _award_xp_direct(event, points):
    data = load_json(XP_FILE) or {"user": "unknown", "xp": 0, "badges": [], "history": []}
    data["xp"] = data.get("xp", 0) + points
    xp = data["xp"]
    level, title, badge = level_from_xp(xp)
    xp_to_next = next((t for t, _, _ in LEVELS if t > xp), xp)
    data.update({"level": level, "level_title": title, "xp_to_next": xp_to_next})
    data.setdefault("history", []).append({
        "event": event, "xp": points, "timestamp": NOW
    })
    save_json(XP_FILE, data)

# ── Init flow ──────────────────────────────────────────────────────────────────
def collect_identity():
    print(f"\n{bold('── Identity ────────────────────────────────')}")
    name = ask("Your name (for personalization)", default="Researcher")
    stage = ask("Career stage", default="postdoc",
                choices=["undergrad", "masters", "phd", "postdoc", "faculty", "independent"])
    fields = ask_list("Primary research field(s)", default="neuroscience, machine learning")
    disciplines = ask_list("Disciplines spanned", default="biomedical, computational")
    return name, stage, fields, disciplines

def create_obsidian_vault(vault_path):
    """Create a new Obsidian vault directory with a .obsidian stub."""
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)
    (vault / ".obsidian").mkdir(exist_ok=True)
    # Minimal app.json so Obsidian recognises it as a vault
    (vault / ".obsidian" / "app.json").write_text("{}")
    print(f"  {green('✓')} New Obsidian vault created at {vault_path}")
    print(f"  {dim('→ Open Obsidian → \"Open folder as vault\" → select this folder')}")
    return vault_path

def collect_tools():
    print(f"\n{bold('── Knowledge Store ─────────────────────────')}")
    print("LabOS can save paper summaries, digests, and project notes to Obsidian or Notion.")
    print()

    obsidian = None
    notion_db = None

    store_choice = ask(
        "Where should LabOS store your research notes?",
        default="1",
        choices=["1", "2", "3"]
    )
    print("  1 = Obsidian (recommended — local, Markdown, free)")
    print("  2 = Notion")
    print("  3 = Skip for now")
    store_choice = ask("Choice", default="1", choices=["1", "2", "3"])

    if store_choice == "1":
        print()
        vault_action = ask(
            "Obsidian vault",
            default="1",
            choices=["1", "2"]
        )
        print("  1 = Create a new vault for LabOS")
        print("  2 = Use an existing vault")
        vault_action = ask("Choice", default="1", choices=["1", "2"])

        if vault_action == "1":
            default_path = str(Path.home() / "LabOS-Vault")
            raw = ask("Where to create the new vault?", default=default_path)
            obsidian = create_obsidian_vault(raw or default_path)
        else:
            raw = ask("Path to your existing Obsidian vault", default=str(Path.home() / "obsidian-vault"))
            obsidian = raw if raw else None
            if obsidian and not Path(obsidian).exists():
                print(f"  {yellow('⚠')}  Path does not exist — will try to create it during setup")

    elif store_choice == "2":
        print()
        print(f"  {cyan('Notion setup:')}")
        print("  1. Go to notion.so → create a new page called 'LabOS Research'")
        print("  2. Add a Database (table) called 'Papers'")
        print("  3. Share → Copy link → paste the database ID (32-char hex after last /)")
        print()
        notion_db = ask("Notion database ID (or Enter to skip)", default="")
        if not notion_db:
            notion_db = None
            print(f"  {yellow('⚠')}  Notion not connected — you can add it later via --update-prefs")
        else:
            print(f"  {green('✓')} Notion DB ID saved")

    else:
        print(f"  {yellow('ℹ')}  No knowledge store set — digests will print to terminal only")
        print("  You can connect one later with: python3 lab_init.py --update-prefs")

    print(f"\n{bold('── Reference Manager ───────────────────────')}")
    zotero_type = None
    zotero_lib = None
    if confirm("Do you use Zotero?", default="n"):
        zotero_type = ask("Zotero type", default="web", choices=["local", "web"])
        if zotero_type == "web":
            zotero_lib = ask("Zotero library ID", default="")
            if not zotero_lib:
                zotero_lib = None

    print(f"\n{bold('── Literature Databases ─────────────────────')}")
    print("LabOS searches these for your weekly field digests and literature reviews.")
    dbs_input = ask_list(
        "Which databases? (pubmed, openalex, arxiv, semanticscholar, biorxiv)",
        default="pubmed, openalex, arxiv"
    )
    valid_dbs = {"pubmed", "openalex", "arxiv", "semanticscholar", "biorxiv"}
    databases = [d.lower() for d in dbs_input if d.lower() in valid_dbs] or ["pubmed", "openalex", "arxiv"]

    return obsidian, notion_db, zotero_type, zotero_lib, databases

def collect_prefs():
    print(f"\n{bold('── Preferences ─────────────────────────────')}")
    writing_style = ask(
        "Writing style",
        default="concise, methods-forward, active voice"
    )
    citation = ask("Citation format", default="APA",
                   choices=["APA", "APA7", "Vancouver", "Nature", "Chicago", "MLA"])
    summary = ask("Paper summary style", default="bullet",
                  choices=["bullet", "paragraph", "detailed"])
    batch = ask("Papers per batch to review", default="5")
    try:
        batch = int(batch)
    except ValueError:
        batch = 5

    return writing_style, citation, summary, batch

def collect_notifications():
    print(f"\n{bold('── Notifications ───────────────────────────')}")
    channel = ask("Weekly digest channel", default="discord",
                  choices=["discord", "slack", "none"])
    trend_day = ask("Weekly trend digest day", default="Monday",
                    choices=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
    trend_time = ask("Delivery time (HH:MM)", default="08:00")
    return channel, trend_day, trend_time

def collect_first_project():
    print(f"\n{bold('── First Project (optional) ────────────────')}")
    if not confirm("Set up your first research project now?", default="y"):
        return None
    name = ask("Project name", default="My Research Project")
    desc = ask("One-line description")
    hyp = ask("Main hypothesis (or press Enter to skip)", default="")
    status = ask("Current status", default="active",
                 choices=["idea", "active", "writing", "submitted", "published"])
    return {"name": name, "description": desc, "hypothesis": hyp, "status": status}

def write_lab_config(cfg):
    save_json(LAB_CONFIG, cfg)
    print(f"  {green('✓')} LAB_CONFIG.json")

def write_lab_memory(cfg, project=None):
    project_lines = ""
    if project:
        project_lines = f"- **{project['name']}:** {project['description']} — Status: {project['status']}\n"
    else:
        project_lines = "(none yet — add with: `python3 lab_init.py --add-project`)\n"

    content = f"""# Lab Memory — {cfg['user']}

> Auto-generated by lab-init. Updated after each research session.

## Research Identity
- **Name:** {cfg['user']}
- **Career stage:** {cfg['career_stage']}
- **Primary fields:** {', '.join(cfg['fields'])}
- **Disciplines:** {', '.join(cfg['disciplines'])}
- **Methods comfort:** (to be learned)
- **Known weak spots:** (to be learned)

## Tools Connected
- **Knowledge store:** {cfg['knowledge_store']} @ {cfg.get('obsidian_vault') or 'not set'}
- **Notion DB:** {cfg.get('notion_research_db') or 'not connected'}
- **Zotero:** {cfg.get('zotero_type') or 'not connected'}
- **Databases:** {', '.join(cfg['databases'])}

## Preferences
- **Summary style:** {cfg['summary_style']}
- **Papers per batch:** {cfg['papers_per_batch']}
- **Writing voice:** {cfg['writing_style']}
- **Citation format:** {cfg['citation_format']}
- **Feedback intensity:** hard (default)

## Active Projects
{project_lines}
## Interaction Patterns
- Working hours: (to be learned)
- Common blind spots: (to be learned)
- Notes: (to be learned)

## Last Updated
{NOW[:10]} by lab-init
"""
    LAB_MEMORY.parent.mkdir(parents=True, exist_ok=True)
    LAB_MEMORY.write_text(content)
    print(f"  {green('✓')} LAB_MEMORY.md")

def write_research_graph(cfg, project=None):
    RESEARCH_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    # Reset or create fresh
    with open(RESEARCH_GRAPH, "w") as f:
        f.write(json.dumps({
            "type": "Meta", "schema_version": "0.1",
            "created": NOW, "owner": cfg["user"]
        }) + "\n")
    if project:
        slug = slugify(project["name"])
        hyps = [project["hypothesis"]] if project.get("hypothesis") else []
        append_jsonl(RESEARCH_GRAPH, {
            "type": "Project",
            "id": f"proj_{slug}",
            "name": project["name"],
            "description": project["description"],
            "status": project["status"],
            "hypotheses": hyps,
            "experiments": [],
            "drafts": [],
            "created": NOW,
            "updated": NOW
        })
    print(f"  {green('✓')} research-graph.jsonl")

def write_xp(cfg):
    data = {
        "user": cfg["user"],
        "level": 1,
        "level_title": "Rookie",
        "xp": 100,
        "xp_to_next": 300,
        "badges": ["🧪 Lab Open"],
        "history": [{"event": "Lab initialized", "xp": 100, "timestamp": NOW}]
    }
    save_json(XP_FILE, data)
    print(f"  {green('✓')} xp.json (Level 1 — Rookie 🧪, 100 XP)")

def setup_obsidian(vault_path, project=None):
    vault = Path(vault_path)
    if not vault.exists():
        print(f"  {yellow('⚠')}  Obsidian vault not found at {vault_path} — skipping folder creation")
        return False

    folders = [
        vault / "Research" / "Projects",
        vault / "Research" / "Literature",
        vault / "Research" / "Methods",
        vault / "Research" / "Weekly-Digests",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    readme = vault / "Research" / "README.md"
    readme.write_text("""# Research Vault

Managed by LabOS.

## Folder Structure
- **Projects/** — one folder per research project (notes, hypotheses, drafts)
- **Literature/** — paper summaries and annotations from lab-lit
- **Methods/** — protocol notes, stats tips, code snippets
- **Weekly-Digests/** — field trend digests from lab-trends
""")

    if project:
        slug = slugify(project["name"])
        proj_dir = vault / "Research" / "Projects" / slug
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "hypotheses.md").write_text(
            f"# Hypotheses — {project['name']}\n\n"
            + (f"- {project['hypothesis']}\n" if project.get("hypothesis") else "")
        )
        (proj_dir / "notes.md").write_text(
            f"# Notes — {project['name']}\n\n{project.get('description', '')}\n"
        )
        (proj_dir / "drafts").mkdir(exist_ok=True)
        print(f"  {green('✓')} Obsidian project folder: Research/Projects/{slug}/")

    print(f"  {green('✓')} Obsidian vault scaffolded at {vault_path}")
    return True

def register_cron(cfg):
    day_map = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
               "Friday": 5, "Saturday": 6, "Sunday": 0}
    day_num = day_map.get(cfg.get("weekly_trend_day", "Monday"), 1)
    time_str = cfg.get("weekly_trend_time", "08:00")
    hour, minute = time_str.split(":")

    cron_expr = f"{minute} {hour} * * {day_num}"
    try:
        result = subprocess.run(
            ["openclaw", "cron", "add",
             "--name", "lab-trends-weekly",
             "--schedule", cron_expr,
             "--skill", "lab-trends"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"  {green('✓')} Weekly trend digest cron: {cfg['weekly_trend_day']}s at {time_str}")
        else:
            raise Exception(result.stderr)
    except Exception as e:
        print(f"  {yellow('⚠')}  Cron registration failed ({e}). Add manually:")
        print(f"      openclaw cron add --name lab-trends-weekly --schedule '{cron_expr}' --skill lab-trends")

def check_security(cfg):
    issues = []
    # Check for API keys in config (shouldn't be there)
    cfg_str = json.dumps(cfg)
    if any(kw in cfg_str.lower() for kw in ["api_key", "token", "secret", "password"]):
        issues.append("API keys detected in LAB_CONFIG.json — move to environment variables")
    # Check if obsidian vault is in a git repo synced to public
    vault = cfg.get("obsidian_vault")
    if vault:
        git_check = subprocess.run(
            ["git", "-C", vault, "remote", "get-url", "origin"],
            capture_output=True, text=True
        )
        if "github.com" in git_check.stdout.lower() and "private" not in git_check.stdout.lower():
            issues.append("Obsidian vault may be synced to a public GitHub repo — verify it's private")

    if issues:
        print(f"\n  {yellow('Security notes:')}")
        for i in issues:
            print(f"    {yellow('⚠')}  {i}")
    else:
        print(f"  {green('✓')} Security baseline OK")

def print_summary(cfg, project=None, obsidian_ok=True):
    xp_data = load_json(XP_FILE) or {}
    xp = xp_data.get("xp", 100)
    level = xp_data.get("level", 1)
    title = xp_data.get("level_title", "Rookie")

    proj_line = f"\n📁 First project: {project['name']}" if project else ""

    print(f"""
{bold(green('✅ LabOS initialized!'))}

👤 User:    {cfg['user']} ({cfg['career_stage']})
🔬 Fields:  {', '.join(cfg['fields'])}
📚 Vault:   {'Obsidian @ ' + cfg['obsidian_vault'] if obsidian_ok and cfg.get('obsidian_vault') else yellow('not connected')}
🗃️  Zotero:  {cfg.get('zotero_type') or yellow('not set')}
📊 DBs:     {', '.join(cfg['databases'])}{proj_line}

📁 Files:
   {LAB_CONFIG}
   {LAB_MEMORY}
   {RESEARCH_GRAPH}
   {XP_FILE}

🏆 XP: {xp} | Level {level} — {title}

📅 Weekly trends: {cfg['weekly_trend_day']}s at {cfg['weekly_trend_time']} → {cfg['notify_channel']}

{bold("You're ready. Try:")}
   python3 {LAB_DIR}/skills/lab-trends/lab_trends.py
   python3 {LAB_DIR}/skills/lab-lit/lab_lit.py --query "your topic"
   python3 {LAB_DIR}/skills/lab-init/lab_init.py --add-project
""")

# ── Shared project writer ──────────────────────────────────────────────────────
def _write_project(cfg, project):
    """Write a project to research-graph, LAB_MEMORY, and Obsidian. Shared by all paths."""
    slug = slugify(project["name"])
    hyps = [project["hypothesis"]] if project.get("hypothesis") else []

    append_jsonl(RESEARCH_GRAPH, {
        "type": "Project",
        "id": f"proj_{slug}",
        "name": project["name"],
        "description": project["description"],
        "status": project["status"],
        "hypotheses": hyps,
        "experiments": [],
        "drafts": [],
        "created": NOW,
        "updated": NOW
    })
    print(f"  {green('✓')} Added to research-graph.jsonl")

    # Update LAB_MEMORY.md
    if LAB_MEMORY.exists():
        memory = LAB_MEMORY.read_text()
        new_entry = f"- **{project['name']}:** {project['description']} — Status: {project['status']}\n"
        memory = memory.replace(
            "(none yet — add with: `python3 lab_init.py --add-project`)\n", ""
        )
        memory = memory.replace("## Active Projects\n", f"## Active Projects\n{new_entry}")
        LAB_MEMORY.write_text(memory)
        print(f"  {green('✓')} Updated LAB_MEMORY.md")

    # Obsidian folder
    if cfg.get("obsidian_vault"):
        vault = Path(cfg["obsidian_vault"])
        if vault.exists():
            proj_dir = vault / "Research" / "Projects" / slug
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "hypotheses.md").write_text(
                f"# Hypotheses — {project['name']}\n\n"
                + (f"- {project['hypothesis']}\n" if project.get("hypothesis") else "")
            )
            (proj_dir / "notes.md").write_text(
                f"# Notes — {project['name']}\n\n{project['description']}\n"
            )
            (proj_dir / "drafts").mkdir(exist_ok=True)
            print(f"  {green('✓')} Obsidian folder: Research/Projects/{slug}/")


# ── --add-project ──────────────────────────────────────────────────────────────
def cmd_add_project():
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print(red("❌ No LAB_CONFIG.json found. Run lab-init first."))
        sys.exit(1)

    print(f"\n{bold('── Add New Project ─────────────────────────')}")
    project = collect_first_project()
    if not project:
        print("Cancelled.")
        return

    _write_project(cfg, project)
    award_xp("new_project_added", 50)
    print(f"\n{green('✅')} Project '{project['name']}' added! +50 XP 🏆")

# ── --update-prefs ─────────────────────────────────────────────────────────────
def cmd_update_prefs():
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print(red("❌ No LAB_CONFIG.json found. Run lab-init first."))
        sys.exit(1)
    print(f"\n{bold('── Update Preferences ──────────────────────')}")
    writing_style, citation, summary, batch = collect_prefs()
    channel, trend_day, trend_time = collect_notifications()
    cfg.update({
        "writing_style": writing_style,
        "citation_format": citation,
        "summary_style": summary,
        "papers_per_batch": batch,
        "notify_channel": channel,
        "weekly_trend_day": trend_day,
        "weekly_trend_time": trend_time,
    })
    save_json(LAB_CONFIG, cfg)
    print(f"\n{green('✅')} Preferences updated.")

# ── --status ───────────────────────────────────────────────────────────────────
def cmd_status():
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print(red("❌ No lab found. Run lab-init to get started."))
        sys.exit(1)

    xp_data = load_json(XP_FILE) or {}
    xp = xp_data.get("xp", 0)
    level = xp_data.get("level", 1)
    title = xp_data.get("level_title", "Rookie")
    badges = " ".join(xp_data.get("badges", []))

    # Count projects
    n_projects = 0
    if RESEARCH_GRAPH.exists():
        with open(RESEARCH_GRAPH) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("type") == "Project":
                        n_projects += 1
                except Exception:
                    pass

    print(f"""
{bold('LabOS Status')}

👤 {cfg['user']} ({cfg['career_stage']})
🔬 {', '.join(cfg['fields'])}
🏆 Level {level} — {title} | XP: {xp} | {badges}

📁 Projects: {n_projects}
📚 Vault: {cfg.get('obsidian_vault') or yellow('not set')}
📊 Databases: {', '.join(cfg['databases'])}
📅 Weekly digest: {cfg['weekly_trend_day']}s at {cfg['weekly_trend_time']}

Config: {LAB_CONFIG}
Memory: {LAB_MEMORY}
""")

# ── --reset ────────────────────────────────────────────────────────────────────
def cmd_reset():
    print(red(bold("⚠️  This will delete ALL LabOS data (config, memory, projects, XP).")))
    if not confirm("Are you sure you want to full reset?", default="n"):
        print("Cancelled.")
        return
    for f in [LAB_CONFIG, LAB_MEMORY, RESEARCH_GRAPH, XP_FILE]:
        if f.exists():
            f.unlink()
            print(f"  {yellow('✗')} Deleted {f.name}")
    print(f"\n{yellow('Lab reset. Run lab-init to start fresh.')}")

# ── Full onboarding ────────────────────────────────────────────────────────────
def cmd_init():
    existing = load_json(LAB_CONFIG)
    if existing:
        print(f"\n{bold('LabOS is already set up for')} {existing.get('user', '?')}.")
        action = ask("What do you want to do?", default="1",
                     choices=["1", "2", "3"])
        print("  1 = Add new project  2 = Update preferences  3 = Full reset")
        action = ask("Choice", default="1", choices=["1", "2", "3"])
        if action == "1":
            cmd_add_project()
        elif action == "2":
            cmd_update_prefs()
        elif action == "3":
            cmd_reset()
        return

    print(f"\n{bold(cyan('Welcome to LabOS 🧪'))}")
    print("I'll set up your virtual lab. This takes about 2 minutes.\n")

    # Collect
    name, stage, fields, disciplines = collect_identity()
    obsidian, notion_db, zotero_type, zotero_lib, databases = collect_tools()
    writing_style, citation, summary, batch = collect_prefs()
    channel, trend_day, trend_time = collect_notifications()
    project = collect_first_project()

    # Build config
    cfg = {
        "user": name,
        "career_stage": stage,
        "fields": fields,
        "disciplines": disciplines,
        "knowledge_store": "obsidian" if obsidian else "none",
        "obsidian_vault": obsidian,
        "notion_research_db": notion_db,
        "zotero_type": zotero_type,
        "zotero_library_id": zotero_lib,
        "databases": databases,
        "writing_style": writing_style,
        "citation_format": citation,
        "summary_style": summary,
        "papers_per_batch": batch,
        "weekly_trend_day": trend_day,
        "weekly_trend_time": trend_time,
        "notify_channel": channel,
        "labos_version": "0.1",
        "created": NOW
    }

    # Write files
    print(f"\n{bold('── Creating files ──────────────────────────')}")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    write_lab_config(cfg)
    write_lab_memory(cfg, project)
    write_research_graph(cfg, project)
    write_xp(cfg)

    # Obsidian
    obsidian_ok = False
    if obsidian:
        obsidian_ok = setup_obsidian(obsidian, project)

    # Cron
    if channel != "none":
        register_cron(cfg)

    # Security
    print(f"\n{bold('── Security baseline ───────────────────────')}")
    check_security(cfg)

    # Summary
    print_summary(cfg, project, obsidian_ok)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="LabOS — virtual research lab setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--add-project", action="store_true", help="Add a new project")
    parser.add_argument("--update-prefs", action="store_true", help="Update preferences")
    parser.add_argument("--status", action="store_true", help="Show lab status")
    parser.add_argument("--reset", action="store_true", help="Full reset")

    # Non-interactive flags for AI-mediated project creation
    parser.add_argument("--name",       type=str, help="Project name (non-interactive)")
    parser.add_argument("--desc",       type=str, help="Project description (non-interactive)")
    parser.add_argument("--hypothesis", type=str, default="", help="Main hypothesis (optional)")
    parser.add_argument("--proj-status",type=str, default="active",
                        choices=["idea","active","writing","submitted","published"],
                        help="Project status (default: active)")

    args = parser.parse_args()

    # Non-interactive project creation (AI calls this with pre-filled args)
    if args.name and args.desc:
        cfg = load_json(LAB_CONFIG)
        if not cfg:
            print("❌ No LAB_CONFIG.json found. Run lab-init first.")
            sys.exit(1)
        project = {
            "name": args.name,
            "description": args.desc,
            "hypothesis": args.hypothesis,
            "status": args.proj_status
        }
        _write_project(cfg, project)
        award_xp("new_project_added", 50)
        print(f"✅ Project '{args.name}' added! +50 XP")
    elif args.add_project:
        cmd_add_project()
    elif args.update_prefs:
        cmd_update_prefs()
    elif args.status:
        cmd_status()
    elif args.reset:
        cmd_reset()
    else:
        cmd_init()

if __name__ == "__main__":
    main()
