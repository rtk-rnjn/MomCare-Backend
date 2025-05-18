from __future__ import annotations


import boto3
import os
from typing import Dict, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class S3:
    def __init__(self):
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

        self._internal_cache: Dict[str, str] = {}

    def get_presigned_url(self, file_name: str) -> Optional[str]:
        if file_name in self._internal_cache:
            if self._internal_cache[file_name]["expires"] > datetime.now():
                return self._internal_cache[file_name]["url"]

        try:
            response = self.s3_client.generate_presigned_url(
                "get_object",
                Params={'Bucket': self.bucket_name, 'Key': file_name},
                ExpiresIn=1 * 60 * 60,  # 1 hour
            )
            if response:
                self._internal_cache[file_name] = {"url": response, "expires": datetime.now() + timedelta(hours=1)}
                return response
            return response

        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return None
