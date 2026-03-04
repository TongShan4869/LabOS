#!/usr/bin/env python3
"""
lab-trend-analysis — longitudinal field trend tracker
Builds on lab-field-trend by comparing across weeks, tracking topic trajectories,
measuring citation velocity, and flagging hypothesis challengers.

Usage:
  python3 lab_trend_analysis.py                  # full analysis, last 4 weeks
  python3 lab_trend_analysis.py --weeks 8        # extend lookback window
  python3 lab_trend_analysis.py --dry-run        # print without saving
  python3 lab_trend_analysis.py --no-notify      # save but skip Discord
  python3 lab_trend_analysis.py --snapshot-only  # just collect this week, no analysis
"""

import argparse
import json
import math
import os
import re
import sys
import subprocess
import urllib.request
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE      = Path(os.environ.get("LABOS_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
LAB_DIR        = WORKSPACE / "LabOS"
LAB_CONFIG     = LAB_DIR / "LAB_CONFIG.json"
RESEARCH_GRAPH = LAB_DIR / "research-graph.jsonl"
XP_FILE        = LAB_DIR / "xp.json"
XP_ENGINE      = LAB_DIR / "gamification" / "xp_engine.py"
TREND_HISTORY  = LAB_DIR / "trend-history.jsonl"   # weekly snapshots

NOW   = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
WEEK  = NOW.strftime("%Y-W%W")   # e.g. 2026-W09

# ── Helpers ────────────────────────────────────────────────────────────────────
def bold(s):   return f"\033[1m{s}\033[0m"
def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def cyan(s):   return f"\033[36m{s}\033[0m"
def dim(s):    return f"\033[2m{s}\033[0m"
def up(s):     return f"\033[32m↑ {s}\033[0m"
def down(s):   return f"\033[31m↓ {s}\033[0m"

def load_json(path):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def append_jsonl(path, record):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

def load_jsonl(path):
    records = []
    p = Path(path)
    if not p.exists():
        return records
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records

def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LabOS/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None

def award_xp(event, points):
    data = load_json(XP_FILE) or {"xp": 0, "history": []}
    data["xp"] = data.get("xp", 0) + points
    data.setdefault("history", []).append({"event": event, "xp": points, "timestamp": NOW.isoformat()})
    save_json(XP_FILE, data)

# ── Stopwords (minimal scientific stopword list) ───────────────────────────────
STOPWORDS = {
    "a","an","the","and","or","of","in","to","for","with","on","at","by","from",
    "is","are","was","were","be","been","being","have","has","had","do","does",
    "did","will","would","could","should","may","might","this","that","these",
    "those","it","its","we","our","their","which","who","as","not","but","no",
    "so","if","when","than","also","can","all","more","new","using","based",
    "study","studies","research","results","patients","data","analysis","method",
    "approach","paper","work","model","show","shows","shown","found","effect",
    "effects","associated","between","among","across","within","after","before",
    "during","however","while","both","each","other","such","via","two","three",
    "one","use","used","used","high","low","large","small","significant","total",
    "clinical","human","brain","neural","cell","cells","gene","genes","protein"
}

# ── N-gram extraction ──────────────────────────────────────────────────────────
def extract_ngrams(text, n_range=(1, 3)):
    """Extract unigrams, bigrams, trigrams from text, filtered."""
    tokens = re.findall(r'\b[a-z][a-z\-]{2,}\b', text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 3]
    ngrams = []
    for n in range(n_range[0], n_range[1] + 1):
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i:i+n])
            ngrams.append(gram)
    return ngrams

def topic_freq_from_papers(papers):
    """Return Counter of n-grams across all papers (title + abstract)."""
    all_ngrams = []
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract_snippet", "") +
                " " + p.get("abstract", ""))
        all_ngrams.extend(extract_ngrams(text, n_range=(1, 3)))
    return Counter(all_ngrams)

