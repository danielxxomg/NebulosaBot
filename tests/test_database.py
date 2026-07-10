"""Unit tests for bot.core.database.Database.

Covers the qa-database-coverage spec scenarios:
    - Core CRUD + guild methods (connect, health_check, get_guild, upsert_guild,
      get_member, get_infractions, get_active_warnings, insert_ticket,
      get_ticket, get_ticket_by_channel)
    - Economy + leaderboard methods (update_member_xp, update_member_coins,
      update_member_daily, get_economy_config, upsert_economy_config,
      get_leaderboard, get_member_rank, get_greeting_config)
    - Guild-scoped query filters correctly
    - Missing record returns None without exception
    - Upsert is idempotent
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from bot.core.database import Database
from bot.models.guild import GuildConfig

# ---------------------------------------------------------------------------
# Helpers — fake query builder that supports Supabase chain calls
# ---------------------------------------------------------------------------


class FakeQueryBuilder:
    """Simulates the Supabase query builder chain: table().select().eq().execute().

    Each chain method returns ``self`` so calls like
    ``table("guild").select("*").eq("id", "123").execute()`` work.

    Supports two modes:
    - Simple mode: ``_result_data`` is returned on every ``execute()``
    - Queue mode: ``_result_queue`` pops results in order for multi-query methods
    """

    def __init__(self, result_data: list[dict] | None = None) -> None:
        self._result_data: list[dict] = result_data if result_data is not None else []
        self._result_queue: list[list[dict]] = []
        self._calls: list[tuple[str, Any]] = []
        self._filters: list[tuple[str, str, Any]] = []  # (method, column, value)
        self._orders: list[tuple[str, bool]] = []  # (column, desc)
        self._limits: list[int] = []
        self._execute_count: int = 0
        self._count: int | None = None  # for count="exact" support

    # Chain methods — all return self
    def table(self, name: str) -> FakeQueryBuilder:
        return self

    def select(self, *args: Any, **kwargs: Any) -> FakeQueryBuilder:
        # Capture count="exact" kwarg
        if "count" in kwargs:
            self._count = kwargs["count"]
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
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQueryBuilder:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list) -> FakeQueryBuilder:
        self._filters.append(("in_", column, values))
        return self

    def lt(self, column: str, value: Any) -> FakeQueryBuilder:
        self._filters.append(("lt", column, value))
        return self

    def gt(self, column: str, value: Any) -> FakeQueryBuilder:
        self._filters.append(("gt", column, value))
        return self

    def gte(self, column: str, value: Any) -> FakeQueryBuilder:
        self._filters.append(("gte", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQueryBuilder:
        self._orders.append((column, desc))
        return self

    def limit(self, n: int) -> FakeQueryBuilder:
        self._limits.append(n)
        return self

    def offset(self, n: int) -> FakeQueryBuilder:
        return self

    async def execute(self) -> MagicMock:
        self._execute_count += 1
        data = self._result_queue.pop(0) if self._result_queue else self._result_data

        response = MagicMock()
        response.data = data
        # Set count attribute when count="exact" was used
        if self._count == "exact":
            response.count = len(data)
        return response


class FakeSupabaseClient:
    """Fake Supabase client that returns per-table FakeQueryBuilders.

    Usage:
        client = FakeSupabaseClient()
        client.set_table_data("member", [member_row])
        client.set_table_queue("member", [
            [member_row],   # get_member returns row
            [],             # update returns empty
        ])
    """

    def __init__(self) -> None:
        self._tables: dict[str, FakeQueryBuilder] = defaultdict(FakeQueryBuilder)
        self._rpc_calls: list[tuple[str, dict]] = []
        self._rpc_result: Any = None
        self._rpc_queue: list[Any] = []

    def table(self, name: str) -> FakeQueryBuilder:
        return self._tables[name]

    def rpc(self, fn_name: str, params: dict | None = None) -> FakeQueryBuilder:
        """Record an RPC call and return a FakeQueryBuilder with the result."""
        self._rpc_calls.append((fn_name, params or {}))
        builder = FakeQueryBuilder()
        if self._rpc_queue:
            result_data = self._rpc_queue.pop(0)
        else:
            result_data = self._rpc_result if self._rpc_result is not None else []
        builder._result_data = result_data
        return builder

    def set_rpc_result(self, data: list[dict]) -> None:
        """Set static result data for RPC calls."""
        self._rpc_result = data

    def set_rpc_queue(self, queue: list[list[dict]]) -> None:
        """Set ordered result queue for RPC calls."""
        self._rpc_queue = list(queue)

    def set_table_data(self, name: str, data: list[dict]) -> None:
        """Set static result data for a table."""
        self._tables[name]._result_data = data

    def set_table_queue(self, name: str, queue: list[list[dict]]) -> None:
        """Set ordered result queue for a table (pops on each execute)."""
        self._tables[name]._result_queue = list(queue)

    def get_table_calls(self, name: str) -> list[tuple[str, Any]]:
        """Return recorded calls for a table."""
        return self._tables[name]._calls

    def get_table_filters(self, name: str) -> list[tuple[str, str, Any]]:
        """Return recorded filter calls (eq, in_, lt, gt, gte) for a table."""
        return self._tables[name]._filters

    def get_table_orders(self, name: str) -> list[tuple[str, bool]]:
        """Return recorded order calls (column, desc) for a table."""
        return self._tables[name]._orders

    def get_table_limits(self, name: str) -> list[int]:
        """Return recorded limit() values for a table."""
        return self._tables[name]._limits


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    """Return a FakeSupabaseClient that the Database will use as _client."""
    return FakeSupabaseClient()


@pytest.fixture
def db(fake_client: FakeSupabaseClient) -> Database:
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
        """connect() MUST create an async Supabase client and verify health."""
        database = Database(url="https://test.supabase.co", key="test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "1"}]

        async def mock_execute() -> MagicMock:
            return mock_response

        mock_client.table.return_value.select.return_value.limit.return_value.execute = mock_execute

        with patch("bot.core.db.base.acreate_client", return_value=mock_client) as mock_create:
            # acreate_client is async — return the mock directly (it's awaited)
            mock_create.return_value = mock_client
            await database.connect()

        assert database._client is mock_client

    @pytest.mark.asyncio
    async def test_connect_logs_warning_on_health_failure(self) -> None:
        """connect() MUST log a warning if health check fails but still set client."""
        database = Database(url="https://test.supabase.co", key="test-key")

        mock_client = MagicMock()

        async def mock_execute_fail() -> MagicMock:
            raise Exception("connection refused")

        mock_client.table.return_value.select.return_value.limit.return_value.execute = mock_execute_fail

        with patch("bot.core.db.base.acreate_client", return_value=mock_client):
            await database.connect()

        # Client is still set even if health check fails.
        assert database._client is mock_client


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify Database.health_check() returns True/False."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_success(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """health_check() MUST return True when the query succeeds."""
        fake_client.set_table_data("guild", [{"id": "1"}])
        result = await db.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_exception(self, db: Database) -> None:
        """health_check() MUST return False when the query raises."""
        db._client = MagicMock()
        db._client.table.side_effect = Exception("network error")
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
    async def test_get_guild_returns_row_when_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_guild() MUST return the row dict when a guild exists."""
        guild_row = {"id": "123456789", "prefix": "!", "language": "en"}
        fake_client.set_table_data("guild", [guild_row])

        result = await db.get_guild("123456789")

        assert result == guild_row
        assert result is not None
        assert result["id"] == "123456789"

    @pytest.mark.asyncio
    async def test_get_guild_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_guild() MUST return None when no guild row exists."""
        fake_client.set_table_data("guild", [])

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
    async def test_upsert_guild_calls_client(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """upsert_guild() MUST call client.table('guild').upsert(config.to_db_dict()).execute()."""
        config = GuildConfig(id="123456789", prefix="!", language="en")

        await db.upsert_guild(config)

        upsert_calls = fake_client.get_table_calls("guild")
        assert len(upsert_calls) == 1
        assert upsert_calls[0][0] == "upsert"
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
    async def test_get_member_returns_row_when_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_member() MUST return the row dict when a member exists."""
        member_row = {"guildId": "g1", "userId": "u1", "xp": 100, "level": 5}
        fake_client.set_table_data("member", [member_row])

        result = await db.get_member("g1", "u1")

        assert result == member_row
        assert result is not None
        assert result["guildId"] == "g1"
        assert result["userId"] == "u1"

    @pytest.mark.asyncio
    async def test_get_member_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_member() MUST return None when no member row exists."""
        fake_client.set_table_data("member", [])

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
    async def test_get_infractions_returns_list(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_infractions() MUST return a list of infraction rows."""
        infractions = [
            {"id": "i1", "guildId": "g1", "targetId": "u1", "type": "WARN"},
            {"id": "i2", "guildId": "g1", "targetId": "u1", "type": "MUTE"},
        ]
        fake_client.set_table_data("infraction", infractions)

        result = await db.get_infractions("g1", "u1")

        assert len(result) == 2
        assert result[0]["type"] == "WARN"

    @pytest.mark.asyncio
    async def test_get_infractions_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_infractions() MUST return empty list when no records exist."""
        fake_client.set_table_data("infraction", [])

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
    async def test_get_active_warnings_returns_list(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_active_warnings() MUST return active WARN infractions."""
        warnings = [
            {"id": "w1", "guildId": "g1", "targetId": "u1", "type": "WARN", "active": True},
        ]
        fake_client.set_table_data("infraction", warnings)

        result = await db.get_active_warnings("g1", "u1")

        assert len(result) == 1
        assert result[0]["type"] == "WARN"
        assert result[0]["active"] is True

    @pytest.mark.asyncio
    async def test_get_active_warnings_returns_empty_when_none(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_active_warnings() MUST return empty list when no active warnings."""
        fake_client.set_table_data("infraction", [])

        result = await db.get_active_warnings("g1", "u1")

        assert result == []


# ---------------------------------------------------------------------------
# insert_ticket
# ---------------------------------------------------------------------------


class TestInsertTicket:
    """Verify Database.insert_ticket() creates ticket record."""

    @pytest.mark.asyncio
    async def test_insert_ticket_returns_row(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """insert_ticket() MUST return the persisted ticket row."""
        ticket_row = {
            "id": "t-uuid",
            "ticketNumber": 1,
            "guildId": "g1",
            "authorId": "u1",
            "channelId": "ch1",
            "status": "open",
        }
        fake_client.set_table_data("ticket", [ticket_row])

        result = await db.insert_ticket("g1", "u1", "ch1", None, 1)

        assert result["id"] == "t-uuid"
        assert result["guildId"] == "g1"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_insert_ticket_with_parent_id_stores_parent(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket(parent_id=...) MUST include 'parentId' in the inserted row."""
        fake_client.set_table_data("ticket", [{"id": "t-child", "parentId": "p-uuid"}])

        await db.insert_ticket("g1", "u1", "ch1", None, 1, parent_id="p-uuid")

        insert_calls = fake_client.get_table_calls("ticket")
        assert len(insert_calls) == 1
        assert insert_calls[0][0] == "insert"
        inserted_row = insert_calls[0][1]
        assert inserted_row["parentId"] == "p-uuid"

    @pytest.mark.asyncio
    async def test_insert_ticket_without_parent_id_defaults_none(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket() without parent_id MUST insert parentId=None (backward compat)."""
        fake_client.set_table_data("ticket", [{"id": "t-plain", "parentId": None}])

        await db.insert_ticket("g1", "u1", "ch1", None, 1)

        insert_calls = fake_client.get_table_calls("ticket")
        inserted_row = insert_calls[0][1]
        assert inserted_row["parentId"] is None

    @pytest.mark.asyncio
    async def test_insert_ticket_raises_without_connect(self, disconnected_db: Database) -> None:
        """insert_ticket() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.insert_ticket("g1", "u1", "ch1", None, 1)


# ---------------------------------------------------------------------------
# get_tickets_by_parent — children of a parent ticket
# ---------------------------------------------------------------------------


class TestGetTicketsByParent:
    """Verify Database.get_tickets_by_parent() returns a parent's children."""

    @pytest.mark.asyncio
    async def test_returns_children_of_parent(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST return rows filtered by parentId."""
        children = [
            {"id": "c1", "parentId": "p1", "status": "open"},
            {"id": "c2", "parentId": "p1", "status": "open"},
        ]
        fake_client.set_table_data("ticket", children)

        result = await db.get_tickets_by_parent("p1")

        assert result == children
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_parent_id_column(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST apply an eq('parentId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_tickets_by_parent("p1")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "parentId", "p1") in filters, f"Missing parentId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_children(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST return [] when the parent has no children."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_tickets_by_parent("orphan-parent")

        assert result == []

    @pytest.mark.asyncio
    async def test_orders_newest_first(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST order by createdAt DESC (newest-first)."""
        fake_client.set_table_data("ticket", [])

        await db.get_tickets_by_parent("p-0001")

        orders = fake_client.get_table_orders("ticket")
        assert ("createdAt", True) in orders, f"Expected order('createdAt', desc=True), got: {orders}"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_tickets_by_parent() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_tickets_by_parent("p1")


# ---------------------------------------------------------------------------
# get_ticket — found + not-found
# ---------------------------------------------------------------------------


class TestGetTicket:
    """Verify Database.get_ticket() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_ticket_returns_row_when_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket() MUST return the ticket row when found."""
        ticket_row = {"id": "t1", "guildId": "g1", "status": "open"}
        fake_client.set_table_data("ticket", [ticket_row])

        result = await db.get_ticket("t1")

        assert result == ticket_row
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_ticket_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket() MUST return None when no ticket exists."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_ticket("nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# get_ticket_by_channel — found + not-found
# ---------------------------------------------------------------------------


class TestGetTicketByChannel:
    """Verify Database.get_ticket_by_channel() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_row_when_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_ticket_by_channel() MUST return the ticket row when found."""
        ticket_row = {"id": "t1", "channelId": "ch1", "status": "open"}
        fake_client.set_table_data("ticket", [ticket_row])

        result = await db.get_ticket_by_channel("ch1")

        assert result == ticket_row
        assert result is not None
        assert result["channelId"] == "ch1"

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_none_when_not_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_ticket_by_channel() MUST return None when no ticket exists for channel."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_ticket_by_channel("unknown-channel")

        assert result is None


# ---------------------------------------------------------------------------
# update_member_xp — existing member + new member
# ---------------------------------------------------------------------------


class TestUpdateMemberXp:
    """Verify Database.update_member_xp() increments XP via RPC."""

    @pytest.mark.asyncio
    async def test_update_member_xp_increments_existing(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_xp() MUST call rpc and return the new XP."""
        fake_client.set_rpc_result([{"xp": 150, "level": 5}])

        result = await db.update_member_xp("g1", "u1", 50)

        assert result["xp"] == 150
        assert result["level"] == 5

    @pytest.mark.asyncio
    async def test_update_member_xp_creates_new_member(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_xp() MUST call rpc which handles upsert on new member."""
        fake_client.set_rpc_result([{"xp": 25, "level": 0}])

        result = await db.update_member_xp("g1", "u1", 25)

        assert result["xp"] == 25
        assert result["level"] == 0

    @pytest.mark.asyncio
    async def test_update_member_xp_with_level_override(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_xp() MUST set level when new_level is provided."""
        fake_client.set_rpc_result([{"xp": 600, "level": 5}])

        result = await db.update_member_xp("g1", "u1", 100, new_level=6)

        assert result["xp"] == 600
        assert result["level"] == 6

    @pytest.mark.asyncio
    async def test_update_member_xp_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_member_xp() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_member_xp("g1", "u1", 10)


# ---------------------------------------------------------------------------
# update_member_coins — existing member + new member
# ---------------------------------------------------------------------------


class TestUpdateMemberCoins:
    """Verify Database.update_member_coins() increments coins via RPC."""

    @pytest.mark.asyncio
    async def test_update_member_coins_increments_existing(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_coins() MUST call rpc and return the new coins."""
        fake_client.set_rpc_result([{"coins": 250}])

        result = await db.update_member_coins("g1", "u1", 50)

        assert result["coins"] == 250

    @pytest.mark.asyncio
    async def test_update_member_coins_creates_new_member(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_coins() MUST call rpc which handles upsert on new member."""
        fake_client.set_rpc_result([{"coins": 100}])

        result = await db.update_member_coins("g1", "u1", 100)

        assert result["coins"] == 100

    @pytest.mark.asyncio
    async def test_update_member_coins_clamps_to_zero(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_coins() MUST clamp coins to 0 via SQL GREATEST."""
        fake_client.set_rpc_result([{"coins": 0}])

        result = await db.update_member_coins("g1", "u1", -50)

        assert result["coins"] == 0


# ---------------------------------------------------------------------------
# update_member_daily — streak + timestamps
# ---------------------------------------------------------------------------


class TestUpdateMemberDaily:
    """Verify Database.update_member_daily() updates streak and timestamps via RPC."""

    @pytest.mark.asyncio
    async def test_update_member_daily_updates_existing(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_daily() MUST call rpc('set_member_daily') and return result."""
        fake_client.set_rpc_result([{"coins": 150, "dailyStreak": 3, "lastDailyReset": "2024-06-15T00:00:00Z", "lastDaily": "2024-06-15T12:00:00Z"}])

        result = await db.update_member_daily("g1", "u1", 100, 3, "2024-06-15T00:00:00Z", "2024-06-15T12:00:00Z")

        assert result["coins"] == 150
        assert result["dailyStreak"] == 3

    @pytest.mark.asyncio
    async def test_update_member_daily_creates_new_member(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_daily() MUST call rpc which handles upsert on new member."""
        fake_client.set_rpc_result([{"coins": 50, "dailyStreak": 1, "lastDailyReset": "2024-06-15T00:00:00Z", "lastDaily": "2024-06-15T12:00:00Z"}])

        result = await db.update_member_daily("g1", "u1", 50, 1, "2024-06-15T00:00:00Z", "2024-06-15T12:00:00Z")

        assert result["coins"] == 50
        assert result["dailyStreak"] == 1


# ---------------------------------------------------------------------------
# get_economy_config — found + not-found
# ---------------------------------------------------------------------------


class TestGetEconomyConfig:
    """Verify Database.get_economy_config() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_economy_config_returns_row_when_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_economy_config() MUST return the row when config exists."""
        config_row = {"guildId": "g1", "xpPerMessage": 15, "coinsPerMessage": 5}
        fake_client.set_table_data("economy_config", [config_row])

        result = await db.get_economy_config("g1")

        assert result == config_row
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_economy_config_returns_none_when_not_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_economy_config() MUST return None when no config exists."""
        fake_client.set_table_data("economy_config", [])

        result = await db.get_economy_config("g1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_economy_config_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_economy_config() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_economy_config("g1")


# ---------------------------------------------------------------------------
# upsert_economy_config — idempotent
# ---------------------------------------------------------------------------


class TestUpsertEconomyConfig:
    """Verify Database.upsert_economy_config() persists config."""

    @pytest.mark.asyncio
    async def test_upsert_economy_config_calls_client(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """upsert_economy_config() MUST call client.table('economy_config').upsert()."""
        mock_config = MagicMock()
        mock_config.guild_id = "g1"
        mock_config.to_db_dict.return_value = {
            "guildId": "g1",
            "xpPerMessage": 15,
            "coinsPerMessage": 5,
        }

        await db.upsert_economy_config(mock_config)

        upsert_calls = fake_client.get_table_calls("economy_config")
        assert len(upsert_calls) == 1
        assert upsert_calls[0][0] == "upsert"
        assert upsert_calls[0][1]["guildId"] == "g1"

    @pytest.mark.asyncio
    async def test_upsert_economy_config_idempotent(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Upserting the same config twice MUST not create duplicates."""
        mock_config = MagicMock()
        mock_config.guild_id = "g1"
        mock_config.to_db_dict.return_value = {
            "guildId": "g1",
            "xpPerMessage": 15,
            "coinsPerMessage": 5,
        }

        await db.upsert_economy_config(mock_config)
        await db.upsert_economy_config(mock_config)

        upsert_calls = fake_client.get_table_calls("economy_config")
        # Both calls go through — Supabase upsert handles dedup server-side.
        assert len(upsert_calls) == 2
        # Both calls have the same data (idempotent).
        assert upsert_calls[0][1] == upsert_calls[1][1]


# ---------------------------------------------------------------------------
# get_leaderboard — ordered list
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    """Verify Database.get_leaderboard() returns ordered list."""

    @pytest.mark.asyncio
    async def test_get_leaderboard_returns_ordered_list(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_leaderboard() MUST return members sorted by sort_by descending."""
        leaderboard = [
            {"guildId": "g1", "userId": "u1", "xp": 500, "level": 10, "coins": 200},
            {"guildId": "g1", "userId": "u2", "xp": 300, "level": 7, "coins": 150},
        ]
        fake_client.set_table_data("member", leaderboard)

        result = await db.get_leaderboard("g1", sort_by="xp", limit=10)

        assert len(result) == 2
        assert result[0]["xp"] == 500
        assert result[1]["xp"] == 300

    @pytest.mark.asyncio
    async def test_get_leaderboard_returns_empty_when_no_members(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_leaderboard() MUST return empty list when no members exist."""
        fake_client.set_table_data("member", [])

        result = await db.get_leaderboard("g1")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_leaderboard_respects_limit(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_leaderboard() MUST respect the limit parameter."""
        leaderboard = [
            {"guildId": "g1", "userId": "u1", "xp": 500, "level": 10, "coins": 200},
        ]
        fake_client.set_table_data("member", leaderboard)

        result = await db.get_leaderboard("g1", limit=1)

        assert len(result) <= 1

    @pytest.mark.asyncio
    async def test_get_leaderboard_sort_by_coins(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_leaderboard() MUST sort by coins when sort_by='coins'."""
        leaderboard = [
            {"guildId": "g1", "userId": "u1", "xp": 100, "level": 3, "coins": 500},
        ]
        fake_client.set_table_data("member", leaderboard)

        result = await db.get_leaderboard("g1", sort_by="coins")

        assert len(result) == 1
        assert result[0]["coins"] == 500


# ---------------------------------------------------------------------------
# get_member_rank — rank position
# ---------------------------------------------------------------------------


class TestGetMemberRank:
    """Verify Database.get_member_rank() returns correct rank position."""

    @pytest.mark.asyncio
    async def test_get_member_rank_returns_rank(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_member_rank() MUST return 1-indexed rank based on count of higher values."""
        member_row = {"guildId": "g1", "userId": "u1", "xp": 300}
        # Queue: get_member returns member, then count query returns 2 members with higher XP
        count_response = MagicMock()
        count_response.data = []
        count_response.count = 2

        fake_client.set_table_queue(
            "member",
            [
                [member_row],  # get_member
                [],  # count query (data empty, count set on response)
            ],
        )
        # Override the second execute to have count attribute
        member_builder = fake_client._tables["member"]

        call_count = 0

        async def patched_execute() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.data = [member_row]
                return resp
            else:
                resp = MagicMock()
                resp.data = []
                resp.count = 2
                return resp

        member_builder.execute = patched_execute  # type: ignore[method-assign]

        result = await db.get_member_rank("g1", "u1")

        assert result == 3  # 2 members with higher XP → rank 3

    @pytest.mark.asyncio
    async def test_get_member_rank_returns_none_when_no_member(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_member_rank() MUST return None when member has no row."""
        fake_client.set_table_data("member", [])

        result = await db.get_member_rank("g1", "unknown")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_member_rank_returns_zero_for_zero_xp(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_member_rank() MUST return 0 when member's XP/coins is 0."""
        member_row = {"guildId": "g1", "userId": "u1", "xp": 0}
        fake_client.set_table_data("member", [member_row])

        result = await db.get_member_rank("g1", "u1")

        assert result == 0


# ---------------------------------------------------------------------------
# get_greeting_config — found + not-found
# ---------------------------------------------------------------------------


class TestGetGreetingConfig:
    """Verify Database.get_greeting_config() found and not-found paths."""

    @pytest.mark.asyncio
    async def test_get_greeting_config_returns_row_when_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_greeting_config() MUST return the row when config exists."""
        greeting_row = {"guildId": "g1", "welcomeMessage": "Hello!", "enabled": True}
        fake_client.set_table_data("greeting_config", [greeting_row])

        result = await db.get_greeting_config("g1")

        assert result == greeting_row
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_greeting_config_returns_none_when_not_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_greeting_config() MUST return None when no config exists."""
        fake_client.set_table_data("greeting_config", [])

        result = await db.get_greeting_config("g1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_greeting_config_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_greeting_config() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_greeting_config("g1")


# ---------------------------------------------------------------------------
# Guild-scoped filter assertions — prove guild_id is passed to Supabase
# ---------------------------------------------------------------------------


class TestGuildScopedFilters:
    """Scenario: guild-scoped query filters correctly.

    Per qa-database-coverage/spec.md, queries that scope by guild_id MUST
    pass an eq('guildId', ...) filter to the Supabase query builder.
    These tests assert on captured filter calls to prove the filter is applied.
    """

    @pytest.mark.asyncio
    async def test_get_guild_filters_by_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_guild() MUST filter by 'id' (guild primary key)."""
        fake_client.set_table_data("guild", [{"id": "g1"}])
        await db.get_guild("g1")

        filters = fake_client.get_table_filters("guild")
        assert ("eq", "id", "g1") in filters

    @pytest.mark.asyncio
    async def test_get_member_filters_by_guild_and_user(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_member() MUST filter by both guildId and userId."""
        fake_client.set_table_data("member", [{"guildId": "g1", "userId": "u1"}])
        await db.get_member("g1", "u1")

        filters = fake_client.get_table_filters("member")
        assert ("eq", "guildId", "g1") in filters, f"Missing guildId filter, got: {filters}"
        assert ("eq", "userId", "u1") in filters

    @pytest.mark.asyncio
    async def test_get_infractions_filters_by_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_infractions() MUST filter by guildId."""
        fake_client.set_table_data("infraction", [])
        await db.get_infractions("g99", "u1")

        filters = fake_client.get_table_filters("infraction")
        assert ("eq", "guildId", "g99") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_get_active_warnings_filters_by_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_active_warnings() MUST filter by guildId."""
        fake_client.set_table_data("infraction", [])
        await db.get_active_warnings("g42", "u1")

        filters = fake_client.get_table_filters("infraction")
        assert ("eq", "guildId", "g42") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_get_leaderboard_filters_by_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_leaderboard() MUST filter by guildId."""
        fake_client.set_table_data("member", [])
        await db.get_leaderboard("g77")

        filters = fake_client.get_table_filters("member")
        assert ("eq", "guildId", "g77") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_get_economy_config_filters_by_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_economy_config() MUST filter by guildId."""
        fake_client.set_table_data("economy_config", [])
        await db.get_economy_config("g55")

        filters = fake_client.get_table_filters("economy_config")
        assert ("eq", "guildId", "g55") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_get_greeting_config_filters_by_guild(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_greeting_config() MUST filter by guildId."""
        fake_client.set_table_data("greeting_config", [])
        await db.get_greeting_config("g33")

        filters = fake_client.get_table_filters("greeting_config")
        assert ("eq", "guildId", "g33") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_wrong_guild_id_filter_would_fail(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Test MUST fail if eq() uses wrong column name for guild scoping."""
        fake_client.set_table_data("member", [{"guildId": "g1", "userId": "u1"}])
        await db.get_member("g1", "u1")

        filters = fake_client.get_table_filters("member")
        # Prove that 'guildId' is used, not 'guild_id' or 'guildid'
        guild_filters = [f for f in filters if f[0] == "eq" and f[1] == "guildId"]
        assert len(guild_filters) >= 1, f"No guildId eq filter found in: {filters}"
        assert guild_filters[0][2] == "g1"


# ===========================================================================
# ticket_note CRUD — insert / get (newest-first, capped) / delete
# (tickets-subsidiados, Migration 003)
# ===========================================================================


def _note_row_db(**overrides: object) -> dict:
    """Return a camelCase ticket_note row as Supabase would return it."""
    row: dict = {
        "id": "n-uuid-1",
        "ticketId": "t-0001",
        "authorId": "staff-001",
        "content": "Escalated.",
        "createdAt": "2026-07-01T12:30:00+00:00",
    }
    row.update(overrides)
    return row


class TestInsertTicketNote:
    """Verify Database.insert_ticket_note() persists a staff note row."""

    @pytest.mark.asyncio
    async def test_insert_ticket_note_returns_persisted_row(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket_note() MUST return the persisted note row."""
        fake_client.set_table_data("ticket_note", [_note_row_db()])

        result = await db.insert_ticket_note("t-0001", "staff-001", "Escalated.")

        assert result["id"] == "n-uuid-1"
        assert result["ticketId"] == "t-0001"

    @pytest.mark.asyncio
    async def test_insert_ticket_note_stores_camelcase_columns(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket_note() MUST insert a row with camelCase columns + a UUID id."""
        fake_client.set_table_data("ticket_note", [_note_row_db()])

        await db.insert_ticket_note("t-0001", "staff-001", "Escalated.")

        insert_calls = fake_client.get_table_calls("ticket_note")
        assert len(insert_calls) == 1
        assert insert_calls[0][0] == "insert"
        row = insert_calls[0][1]
        assert row["ticketId"] == "t-0001"
        assert row["authorId"] == "staff-001"
        assert row["content"] == "Escalated."
        # id is a generated v4 UUID string (not null/empty).
        assert isinstance(row["id"], str) and len(row["id"]) > 0
        # createdAt is left to the DB default (NOW()) — not set client-side.
        assert "createdAt" not in row

    @pytest.mark.asyncio
    async def test_insert_ticket_note_raises_without_connect(self, disconnected_db: Database) -> None:
        """insert_ticket_note() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.insert_ticket_note("t-0001", "staff-001", "text")


class TestGetTicketNotes:
    """Verify Database.get_ticket_notes() returns a ticket's notes, newest-first."""

    @pytest.mark.asyncio
    async def test_returns_notes_for_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST return rows filtered by ticketId."""
        notes = [_note_row_db(id="n1"), _note_row_db(id="n2", content="Second.")]
        fake_client.set_table_data("ticket_note", notes)

        result = await db.get_ticket_notes("t-0001")

        assert result == notes
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_ticket_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST apply an eq('ticketId', ...) filter."""
        fake_client.set_table_data("ticket_note", [])

        await db.get_ticket_notes("t-0001")

        filters = fake_client.get_table_filters("ticket_note")
        assert ("eq", "ticketId", "t-0001") in filters, f"Missing ticketId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_orders_newest_first(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST order by createdAt DESC (newest-first)."""
        fake_client.set_table_data("ticket_note", [])

        await db.get_ticket_notes("t-0001")

        orders = fake_client.get_table_orders("ticket_note")
        assert ("createdAt", True) in orders, f"Expected order('createdAt', desc=True), got: {orders}"

    @pytest.mark.asyncio
    async def test_applies_default_cap_limit(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST apply a default limit (cap by caller)."""
        fake_client.set_table_data("ticket_note", [])

        await db.get_ticket_notes("t-0001")

        limits = fake_client.get_table_limits("ticket_note")
        assert limits, f"Expected a limit() call, got: {limits}"
        assert limits[0] == 50

    @pytest.mark.asyncio
    async def test_applies_explicit_limit(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes(limit=...) MUST pass the caller's cap through."""
        fake_client.set_table_data("ticket_note", [])

        await db.get_ticket_notes("t-0001", limit=10)

        limits = fake_client.get_table_limits("ticket_note")
        assert 10 in limits

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_notes(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST return [] when the ticket has no notes."""
        fake_client.set_table_data("ticket_note", [])

        result = await db.get_ticket_notes("t-empty")

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_ticket_notes() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_ticket_notes("t-0001")


class TestDeleteTicketNote:
    """Verify Database.delete_ticket_note() targets a single note by id."""

    @pytest.mark.asyncio
    async def test_delete_targets_note_by_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """delete_ticket_note() MUST delete the row matching the given id."""
        await db.delete_ticket_note("n-uuid-1")

        filters = fake_client.get_table_filters("ticket_note")
        assert ("eq", "id", "n-uuid-1") in filters, f"delete_ticket_note MUST filter by id, got: {filters}"

    @pytest.mark.asyncio
    async def test_delete_raises_without_connect(self, disconnected_db: Database) -> None:
        """delete_ticket_note() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.delete_ticket_note("n-uuid-1")


# ===========================================================================
# get_ticket_by_number — resolve by guild + sequential ticket number (B5)
# ===========================================================================


class TestGetTicketByNumber:
    """Verify Database.get_ticket_by_number() resolves by guild+ticketNumber."""

    @pytest.mark.asyncio
    async def test_returns_row_when_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_by_number() MUST return the ticket row matching guild+number."""
        ticket_row = {"id": "t1", "guildId": "g1", "ticketNumber": 3, "status": "closed"}
        fake_client.set_table_data("ticket", [ticket_row])

        result = await db.get_ticket_by_number("g1", 3)

        assert result == ticket_row
        assert result is not None
        assert result["ticketNumber"] == 3

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_by_number() MUST return None when no ticket matches."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_ticket_by_number("g1", 999)

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_guild_and_number(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_by_number() MUST apply eq('guildId') AND eq('ticketNumber')."""
        fake_client.set_table_data("ticket", [])

        await db.get_ticket_by_number("g1", 3)

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g1") in filters, f"Missing guildId filter for guild scope, got: {filters}"
        assert ("eq", "ticketNumber", 3) in filters, f"Missing ticketNumber filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_ticket_by_number() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_ticket_by_number("g1", 3)


# ===========================================================================
# insert_audit_row — append a ticket_audit row (B5)
# ===========================================================================


class TestInsertAuditRow:
    """Verify Database.insert_audit_row() persists an audit log entry."""

    @pytest.mark.asyncio
    async def test_returns_persisted_row(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """insert_audit_row() MUST return the persisted audit row."""
        audit_row = {
            "id": "a1",
            "guildId": "g1",
            "ticketId": "t1",
            "action": "claim",
            "actorId": "u1",
            "outcome": "success",
            "reason": None,
        }
        fake_client.set_table_data("ticket_audit", [audit_row])

        result = await db.insert_audit_row("g1", "t1", "claim", "u1", "success", None)

        assert result["id"] == "a1"
        assert result["outcome"] == "success"
        assert result["action"] == "claim"

    @pytest.mark.asyncio
    async def test_inserts_all_fields_in_row(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """insert_audit_row() MUST insert a row carrying every field."""
        fake_client.set_table_data("ticket_audit", [{}])

        await db.insert_audit_row(
            guild_id="g1",
            ticket_id="t1",
            action="claim",
            actor_id="u1",
            outcome="success",
            reason="mod claim",
        )

        insert_calls = fake_client.get_table_calls("ticket_audit")
        assert len(insert_calls) == 1
        assert insert_calls[0][0] == "insert"
        inserted = insert_calls[0][1]
        assert inserted["guildId"] == "g1"
        assert inserted["ticketId"] == "t1"
        assert inserted["action"] == "claim"
        assert inserted["actorId"] == "u1"
        assert inserted["outcome"] == "success"
        assert inserted["reason"] == "mod claim"
        # id is generated client-side (matches insert_ticket_note convention).
        assert "id" in inserted and isinstance(inserted["id"], str) and inserted["id"]

    @pytest.mark.asyncio
    async def test_allows_nullable_actor_and_reason(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """insert_audit_row() MUST accept None for actorId and reason (system actions)."""
        fake_client.set_table_data("ticket_audit", [{}])

        await db.insert_audit_row("g1", "t1", "auto_close", None, "error", None)

        inserted = fake_client.get_table_calls("ticket_audit")[0][1]
        assert inserted["actorId"] is None
        assert inserted["reason"] is None

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """insert_audit_row() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.insert_audit_row("g1", "t1", "claim", "u1", "success", None)


# ===========================================================================
# get_audit_rows — paginated guild-scoped audit read (B5)
# ===========================================================================


class TestGetAuditRows:
    """Verify Database.get_audit_rows() returns guild-scoped, paginated audit rows."""

    @pytest.mark.asyncio
    async def test_returns_rows_newest_first(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows() MUST return rows ordered by createdAt DESC."""
        rows = [
            {"id": "a2", "guildId": "g1", "createdAt": "2024-06-15T12:01:00+00:00"},
            {"id": "a1", "guildId": "g1", "createdAt": "2024-06-15T12:00:00+00:00"},
        ]
        fake_client.set_table_data("ticket_audit", rows)

        result = await db.get_audit_rows("g1", limit=50, offset=0)

        assert result == rows
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows() MUST return [] when no audit rows exist."""
        fake_client.set_table_data("ticket_audit", [])

        result = await db.get_audit_rows("g1", limit=50, offset=0)

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows() MUST apply eq('guildId') so other guilds cannot leak."""
        fake_client.set_table_data("ticket_audit", [])

        await db.get_audit_rows("g1", limit=50, offset=0)

        filters = fake_client.get_table_filters("ticket_audit")
        assert ("eq", "guildId", "g1") in filters, f"Missing guildId filter (guild scope), got: {filters}"

    @pytest.mark.asyncio
    async def test_orders_by_created_at_desc(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows() MUST order by createdAt DESC (newest-first)."""
        fake_client.set_table_data("ticket_audit", [])

        await db.get_audit_rows("g1", limit=50, offset=0)

        orders = fake_client.get_table_orders("ticket_audit")
        assert ("createdAt", True) in orders, f"Expected order('createdAt', desc=True), got: {orders}"

    @pytest.mark.asyncio
    async def test_applies_limit_and_offset(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_audit_rows() MUST apply both limit() and offset() for pagination."""
        fake_client.set_table_data("ticket_audit", [])

        await db.get_audit_rows("g1", limit=25, offset=50)

        limits = fake_client.get_table_limits("ticket_audit")
        assert 25 in limits, f"Expected limit(25), got: {limits}"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_audit_rows() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_audit_rows("g1", limit=50, offset=0)


# ===========================================================================
# get_recent_notes_for_dedup — same-author notes in the dedup window (B5)
# ===========================================================================


class TestGetRecentNotesForDedup:
    """Verify Database.get_recent_notes_for_dedup() queries the 2s dedup window."""

    @pytest.mark.asyncio
    async def test_returns_recent_notes_for_author(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST return notes by this author in the window."""
        notes = [{"content": "hello world"}, {"content": "hi"}]
        fake_client.set_table_data("ticket_note", notes)

        result = await db.get_recent_notes_for_dedup("t1", "authorA")

        assert result == notes
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST return [] when no recent notes match."""
        fake_client.set_table_data("ticket_note", [])

        result = await db.get_recent_notes_for_dedup("t1", "authorA")

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_ticket_author_and_window(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST eq ticketId + authorId + gte createdAt(cutoff)."""
        fake_client.set_table_data("ticket_note", [])

        with freeze_time("2024-06-15 12:00:00", tz_offset=0):
            await db.get_recent_notes_for_dedup("t1", "authorA", window_seconds=2)

        filters = fake_client.get_table_filters("ticket_note")
        assert ("eq", "ticketId", "t1") in filters, f"Missing ticketId filter, got: {filters}"
        assert ("eq", "authorId", "authorA") in filters, f"Missing authorId filter, got: {filters}"
        # cutoff = now - 2s = 11:59:58
        gte_filters = [f for f in filters if f[0] == "gte" and f[1] == "createdAt"]
        assert len(gte_filters) == 1, f"Expected one gte createdAt filter, got: {filters}"
        assert gte_filters[0][2] == "2024-06-15T11:59:58+00:00", f"Expected cutoff now()-2s, got: {gte_filters[0][2]}"

    @pytest.mark.asyncio
    async def test_custom_window_seconds_changes_cutoff(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup(window_seconds=5) MUST compute cutoff = now()-5s."""
        fake_client.set_table_data("ticket_note", [])

        with freeze_time("2024-06-15 12:00:00", tz_offset=0):
            await db.get_recent_notes_for_dedup("t1", "authorA", window_seconds=5)

        filters = fake_client.get_table_filters("ticket_note")
        gte_filters = [f for f in filters if f[0] == "gte" and f[1] == "createdAt"]
        assert gte_filters[0][2] == "2024-06-15T11:59:55+00:00", f"Expected cutoff now()-5s, got: {gte_filters[0][2]}"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """get_recent_notes_for_dedup() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.get_recent_notes_for_dedup("t1", "authorA")


# ===========================================================================
# PR5: count_open_tickets_by_category — uses count="exact" (5.4)
# ===========================================================================


class TestCountOpenTicketsByCategory:
    """Verify Database.count_open_tickets_by_category() uses count="exact"."""

    @pytest.mark.asyncio
    async def test_returns_count_from_response(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """count_open_tickets_by_category() MUST return count from response, not len(data)."""
        # With count="exact", the FakeQueryBuilder will set response.count = len(data)
        fake_client.set_table_data("ticket", [{"id": "t1"}, {"id": "t2"}])

        result = await db.count_open_tickets_by_category("g1", "cat-1")

        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_tickets(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """count_open_tickets_by_category() MUST return 0 when no open tickets exist."""
        fake_client.set_table_data("ticket", [])

        result = await db.count_open_tickets_by_category("g1", "cat-empty")

        assert result == 0

    @pytest.mark.asyncio
    async def test_filters_by_guild_category_and_status(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """count_open_tickets_by_category() MUST filter by guildId, categoryId and status IN (open, claimed)."""
        fake_client.set_table_data("ticket", [])

        await db.count_open_tickets_by_category("g1", "cat-1")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "guildId", "g1") in filters
        assert ("eq", "categoryId", "cat-1") in filters
        assert ("in_", "status", ["open", "claimed"]) in filters

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """count_open_tickets_by_category() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.count_open_tickets_by_category("g1", "cat-1")


# ===========================================================================
# PR5: RPC member increment methods (5.7 — RED tests)
# ===========================================================================


class TestRpcIncrementMemberXp:
    """Verify Database.update_member_xp() uses RPC for atomic increment."""

    @pytest.mark.asyncio
    async def test_calls_rpc_increment_member_xp(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_xp() MUST call rpc('increment_member_xp') once."""
        fake_client.set_rpc_result([{"xp": 150, "level": 5}])

        result = await db.update_member_xp("g1", "u1", 50)

        assert len(fake_client._rpc_calls) == 1
        assert fake_client._rpc_calls[0][0] == "increment_member_xp"
        assert fake_client._rpc_calls[0][1]["p_guild_id"] == "g1"
        assert fake_client._rpc_calls[0][1]["p_user_id"] == "u1"
        assert fake_client._rpc_calls[0][1]["p_amount"] == 50
        assert result["xp"] == 150

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_member_xp() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_member_xp("g1", "u1", 10)


class TestRpcIncrementMemberCoins:
    """Verify Database.update_member_coins() uses RPC for atomic increment."""

    @pytest.mark.asyncio
    async def test_calls_rpc_increment_member_coins(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_coins() MUST call rpc('increment_member_coins') once."""
        fake_client.set_rpc_result([{"coins": 250}])

        result = await db.update_member_coins("g1", "u1", 50)

        assert len(fake_client._rpc_calls) == 1
        assert fake_client._rpc_calls[0][0] == "increment_member_coins"
        assert fake_client._rpc_calls[0][1]["p_guild_id"] == "g1"
        assert fake_client._rpc_calls[0][1]["p_user_id"] == "u1"
        assert fake_client._rpc_calls[0][1]["p_amount"] == 50
        assert result["coins"] == 250

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_member_coins() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_member_coins("g1", "u1", 10)


class TestRpcIncrementMemberWarnings:
    """Verify Database.update_member_warnings() uses RPC for atomic increment."""

    @pytest.mark.asyncio
    async def test_calls_rpc_increment_member_warnings(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_warnings() MUST call rpc('increment_member_warnings') once."""
        fake_client.set_rpc_result([{"warnings": 3}])

        await db.update_member_warnings("g1", "u1", 1)

        assert len(fake_client._rpc_calls) == 1
        assert fake_client._rpc_calls[0][0] == "increment_member_warnings"
        assert fake_client._rpc_calls[0][1]["p_guild_id"] == "g1"
        assert fake_client._rpc_calls[0][1]["p_user_id"] == "u1"
        assert fake_client._rpc_calls[0][1]["p_amount"] == 1

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_member_warnings() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_member_warnings("g1", "u1", 1)


class TestRpcSetMemberDaily:
    """Verify Database.update_member_daily() uses RPC for atomic daily claim."""

    @pytest.mark.asyncio
    async def test_calls_rpc_set_member_daily(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_daily() MUST call rpc('set_member_daily') once."""
        fake_client.set_rpc_result([{"coins": 150, "dailyStreak": 3, "lastDailyReset": "2024-06-15T00:00:00Z", "lastDaily": "2024-06-15T12:00:00Z"}])

        result = await db.update_member_daily("g1", "u1", 100, 3, "2024-06-15T00:00:00Z", "2024-06-15T12:00:00Z")

        assert len(fake_client._rpc_calls) == 1
        assert fake_client._rpc_calls[0][0] == "set_member_daily"
        params = fake_client._rpc_calls[0][1]
        assert params["p_guild_id"] == "g1"
        assert params["p_user_id"] == "u1"
        assert params["p_coin_amount"] == 100
        assert params["p_streak"] == 3
        assert result["coins"] == 150
        assert result["dailyStreak"] == 3

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_member_daily() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_member_daily("g1", "u1", 50, 1, None, None)


# ===========================================================================
# PR3: Database facade — import compatibility + mixin method presence
# ===========================================================================


class TestDatabaseFacade:
    """Verify the Database facade preserves import paths and method surface.

    After the PR3 mixin split, ``from bot.core.database import Database``
    MUST continue to work, and every domain method MUST be accessible on
    the class so that no downstream import breaks.
    """

    def test_import_database_from_core_database(self) -> None:
        """from bot.core.database import Database MUST succeed after mixin split."""
        from bot.core.database import Database as Db

        assert Db is not None

    def test_import_create_realtime_client(self) -> None:
        """from bot.core.database import create_realtime_client MUST still work."""
        from bot.core.database import create_realtime_client

        assert callable(create_realtime_client)

    def test_database_has_all_expected_methods(self) -> None:
        """Database instance MUST expose every domain method from all mixins."""
        db = Database(url="https://test.supabase.co", key="test-key")

        expected_methods = [
            # base
            "connect",
            "health_check",
            # guild
            "get_guild",
            "upsert_guild",
            "ensure_guild_exists",
            "update_guild_panel",
            # member
            "get_member",
            "update_member_warnings",
            # infraction
            "insert_infraction",
            "get_infractions",
            "get_active_warnings",
            "deactivate_infraction",
            # ticket
            "insert_ticket",
            "get_tickets_by_parent",
            "get_ticket",
            "get_ticket_by_channel",
            "get_ticket_by_number",
            "update_ticket",
            "get_stale_tickets",
            "get_max_ticket_number",
            "get_open_ticket_channel_ids",
            "update_ticket_last_activity",
            # ticket_note
            "insert_ticket_note",
            "get_ticket_notes",
            "delete_ticket_note",
            "get_recent_notes_for_dedup",
            # ticket_category
            "insert_ticket_category",
            "get_ticket_categories",
            "get_ticket_category",
            "delete_ticket_category",
            "count_open_tickets_by_category",
            "update_ticket_category_field_definitions",
            # ticket_audit
            "insert_audit_row",
            "get_audit_rows",
            # economy
            "get_economy_config",
            "upsert_economy_config",
            "update_member_xp",
            "update_member_coins",
            "update_member_daily",
            "get_leaderboard",
            "get_member_rank",
            # greeting
            "get_greeting_config",
            "upsert_greeting_config",
        ]

        for method_name in expected_methods:
            assert hasattr(db, method_name), f"Database missing method: {method_name}"
            assert callable(getattr(db, method_name)), f"Database.{method_name} is not callable"

    def test_database_preserves_slots(self) -> None:
        """Database MUST have __slots__ (inherited from DatabaseBase)."""
        db = Database(url="https://test.supabase.co", key="test-key")
        assert hasattr(Database, "__slots__")
        # Verify the slot names are correct
        assert "_client" in Database.__slots__
        assert "_url" in Database.__slots__
        assert "_key" in Database.__slots__
        assert "_on_write" in Database.__slots__


# ===========================================================================
# PR1: update_ticket_category_field_definitions — guild-scoped JSONB update
# ===========================================================================


class TestUpdateTicketCategoryFieldDefinitions:
    """Verify Database.update_ticket_category_field_definitions() updates JSONB by id+guildId."""

    @pytest.mark.asyncio
    async def test_updates_field_definitions_by_id_and_guild(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """update_ticket_category_field_definitions() MUST update fieldDefinitions filtered by id AND guildId."""
        defs = [{"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True}]
        fake_client.set_table_data("ticket_category", [{"id": "cat-1", "fieldDefinitions": defs}])

        await db.update_ticket_category_field_definitions("g1", "cat-1", defs)

        update_calls = fake_client.get_table_calls("ticket_category")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["fieldDefinitions"] == defs

    @pytest.mark.asyncio
    async def test_filters_by_id_and_guild_id(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """update_ticket_category_field_definitions() MUST apply eq('id') AND eq('guildId')."""
        fake_client.set_table_data("ticket_category", [])

        await db.update_ticket_category_field_definitions("g1", "cat-1", [])

        filters = fake_client.get_table_filters("ticket_category")
        assert ("eq", "id", "cat-1") in filters, f"Missing id filter, got: {filters}"
        assert ("eq", "guildId", "g1") in filters, f"Missing guildId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_ticket_category_field_definitions() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_ticket_category_field_definitions("g1", "cat-1", [])


# ===========================================================================
# PR1: insert_ticket with custom_fields
# ===========================================================================


class TestInsertTicketWithCustomFields:
    """Verify Database.insert_ticket() handles the custom_fields parameter."""

    @pytest.mark.asyncio
    async def test_insert_ticket_with_custom_fields_stores_jsonb(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket(custom_fields=...) MUST include 'customFields' in the inserted row."""
        fields = {"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"}
        fake_client.set_table_data("ticket", [{"id": "t-cf", "customFields": fields}])

        await db.insert_ticket("g1", "u1", "ch1", "cat-1", 1, custom_fields=fields)

        insert_calls = fake_client.get_table_calls("ticket")
        assert len(insert_calls) == 1
        inserted_row = insert_calls[0][1]
        assert inserted_row["customFields"] == fields

    @pytest.mark.asyncio
    async def test_insert_ticket_without_custom_fields_defaults_empty(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket() without custom_fields MUST insert customFields={} by default."""
        fake_client.set_table_data("ticket", [{"id": "t-no-cf", "customFields": {}}])

        await db.insert_ticket("g1", "u1", "ch1", None, 1)

        insert_calls = fake_client.get_table_calls("ticket")
        inserted_row = insert_calls[0][1]
        assert inserted_row["customFields"] == {}


# ===========================================================================
# PR1: Ticket facade method presence check
# ===========================================================================


class TestDatabaseFacadePR1Methods:
    """Verify Database exposes the new PR1 methods from the mixin."""

    def test_database_has_update_ticket_category_field_definitions(self) -> None:
        """Database MUST expose update_ticket_category_field_definitions()."""
        db = Database(url="https://test.supabase.co", key="test-key")
        assert hasattr(db, "update_ticket_category_field_definitions")
        assert callable(getattr(db, "update_ticket_category_field_definitions"))


# ===========================================================================
# update_guild_panel — _on_write hook call after successful update
# (ticket-panel-persistence, Phase 1)
# ===========================================================================


class TestUpdateGuildPanelOnWrite:
    """Verify Database.update_guild_panel() calls _on_write hook after successful DB write."""

    @pytest.mark.asyncio
    async def test_calls_on_write_after_successful_update(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """update_guild_panel() MUST call self._on_write('guild', guild_id) after the DB write succeeds."""
        on_write = AsyncMock()
        db._on_write = on_write

        await db.update_guild_panel("g1", "msg-123", "ch-456")

        on_write.assert_awaited_once_with("guild", "g1")

    @pytest.mark.asyncio
    async def test_does_not_call_on_write_when_not_set(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """update_guild_panel() MUST NOT raise when _on_write is None."""
        db._on_write = None

        # Should not raise — just skip the hook.
        await db.update_guild_panel("g1", "msg-123", "ch-456")

    @pytest.mark.asyncio
    async def test_supports_nullable_message_id_and_channel_id(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """update_guild_panel(message_id=None, channel_id=None) MUST clear the stored panel IDs."""
        on_write = AsyncMock()
        db._on_write = on_write

        await db.update_guild_panel("g1", None, None)

        update_calls = fake_client.get_table_calls("guild")
        assert len(update_calls) == 1
        assert update_calls[0][0] == "update"
        assert update_calls[0][1]["ticketPanelMessageId"] is None
        assert update_calls[0][1]["ticketPanelChannelId"] is None
        on_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_without_connect(self, disconnected_db: Database) -> None:
        """update_guild_panel() MUST raise RuntimeError if connect() wasn't called."""
        with pytest.raises(RuntimeError, match="connect"):
            await disconnected_db.update_guild_panel("g1", "msg", "ch")
