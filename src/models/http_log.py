from __future__ import annotations

import uuid
from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class HTTPLogDict(TypedDict):
    _id: str
    timestamp: float
    method: str
    path: str
    status_code: int
    process_time_ms: float
    client_ip: str
    query_string: NotRequired[str | None]


class HTTPLogModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    timestamp: float
    method: str
    path: str
    status_code: int
    process_time_ms: float
    client_ip: str
    query_string: str | None = None

    model_config = {"populate_by_name": True}
