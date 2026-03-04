#!/usr/bin/env python3
"""
lab-lit-scout — deep on-demand literature search
Searches PubMed, OpenAlex, arXiv, and Semantic Scholar for a query or hypothesis.
Scores relevance, generates structured summaries, saves to Obsidian, links to research graph.

Usage:
  python3 lab_lit_scout.py --query "speech-music neural coupling"
  python3 lab_lit_scout.py --query "EEG infant speech" --project "infant-hearing-assessment"
  python3 lab_lit_scout.py --query "auditory brainstem response" --limit 15 --since 2023-01-01
  python3 lab_lit_scout.py --query "neural coupling ASD" --dry-run
  python3 lab_lit_scout.py --query "subcortical speech encoding" --sort citations
"""

import argparse
import json
import os
import re
import sys
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE      = Path(os.environ.get("LABOS_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
LAB_DIR        = WORKSPACE / "LabOS"
LAB_CONFIG     = LAB_DIR / "LAB_CONFIG.json"
RESEARCH_GRAPH = LAB_DIR / "research-graph.jsonl"
XP_FILE        = LAB_DIR / "xp.json"
XP_ENGINE      = LAB_DIR / "gamification" / "xp_engine.py"

NOW   = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")

# ── Helpers ────────────────────────────────────────────────────────────────────
def bold(s):   return f"\033[1m{s}\033[0m"
def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def cyan(s):   return f"\033[36m{s}\033[0m"
def dim(s):    return f"\033[2m{s}\033[0m"

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]

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
    if Path(path).exists():
        with open(path) as f:
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except Exception:
                    pass
    return records

def http_get(url, timeout=20):
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

# ── Relevance scoring ──────────────────────────────────────────────────────────
def score_paper(paper, query_tokens, user_fields):
    """
    Score relevance of a paper to the query.
    Returns float 0.0–1.0
    """
    text = " ".join([
        paper.get("title", "") * 3,   # title weighted 3x
        paper.get("abstract", ""),
        paper.get("abstract_snippet", ""),
        paper.get("journal", "")
    ]).lower()

    # Query token overlap
    query_hits = sum(1 for t in query_tokens if t in text)
    query_score = min(query_hits / max(len(query_tokens), 1), 1.0)

    # Field relevance bonus
    field_hits = sum(1 for f in user_fields if f.lower() in text)
    field_score = min(field_hits / max(len(user_fields), 1), 0.5)

    # Recency bonus (papers from last 2 years score higher)
    year = int(paper.get("year", "2000") or "2000")
    recency = max(0, min((year - 2020) / 5, 0.3))

    # Open access bonus
    oa_bonus = 0.05 if paper.get("open_access") else 0

    score = (query_score * 0.6) + (field_score * 0.25) + recency + oa_bonus
    return round(min(score, 1.0), 3)

# ── PubMed ─────────────────────────────────────────────────────────────────────
def search_pubmed(query, limit=20, since=None):
    date_filter = f" AND {since.replace('-', '/')}[PDAT]:{TODAY.replace('-', '/')}[PDAT]" if since else ""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": f"({query}){date_filter}",
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance"
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

    fetch_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        f"db=pubmed&id={','.join(ids)}&retmode=xml"
    )
    xml_raw = http_get(fetch_url)
    return _parse_pubmed_xml(xml_raw) if xml_raw else []

def _parse_pubmed_xml(xml_raw):
    papers = []
    try:
        root = ET.fromstring(xml_raw)
    except Exception:
        return []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.findtext(".//PMID", "")
            title = (article.findtext(".//ArticleTitle", "") or "").strip()
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join((p.text or "") for p in abstract_parts).strip()
            authors = []
            for a in article.findall(".//Author")[:5]:
                ln = a.findtext("LastName", "")
                fn = a.findtext("ForeName", "")
                if ln:
                    authors.append(f"{ln} {fn[0]}." if fn else ln)
            year = (article.findtext(".//PubDate/Year") or
                    (article.findtext(".//PubDate/MedlineDate") or "")[:4] or "")
            journal = article.findtext(".//Journal/Title", "") or article.findtext(".//MedlineTA", "")
            doi = ""
            for id_el in article.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text or ""
            mesh = [m.findtext("DescriptorName", "") for m in article.findall(".//MeshHeading")][:8]
            papers.append({
                "source": "pubmed", "pmid": pmid, "title": title,
                "abstract": abstract, "authors": authors, "year": year,
                "journal": journal, "doi": doi, "mesh": mesh,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "open_access": False
            })
        except Exception:
            continue
    return papers

