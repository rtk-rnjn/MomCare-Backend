from __future__ import annotations

import asyncio
import shlex
from typing import AsyncIterator, TypedDict

from argon2 import PasswordHasher


class CommandOutput(TypedDict):
    type: str
    data: str
    exit_code: int | None


class StreamOutput(TypedDict):
    type: str
    data: str


class TerminalExecutor:
    """Execute terminal commands safely through a web interface."""

    MAX_OUTPUT_LENGTH = 10000
    TIMEOUT_SECONDS = 30

    ph = PasswordHasher()

    def __init__(self):
        pass

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with Argon2."""
        return TerminalExecutor.ph.hash(password)

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return TerminalExecutor.ph.verify(expected_hash, password)

    async def read_stream(self, stream: asyncio.StreamReader, stream_type: str) -> AsyncIterator[StreamOutput]:
        """Read from stdout or stderr and yield lines."""
        total_bytes = 0
        while True:
            line = await stream.readline()
            if not line:
                break

            decoded_line = line.decode("utf-8", errors="replace").rstrip()
            total_bytes += len(line)

            if total_bytes > self.MAX_OUTPUT_LENGTH:
                yield StreamOutput(type=stream_type, data="... (output truncated - limit reached)")
                break

            yield StreamOutput(type=stream_type, data=decoded_line)

    async def execute_command_stream(self, command: str) -> AsyncIterator[CommandOutput]:
        """Execute command and stream output line by line."""
        parts = shlex.split(command.strip())
        if not parts:
            yield CommandOutput(type="error", data="No command provided", exit_code=None)
            return

        yield CommandOutput(type="start", data=f"Executing: {command}", exit_code=None)

        process = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Read stdout and stderr concurrently
        tasks = []
        if process.stdout:
            tasks.append(self.read_stream(process.stdout, "stdout"))
        if process.stderr:
            tasks.append(self.read_stream(process.stderr, "stderr"))

        # Yield output as it comes
        for task in tasks:
            async for item in task:
                yield item

        # Wait for process to complete
        try:
            await asyncio.wait_for(process.wait(), timeout=self.TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            process.kill()
            yield CommandOutput(type="error", data="Command execution timed out", exit_code=None)
            return

        if process.returncode == 0:
            yield CommandOutput(type="end", data="Command completed successfully", exit_code=0)
        else:
            yield CommandOutput(type="end", data=f"Command failed with exit code {process.returncode}", exit_code=process.returncode)
