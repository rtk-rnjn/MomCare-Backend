from __future__ import annotations

import time
import uuid
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection


class AuditLogger:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def log(
        self,
        *,
        admin_id: str,
        admin_username: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        doc = {
            "_id": str(uuid.uuid4()),
            "admin_id": admin_id,
            "admin_username": admin_username,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "timestamp": time.time(),
            "before_data": before_data,
            "after_data": after_data,
            "metadata": metadata,
            "ip_address": ip_address,
        }
        await self.collection.insert_one(doc)
