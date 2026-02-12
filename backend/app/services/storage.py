from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Tuple

import boto3
from botocore.client import Config


class StorageService:
    @staticmethod
    def _client():
        endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")
        access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
        region = os.getenv("S3_REGION", "us-east-1")
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    @staticmethod
    def ensure_bucket(bucket: str):
        client = StorageService._client()
        buckets = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
        if bucket not in buckets:
            client.create_bucket(Bucket=bucket)

    @staticmethod
    def upload_bytes(key: str, data: bytes, content_type: str | None = None) -> str:
        bucket = os.getenv("S3_BUCKET", "evidence-crusher")
        StorageService.ensure_bucket(bucket)
        client = StorageService._client()
        extra = {"ContentType": content_type} if content_type else {}
        client.put_object(Bucket=bucket, Key=key, Body=data, **extra)
        return f"s3://{bucket}/{key}"

    @staticmethod
    def download_bytes(s3_url: str) -> bytes:
        bucket, key = StorageService.parse_s3_url(s3_url)
        client = StorageService._client()
        obj = client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    @staticmethod
    def download_to_tempfile(s3_url: str) -> Path:
        data = StorageService.download_bytes(s3_url)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(s3_url).suffix or ".pdf")
        tmp.write(data)
        tmp.flush()
        return Path(tmp.name)

    @staticmethod
    def delete_object(s3_url: str) -> None:
        bucket, key = StorageService.parse_s3_url(s3_url)
        client = StorageService._client()
        client.delete_object(Bucket=bucket, Key=key)

    @staticmethod
    def parse_s3_url(s3_url: str) -> Tuple[str, str]:
        if not s3_url.startswith("s3://"):
            raise ValueError("Not an s3 url")
        path = s3_url[len("s3://") :]
        bucket, key = path.split("/", 1)
        return bucket, key
