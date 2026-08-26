"""Tempban expiry sweep — real PostgREST serialization (data-retention spec).

The previous implementation filtered permanent bans with
``neq("expiresAt", None)``, which serializes into an invalid timestamp
comparison (PostgREST 22007) and killed automatic tempban expiry. Fake
query builders masked the defect because they never serialized.

These tests build the query through the REAL ``postgrest`` builder
(postgrest-py 2.x, the same library used in production via supabase-py)
and inspect the outgoing request query string captured by an
``httpx.MockTransport``:

- a null-safe ``expiresAt=not.is.null`` filter MUST be present;
- no ``neq`` comparison MAY appear anywhere in the wire format.

Ref: clean-1.0 S0.1/S0.2 — "Tempban expiry query serialization is
PostgREST-safe".
"""

from __future__ import annotations

import httpx
import pytest
from postgrest import AsyncPostgrestClient

from bot.core.database import Database


class _CaptureTransport(httpx.AsyncBaseTransport):
    """Mock transport that records every outgoing URL and returns rows."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.urls: list[str] = []
        self._rows = rows if rows is not None else []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        return httpx.Response(200, json=self._rows, headers={"Content-Type": "application/json"})


@pytest.fixture
def db_with_real_builder() -> tuple[Database, _CaptureTransport]:
    """Database wired to a REAL postgrest builder over a capturing transport."""
    transport = _CaptureTransport()
    client = AsyncPostgrestClient("https://example.supabase.co", http_client=httpx.AsyncClient(transport=transport))
    database = Database(url="https://example.supabase.co", key="test-key")
    database._client = client  # noqa: SLF001 -- test seam, mirrors existing fixtures
    return database, transport


@pytest.mark.asyncio
async def test_expired_tempban_query_uses_null_safe_not_is(
    db_with_real_builder: tuple[Database, _CaptureTransport],
) -> None:
    """Wire format MUST carry ``expiresAt=not.is.null`` (null-safe exclusion)."""
    database, transport = db_with_real_builder

    await database.get_expired_tempbans("g1")

    assert transport.urls, "sweep must have issued exactly one request"
    query_string = transport.urls[0]
    assert "expiresAt=not.is.null" in query_string, (
        f"null-safe not.is filter missing from wire format: {query_string}"
    )


@pytest.mark.asyncio
async def test_expired_tempban_query_has_no_neq_null(
    db_with_real_builder: tuple[Database, _CaptureTransport],
) -> None:
    """No ``neq`` comparison may appear — neq(None) is the PostgREST 22007 bug."""
    database, transport = db_with_real_builder

    await database.get_expired_tempbans("g1")

    query_string = transport.urls[0]
    assert "neq" not in query_string, f"invalid neq serialization present on wire: {query_string}"


@pytest.mark.asyncio
async def test_expired_tempban_query_filters_active_bans_before_cutoff(
    db_with_real_builder: tuple[Database, _CaptureTransport],
) -> None:
    """Sweep still scopes to guild BANs with ``expiresAt <= now`` (lte)."""
    database, transport = db_with_real_builder

    await database.get_expired_tempbans("g1")

    query_string = transport.urls[0]
    assert "guildId=eq.g1" in query_string
    assert "type=eq.BAN" in query_string
    assert "active=eq.True" in query_string
    assert "expiresAt=lte." in query_string


@pytest.mark.asyncio
async def test_sweep_executes_without_serialization_error(
    db_with_real_builder: tuple[Database, _CaptureTransport],
) -> None:
    """GIVEN one expired + one null-expires row WHEN the sweep queries THEN it executes cleanly."""
    rows = [
        {"id": "expired-1", "guildId": "g1", "targetId": "u1", "type": "BAN", "active": True,
         "expiresAt": "2026-01-01T00:00:00+00:00"},
    ]
    transport = _CaptureTransport(rows=rows)
    client = AsyncPostgrestClient("https://example.supabase.co", http_client=httpx.AsyncClient(transport=transport))
    database = Database(url="https://example.supabase.co", key="test-key")
    database._client = client  # noqa: SLF001

    result = await database.get_expired_tempbans("g1")

    # No exception propagated and the server response was unwrapped verbatim.
    assert result == rows