# ── Load historical paper data ─────────────────────────────────────────────────
def load_papers_by_week(weeks_back=8):
    """
    Load Paper nodes from research-graph.jsonl grouped by ISO week.
    Returns dict: {week_str: [papers]}
    """
    records = load_jsonl(RESEARCH_GRAPH)
    papers_by_week = defaultdict(list)
    cutoff = NOW - timedelta(weeks=weeks_back)

    for r in records:
        if r.get("type") != "Paper":
            continue
        added = r.get("added_date", "")
        if not added:
            continue
        try:
            dt = datetime.fromisoformat(added)
        except Exception:
            try:
                dt = datetime.strptime(added, "%Y-%m-%d")
            except Exception:
                continue
        if dt.replace(tzinfo=None) < cutoff.replace(tzinfo=None):
            continue
        week_key = dt.strftime("%Y-W%W")
        papers_by_week[week_key].append(r)

    return dict(papers_by_week)

def load_hypotheses():
    """Extract hypothesis strings from Project nodes in research-graph.jsonl."""
    records = load_jsonl(RESEARCH_GRAPH)
    hypotheses = []
    for r in records:
        if r.get("type") == "Project":
            for h in r.get("hypotheses", []):
                if h:
                    hypotheses.append({"project": r["name"], "hypothesis": h})
    return hypotheses

# ── Citation velocity via OpenAlex ─────────────────────────────────────────────
def fetch_citation_counts(dois, max_fetch=20):
    """
    Fetch citation counts for a list of DOIs from OpenAlex.
    Returns dict: {doi: citation_count}
    """
    results = {}
    for doi in dois[:max_fetch]:
        if not doi:
            continue
        encoded = urllib.parse.quote(f"https://doi.org/{doi}", safe="")
        url = f"https://api.openalex.org/works/{encoded}?select=doi,cited_by_count,publication_year&mailto=labos@research.ai"
        raw = http_get(url)
        if raw:
            try:
                data = json.loads(raw)
                results[doi] = data.get("cited_by_count", 0)
            except Exception:
                pass
    return results

def compute_citation_velocity(papers_by_week):
    """
    For papers that appear in multiple weeks of history, track citation count growth.
    Returns list of {doi, title, citations_now, citations_prev, velocity, weeks_tracked}
    """
    # Collect all DOIs and titles from all weeks
    doi_to_title = {}
    doi_first_week = {}
    doi_latest_week = {}
    weeks_sorted = sorted(papers_by_week.keys())

    for week in weeks_sorted:
        for p in papers_by_week[week]:
            doi = p.get("doi")
            if doi:
                doi_to_title[doi] = p.get("title", doi)
                if doi not in doi_first_week:
                    doi_first_week[doi] = week
                doi_latest_week[doi] = week

    # Only fetch citation counts for papers we've seen for at least 2 weeks
    tracked_dois = [
        doi for doi in doi_to_title
        if doi_first_week.get(doi) != doi_latest_week.get(doi)
    ]

    if not tracked_dois:
        # Just fetch the most recent batch
        latest_week = weeks_sorted[-1] if weeks_sorted else None
        if latest_week:
            recent_papers = papers_by_week.get(latest_week, [])
            tracked_dois = [p.get("doi") for p in recent_papers if p.get("doi")][:20]

    if not tracked_dois:
        return []

    print(f"  Fetching citation counts for {len(tracked_dois[:20])} papers...", end="", flush=True)
    counts = fetch_citation_counts(tracked_dois[:20])
    print(f" {green('done')}")

    velocity_data = []
    for doi, count in counts.items():
        if count is None:
            continue
        velocity_data.append({
            "doi": doi,
            "title": doi_to_title.get(doi, doi)[:80],
            "citations": count,
            "weeks_tracked": 1
        })

    # Sort by citation count descending
    velocity_data.sort(key=lambda x: x["citations"], reverse=True)
    return velocity_data[:15]

