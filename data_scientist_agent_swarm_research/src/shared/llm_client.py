# src/shared/llm_client.py

from openai import OpenAI
from typing import List, Optional
from src.shared.config import SharedConfig

cfg = SharedConfig()

def _client() -> OpenAI:
    return OpenAI(
        base_url=cfg.NOVITA_BASE_URL,
        api_key=cfg.NOVITA_API_KEY,
    )

def chat_analysis(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: Optional[dict] = None,
) -> str:
    """Call the analysis model (qwen3.5-397b). For Strategist, Meta-Learner, Engineer."""
    client = _client()
    kwargs = dict(
        model=cfg.LLM_ANALYSIS_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def chat_routing(
    messages: list,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    """Call the routing model (qwen3-32b). For quick classification decisions."""
    client = _client()
    resp = client.chat.completions.create(
        model=cfg.LLM_ROUTING_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of texts using qwen3-embedding-8b.
    
    HARD CONSTRAINT: max batch size = 10. This function handles chunking.
    Returns list of 4096-dim vectors, one per input text.
    """
    client = _client()
    all_embeddings = []
    batch_size = cfg.LLM_EMBEDDING_BATCH_SIZE  # 10

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(
            model=cfg.LLM_EMBEDDING_MODEL,
            input=batch,
        )
        # Sort by index to preserve order
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


def embed_single(text: str) -> List[float]:
    """Embed a single text. Convenience wrapper."""
    return embed_texts([text])[0]
