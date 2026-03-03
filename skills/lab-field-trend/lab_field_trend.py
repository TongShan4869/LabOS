#!/usr/bin/env python3
"""
lab-field-trend — weekly field intelligence digest
Usage:
  python3 lab_field_trend.py                    # run digest (uses config fields)
  python3 lab_field_trend.py --query "topic"    # override with custom query
  python3 lab_field_trend.py --days 14          # look back N days (default 7)
  python3 lab_field_trend.py --dry-run          # print without saving/notifying
  python3 lab_field_trend.py --no-notify        # save to Obsidian, skip Discord
"""

import argparse
import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE   = Path(os.environ.get("LABOS_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
LAB_DIR     = WORKSPACE / "LabOS"
LAB_CONFIG  = LAB_DIR / "LAB_CONFIG.json"
RESEARCH_GRAPH = LAB_DIR / "research-graph.jsonl"
XP_FILE     = LAB_DIR / "xp.json"
XP_ENGINE   = LAB_DIR / "gamification" / "xp_engine.py"

NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")

# ── Helpers ────────────────────────────────────────────────────────────────────
def bold(s):   return f"\033[1m{s}\033[0m"
def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def cyan(s):   return f"\033[36m{s}\033[0m"
def dim(s):    return f"\033[2m{s}\033[0m"

def load_json(path):
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return None

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def append_jsonl(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LabOS/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        return None

def award_xp(event, points):
    if XP_ENGINE.exists():
        subprocess.run([sys.executable, str(XP_ENGINE), "--event", event, "--xp", str(points)],
                       capture_output=True)
    else:
        data = load_json(XP_FILE) or {"xp": 0, "history": []}
        data["xp"] = data.get("xp", 0) + points
        data.setdefault("history", []).append({"event": event, "xp": points, "timestamp": NOW.isoformat()})
        save_json(XP_FILE, data)

# ── PubMed ─────────────────────────────────────────────────────────────────────
def search_pubmed(query, days=7, max_results=20):
    """Search PubMed via E-utilities (no API key needed for basic use)."""
    since = (NOW - timedelta(days=days)).strftime("%Y/%m/%d")
    params = urllib.parse.urlencode({
        "db": "pubmed", "term": f"({query}) AND {since}[PDAT]",
        "retmax": max_results, "retmode": "json", "sort": "relevance"
    })
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
    raw = http_get(url)
    if not raw:
        return []
    try:
        ids = json.loads(raw)["esearchresult"]["idlist"]
    except Exception:
        return []
    if not ids:
        return []

    # Fetch abstracts
    fetch_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        f"db=pubmed&id={','.join(ids)}&retmode=xml"
    )
    xml_raw = http_get(fetch_url)
    if not xml_raw:
        return []
    return _parse_pubmed_xml(xml_raw)

def _parse_pubmed_xml(xml_raw):
    papers = []
    try:
        root = ET.fromstring(xml_raw)
    except Exception:
        return []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.findtext(".//PMID", "")
            title = article.findtext(".//ArticleTitle", "").strip()
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join((p.text or "") for p in abstract_parts).strip()
            authors = []
            for a in article.findall(".//Author")[:3]:
                ln = a.findtext("LastName", "")
                fn = a.findtext("ForeName", "")
                if ln:
                    authors.append(f"{ln} {fn[:1]}." if fn else ln)
            year = article.findtext(".//PubDate/Year", "") or article.findtext(".//PubDate/MedlineDate", "")[:4]
            journal = article.findtext(".//Journal/Title", "") or article.findtext(".//MedlineTA", "")
            doi = ""
            for id_el in article.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text or ""
            papers.append({
                "source": "pubmed", "pmid": pmid, "title": title,
                "abstract": abstract[:500] + ("..." if len(abstract) > 500 else ""),
                "authors": authors, "year": year, "journal": journal,
                "doi": doi, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            })
        except Exception:
            continue
    return papers

# ── OpenAlex ───────────────────────────────────────────────────────────────────
def search_openalex(query, days=7, max_results=15):
    """Search OpenAlex (open bibliographic database, no key needed)."""
    since = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "search": query,
        "filter": f"from_publication_date:{since}",
        "sort": "relevance_score:desc",
        "per-page": max_results,
        "select": "id,title,authorships,publication_year,primary_location,doi,abstract_inverted_index,open_access"
    })
    url = f"https://api.openalex.org/works?{params}&mailto=labos@research.ai"
    raw = http_get(url)
    if not raw:
        return []
    try:
        results = json.loads(raw).get("results", [])
    except Exception:
        return []

    papers = []
    for r in results:
        # Reconstruct abstract from inverted index
        abstract = ""
        inv = r.get("abstract_inverted_index") or {}
        if inv:
            word_positions = []
            for word, positions in inv.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions[:80])

        authors = []
        for a in r.get("authorships", [])[:3]:
            name = a.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        loc = r.get("primary_location") or {}
        journal = (loc.get("source") or {}).get("display_name", "")
        doi = r.get("doi", "") or ""
        doi_clean = doi.replace("https://doi.org/", "") if doi else ""

        papers.append({
            "source": "openalex",
            "id": r.get("id", ""),
            "title": r.get("title", "").strip(),
            "abstract": abstract[:500] + ("..." if len(abstract) > 500 else ""),
            "authors": authors,
            "year": str(r.get("publication_year", "")),
            "journal": journal,
            "doi": doi_clean,
            "url": doi if doi else r.get("id", ""),
            "open_access": r.get("open_access", {}).get("is_oa", False)
        })
    return papers