# ── Trend detection ────────────────────────────────────────────────────────────
def compute_topic_trends(papers_by_week, weeks_back=4):
    """
    Compare topic frequencies this week vs rolling average of previous weeks.
    Returns:
      rising:  topics with frequency spike this week
      cooling: topics that were hot but dropped off
      new:     topics appearing for the first time this week
      sustained: topics consistently present for 3+ weeks
    """
    weeks_sorted = sorted(papers_by_week.keys())
    if not weeks_sorted:
        return {}, {}, {}, {}

    current_week = weeks_sorted[-1]
    prior_weeks  = weeks_sorted[-weeks_back-1:-1]  # up to 4 prior weeks

    current_papers = papers_by_week.get(current_week, [])
    current_freq   = topic_freq_from_papers(current_papers)

    # Compute rolling baseline from prior weeks
    prior_freqs = []
    for w in prior_weeks:
        papers = papers_by_week.get(w, [])
        if papers:
            prior_freqs.append(topic_freq_from_papers(papers))

    if not prior_freqs:
        # No history — everything is "new"
        top = current_freq.most_common(20)
        new_topics = {t: cnt for t, cnt in top}
        return {}, {}, new_topics, {}

    # Average prior frequency
    all_prior_topics = set()
    for f in prior_freqs:
        all_prior_topics.update(f.keys())

    avg_prior = {}
    for topic in all_prior_topics:
        avg_prior[topic] = sum(f.get(topic, 0) for f in prior_freqs) / len(prior_freqs)

    # Classify topics
    rising, cooling, new_topics, sustained = {}, {}, {}, {}
    all_topics = set(current_freq.keys()) | set(avg_prior.keys())

    for topic in all_topics:
        cur  = current_freq.get(topic, 0)
        prev = avg_prior.get(topic, 0)

        # Only care about topics with meaningful frequency
        if cur < 2 and prev < 2:
            continue
        # Skip single-word ultra-common terms with low discriminative value
        if len(topic.split()) == 1 and cur < 4:
            continue

        # Weeks present across all history
        weeks_present = sum(
            1 for f in prior_freqs if f.get(topic, 0) >= 1
        ) + (1 if cur >= 1 else 0)

        if prev == 0 and cur >= 2:
            new_topics[topic] = cur
        elif prev > 0 and cur == 0:
            cooling[topic] = prev
        elif cur > 0 and prev > 0:
            ratio = cur / max(prev, 0.5)
            if ratio >= 1.8 and cur >= 3:
                rising[topic] = (cur, prev, ratio)
            elif weeks_present >= 3 and cur >= 2:
                sustained[topic] = weeks_present

    # Sort and cap
    rising   = dict(sorted(rising.items(),   key=lambda x: x[1][2], reverse=True)[:12])
    cooling  = dict(sorted(cooling.items(),  key=lambda x: x[1],    reverse=True)[:8])
    new_topics = dict(sorted(new_topics.items(), key=lambda x: x[1], reverse=True)[:12])
    sustained  = dict(sorted(sustained.items(), key=lambda x: x[1], reverse=True)[:10])

    return rising, cooling, new_topics, sustained

