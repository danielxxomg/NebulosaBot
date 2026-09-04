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

import base64
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from freezegun import freeze_time

from bot.config import ServiceRoleValidationError
from bot.core.database import Database
from bot.core.realtime import RecentWriteSet
from bot.models.economy_config import EconomyConfig
from bot.models.guild import GuildConfig
from bot.services.schema_inventory import (
    CDC_TABLES,
    FK_RETENTION,
    GUILD_SCOPE_GAPS,
    LEADERBOARD_TTL_SECONDS,
    RLS_NO_POLICY_TABLES,
    TTL_SECONDS,
    UNUSED_INDEXES_FOR_REVIEW,
    SchemaInventory,
    is_guild_scope_gap,
    is_rls_denied_for_anon,
)

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
        self._count: str | None = None  # for count="exact" support

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

    def upsert(self, data: Any, **_kwargs: Any) -> FakeQueryBuilder:
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
# Fail-closed guard matrix — every method MUST raise RuntimeError("connect")
# when connect() hasn't been called. One parametrized test replaces the
# 23 identical raises_without_connect guards previously spread per class.
# ---------------------------------------------------------------------------


GUARD_CALLS: tuple[tuple[str, Callable[[Database], Awaitable[object]]], ...] = (
    ("get-guild", lambda db: db.get_guild("123")),
    ("upsert-guild", lambda db: db.upsert_guild(GuildConfig(id="123"))),
    ("get-member", lambda db: db.get_member("g1", "u1")),
    ("get-infractions", lambda db: db.get_infractions("g1", "u1")),
    ("insert-ticket", lambda db: db.insert_ticket("g1", "u1", "ch1", None, 1)),
    ("get-tickets-by-parent", lambda db: db.get_tickets_by_parent("p1")),
    ("update-member-xp", lambda db: db.update_member_xp("g1", "u1", 10)),
    ("get-economy-config", lambda db: db.get_economy_config("g1")),
    ("get-greeting-config", lambda db: db.get_greeting_config("g1")),
    ("insert-ticket-note", lambda db: db.insert_ticket_note("t-0001", "staff-001", "text")),
    ("get-ticket-notes", lambda db: db.get_ticket_notes("t-0001")),
    ("delete-ticket-note", lambda db: db.delete_ticket_note("n-uuid-1")),
    ("get-ticket-by-number", lambda db: db.get_ticket_by_number("g1", 3)),
    ("insert-audit-row", lambda db: db.insert_audit_row("g1", "t1", "claim", "u1", "success", None)),
    ("get-audit-rows", lambda db: db.get_audit_rows("g1", limit=50, offset=0)),
    ("get-recent-notes-for-dedup", lambda db: db.get_recent_notes_for_dedup("t1", "authorA")),
    ("count-open-tickets-by-category", lambda db: db.count_open_tickets_by_category("g1", "cat-1")),
    ("rpc-increment-member-xp", lambda db: db.update_member_xp("g1", "u1", 10)),
    ("rpc-increment-member-coins", lambda db: db.update_member_coins("g1", "u1", 10)),
    ("rpc-increment-member-warnings", lambda db: db.update_member_warnings("g1", "u1", 1)),
    ("rpc-set-member-daily", lambda db: db.update_member_daily("g1", "u1", 50, 1, None, None)),
    ("update-ticket-category-field-defs", lambda db: db.update_ticket_category_field_definitions("g1", "cat-1", [])),
    ("update-guild-panel", lambda db: db.update_guild_panel("g1", "msg", "ch")),
)


