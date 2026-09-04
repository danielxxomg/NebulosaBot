"""Unit tests for ticket_db facade methods.

Covers:
    - get_stale_tickets — guild+time scoped
    - get_open_ticket_channel_ids — guild-scoped channel ID extraction
    - update_ticket_last_activity — channel-scoped timestamp update
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from bot.core.database import Database
from tests.test_database import FakeSupabaseClient


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def db(fake_client: FakeSupabaseClient) -> Database:
    database = Database(url="https://test.supabase.co", key="test-key")
    database._client = fake_client
    return database


@pytest.fixture
def disconnected_db() -> Database:
    return Database(url="https://test.supabase.co", key="test-key")


TICKET_GUARD_CALLS: tuple[tuple[str, Callable[[Database], Awaitable[object]]], ...] = (
    ("get-stale-tickets", lambda db: db.get_stale_tickets("g1")),
    ("get-open-ticket-channel-ids", lambda db: db.get_open_ticket_channel_ids("g1")),
    ("update-ticket-last-activity", lambda db: db.update_ticket_last_activity("g1", "ch-001", "2024-06-15T12:00:00+00:00")),
    ("get-active-ticket-by-channel", lambda db: db.get_active_ticket_by_channel("g1", "ch1")),
    ("transition-ticket-to-closed", lambda db: db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))),
    ("transition-ticket-to-closed-guild-scoped", lambda db: db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))),
    ("count-user-open-tickets-in-category", lambda db: db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")),
)


class TestRaisesWithoutConnectMatrix:
    """Every ticket_db facade method MUST fail closed with RuntimeError before connect()."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("guard_call", TICKET_GUARD_CALLS, ids=[g[0] for g in TICKET_GUARD_CALLS])
    async def test_raises_without_connect(self, disconnected_db: Database, guard_call) -> None:
        """MUST raise RuntimeError(match='connect') when no client is wired."""
        _name, call = guard_call
        with pytest.raises(RuntimeError, match="connect"):
            await call(disconnected_db)


class TestGetStaleTickets:
    """get_stale_tickets(guild_id, hours) — guild+time scoped."""

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_returns_stale_tickets(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns tickets matching guild + stale time window."""
        stale = [{"id": "t1", "guildId": "g1", "status": "open", "lastActivity": "2024-06-13T00:00:00+00:00"}]
        fake_client.set_table_data("ticket", stale)

        result = await db.get_stale_tickets("g1", hours=48)

        assert len(result) == 1
        assert result[0]["id"] == "t1"

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns empty list when no stale tickets match."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_stale_tickets("g1")

        assert result == []

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_stale_tickets("g42")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g42") in filters

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_filters_by_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_stale_tickets("g1")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_filters_by_last_activity_cutoff(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies lt('lastActivity', cutoff) with cutoff = now() - hours."""
        fake_client.set_table_data("ticket", [])

        await db.get_stale_tickets("g1", hours=48)

        expected_cutoff = (datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC) - timedelta(hours=48)).isoformat()
        filters = fake_client.get_table_filters("ticket")
        lt_filters = [f for f in filters if f[0] == "lt" and f[1] == "lastActivity"]
        assert len(lt_filters) == 1
        assert lt_filters[0][2] == expected_cutoff