# ── OpenAlex ───────────────────────────────────────────────────────────────────
def search_openalex(query, limit=15, since=None, sort="relevance_score"):
    filters = []
    if since:
        filters.append(f"from_publication_date:{since}")
    filter_str = ",".join(filters) if filters else ""

    params = {
        "search": query,
        "per-page": limit,
        "sort": f"{sort}:desc",
        "select": "id,title,authorships,publication_year,primary_location,doi,abstract_inverted_index,open_access,cited_by_count,concepts",
        "mailto": "labos@research.ai"
    }
    if filter_str:
        params["filter"] = filter_str

    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
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
            word_positions = [(pos, word) for word, positions in inv.items() for pos in positions]
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions[:120])

        authors = [a.get("author", {}).get("display_name", "") for a in r.get("authorships", [])[:5]]
        authors = [a for a in authors if a]

        loc = r.get("primary_location") or {}
        journal = (loc.get("source") or {}).get("display_name", "")
        doi = (r.get("doi") or "").replace("https://doi.org/", "")

        concepts = [c.get("display_name", "") for c in r.get("concepts", [])[:5]]

        papers.append({
            "source": "openalex",
            "id": r.get("id", ""),
            "title": (r.get("title") or "").strip(),
            "abstract": abstract,
            "authors": authors,
            "year": str(r.get("publication_year", "")),
            "journal": journal,
            "doi": doi,
            "url": r.get("doi") or r.get("id", ""),
            "open_access": r.get("open_access", {}).get("is_oa", False),
            "citations": r.get("cited_by_count", 0),
            "concepts": concepts
        })
    return papers

# ── arXiv ──────────────────────────────────────────────────────────────────────
def search_arxiv(query, limit=10, since=None):
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending"
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    raw = http_get(url)
    if not raw:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers = []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []

    for entry in root.findall("atom:entry", ns):
        try:
            published_str = entry.findtext("atom:published", "", ns)
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            if since:
                cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
                if published < cutoff:
                    continue
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)[:5]]
            categories = [c.get("term", "") for c in entry.findall("atom:category", ns)]
            papers.append({
                "source": "arxiv", "arxiv_id": arxiv_id, "title": title,
                "abstract": abstract, "authors": authors,
                "year": str(published.year), "journal": "arXiv",
                "doi": "", "url": f"https://arxiv.org/abs/{arxiv_id}",
                "open_access": True, "categories": categories
            })
        except Exception:
            continue
    return papers

# ── Semantic Scholar ───────────────────────────────────────────────────────────
def search_semantic_scholar(query, limit=10, since=None):
    params = urllib.parse.urlencode({
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,abstract,externalIds,journal,citationCount,openAccessPdf,isOpenAccess,tldr"
    })
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    raw = http_get(url)
    if not raw:
        return []
    try:
        results = json.loads(raw).get("data", [])
    except Exception:
        return []

    papers = []
    for r in results:
        if since and str(r.get("year", "9999")) < since[:4]:
            continue
        authors = [a.get("name", "") for a in r.get("authors", [])[:5]]
        doi = r.get("externalIds", {}).get("DOI", "")
        pmid = r.get("externalIds", {}).get("PubMed", "")
        tldr = (r.get("tldr") or {}).get("text", "")
        papers.append({
            "source": "semanticscholar",
            "ss_id": r.get("paperId", ""),
            "title": r.get("title", "").strip(),
            "abstract": r.get("abstract", "") or tldr,
            "tldr": tldr,
            "authors": authors,
            "year": str(r.get("year", "")),
            "journal": (r.get("journal") or {}).get("name", ""),
            "doi": doi,
            "url": f"https://www.semanticscholar.org/paper/{r.get('paperId', '')}",
            "open_access": r.get("isOpenAccess", False),
            "citations": r.get("citationCount", 0)
        })
    return papers

