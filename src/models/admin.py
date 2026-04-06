from __future__ import annotations

import uuid
from enum import StrEnum
from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class AdminRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    OPERATOR = "operator"


class AdminUserDict(TypedDict, total=False):
    _id: str
    username: str
    display_name: str
    password_hash: str
    role: AdminRole
    created_at_timestamp: float
    updated_at_timestamp: float
    last_login_timestamp: NotRequired[float | None]
    is_active: bool
    allowed_ips: NotRequired[list[str]]


class AdminAuditLogDict(TypedDict):
    _id: str
    admin_id: str
    admin_username: str
    action: str
    resource_type: str
    resource_id: NotRequired[str | None]
    before_state: NotRequired[dict | None]
    after_state: NotRequired[dict | None]
    ip_address: str
    timestamp: float
    details: NotRequired[str | None]


class AdminLoginAttemptDict(TypedDict):
    _id: str
    username: str
    ip_address: str
    success: bool
    timestamp: float
    user_agent: NotRequired[str | None]
    failure_reason: NotRequired[str | None]


class AdminUserCreateModel(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    role: AdminRole = Field(default=AdminRole.OPERATOR)

    class Config:
        extra = "ignore"


class AdminUserUpdateModel(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    role: AdminRole | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    allowed_ips: list[str] | None = Field(default=None)

    class Config:
        extra = "ignore"


def make_admin_user(username: str, password_hash: str, display_name: str, role: AdminRole = AdminRole.OPERATOR) -> AdminUserDict:
    import arrow

    now = arrow.utcnow().timestamp()
    return AdminUserDict(
        _id=str(uuid.uuid4()),
        username=username,
        display_name=display_name,
        password_hash=password_hash,
        role=role,
        created_at_timestamp=now,
        updated_at_timestamp=now,
        last_login_timestamp=None,
        is_active=True,
        allowed_ips=[],
    )


def make_audit_log(
    admin_id: str,
    admin_username: str,
    action: str,
    resource_type: str,
    ip_address: str,
    resource_id: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    details: str | None = None,
) -> AdminAuditLogDict:
    import arrow

    return AdminAuditLogDict(
        _id=str(uuid.uuid4()),
        admin_id=admin_id,
        admin_username=admin_username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        timestamp=arrow.utcnow().timestamp(),
        details=details,
    )


def make_login_attempt(
    username: str,
    ip_address: str,
    success: bool,
    user_agent: str | None = None,
    failure_reason: str | None = None,
) -> AdminLoginAttemptDict:
    import arrow

    return AdminLoginAttemptDict(
        _id=str(uuid.uuid4()),
        username=username,
        ip_address=ip_address,
        success=success,
        timestamp=arrow.utcnow().timestamp(),
        user_agent=user_agent,
        failure_reason=failure_reason,
    )
