"""API-based multilingual embeddings (Gemini by default). No local model, so
it fits on a 512 MB free host. The output size must equal the vector(768)
column -- see settings.embedding_dimensions."""

import logging
import time

import httpx

from settings import settings

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_BATCH = 50
_TIMEOUT = 30.0
logger = logging.getLogger("sahayak.rag")
# Free-tier Gemini returns 429 when many chunks are embedded at once. Ingestion
# can wait it out; a user's question cannot, so queries retry only briefly.
_DOC_WAITS = (15, 30, 60, 60)
_QUERY_WAITS = (1, 3)


class EmbeddingError(Exception):
    pass


def _task_type(is_query: bool) -> str:
    return "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"


def _post_with_retry(client: httpx.Client, url: str, waits: tuple, **kwargs) -> httpx.Response:
    for attempt in range(len(waits) + 1):
        try:
            response = client.post(url, **kwargs)
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
        except (httpx.TimeoutException, httpx.TransportError):
            response = None
        if attempt == len(waits):
            break
        logger.warning("embedding request throttled/failed; retrying in %ss", waits[attempt])
        time.sleep(waits[attempt])
    if response is None:
        raise httpx.TransportError("embedding request failed after retries")
    return response


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    if not settings.embedding_api_key:
        raise EmbeddingError("EMBEDDING_API_KEY is not configured")

    model = settings.embedding_model
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            for start in range(0, len(texts), _BATCH):
                batch = texts[start : start + _BATCH]
                response = _post_with_retry(
                    client,
                    f"{_BASE}/{model}:batchEmbedContents",
                    _QUERY_WAITS if is_query else _DOC_WAITS,
                    headers={"x-goog-api-key": settings.embedding_api_key},
                    json={
                        "requests": [
                            {
                                "model": f"models/{model}",
                                "content": {"parts": [{"text": text}]},
                                "taskType": _task_type(is_query),
                                "outputDimensionality": settings.embedding_dimensions,
                            }
                            for text in batch
                        ]
                    },
                )
                response.raise_for_status()
                vectors.extend(_normalize(item["values"]) for item in response.json()["embeddings"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise EmbeddingError(f"Embedding request failed: {exc}") from exc

    if any(len(v) != settings.embedding_dimensions for v in vectors):
        raise EmbeddingError("Embedding size does not match settings.embedding_dimensions")
    return vectors


def _normalize(vector: list[float]) -> list[float]:
    # Truncated (reduced-dimension) Gemini embeddings are not unit length.
    norm = sum(x * x for x in vector) ** 0.5 or 1.0
    return [x / norm for x in vector]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], is_query=True)[0]


def to_pgvector(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
