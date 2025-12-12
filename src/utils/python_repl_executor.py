from __future__ import annotations

import typing

from argon2 import PasswordHasher

from .async_code_executor import AsyncCodeExecutor, Scope


class ExecutionResult(typing.TypedDict):
    success: bool
    result: str | None
    error: str | None
    command: str


class PythonReplExecutor:
    """Execute Python code safely through a web interface."""

    ph = PasswordHasher()

    def __init__(self):
        self.global_scope = Scope({})

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with Argon2."""
        return PythonReplExecutor.ph.hash(password)

    @staticmethod
    def verify_password(password: str, expected_hash: str) -> bool:
        """Verify password against expected hash."""
        return PythonReplExecutor.ph.verify(expected_hash, password)

    def _create_scope(self, **kwargs: typing.Any) -> Scope:
        """Create a new scope with given variables."""
        return Scope(kwargs)

    async def execute(self, raw_code: str, *, scope: Scope) -> ExecutionResult:
        """Execute Python code safely."""
        result = ""

        self.global_scope.update(scope)

        try:
            async for x in AsyncCodeExecutor(raw_code, scope=self.global_scope, auto_return=True):
                if x is not None:
                    result += str(x) + "\n"

        except Exception as e:
            return ExecutionResult(success=False, result=None, error=str(e), command=raw_code)

        return ExecutionResult(success=True, result=result.strip() or "(no output)", error=None, command=raw_code)

    def reset_scope(self):
        """Reset the REPL scope."""
        self.global_scope = Scope({})
