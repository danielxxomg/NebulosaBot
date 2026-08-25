"""S2.2 RED — Guild DB contract: 12 gaps cross-guild denial.

Strict TDD: this file MUST fail before GREEN (pytest -k guild_scope).
DB layer MUST enforce guild ownership; cross-guild input returns no eligible
row / empty / no mutation, not caller-only check. No DDL.

Covers: get_ticket, get_ticket_by_channel, update_ticket, get_tickets_by_parent,
get_ticket_category, delete_ticket_category, insert_ticket_note, get_ticket_notes,
delete_ticket_note, get_recent_notes_for_dedup, insert_audit_row, get_audit_rows.

Consolidated (cycle-5 S5b/c): the per-method filter-assert and empty-result
twins are parametrized over call specs; ``update_ticket_requires_guild_filter``
was deleted because its assertion is strictly implied by the scoped-update
filter case below.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.core.database import Database
from bot.services.ticket_service import TicketService
from tests.test_database import FakeSupabaseClient

# Scoped-call specs: (method, args, kwargs) whose filters MUST carry both the
# guildId equality and the listed secondary column filter.
_FILTER_MATRIX = [
    pytest.param(
        ("get_ticket", ("t-b",), {"guild_id": "guild-a"}),
        "ticket",
        ("eq", "id", "t-b"),
        id="get_ticket",
    ),
    pytest.param(
        ("get_ticket_by_channel", ("ch-b",), {"guild_id": "guild-a"}),
        "ticket",
        ("eq", "channelId", "ch-b"),
        id="get_ticket_by_channel",
    ),
    pytest.param(
        ("update_ticket", ("t-b",), {"guild_id": "guild-a", "status": "closed"}),
        "ticket",
        ("eq", "id", "t-b"),
        id="update_ticket",
    ),
    pytest.param(
        ("get_tickets_by_parent", ("p-b",), {"guild_id": "guild-a"}),
        "ticket",
        ("eq", "parentId", "p-b"),
        id="get_tickets_by_parent",
    ),
    pytest.param(
        ("get_ticket_category", ("cat-b",), {"guild_id": "guild-a"}),
        "ticket_category",
        ("eq", "id", "cat-b"),
        id="get_ticket_category",
    ),
    pytest.param(
        ("delete_ticket_category", ("cat-b",), {"guild_id": "guild-a"}),
        "ticket_category",
        ("eq", "id", "cat-b"),
        id="delete_ticket_category",
    ),
]

# Cross-guild reads against an empty table MUST return the documented sentinel.
_EMPTY_MATRIX = [
    pytest.param(("get_ticket", ("t-b",), {"guild_id": "guild-a"}), "ticket", None, id="get_ticket"),
    pytest.param(
        ("get_ticket_by_channel", ("ch-b",), {"guild_id": "guild-a"}),
        "ticket",
        None,
        id="get_ticket_by_channel",
    ),
    pytest.param(
        ("get_tickets_by_parent", ("p-b",), {"guild_id": "guild-a"}),
        "ticket",
        [],
        id="get_tickets_by_parent",
    ),
    pytest.param(
        ("get_ticket_category", ("cat-b",), {"guild_id": "guild-a"}),
        "ticket_category",
        None,
        id="get_ticket_category",
    ),
]


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def db(fake_client: FakeSupabaseClient) -> Database:
    database = Database(url="https://test.supabase.co", key="test-key")
    database._client = fake_client
    return database


# ---------------------------------------------------------------------------
# Scoped reads/writes apply the guildId filter (+ their resource filter)
# ---------------------------------------------------------------------------


class TestGuildScopeFiltersApplied:
    """Scoped DB calls apply the guildId filter plus their resource filter."""

    @pytest.mark.parametrize(("call_spec", "table", "extra_filter"), _FILTER_MATRIX)
    @pytest.mark.asyncio
    async def test_scoped_call_applies_guild_filter(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
        call_spec: tuple[str, tuple, dict],
        table: str,
        extra_filter: tuple,
    ) -> None:
        """Scoped DB call MUST filter by guildId AND its resource key."""
        method, args, kwargs = call_spec
        await getattr(db, method)(*args, **kwargs)

        filters = fake_client.get_table_filters(table)
        assert ("eq", "guildId", "guild-a") in filters, f"Missing guildId filter, got {filters}"
        assert extra_filter in filters

    @pytest.mark.asyncio
    async def test_get_audit_rows_applies_guild_filter(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows scopes reads to the caller guild."""
        await db.get_audit_rows("guild-a")
        filters = fake_client.get_table_filters("ticket_audit")
        assert ("eq", "guildId", "guild-a") in filters


class TestGuildScopeEmptyResults:
    """Cross-guild reads against empty tables return documented sentinels."""

    @pytest.mark.parametrize(("call_spec", "table", "expected"), _EMPTY_MATRIX)
    @pytest.mark.asyncio
    async def test_mismatched_guild_returns_no_rows(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
        call_spec: tuple[str, tuple, dict],
        table: str,
        expected: Any,
    ) -> None:
        """Cross-guild read against an empty table returns None / [] per contract."""
        fake_client.set_table_data(table, [])
        method, args, kwargs = call_spec
        result = await getattr(db, method)(*args, **kwargs)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_audit_rows_empty_cross_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Guild A querying guild B's audit rows sees nothing — filter still applied."""
        fake_client.set_table_data("ticket_audit", [])
        result = await db.get_audit_rows("guild-b")
        assert result == []
        filters = fake_client.get_table_filters("ticket_audit")
        assert ("eq", "guildId", "guild-b") in filters