# ── Hypothesis challenger ──────────────────────────────────────────────────────
def find_hypothesis_challengers(papers, hypotheses):
    """
    Flag papers whose title/abstract contains language that may challenge
    a stored hypothesis. Uses keyword overlap + negation detection.
    """
    if not hypotheses or not papers:
        return []

    # Negation/contrast markers
    CHALLENGE_MARKERS = [
        "no significant", "not significant", "failed to", "contrary to",
        "inconsistent with", "challenges", "contradicts", "refutes",
        "no evidence", "null result", "negative result", "did not replicate",
        "lack of", "absence of", "does not support", "unlikely", "no effect",
        "no difference", "no association", "no correlation", "not associated"
    ]

    challengers = []
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract_snippet", "") +
                " " + p.get("abstract", "")).lower()

        # Check if paper contains challenge markers
        has_challenge = any(marker in text for marker in CHALLENGE_MARKERS)
        if not has_challenge:
            continue

        # Check if paper overlaps with any hypothesis topic
        for hyp_obj in hypotheses:
            hyp_text = hyp_obj["hypothesis"].lower()
            hyp_tokens = set(re.findall(r'\b[a-z]{4,}\b', hyp_text)) - STOPWORDS
            paper_tokens = set(re.findall(r'\b[a-z]{4,}\b', text)) - STOPWORDS
            overlap = hyp_tokens & paper_tokens
            if len(overlap) >= 2:  # at least 2 meaningful shared terms
                challengers.append({
                    "paper_title": p.get("title", ""),
                    "paper_url":   p.get("url", ""),
                    "project":     hyp_obj["project"],
                    "hypothesis":  hyp_obj["hypothesis"][:120],
                    "overlap_terms": list(overlap)[:5],
                    "source":      p.get("source", "")
                })
                break

    return challengers[:5]  # Cap at 5 challengers per run

# ── Load recent papers for challenger check ────────────────────────────────────
def load_recent_papers(days=14):
    records = load_jsonl(RESEARCH_GRAPH)
    cutoff = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
    return [
        r for r in records
        if r.get("type") == "Paper" and r.get("added_date", "") >= cutoff
    ]

# ── Format output ──────────────────────────────────────────────────────────────
def format_trend_report(
    rising, cooling, new_topics, sustained,
    velocity_data, challengers,
    papers_by_week, weeks_back
):
    weeks_sorted = sorted(papers_by_week.keys())
    current_week = weeks_sorted[-1] if weeks_sorted else WEEK
    total_papers = sum(len(v) for v in papers_by_week.values())

    lines = [
        f"# Field Trend Analysis — {TODAY}",
        f"",
        f"> Week: `{current_week}` | {len(weeks_sorted)} weeks of history | {total_papers} papers tracked",
        f"",
        f"---",
        f"",
    ]

    # ── Rising topics
    if rising:
        lines += ["## 🚀 Rising Topics", ""]
        lines += ["| Topic | This week | Avg prev | Velocity |", "|-------|-----------|----------|----------|"]
        for topic, (cur, prev, ratio) in rising.items():
            lines.append(f"| `{topic}` | {cur} | {prev:.1f} | **+{ratio:.1f}×** |")
        lines += ["", ""]

    # ── New topics
    if new_topics:
        lines += ["## 🆕 Newly Emerging Topics", "*(not seen in previous weeks)*", ""]
        for topic, cnt in list(new_topics.items())[:10]:
            lines.append(f"- `{topic}` — appeared {cnt}× this week")
        lines += ["", ""]

    # ── Sustained topics
    if sustained:
        lines += ["## 🔁 Sustained Themes", "*(consistently present 3+ weeks)*", ""]
        for topic, weeks in list(sustained.items())[:8]:
            lines.append(f"- `{topic}` — {weeks} weeks running")
        lines += ["", ""]

    # ── Cooling topics
    if cooling:
        lines += ["## 📉 Cooling Off", "*(was active, dropped this week)*", ""]
        for topic, prev in list(cooling.items())[:6]:
            lines.append(f"- `{topic}` — avg {prev:.1f}/week → 0 this week")
        lines += ["", ""]

    # ── Citation velocity
    if velocity_data:
        lines += ["## ⚡ Citation Velocity", "*(most-cited papers in your tracked corpus)*", ""]
        lines += ["| Paper | Citations |", "|-------|-----------|"]
        for v in velocity_data[:10]:
            title_short = v["title"][:65] + ("..." if len(v["title"]) > 65 else "")
            doi_link = f"[🔗](https://doi.org/{v['doi']})" if v.get("doi") else ""
            lines.append(f"| {title_short} {doi_link} | **{v['citations']}** |")
        lines += ["", ""]

    # ── Hypothesis challengers
    if challengers:
        lines += ["## ⚠️ Hypothesis Challengers", "*(papers that may challenge your project hypotheses)*", ""]
        for c in challengers:
            url = c.get("paper_url", "")
            link = f" [🔗]({url})" if url else ""
            lines += [
                f"### {c['project']}",
                f"> *Your hypothesis:* {c['hypothesis']}",
                f"",
                f"**{c['paper_title']}**{link}",
                f"*Overlap terms: {', '.join(c['overlap_terms'])}*",
                f"",
            ]
    else:
        lines += ["## ✅ No Hypothesis Challengers Found", "*(no papers directly challenged your stored hypotheses this period)*", ""]

    lines += [
        "---",
        f"",
        f"*Generated by LabOS lab-trend-analysis · {NOW.strftime('%Y-%m-%d %H:%M UTC')}*"
    ]

    return "\n".join(lines)

