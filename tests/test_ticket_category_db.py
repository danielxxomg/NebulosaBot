"""Unit tests for ticket_category_db facade methods.

Covers:
    - count_open_tickets_by_category — guild-scoped, count="exact"
    - update_ticket_category_field_definitions — guild+id scoped JSONB update
"""

from __future__ import annotations

import pytest

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


class TestCountOpenTicketsByCategory:
    """count_open_tickets_by_category(guild_id, category_id) — guild-scoped count."""

    @pytest.mark.asyncio
    async def test_returns_exact_count(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns count from response when tickets exist."""
        fake_client.set_table_data("ticket", [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}])

        result = await db.count_open_tickets_by_category("g1", "cat-1")

        assert result == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Returns 0 when no open tickets match."""
        fake_client.set_table_data("ticket", [])

        result = await db.count_open_tickets_by_category("g1", "cat-1")

        assert result == 0

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId', guild_id) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_open_tickets_by_category("g99", "cat-1")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g99") in filters

    @pytest.mark.asyncio
    async def test_filters_by_category_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('categoryId', category_id) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_open_tickets_by_category("g1", "cat-99")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "categoryId", "cat-99") in filters

    @pytest.mark.asyncio
    async def test_filters_by_status_open_claimed(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies in_('status', ['open', 'claimed']) filter."""
        fake_client.set_table_data("ticket", [])

        await db.count_open_tickets_by_category("g1", "cat-1")

        filters = fake_client.get_table_filters("ticket")
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    async def test_uses_count_exact(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """select() must pass count='exact' to avoid fetching rows."""
        fake_client.set_table_data("ticket", [{"id": "t1"}])

        # FakeQueryBuilder records count in select kwargs — verify via count attribute
        await db.count_open_tickets_by_category("g1", "cat-1")

        builder = fake_client._tables["ticket"]
        assert builder._count == "exact"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.count_open_tickets_by_category("g1", "cat-1")


class TestUpdateTicketCategoryFieldDefinitions:
    """update_ticket_category_field_definitions(guild_id, category_id, field_defs) — guild+id scoped."""

    @pytest.mark.asyncio
    async def test_updates_field_definitions(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Sends update with fieldDefinitions payload."""
        defs = [{"key": "nick", "label": "Nickname", "style": "short", "required": True}]
        fake_client.set_table_data("ticket_category", [])

        await db.update_ticket_category_field_definitions("g1", "cat-1", defs)

        update_calls = fake_client.get_table_calls("ticket_category")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["fieldDefinitions"] == defs

    @pytest.mark.asyncio
    async def test_filters_by_id_and_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('id') AND eq('guildId') filters."""
        fake_client.set_table_data("ticket_category", [])

        await db.update_ticket_category_field_definitions("g1", "cat-1", [])

        filters = fake_client.get_table_filters("ticket_category")
        assert ("eq", "id", "cat-1") in filters
        assert ("eq", "guildId", "g1") in filters

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_ticket_category_field_definitions("g1", "cat-1", [])