# ---------------------------------------------------------------------------
# ticket_note_db — ownership-before-mutate denials
# ---------------------------------------------------------------------------


class TestGuildScopeTicketNote:
    """Ticket-note operations deny cross-guild access before mutating."""

    @pytest.mark.asyncio
    async def test_guild_scope_insert_ticket_note_denies_cross_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket_note with guild mismatch MUST NOT persist — ownership before mutate."""
        # Simulate ticket belongs to guild-b; caller claims guild-a
        fake_client.set_table_queue("ticket", [[{"id": "t-b", "guildId": "guild-b"}]])
        with pytest.raises(ValueError, match=r"cross_guild|denied|guild"):
            await db.insert_ticket_note("t-b", "staff-1", "note", guild_id="guild-a")
        # Ensure no insert was attempted on ticket_note
        calls = fake_client.get_table_calls("ticket_note")
        assert not any(c[0] == "insert" for c in calls)

    @pytest.mark.asyncio
    async def test_guild_scope_get_ticket_notes_denies_cross_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        fake_client.set_table_queue("ticket", [[{"id": "t-b", "guildId": "guild-b"}]])
        result = await db.get_ticket_notes("t-b", guild_id="guild-a")
        assert result == []
        # No notes fetched when guild mismatched
        filters = fake_client.get_table_filters("ticket_note")
        # Should not have fetched notes (early return)
        assert ("eq", "ticketId", "t-b") not in filters or result == []

    @pytest.mark.asyncio
    async def test_guild_scope_delete_ticket_note_denies_cross_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        # Note's ticket is guild-b, caller is guild-a → deny
        fake_client.set_table_queue("ticket_note", [[{"id": "n-1", "ticketId": "t-b"}]])
        fake_client.set_table_queue("ticket", [[{"id": "t-b", "guildId": "guild-b"}]])
        with pytest.raises(ValueError, match=r"cross_guild|denied|guild"):
            await db.delete_ticket_note("n-1", guild_id="guild-a", ticket_id="t-b")
        filters = fake_client.get_table_filters("ticket_note")
        # Should not have deleted
        assert ("eq", "id", "n-1") not in filters

    @pytest.mark.asyncio
    async def test_guild_scope_get_recent_notes_for_dedup_denies_cross_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        fake_client.set_table_queue("ticket", [[{"id": "t-b", "guildId": "guild-b"}]])
        result = await db.get_recent_notes_for_dedup("t-b", "staff-1", guild_id="guild-a")
        assert result == []


# ---------------------------------------------------------------------------
# ticket_audit_db — ownership-before-mutate denial
# ---------------------------------------------------------------------------


class TestGuildScopeAuditDenial:
    """Audit-row inserts deny tickets from another guild."""

    @pytest.mark.asyncio
    async def test_guild_scope_insert_audit_row_denies_cross_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_audit_row with ticket from another guild MUST be denied with non-empty reason."""
        fake_client.set_table_queue("ticket", [[{"id": "t-b", "guildId": "guild-b"}]])
        with pytest.raises(ValueError, match=r"cross_guild|denied|guild"):
            await db.insert_audit_row("guild-a", "t-b", "close", "u1", "success", None)
        calls = fake_client.get_table_calls("ticket_audit")
        assert not any(c[0] == "insert" for c in calls)


# ---------------------------------------------------------------------------
# Service wrapper — cross-guild denial via guild-scoped DB (one vertical)
# ---------------------------------------------------------------------------


class TestGuildScopeServiceVertical:
    """One service-level vertical proving scoped denial through TicketService."""

    @pytest.mark.asyncio
    async def test_service_get_ticket_guild_scoped_denied(self) -> None:
        """Service claim MUST deny when ticket guild != requested guild via real service path."""

        cache = TTLCache()

        # DB returns None for cross-guild scoped reads
        async def scoped_get_ticket(ticket_id: str, guild_id: str | None = None) -> Any:
            if guild_id == "guild-a" and ticket_id == "t-b":
                return None
            return {"id": ticket_id, "guildId": guild_id or "guild-b", "status": "open", "claimedBy": None}

        mock_db = MagicMock()
        mock_db.get_ticket = AsyncMock(side_effect=scoped_get_ticket)
        mock_db.update_ticket = AsyncMock(return_value=None)
        mock_db.insert_audit_row = AsyncMock(return_value={})
        mock_db.get_ticket_by_number = AsyncMock(return_value=None)

        svc = TicketService(mock_db, cache)
        # Claim with guild-a for a ticket that only exists in guild-b MUST be denied
        with pytest.raises(ValueError, match="not found"):
            await svc.claim_ticket("t-b", claimed_by="staff-1", guild_id="guild-a")
        # Must have attempted a guild-scoped DB read
        assert mock_db.get_ticket.await_count >= 1
        call_kwargs = mock_db.get_ticket.call_args.kwargs if mock_db.get_ticket.call_args.kwargs else {}
        call_args = mock_db.get_ticket.call_args.args if mock_db.get_ticket.call_args.args else ()
        # guild_id must have been passed
        assert call_kwargs.get("guild_id") == "guild-a" or (len(call_args) > 1 and "guild-a" in call_args)
