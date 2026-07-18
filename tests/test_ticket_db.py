"""Unit tests for ticket_db facade methods.

Covers:
    - get_stale_tickets — guild+time scoped
    - get_open_ticket_channel_ids — guild-scoped channel ID extraction
    - update_ticket_last_activity — channel-scoped timestamp update
"""

from __future__ import annotations

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

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_stale_tickets("g1")


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

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_open_ticket_channel_ids("g1")


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

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_ticket_last_activity("g1", "ch-001", "2024-06-15T12:00:00+00:00")


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

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.count_user_open_tickets_in_category("g1", "userA", "cat-Support")


# ===========================================================================
# get_active_ticket_by_channel — guild+channel+status scoped
# ===========================================================================


class TestGetActiveTicketByChannel:
    """get_active_ticket_by_channel(guild_id, channel_id) — active status filter."""

    @pytest.mark.asyncio
    async def test_returns_active_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns the open ticket matching guild + channel."""
        row = {"id": "t1", "guildId": "g1", "channelId": "ch-001", "status": "open"}
        fake_client.set_table_data("ticket", [row])

        result = await db.get_active_ticket_by_channel("g1", "ch-001")

        assert result is not None
        assert result["id"] == "t1"

    @pytest.mark.asyncio
    async def test_returns_claimed_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns the claimed ticket matching guild + channel."""
        row = {"id": "t2", "guildId": "g1", "channelId": "ch-001", "status": "claimed"}
        fake_client.set_table_data("ticket", [row])

        result = await db.get_active_ticket_by_channel("g1", "ch-001")

        assert result is not None
        assert result["id"] == "t2"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when no active ticket matches."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_active_ticket_by_channel("g1", "ch-999")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_closed(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when only a closed ticket matches (not active)."""
        # DB-level in_ filter means the query returns [] for closed-only.
        fake_client.set_table_data("ticket", [])

        result = await db.get_active_ticket_by_channel("g1", "ch-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g42", "ch-001")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g42") in filters

    @pytest.mark.asyncio
    async def test_filters_by_channel_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('channelId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g1", "ch-999")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "channelId", "ch-999") in filters

    @pytest.mark.asyncio
    async def test_filters_by_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_active_ticket_by_channel("g1", "ch-001")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_active_ticket_by_channel("g1", "ch-001")


# ===========================================================================
# transition_ticket_to_closed — conditional close with status predicate
# ===========================================================================


class TestTransitionTicketToClosed:
    """transition_ticket_to_closed(ticket_id, expected_statuses, close_reason, ...) — conditional close."""

    @pytest.mark.asyncio
    async def test_closes_open_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Closes an open ticket and returns the closed row."""
        open_row = {
            "id": "t1",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "open",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {
            **open_row,
            "status": "closed",
            "closedAt": "2024-06-15T12:00:00+00:00",
            "closeReason": "zombie:channel_deleted",
        }
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        result = await db.transition_ticket_to_closed(
            "t1",
            expected_statuses=("open", "claimed"),
            close_reason="zombie:channel_deleted",
        )

        assert result is not None
        assert result["status"] == "closed"
        assert result["closeReason"] == "zombie:channel_deleted"

    @pytest.mark.asyncio
    async def test_closes_claimed_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Closes a claimed ticket within expected_statuses."""
        claimed_row = {
            "id": "t2",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "claimed",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {**claimed_row, "status": "closed", "closedAt": "2024-06-15T12:00:00+00:00"}
        fake_client.set_table_queue("ticket", [[claimed_row], [closed_row]])

        result = await db.transition_ticket_to_closed(
            "t2",
            expected_statuses=("open", "claimed"),
        )

        assert result is not None
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_returns_none_when_already_closed(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when ticket is already closed (not in expected_statuses).

        The SELECT returns [] because closed is not in ('open','claimed'),
        so no UPDATE is attempted.
        """
        fake_client.set_table_data("ticket", [])

        result = await db.transition_ticket_to_closed(
            "t1",
            expected_statuses=("open", "claimed"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns None when ticket_id doesn't match any row."""
        fake_client.set_table_data("ticket", [])

        result = await db.transition_ticket_to_closed(
            "nonexistent",
            expected_statuses=("open", "claimed"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_applies_status_filter_to_select(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """The SELECT uses in_('status', expected_statuses) to guard against races."""
        fake_client.set_table_data("ticket", [])

        await db.transition_ticket_to_closed(
            "t1",
            expected_statuses=("open", "claimed"),
        )

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    async def test_applies_ticket_id_filter(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('id', ticket_id) filter."""
        fake_client.set_table_data("ticket", [])

        await db.transition_ticket_to_closed("t-abc")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "id", "t-abc") in filters

    @pytest.mark.asyncio
    async def test_records_close_reason(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Persists close_reason when provided."""
        open_row = {
            "id": "t1",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "open",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {**open_row, "status": "closed", "closeReason": "zombie:sweep"}
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        result = await db.transition_ticket_to_closed(
            "t1",
            close_reason="zombie:sweep",
        )

        assert result is not None
        # Verify the update call included closeReason.
        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert update_calls[0][1]["closeReason"] == "zombie:sweep"

    @pytest.mark.asyncio
    async def test_records_transcript_url(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Persists transcript_url when provided."""
        open_row = {
            "id": "t1",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "open",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {**open_row, "status": "closed", "transcriptUrl": "https://cdn.discord.com/t.html"}
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        result = await db.transition_ticket_to_closed(
            "t1",
            transcript_url="https://cdn.discord.com/t.html",
        )

        assert result is not None
        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert update_calls[0][1]["transcriptUrl"] == "https://cdn.discord.com/t.html"

    @pytest.mark.asyncio
    async def test_skips_close_reason_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Does NOT include closeReason in update when close_reason is None.

        close_reason=None means non-overwriting — the field stays as-is.
        """
        open_row = {
            "id": "t1",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "open",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {**open_row, "status": "closed"}
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        await db.transition_ticket_to_closed("t1")

        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert "closeReason" not in update_calls[0][1]

    @pytest.mark.asyncio
    async def test_skips_transcript_url_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Does NOT include transcriptUrl in update when transcript_url is None."""
        open_row = {
            "id": "t1",
            "guildId": "g1",
            "channelId": "ch-001",
            "status": "open",
            "closeReason": None,
            "transcriptUrl": None,
        }
        closed_row = {**open_row, "status": "closed"}
        fake_client.set_table_queue("ticket", [[open_row], [closed_row]])

        await db.transition_ticket_to_closed("t1")

        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert "transcriptUrl" not in update_calls[0][1]

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.transition_ticket_to_closed("t1")
