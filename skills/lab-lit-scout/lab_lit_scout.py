#!/usr/bin/env python3
"""
lab-lit-scout — On-demand literature search for LabOS
Searches PubMed, OpenAlex, arXiv. No API keys required.
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lab_utils import (
    load_config, load_graph, save_graph,
    award_xp, log_session, progress, section_header,
    checkpoint, confirm, interactive_loop, CheckpointAborted,
    call_llm, find_project, get_project_hypotheses,
    upsert_node, now_iso, today_str, short_hash,
    LAB_DIR,
)


# ─── HTTP helper ──────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 10) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LabOS/1.0 (academic research tool)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None


def http_get_json(url: str, timeout: int = 10) -> dict | list | None:
    raw = http_get(url, timeout)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60].strip("-")


# ─── PubMed ───────────────────────────────────────────────────────────────────

def search_pubmed(query: str, limit: int, since: str | None) -> list[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # ESearch
    params = {"db": "pubmed", "term": query, "retmax": limit * 2,
              "retmode": "json", "sort": "relevance"}
    if since:
        params["mindate"] = since.replace("-", "/")
        params["datetype"] = "pdat"

    url = f"{base}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    if not data:
        return []

    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    # EFetch
    fetch_url = f"{base}/efetch.fcgi?db=pubmed&id={','.join(ids)}&retmode=xml"
    xml_text = http_get(fetch_url)
    if not xml_text:
        return []

    papers = []
    try:
        root = ET.fromstring(xml_text)
        for article in root.findall(".//PubmedArticle"):
            try:
                medline = article.find("MedlineCitation")
                art     = medline.find("Article")
                title   = art.findtext("ArticleTitle", "").strip()
                abstract_el = art.find(".//AbstractText")
                abstract = abstract_el.text if abstract_el is not None else ""

                # Authors
                authors = []
                for auth in art.findall(".//Author"):
                    last  = auth.findtext("LastName", "")
                    first = auth.findtext("ForeName", "")
                    if last:
                        authors.append(f"{last} {first}".strip())

                # Year
                year = medline.findtext(".//PubDate/Year") or \
                       medline.findtext(".//PubDate/MedlineDate", "")[:4]

                # Journal
                journal = art.findtext(".//Journal/Title", "") or \
                          art.findtext(".//Journal/ISOAbbreviation", "")

                # DOI
                doi = ""
                for aid in article.findall(".//ArticleId"):
                    if aid.get("IdType") == "doi":
                        doi = aid.text or ""

                # Citations (not available from PubMed directly, default 0)
                pmid = medline.findtext("PMID", "")

                papers.append({
                    "source": "pubmed",
                    "title": title,
                    "abstract": abstract or "",
                    "authors": authors[:3],
                    "year": year,
                    "journal": journal,
                    "doi": doi,
                    "pmid": pmid,
                    "citations": 0,
                    "open_access": False,
                })
            except Exception:
                continue
    except ET.ParseError:
        pass

    return papers


# ─── OpenAlex ─────────────────────────────────────────────────────────────────

def search_openalex(query: str, limit: int, since: str | None) -> list[dict]:
    params = {
        "search": query,
        "per-page": limit,
        "sort": "relevance_score:desc",
        "select": "title,abstract_inverted_index,authorships,publication_year,primary_location,doi,cited_by_count,open_access",
        "mailto": "labos@example.com",
    }
    if since:
        params["filter"] = f"publication_year:>{since[:4]}"

    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    if not data:
        return []

    papers = []
    for work in data.get("results", []):
        # Reconstruct abstract from inverted index
        abstract = ""
        inv = work.get("abstract_inverted_index") or {}
        if inv:
            word_positions = []
            for word, positions in inv.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions)

        # Authors
        authors = []
        for a in work.get("authorships", [])[:3]:
            name = a.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        # Journal
        loc = work.get("primary_location") or {}
        source = loc.get("source") or {}
        journal = source.get("display_name", "")

        doi_raw = work.get("doi", "") or ""
        doi = doi_raw.replace("https://doi.org/", "")

        papers.append({
            "source": "openalex",
            "title": work.get("title", ""),
            "abstract": abstract,
            "authors": authors,
            "year": str(work.get("publication_year", "")),
            "journal": journal,
            "doi": doi,
            "pmid": "",
            "citations": work.get("cited_by_count", 0),
            "open_access": work.get("open_access", {}).get("is_oa", False),
        })

    return papers


# ─── arXiv ────────────────────────────────────────────────────────────────────

def search_arxiv(query: str, limit: int, since: str | None) -> list[dict]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    url = f"https://export.arxiv.org/api/query?{urllib.parse.urlencode(params)}"
    xml_text = http_get(url)
    if not xml_text:
        return []

    papers = []
    try:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        for entry in root.findall("atom:entry", ns):
            title    = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip()
            published = entry.findtext("atom:published", "", ns)[:10]
            year     = published[:4] if published else ""

            if since and published < since:
                continue

            authors = []
            for auth in entry.findall("atom:author", ns):
                name = auth.findtext("atom:name", "", ns)
                if name:
                    authors.append(name)

            doi = ""
            arxiv_id = ""
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "doi":
                    doi = link.get("href", "").replace("https://doi.org/", "")
                if link.get("type") == "text/html":
                    href = link.get("href", "")
                    arxiv_id = href.split("/abs/")[-1] if "/abs/" in href else ""

            papers.append({
                "source": "arxiv",
                "title": title,
                "abstract": abstract,
                "authors": authors[:3],
                "year": year,
                "journal": "arXiv",
                "doi": doi or f"arxiv:{arxiv_id}",
                "pmid": "",
                "citations": 0,
                "open_access": True,
                "arxiv_id": arxiv_id,
            })
    except ET.ParseError:
        pass

    return papers


# ─── Deduplication & scoring ──────────────────────────────────────────────────

def dedup(papers: list[dict]) -> list[dict]:
    seen_dois = set()
    seen_titles = set()
    result = []
    for p in papers:
        doi = p.get("doi", "").lower().strip()
        title_key = re.sub(r"\W+", "", p.get("title", "").lower())[:60]
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


def score_paper(paper: dict, query: str, user_fields: list[str]) -> int:
    query_words = set(query.lower().split())
    field_words = set(" ".join(user_fields).lower().split())

    title    = paper.get("title", "").lower()
    abstract = paper.get("abstract", "").lower()

    title_hits    = sum(1 for w in query_words if w in title)
    abstract_hits = sum(1 for w in query_words if w in abstract)
    field_hits    = sum(1 for w in field_words if w in title or w in abstract)

    try:
        year = int(paper.get("year", 0) or 0)
        recency = 10 if year >= 2022 else (5 if year >= 2019 else 0)
    except ValueError:
        recency = 0

    cite_score = min(5, (paper.get("citations", 0) or 0) // 20)

    return (
        min(35, title_hits * 12) +
        min(35, abstract_hits * 3) +
        min(15, field_hits * 5) +
        recency +
        cite_score
    )


# ─── LLM summarise ────────────────────────────────────────────────────────────

def summarise_papers(papers: list[dict], query: str, hypotheses: list[dict]) -> list[dict]:
    """Generate structured summaries for each paper via LLM."""
    hyp_texts = [h.get("text", "") for h in hypotheses if h.get("text")]
    hyp_block = "\n".join(f"- {h}" for h in hyp_texts) if hyp_texts else "none"

    summarised = []
    for i, p in enumerate(papers):
        progress(f"Summarising paper {i+1}/{len(papers)}: {p['title'][:50]}…", "🤖")

        prompt = f"""Analyse this academic paper and respond ONLY as valid JSON (no markdown, no commentary):

