# lab-biostat — Execution Script

## Mode: `design`

### Step 1: Load project context
From research-graph.jsonl: hypothesis, expected groups/conditions, outcome measures, field.

### Step 2: Ask design questions conversationally
- "What is your research question? (Be specific: comparing groups? measuring change over time? finding associations?)"
- "What is your outcome variable? Is it continuous, ordinal, or categorical?"
- "How many groups or conditions are you comparing?"
- "Do you have any within-subject measurements (repeated measures)?"
- "What's your expected effect size? (small/medium/large, or Cohen's d if known)"
- "What are your key potential confounders?"

### Step 3: Recommend design

```
📐 Study Design Recommendation — {project}

**Recommended design:** {e.g., 2x2 mixed factorial ANOVA, randomized controlled trial, repeated measures}

**Why:** {rationale in 2-3 sentences}

**Sample size (power analysis):**
- Effect size: {d or η²}
- α = 0.05, power = 0.80
- Required N per group: {n}
- Total N: {total}

**Controls to include:**
- {control 1}: {why}
- {control 2}: {why}

**Key confounders to address:**
- {confounder}: {how to handle — exclude, match, covariate}

**Analysis plan:**
- Primary: {test} for {main hypothesis}
- Secondary: {test} for {secondary hypothesis}
- Corrections: {Bonferroni/FDR if multiple comparisons}

⚠️ Watch out for: {common pitfall for this design}
```

---

## Mode: `analyze`

### Step 1: Load data
```python
import pandas as pd
df = pd.read_csv("{data_path}")
print(df.head())
print(df.describe())
print(df.dtypes)
```

### Step 2: Understand the question
Parse `--question` to determine:
- Comparison type: group difference / correlation / time series / predictive
- Variables involved
- Number of groups

### Step 3: Check assumptions first
Before running any parametric test:

```python
# Normality (Shapiro-Wilk for n<50, D'Agostino for larger)
from scipy import stats
import pingouin as pg

for group in df[group_col].unique():
    data = df[df[group_col]==group][outcome_col]
    stat, p = stats.shapiro(data)
    print(f"{group}: W={stat:.3f}, p={p:.3f} {'✅ Normal' if p>0.05 else '⚠️ Non-normal'}")

# Homogeneity of variance (Levene's test)
stat, p = stats.levene(*[df[df[group_col]==g][outcome_col] for g in df[group_col].unique()])
print(f"Levene's: F={stat:.3f}, p={p:.3f} {'✅ Equal variances' if p>0.05 else '⚠️ Unequal variances'}")
```

If assumptions violated: recommend non-parametric alternative. Explain why.

### Step 4: Run appropriate test

**Test selection logic:**
```
2 groups, continuous outcome:
  → normal + equal var: independent t-test
  → normal + unequal var: Welch's t-test
  → non-normal: Mann-Whitney U

3+ groups, continuous outcome:
  → ANOVA (if normal + equal var)
  → Kruskal-Wallis (if non-normal)
  + post-hoc: Tukey HSD or Dunn's

Correlation:
  → Pearson (normal) or Spearman (non-normal)

Repeated measures:
  → Paired t-test or Wilcoxon (2 timepoints)
  → Repeated measures ANOVA or Friedman (3+ timepoints)

Categorical outcome:
  → Chi-square or Fisher's exact
```

```python
# Example: t-test
from scipy.stats import ttest_ind
import pingouin as pg

result = pg.ttest(group1_data, group2_data, correction=True)
print(result)

# Effect size (Cohen's d)
d = pg.compute_effsize(group1_data, group2_data, eftype='cohen')
print(f"Cohen's d = {d:.3f}")
```

### Step 5: Multiple comparisons correction
If running >1 test: apply FDR (Benjamini-Hochberg) or Bonferroni:
```python
from statsmodels.stats.multitest import multipletests
reject, p_corrected, _, _ = multipletests(p_values, method='fdr_bh')
```

### Step 6: Generate figures
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Box + strip plot for group comparisons
fig, ax = plt.subplots(figsize=(8,6))
sns.boxplot(data=df, x=group_col, y=outcome_col, ax=ax)
sns.stripplot(data=df, x=group_col, y=outcome_col, ax=ax, alpha=0.5, color='black')
ax.set_title(f"{outcome_col} by {group_col}")
plt.savefig("{output_path}/figure_analysis_{date}.png", dpi=300, bbox_inches='tight')
```

### Step 7: Plain-English interpretation

```
📊 **Analysis Results — {date}**

**Question:** {question}
**Test used:** {test} — {why this test in 1 sentence}
**Assumptions:** {normality ✅/⚠️, equal variances ✅/⚠️}

**Result:**
{Group A} (M={mean}, SD={sd}) vs {Group B} (M={mean}, SD={sd})
{test}({df}) = {statistic}, p = {p-value}, {Cohen's d or η²} = {effect_size}

**Interpretation:**
{Plain English: "There was a statistically significant difference between groups..."}
Effect size: {small/medium/large} — {plain English meaning}

**⚠️ Cautions:**
- {e.g., "p = 0.048 is just above threshold — interpret cautiously"}
- {e.g., "Small N (n=12) limits power. Consider replication."}
- {e.g., "Multiple comparisons correction applied — 2 of 5 comparisons survive FDR"}

**Hypothesis verdict:**
→ H1 ("{hypothesis text}"): {SUPPORTED / NOT SUPPORTED / INCONCLUSIVE}
Reason: {1 sentence}
```

---

## Mode: `power`

```python
from statsmodels.stats.power import TTestIndPower, FTestAnovaPower
import numpy as np

# Solve for any one parameter given the others
analysis = TTestIndPower()

# Default: solve for N
n = analysis.solve_power(
    effect_size=float(effect_size),
    alpha=float(alpha),
    power=float(power),
    alternative='two-sided'
)
print(f"Required N per group: {np.ceil(n):.0f}")
print(f"Total N: {np.ceil(n)*2:.0f}")
```

Output:
```
⚡ Power Analysis

Test: Independent samples t-test (two-tailed)
Effect size (Cohen's d): {d}
Alpha (Type I error): {α}
Desired power: {power}

→ Required N per group: {n}
→ Total N: {total}

Interpretation:
{e.g., "With your expected medium effect (d=0.5) and n=20 per group, you have ~56% power — likely underpowered. You need n=64 per group for 80% power."}
```

---

## Mode: `review-methods`

Send methods section to LLM:
```
You are a biostatistician reviewing this methods section. Evaluate:

1. Is the statistical test appropriate for the research question and data type?
2. Are assumptions stated or checked?
3. Is the sample size justified? Is there a power analysis?
4. Are multiple comparisons addressed?
5. Are effect sizes reported alongside p-values?
6. Is the analysis plan pre-specified or exploratory? (important for interpretation)
7. Any risk of p-hacking or HARKing (Hypothesizing After Results are Known)?

Rate each item: ✅ OK / ⚠️ Concern / ❌ Problem
For each concern/problem: explain and suggest fix.

Methods section:
{text}
```

---

## Mode: `assumption-check`

Run assumption tests for the specified test type and output a report before the user runs analysis.

---

## Save results

All analysis outputs (figures, results tables, interpretation) saved to:
`{vault}/Research/Projects/{project}/analysis/{date}-{test-type}/`

Update research graph:
- Mark hypothesis as `supported` / `not_supported` / `inconclusive`
- Link analysis files to hypothesis node

Award +150 XP. Badge: "📊 Experimenter". Log session.
