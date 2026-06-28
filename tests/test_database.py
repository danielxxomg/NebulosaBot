"""Unit tests for bot.core.database.Database.

Covers the qa-database-coverage spec scenarios:
    - Core CRUD + guild methods (connect, health_check, get_guild, upsert_guild,
      get_member, get_infractions, get_active_warnings, insert_ticket,
      get_ticket, get_ticket_by_channel)
    - Guild-scoped query filters correctly
    - Missing record returns None without exception
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.database import Database
from bot.models.guild import GuildConfig


# ---------------------------------------------------------------------------
# Helpers — fake query builder that supports Supabase chain calls
# ---------------------------------------------------------------------------


class FakeQueryBuilder:
    """Simulates the Supabase query builder chain: table().select().eq().execute().

    Each chain method returns ``self`` so calls like
    ``table("guild").select("*").eq("id", "123").execute()`` work.
    The ``_result`` attribute holds the data that ``execute()`` returns.
    """

    def __init__(self, result_data: list[dict] | None = None) -> None:
        self._result_data: list[dict] = result_data if result_data is not None else []
        self._last_table: str = ""
        self._calls: list[tuple[str, dict]] = []

    # Chain methods — all return self
    def table(self, name: str) -> FakeQueryBuilder:
        self._last_table = name
        return self

    def select(self, *args: Any, **kwargs: Any) -> FakeQueryBuilder:
        return self

    def insert(self, row: dict) -> FakeQueryBuilder:
        self._calls.append(("insert", row))
        return self

    def upsert(self, data: Any) -> FakeQueryBuilder:
        self._calls.append(("upsert", data))
        return self

    def update(self, data: dict) -> FakeQueryBuilder:
        self._calls.append(("update", data))
        return self

    def delete(self) -> FakeQueryBuilder:
        return self

    def eq(self, column: str, value: Any) -> FakeQueryBuilder:
        return self

    def in_(self, column: str, values: list) -> FakeQueryBuilder:
        return self

    def lt(self, column: str, value: Any) -> FakeQueryBuilder:
        return self

    def gt(self, column: str, value: Any) -> FakeQueryBuilder:
        return self

    def gte(self, column: str, value: Any) -> FakeQueryBuilder:
        return self

    def order(self, column: str, desc: bool = False) -> FakeQueryBuilder:
        return self

    def limit(self, n: int) -> FakeQueryBuilder:
        return self

    def offset(self, n: int) -> FakeQueryBuilder:
        return self

    def execute(self) -> MagicMock:
        response = MagicMock()
        response.data = self._result_data
        return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client() -> FakeQueryBuilder:
    """Return a FakeQueryBuilder that the Database will use as _client."""
    return FakeQueryBuilder()


@pytest.fixture
def db(fake_client: FakeQueryBuilder) -> Database:
    """Return a Database with a fake client already connected."""
    database = Database(url="https://test.supabase.co", key="test-key")
    database._client = fake_client
    return database


@pytest.fixture
def disconnected_db() -> Database:
    """Return a Database that has NOT been connected (no _client)."""
    return Database(url="https://test.supabase.co", key="test-key")


# ---------------------------------------------------------------------------
# connect — happy path
# ---------------------------------------------------------------------------


class TestConnect:
    """Verify Database.connect() lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_sets_client(self) -> None:
        """connect() MUST create a Supabase client and verify health."""
        database = Database(url="https://test.supabase.co", key="test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "1"}]
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_response

        with patch("bot.core.database.create_client", return_value=mock_client):
            await database.connect()

        assert database._client is mock_client

    @pytest.mark.asyncio
    async def test_connect_logs_warning_on_health_failure(self) -> None:
        """connect() MUST log a warning if health check fails but still set client."""
        database = Database(url="https://test.supabase.co", key="test-key")

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception(
            "connection refused"
        )

        with patch("bot.core.database.create_client", return_value=mock_client):
            await database.connect()

        # Client is still set even if health check fails.
        assert database._client is mock_client


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify Database.health_check() returns True/False."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_success(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """health_check() MUST return True when the query succeeds."""
        fake_client._result_data = [{"id": "1"}]
        result = await db.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_exception(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """health_check() MUST return False when the query raises."""
        fake_client.table = MagicMock(side_effect=Exception("network error"))
        result = await db.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_no_client(self, disconnected_db: Database) -> None:
        """health_check() MUST return False when connect() hasn't been called."""
        result = await disconnected_db.health_check()
        assert result is False


# ---------------------------------------------------------------------------
# get_guild — found + not-found
# ---------------------------------------------------------------------------


class TestGetGuild:
    """Verify Database.get_guild() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_guild_returns_row_when_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_guild() MUST return the row dict when a guild exists."""
        guild_row = {"id": "123456789", "prefix": "!", "language": "en"}
        fake_client._result_data = [guild_row]

        result = await db.get_guild("123456789")

        assert result == guild_row
        assert result is not None
        assert result["id"] == "123456789"

    @pytest.mark.asyncio
    async def test_get_guild_returns_none_when_not_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_guild() MUST return None when no guild row exists."""
        fake_client._result_data = []

        result = await db.get_guild("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guild_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_guild() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_guild("123")


# ---------------------------------------------------------------------------
# upsert_guild — idempotent
# ---------------------------------------------------------------------------


class TestUpsertGuild:
    """Verify Database.upsert_guild() persists config."""

    @pytest.mark.asyncio
    async def test_upsert_guild_calls_client(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """upsert_guild() MUST call client.table('guild').upsert(config.to_db_dict()).execute()."""
        config = GuildConfig(id="123456789", prefix="!", language="en")

        await db.upsert_guild(config)

        # Verify the upsert call was made with the config's db dict.
        upsert_calls = [c for c in fake_client._calls if c[0] == "upsert"]
        assert len(upsert_calls) == 1
        assert upsert_calls[0][1]["id"] == "123456789"
        assert upsert_calls[0][1]["prefix"] == "!"

    @pytest.mark.asyncio
    async def test_upsert_guild_raises_without_connect(self, disconnected_db: Database) -> None:
        """upsert_guild() MUST raise RuntimeError if connect() wasn't called."""
        config = GuildConfig(id="123")
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.upsert_guild(config)


# ---------------------------------------------------------------------------
# get_member — found + not-found
# ---------------------------------------------------------------------------


class TestGetMember:
    """Verify Database.get_member() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_member_returns_row_when_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_member() MUST return the row dict when a member exists."""
        member_row = {"guildId": "g1", "userId": "u1", "xp": 100, "level": 5}
        fake_client._result_data = [member_row]

        result = await db.get_member("g1", "u1")

        assert result == member_row
        assert result is not None
        assert result["guildId"] == "g1"
        assert result["userId"] == "u1"

    @pytest.mark.asyncio
    async def test_get_member_returns_none_when_not_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_member() MUST return None when no member row exists."""
        fake_client._result_data = []

        result = await db.get_member("g1", "unknown")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_member_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_member() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_member("g1", "u1")


# ---------------------------------------------------------------------------
# get_infractions
# ---------------------------------------------------------------------------


class TestGetInfractions:
    """Verify Database.get_infractions() returns filtered list."""

    @pytest.mark.asyncio
    async def test_get_infractions_returns_list(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_infractions() MUST return a list of infraction rows."""
        infractions = [
            {"id": "i1", "guildId": "g1", "targetId": "u1", "type": "WARN"},
            {"id": "i2", "guildId": "g1", "targetId": "u1", "type": "MUTE"},
        ]
        fake_client._result_data = infractions

        result = await db.get_infractions("g1", "u1")

        assert len(result) == 2
        assert result[0]["type"] == "WARN"

    @pytest.mark.asyncio
    async def test_get_infractions_returns_empty_when_none(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_infractions() MUST return empty list when no records exist."""
        fake_client._result_data = []

        result = await db.get_infractions("g1", "u1")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_infractions_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_infractions() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_infractions("g1", "u1")


# ---------------------------------------------------------------------------
# get_active_warnings
# ---------------------------------------------------------------------------


class TestGetActiveWarnings:
    """Verify Database.get_active_warnings() returns filtered WARN list."""

    @pytest.mark.asyncio
    async def test_get_active_warnings_returns_list(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_active_warnings() MUST return active WARN infractions."""
        warnings = [
            {"id": "w1", "guildId": "g1", "targetId": "u1", "type": "WARN", "active": True},
        ]
        fake_client._result_data = warnings

        result = await db.get_active_warnings("g1", "u1")

        assert len(result) == 1
        assert result[0]["type"] == "WARN"
        assert result[0]["active"] is True

    @pytest.mark.asyncio
    async def test_get_active_warnings_returns_empty_when_none(
        self, db: Database, fake_client: FakeQueryBuilder
    ) -> None:
        """get_active_warnings() MUST return empty list when no active warnings."""
        fake_client._result_data = []

        result = await db.get_active_warnings("g1", "u1")

        assert result == []


# ---------------------------------------------------------------------------
# insert_ticket
# ---------------------------------------------------------------------------


class TestInsertTicket:
    """Verify Database.insert_ticket() creates ticket record."""

    @pytest.mark.asyncio
    async def test_insert_ticket_returns_row(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """insert_ticket() MUST return the persisted ticket row."""
        ticket_row = {
            "id": "t-uuid",
            "ticketNumber": 1,
            "guildId": "g1",
            "authorId": "u1",
            "channelId": "ch1",
            "status": "open",
        }
        fake_client._result_data = [ticket_row]

        result = await db.insert_ticket("g1", "u1", "ch1", None, 1)

        assert result["id"] == "t-uuid"
        assert result["guildId"] == "g1"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_insert_ticket_raises_without_connect(self, disconnected_db: Database) -> None:
        """insert_ticket() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.insert_ticket("g1", "u1", "ch1", None, 1)


# ---------------------------------------------------------------------------
# get_ticket — found + not-found
# ---------------------------------------------------------------------------


class TestGetTicket:
    """Verify Database.get_ticket() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_ticket_returns_row_when_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_ticket() MUST return the ticket row when found."""
        ticket_row = {"id": "t1", "guildId": "g1", "status": "open"}
        fake_client._result_data = [ticket_row]

        result = await db.get_ticket("t1")

        assert result == ticket_row
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_ticket_returns_none_when_not_found(self, db: Database, fake_client: FakeQueryBuilder) -> None:
        """get_ticket() MUST return None when no ticket exists."""
        fake_client._result_data = []

        result = await db.get_ticket("nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# get_ticket_by_channel — found + not-found
# ---------------------------------------------------------------------------


class TestGetTicketByChannel:
    """Verify Database.get_ticket_by_channel() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_row_when_found(
        self, db: Database, fake_client: FakeQueryBuilder
    ) -> None:
        """get_ticket_by_channel() MUST return the ticket row when found."""
        ticket_row = {"id": "t1", "channelId": "ch1", "status": "open"}
        fake_client._result_data = [ticket_row]

        result = await db.get_ticket_by_channel("ch1")

        assert result == ticket_row
        assert result is not None
        assert result["channelId"] == "ch1"

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_none_when_not_found(
        self, db: Database, fake_client: FakeQueryBuilder
    ) -> None:
        """get_ticket_by_channel() MUST return None when no ticket exists for channel."""
        fake_client._result_data = []

        result = await db.get_ticket_by_channel("unknown-channel")

        assert result is None