Paper:
Title: {p['title']}
Abstract: {p['abstract'][:1500]}
Year: {p['year']} | Journal: {p['journal']}

Query the user is researching: "{query}"

Stored project hypotheses:
{hyp_block}

Respond with this exact JSON structure:
{{
  "key_claim": "one sentence main claim",
  "method": "study design, sample size if mentioned, key technique",
  "key_finding": "1-2 sentence finding",
  "limitation": "one sentence main limitation",
  "relevance": "one sentence — why this matters for the query",
  "contradicts_hypothesis": true or false,
  "contradiction_note": "if true: which hypothesis and why, else empty string"
}}"""

        raw = call_llm(prompt)
        try:
            # Strip markdown code fences if present
            cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            summary = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            summary = {
                "key_claim": "",
                "method": "",
                "key_finding": p["abstract"][:200] if p["abstract"] else "No abstract available.",
                "limitation": "",
                "relevance": "See abstract.",
                "contradicts_hypothesis": False,
                "contradiction_note": "",
            }

        p.update(summary)
        summarised.append(p)

    return summarised


# ─── Relevance bar ────────────────────────────────────────────────────────────

def relevance_bar(score: int, max_score: int = 100) -> str:
    filled = round((score / max(max_score, 1)) * 10)
    return "█" * filled + "░" * (10 - filled) + f" {score}%"


# ─── Output ───────────────────────────────────────────────────────────────────

def print_results(papers: list[dict], query: str, project_name: str | None):
    section_header(f"🔍 Lit Scout — \"{query}\"")
    if project_name:
        print(f"   Project: {project_name}")
    print(f"   {len(papers)} paper(s) found\n")

    for i, p in enumerate(papers, 1):
        score = p.get("relevance_score", 0)
        oa    = "🔓" if p.get("open_access") else "🔒"
        contra = "⚠️  CONTRADICTS HYPOTHESIS" if p.get("contradicts_hypothesis") else ""

        print(f"{'─'*60}")
        print(f"**{i}. {p['title']}** ({p.get('year', '?')}) {oa}")
        print(f"   {', '.join(p.get('authors', [])[:3])}")
        print(f"   Journal: {p.get('journal', '?')} | Citations: {p.get('citations', 0)}")
        print(f"   Relevance: {relevance_bar(score)}")
        if p.get("key_claim"):
            print(f"   🔑 Claim: {p['key_claim']}")
        if p.get("method"):
            print(f"   🧪 Method: {p['method']}")
        if p.get("key_finding"):
            print(f"   📊 Finding: {p['key_finding']}")
        if p.get("limitation"):
            print(f"   ⚠️  Limit: {p['limitation']}")
        if p.get("relevance"):
            print(f"   🎯 Why relevant: {p['relevance']}")
        if p.get("doi"):
            print(f"   DOI: {p['doi']}")
        if contra:
            print(f"\n   🚨 {contra}")
            if p.get("contradiction_note"):
                print(f"      {p['contradiction_note']}")
        print()


# ─── Save to Obsidian ─────────────────────────────────────────────────────────

def save_to_obsidian(papers: list[dict], query: str, project_name: str | None, config: dict) -> Path | None:
    vault = config.get("obsidian_vault", "")
    if not vault:
        lit_dir = LAB_DIR / "literature"
    else:
        lit_dir = Path(vault) / "Research" / "Literature"
    lit_dir.mkdir(parents=True, exist_ok=True)

    fname = lit_dir / f"{today_str()}-{slugify(query)}.md"
    lines = [
        f"# Lit Scout — {query}",
        f"*{today_str()} | {len(papers)} papers | Project: {project_name or 'global'}*\n",
        "## Papers\n",
    ]
    for i, p in enumerate(papers, 1):
        oa = "🔓 Open Access" if p.get("open_access") else ""
        lines += [
            f"### {i}. {p['title']} ({p.get('year', '?')}) {oa}",
            f"**Authors:** {', '.join(p.get('authors', []))}  ",
            f"**Journal:** {p.get('journal', '?')} | **Citations:** {p.get('citations', 0)}  ",
            f"**DOI:** {p.get('doi', '')}  ",
            f"**Relevance:** {p.get('relevance_score', 0)}%\n",
            f"**Key claim:** {p.get('key_claim', '')}  ",
            f"**Method:** {p.get('method', '')}  ",
            f"**Finding:** {p.get('key_finding', '')}  ",
            f"**Limitation:** {p.get('limitation', '')}  ",
            f"**Why relevant:** {p.get('relevance', '')}\n",
        ]
        if p.get("contradicts_hypothesis"):
            lines.append(f"⚠️ **CONTRADICTS HYPOTHESIS:** {p.get('contradiction_note', '')}\n")

    fname.write_text("\n".join(lines))
    return fname


# ─── Export BibTeX for Zotero ─────────────────────────────────────────────────

def export_bib(papers: list[dict]) -> Path:
    sessions_dir = LAB_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    bib_path = sessions_dir / f"{today_str()}-lit-scout.bib"

    entries = []
    for p in papers:
        key = short_hash(p.get("doi", p.get("title", "")))
        authors_str = " and ".join(p.get("authors", ["Unknown"]))
        entries.append(
            f"@article{{{key},\n"
            f"  title = {{{p.get('title', '')}}},\n"
            f"  author = {{{authors_str}}},\n"
            f"  year = {{{p.get('year', '')}}},\n"
            f"  journal = {{{p.get('journal', '')}}},\n"
            f"  doi = {{{p.get('doi', '')}}},\n"
            f"}}"
        )
    bib_path.write_text("\n\n".join(entries))
    return bib_path


# ─── Research graph ───────────────────────────────────────────────────────────

def papers_to_graph_nodes(papers: list[dict], query: str, project_id: str | None) -> list[dict]:
    nodes = []
    for p in papers:
        pid = f"paper_{short_hash(p.get('doi', '') or p.get('title', ''))}"
        node = {
            "type": "Paper",
            "id": pid,
            "title": p.get("title", ""),
            "doi": p.get("doi", ""),
            "authors": p.get("authors", []),
            "year": p.get("year", ""),
            "journal": p.get("journal", ""),
            "abstract": p.get("abstract", "")[:500],
            "key_claim": p.get("key_claim", ""),
            "key_finding": p.get("key_finding", ""),
            "summary": p.get("key_finding", ""),
            "relevance_score": p.get("relevance_score", 0),
            "query": query,
            "projects": [project_id] if project_id else [],
            "contradicts": p.get("contradicts_hypothesis", False),
            "contradiction_note": p.get("contradiction_note", ""),
            "open_access": p.get("open_access", False),
            "citations": p.get("citations", 0),
            "source": p.get("source", ""),
            "added_by": "lab-lit-scout",
            "added": now_iso(),
        }
        nodes.append(node)
    return nodes


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LabOS Lit Scout — literature search")
    parser.add_argument("--query",   "-q", required=True, help="Search query")
    parser.add_argument("--project", "-p", help="Project to link papers to")
    parser.add_argument("--limit",   "-l", type=int, default=10, help="Max papers (1-20)")
    parser.add_argument("--since",   "-s", help="Filter from date YYYY-MM-DD")
    parser.add_argument("--sort",    choices=["relevance", "citations", "date"], default="relevance")
    parser.add_argument("--dry-run", action="store_true", help="Print without saving")
    parser.add_argument("--no-interactive", action="store_true")
    args = parser.parse_args()

    args.limit = max(1, min(20, args.limit))

    config = load_config()
    nodes  = load_graph()

    # Find project
    project = find_project(nodes, args.project) if args.project else None
    project_name = None
    project_id   = None
    hypotheses   = []
    if project:
        props        = project.get("properties", project)
        project_name = props.get("name", project.get("id", ""))
        project_id   = project.get("id", "")
        hypotheses   = get_project_hypotheses(nodes, project_id)

    databases = config.get("databases", ["pubmed", "openalex", "arxiv"])
    user_fields = config.get("fields", [])

    section_header(f"🔍 Lab Lit Scout — \"{args.query}\"")
    if project_name:
        print(f"   Project: {project_name}")
    print(f"   Databases: {', '.join(databases)} | Limit: {args.limit}")
    if args.since:
        print(f"   Since: {args.since}")
    print()

    # ── Fetch ──
    all_papers = []
    per_source = max(args.limit, 8)

    if "pubmed" in databases:
        progress("Searching PubMed…", "🔬")
        all_papers += search_pubmed(args.query, per_source, args.since)
        time.sleep(0.4)  # be nice to NCBI

    if "openalex" in databases:
        progress("Searching OpenAlex…", "📖")
        all_papers += search_openalex(args.query, per_source, args.since)

    if "arxiv" in databases:
        progress("Searching arXiv…", "📄")
        all_papers += search_arxiv(args.query, per_source, args.since)

    if not all_papers:
        print("❌ No papers found. Try a broader query.")
        sys.exit(0)

    # ── Dedup + score ──
    progress(f"Deduplicating {len(all_papers)} raw results…", "🔀")
    papers = dedup(all_papers)

    for p in papers:
        p["relevance_score"] = score_paper(p, args.query, user_fields)

    # Sort
    if args.sort == "citations":
        papers.sort(key=lambda p: p.get("citations", 0), reverse=True)
    elif args.sort == "date":
        papers.sort(key=lambda p: p.get("year", "0"), reverse=True)
    else:
        papers.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

    papers = papers[:args.limit]

    # ── Checkpoint: show preview before full summarise ──
    print(f"\n📋 Found {len(papers)} unique papers. Quick preview:")
    for i, p in enumerate(papers, 1):
        print(f"  {i}. [{p['relevance_score']:3d}%] {p['title'][:65]} ({p.get('year','?')})")

    if not args.no_interactive:
        try:
            choice = checkpoint(
                "Summarise all with AI, or select specific papers?",
                options=["all"] + [str(i) for i in range(1, len(papers)+1)] + ["done"],
                default="all",
                emoji="🤖",
            )
            if choice.lower() == "done":
                print("Skipping summaries.")
            elif choice.lower() != "all":
                # User picked specific indices
                selected_indices = []
                for token in re.split(r"[,\s]+", choice):
                    try:
                        idx = int(token) - 1
                        if 0 <= idx < len(papers):
                            selected_indices.append(idx)
                    except ValueError:
                        pass
                if selected_indices:
                    papers = [papers[i] for i in selected_indices]
                    print(f"  Summarising {len(papers)} selected paper(s).")
        except CheckpointAborted:
            pass

    # ── Summarise ──
    progress("Generating AI summaries…", "🤖")
    papers = summarise_papers(papers, args.query, hypotheses)

    # ── Print results ──
    print_results(papers, args.query, project_name)

    # ── Contradiction summary ──
    contradictions = [p for p in papers if p.get("contradicts_hypothesis")]
    if contradictions:
        print(f"\n🚨 **{len(contradictions)} paper(s) contradict stored hypotheses:**")
        for p in contradictions:
            print(f"   • \"{p['title'][:60]}\"")
            print(f"     → {p.get('contradiction_note', '')}")

    if args.dry_run:
        print("\n[DRY RUN] Nothing saved.")
        return

    # ── Save ──
    obs_path = save_to_obsidian(papers, args.query, project_name, config)
    bib_path = export_bib(papers)

    # Update graph
    new_nodes = papers_to_graph_nodes(papers, args.query, project_id)
    for n in new_nodes:
        nodes = upsert_node(nodes, n)
    save_graph(nodes)

    # Update project's last_lit_scout timestamp
    if project_id:
        from lab_utils import update_node
        nodes = update_node(nodes, project_id, {"last_lit_scout": now_iso()})
        save_graph(nodes)

    # Session log
    summary_lines = "\n".join(
        f"- [{p.get('relevance_score',0)}%] {p['title']} ({p.get('year','?')})"
        for p in papers
    )
    log_session("lab-lit-scout", project_name or "global",
                f"Query: {args.query}\nPapers found: {len(papers)}\n\n{summary_lines}")

    print(f"\n💾 Obsidian: {obs_path}")
    print(f"📚 BibTeX:   {bib_path}  (drag into Zotero to import)")
    print(f"🗂️  Research graph updated — {len(new_nodes)} paper(s) added")

    if not args.no_interactive:
        try:
            deep = checkpoint(
                "Go deeper on any paper? Enter number or 'done'.",
                options=[str(i) for i in range(1, len(papers)+1)] + ["done"],
                default="done",
                emoji="🔎",
            )
            if deep.lower() != "done":
                try:
                    idx = int(deep) - 1
                    p = papers[idx]
                    print(f"\n📄 Full abstract — {p['title']}\n")
                    print(p.get("abstract", "No abstract available."))
                    print(f"\nDOI: {p.get('doi', '')}")
                except (ValueError, IndexError):
                    pass
        except CheckpointAborted:
            pass

    award_xp(50, "🔬 Literature Dive")
    print("\n✅ Lit scout complete.\n")


if __name__ == "__main__":
    main()
