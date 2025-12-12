from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from dotenv import load_dotenv

if TYPE_CHECKING:
    pass


_ = load_dotenv(verbose=True)


class S3:
    def __init__(self):
        AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
        AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

        if AWS_ACCESS_KEY is None or AWS_SECRET_KEY is None:
            raise ValueError("AWS_ACCESS_KEY or AWS_SECRET_KEY is not set")

        BUCKET_NAME = os.environ["AWS_BUCKET_NAME"]
        REGION = os.environ["AWS_REGION"]
        self.bucket_name: str = BUCKET_NAME
        self.region: str = REGION

        self.s3_client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
            ),
        )

    async def get_presigned_url(self, file_name: str) -> str | None:
        response = await asyncio.to_thread(
            self.s3_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": file_name},
            ExpiresIn=1 * 60 * 60,  # 1 hour
        )
        return response

    async def _list_s3_items(self, prefix: str, key: str) -> list[str]:
        response = await asyncio.to_thread(
            self.s3_client.list_objects_v2,
            Bucket=self.bucket_name,
            Prefix=prefix,
            Delimiter="/",
        )
        return [item[key] for item in response.get(key == "Key" and "Contents" or "CommonPrefixes", [])]

    async def list_files(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Key")

    async def list_folder(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Prefix")

    async def get_metadata(self, file_name: str) -> dict:
        response = await asyncio.to_thread(
            self.s3_client.head_object,
            Bucket=self.bucket_name,
            Key=file_name,
        )
        return response
