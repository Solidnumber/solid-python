"""SolidClient — sync HTTP client for the Solid# REST API.

Design choices for v0.0.1:
  - Sync only. Async client is on the roadmap; httpx supports both so the
    later layer is mechanical.
  - Hand-written, not generated. The 1,615-endpoint codegen pass comes
    later — for the v1 we want the auth + error envelope code paths to be
    audited by hand.
  - Error envelope mirroring the CLI's v2.0 shape so a Python user gets
    the same typed-exception experience as a JS/TS user importing
    `@solidnumber/cli/sdk`.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ._errors import SolidError, raise_for_status


DEFAULT_BASE_URL = "https://api.solidnumber.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT_PREFIX = "solidnumber-python/0.0.1"


class SolidClient:
    """Entry point to the Solid# REST API.

    Auth precedence (highest first):
      1. `api_key` constructor kwarg
      2. `SOLID_API_KEY` env var

    If neither is set the client constructs without auth; calls to
    authenticated endpoints will then raise AuthError on the first request.
    Public endpoints (e.g. /health) work without auth.

    Example:
        from solidnumber import SolidClient

        # Reads SOLID_API_KEY from env
        client = SolidClient()

        contacts = client.contacts.list(limit=20)
        for c in contacts["items"]:
            print(c["name"], c["email"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str | None = None,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("SOLID_API_KEY")
        self._base_url = (base_url or os.environ.get("SOLID_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        ua = USER_AGENT_PREFIX
        if user_agent:
            ua = f"{ua} {user_agent}"

        headers: dict[str, str] = {"User-Agent": ua}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # `_transport` lets tests inject httpx.MockTransport without
        # polluting the public API.
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
            transport=_transport,
        )

        # Resource namespaces. Imported lazily here to avoid circular import.
        from ._resources import ContactsResource, HealthResource

        self.health = HealthResource(self)
        self.contacts = ContactsResource(self)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SolidClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    # ── Low-level request ───────────────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Issue one request, parse the response, raise on non-2xx.

        Returns the decoded JSON body on success. Raises a `SolidError`
        subclass (`AuthError`, `RateLimitError`, etc.) on any non-2xx
        status — never returns a status code to the caller.
        """
        try:
            response = self._http.request(
                method,
                path,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.TimeoutException as e:
            raise SolidError(
                f"timeout after {DEFAULT_TIMEOUT}s contacting {self._base_url}{path}",
                code="network.timeout",
            ) from e
        except httpx.HTTPError as e:
            raise SolidError(
                f"network error contacting {self._base_url}{path}: {e}",
                code="network.error",
            ) from e

        request_id = response.headers.get("X-Request-Id")
        body: Any = None
        if response.content:
            try:
                body = response.json()
            except ValueError:
                # Non-JSON body — surface the raw text up to a reasonable cap
                # so 502 HTML from a CDN edge isn't dumped wholesale.
                body = {"detail": response.text[:500]}

        raise_for_status(status_code=response.status_code, body=body, request_id=request_id)
        return body

    # Convenience wrappers — keep the resource code readable.

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json: Any | None = None) -> Any:
        return self.request("POST", path, json=json)

    def put(self, path: str, *, json: Any | None = None) -> Any:
        return self.request("PUT", path, json=json)

    def patch(self, path: str, *, json: Any | None = None) -> Any:
        return self.request("PATCH", path, json=json)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