class TestGetOpenTicketChannelIds:
    """get_open_ticket_channel_ids(guild_id) — guild-scoped channel extraction."""

    @pytest.mark.asyncio
    async def test_returns_channel_ids(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Extracts channelId from each matching row."""
        rows = [
            {"channelId": "ch-001"},
            {"channelId": "ch-002"},
            {"channelId": "ch-003"},
        ]
        fake_client.set_table_data("ticket", rows)

        result = await db.get_open_ticket_channel_ids("g1")

        assert result == ["ch-001", "ch-002", "ch-003"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns empty list when no open tickets exist."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_open_ticket_channel_ids("g1")

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_open_ticket_channel_ids("g77")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g77") in filters

    @pytest.mark.asyncio
    async def test_filters_by_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_open_ticket_channel_ids("g1")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters


class TestUpdateTicketLastActivity:
    """update_ticket_last_activity(guild_id, channel_id, timestamp) — guild+channel scoped."""

    @pytest.mark.asyncio
    async def test_updates_last_activity(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Sends update with lastActivity = provided timestamp."""
        fake_client.set_table_data("ticket", [])

        await db.update_ticket_last_activity("g1", "ch-001", "2024-06-15T12:00:00+00:00")

        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["lastActivity"] == "2024-06-15T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.update_ticket_last_activity("g99", "ch-001", "2024-06-15T12:00:00+00:00")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g99") in filters

    @pytest.mark.asyncio
    async def test_filters_by_channel_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('channelId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.update_ticket_last_activity("g1", "ch-999", "2024-06-15T12:00:00+00:00")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "channelId", "ch-999") in filters


# ===========================================================================
# get_active_ticket_by_channel — guild-scoped active lookup by (guild_id, channel_id)
# ===========================================================================


class TestGetActiveTicketByChannel:
    """get_active_ticket_by_channel(guild_id, channel_id) — guild+channel scoped, open|claimed only."""

    @pytest.mark.asyncio
    async def test_returns_open_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns the active ticket when status is 'open'."""
        row = {"id": "t1", "guildId": "g1", "channelId": "ch1", "status": "open"}
        fake_client.set_table_data("ticket", [row])

        result = await db.get_active_ticket_by_channel("g1", "ch1")

        assert result is not None
        assert result["id"] == "t1"

    @pytest.mark.asyncio
    async def test_returns_claimed_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns the active ticket when status is 'claimed'."""
        row = {"id": "t2", "guildId": "g1", "channelId": "ch1", "status": "claimed"}
        fake_client.set_table_data("ticket", [row])

        result = await db.get_active_ticket_by_channel("g1", "ch1")

        assert result is not None
        assert result["id"] == "t2"

    @pytest.mark.asyncio
    async def test_returns_none_for_closed_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when the matching ticket is closed (not active)."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_active_ticket_by_channel("g1", "ch1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns empty when no ticket matches the channel."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_active_ticket_by_channel("g1", "ch-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId') filter for guild scoping."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g42", "ch1")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g42") in filters

    @pytest.mark.asyncio
    async def test_filters_by_channel_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('channelId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g1", "ch99")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "channelId", "ch99") in filters

    @pytest.mark.asyncio
    async def test_filters_by_active_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g1", "ch1")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters


# ===========================================================================
# transition_ticket_to_closed — conditional close with expected_statuses
# ===========================================================================


class TestTransitionTicketToClosed:
    """transition_ticket_to_closed(ticket_id, expected_statuses, close_reason) — conditional close."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("ticket_id", "initial_status"),
        [
            pytest.param("t1", "open", id="closes-open-ticket"),
            pytest.param("t2", "claimed", id="closes-claimed-ticket"),
        ],
    )
    async def test_closes_active_ticket(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
        ticket_id: str,
        initial_status: str,
    ) -> None:
        """Closes an active (open or claimed) ticket and returns the closed row."""
        active_row = {"id": ticket_id, "status": initial_status, "guildId": "g1"}
        closed_row = {"id": ticket_id, "status": "closed", "guildId": "g1", "closeReason": None}
        fake_client.set_table_queue(
            "ticket",
            [
                [active_row],  # select: found active ticket
                [closed_row],  # update: returns closed row
            ],
        )

        result = await db.transition_ticket_to_closed("g1", ticket_id, expected_statuses=("open", "claimed"))

        assert result is not None
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_returns_none_for_already_closed(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when ticket is already closed (no mutation)."""
        fake_client.set_table_data("ticket", [])  # no matching row (closed not in expected_statuses)

        result = await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when ticket does not exist."""
        fake_client.set_table_data("ticket", [])

        result = await db.transition_ticket_to_closed("g1", "nonexistent", expected_statuses=("open", "claimed"))

        assert result is None

    @pytest.mark.asyncio
    async def test_persists_close_reason(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """When close_reason is provided, it MUST be persisted on the row."""
        open_row = {"id": "t1", "status": "open", "guildId": "g1"}
        closed_row = {"id": "t1", "status": "closed", "guildId": "g1", "closeReason": "zombie:channel_missing"}
        fake_client.set_table_queue(
            "ticket",
            [
                [open_row],
                [closed_row],
            ],
        )

        result = await db.transition_ticket_to_closed(
            "g1",
            "t1",
            expected_statuses=("open", "claimed"),
            close_reason="zombie:channel_missing",
        )

        assert result is not None
        # Verify the update included closeReason.
        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) >= 1
        update_data = update_calls[0][1]
        assert update_data["closeReason"] == "zombie:channel_missing"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_close_reason_when_none(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """When close_reason is None, closeReason MUST NOT be in the update dict."""
        open_row = {"id": "t1", "status": "open", "guildId": "g1"}
        closed_row = {"id": "t1", "status": "closed", "guildId": "g1", "closeReason": None}
        fake_client.set_table_queue(
            "ticket",
            [
                [open_row],
                [closed_row],
            ],
        )

        await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) >= 1
        update_data = update_calls[0][1]
        assert "closeReason" not in update_data

    @pytest.mark.asyncio
    async def test_filters_by_expected_statuses(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', expected_statuses) filter."""
        fake_client.set_table_data("ticket", [])

        await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    async def test_update_carries_status_predicate(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """R1-001: the UPDATE step MUST also apply in_('status', expected_statuses)
        so a status change between SELECT and UPDATE mutates 0 rows (atomic close)."""
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "status": "open", "guildId": "g1"}],
                [{"id": "t1", "status": "closed", "guildId": "g1"}],
            ],
        )
        await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))
        # SELECT records one in_('status') filter; the UPDATE MUST record a second.
        predicate = ("in_", "status", ["open", "claimed"])
        assert fake_client.get_table_filters("ticket").count(predicate) == 2

    @pytest.mark.asyncio
    async def test_update_zero_rows_returns_none(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """R1-001: when the status-guarded UPDATE matches 0 rows (a race flipped
        the status between SELECT and UPDATE), return None (already_closed)."""
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "status": "open", "guildId": "g1"}],
                [],  # UPDATE matched nothing
            ],
        )
        writes: list[tuple[str, str]] = []

        async def on_write(table: str, identifier: str) -> None:
            writes.append((table, identifier))

        db._on_write = on_write

        result = await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))
        assert result is None
        assert writes == []

    @pytest.mark.asyncio
    async def test_persists_transcript_url(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """R2-002: transcript_url MUST be persisted as transcriptUrl on close."""
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "status": "open", "guildId": "g1"}],
                [{"id": "t1", "status": "closed", "guildId": "g1", "transcriptUrl": "https://t/x.html"}],
            ],
        )
        await db.transition_ticket_to_closed(
            "g1",
            "t1",
            expected_statuses=("open", "claimed"),
            transcript_url="https://t/x.html",
        )
        update_calls = fake_client.get_table_calls("ticket")
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["transcriptUrl"] == "https://t/x.html"


