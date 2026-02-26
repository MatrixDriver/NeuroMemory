"""S3-compatible object storage (MinIO / AWS S3 / Huawei OBS)."""

import asyncio
import logging
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from neuromem.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


class S3Storage(ObjectStorage):
    """S3-compatible object storage client."""

    def __init__(
        self,
        endpoint: str = "http://localhost:9000",
        access_key: str = "neuromem",
        secret_key: str = "neuromem123",
        bucket: str = "neuromem-files",
        region: str = "us-east-1",
    ):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    async def init(self) -> None:
        """Create bucket if it doesn't exist."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
            logger.info("S3 bucket exists: %s", self._bucket)
        except ClientError:
            await asyncio.to_thread(
                self._client.create_bucket, Bucket=self._bucket
            )
            logger.info("S3 bucket created: %s", self._bucket)

    async def upload(
        self,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file. Returns the object key."""
        object_key = f"{prefix}/{uuid.uuid4()}/{filename}"
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("Uploaded %s (%d bytes)", object_key, len(data))
        return object_key

    async def download(self, object_key: str) -> bytes:
        resp = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=object_key,
        )
        data = await asyncio.to_thread(resp["Body"].read)
        return data

    async def delete(self, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=object_key,
        )
        logger.info("Deleted %s", object_key)

    async def get_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )
        return url
