# src/swarm/research/crawler.py
"""
Research crawler. Runs inside the orchestrator pod (not a separate Argo step).
Crawls up to 20 new unique resources per cycle.

Flow:
  1. Read active sources from ClickHouse (research_sources)
  2. For each source, fetch candidate URLs (arXiv API or Tavily search)
  3. xxhash each URL → check research_crawl_log → skip if seen
  4. Extract full text (arXiv API abstract+body or Tavily extract)
  5. Route through qwen3-32b-fp8 for relevance classification
  6. If relevant: chunk, embed, store in research_corpus + Qdrant
  7. Log all attempts (accepted + rejected) to research_crawl_log
"""

import os, uuid, json, time, xmltodict, requests
import xxhash
from typing import List, Dict, Optional, Tuple
from src.shared.config import SharedConfig
from src.shared.ch_client import get_client
from src.shared.llm_client import chat_routing, embed_texts

cfg = SharedConfig()

MAX_NEW_PER_CYCLE = 20


# ── arXiv API ──────────────────────────────────────────────

def fetch_arxiv_candidates(
    category: str,
    keywords: List[str],
    max_results: int = 10,
) -> List[Dict]:
    """
    Query arXiv API for recent papers in a category, filtered by keywords.
    Rate limit: 1 request per 3 seconds (arXiv policy).
    """
    kw_query = " OR ".join(f'all:"{kw}"' for kw in keywords)
    query = f"cat:{category} AND ({kw_query})"

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    resp = requests.get(
        "http://export.arxiv.org/api/query",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()

    parsed = xmltodict.parse(resp.text)
    feed = parsed.get("feed", {})
    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]

    results = []
    for entry in entries:
        arxiv_id = entry.get("id", "").split("/abs/")[-1]
        authors = entry.get("author", [])
        if isinstance(authors, dict):
            authors = [authors]
        author_names = [a.get("name", "") for a in authors]

        published = entry.get("published", "2025")
        year = int(published[:4]) if published else 2025

        results.append({
            "arxiv_id": arxiv_id,
            "title": entry.get("title", "").replace("\n", " ").strip(),
            "authors": author_names,
            "abstract": entry.get("summary", "").replace("\n", " ").strip(),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "year": year,
            "source_type": "arxiv",
        })

    return results


# ── Tavily ─────────────────────────────────────────────────

