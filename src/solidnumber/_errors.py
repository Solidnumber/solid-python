"""Typed exceptions for the Solidnumber SDK.

The backend's structured error envelope (`SOLID_LEGACY_ERRORS=1` to opt out
on the CLI side) is shaped:

    {
        "error": {
            "code": "auth.invalid_token",
            "message": "Token expired or revoked",
            "details": {...},
            "request_id": "req_..."
        }
    }

We parse that into a typed exception so users can `except AuthError` instead
of pattern-matching on status codes. The SDK never swallows server errors —
every non-2xx response raises.
"""
from __future__ import annotations

from typing import Any


class SolidError(Exception):
    """Base exception for every error the SDK raises.

    Caller can `except SolidError` to catch anything the SDK might throw
    without enumerating subclasses.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id

    def __repr__(self) -> str:
        bits = [f"message={self.message!r}"]
        if self.code:
            bits.append(f"code={self.code!r}")
        if self.status_code is not None:
            bits.append(f"status_code={self.status_code}")
        if self.request_id:
            bits.append(f"request_id={self.request_id!r}")
        return f"{type(self).__name__}({', '.join(bits)})"


class AuthError(SolidError):
    """401 / 403 — bad or missing API key, expired token, insufficient scope."""


class RateLimitError(SolidError):
    """429 — exceeded rate limit. The `retry_after` field on `details` (when
    present) is the seconds the server suggests waiting."""

    @property
    def retry_after(self) -> float | None:
        v = self.details.get("retry_after")
        return float(v) if v is not None else None


class NotFoundError(SolidError):
    """404 — the requested resource doesn't exist (or the caller can't see it)."""


class ValidationError(SolidError):
    """400 / 422 — request shape rejected. `details` typically lists fields."""


class ServerError(SolidError):
    """5xx — server-side fault. Safe to retry idempotent operations."""


def raise_for_status(
    *,
    status_code: int,
    body: Any,
    request_id: str | None = None,
) -> None:
    """Inspect a response body + status and raise the right typed error.

    Tolerates non-envelope responses (e.g. a plain HTML 502 from a CDN edge
    proxy) by falling back to a generic message + code derived from status.
    """
    if 200 <= status_code < 300:
        return  # success — caller handles the body

    # Try to parse the structured envelope; fall back if it isn't there.
    code: str | None = None
    message: str = f"HTTP {status_code}"
    details: dict[str, Any] = {}

    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = str(err.get("message") or message)
            details = err.get("details") or {}
        elif "detail" in body:
            # FastAPI default shape: {"detail": "..."}
            message = str(body["detail"])
        elif "message" in body:
            message = str(body["message"])

    cls: type[SolidError]
    if status_code in (401, 403):
        cls = AuthError
    elif status_code == 404:
        cls = NotFoundError
    elif status_code in (400, 422):
        cls = ValidationError
    elif status_code == 429:
        cls = RateLimitError
    elif 500 <= status_code < 600:
        cls = ServerError
    else:
        cls = SolidError

    raise cls(
        message,
        code=code,
        status_code=status_code,
        details=details,
        request_id=request_id,
    )
