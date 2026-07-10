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
    """update_ticket_last_activity(channel_id) — channel-scoped timestamp update."""

    @pytest.mark.asyncio
    @freeze_time("2024-06-15 12:00:00", tz_offset=0)
    async def test_updates_last_activity(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Sends update with lastActivity = now()."""
        fake_client.set_table_data("ticket", [])

        await db.update_ticket_last_activity("ch-001")

        update_calls = fake_client.get_table_calls("ticket")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["lastActivity"] == "2024-06-15T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_filters_by_channel_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('channelId') filter."""
        fake_client.set_table_data("ticket", [])

        await db.update_ticket_last_activity("ch-999")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "channelId", "ch-999") in filters

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_ticket_last_activity("ch-001")
