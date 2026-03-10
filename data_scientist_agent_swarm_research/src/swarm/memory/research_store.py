# src/swarm/memory/research_store.py

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchAny, MatchValue,
)
from src.shared.config import SharedConfig
from src.shared.llm_client import embed_single, embed_texts
import uuid

cfg = SharedConfig()
RESEARCH_COLLECTION = cfg.QDRANT_RESEARCH_COLLECTION
EMBEDDING_DIM = cfg.LLM_EMBEDDING_DIM


def get_qdrant() -> QdrantClient:
    return QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT)


def ensure_research_collection():
    client = get_qdrant()
    if not client.collection_exists(RESEARCH_COLLECTION):
        client.create_collection(
            collection_name=RESEARCH_COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )


def query_research(
    query_text: str,
    limit: int = 10,
    strategy_filter: list = None,
    model_filter: list = None,
) -> list:
    """Semantic search over research corpus."""
    client = get_qdrant()
    embedding = embed_single(query_text)

    conditions = []
    if strategy_filter:
        conditions.append(FieldCondition(
            key="strategy_families", match=MatchAny(any=strategy_filter)
        ))
    if model_filter:
        conditions.append(FieldCondition(
            key="model_families", match=MatchAny(any=model_filter)
        ))

    search_filter = Filter(must=conditions) if conditions else None
    hits = client.search(
        collection_name=RESEARCH_COLLECTION,
        query_vector=embedding,
        query_filter=search_filter,
        limit=limit,
    )
    return [{"score": h.score, **h.payload} for h in hits]


def query_research_for_cycle(
    allocation: dict,
    champion_metrics: dict,
    past_experiment_strategies: list,
    limit_per_direction: int = 5,
) -> list:
    """Query research corpus based on what the swarm needs this cycle."""
    seen_ids = set()
    results = []

    direction_queries = {
        "arch_search": "novel neural network architectures for financial time series forecasting",
        "feature_eng": "feature engineering technical indicators FX prediction",
        "strategy": "trading strategy design entry exit signals FX currency pairs",
        "ensemble": "ensemble methods model combination financial prediction",
        "regime": "regime detection hidden markov models volatility clustering FX markets",
        "refine": "hyperparameter optimization deep learning financial time series",
    }

    for direction, count in (allocation or {}).items():
        if count <= 0:
            continue

        query_text = direction_queries.get(
            direction, f"{direction} FX prediction strategy",
        )
        hits = query_research(query_text, limit=limit_per_direction * 2)

        for hit in hits:
            if hit.get("entry_id") not in seen_ids:
                seen_ids.add(hit["entry_id"])
                results.append({
                    "entry_id": hit["entry_id"],
                    "title": hit.get("title", ""),
                    "chunk_text": hit.get("chunk_text", ""),
                    "strategy_families": hit.get("strategy_families", []),
                    "model_families": hit.get("model_families", []),
                    "year": hit.get("year", 0),
                    "relevance": hit["score"],
                    "matched_direction": direction,
                })

            if len(results) >= limit_per_direction * len(allocation):
                break

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results