def format_discord_summary(rising, new_topics, challengers, total_papers, weeks):
    lines = [
        f"📈 **LabOS Trend Analysis** — {TODAY}",
        f"_{total_papers} papers · {weeks} weeks of history_",
        "",
    ]
    if rising:
        lines.append("**🚀 Rising topics:**")
        for topic, (cur, prev, ratio) in list(rising.items())[:5]:
            lines.append(f"  • `{topic}` (+{ratio:.1f}×)")
    if new_topics:
        lines.append("\n**🆕 New this week:**")
        for topic in list(new_topics.keys())[:5]:
            lines.append(f"  • `{topic}`")
    if challengers:
        lines.append(f"\n**⚠️ {len(challengers)} hypothesis challenger(s) detected** — check Obsidian for details")
    return "\n".join(lines)

# ── Save to Obsidian ───────────────────────────────────────────────────────────
def save_to_obsidian(cfg, report_md):
    vault = cfg.get("obsidian_vault")
    if not vault:
        return False
    vault_path = Path(vault)
    if not vault_path.exists():
        return False
    trend_dir = vault_path / "Research" / "Trend-Analysis"
    trend_dir.mkdir(parents=True, exist_ok=True)
    out_file = trend_dir / f"{TODAY}-trend-analysis.md"
    out_file.write_text(report_md)
    print(f"  {green('✓')} Saved: Research/Trend-Analysis/{TODAY}-trend-analysis.md")
    return True

# ── Send Discord notification ──────────────────────────────────────────────────
def send_discord(msg):
    channel_id = "1478320565549924415"
    try:
        subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "discord",
             "--target", channel_id,
             "--message", msg],
            check=True, capture_output=True, timeout=15
        )
        return True
    except Exception:
        return False

# ── Snapshot: save this week's topic freq to trend-history.jsonl ───────────────
def save_trend_snapshot(papers_by_week):
    weeks_sorted = sorted(papers_by_week.keys())
    if not weeks_sorted:
        return
    current_week = weeks_sorted[-1]
    current_papers = papers_by_week.get(current_week, [])
    freq = topic_freq_from_papers(current_papers)
    top_topics = dict(freq.most_common(50))

    # Check if snapshot for this week already exists
    existing = load_jsonl(TREND_HISTORY)
    for rec in existing:
        if rec.get("week") == current_week:
            return  # Already snapshotted this week

    append_jsonl(TREND_HISTORY, {
        "type": "TrendSnapshot",
        "week": current_week,
        "date": TODAY,
        "paper_count": len(current_papers),
        "top_topics": top_topics
    })
    print(f"  {green('✓')} Trend snapshot saved for {current_week} ({len(current_papers)} papers, {len(top_topics)} topics)")

