"""Local sentence-transformers embedding provider."""

from __future__ import annotations

from neuromem.providers.embedding import EmbeddingProvider


class SentenceTransformerEmbedding(EmbeddingProvider):
    """Local embedding using sentence-transformers (no API calls).

    Usage:
        embedding = SentenceTransformerEmbedding(model="all-MiniLM-L6-v2")
        # or for multilingual / higher quality:
        embedding = SentenceTransformerEmbedding(model="BAAI/bge-m3")
    """

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model_name = model
        self._model = SentenceTransformer(model)
        self._dims = self._model.get_sentence_embedding_dimension()

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return vecs.tolist()
