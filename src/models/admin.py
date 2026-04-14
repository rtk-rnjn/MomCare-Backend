from __future__ import annotations

import uuid
from enum import StrEnum
from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class AdminRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"


class AdminUserDict(TypedDict):
    _id: str
    username: str
    password_hash: str
    role: str
    is_active: bool
    created_at_timestamp: float
    updated_at_timestamp: NotRequired[float]
    last_login_timestamp: NotRequired[float]
    created_by: NotRequired[str | None]


class AdminUserModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    username: str
    role: AdminRole = AdminRole.ADMIN
    is_active: bool = True
    created_at_timestamp: float | None = None
    updated_at_timestamp: float | None = None
    last_login_timestamp: float | None = None
    created_by: str | None = None

    model_config = {"populate_by_name": True}


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class AdminUpdateRequest(BaseModel):
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
