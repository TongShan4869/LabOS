# lab-publishing-assistant

## Description
Helps researchers choose the right journal or conference and prepares the manuscript for submission — restructuring sections, formatting references, checking figures, and drafting a cover letter. Knows the differences between journal families (Nature, PLOS, Elsevier, conference proceedings). Flags predatory journals.

## When to activate
- User says "find a journal for my paper", "where should I submit", "format my manuscript", "submission checklist", "lab-publishing-assistant"
- User is ready to submit and needs submission prep

## Usage
```bash
openclaw lab-publishing-assistant --mode "find-journal" --project "neural-coupling"
openclaw lab-publishing-assistant --mode "reformat" --draft "path/to/draft.md" --target "Nature Neuroscience"
openclaw lab-publishing-assistant --mode "checklist" --draft "path/to/draft.md" --target "Journal of Neuroscience"
openclaw lab-publishing-assistant --mode "references" --draft "path/to/draft.md" --target "PLOS ONE"
openclaw lab-publishing-assistant --mode "figure-spec" --project "neural-coupling" --target "NeuroImage"
openclaw lab-publishing-assistant --mode "cover-letter" --project "neural-coupling" --target "Nature Neuroscience"
```

## Modes
- `find-journal`: ranked journal/conference shortlist with trade-offs
- `reformat`: restructure manuscript to match journal requirements
- `checklist`: pre-submission checklist
- `references`: reformat citations to journal style
- `figure-spec`: check/list figure requirements
- `cover-letter`: draft a tailored cover letter

## Output
- Journal recommendation saved to Obsidian project folder
- Reformatted manuscript in submission-ready folder
- XP: +300 (on first submission prep)
