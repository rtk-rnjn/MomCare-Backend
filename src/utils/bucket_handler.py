from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Optional

import boto3
from dotenv import load_dotenv

if TYPE_CHECKING:
    from src.utils.cache_handler import CacheHandler

load_dotenv()


class S3:
    def __init__(self, cache_handler: CacheHandler):
        AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
        AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

        if AWS_ACCESS_KEY is None or AWS_SECRET_KEY is None:
            raise ValueError("AWS_ACCESS_KEY or AWS_SECRET_KEY is not set")

        BUCKET_NAME = os.environ["AWS_BUCKET_NAME"]
        REGION = os.environ["AWS_REGION"]
        self.bucket_name = BUCKET_NAME
        self.region = REGION

        self.s3_client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
        )

        self.cache_handler = cache_handler

    async def get_presigned_url(self, file_name: str) -> Optional[str]:
        link = await self.cache_handler.get_file_link(file_name=file_name)
        if link:
            return link

        try:
            response = await asyncio.to_thread(
                self.s3_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_name},
                ExpiresIn=1 * 60 * 60,  # 1 hour
            )
            if response:
                await self.cache_handler.set_file_link(file_name=file_name, file_link=response)
                return response
            return response

        except Exception:
            return None

    async def _list_s3_items(self, prefix: str, key: str) -> list[str]:
        try:
            response = await asyncio.to_thread(self.s3_client.list_objects_v2, Bucket=self.bucket_name, Prefix=prefix, Delimiter="/")
            return [item[key] for item in response.get(key == "Key" and "Contents" or "CommonPrefixes", [])]
        except Exception:
            return []

    async def list_files(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Key")

    async def list_folder(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Prefix")
