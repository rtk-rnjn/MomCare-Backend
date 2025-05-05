from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, TYPE_CHECKING, Union
import json
import jwt
from dotenv import load_dotenv, unset_key
from google import genai
from pydantic import BaseModel
from pymongo import InsertOne, UpdateOne
import redis
from src.models import User
import asyncio

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY is not set")


class Token(BaseModel):
    sub: str
    email: str
    name: str
    iat: int = int(datetime.now(timezone.utc).timestamp())
    exp: int


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        payload = Token(
            sub=user.id,
            email=user.email_address,
            name=f"{user.first_name} {user.last_name}",
            exp=int((datetime.now(timezone.utc) + timedelta(seconds=expire_in)).timestamp()),
        )

        return jwt.encode(dict(payload), self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[Token]:
        try:
            return Token(**jwt.decode(token, self.secret, algorithms=[self.algorithm]))
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def decode_token(self, token: str) -> Optional[Token]:
        try:
            return Token(
                **jwt.decode(
                    token,
                    self.secret,
                    algorithms=[self.algorithm],
                )
            )
        except jwt.InvalidTokenError:
            raise

class _CacheHandler:
    redis_client: Redis
    mongo_client: AsyncIOMotorClient

    def __init__(self, *, mongo_client: AsyncIOMotorClient):
        self.mongo_client = mongo_client
        self.collection = mongo_client["MomCare"]["users"]

        self.operations: asyncio.Queue[Union[InsertOne, UpdateOne, None]] = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.process_operations())
    
    async def process_operations(self) -> None:
        while True:
            operation = await self.operations.get()
            if operation is None:
                break

            await self.collection.bulk_write([operation])

    async def cancel_operations(self) -> None:
        await self.operations.put(None)
        await self.loop.shutdown_asyncgens()

    def on_startup(self) -> List[Callable]:
        async def ping_redis():
            return await self.redis_client.ping()
        
        async def ping_mongo():
            return await self.mongo_client.admin.command("ping")
        
        return [ping_redis, ping_mongo]
    
    def on_shutdown(self) -> List[Callable]:
        async def close_redis():
            await self.redis_client.close()
        
        async def close_mongo():
            self.mongo_client.close()
        
        return [close_redis, close_mongo]

class CacheHandler(_CacheHandler):
    def __init__(self, *, redis_client: Redis, mongo_client: AsyncIOMotorClient):
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.collection = mongo_client["MomCare"]["users"]

    async def get_user(self, user_id: str) -> Optional[User]:
        user = await self.redis_client.get(user_id)
        if user:
            user = json.loads(user)
            return User(**user)

        user = await self.collection.find_one({"_id": user_id})
        if user:
            await self.redis_client.set(user_id, user)
            return User(**user)

        return None
    
    async def set_user(self, *, user: User) -> None:
        payload = user.model_dump_json()
        await self.redis_client.set(user.id, payload, ex=3600)

    async def update_user(self, *, user: User) -> None:
        await self.redis_client.delete(user.id)

    async def delete_user(self, *, user_id: str) -> None:
        await self.redis_client.delete(user_id)
