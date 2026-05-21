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
                "verb": "voice_outbound_call",
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
                "verb": "sms_send",
                "args": {
                    "contact_id": contact_id,
                    "message": message,
                    "intent": intent,
                },
                "confirm": bool(confirm),
            },
        )


# ---------------------------------------------------------------------------
# Convenience: every resource below is a thin wrapper around the same
# /api/v1/ada/cli-dispatch endpoint with a different verb name. The
# generic `client.dispatch(verb=..., args=..., confirm=True)` works too,
# but per-domain resources read cleaner in user code.
# ---------------------------------------------------------------------------


class KbResource(_Resource):
    """Knowledge base writes (kb_articles). Reads use ADA chat or the search verb."""

    def create(
        self,
        *,
        title: str,
        content: str,
        category_id: int,
        excerpt: str | None = None,
        status: str = "draft",
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "kb_entry_create",
                "args": {
                    "title": title,
                    "content": content,
                    "category_id": category_id,
                    "excerpt": excerpt,
                    "status": status,
                },
                "confirm": bool(confirm),
            },
        )

    def update(
        self,
        article_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        excerpt: str | None = None,
        status: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"article_id": article_id}
        if title is not None:    args["title"] = title
        if content is not None:  args["content"] = content
        if excerpt is not None:  args["excerpt"] = excerpt
        if status is not None:   args["status"] = status
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={"verb": "kb_entry_update", "args": args, "confirm": bool(confirm)},
        )


class CalendarResource(_Resource):
    """Google Calendar event create. Other appointment ops live on AppointmentsResource."""

    def create_event(
        self,
        *,
        title: str,
        start_time: str,
        end_time: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        with_meet_link: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "google_calendar_event_create",
                "args": {
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description,
                    "location": location,
                    "attendees": attendees,
                    "with_meet_link": with_meet_link,
                },
                "confirm": bool(confirm),
            },
        )


class GmailResource(_Resource):
    """Send mail from the user's connected Gmail account. For branded
    transactional mail use EmailResource (SendGrid/Mailgun/Postmark)."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "google_gmail_send",
                "args": {"to": to, "subject": subject, "body": body, "cc": cc},
                "confirm": bool(confirm),
            },
        )


class EmailResource(_Resource):
    """Transactional email through the company's email provider."""

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        body_type: str = "text",
        sender_name: str | None = None,
        reply_to: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "email_send",
                "args": {
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "body_type": body_type,
                    "sender_name": sender_name,
                    "reply_to": reply_to,
                },
                "confirm": bool(confirm),
            },
        )


class DealsResource(_Resource):
    """Sales deals — search / create / update / advance / mark won."""

    def create(
        self,
        *,
        title: str,
        contact_id: int,
        amount_cents: int | None = None,
        stage: str = "new",
        notes: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "deals_create",
                "args": {
                    "title": title, "contact_id": contact_id,
                    "amount_cents": amount_cents, "stage": stage, "notes": notes,
                },
                "confirm": bool(confirm),
            },
        )

    def advance(self, deal_id: int, to_stage: str, *, confirm: bool = False) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "deals_advance",
                "args": {"deal_id": deal_id, "to_stage": to_stage},
                "confirm": bool(confirm),
            },
        )

    def won(self, deal_id: int, *, amount_cents: int | None = None, confirm: bool = False) -> dict[str, Any]:
        args: dict[str, Any] = {"deal_id": deal_id}
        if amount_cents is not None:
            args["amount_cents"] = amount_cents
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={"verb": "deals_won", "args": args, "confirm": bool(confirm)},
        )


class LeadsResource(_Resource):
    """Lead form submissions. `promote` turns one into a CRM Contact."""

    def promote(self, lead_id: int, *, confirm: bool = False) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "crm_lead_promote",
                "args": {"lead_id": lead_id},
                "confirm": bool(confirm),
            },
        )


class AppointmentsResource(_Resource):
    """Internal company calendar (not Google). Book / reschedule / cancel."""

    def book(
        self,
        *,
        title: str,
        start_time: str,
        end_time: str,
        customer_id: int | None = None,
        staff_id: int | None = None,
        location: str | None = None,
        description: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "appointment_book",
                "args": {
                    "title": title, "start_time": start_time, "end_time": end_time,
                    "customer_id": customer_id, "staff_id": staff_id,
                    "location": location, "description": description,
                },
                "confirm": bool(confirm),
            },
        )

    def reschedule(self, appointment_id: int, *, new_start_time: str, new_end_time: str, reason: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "appointment_reschedule",
                "args": {
                    "appointment_id": appointment_id,
                    "new_start_time": new_start_time,
                    "new_end_time": new_end_time,
                    "reason": reason,
                },
                "confirm": bool(confirm),
            },
        )

    def cancel(self, appointment_id: int, *, reason: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return self._client.post(
            "/api/v1/ada/cli-dispatch",
            json={
                "verb": "appointment_cancel",
                "args": {"appointment_id": appointment_id, "reason": reason},
                "confirm": bool(confirm),
            },
        )
