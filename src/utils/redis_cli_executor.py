from __future__ import annotations

import hashlib
import secrets
from typing import Any

from redis.asyncio import Redis


class RedisCliExecutor:
    """Execute Redis commands safely through a web interface."""

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
        """Hash password with SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return secrets.compare_digest(RedisCliExecutor.hash_password(password), expected_hash)

    async def execute_command(self, command: str) -> dict[str, Any]:
        try:
            parts = command.strip().split()
            if not parts:
                return {"success": False, "error": "Empty command"}

            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in self.FORBIDDEN_COMMANDS:
                return {"success": False, "error": f"Command '{cmd}' is forbidden for security reasons"}

            if cmd not in self.ALLOWED_COMMANDS:
                return {"success": False, "error": f"Command '{cmd}' is not in the allowed list"}

            result = await self.redis_client.execute_command(cmd, *args)

            formatted_result = self._format_result(result)

            return {"success": True, "result": formatted_result, "command": command}

        except Exception as e:
            return {"success": False, "error": str(e), "command": command}

    def _format_result(self, result: Any) -> str:
        if result is None:
            return "(nil)"
        elif isinstance(result, bytes):
            return result.decode("utf-8", errors="replace")
        elif isinstance(result, list):
            if not result:
                return "(empty list)"
            formatted = []
            for i, item in enumerate(result, 1):
                if isinstance(item, bytes):
                    formatted.append(f"{i}) {item.decode('utf-8', errors='replace')}")
                else:
                    formatted.append(f"{i}) {item}")
            return "\n".join(formatted)
        elif isinstance(result, dict):
            formatted = []
            for key, value in result.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                v = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                formatted.append(f"{k}: {v}")
            return "\n".join(formatted)
        else:
            return str(result)

    def get_allowed_commands(self) -> list[str]:
        return sorted(list(self.ALLOWED_COMMANDS))
