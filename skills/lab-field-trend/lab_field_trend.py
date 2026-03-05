#!/usr/bin/env python3
"""
lab-field-trend — Weekly field intelligence digest for LabOS
Usage:
  python3 lab_field_trend.py                 # run digest (uses config fields)
  python3 lab_field_trend.py --query "topic" # override with custom query
  python3 lab_field_trend.py --days 14       # look back N days (default 7)
  python3 lab_field_trend.py --dry-run       # print without saving/notifying
  python3 lab_field_trend.py --no-notify     # save but skip Discord
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, upsert_node, now_iso, today_str, short_hash,
    LAB_DIR, SESSIONS_DIR,
)


NOW   = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")


# ─── HTTP ─────────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 15) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LabOS/1.0 (academic research)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def http_get_json(url: str) -> dict | list | None:
    raw = http_get(url)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


# ─── PubMed ───────────────────────────────────────────────────────────────────

def search_pubmed(query: str, days: int, limit: int) -> list[dict]:
    since = (NOW - timedelta(days=days)).strftime("%Y/%m/%d")
    params = {
        "db": "pubmed",
        "term": f"({query}) AND {since}[PDAT]",
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance",
    }
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    if not data:
        return []
    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    fetch_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        f"db=pubmed&id={','.join(ids)}&retmode=xml"
    )
    xml_raw = http_get(fetch_url)
    if not xml_raw:
        return []

    papers = []
    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return []

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid    = article.findtext(".//PMID", "")
            title   = article.findtext(".//ArticleTitle", "").strip()
            abs_els = article.findall(".//AbstractText")
            abstract = " ".join((a.text or "") for a in abs_els).strip()
            authors = []
            for a in article.findall(".//Author")[:3]:
                ln = a.findtext("LastName", "")
                fn = a.findtext("ForeName", "")
                if ln:
                    authors.append(f"{ln} {fn[:1]}." if fn else ln)
            year    = article.findtext(".//PubDate/Year", "") or article.findtext(".//PubDate/MedlineDate", "")[:4]
            journal = article.findtext(".//Journal/Title", "") or article.findtext(".//MedlineTA", "")
            doi = ""
            for id_el in article.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text or ""
            papers.append({
                "source": "pubmed", "pmid": pmid, "title": title,
                "abstract": abstract[:600], "authors": authors,
                "year": year, "journal": journal, "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "citations": 0, "open_access": False,
            })
        except Exception:
            continue
    return papers


# ─── OpenAlex ─────────────────────────────────────────────────────────────────

def search_openalex(query: str, days: int, limit: int) -> list[dict]:
    since = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "search": query,
        "filter": f"from_publication_date:{since}",
        "sort": "relevance_score:desc",
        "per-page": limit,
        "select": "title,authorships,publication_year,primary_location,doi,abstract_inverted_index,open_access",
        "mailto": "labos@example.com",
    }
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    if not data:
        return []

    papers = []
    for r in data.get("results", []):
        # Reconstruct abstract
        abstract = ""
        inv = r.get("abstract_inverted_index") or {}
        if inv:
            positions = [(pos, word) for word, pos_list in inv.items() for pos in pos_list]
            positions.sort()
            abstract = " ".join(w for _, w in positions[:80])

        authors = [
            a.get("author", {}).get("display_name", "")
            for a in r.get("authorships", [])[:3]
            if a.get("author", {}).get("display_name")
        ]
        loc     = r.get("primary_location") or {}
        journal = (loc.get("source") or {}).get("display_name", "")
        doi_raw = r.get("doi", "") or ""
        doi     = doi_raw.replace("https://doi.org/", "")

        papers.append({
            "source": "openalex", "title": r.get("title", "").strip(),
            "abstract": abstract[:600], "authors": authors,
            "year": str(r.get("publication_year", "")), "journal": journal,
            "doi": doi, "url": doi_raw or "", "citations": 0,
            "open_access": r.get("open_access", {}).get("is_oa", False),
        })
    return papers


# ─── arXiv ────────────────────────────────────────────────────────────────────

def search_arxiv(query: str, days: int, limit: int) -> list[dict]:
    params = {
        "search_query": f"all:{query}",
        "start": 0, "max_results": limit,
        "sortBy": "submittedDate", "sortOrder": "descending",
    }
    url = f"https://export.arxiv.org/api/query?{urllib.parse.urlencode(params)}"
    xml_raw = http_get(url)
    if not xml_raw:
        return []

    ns     = {"atom": "http://www.w3.org/2005/Atom"}
    cutoff = NOW - timedelta(days=days)
    papers = []
    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        return []

    for entry in root.findall("atom:entry", ns):
        try:
            pub_str   = entry.findtext("atom:published", "", ns)
            published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if published < cutoff:
                continue
            title    = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            authors  = [
                a.findtext("atom:name", "", ns)
                for a in entry.findall("atom:author", ns)[:3]
                if a.findtext("atom:name", "", ns)
            ]
            papers.append({
                "source": "arxiv", "arxiv_id": arxiv_id, "title": title,
                "abstract": abstract[:600], "authors": authors,
                "year": str(published.year), "journal": "arXiv",
                "doi": f"arxiv:{arxiv_id}", "url": f"https://arxiv.org/abs/{arxiv_id}",
                "citations": 0, "open_access": True,
            })
        except Exception:
            continue
    return papers


# ─── Dedup & score ────────────────────────────────────────────────────────────

def dedup(papers: list[dict]) -> list[dict]:
    seen_dois, seen_titles, result = set(), set(), []
    for p in papers:
        doi       = (p.get("doi") or "").lower().strip()
        title_key = re.sub(r"\W+", "", (p.get("title") or "").lower())[:60]
        if doi and doi in seen_dois:
            continue
        if title_key and title_key in seen_titles:
            continue
        if doi:
            seen_dois.add(doi)
        if title_key:
            seen_titles.add(title_key)
        result.append(p)
    return result


def score_paper(paper: dict, query: str, fields: list[str]) -> int:
    query_words = set(query.lower().split())
    field_words = set(" ".join(fields).lower().split())
    title       = (paper.get("title") or "").lower()
    abstract    = (paper.get("abstract") or "").lower()
    title_hits    = sum(1 for w in query_words if w in title)
    abstract_hits = sum(1 for w in query_words if w in abstract)
    field_hits    = sum(1 for w in field_words if w in title or w in abstract)
    try:
        year    = int(paper.get("year") or 0)
        recency = 10 if year >= 2023 else (7 if year >= 2021 else 0)
    except ValueError:
        recency = 0
    return (
        min(35, title_hits * 12) +
        min(35, abstract_hits * 3) +
        min(15, field_hits * 5) +
        recency
    )


# ─── LLM clustering ───────────────────────────────────────────────────────────

def cluster_with_llm(papers: list[dict], fields: list[str]) -> dict[str, list[dict]]:
    """Ask LLM to group papers into themes. Falls back to keyword clustering."""
    titles_block = "\n".join(f"{i+1}. {p['title']}" for i, p in enumerate(papers))
    prompt = (
        f"Group these {len(papers)} academic paper titles into 3-5 thematic clusters. "
        f"Research fields: {', '.join(fields)}.\n\n"
        f"{titles_block}\n\n"
        f"Respond ONLY as JSON: {{\"clusters\": {{\"Theme Name\": [1,2,5], \"Theme 2\": [3,4]}}}} "
        f"(use 1-based indices). No commentary."
    )
    raw = call_llm(prompt)
    try:
        cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data    = json.loads(cleaned)
        clusters_raw = data.get("clusters", {})
        result  = {}
        for theme, indices in clusters_raw.items():
            group = []
            for idx in indices:
                try:
                    group.append(papers[int(idx) - 1])
                except (IndexError, ValueError):
                    pass
            if group:
                result[theme] = group
        if result:
            return result
    except Exception:
        pass

    # Fallback: keyword clustering
    return _keyword_cluster(papers, fields)


def _keyword_cluster(papers: list[dict], fields: list[str]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = {}
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        matched = next(
            (f for f in fields if f.lower() in text or any(w in text for w in f.lower().split())),
            None
        )
        theme = matched or "General / Cross-cutting"
        clusters.setdefault(theme, []).append(p)
    return clusters


# ─── Highlight generation ─────────────────────────────────────────────────────

def generate_highlights(papers: list[dict], query: str) -> dict:
    """Generate top-level digest highlights via LLM."""
    titles_block = "\n".join(
        f"- {p['title']} ({p.get('year', '?')}, {p.get('journal', '?')})"
        for p in papers[:20]
    )
    prompt = (
        f"Based on these recent papers in the field ({query}), generate a research digest.\n\n"
        f"{titles_block}\n\n"
        f"Respond ONLY as JSON with this exact structure:\n"
        f"{{\n"
        f'  "top_breakthroughs": ["1 sentence each, max 3"],\n'
        f'  "emerging_methods": ["method name: 1 sentence, max 3"],\n'
        f'  "open_gaps": ["1 sentence gap, max 2"]\n'
        f"}}"
    )
    raw = call_llm(prompt)
    try:
        cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return json.loads(cleaned)
    except Exception:
        return {"top_breakthroughs": [], "emerging_methods": [], "open_gaps": []}


# ─── Format output ────────────────────────────────────────────────────────────

def format_paper_line(p: dict) -> str:
    oa      = "🔓" if p.get("open_access") else ""
    src_icon = {"pubmed": "📗", "openalex": "📘", "arxiv": "📙"}.get(p.get("source", ""), "📄")
    authors  = p.get("authors", [])
    auth_str = (authors[0] + " et al.") if len(authors) > 1 else (authors[0] if authors else "?")
    return (
        f"  {src_icon}{oa} **{p['title'][:70]}{'…' if len(p['title'])>70 else ''}**\n"
        f"     {auth_str} · {p.get('journal','?')} · {p.get('year','?')}"
        + (f"\n     > {p['abstract'][:180]}…" if p.get("abstract") else "")
    )


def print_digest(clusters: dict, highlights: dict, n_papers: int, query: str, days: int):
    section_header(f"📰 LabOS Weekly Digest — {TODAY}")
    print(f"   Query: {query} | Last {days} days | {n_papers} papers\n")

    if highlights.get("top_breakthroughs"):
        print("🔥 **Top Breakthroughs**")
        for b in highlights["top_breakthroughs"]:
            print(f"   • {b}")

    if highlights.get("emerging_methods"):
        print("\n📈 **Emerging Methods**")
        for m in highlights["emerging_methods"]:
            print(f"   • {m}")

    if highlights.get("open_gaps"):
        print("\n💡 **Open Gaps**")
        for g in highlights["open_gaps"]:
            print(f"   • {g}")

    print()
    for theme, papers in clusters.items():
        print(f"\n{'─'*60}")
        print(f"**{theme}** — {len(papers)} paper(s)")
        for p in papers[:4]:
            print(format_paper_line(p))
        if len(papers) > 4:
            print(f"  … and {len(papers)-4} more")


# ─── Obsidian save ────────────────────────────────────────────────────────────

def save_obsidian(clusters: dict, highlights: dict, papers: list[dict],
                  query: str, days: int, config: dict) -> Path:
    vault = config.get("obsidian_vault", "")
    if vault:
        digest_dir = Path(vault) / "Research" / "Weekly-Digests"
    else:
        digest_dir = LAB_DIR / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Field Digest — {TODAY}",
        f"> Query: `{query}` | Last {days} days | {len(papers)} papers",
        "",
    ]

    if highlights.get("top_breakthroughs"):
        lines += ["## 🔥 Top Breakthroughs", ""]
        for b in highlights["top_breakthroughs"]:
            lines.append(f"- {b}")
        lines.append("")

    if highlights.get("emerging_methods"):
        lines += ["## 📈 Emerging Methods", ""]
        for m in highlights["emerging_methods"]:
            lines.append(f"- {m}")
        lines.append("")

    if highlights.get("open_gaps"):
        lines += ["## 💡 Open Gaps", ""]
        for g in highlights["open_gaps"]:
            lines.append(f"- {g}")
        lines.append("")

    lines += ["## Papers by Theme", ""]
    for theme, theme_papers in clusters.items():
        lines.append(f"### {theme}")
        for p in theme_papers:
            oa = " 🔓" if p.get("open_access") else ""
            auth = p["authors"][0] + " et al." if len(p.get("authors",[])) > 1 else (p["authors"][0] if p.get("authors") else "?")
            lines += [
                f"#### {p['title']}{oa}",
                f"*{auth} · {p.get('journal','?')} · {p.get('year','?')}*",
                f"DOI: {p.get('doi','')}",
                "",
                p.get("abstract", "")[:300],
                "",
            ]

    lines += ["---", f"*Generated by LabOS lab-field-trend · {NOW.strftime('%Y-%m-%d %H:%M UTC')}*"]

    path = digest_dir / f"{TODAY}-digest.md"
    path.write_text("\n".join(lines))
    return path


# ─── Discord notify ───────────────────────────────────────────────────────────

def build_discord_message(highlights: dict, clusters: dict, n_papers: int, query: str) -> str:
    lines = [
        f"📰 **LabOS Field Digest** — {TODAY}",
        f"🔬 `{query}` | {n_papers} papers",
        "",
    ]
    if highlights.get("top_breakthroughs"):
        lines.append("🔥 **Breakthroughs:**")
        for b in highlights["top_breakthroughs"][:2]:
            lines.append(f"  • {b}")
    if highlights.get("emerging_methods"):
        lines.append("\n📈 **Methods trending:**")
        for m in highlights["emerging_methods"][:2]:
            lines.append(f"  • {m}")
    for theme, papers in list(clusters.items())[:2]:
        lines.append(f"\n**{theme}** ({len(papers)}p)")
        for p in papers[:2]:
            lines.append(f"  • {p['title'][:65]}{'…' if len(p['title'])>65 else ''}")
    lines.append("\n*(full digest saved to Obsidian)*")
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS field trend digest")
    parser.add_argument("--query",        help="Override search query")
    parser.add_argument("--days",  type=int, default=7, help="Lookback days (default 7)")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--no-notify",    action="store_true")
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    config  = load_config()
    fields  = config.get("fields", ["neuroscience"])
    databases = config.get("databases", ["pubmed", "openalex", "arxiv"])
    batch   = config.get("papers_per_batch", 5)

    # Build query
    query = args.query or " OR ".join(f'"{f}"' for f in fields[:4])

    section_header(f"🔬 LabOS Field Trend Digest — last {args.days} days")
    print(f"   Query: {query}")
    print(f"   Fields: {', '.join(fields)}\n")

    # ── Fetch ──
    all_papers = []
    per_src    = max(batch * 3, 15)

    if "pubmed" in databases:
        progress("Searching PubMed…", "📗")
        all_papers += search_pubmed(query, args.days, per_src)
        time.sleep(0.4)

    if "openalex" in databases:
        progress("Searching OpenAlex…", "📘")
        all_papers += search_openalex(query, args.days, per_src)

    if "arxiv" in databases:
        progress("Searching arXiv…", "📙")
        all_papers += search_arxiv(query, args.days, per_src)

    if not all_papers:
        print("⚠️  No papers found. Try --days 14 or a broader --query.")
        return

    # ── Dedup + score ──
    progress(f"Deduplicating {len(all_papers)} raw results…", "🔀")
    papers = dedup(all_papers)
    for p in papers:
        p["relevance_score"] = score_paper(p, query, fields)
    papers.sort(key=lambda p: p["relevance_score"], reverse=True)
    papers = papers[:40]  # cap for digest

    print(f"   ✓ {len(papers)} unique papers after dedup\n")

    # ── Checkpoint: quick preview before LLM work ──
    if not args.no_interactive:
        print("📋 Top papers by relevance:")
        for i, p in enumerate(papers[:5], 1):
            print(f"  {i}. [{p['relevance_score']:3d}%] {p['title'][:65]} ({p.get('year','?')})")
        try:
            go = confirm(f"Generate full digest for all {len(papers)} papers?", default=True)
            if not go:
                print("Aborted.")
                return
        except CheckpointAborted:
            return

    # ── LLM: cluster + highlights ──
    progress("Clustering papers into themes…", "🗂️")
    clusters = cluster_with_llm(papers, fields)

    progress("Generating digest highlights…", "✨")
    highlights = generate_highlights(papers, query)

    # ── Print ──
    print_digest(clusters, highlights, len(papers), query, args.days)

    if args.dry_run:
        print("\n[DRY RUN] Nothing saved.")
        return

    # ── Save ──
    obs_path = save_obsidian(clusters, highlights, papers, query, args.days, config)
    progress(f"Saved to Obsidian: {obs_path}", "💾")

    # Update research graph
    nodes = load_graph()
    for p in papers:
        node = {
            "type": "Paper",
            "id": f"paper_{short_hash(p.get('doi','') or p.get('title',''))}",
            "title": p.get("title", ""),
            "doi": p.get("doi", ""),
            "authors": p.get("authors", []),
            "year": p.get("year", ""),
            "journal": p.get("journal", ""),
            "abstract": p.get("abstract", "")[:300],
            "relevance_score": p.get("relevance_score", 0),
            "source": p.get("source", ""),
            "open_access": p.get("open_access", False),
            "added_by": "lab-field-trend",
            "added": now_iso(),
            "projects": [],
        }
        nodes = upsert_node(nodes, node)
    save_graph(nodes)
    progress(f"{len(papers)} papers written to research graph", "🗂️")

    # ── Notify via Discord ──
    if not args.no_notify:
        notify_channel = config.get("notify_channel", "")
        if notify_channel == "discord":
            msg = build_discord_message(highlights, clusters, len(papers), query)
            print(f"\n[NOTIFY:discord] {msg}")

    # ── Interactive: follow-up ──
    if not args.no_interactive:
        try:
            action = checkpoint(
                "What next? Go deeper on a paper, search a topic, or done?",
                options=["paper", "search", "done"],
                default="done",
                emoji="🔎",
            )
            if action.lower() == "paper":
                pick = checkpoint(
                    "Which paper number?",
                    options=[str(i) for i in range(1, min(6, len(papers)+1))],
                    emoji="📄",
                )
                try:
                    p = papers[int(pick) - 1]
                    print(f"\n📄 **{p['title']}**")
                    print(f"   {p.get('abstract','No abstract.')}")
                    print(f"   DOI: {p.get('doi','')} | URL: {p.get('url','')}")
                except (ValueError, IndexError):
                    pass
        except CheckpointAborted:
            pass

    # ── Session log ──
    summary = "\n".join(f"- {p['title'][:70]} ({p.get('year','')})" for p in papers[:10])
    log_session("lab-field-trend", "global", f"Query: {query}\nPapers: {len(papers)}\n\n{summary}")

    # ── XP ──
    award_xp(25, "📰 Stayed Current")
    print("\n✅ Digest complete.\n")


if __name__ == "__main__":
    main()