# ── Dedup ──────────────────────────────────────────────────────────────────────
def dedup(papers):
    seen = {}
    result = []
    for p in papers:
        key = re.sub(r"[^a-z0-9]", "", p["title"].lower())[:50]
        if key not in seen:
            seen[key] = True
            result.append(p)
    return result

# ── Already in library? ────────────────────────────────────────────────────────
def get_known_dois():
    records = load_jsonl(RESEARCH_GRAPH)
    return {r.get("doi", "") for r in records if r.get("type") == "Paper" and r.get("doi")}

# ── Format paper summary ───────────────────────────────────────────────────────
def format_paper_full(p, rank, style="bullet", known_dois=None):
    known_dois = known_dois or set()
    authors = ", ".join(p["authors"][:3])
    if len(p["authors"]) > 3:
        authors += " et al."
    year = p.get("year", "")
    journal = p.get("journal", p.get("source", ""))
    url = p.get("url", "")
    doi = p.get("doi", "")
    citations = p.get("citations")
    open_access = p.get("open_access", False)

    source_icon = {"pubmed": "📗", "openalex": "📘", "arxiv": "📙",
                   "semanticscholar": "📕"}.get(p.get("source", ""), "📄")
    oa_badge = " 🔓" if open_access else ""
    already = " ✅" if doi and doi in known_dois else ""
    cite_str = f" | {citations} citations" if citations else ""
    tldr = p.get("tldr", "")

    abstract = p.get("abstract", "") or p.get("abstract_snippet", "")
    abstract_short = abstract[:300] + "..." if len(abstract) > 300 else abstract

    lines = [
        f"### {rank}. {source_icon}{oa_badge}{already} {p['title']}",
        f"**{authors}** ({year}) — *{journal}*{cite_str}",
        f"[🔗 Link]({url})" + (f" | [DOI](https://doi.org/{doi})" if doi else ""),
        "",
    ]

    if tldr:
        lines += [f"**TL;DR:** {tldr}", ""]
    elif abstract_short:
        lines += [f"> {abstract_short}", ""]

    # Mesh or concepts as tags
    tags = p.get("mesh", []) or p.get("concepts", []) or p.get("categories", [])
    if tags:
        tag_str = " ".join(f"`{t}`" for t in tags[:5] if t)
        lines += [f"Tags: {tag_str}", ""]

    return "\n".join(lines)

# ── Contradiction checker ──────────────────────────────────────────────────────
NEGATION_MARKERS = [
    "no significant", "not significant", "failed to", "contrary to",
    "inconsistent with", "challenges the", "contradicts", "refutes",
    "no evidence", "null result", "negative result", "did not replicate",
    "lack of", "absence of", "does not support", "no effect",
    "no difference", "no association", "no correlation", "not associated",
    "argue against", "questions the", "challenges current"
]

def check_contradictions(papers, hypotheses):
    hits = []
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        if any(m in text for m in NEGATION_MARKERS):
            for h in hypotheses:
                hyp_tokens = set(re.findall(r'\b[a-z]{4,}\b', h["hypothesis"].lower()))
                paper_tokens = set(re.findall(r'\b[a-z]{4,}\b', text))
                overlap = hyp_tokens & paper_tokens
                if len(overlap) >= 2:
                    hits.append({
                        "paper": p,
                        "hypothesis": h["hypothesis"],
                        "project": h["project"],
                        "overlap": list(overlap)[:4]
                    })
    return hits

# ── Write to Obsidian ──────────────────────────────────────────────────────────
def save_to_obsidian(cfg, query, papers, report_md):
    vault = cfg.get("obsidian_vault")
    if not vault or not Path(vault).exists():
        return False
    lit_dir = Path(vault) / "Research" / "Literature"
    lit_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{TODAY}-{slugify(query)}.md"
    (lit_dir / fname).write_text(report_md)
    print(f"  {green('✓')} Saved: Research/Literature/{fname}")
    return True

