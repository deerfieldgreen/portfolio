# src/swarm/memory/qdrant_store.py

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue, Range,
)
from src.shared.config import SharedConfig
from src.shared.llm_client import embed_single, embed_texts
import uuid

cfg = SharedConfig()
COLLECTION = cfg.QDRANT_COLLECTION
EMBEDDING_DIM = cfg.LLM_EMBEDDING_DIM


def get_qdrant() -> QdrantClient:
    return QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT)


def ensure_collection():
    client = get_qdrant()
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )


def compose_experiment_text(spec: dict, result: dict) -> str:
    """Composite text for embedding. Architecture-agnostic."""
    parts = [
        f"Architecture: {spec.get('architecture', 'unknown')}",
        f"Features: {spec.get('feature_set', [])}",
        f"Strategy: {spec.get('strategy_type', 'unknown')}",
        f"Pair: {spec.get('pair', '')} {spec.get('timeframe', '')}",
    ]
    if result:
        metrics = result.get("metrics", {})
        parts.append(f"Sharpe: {metrics.get('sharpe', 'N/A')}")
        parts.append(f"Status: {result.get('status', 'unknown')}")
        if result.get("failure_detail"):
            parts.append(f"Detail: {result['failure_detail']}")
    return ", ".join(parts)


def upsert_experiment(experiment_id: str, spec: dict, result: dict) -> float:
    """Store experiment. Returns novelty score (1.0 - cosine similarity to nearest)."""
    client = get_qdrant()
    ensure_collection()

    text = compose_experiment_text(spec, result)
    embedding = embed_single(text)

    novelty = 1.0
    hits = client.search(collection_name=COLLECTION, query_vector=embedding, limit=1)
    if hits:
        novelty = 1.0 - hits[0].score

    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, experiment_id)),
            vector=embedding,
            payload={
                "experiment_id": experiment_id,
                "architecture": spec.get("architecture"),
                "strategy_type": spec.get("strategy_type"),
                "pair": spec.get("pair"),
                "timeframe": spec.get("timeframe"),
                "status": result.get("status"),
                "sharpe": result.get("metrics", {}).get("sharpe"),
                "text": text,
            },
        )]
    )
    return novelty


def find_similar(
    spec: dict,
    limit: int = 10,
    strategy_filter: str = None,
    min_sharpe: float = None,
) -> list:
    """Find semantically similar past experiments."""
    client = get_qdrant()
    text = compose_experiment_text(spec, {})
    embedding = embed_single(text)

    conditions = []
    if strategy_filter:
        conditions.append(FieldCondition(
            key="strategy_type", match=MatchValue(value=strategy_filter)
        ))
    if min_sharpe is not None:
        conditions.append(FieldCondition(
            key="sharpe", range=Range(gte=min_sharpe)
        ))

    search_filter = Filter(must=conditions) if conditions else None
    hits = client.search(
        collection_name=COLLECTION, query_vector=embedding,
        query_filter=search_filter, limit=limit,
    )
    return [{"score": h.score, **h.payload} for h in hits]


def batch_upsert_experiments(experiments: list) -> list:
    """Batch insert. experiments: list of (experiment_id, spec, result) tuples."""
    client = get_qdrant()
    ensure_collection()

    texts = [compose_experiment_text(s, r) for _, s, r in experiments]
    embeddings = embed_texts(texts)

    novelties = []
    points = []
    for i, (exp_id, spec, result) in enumerate(experiments):
        hits = client.search(
            collection_name=COLLECTION, query_vector=embeddings[i], limit=1
        )
        novelty = 1.0 - hits[0].score if hits else 1.0
        novelties.append(novelty)

        points.append(PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, exp_id)),
            vector=embeddings[i],
            payload={
                "experiment_id": exp_id,
                "architecture": spec.get("architecture"),
                "strategy_type": spec.get("strategy_type"),
                "pair": spec.get("pair"),
                "timeframe": spec.get("timeframe"),
                "status": result.get("status"),
                "sharpe": result.get("metrics", {}).get("sharpe"),
                "text": texts[i],
            },
        ))

    client.upsert(collection_name=COLLECTION, points=points)
    return novelties
