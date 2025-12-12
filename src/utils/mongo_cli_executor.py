from __future__ import annotations

import typing

from argon2 import PasswordHasher
from bson import ObjectId, json_util
from motor.motor_asyncio import AsyncIOMotorClient

from .async_code_executor import AsyncCodeExecutor, Scope


class MongoCliExecutor:
    """Execute MongoDB commands safely through a web interface."""

    ph = PasswordHasher()

    def __init__(self, mongo_client: AsyncIOMotorClient, database_name: str = "MomCare"):
        self.mongo_client = mongo_client
        self.database_name = database_name
        self.db = mongo_client[database_name]

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with Argon2."""
        return MongoCliExecutor.ph.hash(password)

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return MongoCliExecutor.ph.verify(expected_hash, password)

    async def execute_command(self, raw_code: str) -> dict[str, typing.Any]:
        """Execute a MongoDB command safely."""
        context = {
            "db": self.db,
            "ObjectId": ObjectId,
            "json_util": json_util,
        }
        scope = Scope(context)
        result = ""

        try:
            async for x in AsyncCodeExecutor(raw_code, scope=scope, auto_return=True):
                result += self._format_result(x) + "\n"

        except Exception as e:
            return {"success": False, "error": str(e), "command": raw_code}

        return {"success": True, "result": result.strip(), "command": raw_code}

    def _format_result(self, result: typing.Any) -> str:
        """Format result for display."""
        if result is None:
            return "(null)"

        if isinstance(result, (dict, list)):
            return json_util.dumps(result, indent=2)

        if isinstance(result, ObjectId):
            return str(result)

        return str(result)

    async def get_collections(self) -> list[str]:
        """Get list of collections in the database."""
        return await self.db.list_collection_names()
