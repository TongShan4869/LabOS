# lab-security — Execution Script

## Mode: `--audit` (full security audit)

### Check 1: Credential exposure
```bash
# Scan LAB_CONFIG.json for plaintext secrets
grep -E "(api_key|token|secret|password|key)" ~/.openclaw/workspace/lab/LAB_CONFIG.json
```
- Any secrets stored in plaintext → WARN: "Move to environment variable or ~/.openclaw/.env.lab"
- Check `.env.lab` is in `.gitignore` if vault is git-synced

### Check 2: Obsidian vault git exposure
```bash
cd "{obsidian_vault}" && git remote -v 2>/dev/null
```
- If public remote detected → WARN: "Your Obsidian vault syncs to a remote. Ensure sensitive research files are excluded via .gitignore"
- Check `.gitignore` for `confidential/` and `sensitive/` folders

### Check 3: Research graph integrity
```bash
# Check file hasn't been unexpectedly modified
stat ~/.openclaw/workspace/lab/research-graph.jsonl
```
- Compare last-modified timestamp to last known good timestamp in audit log
- If modified outside of lab-* skills → WARN: "research-graph.jsonl modified by unknown process"

### Check 4: Sensitive project inventory
Scan research-graph.jsonl for all projects. List their sensitivity levels:
```
Project: neural-coupling → sensitivity: sensitive ✅
Project: infant-hearing → sensitivity: NOT SET ⚠️ (recommend: confidential — involves human subjects)
```
- Projects with "participant", "patient", "subject", "human" in description but no sensitivity set → auto-flag for `confidential`

### Check 5: Session log scan
Check recent session logs for accidental credential leakage:
```bash
grep -r "api_key\|token\|password" ~/.openclaw/workspace/lab/sessions/
```

### Output audit report:
```markdown
# LabOS Security Audit — {date}

## ✅ Passed
- No plaintext credentials in LAB_CONFIG.json
- research-graph.jsonl integrity OK

## ⚠️ Warnings
- Project "infant-hearing" has no sensitivity level set. Recommend: confidential (human subjects detected)
- Obsidian vault synced to GitHub — verify .gitignore covers sensitive folders

## ❌ Critical
- (none)

## Recommendations
1. Run: openclaw lab-security --classify --project "infant-hearing" --level confidential
2. Add Research/Projects/*/confidential/ to vault .gitignore
```

---

## Mode: `--check <file>` (pre-sharing check)

Read the file. Scan for:
- Participant IDs (patterns: P001, Sub-01, patient name patterns)
- Unpublished data markers (phrases: "preliminary", "not yet published", "in preparation")
- Links to confidential project nodes in research graph
- API keys or credentials accidentally included

Output:
```
🔒 Security check: {filename}

Content classification: SENSITIVE
Reason: Contains reference to "infant-hearing" project (confidential) + phrase "preliminary data"

⚠️ Recommend: Do not send to external API or share externally without review.
If you must proceed: strip participant references and mark as anonymized first.

Proceed anyway? (yes/no)
```

---

## Mode: `--classify --project X --level Y`

Update research-graph.jsonl project node:
```jsonl
{"op":"update","id":"proj_X","fields":{"sensitivity":"confidential","classified_by":"lab-security","classified_date":"<ISO>"}}
```

Confirm to user:
```
✅ Project "infant-hearing" classified as: confidential
All lab-* skills will now require confirmation before sending content from this project to external APIs.
```

---

## Mode: `--preflight --skill X` (called automatically by other skills)

Quick check before any skill sends content externally:

1. Identify which project(s) the content belongs to
2. Check sensitivity level of each
3. If any are `sensitive` or `confidential`:
   - Prompt user for confirmation
   - Log the external call: which skill, which project, what data type, timestamp
4. If `public` or `internal`: proceed silently

Pre-flight log entry (always, regardless of level):
```jsonl
{"type":"ExternalCall","skill":"{skill}","project":"{proj}","sensitivity":"{level}","approved":true,"timestamp":"<ISO>"}
```

---

## Automatic triggers

### On lab-init:
- Run Check 1 (credentials) and Check 4 (project sensitivity inventory)

### Weekly (cron alongside lab-field-trend):
- Run full audit
- Send brief summary to notify channel if any warnings found

### Before every external API call from any lab-* skill:
- Run preflight check silently
- Only interrupt user if sensitivity is `sensitive` or `confidential`
