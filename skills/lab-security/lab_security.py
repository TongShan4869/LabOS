#!/usr/bin/env python3
"""
lab-security — Research IP and credential warden for LabOS
Modes: audit, check, classify, preflight
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, CheckpointAborted,
    find_project, update_node, upsert_node,
    now_iso, today_str, LAB_DIR,
)

# ── Lab UI state bridge (optional, silent if UI not running) ──────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "lab-ui"))
    from lab_state import AgentWorking, working, idle as idle_state, error as error_state
    _UI = True
except ImportError:
    class AgentWorking:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def update(self, *a): pass
        def __exit__(self, *a): return False
    def working(*a, **kw): pass
    def idle_state(*a): pass
    def error_state(*a): pass
    _UI = False


SENSITIVITY_LEVELS = ["public", "internal", "sensitive", "confidential"]

# Patterns that indicate exposed secrets
SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"github_pat_[A-Za-z0-9_]{82}", "GitHub fine-grained PAT"),
    (r"xoxb-[A-Za-z0-9\-]+", "Slack bot token"),
    (r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}", "SendGrid key"),
    (r"AKIA[A-Z0-9]{16}", "AWS access key"),
    (r"['\"]password['\"]:\s*['\"][^'\"]{6,}['\"]", "Hardcoded password"),
    (r"['\"]api_key['\"]:\s*['\"][^'\"]{8,}['\"]", "Hardcoded API key"),
    (r"Bearer\s+[A-Za-z0-9\-_\.]{20,}", "Bearer token"),
]

# HIPAA / sensitive data signals
HIPAA_PATTERNS = [
    r"\bSSN\b", r"\bsocial.?security\b", r"\bdate.?of.?birth\b", r"\bDOB\b",
    r"\bmedical.?record\b", r"\bMRN\b", r"\bdiagnosis\b", r"\bpatient.?id\b",
    r"\bPHI\b", r"\bHIPAA\b",
]


def scan_file_for_secrets(path: Path) -> list[dict]:
    findings = []
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return []
    for pattern, label in SECRET_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            findings.append({
                "file": str(path),
                "label": label,
                "match": match.group()[:40] + "…" if len(match.group()) > 40 else match.group(),
                "line": text[:match.start()].count("\n") + 1,
            })
    return findings


def scan_file_for_hipaa(path: Path) -> bool:
    try:
        text = path.read_text(errors="ignore").lower()
    except Exception:
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in HIPAA_PATTERNS)


def classify_content(text: str) -> str:
    """Heuristic classification of content sensitivity."""
    text_lower = text.lower()
    if any(re.search(p, text_lower) for p in HIPAA_PATTERNS):
        return "confidential"
    if any(w in text_lower for w in ["unpublished", "preliminary", "embargo", "patent pending", "novel finding"]):
        return "sensitive"
    if any(w in text_lower for w in ["draft", "in progress", "internal", "not for distribution"]):
        return "internal"
    return "public"


# ─── Mode: audit ──────────────────────────────────────────────────────────────

def mode_audit(config: dict):
    section_header("🔒 Lab Security Audit")
    issues   = []
    warnings = []

    # 1. Scan LAB_CONFIG.json for exposed credentials
    progress("Scanning LAB_CONFIG.json for exposed credentials…", "🔑")
    config_path = LAB_DIR / "LAB_CONFIG.json"
    if config_path.exists():
        findings = scan_file_for_secrets(config_path)
        for f in findings:
            issues.append(f"❌ Exposed secret in LAB_CONFIG.json line {f['line']}: {f['label']} — {f['match']}")
    else:
        warnings.append("⚠️  LAB_CONFIG.json not found.")

    # 2. Scan workspace for secrets
    progress("Scanning workspace files for secrets…", "🔍")
    scan_dirs = [LAB_DIR]
    vault = config.get("obsidian_vault")
    if vault:
        scan_dirs.append(Path(vault) / "Research")

    found_secrets = []
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for ext in ["*.json", "*.md", "*.py", "*.env", "*.yaml", "*.yml", "*.toml"]:
            for f in scan_dir.rglob(ext):
                results = scan_file_for_secrets(f)
                found_secrets.extend(results)

    for f in found_secrets[:10]:  # cap output
        issues.append(f"❌ Secret in {Path(f['file']).name} line {f['line']}: {f['label']}")
    if len(found_secrets) > 10:
        issues.append(f"   … and {len(found_secrets)-10} more secrets found")

    # 3. Scan for HIPAA signals in research files
    progress("Checking for HIPAA-sensitive content…", "🏥")
    hipaa_files = []
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*.md"):
            if scan_file_for_hipaa(f):
                hipaa_files.append(f)

    if hipaa_files:
        warnings.append(f"⚠️  {len(hipaa_files)} file(s) may contain HIPAA-sensitive content:")
        for f in hipaa_files[:5]:
            warnings.append(f"   • {f.name}")

    # 4. Research graph integrity
    progress("Checking research graph integrity…", "🗂️")
    graph_file = LAB_DIR / "research-graph.jsonl"
    if graph_file.exists():
        try:
            lines = graph_file.read_text().splitlines()
            bad   = sum(1 for l in lines if l.strip() and not _valid_json(l))
            if bad:
                warnings.append(f"⚠️  research-graph.jsonl has {bad} malformed line(s).")
            else:
                print(f"   ✅ research-graph.jsonl: {len(lines)} nodes, all valid JSON")
        except Exception as e:
            warnings.append(f"⚠️  Could not read research-graph.jsonl: {e}")
    else:
        warnings.append("⚠️  research-graph.jsonl not found.")

    # 5. XP/session file permissions
    progress("Checking file permissions…", "🔐")
    sensitive_files = [LAB_DIR / "LAB_CONFIG.json", LAB_DIR / "LAB_MEMORY.md"]
    for sf in sensitive_files:
        if sf.exists():
            mode = oct(sf.stat().st_mode)[-3:]
            if mode[2] != "0":  # world-readable
                warnings.append(f"⚠️  {sf.name} is world-readable (permissions: {mode}). Run: chmod 600 {sf}")

    # ── Summary ──
    print("\n" + "═"*60)
    print("  🔒 Security Audit Report")
    print("═"*60)
    if issues:
        print(f"\n❌ **{len(issues)} issue(s) found:**")
        for i in issues:
            print(f"   {i}")
    if warnings:
        print(f"\n⚠️  **{len(warnings)} warning(s):**")
        for w in warnings:
            print(f"   {w}")
    if not issues and not warnings:
        print("\n✅ No issues found. Lab security looks good.")
    else:
        print("\n📋 **Recommended actions:**")
        if found_secrets:
            print("   1. Move secrets to environment variables or a secrets manager")
            print("   2. Rotate any exposed keys immediately")
        if hipaa_files:
            print("   3. Classify HIPAA-sensitive projects as 'confidential' using --classify")
            print("   4. Ensure participant data is de-identified before LLM use")

    return {"issues": issues, "warnings": warnings}


def _valid_json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except Exception:
        return False


# ─── Mode: check ──────────────────────────────────────────────────────────────

def mode_check(path: str) -> dict:
    section_header(f"🔍 Security Check — {Path(path).name}")

    p = Path(path)
    if not p.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    text       = p.read_text(errors="ignore")
    secrets    = scan_file_for_secrets(p)
    hipaa      = scan_file_for_hipaa(p)
    level      = classify_content(text)
    word_count = len(text.split())

    print(f"\n📄 File: {p.name} ({word_count} words)")
    print(f"🏷️  Detected sensitivity: [{level.upper()}]")

    if secrets:
        print(f"\n❌ {len(secrets)} potential secret(s) found:")
        for s in secrets:
            print(f"   • Line {s['line']}: {s['label']} — {s['match']}")
    else:
        print("✅ No credentials detected")

    if hipaa:
        print("⚠️  HIPAA-sensitive content detected — classify as CONFIDENTIAL before sharing")
    else:
        print("✅ No HIPAA signals detected")

    # LLM leakage risk
    if level in ("sensitive", "confidential"):
        print(f"\n🚨 HIGH RISK: This file is [{level.upper()}]")
        print("   Do NOT send this content to external LLM APIs without review.")
        print("   Use a local model or redact sensitive sections first.")
    elif level == "internal":
        print(f"\n⚠️  MODERATE: This file is [INTERNAL] — review before external sharing")
    else:
        print(f"\n✅ LOW RISK: This file appears [PUBLIC] — safe for LLM use")

    return {"path": path, "level": level, "secrets": len(secrets), "hipaa": hipaa}


# ─── Mode: classify ───────────────────────────────────────────────────────────

def mode_classify(project_name: str, level: str, nodes: list) -> list:
    section_header(f"🏷️  Classify Project — {project_name}")

    from lab_utils import find_project
    project = find_project(nodes, project_name)
    if not project:
        print(f"❌ Project '{project_name}' not found in research graph.")
        sys.exit(1)

    if level not in SENSITIVITY_LEVELS:
        print(f"❌ Invalid level '{level}'. Choose: {', '.join(SENSITIVITY_LEVELS)}")
        sys.exit(1)

    props        = project.get("properties", project)
    current      = props.get("sensitivity", "internal")
    project_id   = project.get("id","")
    project_label = props.get("name", project_id)

    print(f"\n   Current: [{current.upper()}] → New: [{level.upper()}]")

    if level == "confidential" and current != "confidential":
        print("   ⚠️  CONFIDENTIAL mode enables:")
        print("     • Pre-flight check before ALL external LLM calls")
        print("     • HIPAA scanning on all files")
        print("     • Access logging for all skill interactions")
        try:
            if not confirm("Proceed with CONFIDENTIAL classification?", default=False):
                print("Aborted.")
                sys.exit(0)
        except CheckpointAborted:
            sys.exit(0)

    nodes = update_node(nodes, project_id, {"sensitivity": level, "classified_at": now_iso()})
    print(f"\n✅ Project '{project_label}' classified as [{level.upper()}]")

    if level in ("sensitive", "confidential"):
        print("   All lab skills will now run a security pre-flight before sending data to LLMs.")

    return nodes


# ─── Mode: preflight ──────────────────────────────────────────────────────────

def mode_preflight(content: str, project_name: str, nodes: list) -> bool:
    """
    Silent pre-flight check. Returns True if safe to proceed, False if blocked.
    Called automatically by other skills before external LLM calls.
    """
    from lab_utils import find_project
    project = find_project(nodes, project_name) if project_name else None
    level   = "internal"
    if project:
        props = project.get("properties", project)
        level = props.get("sensitivity", "internal")

    secrets = []
    # Quick in-memory secret scan
    for pattern, label in SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            secrets.append(label)

    hipaa = any(re.search(p, content, re.IGNORECASE) for p in HIPAA_PATTERNS)

    if secrets:
        print(f"🚨 [SECURITY PREFLIGHT] Potential secrets detected: {', '.join(secrets)}")
        print("   Content not sent to LLM. Remove secrets and retry.")
        return False

    if level == "confidential":
        print(f"🔒 [SECURITY PREFLIGHT] Project is CONFIDENTIAL.")
        try:
            go = confirm("Send this content to external LLM API?", default=False)
            return go
        except CheckpointAborted:
            return False

    if level == "sensitive" and hipaa:
        print("⚠️  [SECURITY PREFLIGHT] HIPAA content detected in SENSITIVE project.")
        try:
            go = confirm("Proceed? (consider redacting participant data first)", default=False)
            return go
        except CheckpointAborted:
            return False

    return True  # safe


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LabOS Security Warden")
    parser.add_argument("--mode", "-m",
                        choices=["audit", "check", "classify", "preflight"],
                        default="audit")
    parser.add_argument("--check",   "-c", help="File path to check (for check mode)")
    parser.add_argument("--project", "-p", help="Project name (for classify/preflight)")
    parser.add_argument("--level",   "-l", choices=SENSITIVITY_LEVELS,
                        help="Sensitivity level (for classify mode)")
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    if args.mode == "audit":
        result = mode_audit(config)
        log_session("lab-security", "global",
                    f"Audit: {len(result['issues'])} issues, {len(result['warnings'])} warnings")
        award_xp(30, None)

    elif args.mode == "check":
        target = args.check
        if not target:
            try:
                target = checkpoint("File path to check?", emoji="📄")
            except CheckpointAborted:
                sys.exit(0)
        result = mode_check(target)
        log_session("lab-security", "global", f"Check: {target} → {result['level']}")
        award_xp(10, None)

    elif args.mode == "classify":
        if not args.project:
            try:
                args.project = checkpoint("Project name to classify?", emoji="🏷️")
            except CheckpointAborted:
                sys.exit(0)
        if not args.level:
            try:
                args.level = checkpoint(
                    "Sensitivity level?",
                    options=SENSITIVITY_LEVELS,
                    allow_freetext=False,
                    emoji="🏷️",
                )
            except CheckpointAborted:
                sys.exit(0)
        nodes = mode_classify(args.project, args.level, nodes)
        save_graph(nodes)
        award_xp(20, "🔒 Security Conscious")

    elif args.mode == "preflight":
        content = sys.stdin.read() if not sys.stdin.isatty() else ""
        if not content:
            try:
                path = checkpoint("File to pre-flight check?", emoji="✈️")
                content = Path(path).read_text(errors="ignore")
            except CheckpointAborted:
                sys.exit(0)
        safe = mode_preflight(content, args.project or "", nodes)
        sys.exit(0 if safe else 1)

    print("\n✅ Done.\n")


if __name__ == "__main__":
    with AgentWorking("warden", "Running security checks..."):
        main()
