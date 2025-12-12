from __future__ import annotations

import inspect
from typing import Any, TypedDict

from argon2 import PasswordHasher
from redis.asyncio import Redis


class CommandResult(TypedDict):
    success: bool
    result: str | None
    error: str | None
    command: str


class RedisCliExecutor:
    """Execute Redis commands safely through a web interface."""

    ph = PasswordHasher()

    ALLOWED_COMMANDS = {
        "get",
        "set",
        "del",
        "exists",
        "keys",
        "ttl",
        "expire",
        "info",
        "dbsize",
        "ping",
        "echo",
        "type",
        "scan",
        "hget",
        "hset",
        "hdel",
        "hgetall",
        "hkeys",
        "hvals",
        "lrange",
        "llen",
        "lpush",
        "rpush",
        "lpop",
        "rpop",
        "smembers",
        "sadd",
        "srem",
        "scard",
        "zrange",
        "zadd",
        "zrem",
        "zcard",
        "zscore",
        "mget",
        "mset",
        "incr",
        "decr",
        "strlen",
    }

    FORBIDDEN_COMMANDS = {
        "flushdb",
        "flushall",
        "shutdown",
        "config",
        "script",
        "eval",
        "evalsha",
        "debug",
        "save",
        "bgsave",
        "migrate",
    }

    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with Argon2."""
        return RedisCliExecutor.ph.hash(password)

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return RedisCliExecutor.ph.verify(expected_hash, password)

    async def execute_command(self, command: str) -> CommandResult:
        try:
            parts = command.strip().split()
            if not parts:
                return CommandResult(success=False, result=None, error="No command provided", command=command)

            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in self.FORBIDDEN_COMMANDS:
                return CommandResult(
                    success=False, result=None, error=f"Command '{cmd}' is forbidden for security reasons", command=command
                )

            if cmd not in self.ALLOWED_COMMANDS:
                return CommandResult(success=False, result=None, error=f"Command '{cmd}' is not in the allowed list", command=command)

            execute_command_method = self.redis_client.execute_command
            if not inspect.iscoroutinefunction(execute_command_method):
                result = execute_command_method(cmd, *args)
            else:
                result = await self.redis_client.execute_command(cmd, *args)

            formatted_result = self._format_result(result)

            return CommandResult(success=True, result=formatted_result, error=None, command=command)

        except Exception as e:
            return CommandResult(success=False, result=None, error=str(e), command=command)

    def _format_result(self, result: Any) -> str:
        if result is None:
            return "(nil)"

        if isinstance(result, bytes):
            return result.decode("utf-8", errors="replace")

        if isinstance(result, list):
            if not result:
                return "(empty list)"
            formatted = []
            for i, item in enumerate(result, 1):
                if isinstance(item, bytes):
                    formatted.append(f"{i}) {item.decode('utf-8', errors='replace')}")
                else:
                    formatted.append(f"{i}) {item}")
            return "\n".join(formatted)

        if isinstance(result, dict):
            formatted = []
            for key, value in result.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                v = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                formatted.append(f"{k}: {v}")
            return "\n".join(formatted)

        return str(result)

    def get_allowed_commands(self) -> list[str]:
        return sorted(list(self.ALLOWED_COMMANDS))
