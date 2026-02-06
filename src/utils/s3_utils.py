from __future__ import annotations

import os
from contextlib import AsyncExitStack

from aiobotocore.session import AioSession, get_session
from aiobotocore.config import AioConfig
from dotenv import load_dotenv
from types_aiobotocore_s3.client import S3Client


_ = load_dotenv(verbose=True)

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

BUCKET_NAME = os.environ["AWS_BUCKET_NAME"]
REGION = os.environ["AWS_REGION"]


class Manager:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._s3_client = None

    async def __aenter__(self):
        session = AioSession()
        self._s3_client = await self._exit_stack.enter_async_context(
            session.create_client("s3")
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)


async def create_s3_client(session: AioSession, exit_stack: AsyncExitStack) -> S3Client:
    client = await exit_stack.enter_async_context(
        session.create_client(
            "s3",
            region_name=REGION,
            aws_secret_access_key=AWS_SECRET_KEY,
            aws_access_key_id=AWS_ACCESS_KEY,
            config=AioConfig(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
            ),
        )
    )
    return client


class S3:
    def __init__(self):
        self.bucket_name: str = BUCKET_NAME

        self.session = get_session()

    async def get_presigned_url(self, file_name: str) -> str:
        async with AsyncExitStack() as stack:
            s3_client = await create_s3_client(self.session, stack)
            response = await s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_name},
                ExpiresIn=1 * 60 * 60,  # 1 hour
            )
            return response

    async def _list_s3_items(self, prefix: str, key: str) -> list[str]:
        async with AsyncExitStack() as stack:
            s3_client = await create_s3_client(self.session, stack)
            response = await s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter="/",
            )
            return [
                item[key]
                for item in response.get(
                    key == "Key" and "Contents" or "CommonPrefixes", []
                )
            ]

    async def list_files(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Key")

    async def list_folder(self, prefix: str) -> list[str]:
        return await self._list_s3_items(prefix, "Prefix")

    async def get_metadata(self, file_name: str):
        async with AsyncExitStack() as stack:
            s3_client = await create_s3_client(self.session, stack)
            response = await s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_name,
            )
            return response