# ===========================================================================
# transition_ticket_to_closed — guild-scoped conditional close (task 2.2 RED)
# ===========================================================================


class TestTransitionTicketToClosedGuildScoped:
    """transition_ticket_to_closed(guild_id, ticket_id, ("open","claimed")) — one-winner, guild-isolated."""

    @pytest.mark.asyncio
    async def test_closes_open_ticket_with_guild_scope(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """Guild-scoped transition MUST close an open ticket and return the closed row."""
        open_row = {"id": "t1", "guildId": "g1", "status": "open", "channelId": "ch1"}
        closed_row = {"id": "t1", "guildId": "g1", "status": "closed", "closeReason": "zombie:repair"}
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        result = await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        assert result is not None
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_guild_filter_applied_on_select_and_update(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """BOTH the SELECT and the UPDATE MUST carry eq('guildId') for strict guild isolation."""
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "guildId": "g1", "status": "open"}],
                [{"id": "t1", "guildId": "g1", "status": "closed"}],
            ],
        )
        await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        filters = fake_client.get_table_filters("ticket")
        assert filters.count(("eq", "guildId", "g1")) == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_ticket_belongs_to_other_guild(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """A ticket in guild B MUST NOT be closable from guild A (no match)."""
        fake_client.set_table_queue("ticket", [[], []])

        result = await db.transition_ticket_to_closed("gA", "t1", expected_statuses=("open", "claimed"))

        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_transition_has_one_winner(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """Two repairs for the same active ticket: one closes, the second gets no row.

        Simulated as: first SELECT finds the open row + UPDATE returns closed;
        second SELECT finds nothing (already closed in the expected statuses).
        """
        # Attempt 1: open row found and updated to closed.
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "guildId": "g1", "status": "open"}],
                [{"id": "t1", "guildId": "g1", "status": "closed"}],
            ],
        )
        first = await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))
        assert first is not None
        assert first["status"] == "closed"

        # Attempt 2: ticket is closed → SELECT matches nothing → None (no-op).
        fake_client.set_table_queue("ticket", [[]])
        second = await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))
        assert second is None

    @pytest.mark.asyncio
    async def test_preserves_close_reason_when_none_guild_scoped(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
    ) -> None:
        """With close_reason=None, closeReason MUST NOT be in the update dict."""
        fake_client.set_table_queue(
            "ticket",
            [
                [{"id": "t1", "guildId": "g1", "status": "open"}],
                [{"id": "t1", "guildId": "g1", "status": "closed"}],
            ],
        )

        await db.transition_ticket_to_closed("g1", "t1", expected_statuses=("open", "claimed"))

        update_calls = fake_client.get_table_calls("ticket")
        assert update_calls[0][0] == "update"
        assert "closeReason" not in update_calls[0][1]


