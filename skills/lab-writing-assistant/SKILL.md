# lab-writing-assistant

## Description
Drafts paper sections, abstracts, grant aims, and structured notes from your research graph context and writing preferences. Writes in your voice. Produces working drafts — not final prose. The researcher edits and owns the output.

## When to activate
- User says "draft my introduction", "write abstract", "help me write X section", "lab-writing-assistant"
- User wants to generate a first draft from their research graph context

## Usage
```bash
openclaw lab-writing-assistant --project "neural-coupling" --section "introduction"
openclaw lab-writing-assistant --project "neural-coupling" --type "abstract"
openclaw lab-writing-assistant --project "neural-coupling" --type "grant-aim" --aim 1
openclaw lab-writing-assistant --project "neural-coupling" --type "methods"
openclaw lab-writing-assistant --project "neural-coupling" --type "discussion"
openclaw lab-writing-assistant --project "neural-coupling" --type "cover-letter" --journal "Nature Neuroscience"
```

## Flags
- `--project` (required): which project to draft for
- `--section` or `--type`: what to write (introduction / methods / results / discussion / abstract / grant-aim / cover-letter / response-to-reviewers)
- `--aim N` (optional): for grant-aim, which specific aim number
- `--journal` (optional): target journal for style calibration
- `--draft` (optional): path to existing draft to extend/revise rather than start fresh

## Output
- Draft saved to Obsidian at `/Research/Projects/{project}/drafts/{type}-{date}.md`
- Inline citation placeholders linked to Zotero keys
- XP: +200 (first draft per paper section)
