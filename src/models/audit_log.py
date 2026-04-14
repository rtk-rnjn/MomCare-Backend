from __future__ import annotations

import uuid
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field


class AuditLogDict(TypedDict):
    _id: str
    admin_id: str
    admin_username: str
    action: str
    target_type: str
    target_id: NotRequired[str | None]
    timestamp: float
    before_data: NotRequired[dict[str, Any] | None]
    after_data: NotRequired[dict[str, Any] | None]
    metadata: NotRequired[dict[str, Any] | None]
    ip_address: NotRequired[str | None]


class AuditLogModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    admin_id: str
    admin_username: str
    action: str
    target_type: str
    target_id: str | None = None
    timestamp: float
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    ip_address: str | None = None

    model_config = {"populate_by_name": True}
