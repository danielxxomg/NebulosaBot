"""Unit tests for infraction_db facade methods.

Covers:
    - deactivate_infraction — guild-scoped soft-delete (active=false)
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


class TestDeactivateInfraction:
    """deactivate_infraction(guild_id, infraction_id) — guild-scoped soft-delete."""

    @pytest.mark.asyncio
    async def test_sets_active_false(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Sends update with active=False."""
        fake_client.set_table_data("infraction", [])

        await db.deactivate_infraction("g1", "inf-001")

        update_calls = fake_client.get_table_calls("infraction")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1] == {"active": False}

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('guildId', guild_id) filter."""
        fake_client.set_table_data("infraction", [])

        await db.deactivate_infraction("g99", "inf-001")

        filters = fake_client.get_table_filters("infraction")
        assert ("eq", "guildId", "g99") in filters

    @pytest.mark.asyncio
    async def test_filters_by_infraction_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Applies eq('id', infraction_id) filter."""
        fake_client.set_table_data("infraction", [])

        await db.deactivate_infraction("g1", "inf-999")

        filters = fake_client.get_table_filters("infraction")
        assert ("eq", "id", "inf-999") in filters

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.deactivate_infraction("g1", "inf-001")
