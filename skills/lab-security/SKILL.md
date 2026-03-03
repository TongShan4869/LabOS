# lab-security

## Description
Quiet lab warden. Protects research IP, API credentials, and sensitive data. Runs automatically on init, weekly, and as a pre-flight check before any skill sends data to an external LLM or API. Auditable on demand.

## When to activate
- Automatically: on lab-init, weekly cron, pre-flight before external API calls
- User says "security audit", "lab-security", "check my lab security", "classify project"
- Any skill is about to send sensitive content externally

## Usage
```bash
openclaw lab-security --audit                                         # full audit
openclaw lab-security --check "path/to/draft.md"                     # check before sharing
openclaw lab-security --classify --project "infant-hearing" --level confidential
openclaw lab-security --preflight --skill lab-writing-assistant       # pre-flight check
```

## Sensitivity levels
- `public`: safe to share anywhere (published papers, public methods)
- `internal`: lab-only (working notes, in-progress analysis)
- `sensitive`: pre-publication IP (unpublished hypotheses, novel results)
- `confidential`: human subjects / grant-restricted (participant data, NIH-restricted)

## Output
- Audit report saved to `~/.openclaw/workspace/lab/sessions/security-audit-{date}.md`
- Pre-flight: inline warning or block before external call
- Classification: updates project node in research-graph.jsonl
