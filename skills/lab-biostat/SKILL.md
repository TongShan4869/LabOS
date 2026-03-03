# lab-biostat

## Description
A biostatistician-in-residence. Advises on study design, runs statistical analysis via Python or R, interprets results in plain English, flags methodological issues, and teaches as it goes. Always shows its work — which test, why, what assumptions were checked. Never a black box.

## When to activate
- User says "run stats", "analyze my data", "power analysis", "study design", "lab-biostat"
- User needs statistical advice at any stage of research
- User wants to check a methods section for statistical validity

## Usage
```bash
openclaw lab-biostat --mode "design" --project "infant-hearing"
openclaw lab-biostat --mode "analyze" --data "path/to/data.csv" --question "Is there a group difference in ABR latency?"
openclaw lab-biostat --mode "interpret" --results "path/to/results.md" --project "neural-coupling"
openclaw lab-biostat --mode "power" --effect-size 0.5 --alpha 0.05 --power 0.8
openclaw lab-biostat --mode "review-methods" --draft "path/to/methods.md"
openclaw lab-biostat --mode "assumption-check" --data "path/to/data.csv" --test "t-test"
```

## Modes
- `design`: study design advice — sample size, controls, confounds
- `analyze`: run statistical tests, generate figures
- `interpret`: explain results in plain English, flag over-interpretation
- `power`: power analysis — is your N sufficient?
- `review-methods`: audit a methods section for statistical validity
- `assumption-check`: check test assumptions before running parametric tests

## Prerequisites
- Python 3 with scipy, statsmodels, pingouin, matplotlib (for `analyze` mode)
- Or R with common packages (alternative backend)
- Data files in CSV/TSV format for `analyze` mode

## Output
- Analysis results + figures saved to Obsidian project folder
- Results linked to hypothesis nodes in research graph (supported/not supported/inconclusive)
- XP: +150