# ===========================================================================
# count_user_open_tickets_in_category — per-author category count
# ===========================================================================


class TestCountUserOpenTicketsInCategory:
    """count_user_open_tickets_in_category(guild_id, author_id, category_id) — 4 filters + exclude."""

    @pytest.mark.asyncio
    async def test_returns_count(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns the count of matching open/claimed tickets."""
        rows = [{"id": "t1"}, {"id": "t2"}]
        fake_client.set_table_data("ticket", rows)

        result = await db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")

        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns 0 when no matching tickets exist."""
        fake_client.set_table_data("ticket", [])

        result = await db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")

        assert result == 0

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_user_open_tickets_in_category("g42", "userA", "cat-Support")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g42") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_filters_by_author_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('authorId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_user_open_tickets_in_category("g1", "user99", "cat-Support")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "authorId", "user99") in filters, f"Missing authorId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_filters_by_category_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('categoryId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_user_open_tickets_in_category("g1", "userA", "cat-Billing")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "categoryId", "cat-Billing") in filters, f"Missing categoryId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_filters_by_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters, f"Missing status filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_exclude_ticket_id_filters_out_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """When exclude_ticket_id is set, applies ne('id', ...) or neq filter."""
        fake_client.set_table_data("ticket", [{"id": "t1"}])

        await db.count_user_open_tickets_in_category("g1", "userA", "cat-Support", exclude_ticket_id="t-exclude")

        filters = fake_client.get_table_filters("ticket")
        neq_filters = [f for f in filters if f[0] in ("neq", "ne", "not.eq")]
        assert len(neq_filters) >= 1, f"Expected neq filter for exclude_ticket_id, got: {filters}"
        assert neq_filters[0][1] == "id"
        assert neq_filters[0][2] == "t-exclude"

    @pytest.mark.asyncio
    async def test_no_exclude_when_not_provided(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Without exclude_ticket_id, no neq filter is applied."""
        fake_client.set_table_data("ticket", [])

        await db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")

        filters = fake_client.get_table_filters("ticket")
        neq_filters = [f for f in filters if f[0] in ("neq", "ne", "not.eq")]
        assert len(neq_filters) == 0, f"Unexpected neq filter, got: {filters}"
