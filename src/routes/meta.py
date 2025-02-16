from __future__ import annotations

import binascii
import hashlib
import hmac
import os
import subprocess
from time import perf_counter
from typing import Literal

from fastapi import Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from src.app import app, mongo_client

__all__ = ("ping", "root")

GITHUB_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


class PingResponse(BaseModel):
    success: bool = Field(
        ...,
        description="Whether the ping was successful. True if database is reachable, False otherwise.",
    )
    ping: Literal["pong"] = Field(
        "pong",
        description="The response to the ping request. Should be 'pong' if successful.",
    )
    response_time: float = Field(
        ...,
        description="The time taken to receive a response from the database in seconds.",
    )


class RootResponse(BaseModel):
    success: Literal[True] = Field(
        True,
        description="Whether the request was successful. Should always be True.",
        frozen=True,
    )
    message: Literal["Welcome to MomCare API!"] = Field(
        "Welcome to MomCare API!",
        description="A welcome message for the API.",
        frozen=True,
    )


class GitHubPushPayload(BaseModel):
    ref: str


def verify_signature(x_hub_signature_256: str = Header(...), body: bytes = b""):
    digest = hmac.new(GITHUB_SECRET.encode(), body, hashlib.sha256).digest()
    expected_signature = "sha256=" + binascii.hexlify(digest).decode()

    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")


@app.get("/ping")
async def ping() -> PingResponse:
    """
    Check if the database is reachable. Returns the response time if successful.
    """

    start = perf_counter()
    success = True
    try:
        await mongo_client.server_info()
    except Exception:
        success = False

    fin = perf_counter()

    return PingResponse(success=success, ping="pong", response_time=fin - start)


@app.get("/")
async def root() -> RootResponse:
    """
    A welcome message for the API. This endpoint is used to check if the API is running; it should always return True.
    """
    return RootResponse(success=True, message="Welcome to MomCare API!")


@app.post("/webhook", dependencies=[Depends(verify_signature)])
def github_webhook(payload: GitHubPushPayload, response: Response):
    """
    Private endpoint for GitHub webhook. This endpoint is used to automatically deploy the API when a push event is detected on the main branch.
    """
    if payload.ref == "refs/heads/main":
        subprocess.run(["pm2", "restart", "all"], check=True)
    return Response(status_code=204)
