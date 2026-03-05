#!/usr/bin/env python3
"""
lab-biostat — Biostatistician-in-residence for LabOS
Runs statistical analysis via Python (scipy, statsmodels, pingouin, matplotlib).
Always shows its work. Never a black box.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, find_project, get_project_hypotheses, get_project_experiments,
    update_node, upsert_node, now_iso, today_str, short_hash,
    LAB_DIR,
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


# ── Try importing stats libs ──────────────────────────────────────────────────

def _require(*packages):
    missing = []
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        print(f"   Install with: pip install {' '.join(missing)}")
        sys.exit(1)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def save_results(content: str, project_name: str, analysis_type: str, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        out_dir = Path(vault) / "Research" / "Projects" / project_name / "analysis"
    else:
        out_dir = LAB_DIR / "analysis" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today_str()}-{analysis_type}.md"
    path.write_text(content)
    return path


def save_figure(fig, project_name: str, name: str, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        out_dir = Path(vault) / "Research" / "Projects" / project_name / "analysis"
    else:
        out_dir = LAB_DIR / "analysis" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today_str()}-{name}.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    return path


def effect_size_label(d: float) -> str:
    d = abs(d)
    if d < 0.2:   return "negligible"
    if d < 0.5:   return "small"
    if d < 0.8:   return "medium"
    return "large"


def interpret_p(p: float) -> str:
    if p < 0.001: return "p < 0.001 (very strong evidence against H0)"
    if p < 0.01:  return f"p = {p:.3f} (strong evidence)"
    if p < 0.05:  return f"p = {p:.3f} (statistically significant)"
    if p < 0.10:  return f"p = {p:.3f} (marginal — interpret cautiously)"
    return f"p = {p:.3f} (not statistically significant)"


# ═══════════════════════════════════════════════════════════════
# MODE: power
# ═══════════════════════════════════════════════════════════════

def mode_power(args):
    _require("statsmodels", "scipy")
    from statsmodels.stats.power import (
        TTestIndPower, TTestPower, FTestAnovaPower, NormalIndPower
    )
    import numpy as np

    section_header("⚡ Power Analysis")

    # Gather parameters interactively if not provided
    effect_size = args.effect_size
    alpha       = args.alpha
    power       = args.power
    test_type   = getattr(args, "test_type", None) or "t-test-ind"
    n_groups    = getattr(args, "n_groups", 2)

    if effect_size is None:
        try:
            raw = checkpoint(
                "Effect size? (Cohen's d for t-tests, η² for ANOVA)\n"
                "   Common values: small=0.2, medium=0.5, large=0.8",
                default="0.5", emoji="📐",
            )
            effect_size = float(raw)
        except (CheckpointAborted, ValueError):
            effect_size = 0.5

    if alpha is None:
        try:
            raw = checkpoint("Alpha (Type I error rate)?", default="0.05", emoji="📐")
            alpha = float(raw)
        except (CheckpointAborted, ValueError):
            alpha = 0.05

    if power is None:
        try:
            raw = checkpoint("Desired power?", default="0.80", emoji="📐")
            power = float(raw)
        except (CheckpointAborted, ValueError):
            power = 0.80

    # Select analysis object
    if "anova" in test_type.lower() or n_groups > 2:
        analysis  = FTestAnovaPower()
        label     = f"One-way ANOVA ({n_groups} groups)"
        n_per_grp = analysis.solve_power(effect_size=effect_size, alpha=alpha, power=power, k_groups=n_groups)
        n_total   = math.ceil(n_per_grp) * n_groups
    elif "paired" in test_type.lower():
        analysis  = TTestPower()
        label     = "Paired t-test"
        n_per_grp = analysis.solve_power(effect_size=effect_size, alpha=alpha, power=power, alternative="two-sided")
        n_total   = math.ceil(n_per_grp)
    else:
        analysis  = TTestIndPower()
        label     = "Independent samples t-test (two-tailed)"
        n_per_grp = analysis.solve_power(effect_size=effect_size, alpha=alpha, power=power, alternative="two-sided")
        n_total   = math.ceil(n_per_grp) * 2

    n_per_grp = math.ceil(n_per_grp)

    # Current N check
    current_n = getattr(args, "current_n", None)
    if current_n:
        if "anova" in test_type.lower():
            achieved = analysis.solve_power(effect_size=effect_size, alpha=alpha, nobs=current_n / n_groups, k_groups=n_groups)
        else:
            achieved = analysis.solve_power(effect_size=effect_size, alpha=alpha, nobs1=current_n / 2, alternative="two-sided")
        power_status = (
            f"\n📌 **Your current N = {current_n}**\n"
            f"   Achieved power: {achieved:.2f} "
            f"{'✅ Sufficient' if achieved >= 0.80 else '⚠️ Underpowered'}"
        )
    else:
        power_status = ""

    # Plain-English interpretation
    d_label   = effect_size_label(effect_size)
    interp    = (
        f"With a {d_label} effect (d={effect_size}), α={alpha}, you need "
        f"**{n_per_grp} per group** ({n_total} total) for {power*100:.0f}% power."
    )
    if n_total > 200:
        interp += " This is a large study — consider a pilot first to validate your effect size estimate."
    if effect_size < 0.3:
        interp += " Small effects require large samples. Are you confident this effect size is correct?"

    output = [
        f"## Power Analysis — {today_str()}",
        f"",
        f"**Test:** {label}",
        f"**Effect size:** {effect_size} ({d_label})",
        f"**Alpha:** {alpha}  |  **Desired power:** {power}",
        f"",
        f"### Results",
        f"→ **Required N per group: {n_per_grp}**",
        f"→ **Total N: {n_total}**",
        f"",
        power_status,
        f"",
        f"### Interpretation",
        interp,
        f"",
        f"### Recommendations",
        f"- Pre-register your sample size and analysis plan before collecting data",
        f"- If recruiting is expensive, consider a sequential design with interim analysis",
        f"- Report effect sizes alongside p-values in your paper",
        f"- If N is fixed by constraint, report achieved power in your methods",
    ]

    result_text = "\n".join(output)
    print("\n" + result_text)
    return result_text


# ═══════════════════════════════════════════════════════════════
# MODE: assumption-check
# ═══════════════════════════════════════════════════════════════

def mode_assumption_check(args, df=None):
    _require("scipy", "pandas")
    import pandas as pd
    from scipy import stats

    section_header("🔍 Assumption Check")

    if df is None:
        if not args.data:
            print("❌ --data required for assumption-check mode.")
            sys.exit(1)
        df = pd.read_csv(args.data)

    # Detect columns
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols     = df.select_dtypes(exclude="number").columns.tolist()

    print(f"\n📋 Data: {len(df)} rows × {len(df.columns)} columns")
    print(f"   Numeric: {numeric_cols}")
    print(f"   Categorical: {cat_cols}")

    results = []

    # Normality for each numeric column
    print("\n### Normality tests (Shapiro-Wilk for n≤50, D'Agostino for n>50)")
    for col in numeric_cols:
        data = df[col].dropna()
        n    = len(data)
        if n < 3:
            continue
        if n <= 50:
            stat, p = stats.shapiro(data)
            test_name = "Shapiro-Wilk"
        else:
            stat, p = stats.normaltest(data)
            test_name = "D'Agostino"
        status = "✅ Normal" if p > 0.05 else "⚠️  Non-normal"
        print(f"   {col}: {test_name} W={stat:.3f}, p={p:.3f}  {status}")
        results.append({"col": col, "test": test_name, "stat": stat, "p": p, "normal": p > 0.05})

    # Variance homogeneity (if group column exists)
    if cat_cols and len(numeric_cols) >= 1:
        group_col   = cat_cols[0]
        outcome_col = numeric_cols[0]
        groups      = [df[df[group_col] == g][outcome_col].dropna() for g in df[group_col].unique()]
        if len(groups) >= 2 and all(len(g) >= 2 for g in groups):
            lev_stat, lev_p = stats.levene(*groups)
            status = "✅ Equal variances" if lev_p > 0.05 else "⚠️  Unequal variances"
            print(f"\n### Levene's test ({group_col} → {outcome_col})")
            print(f"   F={lev_stat:.3f}, p={lev_p:.3f}  {status}")

    # Test recommendation
    non_normal = [r for r in results if not r["normal"]]
    print("\n### Recommendation")
    if non_normal:
        print(f"   ⚠️  {len(non_normal)} column(s) appear non-normal.")
        print("   → Consider non-parametric tests:")
        print("     2 groups: Mann-Whitney U  |  3+ groups: Kruskal-Wallis")
        print("     Correlation: Spearman ρ   |  Repeated measures: Friedman")
    else:
        print("   ✅ Data appear approximately normal — parametric tests appropriate.")

    return results


# ═══════════════════════════════════════════════════════════════
# MODE: analyze
# ═══════════════════════════════════════════════════════════════

def mode_analyze(args, project: dict | None, hypotheses: list, config: dict, nodes: list):
    _require("scipy", "pandas", "matplotlib")
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    from scipy import stats

    try:
        import pingouin as pg
        HAS_PINGOUIN = True
    except ImportError:
        HAS_PINGOUIN = False

    try:
        from statsmodels.stats.multitest import multipletests
        HAS_STATSMODELS = True
    except ImportError:
        HAS_STATSMODELS = False

    if not args.data:
        print("❌ --data path required for analyze mode.")
        sys.exit(1)

    section_header("📊 Statistical Analysis")

    # Load data
    progress("Loading data…", "📂")
    try:
        df = pd.read_csv(args.data)
    except Exception as e:
        print(f"❌ Failed to read {args.data}: {e}")
        sys.exit(1)

    print(f"\n📋 Data loaded: {len(df)} rows × {len(df.columns)} columns")
    print(f"   Columns: {list(df.columns)}")
    print(df.describe().to_string())

    # Parse question
    question = args.question or ""
    if not question:
        try:
            question = checkpoint("What is your research question?", emoji="❓")
        except CheckpointAborted:
            question = "Is there a group difference?"

    # Detect columns
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols     = df.select_dtypes(exclude="number").columns.tolist()

    # Auto-detect group and outcome columns
    group_col   = cat_cols[0]   if cat_cols   else None
    outcome_col = numeric_cols[0] if numeric_cols else None

    if not args.no_interactive:
        if cat_cols:
            try:
                gc = checkpoint(
                    f"Group column? (detected: {group_col})",
                    options=list(df.columns), default=group_col, emoji="🔀",
                )
                group_col = gc if gc in df.columns else group_col
            except CheckpointAborted:
                pass
        if numeric_cols:
            try:
                oc = checkpoint(
                    f"Outcome column? (detected: {outcome_col})",
                    options=numeric_cols, default=outcome_col, emoji="📈",
                )
                outcome_col = oc if oc in numeric_cols else outcome_col
            except CheckpointAborted:
                pass

    results_lines = [
        f"# Statistical Analysis — {today_str()}",
        f"**Question:** {question}",
        f"**Data:** {args.data} ({len(df)} rows)",
        f"**Group:** {group_col}  |  **Outcome:** {outcome_col}",
        "",
    ]

    # ── Assumption check ──
    progress("Checking assumptions…", "🔍")
    assumption_results = mode_assumption_check(args, df)
    any_non_normal     = any(not r["normal"] for r in assumption_results)

    results_lines += ["## Assumptions", ""]
    for r in assumption_results:
        status = "✅ Normal" if r["normal"] else "⚠️ Non-normal"
        results_lines.append(f"- {r['col']}: {r['test']} W={r['stat']:.3f}, p={r['p']:.3f}  {status}")
    results_lines.append("")

    # ── Test selection ──
    groups = []
    if group_col:
        group_vals = df[group_col].dropna().unique()
        groups     = [df[df[group_col] == g][outcome_col].dropna() for g in group_vals]
        n_groups   = len(groups)
    else:
        n_groups = 1

    progress("Running statistical test…", "🧮")

    stat_result = {}
    test_name   = ""
    fig_path    = None

    project_name = ""
    if project:
        props        = project.get("properties", project)
        project_name = props.get("name", "project")

    if n_groups == 2 and group_col and outcome_col:
        g1, g2 = groups[0], groups[1]
        g1_name, g2_name = str(group_vals[0]), str(group_vals[1])

        if any_non_normal:
            # Mann-Whitney U
            stat, p    = stats.mannwhitneyu(g1, g2, alternative="two-sided")
            test_name  = "Mann-Whitney U (non-parametric)"
            effect     = stat / (len(g1) * len(g2))  # rank-biserial approx
            stat_result = {
                "test": test_name, "statistic": float(stat), "p": float(p),
                "effect_r": float(effect),
                "g1_median": float(g1.median()), "g2_median": float(g2.median()),
            }
            interp = (
                f"{g1_name} (Mdn={g1.median():.3f}) vs {g2_name} (Mdn={g2.median():.3f})\n"
                f"Mann-Whitney U={stat:.1f}, {interpret_p(p)}\n"
                f"Effect size r = {effect:.3f} ({effect_size_label(effect * 2)})"  # approx d
            )
        else:
            # Welch's t-test (handles unequal variances by default)
            if HAS_PINGOUIN:
                import pingouin as pg
                pg_result = pg.ttest(g1, g2, correction=True)
                stat      = float(pg_result["T"].iloc[0])
                p         = float(pg_result["p-val"].iloc[0])
                d         = float(pg_result["cohen-d"].iloc[0])
                df_stat   = float(pg_result["dof"].iloc[0])
            else:
                stat, p = stats.ttest_ind(g1, g2, equal_var=False)
                d       = (g1.mean() - g2.mean()) / math.sqrt((g1.std()**2 + g2.std()**2) / 2)
                df_stat = len(g1) + len(g2) - 2

            test_name = "Welch's t-test (two-tailed)"
            stat_result = {
                "test": test_name, "t": float(stat), "df": float(df_stat),
                "p": float(p), "cohen_d": float(d),
                "g1_mean": float(g1.mean()), "g1_sd": float(g1.std()),
                "g2_mean": float(g2.mean()), "g2_sd": float(g2.std()),
            }
            interp = (
                f"{g1_name}: M={g1.mean():.3f} (SD={g1.std():.3f})\n"
                f"{g2_name}: M={g2.mean():.3f} (SD={g2.std():.3f})\n"
                f"t({df_stat:.1f}) = {stat:.3f}, {interpret_p(p)}\n"
                f"Cohen's d = {d:.3f} ({effect_size_label(d)} effect)"
            )

        # Figure
        import matplotlib.pyplot as plt
        try:
            import seaborn as sns
            HAS_SEABORN = True
        except ImportError:
            HAS_SEABORN = False

        fig, ax = plt.subplots(figsize=(7, 5))
        if HAS_SEABORN:
            sns.boxplot(data=df, x=group_col, y=outcome_col, ax=ax, width=0.4, palette="Set2")
            sns.stripplot(data=df, x=group_col, y=outcome_col, ax=ax, alpha=0.5, color="black", size=4)
        else:
            ax.boxplot([g1, g2], labels=[g1_name, g2_name])
        ax.set_title(f"{outcome_col} by {group_col}\n{test_name}")
        ax.set_xlabel(group_col)
        ax.set_ylabel(outcome_col)
        fig.tight_layout()
        if project_name:
            fig_path = save_figure(fig, project_name, f"{outcome_col}-by-{group_col}", config)
        plt.close(fig)

    elif n_groups >= 3 and group_col and outcome_col:
        if any_non_normal:
            stat, p   = stats.kruskal(*groups)
            test_name = "Kruskal-Wallis H (non-parametric)"
            stat_result = {"test": test_name, "H": float(stat), "p": float(p)}
            interp = (
                f"Kruskal-Wallis H({n_groups-1}) = {stat:.3f}, {interpret_p(p)}\n"
                "If significant, run post-hoc Dunn's test with correction."
            )
        else:
            stat, p   = stats.f_oneway(*groups)
            test_name = "One-way ANOVA"
            # Eta-squared
            grand_mean = df[outcome_col].mean()
            ss_between = sum(len(g) * (g.mean() - grand_mean)**2 for g in groups)
            ss_total   = sum((df[outcome_col] - grand_mean)**2)
            eta2       = ss_between / ss_total if ss_total > 0 else 0
            stat_result = {
                "test": test_name, "F": float(stat), "p": float(p),
                "eta_squared": float(eta2),
            }
            interp = (
                f"One-way ANOVA F({n_groups-1}, {len(df)-n_groups}) = {stat:.3f}, {interpret_p(p)}\n"
                f"η² = {eta2:.3f} ({effect_size_label(math.sqrt(eta2))} effect)\n"
                "If significant, run post-hoc Tukey HSD."
            )

    elif len(numeric_cols) >= 2 and not group_col:
        # Correlation
        x, y = df[numeric_cols[0]].dropna(), df[numeric_cols[1]].dropna()
        if any_non_normal:
            r, p      = stats.spearmanr(x, y)
            test_name = "Spearman correlation (non-parametric)"
        else:
            r, p      = stats.pearsonr(x, y)
            test_name = "Pearson correlation"
        stat_result = {"test": test_name, "r": float(r), "p": float(p)}
        interp = (
            f"{test_name}: r = {r:.3f}, {interpret_p(p)}\n"
            f"Effect: {effect_size_label(abs(r))}"
        )
    else:
        interp = "Could not auto-detect test type. Please specify --question more precisely."
        test_name = "unknown"

    # ── Results output ──
    print("\n" + "═"*60)
    print(f"  📊 Results — {test_name}")
    print("═"*60)
    print(f"\n{interp}")
    if fig_path:
        print(f"\n📈 Figure saved: {fig_path}")

    # Hypothesis verdict
    hypothesis_text = ""
    verdict         = "inconclusive"
    if hypotheses:
        hypothesis_text = hypotheses[0].get("text", "")
        p_val = stat_result.get("p", 1.0)
        if p_val < 0.05:
            verdict = "supported" if (
                stat_result.get("t", stat_result.get("H", stat_result.get("F", 0))) > 0
            ) else "not_supported"
        else:
            verdict = "not_supported" if p_val > 0.10 else "inconclusive"

    verdict_icon = {"supported": "✅", "not_supported": "❌", "inconclusive": "⚠️"}.get(verdict, "⚠️")
    verdict_line = f"\n{verdict_icon} **Hypothesis verdict: {verdict.upper()}**"
    if hypothesis_text:
        verdict_line += f"\n   H1: \"{hypothesis_text[:80]}\""
    print(verdict_line)

    # Caveats
    p_val = stat_result.get("p", 1.0)
    print("\n⚠️  Cautions:")
    if p_val > 0.04 and p_val < 0.06:
        print("   • p is very close to 0.05 — interpret carefully, not a bright line")
    if len(df) < 20:
        print(f"   • Small N ({len(df)}) — results may not be stable. Consider replication.")
    if any_non_normal:
        print("   • Non-parametric test used — check that this matches your pre-registered plan")

    # Build markdown results
    results_lines += [
        f"## Results",
        f"**Test:** {test_name}",
        f"",
        interp,
        f"",
        verdict_line,
        f"",
        f"**Raw stats:** {json.dumps(stat_result, indent=2)}",
        f"",
        f"## Cautions",
        f"- Report effect sizes alongside p-values",
        f"- Pre-registered analysis? If exploratory, label clearly.",
        f"- Consider replication if N is small",
    ]
    if fig_path:
        rel = str(fig_path).split("/")[-1]
        results_lines.append(f"\n![]({rel})")

    result_text = "\n".join(results_lines)

    # Save
    if project_name:
        res_path = save_results(result_text, project_name, f"analysis-{today_str()}", config)
        print(f"\n💾 Results saved: {res_path}")

        # Update hypothesis node in graph
        if hypotheses and project:
            project_id = project.get("id", "")
            hyp_id     = hypotheses[0].get("id", "")
            nodes = update_node(nodes, hyp_id, {
                "verdict": verdict,
                "last_analysis": now_iso(),
                "analysis_path": str(res_path),
            })
            save_graph(nodes)

    return result_text


# ═══════════════════════════════════════════════════════════════
# MODE: design
# ═══════════════════════════════════════════════════════════════

def mode_design(args, project: dict | None, hypotheses: list, config: dict):
    section_header("📐 Study Design Advisor")

    ctx = ""
    if project:
        props = project.get("properties", project)
        ctx   = f"Project: {props.get('name','?')}\nDescription: {props.get('description','')}"
    if hypotheses:
        ctx += f"\nH1: {hypotheses[0].get('text','')}"

    # Gather design parameters interactively
    questions = [
        ("question", "What is your specific research question? (comparing groups, measuring change, associations?)"),
        ("outcome",  "What is your primary outcome variable? Is it continuous, ordinal, or categorical?"),
        ("groups",   "How many groups or conditions are you comparing?"),
        ("repeated", "Any within-subject / repeated measures? (yes/no)"),
        ("effect",   "Expected effect size? (small=0.2, medium=0.5, large=0.8, or 'I don't know')"),
        ("confounds","Key potential confounders? (list them)"),
    ]

    answers = {}
    for key, q in questions:
        try:
            answers[key] = checkpoint(q, emoji="📐")
        except CheckpointAborted:
            answers[key] = "not specified"

    prompt = (
        f"You are a biostatistician advising a researcher. Based on their answers, "
        f"recommend a study design, sample size, and analysis plan.\n\n"
        f"Context:\n{ctx}\n\n"
        f"Researcher answers:\n"
        + "\n".join(f"- {k}: {v}" for k, v in answers.items())
        + "\n\nProvide:\n"
        "1. Recommended study design (name + why)\n"
        "2. Power analysis (N per group for d=medium, α=0.05, power=0.80 if effect unknown)\n"
        "3. Controls to include (and why)\n"
        "4. Key confounders to address (and how)\n"
        "5. Primary and secondary analysis plan (specific tests)\n"
        "6. One key pitfall to watch out for\n\n"
        "Be specific and practical. Use markdown formatting."
    )

    progress("Generating design recommendation…", "🤖")
    result = call_llm(prompt)
    print("\n" + result)

    # Interactive revision
    if not args.no_interactive:
        result = interactive_loop(
            content=result,
            content_type="study design recommendation",
            config=config,
        )

    return result


# ═══════════════════════════════════════════════════════════════
# MODE: interpret
# ═══════════════════════════════════════════════════════════════

def mode_interpret(args, project: dict | None, hypotheses: list, config: dict):
    section_header("🔎 Results Interpretation")

    if not args.results:
        print("❌ --results path required for interpret mode.")
        sys.exit(1)

    results_text = Path(args.results).read_text()
    hyp_text     = hypotheses[0].get("text", "") if hypotheses else ""
    proj_name    = ""
    if project:
        props     = project.get("properties", project)
        proj_name = props.get("name", "")

    prompt = (
        f"You are a biostatistician interpreting these research results.\n\n"
        f"Project: {proj_name}\n"
        f"Hypothesis (H1): {hyp_text or 'not provided'}\n\n"
        f"Results:\n{results_text[:3000]}\n\n"
        "Provide:\n"
        "1. Plain-English summary of what the results show\n"
        "2. Effect size interpretation (practical significance)\n"
        "3. Hypothesis verdict: supported / not supported / inconclusive (with reason)\n"
        "4. Cautions: any over-interpretation, p-value caveats, sample size issues\n"
        "5. What this means for next steps\n\n"
        "Be rigorous but accessible. Flag any red flags clearly."
    )

    progress("Interpreting results…", "🤖")
    interpretation = call_llm(prompt)
    print("\n" + interpretation)

    if not args.no_interactive:
        interpretation = interactive_loop(
            content=interpretation,
            content_type="results interpretation",
            config=config,
        )

    return interpretation


# ═══════════════════════════════════════════════════════════════
# MODE: review-methods
# ═══════════════════════════════════════════════════════════════

def mode_review_methods(args, config: dict):
    section_header("🔬 Methods Section Review")

    if not args.draft:
        print("❌ --draft path required for review-methods mode.")
        sys.exit(1)

    methods_text = Path(args.draft).read_text()

    prompt = (
        "You are a senior biostatistician reviewing this methods section. "
        "Evaluate each item with ✅ OK / ⚠️ Concern / ❌ Problem:\n\n"
        "1. Is the statistical test appropriate for the research question and data type?\n"
        "2. Are test assumptions stated or checked?\n"
        "3. Is sample size justified? Is there a power analysis?\n"
        "4. Are multiple comparisons addressed?\n"
        "5. Are effect sizes reported alongside p-values?\n"
        "6. Is the analysis plan pre-specified or exploratory?\n"
        "7. Any risk of p-hacking or HARKing?\n"
        "8. Are missing data handled appropriately?\n\n"
        "For each ⚠️ or ❌: explain the concern and give a specific fix.\n\n"
        f"Methods section:\n---\n{methods_text[:4000]}\n---"
    )

    progress("Reviewing methods section…", "🤖")
    review = call_llm(prompt)
    print("\n" + review)

    if not args.no_interactive:
        review = interactive_loop(
            content=review,
            content_type="methods review",
            config=config,
        )

    return review


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="LabOS Biostat — biostatistician-in-residence")
    parser.add_argument("--mode", "-m",
                        choices=["design", "analyze", "interpret", "power", "review-methods", "assumption-check"],
                        required=True)
    parser.add_argument("--project",  "-p", help="Project name")
    parser.add_argument("--data",     "-d", help="Path to CSV data file")
    parser.add_argument("--question", "-q", help="Research question (for analyze mode)")
    parser.add_argument("--results",  "-r", help="Path to results file (for interpret mode)")
    parser.add_argument("--draft",          help="Path to methods draft (for review-methods mode)")
    parser.add_argument("--effect-size", type=float, help="Effect size (for power mode)")
    parser.add_argument("--alpha",       type=float, help="Alpha level (default 0.05)")
    parser.add_argument("--power",       type=float, help="Desired power (default 0.80)")
    parser.add_argument("--current-n",   type=int,   help="Current N to check achieved power")
    parser.add_argument("--n-groups",    type=int,   default=2)
    parser.add_argument("--test-type",               help="Test type hint (t-test-ind, paired, anova)")
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    config = load_config()
    nodes  = load_graph()

    project    = find_project(nodes, args.project) if args.project else None
    hypotheses = get_project_hypotheses(nodes, project.get("id","")) if project else []
    project_name = ""
    if project:
        props        = project.get("properties", project)
        project_name = props.get("name", "")

    # Dispatch
    if args.mode == "power":
        result = mode_power(args)

    elif args.mode == "assumption-check":
        mode_assumption_check(args)
        result = "Assumption check complete."

    elif args.mode == "analyze":
        result = mode_analyze(args, project, hypotheses, config, nodes)

    elif args.mode == "design":
        result = mode_design(args, project, hypotheses, config)

    elif args.mode == "interpret":
        result = mode_interpret(args, project, hypotheses, config)

    elif args.mode == "review-methods":
        result = mode_review_methods(args, config)

    else:
        print(f"❌ Unknown mode: {args.mode}")
        sys.exit(1)

    # Save results
    if project_name and result:
        res_path = save_results(
            f"# lab-biostat — {args.mode} — {today_str()}\n\n{result}",
            project_name, f"biostat-{args.mode}", config
        )
        print(f"\n💾 Saved: {res_path}")

    # Session log
    log_session("lab-biostat", project_name or "global",
                f"Mode: {args.mode}\n\n{str(result)[:500]}")

    # XP
    xp_map = {
        "analyze": (150, "📊 Experimenter"),
        "design":  (50,  "📐 Designer"),
        "power":   (30,  "⚡ Powered"),
        "review-methods": (75, "🔬 Rigorous"),
        "interpret": (50, None),
        "assumption-check": (20, None),
    }
    xp_amount, badge = xp_map.get(args.mode, (30, None))
    award_xp(xp_amount, badge)
    print("\n✅ Done.\n")


if __name__ == "__main__":
    with AgentWorking("stat", "Running statistics..."):
        main()