def fetch_tavily_candidates(
    domain: str,
    search_terms: List[str],
    max_results: int = 5,
) -> List[Dict]:
    """Search a specific domain via Tavily API."""
    results = []
    for term in search_terms:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": cfg.TAVILY_API_KEY,
                "query": term,
                "include_domains": [domain],
                "max_results": max(2, max_results // len(search_terms)),
                "search_depth": "advanced",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("results", []):
            results.append({
                "url": item["url"],
                "title": item.get("title", ""),
                "content_snippet": item.get("content", ""),
                "source_type": "tavily",
            })

        if len(results) >= max_results:
            break

    return results[:max_results]


def extract_tavily_content(url: str) -> Optional[str]:
    """Extract full page content via Tavily extract endpoint."""
    resp = requests.post(
        "https://api.tavily.com/extract",
        json={
            "api_key": cfg.TAVILY_API_KEY,
            "urls": [url],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if results:
        return results[0].get("raw_content", "")
    return None


# ── Dedup ──────────────────────────────────────────────────

def content_hash(identifier: str) -> int:
    """xxhash64 of a URL or arXiv ID. Used for dedup."""
    return xxhash.xxh64(identifier.encode()).intdigest()


def is_already_crawled(ch, identifier: str) -> bool:
    """Check if this resource was already crawled (accepted OR rejected)."""
    h = content_hash(identifier)
    result = ch.query(
        "SELECT count() as c FROM fxs_research_crawl_log WHERE content_hash = %(h)s",
        parameters={"h": h},
    )
    return result.first_row[0] > 0


# ── Relevance Gate (routing model) ─────────────────────────

RELEVANCE_PROMPT = """You are a research relevance classifier for an FX prediction ML system.

Score the following research content for relevance to building ML-based
forex trading strategies. Consider:
- Does it describe a trading strategy (entry/exit signals, position sizing)?
- Does it present a model architecture applicable to financial time series?
- Does it cover feature engineering for price/volume/volatility data?
- Does it address FX-specific phenomena (carry, momentum, regime switching)?
- Does it discuss evaluation methodology for trading systems?

Content title: {title}
Content excerpt (first 1500 chars):
{excerpt}

Respond with ONLY a JSON object:
{{
  "relevant": true/false,
  "score": 0.0 to 1.0,
  "topics": ["list", "of", "topics"],
  "strategy_families": ["list", "if", "applicable"],
  "model_families": ["list", "if", "applicable"],
  "reason": "one sentence explanation"
}}"""


def classify_relevance(title: str, text: str) -> Dict:
    """Use routing model (qwen3-32b-fp8) to classify relevance."""
    excerpt = text[:1500]
    prompt = RELEVANCE_PROMPT.format(title=title, excerpt=excerpt)

    response = chat_routing(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300,
    )

    try:
        clean = response.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"relevant": False, "score": 0.0, "topics": [], "reason": "parse_error"}


# ── Chunking ───────────────────────────────────────────────

def chunk_text(text: str, chunk_chars: int = 2000) -> List[str]:
    """Split text into ~500-token chunks with 10% overlap."""
    chunks = []
    step = chunk_chars - 200
    for i in range(0, len(text), step):
        chunk = text[i : i + chunk_chars].strip()
        if len(chunk) > 100:
            chunks.append(chunk)
    return chunks


# ── Main Crawl Orchestrator ────────────────────────────────

def run_crawl_cycle() -> Dict:
    """
    Main entry point. Called from crawl_research_node in graph.py.
    Returns summary: {crawled: int, accepted: int, rejected: int, chunks_embedded: int}
    """
    ch = get_client()

    sources = ch.query(
        "SELECT * FROM fxs_research_sources "
        "WHERE active = 1 ORDER BY priority ASC"
    ).named_results()

    total_new = 0
    total_accepted = 0
    total_rejected = 0
    total_chunks = 0

    for source in sources:
        if total_new >= MAX_NEW_PER_CYCLE:
            break

        remaining = MAX_NEW_PER_CYCLE - total_new
        source_max = min(source["max_items_per_crawl"], remaining)
        source_id = source["source_id"]

        if source["source_type"] == "arxiv_category":
            candidates = fetch_arxiv_candidates(
                category=source["arxiv_category"],
                keywords=source["arxiv_keywords"],
                max_results=source_max * 3,
            )
            time.sleep(3)  # arXiv rate limit
        elif source["source_type"] == "tavily_site":
            candidates = fetch_tavily_candidates(
                domain=source["site_domain"],
                search_terms=source["site_search_terms"],
                max_results=source_max * 2,
            )
        else:
            continue

        accepted_from_source = 0
        for candidate in candidates:
            if total_new >= MAX_NEW_PER_CYCLE:
                break
            if accepted_from_source >= source_max:
                break

            identifier = candidate.get("arxiv_id") or candidate.get("url", "")
            if is_already_crawled(ch, identifier):
                continue

            if candidate["source_type"] == "arxiv":
                full_text = candidate["abstract"]
                title = candidate["title"]
                url = candidate["url"]
                authors = candidate.get("authors", [])
                year = candidate.get("year", 2025)
            else:
                full_text = extract_tavily_content(candidate["url"])
                if not full_text or len(full_text) < 200:
                    continue
                title = candidate["title"]
                url = candidate["url"]
                authors = []
                year = 2025

            total_new += 1

            classification = classify_relevance(title, full_text)
            is_relevant = classification.get("relevant", False)
            rel_score = classification.get("score", 0.0)

            if is_relevant and rel_score >= 0.4:
                entry_id = str(uuid.uuid4())
                chunks = chunk_text(full_text)
                embeddings = embed_texts(chunks)

                for i, chunk in enumerate(chunks):
                    ch.insert(
                        "fxs_research_corpus",
                        data=[[entry_id, candidate["source_type"], source_id,
                               title, authors, url, year, i, chunk,
                               classification.get("topics", []),
                               ["fx"],
                               classification.get("strategy_families", []),
                               classification.get("model_families", []),
                               rel_score]],
                        column_names=["entry_id", "source_type", "source_id",
                                      "title", "authors", "url", "year",
                                      "chunk_index", "chunk_text", "topics",
                                      "asset_classes", "strategy_families",
                                      "model_families", "relevance_score"],
                    )

                from src.swarm.memory.research_store import (
                    get_qdrant, ensure_research_collection, RESEARCH_COLLECTION,
                )
                from qdrant_client.models import PointStruct
                client = get_qdrant()
                ensure_research_collection()
                points = []
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entry_id}-{i}"))
                    points.append(PointStruct(
                        id=point_id,
                        vector=emb,
                        payload={
                            "entry_id": entry_id,
                            "title": title,
                            "chunk_index": i,
                            "chunk_text": chunk,
                            "topics": classification.get("topics", []),
                            "strategy_families": classification.get("strategy_families", []),
                            "model_families": classification.get("model_families", []),
                            "source_type": candidate["source_type"],
                            "year": year,
                        },
                    ))
                client.upsert(collection_name=RESEARCH_COLLECTION, points=points)

                total_accepted += 1
                total_chunks += len(chunks)
                accepted_from_source += 1

                ch.insert(
                    "fxs_research_crawl_log",
                    data=[[content_hash(identifier), url, title, source_id,
                           1, rel_score, entry_id, len(chunks)]],
                    column_names=["content_hash", "url", "title", "source_id",
                                  "relevant", "relevance_score", "entry_id", "chunks_created"],
                )
            else:
                total_rejected += 1
                ch.insert(
                    "fxs_research_crawl_log",
                    data=[[content_hash(identifier), url, title, source_id,
                           0, rel_score, None, 0]],
                    column_names=["content_hash", "url", "title", "source_id",
                                  "relevant", "relevance_score", "entry_id", "chunks_created"],
                )

    summary = {
        "crawled": total_new,
        "accepted": total_accepted,
        "rejected": total_rejected,
        "chunks_embedded": total_chunks,
    }
    with open("/tmp/crawl_summary.json", "w") as f:
        json.dump(summary, f)

    return summary


if __name__ == "__main__":
    summary = run_crawl_cycle()
    print(f"Crawl complete: {summary}")