# ── Save to Zotero (basic RIS export) ─────────────────────────────────────────
def export_ris(papers, path):
    """Write a .ris file that Zotero can import."""
    lines = []
    for p in papers:
        if not p.get("doi") and not p.get("pmid"):
            continue
        lines += [
            "TY  - JOUR",
            f"TI  - {p.get('title', '')}",
        ]
        for a in p.get("authors", []):
            lines.append(f"AU  - {a}")
        if p.get("year"):
            lines.append(f"PY  - {p['year']}")
        if p.get("journal"):
            lines.append(f"JO  - {p['journal']}")
        if p.get("doi"):
            lines.append(f"DO  - {p['doi']}")
        if p.get("url"):
            lines.append(f"UR  - {p['url']}")
        if p.get("abstract"):
            lines.append(f"AB  - {p['abstract'][:500]}")
        lines.append("ER  - ")
        lines.append("")
    Path(path).write_text("\n".join(lines))

# ── Link to project in research graph ─────────────────────────────────────────
def link_to_project(project_slug, paper_ids):
    """Append a PaperLink node connecting papers to a project."""
    for pid in paper_ids:
        append_jsonl(RESEARCH_GRAPH, {
            "type": "PaperLink",
            "project_id": f"proj_{project_slug}",
            "paper_ref": pid,
            "linked_by": "lab-lit-scout",
            "linked_date": TODAY
        })