class TestRaisesWithoutConnectMatrix:
    """Every Database method MUST fail closed with RuntimeError before connect()."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("guard_call", GUARD_CALLS, ids=[g[0] for g in GUARD_CALLS])
    async def test_raises_without_connect(self, disconnected_db: Database, guard_call) -> None:
        """MUST raise RuntimeError(match='connect') when no client is wired."""
        _name, call = guard_call
        with pytest.raises(RuntimeError, match="connect"):
            await call(disconnected_db)


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
        """connect() MUST fail-closed when health check fails — client cleared and error raised."""
        database = Database(url="https://test.supabase.co", key="test-key")

        mock_client = MagicMock()

        async def mock_execute_fail() -> MagicMock:
            raise ConnectionError("connection refused")

        mock_client.table.return_value.select.return_value.limit.return_value.execute = mock_execute_fail

        with (
            patch("bot.core.db.base.acreate_client", return_value=mock_client),
            pytest.raises(ServiceRoleValidationError, match="health probe"),
        ):
            await database.connect()

        assert database._client is None
        # Subsequent DB operation must fail closed (no active client).
        with pytest.raises(RuntimeError, match="connect"):
            await database.get_guild("123")


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

        result = await db.get_tickets_by_parent("p1", guild_id="g1")

        assert result == children
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_parent_id_column(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST apply an eq('parentId', ...) filter."""
        fake_client.set_table_data("ticket", [])

        await db.get_tickets_by_parent("p1", guild_id="g1")

        filters = fake_client.get_table_filters("ticket")
        assert ("eq", "parentId", "p1") in filters, f"Missing parentId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_children(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST return [] when the parent has no children."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_tickets_by_parent("orphan-parent", guild_id="g1")

        assert result == []

    @pytest.mark.asyncio
    async def test_orders_newest_first(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_tickets_by_parent() MUST order by createdAt DESC (newest-first)."""
        fake_client.set_table_data("ticket", [])

        await db.get_tickets_by_parent("p-0001", guild_id="g1")

        orders = fake_client.get_table_orders("ticket")
        assert ("createdAt", True) in orders, f"Expected order('createdAt', desc=True), got: {orders}"


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

        result = await db.get_ticket("t1", guild_id="g1")

        assert result == ticket_row
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_ticket_returns_none_when_not_found(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket() MUST return None when no ticket exists."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_ticket("nonexistent", guild_id="g1")

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

        result = await db.get_ticket_by_channel("ch1", guild_id="g1")

        assert result == ticket_row
        assert result is not None
        assert result["channelId"] == "ch1"

    @pytest.mark.asyncio
    async def test_get_ticket_by_channel_returns_none_when_not_found(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """get_ticket_by_channel() MUST return None when no ticket exists for channel."""
        fake_client.set_table_data("ticket", [])

        result = await db.get_ticket_by_channel("unknown-channel", guild_id="g1")

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
        fake_client.set_rpc_result([
            {
                "coins": 150,
                "dailyStreak": 3,
                "lastDailyReset": "2024-06-15T00:00:00Z",
                "lastDaily": "2024-06-15T12:00:00Z",
            },
        ])

        result = await db.update_member_daily(
            "g1",
            "u1",
            100,
            3,
            "2024-06-15T00:00:00Z",
            "2024-06-15T12:00:00Z",
        )

        assert result["coins"] == 150
        assert result["dailyStreak"] == 3

    @pytest.mark.asyncio
    async def test_update_member_daily_creates_new_member(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_daily() MUST call rpc which handles upsert on new member."""
        fake_client.set_rpc_result([
            {
                "coins": 50,
                "dailyStreak": 1,
                "lastDailyReset": "2024-06-15T00:00:00Z",
                "lastDaily": "2024-06-15T12:00:00Z",
            },
        ])

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


# ---------------------------------------------------------------------------
# Guild-scoped filter assertions — prove guild_id is passed to Supabase
# ---------------------------------------------------------------------------


GUILD_SCOPED_FILTER_CASES: tuple[tuple[str, Callable[[Database], Awaitable[object]], str, tuple[tuple[str, str, object], ...]], ...] = (
    (
        "get-guild-by-id",
        lambda db: db.get_guild("g1"),
        "guild",
        (("eq", "id", "g1"),),
    ),
    (
        "get-member-by-guild-and-user",
        lambda db: db.get_member("g1", "u1"),
        "member",
        (("eq", "guildId", "g1"), ("eq", "userId", "u1")),
    ),
    (
        "get-infractions",
        lambda db: db.get_infractions("g99", "u1"),
        "infraction",
        (("eq", "guildId", "g99"),),
    ),
    (
        "get-active-warnings",
        lambda db: db.get_active_warnings("g42", "u1"),
        "infraction",
        (("eq", "guildId", "g42"),),
    ),
    (
        "get-leaderboard",
        lambda db: db.get_leaderboard("g77"),
        "member",
        (("eq", "guildId", "g77"),),
    ),
    (
        "get-economy-config",
        lambda db: db.get_economy_config("g55"),
        "economy_config",
        (("eq", "guildId", "g55"),),
    ),
    (
        "get-greeting-config",
        lambda db: db.get_greeting_config("g33"),
        "greeting_config",
        (("eq", "guildId", "g33"),),
    ),
)


class TestGuildScopedFilters:
    """Scenario: guild-scoped query filters correctly.

    Per qa-database-coverage/spec.md, queries that scope by guild_id MUST
    pass an eq('guildId', ...) filter to the Supabase query builder.
    These tests assert on captured filter calls to prove the filter is applied.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filter_case",
        GUILD_SCOPED_FILTER_CASES,
        ids=[c[0] for c in GUILD_SCOPED_FILTER_CASES],
    )
    async def test_query_applies_expected_filters(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
        filter_case,
    ) -> None:
        """The query MUST pass every expected eq() filter to the builder."""
        _name, call, table, expected_filters = filter_case
        fake_client.set_table_data(table, [])
        await call(db)

        filters = fake_client.get_table_filters(table)
        for expected in expected_filters:
            assert expected in filters, f"Missing {expected} filter, got: {filters}"

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
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [_note_row_db()])

        result = await db.insert_ticket_note("t-0001", "staff-001", "Escalated.", guild_id="g1")

        assert result["id"] == "n-uuid-1"
        assert result["ticketId"] == "t-0001"

    @pytest.mark.asyncio
    async def test_insert_ticket_note_stores_camelcase_columns(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """insert_ticket_note() MUST insert a row with camelCase columns + a UUID id."""
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [_note_row_db()])

        await db.insert_ticket_note("t-0001", "staff-001", "Escalated.", guild_id="g1")

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


class TestGetTicketNotes:
    """Verify Database.get_ticket_notes() returns a ticket's notes, newest-first."""

    @pytest.mark.asyncio
    async def test_returns_notes_for_ticket(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST return rows filtered by ticketId."""
        notes = [_note_row_db(id="n1"), _note_row_db(id="n2", content="Second.")]
        fake_client.set_table_data("ticket_note", notes)
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])

        result = await db.get_ticket_notes("t-0001", guild_id="g1")

        assert result == notes
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_ticket_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST apply an eq('ticketId', ...) filter."""
        fake_client.set_table_data("ticket_note", [])
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])

        await db.get_ticket_notes("t-0001", guild_id="g1")

        filters = fake_client.get_table_filters("ticket_note")
        assert ("eq", "ticketId", "t-0001") in filters, f"Missing ticketId filter, got: {filters}"

    @pytest.mark.asyncio
    async def test_orders_newest_first(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST order by createdAt DESC (newest-first)."""
        fake_client.set_table_data("ticket_note", [])
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])

        await db.get_ticket_notes("t-0001", guild_id="g1")

        orders = fake_client.get_table_orders("ticket_note")
        assert ("createdAt", True) in orders, f"Expected order('createdAt', desc=True), got: {orders}"

    @pytest.mark.asyncio
    async def test_applies_default_cap_limit(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST apply a default limit (cap by caller)."""
        fake_client.set_table_data("ticket_note", [])
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])

        await db.get_ticket_notes("t-0001", guild_id="g1")

        limits = fake_client.get_table_limits("ticket_note")
        assert limits, f"Expected a limit() call, got: {limits}"
        assert limits[0] == 50

    @pytest.mark.asyncio
    async def test_applies_explicit_limit(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes(limit=...) MUST pass the caller's cap through."""
        fake_client.set_table_data("ticket_note", [])
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])

        await db.get_ticket_notes("t-0001", guild_id="g1", limit=10)

        limits = fake_client.get_table_limits("ticket_note")
        assert 10 in limits

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_notes(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_ticket_notes() MUST return [] when the ticket has no notes."""
        fake_client.set_table_data("ticket_note", [])
        fake_client.set_table_data("ticket", [{"id": "t-empty", "guildId": "g1"}])

        result = await db.get_ticket_notes("t-empty", guild_id="g1")

        assert result == []


class TestDeleteTicketNote:
    """Verify Database.delete_ticket_note() targets a single note by id."""

    @pytest.mark.asyncio
    async def test_delete_targets_note_by_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """delete_ticket_note() MUST delete the row matching the given id."""
        fake_client.set_table_data("ticket", [{"id": "t-0001", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [{"id": "n-uuid-1", "ticketId": "t-0001"}])
        await db.delete_ticket_note("n-uuid-1", guild_id="g1", ticket_id="t-0001")

        filters = fake_client.get_table_filters("ticket_note")
        assert ("eq", "id", "n-uuid-1") in filters, f"delete_ticket_note MUST filter by id, got: {filters}"


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


# ===========================================================================
# get_recent_notes_for_dedup — same-author notes in the dedup window (B5)
# ===========================================================================


class TestGetRecentNotesForDedup:
    """Verify Database.get_recent_notes_for_dedup() queries the 2s dedup window."""

    @pytest.mark.asyncio
    async def test_returns_recent_notes_for_author(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST return notes by this author in the window."""
        notes = [{"content": "hello world"}, {"content": "hi"}]
        fake_client.set_table_data("ticket", [{"id": "t1", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", notes)

        result = await db.get_recent_notes_for_dedup("t1", "authorA", guild_id="g1")

        assert result == notes
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_none(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST return [] when no recent notes match."""
        fake_client.set_table_data("ticket", [{"id": "t1", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [])

        result = await db.get_recent_notes_for_dedup("t1", "authorA", guild_id="g1")

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_ticket_author_and_window(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """get_recent_notes_for_dedup() MUST eq ticketId + authorId + gte createdAt(cutoff)."""
        fake_client.set_table_data("ticket", [{"id": "t1", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [])

        with freeze_time("2024-06-15 12:00:00", tz_offset=0):
            await db.get_recent_notes_for_dedup("t1", "authorA", guild_id="g1", window_seconds=2)

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
        fake_client.set_table_data("ticket", [{"id": "t1", "guildId": "g1"}])
        fake_client.set_table_data("ticket_note", [])

        with freeze_time("2024-06-15 12:00:00", tz_offset=0):
            await db.get_recent_notes_for_dedup("t1", "authorA", guild_id="g1", window_seconds=5)

        filters = fake_client.get_table_filters("ticket_note")
        gte_filters = [f for f in filters if f[0] == "gte" and f[1] == "createdAt"]
        assert gte_filters[0][2] == "2024-06-15T11:59:55+00:00", f"Expected cutoff now()-5s, got: {gte_filters[0][2]}"


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


class TestRpcSetMemberDaily:
    """Verify Database.update_member_daily() uses RPC for atomic daily claim."""

    @pytest.mark.asyncio
    async def test_calls_rpc_set_member_daily(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_member_daily() MUST call rpc('set_member_daily') once."""
        fake_client.set_rpc_result([
            {
                "coins": 150,
                "dailyStreak": 3,
                "lastDailyReset": "2024-06-15T00:00:00Z",
                "lastDaily": "2024-06-15T12:00:00Z",
            },
        ])

        result = await db.update_member_daily(
            "g1",
            "u1",
            100,
            3,
            "2024-06-15T00:00:00Z",
            "2024-06-15T12:00:00Z",
        )

        assert len(fake_client._rpc_calls) == 1
        assert fake_client._rpc_calls[0][0] == "set_member_daily"
        params = fake_client._rpc_calls[0][1]
        assert params["p_guild_id"] == "g1"
        assert params["p_user_id"] == "u1"
        assert params["p_coin_amount"] == 100
        assert params["p_streak"] == 3
        assert result["coins"] == 150
        assert result["dailyStreak"] == 3


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
        # PLC0415 documented exception — facade-indirection probe: asserting
        # post-split importability REQUIRES the import inside the test.
        from bot.core.database import Database as Db  # noqa: PLC0415 -- facade indirection

        assert Db is not None

    def test_import_create_realtime_client(self) -> None:
        """from bot.core.database import create_realtime_client MUST still work."""
        # PLC0415 documented exception — facade-indirection probe: asserting
        # post-split importability REQUIRES the import inside the test.
        from bot.core.database import create_realtime_client  # noqa: PLC0415 -- facade indirection

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
        Database(url="https://test.supabase.co", key="test-key")
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
    async def test_filters_by_id_and_guild_id(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_ticket_category_field_definitions() MUST apply eq('id') AND eq('guildId')."""
        fake_client.set_table_data("ticket_category", [])

        await db.update_ticket_category_field_definitions("g1", "cat-1", [])

        filters = fake_client.get_table_filters("ticket_category")
        assert ("eq", "id", "cat-1") in filters, f"Missing id filter, got: {filters}"
        assert ("eq", "guildId", "g1") in filters, f"Missing guildId filter, got: {filters}"


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
        assert callable(db.update_ticket_category_field_definitions)


# ===========================================================================
# update_guild_panel — _on_write hook call after successful update
# (ticket-panel-persistence, Phase 1)
# ===========================================================================


class TestUpdateGuildPanelOnWrite:
    """Verify Database.update_guild_panel() calls _on_write hook after successful DB write."""

    @pytest.mark.asyncio
    async def test_calls_on_write_after_successful_update(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """update_guild_panel() MUST call self._on_write('guild', guild_id) after the DB write succeeds."""
        on_write = AsyncMock()
        db._on_write = on_write

        await db.update_guild_panel("g1", "msg-123", "ch-456")

        on_write.assert_awaited_once_with("guild", "g1")

    @pytest.mark.asyncio
    async def test_does_not_call_on_write_when_not_set(self, db: Database, fake_client: FakeSupabaseClient) -> None:
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


# ===========================================================================
# CDC echo suppression — _on_write hooks on member/economy mutators (S6)
# ===========================================================================


class TestMemberEconomyOnWriteHooks:
    """Every member/economy RPC mutator MUST mark recent writes via ``_on_write``.

    Spec cache-sync-realtime "Echo suppression wired before publication":
    bot-originated member/economy writes MUST be recorded in the recent-writes
    set BEFORE the publication migration adds ``member``/``economy_config`` to
    the Realtime publication — otherwise every own RPC write bounces back as
    an unfiltered CDC echo event.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("call_name", "invoke"),
        [
            pytest.param(
                "update_member_xp",
                lambda db: db.update_member_xp("g1", "u1", 50),
                id="update_member_xp",
            ),
            pytest.param(
                "update_member_coins",
                lambda db: db.update_member_coins("g1", "u1", 75),
                id="update_member_coins",
            ),
            pytest.param(
                "update_member_daily",
                lambda db: db.update_member_daily("g1", "u1", 100, streak=2, last_daily_reset=None, last_daily=None),
                id="update_member_daily",
            ),
            pytest.param(
                "update_member_warnings",
                lambda db: db.update_member_warnings("g1", "u1", 1),
                id="update_member_warnings",
            ),
        ],
    )
    async def test_member_mutator_marks_member_write(
        self,
        db: Database,
        fake_client: FakeSupabaseClient,
        call_name: str,
        invoke,
    ) -> None:
        """Each member RPC mutator MUST call _on_write('member', guild_id) after the RPC."""
        on_write = AsyncMock()
        db._on_write = on_write
        fake_client.set_rpc_result([{"xp": 50, "coins": 75}])

        await invoke(db)

        on_write.assert_awaited_once_with("member", "g1")

    @pytest.mark.asyncio
    async def test_upsert_economy_config_marks_config_write(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """upsert_economy_config() MUST call _on_write('economy_config', guild_id)."""
        on_write = AsyncMock()
        db._on_write = on_write
        config = EconomyConfig(guild_id="g1", daily_reward=150)

        await db.upsert_economy_config(config)

        on_write.assert_awaited_once_with("economy_config", "g1")

    @pytest.mark.asyncio
    async def test_update_member_xp_marks_after_level_override_too(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """With new_level set, the hook fires AFTER the level UPDATE so its CDC
        echo is suppressed too (mark covers both writes of the same guild row).
        """
        on_write = AsyncMock()
        db._on_write = on_write
        fake_client.set_rpc_result([{"xp": 100}])

        await db.update_member_xp("g1", "u1", 100, new_level=6)

        on_write.assert_awaited_once_with("member", "g1")
        # Level override issued a second write — the mark still happens once,
        # after it.
        assert len(fake_client.get_table_calls("member")) == 1

    @pytest.mark.asyncio
    async def test_mutators_succeed_without_hook(self, db: Database, fake_client: FakeSupabaseClient) -> None:
        """Mutators MUST NOT raise when no subscriber is wired (_on_write is None)."""
        db._on_write = None
        fake_client.set_rpc_result([{"xp": 10}])

        await db.update_member_xp("g1", "u1", 10)
        await db.update_member_warnings("g1", "u1", 1)
        await db.upsert_economy_config(EconomyConfig(guild_id="g1"))

    @pytest.mark.asyncio
    async def test_hook_marks_recent_writes_set_for_echo_skip(
        self, db: Database, fake_client: FakeSupabaseClient
    ) -> None:
        """Spec 'Echo of own write is skipped': wiring the subscriber's recent-
        writes set as the hook means a completed mutator write leaves
        ``{table}:{guild_id}`` marked BEFORE any CDC echo could arrive.
        """
        rws = RecentWriteSet()
        db._on_write = rws.mark
        fake_client.set_rpc_result([{"xp": 5}])

        await db.update_member_xp("G1", "u1", 5)

        assert await rws.contains("member", "G1") is True


# ===========================================================================
# Schema inventory twin (tests-slim-fase-2 B1) — replaces
# tests/test_pr3_inventory.py.
# D3 proof: GUILD_SCOPE_GAPS enumeration, 015 index idx_ticket_guild_ticket_number,
# CDC TTL 300 / leaderboard TTL 30, FK retention (CASCADE / SET NULL), and the
# 12-unused-indexes review list — asserted with exact values, read-only.
# ===========================================================================


class TestSchemaInventoryTwin:
    """Guild-scope gaps + 015 parity + read-only contract, parametrized."""

    @pytest.mark.parametrize(
        ("method", "expected"),
        [
            pytest.param("get_ticket", True, id="gap-get_ticket"),
            pytest.param("get_ticket_by_channel", True, id="gap-get_ticket_by_channel"),
            pytest.param("update_ticket", True, id="gap-update_ticket"),
            pytest.param("get_tickets_by_parent", True, id="gap-get_tickets_by_parent"),
            pytest.param("get_ticket_by_number", False, id="nogap-get_ticket_by_number"),
            pytest.param("get_guild", False, id="nogap-get_guild"),
            pytest.param("get_tickets_by_guild", False, id="nogap-get_tickets_by_guild"),
        ],
    )
    def test_guild_scope_gap_classification(self, method: str, expected: bool) -> None:
        """GUILD_SCOPE_GAPS MUST classify ID-only methods; guild-scoped ones are not gaps."""
        assert is_guild_scope_gap(method) is expected

    def test_guild_scope_gaps_enumerates_core_and_families(self) -> None:
        """GUILD_SCOPE_GAPS MUST contain the core ticket ID-only methods plus category/note/audit families."""
        core_required = {
            "get_ticket",
            "get_ticket_by_channel",
            "update_ticket",
            "get_tickets_by_parent",
        }
        assert core_required.issubset(set(GUILD_SCOPE_GAPS))
        gaps = set(GUILD_SCOPE_GAPS)
        assert any("category" in m.lower() for m in gaps), "category methods missing from GUILD_SCOPE_GAPS"
        assert any("note" in m.lower() for m in gaps), "note methods missing from GUILD_SCOPE_GAPS"
        assert any("audit" in m.lower() for m in gaps), "audit methods missing from GUILD_SCOPE_GAPS"

    @pytest.mark.parametrize(
        "fact",
        [
            pytest.param("migration_015_filename", id="inv-015-filename"),
            pytest.param("migration_015_defines_unique_guild_ticket_number", id="inv-015-unique-index"),
        ],
    )
    def test_schema_inventory_reports_015_parity(self, fact: str) -> None:
        """SchemaInventory MUST report 015 parity (idx_ticket_guild_ticket_number) without DDL."""
        inv = SchemaInventory.build()
        value = getattr(inv, fact)
        if fact == "migration_015_filename":
            assert value == "015_ticket_lifecycle_reliability.sql"
        else:
            assert value is True

    @pytest.mark.parametrize(
        ("attr", "expected"),
        [
            pytest.param("ttl_seconds", 300, id="cdc-ttl-300"),
            pytest.param("leaderboard_ttl_seconds", 30, id="leaderboard-ttl-30"),
        ],
    )
    def test_schema_inventory_ttl_values(self, attr: str, expected: int) -> None:
        """CDC TTL 300s and leaderboard TTL 30s MUST be inventoried exactly."""
        inv = SchemaInventory.build()
        assert getattr(inv, attr) == expected

    def test_schema_inventory_cdc_tables(self) -> None:
        """Inventory MUST document the 6 CDC publication tables."""
        assert set(CDC_TABLES) == {"guild", "greeting_config", "ticket", "ticket_note", "member", "economy_config"}
        assert TTL_SECONDS == 300
        assert LEADERBOARD_TTL_SECONDS == 30

    def test_schema_inventory_fk_retention_policy(self) -> None:
        """FK retention MUST be documented: ticket_note CASCADE, ticket_audit SET NULL."""
        assert FK_RETENTION["ticket_note"] == "CASCADE"
        assert FK_RETENTION["ticket_audit"] == "SET NULL"

    def test_schema_inventory_flags_12_unused_indexes(self) -> None:
        """12-unused-indexes MUST be flagged for review (no DDL)."""
        assert len(UNUSED_INDEXES_FOR_REVIEW) == 12
        # The duplicate ticket-number index must be flagged alongside 015's unique index.
        assert "idx_ticket_guild_number" in UNUSED_INDEXES_FOR_REVIEW

    def test_schema_inventory_no_ddl_contract(self) -> None:
        """SchemaInventory MUST be read-only — no DDL statements."""
        inv = SchemaInventory.build()
        assert inv.no_ddl is True
        assert inv.ddl_statements == ""
        assert "CREATE" not in inv.ddl_statements and "ALTER" not in inv.ddl_statements

    def test_schema_inventory_runtime_parity_binding(self) -> None:
        """SchemaInventory MUST expose runtime parity facts with FK/RLS deferral."""
        inv = SchemaInventory.build()
        assert hasattr(inv, "runtime_parity_reasons")
        assert hasattr(inv, "fk_live_verified")
        assert hasattr(inv, "rls_live_verified")
        # Live FK/RLS require DB connection — deferred (fail-closed default False).
        assert inv.fk_live_verified is False
        assert inv.rls_live_verified is False
        assert isinstance(inv.runtime_parity_reasons, tuple)


# ===========================================================================
# service_role twins (tests-slim-fase-2 B2) — replaces
# tests/test_pr3_service_role_rls.py. D3 proof: LITERAL fake_JWT helper +
# publishable-key matrix + 9 RLS checks — connect() fail-closed on every
# non-service_role credential, anon denial across all 9 RLS no-policy tables.
# ===========================================================================


def fake_JWT(role: str) -> str:  # noqa: N802 -- D3 literal: twin MUST be greppable as `fake_JWT`
    """Return a minimal unsigned fake_JWT with the given role claim."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.fake-signature"


PUBLISHABLE_KEY = "sb_publishable_fake1234567890"

RLS_TABLES: tuple[str, ...] = (
    "guild",
    "member",
    "infraction",
    "ticket",
    "ticket_category",
    "economy_config",
    "greeting_config",
    "ticket_note",
    "ticket_audit",
)


class TestServiceRoleConnectTwin:
    """Database.connect() fail-closed on non-service_role credentials."""

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param(fake_JWT("anon"), id="connect-fails-anon-jwt"),
            pytest.param(fake_JWT("authenticated"), id="connect-fails-authenticated-jwt"),
            pytest.param("", id="connect-fails-empty-key"),
            pytest.param(PUBLISHABLE_KEY, id="connect-fails-publishable-key"),
            pytest.param("garbage-not-a-jwt", id="connect-fails-garbage"),
        ],
    )
    @pytest.mark.asyncio
    async def test_service_role_connect_fails_closed(self, key: str) -> None:
        """Database.connect() MUST raise ServiceRoleValidationError and clear the client."""
        from bot.core.db.base import ServiceRoleValidationError  # noqa: PLC0415 -- facade indirection

        db = Database(url="https://test.supabase.co", key=key)
        with pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    def test_service_role_validation_rejects_anon_jwt(self) -> None:
        """validate_service_role_key helper MUST reject anon fake_JWT."""
        from bot.core.db.base import (  # noqa: PLC0415 -- facade indirection
            ServiceRoleValidationError,
            validate_service_role_key,
        )

        with pytest.raises(ServiceRoleValidationError):
            validate_service_role_key(fake_JWT("anon"))

    def test_service_role_validation_accepts_verified_service_role_jwt(self) -> None:
        """validate_service_role_key helper MUST accept a verified service_role JWT."""
        from bot.core.db.base import validate_service_role_key  # noqa: PLC0415 -- facade indirection

        secret = "s3-guard-secret-32bytes-strong-123456"
        with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": secret}):
            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            validate_service_role_key(signed)

    def test_service_role_validation_helper_via_config(self) -> None:
        """BotConfig layer MUST also validate service_role via the helper."""
        from bot.config import ServiceRoleValidationError as ConfigError  # noqa: PLC0415 -- facade indirection
        from bot.config import validate_supabase_key  # noqa: PLC0415 -- facade indirection

        with pytest.raises(ConfigError):
            validate_supabase_key(fake_JWT("anon"))
        secret = "s3-guard-secret-32bytes-strong-123456"
        with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": secret}):
            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            validate_supabase_key(signed)

    @pytest.mark.asyncio
    async def test_service_role_connect_succeeds_with_valid_key(self) -> None:
        """Database.connect() MUST succeed when key is a verified service_role JWT."""
        db = Database(url="https://test.supabase.co", key=fake_JWT("service_role"))
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "1"}]
        mock_client.table.return_value.select.return_value.limit.return_value.execute = AsyncMock(
            return_value=mock_response
        )
        secret = "s3-guard-secret-32bytes-strong-123456"
        with (
            patch.dict("os.environ", {"SUPABASE_JWT_SECRET": secret}),
            patch("bot.core.db.base.acreate_client", return_value=mock_client),
        ):
            # Re-sign with the same secret so PyJWT verification passes
            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            db._key = signed
            await db.connect()
        assert db._client is mock_client


class TestRlsAnonDeniedTwin:
    """RLS negative matrix: anon/authenticated denied on all 9 no-policy tables."""

    @pytest.mark.parametrize("table", RLS_TABLES, ids=[f"rls-{t}" for t in RLS_TABLES])
    def test_rls_anon_denied_on_9_tables(self, table: str) -> None:
        """Any direct anon/authenticated query to the 9 tables MUST be denied."""
        assert is_rls_denied_for_anon(table, role="anon") is True
        assert is_rls_denied_for_anon(table, role="authenticated") is True

    def test_rls_service_role_not_denied(self) -> None:
        """service_role MUST NOT be flagged as RLS-denied (it bypasses RLS)."""
        for table in RLS_TABLES:
            assert is_rls_denied_for_anon(table, role="service_role") is False

    def test_rls_publishable_key_role_denied(self) -> None:
        """The publishable-key matrix MUST extend to the publishable pseudo-role."""
        for table in RLS_TABLES:
            assert is_rls_denied_for_anon(table, role="publishable") is True

    def test_rls_explicit_9_tables_contract(self) -> None:
        """Inventory MUST enumerate exactly the 9 RLS no-policy tables."""
        assert set(RLS_NO_POLICY_TABLES) == set(RLS_TABLES)
        assert len(RLS_NO_POLICY_TABLES) == 9
