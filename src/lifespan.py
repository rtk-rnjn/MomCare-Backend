from contextlib import asynccontextmanager

from fastapi import FastAPI
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        if hasattr(app.state, "redis_client"):
            redis_client: Redis = app.state.redis_client
            await redis_client.close()

        if hasattr(app.state, "mongo_client"):
            mongo_client: AsyncMongoClient = app.state.mongo_client
            await mongo_client.close()