# ── Main ───────────────────────────────────────────────────────────────────────
def run(args):
    cfg = load_json(LAB_CONFIG)
    if not cfg:
        print("❌ No LAB_CONFIG.json found. Run lab-init first.")
        sys.exit(1)

    query   = args.query
    limit   = args.limit
    since   = args.since
    project = args.project
    sort_by = args.sort
    style   = cfg.get("summary_style", "bullet")
    fields  = cfg.get("fields", [])
    databases = cfg.get("databases", ["pubmed", "openalex", "arxiv"])

    print(f"\n{bold('🔍 LabOS Literature Scout')}")
    print(f"{dim(f'Query: {query}')}")
    if project: print(f"{dim(f'Project: {project}')}")
    if since:   print(f"{dim(f'Since: {since}')}")
    print()

    # Query tokenization for scoring
    query_tokens = set(re.findall(r'\b[a-z]{3,}\b', query.lower()))

    # Search all configured databases
    all_papers = []

    if "pubmed" in databases:
        print(f"  Searching PubMed...", end="", flush=True)
        p = search_pubmed(query, limit=limit * 2, since=since)
        print(f" {green(str(len(p)))} results")
        all_papers.extend(p)

    if "openalex" in databases:
        oa_sort = "cited_by_count" if sort_by == "citations" else "relevance_score"
        print(f"  Searching OpenAlex...", end="", flush=True)
        p = search_openalex(query, limit=limit * 2, since=since, sort=oa_sort)
        print(f" {green(str(len(p)))} results")
        all_papers.extend(p)

    if "arxiv" in databases:
        print(f"  Searching arXiv...", end="", flush=True)
        p = search_arxiv(query, limit=limit, since=since)
        print(f" {green(str(len(p)))} results")
        all_papers.extend(p)

    if "semanticscholar" in databases:
        print(f"  Searching Semantic Scholar...", end="", flush=True)
        p = search_semantic_scholar(query, limit=limit, since=since)
        print(f" {green(str(len(p)))} results")
        all_papers.extend(p)

    all_papers = dedup(all_papers)
    print(f"\n  {bold(str(len(all_papers)))} unique papers found")

    if not all_papers:
        print(yellow("\n⚠️  No results. Try a broader query or remove --since."))
        return

    # Score & sort
    known_dois = get_known_dois()
    for p in all_papers:
        p["_score"] = score_paper(p, query_tokens, fields)
        p["_known"] = bool(p.get("doi") and p.get("doi") in known_dois)

    if sort_by == "citations":
        all_papers.sort(key=lambda x: x.get("citations", 0), reverse=True)
    elif sort_by == "date":
        all_papers.sort(key=lambda x: x.get("year", "0"), reverse=True)
    else:
        all_papers.sort(key=lambda x: x["_score"], reverse=True)

    top_papers = all_papers[:limit]

    # Check hypotheses
    hypotheses = []
    for r in load_jsonl(RESEARCH_GRAPH):
        if r.get("type") == "Project":
            for h in r.get("hypotheses", []):
                if h:
                    hypotheses.append({"project": r["name"], "hypothesis": h})

    contradictions = check_contradictions(top_papers, hypotheses) if hypotheses else []

    # ── Print terminal output ──────────────────────────────────────────────────
    print(f"\n{'-'*60}")
    for i, p in enumerate(top_papers, 1):
        authors_short = (p["authors"][0] + " et al." if len(p["authors"]) > 1
                         else (p["authors"][0] if p["authors"] else "?"))
        score_bar = "█" * int(p["_score"] * 10) + "░" * (10 - int(p["_score"] * 10))
        known_mark = f" {green('✅ in library')}" if p["_known"] else ""
        oa_mark = " 🔓" if p.get("open_access") else ""
        cite_str = f" | {p['citations']} cited" if p.get("citations") else ""
        print(f"\n{bold(f'{i}.')} {p['title'][:72]}{'...' if len(p['title'])>72 else ''}")
        print(f"   {dim(authors_short + ' · ' + p.get('journal','') + ' · ' + str(p.get('year',''))+ cite_str)}")
        print(f"   Relevance: {score_bar} {p['_score']:.2f}{oa_mark}{known_mark}")
        if p.get("tldr"):
            print(f"   {dim('TL;DR: ' + p['tldr'][:120])}")

    if contradictions:
        print(f"\n{bold(yellow(f'⚠️  {len(contradictions)} potential contradiction(s) with your hypotheses:'))}")
        for c in contradictions:
            print(f"  [{c['project']}] {c['paper']['title'][:70]}...")
            print(f"  {dim('Hypothesis: ' + c['hypothesis'][:80])}")
    print(f"{'-'*60}")

    if args.dry_run:
        print(f"\n{yellow('[dry-run] Skipping save.')}")
        return

    # ── Build markdown report ──────────────────────────────────────────────────
    report_lines = [
        f"# Literature Search: {query}",
        f"",
        f"> Date: {TODAY} | {len(top_papers)} papers | Sort: {sort_by}",
        (f"> Project: `{project}`" if project else ""),
        f"",
        f"---",
        f"",
    ]

    if contradictions:
        report_lines += [
            "## ⚠️ Hypothesis Contradictions",
            ""
        ]
        for c in contradictions:
            report_lines += [
                f"**{c['paper']['title']}** may challenge:",
                f"> {c['hypothesis']}",
                f"*Shared terms: {', '.join(c['overlap'])}*",
                ""
            ]
        report_lines += ["---", ""]

    report_lines += [f"## Results ({len(top_papers)} papers)", ""]
    for i, p in enumerate(top_papers, 1):
        report_lines.append(format_paper_full(p, i, style=style, known_dois=known_dois))

    report_lines += [
        "---",
        f"*Generated by LabOS lab-lit-scout · {NOW.strftime('%Y-%m-%d %H:%M UTC')}*"
    ]
    report_md = "\n".join(report_lines)

    # ── Save to Obsidian ───────────────────────────────────────────────────────
    vault = cfg.get("obsidian_vault")
    query_slug = slugify(query)
    if vault and Path(vault).exists():
        lit_dir = Path(vault) / "Research" / "Literature"
        lit_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{TODAY}-{query_slug}.md"
        out_path = lit_dir / fname
        out_path.write_text(report_md)
        print(f"\n  {green('✓')} Report saved to Obsidian:")
        print(f"     {bold(str(out_path))}")
    else:
        # Fallback: save to sessions folder
        fallback = LAB_DIR / "sessions" / f"{TODAY}-{query_slug}.md"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(report_md)
        print(f"\n  {yellow('⚠')}  No Obsidian vault configured — saved to:")
        print(f"     {bold(str(fallback))}")
        print(f"     Run {cyan('lab-init --update-prefs')} to connect your vault.")

    # ── Interactive Zotero prompt ──────────────────────────────────────────────
    # Always ask — even if Zotero not configured yet
    ris_path = LAB_DIR / "sessions" / f"{TODAY}-{query_slug}.ris"
    ris_path.parent.mkdir(parents=True, exist_ok=True)
    export_ris(top_papers, ris_path)   # always write RIS so it's ready

    print()
    try:
        ans = input(f"  {cyan('?')} Import these papers into Zotero? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans in ("y", "yes"):
        if cfg.get("zotero_type") == "web":
            print(f"\n  {bold('Zotero import steps:')}")
            print(f"  1. Open Zotero desktop app (or zotero.org)")
            print(f"  2. File → Import → {bold(str(ris_path))}")
            print(f"  3. Or drag-drop the .ris file into your library")
            print(f"\n  {green('✓')} RIS file ready: {ris_path}")
        elif cfg.get("zotero_type") == "local":
            print(f"\n  {bold('Zotero import:')}")
            print(f"  File → Import → {bold(str(ris_path))}")
            print(f"\n  {green('✓')} RIS file ready: {ris_path}")
        else:
            print(f"\n  {yellow('Zotero not connected yet.')}")
            print(f"  Set it up with: {cyan('python3 lab_init.py --update-prefs')}")
            print(f"\n  Your .ris file is ready when you do:")
            print(f"  {bold(str(ris_path))}")
    else:
        print(f"  {dim('Skipped. RIS saved at:')} {dim(str(ris_path))}")

    # ── Write to research-graph.jsonl ─────────────────────────────────────────
    paper_refs = []
    for p in top_papers:
        ref = p.get("doi") or p.get("pmid") or p.get("arxiv_id") or p.get("ss_id", "")
        append_jsonl(RESEARCH_GRAPH, {
            "type": "Paper",
            "source": p.get("source"),
            "title": p.get("title"),
            "authors": p.get("authors"),
            "year": p.get("year"),
            "journal": p.get("journal"),
            "doi": p.get("doi"),
            "url": p.get("url"),
            "citations": p.get("citations"),
            "abstract_snippet": p.get("abstract", "")[:200],
            "relevance_score": p["_score"],
            "added_by": "lab-lit-scout",
            "added_date": TODAY,
            "query": query
        })
        paper_refs.append(ref)
    print(f"  {green('✓')} {len(top_papers)} papers written to research-graph.jsonl")

    # ── Link to project ────────────────────────────────────────────────────────
    if project:
        link_to_project(slugify(project), paper_refs)
        print(f"  {green('✓')} Papers linked to project: {project}")

    # ── XP ─────────────────────────────────────────────────────────────────────
    award_xp("lit_search_done", 50)
    print(f"  {green('✓')} +50 XP awarded")
    print(f"\n{bold(green('✅ Done!'))} {len(top_papers)} papers saved · {len(contradictions)} contradictions flagged\n")


def main():
    parser = argparse.ArgumentParser(description="LabOS deep literature search")
    parser.add_argument("--query",    required=True,         help="Search query or hypothesis")
    parser.add_argument("--project",  type=str, default=None, help="Project to link results to")
    parser.add_argument("--limit",    type=int, default=10,   help="Max papers to return (default 10)")
    parser.add_argument("--since",    type=str, default=None, help="Filter by date YYYY-MM-DD")
    parser.add_argument("--sort",     type=str, default="relevance",
                        choices=["relevance", "citations", "date"],
                        help="Sort by: relevance (default), citations, date")
    parser.add_argument("--dry-run",  action="store_true",   help="Print without saving")
    args = parser.parse_args()
    run(args)

if __name__ == "__main__":
    main()