# ── arXiv ──────────────────────────────────────────────────────────────────────
def search_arxiv(query, days=7, max_results=10):
    """Search arXiv."""
    params = urllib.parse.urlencode({
        "search_query": f"all:{urllib.parse.quote(query)}",
        "start": 0, "max_results": max_results,
        "sortBy": "submittedDate", "sortOrder": "descending"
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    raw = http_get(url)
    if not raw:
        return []

    papers = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []

    cutoff = NOW - timedelta(days=days)
    for entry in root.findall("atom:entry", ns):
        try:
            published_str = entry.findtext("atom:published", "", ns)
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            if published < cutoff:
                continue
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            authors = []
            for a in entry.findall("atom:author", ns)[:3]:
                name = a.findtext("atom:name", "", ns)
                if name:
                    authors.append(name)
            papers.append({
                "source": "arxiv", "arxiv_id": arxiv_id, "title": title,
                "abstract": abstract[:500] + ("..." if len(abstract) > 500 else ""),
                "authors": authors, "year": str(published.year), "journal": "arXiv",
                "doi": "", "url": f"https://arxiv.org/abs/{arxiv_id}"
            })
        except Exception:
            continue
    return papers

# ── Dedup ──────────────────────────────────────────────────────────────────────
def dedup_papers(papers):
    """Remove duplicate papers by title similarity."""
    seen = {}
    result = []
    for p in papers:
        title_key = "".join(c for c in p["title"].lower() if c.isalnum())[:60]
        if title_key not in seen:
            seen[title_key] = True
            result.append(p)
    return result

# ── Cluster & Summarize ────────────────────────────────────────────────────────
def cluster_papers(papers, fields):
    """
    Simple keyword-based clustering into themes.
    Returns dict of {theme: [papers]}
    """
    # Build theme keywords from user fields
    field_keywords = {
        "neuroscience":        ["neural", "brain", "cortex", "neuron", "eeg", "fmri", "auditory", "speech"],
        "speech processing":   ["speech", "language", "phoneme", "ASR", "speaker", "voice", "acoustic"],
        "auditory neuroscience": ["auditory", "hearing", "cochlea", "brainstem", "ABR", "tonotopy"],
        "machine learning":    ["deep learning", "transformer", "neural network", "model", "training", "LLM"],
        "biomedical":          ["clinical", "patient", "diagnosis", "biomarker", "therapy"],
        "computational":       ["algorithm", "simulation", "computational", "model", "dataset"],
    }

    clusters = {}
    unclustered = []

    for p in papers:
        text = (p["title"] + " " + p["abstract"]).lower()
        matched = []
        for field in fields:
            kws = field_keywords.get(field.lower(), [field.lower()])
            if any(kw in text for kw in kws):
                matched.append(field)
        if matched:
            theme = matched[0]
            clusters.setdefault(theme, []).append(p)
        else:
            unclustered.append(p)

    if unclustered:
        clusters["Other / Cross-cutting"] = unclustered

    return clusters

def format_paper_md(p, style="bullet"):
    authors = ", ".join(p["authors"]) if p["authors"] else "Unknown"
    if len(p["authors"]) >= 3:
        authors = p["authors"][0] + " et al."
    year = p.get("year", "")
    journal = p.get("journal", p.get("source", ""))
    url = p.get("url", "")
    source_badge = {"pubmed": "📗", "openalex": "📘", "arxiv": "📙"}.get(p.get("source", ""), "📄")
    oa_badge = " 🔓" if p.get("open_access") else ""

    if style == "bullet":
        lines = [
            f"- {source_badge}{oa_badge} **{p['title']}**",
            f"  *{authors} ({year}) — {journal}*",
        ]
        if p.get("abstract"):
            lines.append(f"  > {p['abstract'][:200]}...")
        if url:
            lines.append(f"  [🔗 Link]({url})")
        return "\n".join(lines)
    else:
        return f"**{p['title']}** — {authors} ({year}). {journal}. {url}"

# ── Discord Notification ───────────────────────────────────────────────────────
def send_discord(cfg, digest_md, n_papers, fields):
    """Send a compact digest summary to Discord via OpenClaw."""
    channel_id = "1478320565549924415"  # brainstorm channel from config
    field_str = ", ".join(fields[:3])
    msg = (
        f"📰 **LabOS Weekly Field Digest** — {TODAY}\n"
        f"🔬 Fields: {field_str}\n"
        f"📄 {n_papers} papers scanned\n\n"
        + digest_md[:1500]
        + ("\n\n*(digest truncated — full version saved to Obsidian)*" if len(digest_md) > 1500 else "")
    )
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

# ── Main ───────────────────────────────────────────────────────────────────────
def run_digest(args):
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print("❌ No LAB_CONFIG.json found. Run lab-init first.")
        sys.exit(1)

    fields = cfg.get("fields", ["neuroscience"])
    summary_style = cfg.get("summary_style", "bullet")
    batch = cfg.get("papers_per_batch", 5)
    obsidian = cfg.get("obsidian_vault")
    notify_channel = cfg.get("notify_channel", "none")
    days = args.days

    # Build query
    if args.query:
        query = args.query
    else:
        # Combine top 3 fields into a PubMed-style OR query
        terms = [f'"{f}"' for f in fields[:4]]
        query = " OR ".join(terms)

    print(f"\n{bold('🔬 LabOS Field Trend Digest')}")
    print(f"{dim(f'Query: {query} | Last {days} days')}\n")

    # Search all databases
    all_papers = []
    databases = cfg.get("databases", ["pubmed", "openalex", "arxiv"])

    if "pubmed" in databases:
        print(f"  Searching PubMed...", end="", flush=True)
        papers = search_pubmed(query, days=days, max_results=batch * 3)
        print(f" {green(str(len(papers)))} results")
        all_papers.extend(papers)

    if "openalex" in databases:
        print(f"  Searching OpenAlex...", end="", flush=True)
        papers = search_openalex(query, days=days, max_results=batch * 2)
        print(f" {green(str(len(papers)))} results")
        all_papers.extend(papers)

    if "arxiv" in databases:
        print(f"  Searching arXiv...", end="", flush=True)
        papers = search_arxiv(query, days=days, max_results=batch)
        print(f" {green(str(len(papers)))} results")
        all_papers.extend(papers)

    all_papers = dedup_papers(all_papers)
    print(f"\n  {bold(str(len(all_papers)))} unique papers found after dedup")

    if not all_papers:
        print(yellow("\n⚠️  No papers found. Try --days 14 or a broader --query."))
        return

    # Cluster
    clusters = cluster_papers(all_papers, fields)

    # Build markdown digest
    digest_lines = [
        f"# Field Trend Digest — {TODAY}",
        f"",
        f"> Query: `{query}` | Last {days} days | {len(all_papers)} papers",
        f"> Fields: {', '.join(fields)}",
        f"",
        f"---",
        f"",
    ]

    discord_lines = []

    for theme, papers in clusters.items():
        section_header = f"## 🔬 {theme.title()} ({len(papers)} papers)"
        digest_lines.append(section_header)
        digest_lines.append("")
        discord_lines.append(f"\n**{theme.title()}** ({len(papers)})")

        for i, p in enumerate(papers[:batch]):
            digest_lines.append(format_paper_md(p, style=summary_style))
            digest_lines.append("")
            # Short version for Discord
            authors_short = p["authors"][0] + " et al." if len(p["authors"]) > 1 else (p["authors"][0] if p["authors"] else "?")
            discord_lines.append(f"• {p['title'][:80]}{'...' if len(p['title'])>80 else ''} — {authors_short} ({p.get('year','')})")

        if len(papers) > batch:
            digest_lines.append(f"*+{len(papers) - batch} more papers in this cluster*")
            digest_lines.append("")

    digest_lines += [
        "---",
        "",
        f"*Generated by LabOS lab-field-trend · {NOW.strftime('%Y-%m-%d %H:%M UTC')}*"
    ]

    digest_md = "\n".join(digest_lines)
    discord_summary = "\n".join(discord_lines)

    # Print to terminal
    print(f"\n{'-'*60}")
    for theme, papers in clusters.items():
        print(f"\n{bold(f'🔬 {theme.title()}')} — {len(papers)} papers")
        for p in papers[:3]:
            authors_short = p["authors"][0] + " et al." if len(p["authors"]) > 1 else (p["authors"][0] if p["authors"] else "?")
            print(f"  • {p['title'][:75]}{'...' if len(p['title'])>75 else ''}")
            print(f"    {dim(authors_short + ' · ' + p.get('journal','') + ' · ' + p.get('year',''))}")
    print(f"{'-'*60}")

    if args.dry_run:
        print(f"\n{yellow('[dry-run] Skipping save and notification.')}")
        return

    # Save to Obsidian
    if obsidian:
        vault = Path(obsidian)
        digest_dir = vault / "Research" / "Weekly-Digests"
        digest_dir.mkdir(parents=True, exist_ok=True)
        digest_file = digest_dir / f"{TODAY}.md"
        digest_file.write_text(digest_md)
        print(f"\n{green('✓')} Saved to Obsidian: Research/Weekly-Digests/{TODAY}.md")

    # Write papers to research-graph.jsonl
    if RESEARCH_GRAPH.exists():
        for p in all_papers:
            append_jsonl(RESEARCH_GRAPH, {
                "type": "Paper",
                "source": p.get("source"),
                "title": p.get("title"),
                "authors": p.get("authors"),
                "year": p.get("year"),
                "journal": p.get("journal"),
                "doi": p.get("doi"),
                "url": p.get("url"),
                "abstract_snippet": p.get("abstract", "")[:200],
                "added_by": "lab-field-trend",
                "added_date": TODAY
            })
        print(f"{green('✓')} {len(all_papers)} papers written to research-graph.jsonl")

    # Notify
    if not args.no_notify and notify_channel == "discord":
        sent = send_discord(cfg, discord_summary, len(all_papers), fields)
        print(f"{green('✓') if sent else yellow('⚠')}  Discord notification {'sent' if sent else 'failed (check channel config)'}")

    # XP
    award_xp("field_trend_digest", 25)
    print(f"{green('✓')} +25 XP awarded")
    print(f"\n{bold(green('✅ Digest complete!'))} {len(all_papers)} papers · {len(clusters)} themes\n")


def main():
    parser = argparse.ArgumentParser(description="LabOS field trend digest")
    parser.add_argument("--query", type=str, help="Override search query")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    parser.add_argument("--dry-run", action="store_true", help="Print without saving or notifying")
    parser.add_argument("--no-notify", action="store_true", help="Save but skip Discord")
    args = parser.parse_args()
    run_digest(args)

if __name__ == "__main__":
    main()
