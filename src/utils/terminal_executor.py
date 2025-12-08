from __future__ import annotations

import asyncio
import hashlib
import secrets
import shlex
from typing import Any, AsyncIterator


class TerminalExecutor:
    """Execute terminal commands safely through a web interface."""

    MAX_OUTPUT_LENGTH = 10000
    TIMEOUT_SECONDS = 30

    def __init__(self):
        pass

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return secrets.compare_digest(TerminalExecutor.hash_password(password), expected_hash)

    async def execute_command_stream(self, command: str) -> AsyncIterator[dict[str, Any]]:
        """Execute command and stream output line by line."""
        try:
            parts = shlex.split(command.strip())
            if not parts:
                yield {"type": "error", "data": "Empty command"}
                return

            yield {"type": "start", "data": f"Executing: {command}"}

            process = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def read_stream(stream, stream_type):
                """Read from stdout or stderr and yield lines."""
                total_bytes = 0
                while True:
                    line = await stream.readline()
                    if not line:
                        break

                    decoded_line = line.decode("utf-8", errors="replace").rstrip()
                    total_bytes += len(line)

                    if total_bytes > self.MAX_OUTPUT_LENGTH:
                        yield {"type": stream_type, "data": "... (output truncated - limit reached)"}
                        break

                    yield {"type": stream_type, "data": decoded_line}

            # Read stdout and stderr concurrently
            tasks = []
            if process.stdout:
                tasks.append(read_stream(process.stdout, "stdout"))
            if process.stderr:
                tasks.append(read_stream(process.stderr, "stderr"))

            # Yield output as it comes
            for task in tasks:
                async for item in task:
                    yield item

            # Wait for process to complete
            try:
                await asyncio.wait_for(process.wait(), timeout=self.TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                yield {"type": "error", "data": "Command execution timed out"}
                return

            if process.returncode == 0:
                yield {"type": "end", "data": "Command completed successfully", "exit_code": 0}
            else:
                yield {"type": "end", "data": f"Command failed with exit code {process.returncode}", "exit_code": process.returncode}

        except Exception as e:
            yield {"type": "error", "data": str(e)}
