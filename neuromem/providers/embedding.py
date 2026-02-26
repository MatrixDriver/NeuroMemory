"""Abstract base class for embedding providers."""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract embedding provider interface."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts. Default: sequential calls."""
        return [await self.embed(t) for t in texts]

    @property
    @abstractmethod
    def dims(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...
