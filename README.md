# solidnumber — Official Python SDK for Solid#

[![PyPI](https://img.shields.io/badge/pypi-coming%20soon-yellow)](https://pypi.org/project/solidnumber/)
[![License: BUSL-1.1](https://img.shields.io/badge/license-BUSL--1.1-blue.svg)](LICENSE)

Run an AI-powered business from Python. CRM, payments, voice AI, 116 agents,
1,615 REST endpoints — typed Python interface, the same auth and error envelope
as the Node CLI.

> **Status: 0.0.1 (alpha).** Hand-written core (auth, error envelope, request
> plumbing) verified by 17 tests. Resource coverage is intentionally narrow
> (`health`, `contacts.list`) — the full surface lands in v0.1 once the
> codegen pass over `openapi.json` is in. See [Roadmap](#roadmap).

## Install

```bash
pip install solidnumber  # PyPI publish coming with v0.1
```

For local dev today:

```bash
git clone https://github.com/Solidnumber/solid-python
cd solid-python
pip install -e ".[dev]"
pytest
```

## Quickstart

```python
from solidnumber import SolidClient

# Reads SOLID_API_KEY from env if you don't pass it.
# Get a key from https://app.solidnumber.com/dashboard/settings/advanced
# (or run `solid auth token create` from the CLI).
client = SolidClient()

# Public endpoint, no auth required:
print(client.health.check())
# → {"status": "healthy", ...}

# Authenticated endpoint:
page = client.contacts.list(limit=20, search="acme")
for c in page["items"]:
    print(c["name"], c.get("email"))
```

## Auth

Three precedence levels (highest first):

1. `api_key=` constructor kwarg — `SolidClient(api_key="sk_solid_...")`
2. `SOLID_API_KEY` env var — set in your shell, `.env`, CI secrets, etc.
3. No auth — for public endpoints only (e.g. `/api/v1/health`)

The SDK emits an `Authorization: Bearer <key>` header when a key is present;
if you call an authenticated endpoint without one you'll get an `AuthError`.

You can also override the API base URL via the `SOLID_API_URL` env var or
the `base_url=` kwarg — useful for hitting a sandbox or your own self-hosted
instance.

## Errors

Every non-2xx response raises a typed exception. Catch by category:

```python
from solidnumber import (
    SolidClient,
    SolidError,
    AuthError,
    RateLimitError,
    NotFoundError,
    ValidationError,
    ServerError,
)

client = SolidClient()

try:
    contact = client.contacts.list(limit=20)
except AuthError as e:
    # 401 / 403 — bad key, expired token, missing scope
    print(f"auth failed: {e.code} (request_id={e.request_id})")
except RateLimitError as e:
    # 429 — server suggests waiting `retry_after` seconds
    wait = e.retry_after or 60
    print(f"rate limited; retry in {wait}s")
except NotFoundError:
    # 404
    print("contact not found")
except ValidationError as e:
    # 400 / 422 — request shape rejected; e.details usually lists fields
    print(f"validation failed: {e.details}")
except ServerError:
    # 5xx — safe to retry idempotent operations
    print("server error; retry")
except SolidError as e:
    # Catch-all for anything else (network, timeout, unknown status)
    print(f"{e.code}: {e.message}")
```

The error envelope mirrors the same shape the
[`@solidnumber/cli`](https://www.npmjs.com/package/@solidnumber/cli) Node SDK
emits with `--json`, so a Python service and a Node service handling the same
backend errors look the same in code.

## Resource coverage (v0.0.1)

| Resource | Method | Endpoint | Status |
|---|---|---|---|
| `client.health` | `.check()` | `GET /api/v1/health` | ✅ |
| `client.contacts` | `.list(limit=, offset=, search=)` | `GET /api/v1/crm/contacts` | ✅ |
| All 1,613 other endpoints | — | — | 🚧 [Roadmap](#roadmap) |

For unmapped endpoints today, you can use the low-level request methods:

```python
client.get("/api/v1/orders", params={"limit": 10})
client.post("/api/v1/crm/contacts", json={"name": "Acme"})
client.put("/api/v1/crm/contacts/42", json={"email": "new@a.com"})
client.patch("/api/v1/crm/contacts/42", json={"name": "Acme Co"})
client.delete("/api/v1/crm/contacts/42")
```

Same auth, same error envelope, same return shape — these compose with
generated resources later without breaking.

## Roadmap

- **v0.1** — full resource coverage generated from `openapi.json` via
  `openapi-python-client`, hand-polished on top of the v0.0.1 core. Async
  client (`AsyncSolidClient`). Pagination iterators
  (`for c in client.contacts.iter_all(): ...`). Webhook signature verify.
  Idempotency-Key header support. Rate-limit auto-backoff.
- **v1.0** — PyPI publish, semver-stable surface, type stubs verified
  end-to-end against `openapi.json` in CI.

## Related projects

- [`@solidnumber/cli`](https://www.npmjs.com/package/@solidnumber/cli) — Node CLI
  + TS SDK. Same backend, same auth, same error envelope.
- [`@solidnumber/mcp`](https://www.npmjs.com/package/@solidnumber/mcp) — MCP
  server for Claude Code, Cursor, Windsurf. 608 tools.
- [REST API reference](https://solidnumber.com/docs/api) — full endpoint
  catalog.

## License

[BUSL-1.1](LICENSE). Same license as the Node CLI.
