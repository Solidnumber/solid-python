"""Tests for the SolidClient core — auth, request, error envelope.

We use httpx.MockTransport rather than respx so the test surface stays
thin (one fewer dev dep, one fewer mock framework to learn). The transport
fixture covers: auth header propagation, env-var fallback, success path,
all the typed error subclasses, and request-id surfacing.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from solidnumber import (
    AuthError,
    NotFoundError,
    RateLimitError,
    ServerError,
    SolidClient,
    SolidError,
    ValidationError,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_transport(handler: Any) -> httpx.MockTransport:
    """Wrap a request handler in a MockTransport so we can build a client
    against a fake backend without touching the network."""
    return httpx.MockTransport(handler)


def _client_with(handler: Any, **kwargs: Any) -> SolidClient:
    return SolidClient(_transport=_make_transport(handler), **kwargs)


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make sure no real SOLID_API_KEY in the dev shell leaks into tests."""
    monkeypatch.delenv("SOLID_API_KEY", raising=False)
    monkeypatch.delenv("SOLID_API_URL", raising=False)
    yield


# ── Auth wiring ──────────────────────────────────────────────────────────


def test_api_key_kwarg_sets_authorization_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"status": "OK"})

    client = _client_with(handler, api_key="sk_solid_TEST")
    client.get("/api/v1/health")
    assert captured["auth"] == "Bearer sk_solid_TEST"


def test_env_var_provides_api_key_when_kwarg_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOLID_API_KEY", "sk_solid_FROM_ENV")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"status": "OK"})

    client = _client_with(handler)
    client.get("/api/v1/health")
    assert captured["auth"] == "Bearer sk_solid_FROM_ENV"


def test_no_api_key_omits_authorization_header() -> None:
    """Public endpoints work without auth. The header should be absent
    rather than `Bearer None` or `Bearer `."""
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "OK"})

    client = _client_with(handler)  # no key
    client.get("/api/v1/health")
    assert captured["auth"] is None


def test_kwarg_takes_precedence_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOLID_API_KEY", "sk_solid_FROM_ENV")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"status": "OK"})

    client = _client_with(handler, api_key="sk_solid_KWARG_WINS")
    client.get("/api/v1/health")
    assert captured["auth"] == "Bearer sk_solid_KWARG_WINS"


def test_user_agent_includes_sdk_version() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json={"status": "OK"})

    client = _client_with(handler, api_key="x")
    client.get("/api/v1/health")
    assert "solidnumber-python/" in captured["ua"]


# ── Success path ─────────────────────────────────────────────────────────


def test_get_returns_decoded_json_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [1, 2, 3], "total": 3})

    client = _client_with(handler, api_key="x")
    body = client.get("/api/v1/crm/contacts")
    assert body == {"items": [1, 2, 3], "total": 3}


def test_post_sends_json_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 42})

    client = _client_with(handler, api_key="x")
    body = client.post("/api/v1/crm/contacts", json={"name": "Acme", "email": "a@b.com"})
    assert captured["body"] == {"name": "Acme", "email": "a@b.com"}
    assert body == {"id": 42}


def test_resource_methods_compose_correctly() -> None:
    """ContactsResource.list builds the right URL + params."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"items": [], "total": 0})

    client = _client_with(handler, api_key="x")
    client.contacts.list(limit=20, offset=0, search="acme")
    assert "/api/v1/crm/contacts" in captured["url"]
    assert "limit=20" in captured["url"]
    assert "offset=0" in captured["url"]
    assert "search=acme" in captured["url"]


# ── Error envelope ──────────────────────────────────────────────────────


def test_401_raises_auth_error_with_envelope_fields() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "auth.invalid_token", "message": "Token expired"}},
            headers={"X-Request-Id": "req_abc"},
        )

    client = _client_with(handler, api_key="bad")
    with pytest.raises(AuthError) as excinfo:
        client.contacts.list()
    err = excinfo.value
    assert err.status_code == 401
    assert err.code == "auth.invalid_token"
    assert err.message == "Token expired"
    assert err.request_id == "req_abc"


def test_403_raises_auth_error_too() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "auth.scope_denied", "message": "no"}})

    with pytest.raises(AuthError):
        _client_with(handler, api_key="x").contacts.list()


def test_404_raises_not_found_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Contact 999 not found"})

    with pytest.raises(NotFoundError) as excinfo:
        _client_with(handler, api_key="x").get("/api/v1/crm/contacts/999")
    assert excinfo.value.message == "Contact 999 not found"


def test_422_raises_validation_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"code": "validation", "message": "email required", "details": {"field": "email"}}},
        )

    with pytest.raises(ValidationError) as excinfo:
        _client_with(handler, api_key="x").post("/api/v1/crm/contacts", json={})
    assert excinfo.value.details == {"field": "email"}


def test_429_raises_rate_limit_with_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "rate_limit.exceeded",
                    "message": "slow down",
                    "details": {"retry_after": 30},
                }
            },
        )

    with pytest.raises(RateLimitError) as excinfo:
        _client_with(handler, api_key="x").contacts.list()
    assert excinfo.value.retry_after == 30.0


def test_500_raises_server_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>502 Bad Gateway</html>")

    with pytest.raises(ServerError) as excinfo:
        _client_with(handler, api_key="x").get("/api/v1/health")
    assert excinfo.value.status_code == 500


def test_unknown_4xx_falls_back_to_solid_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"error": {"code": "teapot", "message": "I'm a teapot"}})

    with pytest.raises(SolidError) as excinfo:
        _client_with(handler, api_key="x").get("/anywhere")
    # Not one of the typed subclasses
    assert type(excinfo.value) is SolidError
    assert excinfo.value.status_code == 418


# ── Network-layer errors ─────────────────────────────────────────────────


def test_network_error_raises_solid_error_with_network_code() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(SolidError) as excinfo:
        _client_with(handler, api_key="x").get("/api/v1/health")
    assert excinfo.value.code == "network.error"


# ── Sanity ───────────────────────────────────────────────────────────────


def test_context_manager_closes_underlying_http_client() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "OK"})

    with _client_with(handler, api_key="x") as client:
        client.get("/api/v1/health")
    # If close() was called, a follow-up request should fail because the
    # transport is shut.
    with pytest.raises(RuntimeError):
        client.get("/api/v1/health")
