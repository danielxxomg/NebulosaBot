"""Unit tests for greeting_db facade methods.

Covers:
    - upsert_greeting_config — persists and fires _on_write hook
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.database import Database
from bot.models.greeting_config import GreetingConfig
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


def _mock_greeting_config(guild_id: str = "g1") -> MagicMock:
    """Return a mock GreetingConfig with to_db_dict()."""
    config = MagicMock()
    config.guild_id = guild_id
    config.to_db_dict.return_value = {
        "guildId": guild_id,
        "welcomeMessage": "Welcome!",
        "enabled": True,
    }
    return config


class TestUpsertGreetingConfig:
    """upsert_greeting_config(guild_id, config) — upsert + _on_write hook."""

    @pytest.mark.asyncio
    async def test_persists_config(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Calls upsert with config.to_db_dict() payload."""
        config = _mock_greeting_config("g1")

        await db.upsert_greeting_config("g1", config)

        upsert_calls = fake_client.get_table_calls("greeting_config")
        assert len(upsert_calls) == 1
        assert upsert_calls[0][0] == "upsert"
        assert upsert_calls[0][1]["guildId"] == "g1"
        assert upsert_calls[0][1]["welcomeMessage"] == "Welcome!"

    @pytest.mark.asyncio
    async def test_persists_onboarding_channel(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """upsert_greeting_config() MUST include the optional channel field."""
        config = GreetingConfig(guild_id="g1", onboarding_channel_id="onboarding-1")

        await db.upsert_greeting_config("g1", config)

        upsert_calls = fake_client.get_table_calls("greeting_config")
        assert upsert_calls[0][1]["onboardingChannelId"] == "onboarding-1"

    @pytest.mark.asyncio
    async def test_clears_onboarding_channel_to_null(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """upsert_greeting_config() MUST persist clearing the channel as NULL."""
        config = GreetingConfig(guild_id="g1", onboarding_channel_id=None)

        await db.upsert_greeting_config("g1", config)

        upsert_calls = fake_client.get_table_calls("greeting_config")
        assert upsert_calls[0][1]["onboardingChannelId"] is None

    @pytest.mark.asyncio
    async def test_calls_on_write_hook(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Fires _on_write('greeting_config', guild_id) after successful upsert."""
        on_write = AsyncMock()
        db._on_write = on_write
        config = _mock_greeting_config("g42")

        await db.upsert_greeting_config("g42", config)

        on_write.assert_awaited_once_with("greeting_config", "g42")

    @pytest.mark.asyncio
    async def test_skips_on_write_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Does not raise when _on_write is None."""
        db._on_write = None
        config = _mock_greeting_config("g1")

        # Should not raise.
        await db.upsert_greeting_config("g1", config)

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """Raises RuntimeError when not connected."""
        config = _mock_greeting_config("g1")
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.upsert_greeting_config("g1", config)


class TestGetGreetingConfig:
    """get_greeting_config() returns the nullable channel field unchanged."""

    @pytest.mark.asyncio
    async def test_returns_onboarding_channel(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_greeting_config() MUST return a configured onboarding channel."""
        row = {"guildId": "g1", "onboardingChannelId": "onboarding-1"}
        fake_client.set_table_data("greeting_config", [row])

        result = await db.get_greeting_config("g1")

        assert result == row
        assert result["onboardingChannelId"] == "onboarding-1"

    @pytest.mark.asyncio
    async def test_returns_null_onboarding_channel(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_greeting_config() MUST preserve a cleared NULL channel."""
        row = {"guildId": "g1", "onboardingChannelId": None}
        fake_client.set_table_data("greeting_config", [row])

        result = await db.get_greeting_config("g1")

        assert result == row
        assert result["onboardingChannelId"] is None
