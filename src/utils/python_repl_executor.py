from __future__ import annotations

import hashlib
import secrets
import typing

from .async_code_executor import AsyncCodeExecutor, Scope


class PythonReplExecutor:
    """Execute Python code safely through a web interface."""

    def __init__(self):
        self.global_scope = Scope({})

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return secrets.compare_digest(PythonReplExecutor.hash_password(password), expected_hash)
    
    def _create_scope(self, **kwargs: typing.Any) -> Scope:
        """Create a new scope with given variables."""
        return Scope(kwargs)

    async def execute(self, raw_code: str, *, scope: Scope) -> dict[str, typing.Any]:
        """Execute Python code safely."""
        result = ""

        self.global_scope.update(scope)

        try:
            async for x in AsyncCodeExecutor(raw_code, scope=self.global_scope, auto_return=True):
                if x is not None:
                    result += str(x) + "\n"

        except Exception as e:
            return {"success": False, "error": str(e), "command": raw_code}

        return {"success": True, "result": result.strip() or "(no output)", "command": raw_code}

    def reset_scope(self):
        """Reset the REPL scope."""
        self.global_scope = Scope({})
