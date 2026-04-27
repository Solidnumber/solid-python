"""Resource namespaces — `client.health.check()`, `client.contacts.list()`.

Two resources for v0.0.1:
  - HealthResource    : public, no auth required, proves the request path
  - ContactsResource  : authenticated, paginated list, proves the auth +
                        params plumbing

Future codegen pass will hang every other resource (orders, agents, kb,
etc.) off this same shape so user-facing API stays uniform.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._client import SolidClient


class _Resource:
    """Base — every resource gets a back-reference to the SolidClient so it
    can issue HTTP. Keeps state out of the resources themselves."""

    def __init__(self, client: SolidClient) -> None:
        self._client = client


class HealthResource(_Resource):
    """`/api/v1/health` — public liveness probe. Useful for connectivity tests."""

    def check(self) -> dict[str, Any]:
        """GET /api/v1/health — returns `{"status": "OK", ...}` when live."""
        return self._client.get("/api/v1/health")


class ContactsResource(_Resource):
    """`/api/v1/crm/contacts` — CRM contacts. List returns a paginated envelope."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/crm/contacts.

        Returns the API's standard paginated envelope:
            {"items": [...], "total": N, "limit": L, "offset": O}
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        return self._client.get("/api/v1/crm/contacts", params=params)
