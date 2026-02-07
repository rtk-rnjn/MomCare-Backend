from __future__ import annotations

from pydantic import BaseModel, Field


class ServerMessage(BaseModel):
    detail: str = Field(
        ...,
        description="A message describing the result of the operation.",
    )

    class Config:
        extra = "ignore"


class RegistrationResponse(BaseModel):
    email_address: str = Field(..., description="The registered email address.", examples=["user@example.com"], title="Email Address")
    access_token: str = Field(
        ...,
        description="The access token for authentication.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        title="Access Token",
    )
    refresh_token: str = Field(
        ...,
        description="The refresh token for obtaining new access tokens.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        title="Refresh Token",
    )

    class Config:
        extra = "ignore"


class TimestampRange(BaseModel):
    start_timestamp: float = Field(
        ...,
        description="The start of the timestamp range.",
        examples=[1622505600.0],
        title="Start Timestamp",
    )
    end_timestamp: float = Field(
        ...,
        description="The end of the timestamp range.",
        examples=[1622592000.0],
        title="End Timestamp",
    )
