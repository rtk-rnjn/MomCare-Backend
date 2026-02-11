from __future__ import annotations

import sys
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TextIO

import colorama
from colorama import Fore, Style
from fastapi import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

colorama.init(autoreset=True)


@dataclass
class ConsoleLoggingMiddleware:
    app: ASGIApp
    output: TextIO = sys.stdout

    def __post_init__(self) -> None:
        self._setup_uvicorn_logging()

    # Color mappings for status codes and HTTP methods
    _STATUS_COLORS = {
        range(200, 300): Fore.BLACK + colorama.Back.GREEN,
        range(300, 400): Fore.BLACK + colorama.Back.YELLOW,
        range(400, 500): Fore.WHITE + colorama.Back.RED,
        range(500, 600): Fore.WHITE + colorama.Back.MAGENTA,
    }

    _METHOD_COLORS = {
        "GET": Fore.WHITE + colorama.Back.BLUE,
        "POST": Fore.WHITE + colorama.Back.GREEN,
        "PUT": Fore.BLACK + colorama.Back.YELLOW,
        "DELETE": Fore.WHITE + colorama.Back.RED,
        "PATCH": Fore.WHITE + colorama.Back.CYAN,
        "HEAD": Fore.WHITE + colorama.Back.MAGENTA,
        "OPTIONS": Fore.BLACK + colorama.Back.WHITE,
    }

    _DEFAULT_COLOR = Fore.BLACK + colorama.Back.WHITE

    @staticmethod
    def _setup_uvicorn_logging() -> None:
        """Configure Uvicorn logging, disabling standard access logs."""
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        uvicorn_access_logger.disabled = True
        uvicorn_access_logger.propagate = False

        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.setLevel(logging.INFO)

    @staticmethod
    def _format_duration(duration_ms: float) -> str:
        """Format duration in a human-readable way."""

        SECOND_TO_MS = 1000
        MINUTE_TO_MS = 60 * SECOND_TO_MS
        HOUR_TO_MS = 60 * MINUTE_TO_MS

        if duration_ms < 1:
            return f"{duration_ms * 1000:.0f}µs"
        elif duration_ms < SECOND_TO_MS:
            return f"{duration_ms:.1f}ms"
        elif duration_ms < MINUTE_TO_MS:
            return f"{duration_ms / 1000:.2f}s"
        elif duration_ms < HOUR_TO_MS:
            duration_s = duration_ms / 1000
            return f"{int(duration_s // 60)}m{int(duration_s % 60)}s"
        else:
            duration_s = duration_ms / 1000
            hours = int(duration_s // 3600)
            minutes = int((duration_s % 3600) // 60)
            seconds = int(duration_s % 60)
            return f"{hours}h{minutes}m{seconds}s"

    @staticmethod
    def _get_client_ip(scope: Scope) -> str:
        """Extract client IP address from ASGI scope."""

        client = scope.get("client")
        if client:
            return client[0]

        headers = dict(scope.get("headers", []))

        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode().split(",")[0].strip()

        real_ip = headers.get(b"x-real-ip")
        if real_ip:
            return real_ip.decode()

        return "unknown"

    def _log_message(self, message: str) -> None:
        print(message, file=self.output, flush=True)

    def _get_status_color(self, status_code: int) -> str:
        """Return background color for status code."""
        for status_range, color in self._STATUS_COLORS.items():
            if status_code in status_range:
                return color
        return self._DEFAULT_COLOR

    def _get_method_color(self, method: str) -> str:
        return self._METHOD_COLORS.get(method, self._DEFAULT_COLOR)

    def _build_log_message(self, scope: Scope, status_code: int, duration_ms: float) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        status_color = self._get_status_color(status_code)
        method = scope.get("method", "GET")
        method_color = self._get_method_color(method)

        client_ip = self._get_client_ip(scope)
        formatted_duration = self._format_duration(duration_ms)

        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"").decode()
        url_path = path
        if query_string:
            url_path += f"?{query_string}"

        log_message = (
            f"{timestamp} "
            f"{status_color} {status_code} {Style.RESET_ALL} | "
            f"{formatted_duration:>8} | "
            f"{client_ip:>15} | "
            f"{method_color} {method:>4} {Style.RESET_ALL} "
            f'"{url_path}"'
        )

        return log_message

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_message = f"Request failed after {self._format_duration(duration_ms)}: {str(e)}"
            self._log_message(error_message)
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        log_message = self._build_log_message(scope, status_code, duration_ms)
        self._log_message(log_message)
