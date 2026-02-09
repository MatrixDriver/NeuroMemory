"""Embedding service - generate vector embeddings."""

import httpx

from server.app.core.config import get_settings
from server.app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self):
        self._settings = get_settings()

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if self._settings.embedding_provider == "siliconflow":
            return await self._embed_siliconflow(text)
        raise ValueError(f"Unknown embedding provider: {self._settings.embedding_provider}")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if self._settings.embedding_provider == "siliconflow":
            return await self._embed_siliconflow_batch(texts)
        raise ValueError(f"Unknown embedding provider: {self._settings.embedding_provider}")

    async def _embed_siliconflow(self, text: str) -> list[float]:
        result = await self._embed_siliconflow_batch([text])
        return result[0]

    async def _embed_siliconflow_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._settings.siliconflow_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._settings.siliconflow_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.siliconflow_model,
                    "input": texts,
                    "encoding_format": "float",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Sort by index to maintain order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
