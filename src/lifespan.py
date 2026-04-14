from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


async def _bootstrap_super_admin(app: FastAPI) -> None:
    """Seed the bootstrap super admin from env vars if it doesn't exist."""
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")

    if not username or not password:
        logger.warning("ADMIN_USERNAME or ADMIN_PASSWORD not set; skipping super admin bootstrap")
        return

    db = app.state.mongo_database
    admin_collection = db["admin_users"]

    existing = await admin_collection.find_one({"role": "super_admin"})
    if existing:
        logger.info(f"Super admin already exists: {existing['username']}")
        return

    import bcrypt

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    admin_doc = {
        "_id": str(uuid.uuid4()),
        "username": username,
        "password_hash": password_hash,
        "role": "super_admin",
        "is_active": True,
        "created_at_timestamp": time.time(),
        "created_by": None,
    }

    await admin_collection.insert_one(admin_doc)
    logger.info(f"Bootstrap super admin created: {username}")

    # Create index for unique username
    await admin_collection.create_index("username", unique=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _bootstrap_super_admin(app)
        yield
    finally:
        if hasattr(app.state, "redis_client"):
            redis_client: Redis = app.state.redis_client
            await redis_client.close()

        if hasattr(app.state, "mongo_client"):
            mongo_client: AsyncMongoClient = app.state.mongo_client
            await mongo_client.close()
