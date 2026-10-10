"""
Thin wrapper around ChromaDB's built-in ONNX embedding function.

Produces 384-dimensional float vectors (all-MiniLM-L6-v2).
Lazy-initialises the model once and reuses it for the process lifetime.
No Ollama or GPU required — runs on any CPU-only cloud host.
"""
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

_ef: DefaultEmbeddingFunction | None = None


def _get_ef() -> DefaultEmbeddingFunction:
    global _ef
    if _ef is None:
        _ef = DefaultEmbeddingFunction()
    return _ef


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Returns a list of 384-dim float vectors."""
    ef = _get_ef()
    return [list(v) for v in ef(texts)]


def embed_query(text: str) -> list[float]:
    """Embed a single query string (convenience wrapper)."""
    return embed_texts([text])[0]
