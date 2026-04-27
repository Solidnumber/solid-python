"""solidnumber — official Python SDK for Solid# AI business infrastructure.

Quickstart:

    from solidnumber import SolidClient

    # Reads SOLID_API_KEY from env
    client = SolidClient()

    # Public endpoint (no auth)
    print(client.health.check())

    # Authenticated endpoint
    page = client.contacts.list(limit=20, search="acme")
    for c in page["items"]:
        print(c["name"], c.get("email"))

Errors raise typed exceptions:

    from solidnumber import AuthError, RateLimitError, SolidError

    try:
        client.contacts.list()
    except AuthError as e:
        print(f"auth failed: {e.code} — get a key at solidnumber.com/dashboard")
    except RateLimitError as e:
        wait = e.retry_after or 60
        print(f"rate limited; retry after {wait}s")
    except SolidError as e:
        # Catch-all for anything else the SDK throws
        print(f"{e.code}: {e.message} (request_id={e.request_id})")

See https://solidnumber.com/docs/sdks for the full SDK reference and
https://solidnumber.com/docs/api for the underlying REST API.
"""
from ._client import SolidClient
from ._errors import (
    AuthError,
    NotFoundError,
    RateLimitError,
    ServerError,
    SolidError,
    ValidationError,
)

__all__ = [
    "SolidClient",
    "SolidError",
    "AuthError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "ServerError",
]

__version__ = "0.0.1"
