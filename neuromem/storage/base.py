"""Abstract base class for object storage."""

from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Abstract object storage interface (S3/MinIO/OBS)."""

    async def init(self) -> None:
        """Initialize storage (e.g., create bucket). Override if needed."""

    @abstractmethod
    async def upload(
        self,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file. Returns the object key."""
        ...

    @abstractmethod
    async def download(self, object_key: str) -> bytes:
        """Download file by object key."""
        ...

    @abstractmethod
    async def delete(self, object_key: str) -> None:
        """Delete file by object key."""
        ...

    @abstractmethod
    async def get_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Generate a presigned download URL."""
        ...
