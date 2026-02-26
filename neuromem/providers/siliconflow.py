"""SiliconFlow embedding provider (BAAI/bge-m3)."""

import httpx

from neuromem.providers.embedding import EmbeddingProvider


class SiliconFlowEmbedding(EmbeddingProvider):
    """SiliconFlow embedding using BAAI/bge-m3 (1024 dims)."""

    def __init__(
        self,
        api_key: str,
        model: str = "BAAI/bge-m3",
        base_url: str = "https://api.siliconflow.cn/v1",
        dimensions: int = 1024,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._dims = dimensions

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        result = await self.embed_batch([text])
        return result[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "input": texts,
                    "encoding_format": "float",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]
