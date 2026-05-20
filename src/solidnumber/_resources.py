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


class VoiceResource(_Resource):
    """Outbound voice + SMS dispatch through ADA's verb registry.

    Routes through the same `services.ada_tool_dispatcher` boundary the
    /dashboard/ada UI uses, so consent gates, role gates, audit logs,
    and idempotency are identical. The CLI's `--confirm` flag here is
    expressed as `confirm=True` on every method — passing `False`
    raises a 400 server-side rather than silently dispatching.

    See Owners-Manual/42-UVX-User-Voice-Experience/13-ADA-OUTBOUND-DISPATCH.md.
    """

    def outbound_call(
        self,
        *,
        contact_id: int,
        intent: str,
        agent_type: str = "customer_service",
        confirm: bool = False,
    ) -> dict[str, Any]:
        """POST /api/v1/ada/cli-dispatch — dispatch an outbound voice call.

        Args:
            contact_id: CRM contact ID owned by the authenticated company.
            intent: One-sentence reason for the call (briefs the agent).
            agent_type: Which trained agent should make the call.
            confirm: REQUIRED. Pass `True` to actually place the call.
                If `False`, the server returns a 400.
        """
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "voice.outbound_call",
                "args": {
                    "contact_id": contact_id,
                    "intent": intent,
                    "agent_type": agent_type,
                },
                "confirm": bool(confirm),
            },
        )

    def send_sms(
        self,
        *,
        contact_id: int,
        message: str,
        intent: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """POST /api/v1/ada/cli-dispatch — send an outbound SMS.

        STOP language is auto-appended for TCPA if not already in the
        message. Consent + opt-out + DNC checks live in the backend
        verb impl — see solid-backend/services/ada_verbs.py::sms_send.
        """
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "sms.send",
                "args": {
                    "contact_id": contact_id,
                    "message": message,
                    "intent": intent,
                },
                "confirm": bool(confirm),
            },
        )