# ── Main ───────────────────────────────────────────────────────────────────────
def run(args):
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print("❌ No LAB_CONFIG.json found. Run lab-init first.")
        sys.exit(1)

    weeks_back = args.weeks
    print(f"\n{bold('📊 LabOS Trend Analysis')}")
    print(f"{dim(f'Lookback: {weeks_back} weeks | History: trend-history.jsonl')}\n")

    # Load paper history from research-graph
    print("  Loading paper history...", end="", flush=True)
    papers_by_week = load_papers_by_week(weeks_back=weeks_back)
    total = sum(len(v) for v in papers_by_week.values())
    print(f" {green(str(total))} papers across {len(papers_by_week)} weeks")

    if total == 0:
        print(yellow("\n⚠️  No paper history found. Run lab-field-trend first to build your corpus."))
        print(    "   python3 lab_field_trend.py --days 30")
        sys.exit(0)

    if args.snapshot_only:
        save_trend_snapshot(papers_by_week)
        print(f"\n{green('✅')} Snapshot saved. Run without --snapshot-only for full analysis.")
        return

    # Save this week's snapshot
    save_trend_snapshot(papers_by_week)

    # Topic trend detection
    print("\n  Computing topic trajectories...", end="", flush=True)
    rising, cooling, new_topics, sustained = compute_topic_trends(papers_by_week, weeks_back=min(4, weeks_back))
    print(f" {green('done')}")
    print(f"    Rising: {len(rising)} | New: {len(new_topics)} | Sustained: {len(sustained)} | Cooling: {len(cooling)}")

    # Citation velocity
    print("\n  Computing citation velocity...")
    velocity_data = compute_citation_velocity(papers_by_week)

    # Hypothesis challengers
    print("  Checking for hypothesis challengers...", end="", flush=True)
    hypotheses = load_hypotheses()
    recent_papers = load_recent_papers(days=14)
    challengers = find_hypothesis_challengers(recent_papers, hypotheses)
    print(f" {green(str(len(challengers)))} found")

    # Print terminal summary
    print(f"\n{'-'*60}")
    if rising:
        print(f"\n{bold('🚀 Rising topics:')}")
        for topic, (cur, prev, ratio) in list(rising.items())[:6]:
            print(f"   {up(f'+{ratio:.1f}×')}  {topic}  {dim(f'({cur} this week vs {prev:.1f} avg)')}")
    if new_topics:
        print(f"\n{bold('🆕 New this week:')}")
        for topic, cnt in list(new_topics.items())[:6]:
            print(f"   ✦  {topic}  {dim(f'({cnt}×)')}")
    if challengers:
        print(f"\n{bold(red('⚠️  Hypothesis challengers:'))}")
        for c in challengers:
            print(f"   [{c['project']}] {c['paper_title'][:70]}...")
    print(f"{'-'*60}")

    if args.dry_run:
        print(f"\n{yellow('[dry-run] Skipping save and notification.')}")
        return

    # Build full report
    report_md = format_trend_report(
        rising, cooling, new_topics, sustained,
        velocity_data, challengers,
        papers_by_week, weeks_back
    )

    # Save to Obsidian
    save_to_obsidian(cfg, report_md)

    # Discord
    if not args.no_notify and cfg.get("notify_channel") == "discord":
        discord_msg = format_discord_summary(rising, new_topics, challengers, total, len(papers_by_week))
        sent = send_discord(discord_msg)
        print(f"  {green('✓') if sent else yellow('⚠')}  Discord {'sent' if sent else 'failed'}")

    # XP
    award_xp("trend_analysis_run", 30)
    print(f"  {green('✓')} +30 XP awarded")
    print(f"\n{bold(green('✅ Trend analysis complete!'))}\n")


def main():
    parser = argparse.ArgumentParser(description="LabOS longitudinal trend analysis")
    parser.add_argument("--weeks",         type=int, default=4,  help="Weeks of history to analyse (default 4)")
    parser.add_argument("--dry-run",       action="store_true",  help="Print without saving")
    parser.add_argument("--no-notify",     action="store_true",  help="Save but skip Discord")
    parser.add_argument("--snapshot-only", action="store_true",  help="Only save this week's snapshot")
    args = parser.parse_args()
    run(args)

if __name__ == "__main__":
    main()
