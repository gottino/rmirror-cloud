"""S3/MinIO storage implementation (for future use)."""

from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings
from app.storage.base import StorageService

settings = get_settings()


class S3StorageService(StorageService):
    """S3-compatible storage implementation."""

    def __init__(self):
        """Initialize S3 client."""
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self.bucket_name = settings.s3_bucket_name
        self.key_prefix = settings.s3_key_prefix

    def _prefixed_key(self, key: str) -> str:
        """Add prefix to key for environment isolation (e.g., staging/)."""
        if self.key_prefix:
            return f"{self.key_prefix}{key}"
        return key

    async def upload_file(
        self, file: BinaryIO, key: str, content_type: str | None = None
    ) -> str:
        """Upload file to S3."""
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        prefixed_key = self._prefixed_key(key)
        self.s3_client.upload_fileobj(file, self.bucket_name, prefixed_key, ExtraArgs=extra_args)
        return key  # Return original key (without prefix) for consistency

    async def download_file(self, key: str) -> bytes:
        """Download file from S3."""
        try:
            prefixed_key = self._prefixed_key(key)
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=prefixed_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {key}")
            raise

    async def delete_file(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            prefixed_key = self._prefixed_key(key)
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=prefixed_key)
            return True
        except ClientError:
            return False

    async def file_exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        try:
            prefixed_key = self._prefixed_key(key)
            self.s3_client.head_object(Bucket=self.bucket_name, Key=prefixed_key)
            return True
        except ClientError:
            return False

    async def get_file_url(self, key: str) -> str:
        """Get presigned URL for S3 object."""
        prefixed_key = self._prefixed_key(key)
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": prefixed_key},
            ExpiresIn=3600,  # 1 hour
        )
