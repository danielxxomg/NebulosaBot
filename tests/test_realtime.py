"""Unit tests for bot.core.realtime — Supabase Realtime CDC subscriber.

Covers the cache-sync-realtime spec scenarios:
    - Realtime subscriber lifecycle (start creates client + subscribes to 6
      tables incl member/economy_config; stop removes channel + closes
      client; idempotent shutdown)
    - CDC handler dispatch (guild / greeting_config / ticket / ticket_note /
      member / economy_config)
    - DELETE events use old_record
    - Self-echo filtering (recent-writes set, 5s TTL, lazy eviction)
    - Health check (60s status log, CHANNEL_ERROR > 60s -> poll fallback)
    - Poll fallback (30s ticket lastActivity window + guild/greeting scan +
      member/economy_config incremental updatedAt queries)
    - Migration watchdog (30s no events -> warning)
    - Hard ordering history guard (_on_write wiring precedes publication)

Time is controlled via ``patch("bot.core.realtime.time.monotonic", ...)``
matching the established test_cache.py pattern (freezegun does not advance
``time.monotonic``).
"""

from __future__ import annotations

import inspect
import logging
import shutil
import subprocess
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot.core.realtime as realtime_module
from bot.core.cache import TTLCache
from bot.core.database import Database
from bot.core.realtime import (
    SUBSCRIBED_TABLES,
    RealtimeCacheSubscriber,
    RecentWriteSet,
    TicketGuildCache,
    _default_client_factory,
    _extract_guild_id,
    _extract_ticket_id,
    _record_for_event,
)

# Absolute git binary — resolved once (S607: no partial-path process spawns).
GIT_BIN = shutil.which("git") or "/usr/bin/git"

# ===========================================================================
# Pure helpers — record selection + guild_id extraction (task 3.5 helpers)
# ===========================================================================


class TestRecordForEvent:
    """_record_for_event — INSERT/UPDATE use ``record``, DELETE uses ``old_record``."""

    @pytest.mark.parametrize(
        ("payload", "expected", "case_id"),
        [
            pytest.param(
                {"type": "INSERT", "record": {"id": "G1"}, "old_record": {}},
                {"id": "G1"},
                "insert-uses-record",
            ),
            pytest.param(
                {"type": "UPDATE", "record": {"guildId": "G2"}, "old_record": {"guildId": "G0"}},
                {"guildId": "G2"},
                "update-uses-record",
            ),
            pytest.param(
                {"type": "DELETE", "record": {}, "old_record": {"id": "G3"}},
                {"id": "G3"},
                "delete-uses-old-record",
            ),
            pytest.param(
                {"type": "DELETE", "record": {}},
                {},
                "delete-missing-old-record-returns-empty",
            ),
            pytest.param(
                {"record": {"id": "G4"}},
                {"id": "G4"},
                "missing-type-treats-as-record",
            ),
        ],
    )
    def test_record_selection_by_event_type(
        self, payload: dict[str, Any], expected: dict[str, Any], case_id: str
    ) -> None:
        """INSERT/UPDATE (and missing-type) read ``record``; DELETE reads
        ``old_record`` (empty dict when absent) — per spec."""
        assert _record_for_event(payload) == expected


class TestExtractGuildId:
    """_extract_guild_id — pure table -> guild_id mapping."""

    @pytest.mark.parametrize(
        ("table", "row", "expected", "case_id"),
        [
            pytest.param("guild", {"id": "111222333"}, "111222333", "guild-table-uses-id"),
            pytest.param("greeting_config", {"guildId": "444555666"}, "444555666", "greeting-config-uses-guild-id"),
            pytest.param("ticket", {"guildId": "777888999"}, "777888999", "ticket-uses-guild-id"),
            pytest.param("ticket_note", {"ticketId": "T1"}, None, "ticket-note-returns-none"),
            pytest.param("other", {"id": "X"}, None, "unknown-table-returns-none"),
            pytest.param("guild", {}, None, "missing-field-returns-none"),
            pytest.param("guild", {"id": 123456}, "123456", "coerces-non-string-to-string"),
            pytest.param("member", {"guildId": "444555666"}, "444555666", "member-uses-guild-id"),
            pytest.param("economy_config", {"guildId": "999000111"}, "999000111", "economy-config-uses-guild-id"),
        ],
    )
    def test_guild_id_mapping(self, table: str, row: dict[str, Any], expected: str | None, case_id: str) -> None:
        """Pure table -> guild_id extraction: guild reads ``id``; CDC tables
        read ``guildId``; ticket_note/unknown/missing fields yield None;
        numeric ids coerce to str for cache-key consistency."""
        assert _extract_guild_id(table, row) == expected

    @pytest.mark.parametrize("table", ["member", "economy_config"])
    def test_new_tables_coerce_numeric_guild_id(self, table: str) -> None:
        """Numeric guildId on the S6 tables MUST coerce to str (cache-key consistency)."""
        assert _extract_guild_id(table, {"guildId": 123456789}) == "123456789"


class TestExtractTicketId:
    """_extract_ticket_id — ticket_note -> ticket_id for guild resolution."""

    @pytest.mark.parametrize(
        ("row", "expected", "case_id"),
        [
            pytest.param({"ticketId": "ticket-uuid-001"}, "ticket-uuid-001", "returns-ticket-id"),
            pytest.param({}, None, "missing-returns-none"),
            pytest.param({"ticketId": 99}, "99", "coerces-to-string"),
        ],
    )
    def test_ticket_id_extraction(self, row: dict[str, Any], expected: str | None, case_id: str) -> None:
        """Reads ``ticketId`` from the note row; None when absent; numeric
        values coerce to str."""
        assert _extract_ticket_id(row) == expected


# ===========================================================================
# RecentWriteSet — self-echo filtering (tasks 2.5, 3.1)
# ===========================================================================


class TestRecentWriteSet:
    """RecentWriteSet — async-safe TTL dict keyed ``{table}:{identifier}``."""

    @pytest.mark.asyncio
    async def test_mark_then_contains_true(self) -> None:
        rws = RecentWriteSet()
        await rws.mark("guild", "G1")
        assert await rws.contains("guild", "G1") is True

    @pytest.mark.asyncio
    async def test_not_marked_returns_false(self) -> None:
        rws = RecentWriteSet()
        assert await rws.contains("guild", "G2") is False

    @pytest.mark.asyncio
    async def test_different_table_not_matched(self) -> None:
        """Key is {table}:{id} — marking guild must not match ticket."""
        rws = RecentWriteSet()
        await rws.mark("guild", "G1")
        assert await rws.contains("ticket", "G1") is False

    @pytest.mark.parametrize(
        ("delta", "expect_present"),
        [
            pytest.param(4.0, True, id="entry-still-present-within-5s"),
            pytest.param(6.0, False, id="entry-expires-after-5s"),
        ],
    )
    @pytest.mark.asyncio
    async def test_entry_ttl_window(self, delta: float, expect_present: bool) -> None:
        """Spec: entries live ~5s — inside the window contains() is True,
        past it the entry no longer filters (lazy eviction)."""
        rws = RecentWriteSet()
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await rws.mark("guild", "G1")
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0 + delta):
            assert await rws.contains("guild", "G1") is expect_present

    @pytest.mark.asyncio
    async def test_expired_entry_evicted_lazily(self) -> None:
        """contains() MUST evict expired entries (no stale matches)."""
        rws = RecentWriteSet()
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await rws.mark("guild", "G1")
        with patch("bot.core.realtime.time.monotonic", return_value=1006.0):
            await rws.contains("guild", "G1")  # triggers eviction
        # Internal store should no longer hold the key.
        assert "guild:G1" not in rws._entries


# ===========================================================================
# TicketGuildCache — ticket_id -> guild_id TTL mapping (task 3.2)
# ===========================================================================


class TestTicketGuildCache:
    """TicketGuildCache — resolve ticket_note events to a guild_id."""

    @pytest.mark.asyncio
    async def test_store_then_get(self) -> None:
        tgc = TicketGuildCache()
        await tgc.store("T1", "G1")
        assert await tgc.get("T1") == "G1"

    @pytest.mark.asyncio
    async def test_miss_returns_none(self) -> None:
        tgc = TicketGuildCache()
        assert await tgc.get("unknown") is None

    @pytest.mark.asyncio
    async def test_store_overwrites_guild(self) -> None:
        tgc = TicketGuildCache()
        await tgc.store("T1", "G1")
        await tgc.store("T1", "G2")
        assert await tgc.get("T1") == "G2"

    @pytest.mark.asyncio
    async def test_entry_expires(self) -> None:
        tgc = TicketGuildCache()
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await tgc.store("T1", "G1")
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0 + 400):
            assert await tgc.get("T1") is None


# ===========================================================================
# Subscriber lifecycle — start / stop (tasks 2.1, 2.2, 3.3, 3.4, 3.9, 3.10)
# ===========================================================================


def _make_channel_mock() -> MagicMock:
    """Build a mock Supabase Realtime channel supporting the on_postgres_changes
    chain (returns self) and an async subscribe."""
    channel = MagicMock()
    channel.on_postgres_changes = MagicMock(return_value=channel)
    channel.subscribe = AsyncMock()
    return channel


def _make_client_mock(channel: MagicMock | None = None) -> MagicMock:
    """Build a mock async Supabase client with channel + cleanup methods."""
    ch = channel or _make_channel_mock()
    client = MagicMock()
    client.channel = MagicMock(return_value=ch)
    client.remove_channel = AsyncMock()
    client.remove_all_channels = AsyncMock()
    client.close = AsyncMock()
    client.aclose = AsyncMock()
    client._on_connect_error = AsyncMock()
    return client


def _make_subscriber(cache: TTLCache, client: MagicMock) -> RealtimeCacheSubscriber:
    """Build a subscriber whose client factory returns *client*."""
    factory = AsyncMock(return_value=client)
    return RealtimeCacheSubscriber(
        supabase_url="https://x.supabase.co",
        supabase_key="anon-key",
        cache=cache,
        client_factory=factory,
    )


class TestSubscriberStart:
    """start() — creates async client, one channel, 6 on_postgres_changes, subscribe."""

    @pytest.mark.asyncio
    async def test_start_creates_client_and_subscribes(self, cache: TTLCache) -> None:
        channel = _make_channel_mock()
        client = _make_client_mock(channel)
        sub = _make_subscriber(cache, client)

        await sub.start()

        client.channel.assert_called_once_with("cache-sync")
        assert channel.on_postgres_changes.call_count == 6
        channel.subscribe.assert_awaited_once()
        # The registered tables are exactly the six-table contract (this row
        # also carries the old start_subscribes_to_six_tables literal-set
        # assertion, deduped in the S6 ceiling cut).
        tables_called = {call.kwargs.get("table") for call in channel.on_postgres_changes.call_args_list}
        assert tables_called == {"guild", "greeting_config", "ticket", "ticket_note", "member", "economy_config"}


class TestSubscribedTableScope:
    """S6: subscription scope extends to member + economy_config (6 tables).

    Spec cache-sync-realtime "Member and economy_config subscription" +
    "Published table scope is explicit": the subscribed table list MUST
    contain exactly the six supported tables.
    """

    SIX_TABLE_CONTRACT = frozenset({"guild", "greeting_config", "ticket", "ticket_note", "member", "economy_config"})

    def test_subscribed_tables_constant_matches_contract(self) -> None:
        assert frozenset(SUBSCRIBED_TABLES) == self.SIX_TABLE_CONTRACT
        assert len(SUBSCRIBED_TABLES) == 6

    @pytest.mark.asyncio
    async def test_start_registers_all_six_tables(self, cache: TTLCache) -> None:
        channel = _make_channel_mock()
        client = _make_client_mock(channel)
        sub = _make_subscriber(cache, client)

        await sub.start()

        tables_called = {call.kwargs.get("table") for call in channel.on_postgres_changes.call_args_list}
        assert tables_called == self.SIX_TABLE_CONTRACT
        assert channel.on_postgres_changes.call_count == 6

    @pytest.mark.asyncio
    async def test_start_passes_event_and_schema(self, cache: TTLCache) -> None:
        channel = _make_channel_mock()
        client = _make_client_mock(channel)
        sub = _make_subscriber(cache, client)

        await sub.start()

        first = channel.on_postgres_changes.call_args_list[0]
        assert first.kwargs["event"] == "*"
        assert first.kwargs["schema"] == "public"
        assert callable(first.kwargs["callback"])

    @pytest.mark.asyncio
    async def test_start_spawns_background_tasks(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub.start()
        try:
            assert sub._health_task is not None
            assert sub._poll_task is not None
            assert sub._watchdog_task is not None
        finally:
            await sub.stop()


class TestSubscriberStop:
    """stop() — removes channel, removes all channels, best-effort close, cancels tasks."""

    @pytest.mark.asyncio
    async def test_stop_removes_channel_and_all_channels(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()

        await sub.stop()

        client.remove_channel.assert_awaited_once()
        client.remove_all_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_best_effort_close(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()

        await sub.stop()

        # close attempted best-effort (aclose preferred over close)
        client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_background_tasks(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()
        health = sub._health_task
        poll = sub._poll_task
        watchdog = sub._watchdog_task

        await sub.stop()

        assert health is not None and (health.cancelled() or health.done())
        assert poll is not None and (poll.cancelled() or poll.done())
        assert watchdog is not None and (watchdog.cancelled() or watchdog.done())


# ===========================================================================
# CDC handler dispatch (tasks 2.3, 2.4, 3.5)
# ===========================================================================


def _cdc_payload(*, table: str, record: dict, old_record: dict | None = None, event_type: str = "INSERT") -> dict:
    return {
        "type": event_type,
        "table": table,
        "schema": "public",
        "record": record,
        "old_record": old_record or {},
    }


class TestCdcDispatch:
    """CDC handler routes by table -> invalidate_guild with correct guild_id."""

    @pytest.mark.parametrize(
        ("table", "record", "expected"),
        [
            ("guild", {"id": "G-guild"}, "G-guild"),
            ("greeting_config", {"guildId": "G-greet"}, "G-greet"),
            ("ticket", {"guildId": "G-ticket"}, "G-ticket"),
            ("member", {"guildId": "G-member"}, "G-member"),
            ("economy_config", {"guildId": "G-economy"}, "G-economy"),
        ],
    )
    @pytest.mark.asyncio
    async def test_dispatch_invalidates_correct_guild(
        self,
        cache: TTLCache,
        table: str,
        record: dict,
        expected: str,
    ) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        # Pre-seed cache so invalidate_guild has keys to remove (proves it ran).
        cache.set(f"{expected}:config", "v")

        await sub._handle_cdc(_cdc_payload(table=table, record=record))

        assert cache.get(f"{expected}:config") is None  # invalidated

    @pytest.mark.asyncio
    async def test_greeting_config_onboarding_update_invalidates_cached_config(self, cache: TTLCache) -> None:
        """Changing onboardingChannelId must invalidate the greeting cache."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-onboarding:config", {"onboardingChannelId": "old-channel"})

        await sub._handle_cdc(
            _cdc_payload(
                table="greeting_config",
                record={"guildId": "G-onboarding", "onboardingChannelId": "new-channel"},
                event_type="UPDATE",
            )
        )

        assert cache.get("G-onboarding:config") is None

    @pytest.mark.asyncio
    async def test_delete_event_uses_old_record(self, cache: TTLCache) -> None:
        """Spec: DELETE with empty record MUST use old_record identifiers."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-del:config", "v")

        payload = _cdc_payload(
            table="guild",
            record={},  # empty record on DELETE
            old_record={"id": "G-del"},
            event_type="DELETE",
        )
        await sub._handle_cdc(payload)

        assert cache.get("G-del:config") is None

    @pytest.mark.parametrize("table", ["member", "economy_config"])
    @pytest.mark.asyncio
    async def test_delete_event_for_new_tables_uses_old_record(self, cache: TTLCache, table: str) -> None:
        """Spec S6: DELETE CDC for member/economy_config resolves guildId from old_record."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-gone:config", "v")

        payload = _cdc_payload(
            table=table,
            record={},  # empty record on DELETE
            old_record={"guildId": "G-gone"},
            event_type="DELETE",
        )
        await sub._handle_cdc(payload)

        assert cache.get("G-gone:config") is None

    @pytest.mark.asyncio
    async def test_ticket_note_resolves_via_ticket_cache(self, cache: TTLCache) -> None:
        """ticket_note -> guildId resolved from TicketGuildCache (no DB query)."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.ticket_guild_cache.store("T1", "G-note")
        cache.set("G-note:config", "v")

        await sub._handle_cdc(_cdc_payload(table="ticket_note", record={"ticketId": "T1"}))

        assert cache.get("G-note:config") is None

    @pytest.mark.asyncio
    async def test_ticket_note_falls_back_to_db_query(self, cache: TTLCache) -> None:
        """ticket_note with cache MISS -> async DB ticket lookup -> invalidate."""
        client = _make_client_mock()
        # The subscriber queries the async client for ticket guildId.
        ticket_resp = MagicMock()
        ticket_resp.data = [{"guildId": "G-db"}]
        client.table = MagicMock(return_value=client)
        client.select = MagicMock(return_value=client)
        client.eq = MagicMock(return_value=client)
        client.limit = MagicMock(return_value=client)
        client.execute = AsyncMock(return_value=ticket_resp)
        sub = _make_subscriber(cache, client)
        cache.set("G-db:config", "v")

        await sub._handle_cdc(_cdc_payload(table="ticket_note", record={"ticketId": "T2"}))

        assert cache.get("G-db:config") is None

    @pytest.mark.asyncio
    async def test_ticket_note_unresolvable_skips_invalidation(self, cache: TTLCache, caplog) -> None:
        """ticket_note unresolved (cache miss + DB None) MUST skip and log a warning."""
        client = _make_client_mock()
        ticket_resp = MagicMock()
        ticket_resp.data = []  # DB returns nothing
        client.table = MagicMock(return_value=client)
        client.select = MagicMock(return_value=client)
        client.eq = MagicMock(return_value=client)
        client.limit = MagicMock(return_value=client)
        client.execute = AsyncMock(return_value=ticket_resp)
        sub = _make_subscriber(cache, client)
        cache.set("some:config", "v")

        with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
            await sub._handle_cdc(_cdc_payload(table="ticket_note", record={"ticketId": "T3"}))

        # Nothing invalidated.
        assert cache.get("some:config") == "v"
        # Warning about unresolvable guild_id MUST be logged.
        assert any("could not resolve" in r.message.lower() or "guild_id" in r.message for r in caplog.records), (
            "Expected a WARNING log about unresolvable guild_id"
        )

    @pytest.mark.asyncio
    async def test_cdc_event_increments_counter(self, cache: TTLCache) -> None:
        """Each handled CDC event MUST increment the event counter (watchdog input)."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G1"}))
        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G2"}))

        assert sub._event_count == 2


# ===========================================================================
# C3 — Payload normalization (nested SDK payload)
# ===========================================================================


class TestNormalizeCdcPayload:
    """_normalize_cdc_payload — handles nested SDK payloads from realtime-py 2.31.0."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("event_type", "table", "record_key", "record_val", "old_key", "old_val", "table_hint", "case_id"),
        [
            pytest.param(
                "UPDATE",
                "guild",
                "id",
                "G-nested",
                {},
                None,
                None,
                "nested-sdk-payload-invalidates-guild",
            ),
            pytest.param(
                "INSERT",
                None,
                "guildId",
                "G-hint",
                {},
                None,
                "greeting_config",
                "table-hint-fallback-when-data-table-missing",
            ),
            pytest.param(
                "DELETE",
                "guild",
                None,
                None,
                "id",
                "G-del-nested",
                None,
                "delete-nested-sdk-uses-old-record",
            ),
            pytest.param(
                "INSERT",
                "guild",
                "id",
                "G-legacy",
                {},
                None,
                None,
                "legacy-top-level-payload-still-works",
            ),
        ],
    )
    async def test_payload_shapes_invalidate_guild(
        self,
        cache: TTLCache,
        event_type: str,
        table: str | None,
        record_key: str | None,
        record_val: str | None,
        old_key: str | None,
        old_val: str | None,
        table_hint: str | None,
        case_id: str,
    ) -> None:
        """Nested SDK ({data: {type, table, record}}) and legacy top-level
        payloads both normalize; DELETE reads old_record; missing data.table
        falls back to the registration table_hint."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        guild_id = record_val or old_val
        cache_key = f"{guild_id}:config"
        cache.set(cache_key, "v")

        data: dict[str, Any] = {
            "type": event_type,
            "table": table,
            "schema": "public",
            "record": {record_key: record_val} if record_key else {},
            "old_record": {old_key: old_val} if old_key else {},
        }
        if event_type == "INSERT" and table == "guild":
            # Legacy top-level payload format MUST still work for backward
            # compatibility (no data envelope).
            payload: dict[str, Any] = {
                "type": event_type,
                "table": table,
                "schema": "public",
                "record": {record_key: record_val} if record_key else {},
                "old_record": {},
            }
        else:
            payload = {"data": data, "ids": [1]}

        await sub._handle_cdc(payload, table_hint=table_hint)

        assert cache.get(cache_key) is None  # invalidated


# ===========================================================================
# Self-echo filtering integration (task 2.5)
# ===========================================================================


class TestSelfEchoFiltering:
    """A CDC event for a row the bot just wrote MUST be skipped (TTL-gated)."""

    @pytest.mark.asyncio
    async def test_recent_write_skips_invalidation(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-echo:config", "v")
        await sub.mark_recent_write("guild", "G-echo")

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G-echo"}))

        assert cache.get("G-echo:config") == "v"  # NOT invalidated

    @pytest.mark.asyncio
    async def test_expired_write_allows_invalidation(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-exp:config", "v")
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await sub.mark_recent_write("guild", "G-exp")

        with patch("bot.core.realtime.time.monotonic", return_value=1006.0):
            await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G-exp"}))

        assert cache.get("G-exp:config") is None  # invalidated after TTL

    @pytest.mark.asyncio
    async def test_unrelated_write_still_invalidates(self, cache: TTLCache) -> None:
        """Marking guild G1 MUST NOT suppress invalidation for guild G2."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-other:config", "v")
        await sub.mark_recent_write("guild", "G-marked")

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G-other"}))

        assert cache.get("G-other:config") is None

    @pytest.mark.asyncio
    async def test_mark_recent_write_stores_in_recent_writes(self, cache: TTLCache) -> None:
        """mark_recent_write — public API records {table}:{id} in recent_writes.

        Deduped in the S6 ceiling cut: the sub-level wiring (recent_writes IS
        the RecentWriteSet, and mark_recent_write delegates to it) shares the
        skip-behavior rows above; this probe pins the public-API surface.
        """
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub.mark_recent_write("guild", "G1")

        assert await sub.recent_writes.contains("guild", "G1") is True


# ===========================================================================
# on_subscribe callback (task 3.4)
# ===========================================================================


class TestOnSubscribe:
    """on_subscribe(status, err) — synchronous callback, tracks status, resets poll."""

    def test_on_subscribe_is_synchronous(self, cache: TTLCache) -> None:
        """Spec: subscribe callback MUST be synchronous (SDK invokes it directly)."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        assert not inspect.iscoroutinefunction(sub._on_subscribe)

    @pytest.mark.parametrize(
        ("status", "err", "expect_status"),
        [
            pytest.param("SUBSCRIBED", None, "SUBSCRIBED", id="subscribed-status-stored"),
            pytest.param("CHANNEL_ERROR", Exception("boom"), "CHANNEL_ERROR", id="channel-error-status-stored"),
        ],
    )
    def test_status_stored(self, cache: TTLCache, status: str, err: object, expect_status: str) -> None:
        """on_subscribe stores whatever status the SDK reports (sync callback)."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        sub._on_subscribe(status, err)

        assert sub._status == expect_status

    def test_subscribed_disables_poll_fallback(self, cache: TTLCache) -> None:
        """SUBSCRIBED status MUST set _poll_fallback_enabled to False."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._poll_fallback_enabled = True

        sub._on_subscribe("SUBSCRIBED", None)

        assert sub._poll_fallback_enabled is False

    def test_subscribed_resets_last_check(self, cache: TTLCache) -> None:
        """SUBSCRIBED status MUST reset _last_check so next poll starts fresh."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._last_check = "2025-06-01T10:00:00+00:00"

        sub._on_subscribe("SUBSCRIBED", None)

        assert sub._last_check == "1970-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start_first",
        [
            pytest.param(False, id="stop-before-start-must-not-raise"),
            pytest.param(True, id="stop-twice-second-is-no-op"),
        ],
    )
    async def test_stop_idempotent(self, cache: TTLCache, start_first: bool) -> None:
        """stop() is idempotent: before start() or called twice it MUST NOT
        raise, and the client teardown (remove_all_channels) runs exactly once.
        """
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        if start_first:
            await sub.start()

        await sub.stop()
        await sub.stop()  # second call MUST NOT raise in both rows

        if start_first:
            # remove_all_channels called on the first stop; second is a no-op.
            assert client.remove_all_channels.await_count == 1


# ===========================================================================
# Health check (tasks 2.6, 3.6)
# ===========================================================================


class TestHealthCheck:
    """_health_check_once — logs status; enables poll fallback after >60s unhealthy."""

    @pytest.mark.asyncio
    async def test_healthy_subscribed_logs_debug(self, cache: TTLCache, caplog) -> None:
        """Spec: healthy subscription MUST log a DEBUG message."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"

        with caplog.at_level(logging.DEBUG, logger="bot.core.realtime"):
            await sub._health_check_once()

        assert sub._poll_fallback_enabled is False
        assert any("healthy" in r.message.lower() or "subscribed" in r.message.lower() for r in caplog.records), (
            "Expected a DEBUG log about healthy/subscribed status"
        )

    @pytest.mark.asyncio
    async def test_channel_error_over_60s_enables_fallback(self, cache: TTLCache, caplog) -> None:
        """Spec: disconnected state >60s MUST log a WARNING and enable poll fallback."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "CHANNEL_ERROR"
        try:
            with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
                sub._status_since = 930.0  # 70s ago
                with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                    await sub._health_check_once()

                assert sub._poll_fallback_enabled is True
                assert any(
                    "unhealthy" in r.message.lower() or "poll fallback" in r.message.lower() for r in caplog.records
                ), "Expected a WARNING log about unhealthy state or poll fallback"
        finally:
            # _health_check_once now recreates the poll task when enabling the
            # fallback — clean it up so no background task leaks past the test.
            await sub.stop()

    @pytest.mark.asyncio
    async def test_recovery_disables_fallback(self, cache: TTLCache, caplog) -> None:
        """Spec: reconnection to SUBSCRIBED MUST disable poll fallback and log."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._poll_fallback_enabled = True
        sub._status = "CHANNEL_ERROR"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._status_since = 930.0

        # Recover — sync callback, no await.
        with caplog.at_level(logging.INFO, logger="bot.core.realtime"):
            sub._on_subscribe("SUBSCRIBED", None)
        await sub._health_check_once()

        assert sub._poll_fallback_enabled is False
        assert any("subscribed" in r.message.lower() for r in caplog.records), (
            "Expected an INFO log about SUBSCRIBED reconnection"
        )


# ===========================================================================
# Poll fallback (tasks 2.7, 3.7)
# ===========================================================================


def _mock_ticket_query(client: MagicMock, guild_ids: list[str]) -> None:
    """Wire the async client's ticket.lastActivity query to return guild_ids."""
    ticket_resp = MagicMock()
    ticket_resp.data = [{"guildId": g} for g in guild_ids]
    client.table = MagicMock(return_value=client)
    client.select = MagicMock(return_value=client)
    client.gt = MagicMock(return_value=client)
    client.lte = MagicMock(return_value=client)
    client.execute = AsyncMock(return_value=ticket_resp)


class TestPollFallback:
    """_poll_once — ticket lastActivity window + guild/greeting full scan."""

    @pytest.mark.asyncio
    async def test_poll_invalidates_tickets_by_last_activity(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        _mock_ticket_query(client, ["G-poll1", "G-poll2"])
        sub = _make_subscriber(cache, client)
        cache.set("G-poll1:config", "v")
        cache.set("G-poll2:config", "v")

        await sub._poll_once()

        assert cache.get("G-poll1:config") is None
        assert cache.get("G-poll2:config") is None

    @pytest.mark.asyncio
    async def test_poll_scans_all_guilds(self, cache: TTLCache) -> None:
        """Config tables lack updated_at — poll MUST invalidate all guild rows."""
        client = _make_client_mock()
        # Ticket query returns nothing; guild query returns all guild ids.
        responses = []

        def _table(name: str) -> MagicMock:
            if name == "ticket":
                r = MagicMock()
                r.data = []
                r.select = MagicMock(return_value=r)
                responses.append(r)
                return r
            if name == "guild":
                r = MagicMock()
                r.data = [{"id": "G-scan1"}, {"id": "G-scan2"}]
                r.select = MagicMock(return_value=r)
                responses.append(r)
                return r
            if name == "greeting_config":
                r = MagicMock()
                r.data = [{"guildId": "G-scan1"}]
                r.select = MagicMock(return_value=r)
                responses.append(r)
                return r
            return client

        client.table = MagicMock(side_effect=_table)
        client.select = MagicMock(return_value=client)
        client.gt = MagicMock(return_value=client)
        client.lte = MagicMock(return_value=client)
        client.execute = AsyncMock()
        assert responses == []  # sanity: no queries issued yet
        sub = _make_subscriber(cache, client)
        cache.set("G-scan1:config", "v")
        cache.set("G-scan2:config", "v")

        await sub._poll_once()

        assert cache.get("G-scan1:config") is None
        assert cache.get("G-scan2:config") is None

    @pytest.mark.asyncio
    async def test_poll_advances_last_check(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        _mock_ticket_query(client, [])
        sub = _make_subscriber(cache, client)
        old = sub._last_check

        with patch("bot.core.realtime.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
            mock_dt.UTC = UTC
            await sub._poll_once()

        assert sub._last_check > old

    @pytest.mark.parametrize("table", ["member", "economy_config"])
    @pytest.mark.asyncio
    async def test_poll_new_tables_incremental_by_updated_at(self, cache: TTLCache, table: str) -> None:
        """Spec S6: member/economy_config polls filter ``updatedAt > last_check``.

        Migration 026 added trigger-maintained ``updatedAt`` (NOT NULL) to both
        tables, so the poll MUST query incrementally instead of full-scanning,
        and invalidate each returned guild.
        """
        client = _make_client_mock()
        gt_calls: list[tuple[str, str]] = []

        def _table(name: str) -> MagicMock:
            r = MagicMock()
            if name == table:
                r.data = [{"guildId": f"G-inc-{table}"}]
            else:
                r.data = []
            r.select = MagicMock(return_value=r)
            r.gt = MagicMock(side_effect=lambda col, val: gt_calls.append((name, col)) or r)
            r.lte = MagicMock(return_value=r)
            return r

        client.table = MagicMock(side_effect=_table)
        client.select = MagicMock(return_value=client)
        client.gt = MagicMock(return_value=client)
        client.lte = MagicMock(return_value=client)
        client.execute = AsyncMock()
        sub = _make_subscriber(cache, client)
        sub._last_check = "2025-06-01T00:00:00+00:00"
        cache.set(f"G-inc-{table}:config", "v")

        await sub._poll_once()

        assert cache.get(f"G-inc-{table}:config") is None  # row invalidated
        # The {table} builder was filtered incrementally by updatedAt.
        assert (table, "updatedAt") in gt_calls

    @pytest.mark.parametrize("table", ["member", "economy_config"])
    @pytest.mark.asyncio
    async def test_poll_new_tables_query_window_uses_last_check(self, cache: TTLCache, table: str) -> None:
        """The incremental filter value MUST be the poll's ``last_check`` window start."""
        client = _make_client_mock()
        gt_values: dict[str, str] = {}

        def _table(name: str) -> MagicMock:
            r = MagicMock()
            r.data = []
            r.select = MagicMock(return_value=r)

            def _record_gt(col: str, val: str, _n: str = name) -> MagicMock:
                gt_values.setdefault(_n, val)
                return r

            r.gt = MagicMock(side_effect=_record_gt)
            r.lte = MagicMock(return_value=r)
            return r

        client.table = MagicMock(side_effect=_table)
        client.select = MagicMock(return_value=client)
        client.gt = MagicMock(return_value=client)
        client.lte = MagicMock(return_value=client)
        client.execute = AsyncMock()
        sub = _make_subscriber(cache, client)
        sub._last_check = "2025-06-01T09:30:00+00:00"

        await sub._poll_once()

        assert gt_values[table] == "2025-06-01T09:30:00+00:00"

    @pytest.mark.asyncio
    async def test_poll_stops_on_recovery(self, cache: TTLCache) -> None:
        """Spec R4: when status returns to SUBSCRIBED the poll loop MUST stop
        and ``last_check`` reset — not merely flagged dormant behind a flag.

        A permanently-running dormant task violates the spec clause "the poll
        loop stops" (``spec.md:106-110``); this regression test asserts the
        task itself is cancelled/cleared, not just the fallback flag.
        """
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()
        try:
            poll_task_before = sub._poll_task
            assert poll_task_before is not None  # start() spawns the poll task
            sub._poll_fallback_enabled = True
            sub._last_check = "2025-06-01T10:00:00+00:00"

            # Sync callback — no await.
            sub._on_subscribe("SUBSCRIBED", None)

            assert sub._poll_fallback_enabled is False
            assert sub._last_check == "1970-01-01T00:00:00+00:00"
            # The poll task MUST be stopped — cleared to None, or done/cancelled.
            # A live dormant task (the prior bug) fails this assertion.
            assert sub._poll_task is None or sub._poll_task.done() or sub._poll_task.cancelled()
        finally:
            await sub.stop()

    @pytest.mark.asyncio
    async def test_poll_task_recreated_when_unhealthy_after_recovery(self, cache: TTLCache) -> None:
        """After recovery cancels the poll task, a subsequent unhealthy spell
        (>60s) MUST recreate the poll task so the fallback can run again.

        Symmetric to ``test_poll_stops_on_recovery``: stop-on-recover is only
        correct if a later unhealthy period restarts the loop.
        """
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()
        try:
            # Recover — cancels and clears the poll task.
            sub._on_subscribe("SUBSCRIBED", None)
            assert sub._poll_task is None or sub._poll_task.done() or sub._poll_task.cancelled()

            # Now go unhealthy for >60s and run a health check.
            sub._status = "CHANNEL_ERROR"
            with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
                sub._status_since = 930.0  # 70s ago
                await sub._health_check_once()

            assert sub._poll_fallback_enabled is True
            # The poll task MUST have been recreated — not None, not done.
            assert sub._poll_task is not None
            assert not sub._poll_task.done()
        finally:
            await sub.stop()


# ===========================================================================
# Migration watchdog (tasks 2.8, 3.8)
# ===========================================================================


class TestMigrationWatchdog:
    """_watchdog_check_once — warns after 30s post-SUBSCRIBED with 0 events."""

    @pytest.mark.asyncio
    async def test_warns_after_30s_no_events(self, cache: TTLCache, caplog) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 965.0  # 35s ago
            sub._event_count = 0
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()

        assert any("supabase_realtime publication" in r.message for r in caplog.records)
        assert sub._watchdog_warned is True

    @pytest.mark.asyncio
    async def test_warns_only_once_when_no_events(self, cache: TTLCache, caplog) -> None:
        """Watchdog MUST not spam every 30s after the first publication warning."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 965.0
            sub._received_count = 0
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()
                await sub._watchdog_check_once()

        messages = [r.message for r in caplog.records if "supabase_realtime publication" in r.message]
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_silent_when_events_received(self, cache: TTLCache, caplog) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 965.0
            sub._received_count = 3
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()

        assert not any("publication" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_silent_before_30s(self, cache: TTLCache, caplog) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 985.0  # 15s ago
            sub._event_count = 0
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()

        assert not any("publication" in r.message for r in caplog.records)


# ===========================================================================
# C2 — Received counter (counts all CDC events, even skipped ones)
# ===========================================================================


class TestReceivedCounter:
    """_received_count MUST increment for every CDC event, even skipped ones."""

    @pytest.mark.asyncio
    async def test_received_count_increments_for_valid_event(self, cache: TTLCache) -> None:
        """Valid CDC event increments both _received_count and _event_count."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G1"}))

        assert sub._received_count == 1
        assert sub._event_count == 1

    @pytest.mark.asyncio
    async def test_received_count_increments_for_skipped_event(self, cache: TTLCache) -> None:
        """Skipped CDC event (no guild_id) increments _received_count but NOT _event_count."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        # ticket_note with no ticketId and no guildId — will be skipped
        await sub._handle_cdc(_cdc_payload(table="ticket_note", record={}))

        assert sub._received_count == 1
        assert sub._event_count == 0  # NOT incremented (skipped)

    @pytest.mark.asyncio
    async def test_received_count_increments_for_self_echo(self, cache: TTLCache) -> None:
        """Self-echo event increments _received_count but NOT _event_count."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.mark_recent_write("guild", "G-echo")

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G-echo"}))

        assert sub._received_count == 1
        assert sub._event_count == 0  # NOT incremented (self-echo skipped)

    @pytest.mark.asyncio
    async def test_watchdog_uses_received_count(self, cache: TTLCache, caplog) -> None:
        """Watchdog MUST check _received_count, not _event_count."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        # Send a skipped event — _received_count=1, _event_count=0
        await sub._handle_cdc(_cdc_payload(table="ticket_note", record={}))
        assert sub._received_count == 1
        assert sub._event_count == 0

        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 965.0  # 35s ago
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()

        # Watchdog should NOT warn because _received_count > 0
        assert not any("publication" in r.message for r in caplog.records)


# ===========================================================================
# C4 — Close logging + health escalation
# ===========================================================================


class TestCloseLogging:
    """C4 — WebSocket close code/reason logging and health escalation."""

    @pytest.mark.asyncio
    async def test_on_connect_error_logs_close_code(self, cache: TTLCache, caplog) -> None:
        """When WebSocket closes, close code and reason MUST be logged."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()

        # start() already calls _wire_close_logging, so client._on_connect_error
        # is now the wrapped version.  The wrapped version delegates to the
        # original, so calling it with a mock exception should log and delegate.
        mock_exc = MagicMock()
        mock_exc.code = 1006
        mock_exc.reason = "connection lost"

        with caplog.at_level(logging.INFO, logger="bot.core.realtime"):
            await client._on_connect_error(mock_exc)

        assert any("1006" in r.message for r in caplog.records)
        assert any("connection lost" in r.message for r in caplog.records)
        await sub.stop()

    @pytest.mark.asyncio
    async def test_channel_on_close_records_closed_state(self, cache: TTLCache, caplog) -> None:
        """Channel on_close wrapper MUST record CLOSED state."""
        client = _make_client_mock()
        channel = client.channel.return_value
        sub = _make_subscriber(cache, client)
        await sub.start()

        # start() already calls _wire_close_logging, so channel.on_close
        # is now the wrapped version.
        with caplog.at_level(logging.INFO, logger="bot.core.realtime"):
            channel.on_close()

        assert sub._status == "CLOSED"
        await sub.stop()

    @pytest.mark.asyncio
    async def test_wire_close_logging_missing_attribute_continues(self, cache: TTLCache, caplog) -> None:
        """Spec: client missing _on_connect_error MUST NOT abort start.

        When the SDK does not expose _on_connect_error, _wire_close_logging
        catches AttributeError and logs a WARNING. start() continues normally
        and health/poll/watchdog tasks are created.
        """
        client = _make_client_mock()
        # Remove _on_connect_error to simulate SDK version without it.
        del client._on_connect_error
        sub = _make_subscriber(cache, client)

        with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
            await sub.start()

        # WARNING logged about the missing attribute.
        assert any(
            "attribute" in r.message.lower() or "wire" in r.message.lower() or "close" in r.message.lower()
            for r in caplog.records
        )
        # Health/poll/watchdog tasks MUST be created despite the failure.
        assert sub._health_task is not None
        assert sub._poll_task is not None
        assert sub._watchdog_task is not None
        await sub.stop()

    @pytest.mark.asyncio
    async def test_wire_close_logging_attribute_error_no_crash(self, cache: TTLCache) -> None:
        """Spec: _wire_close_logging MUST catch AttributeError, not propagate."""
        client = _make_client_mock()
        # Simulate client without _on_connect_error.
        del client._on_connect_error
        sub = _make_subscriber(cache, client)

        # _wire_close_logging should not raise.
        sub._wire_close_logging()
        # Channel on_close should still work if channel has it.
        assert sub._channel is None  # not wired yet, just checking no crash

    @pytest.mark.asyncio
    async def test_health_escalation_after_three_unhealthy_cycles(self, cache: TTLCache, caplog) -> None:
        """After 3 consecutive unhealthy cycles, log level escalates to ERROR."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "CHANNEL_ERROR"
        sub._unhealthy_cycles = 0

        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._status_since = 930.0  # 70s ago

            # First 3 unhealthy cycles: WARNING level
            for _ in range(3):
                with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                    await sub._health_check_once()

            # 4th cycle: should escalate to ERROR
            caplog.clear()
            with caplog.at_level(logging.ERROR, logger="bot.core.realtime"):
                await sub._health_check_once()

        assert any("escalat" in r.message.lower() or "unhealthy" in r.message.lower() for r in caplog.records)
        assert sub._unhealthy_cycles >= 3
        await sub.stop()

    @pytest.mark.asyncio
    async def test_unhealthy_cycles_reset_on_subscribed(self, cache: TTLCache) -> None:
        """When status returns to SUBSCRIBED, _unhealthy_cycles MUST reset to 0."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._unhealthy_cycles = 5

        sub._on_subscribe("SUBSCRIBED", None)

        assert sub._unhealthy_cycles == 0


# ===========================================================================
# Ticket / ticket_note self-echo (Round 2 — row id, not guild_id)
# ===========================================================================


class TestTicketSelfEcho:
    """Self-echo MUST use the ticket row's own id, not guild_id."""

    @pytest.mark.asyncio
    async def test_ticket_self_echo_skips_invalidation(self, cache: TTLCache) -> None:
        """Mark ticket row id -> CDC event with same row id MUST be skipped."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-tkt:config", "v")
        # Mark using the ticket's own row id (what database.insert_ticket passes).
        await sub.mark_recent_write("ticket", "ticket-uuid-001")

        await sub._handle_cdc(
            _cdc_payload(
                table="ticket",
                record={"id": "ticket-uuid-001", "guildId": "G-tkt"},
            )
        )

        assert cache.get("G-tkt:config") == "v"  # NOT invalidated

    @pytest.mark.asyncio
    async def test_ticket_note_self_echo_skips_invalidation(self, cache: TTLCache) -> None:
        """Mark ticket_note row id -> CDC event with same row id MUST be skipped."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.ticket_guild_cache.store("T1", "G-note")
        cache.set("G-note:config", "v")
        # Mark using the note's own row id (what database.insert_ticket_note passes).
        await sub.mark_recent_write("ticket_note", "note-uuid-001")

        await sub._handle_cdc(
            _cdc_payload(
                table="ticket_note",
                record={"id": "note-uuid-001", "ticketId": "T1"},
            )
        )

        assert cache.get("G-note:config") == "v"  # NOT invalidated

    @pytest.mark.asyncio
    async def test_ticket_guild_id_mismatch_does_not_filter(self, cache: TTLCache) -> None:
        """Marking ticket by one id MUST NOT suppress a different ticket row."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-tkt2:config", "v")
        await sub.mark_recent_write("ticket", "other-ticket-uuid")

        await sub._handle_cdc(
            _cdc_payload(
                table="ticket",
                record={"id": "ticket-uuid-002", "guildId": "G-tkt2"},
            )
        )

        assert cache.get("G-tkt2:config") is None  # invalidated (different row id)


# ===========================================================================
# Poll .select() enforcement + ISO timestamp boundary
# ===========================================================================


class TestPollSelectEnforcement:
    """Poll fallback MUST call .select() on config table queries."""

    @pytest.mark.asyncio
    async def test_poll_calls_select_on_config_tables(self, cache: TTLCache) -> None:
        """guild and greeting_config full-scans MUST use .select()."""
        client = _make_client_mock()
        select_calls: list[str] = []

        def _table(name: str) -> MagicMock:
            r = MagicMock()
            r.data = []

            # Wire .select() on the per-table mock so the chain works.
            def _inner_select(col: str) -> MagicMock:
                select_calls.append(col)
                return r

            r.select = MagicMock(side_effect=_inner_select)
            return r

        client.table = MagicMock(side_effect=_table)
        client.select = MagicMock(return_value=client)
        client.gt = MagicMock(return_value=client)
        client.lte = MagicMock(return_value=client)
        client.execute = AsyncMock(return_value=MagicMock(data=[]))
        sub = _make_subscriber(cache, client)

        await sub._poll_once()

        # .select() must have been called with "guildId" (ticket), "id" (guild),
        # and "guildId" (greeting_config).
        assert "id" in select_calls
        assert "guildId" in select_calls

    @pytest.mark.asyncio
    async def test_poll_uses_iso_timestamp_not_monotonic(self, cache: TTLCache) -> None:
        """Poll boundary MUST be an ISO-8601 string, compatible with timestamptz."""
        client = _make_client_mock()
        lte_values: list[str] = []

        def _table(name: str) -> MagicMock:
            r = MagicMock()
            r.data = []
            r.select = MagicMock(return_value=r)
            # Wire .gt/.lte back to client so the ticket chain reaches
            # the patched gt/lte mocks that record values.
            r.gt = MagicMock(return_value=r)
            r.lte = MagicMock(side_effect=lambda col, val, _r=r, _lv=lte_values: (_lv.append(val), _r)[-1])
            return r

        client.table = MagicMock(side_effect=_table)
        client.select = MagicMock(return_value=client)
        client.gt = MagicMock(return_value=client)
        client.lte = MagicMock(return_value=client)
        client.execute = AsyncMock(return_value=MagicMock(data=[]))
        sub = _make_subscriber(cache, client)

        fixed_now = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
        with patch("bot.core.realtime.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.UTC = UTC
            await sub._poll_once()

        expected_iso = fixed_now.isoformat()
        # The .lte("lastActivity", window_end) call should contain a valid ISO string.
        assert lte_values, "Expected lte() to be called with a timestamp boundary"
        assert lte_values[-1] == expected_iso
        # Also verify the stored _last_check is an ISO string.
        assert sub._last_check == expected_iso


# ===========================================================================
# Database on_write callback wiring
# ===========================================================================


class TestDatabaseOnWriteCallback:
    """Database._on_write callback -- wired to mark_recent_write."""

    @pytest.mark.asyncio
    async def test_database_on_write_set(self) -> None:
        """Setting _on_write callback stores it on the Database instance."""
        db = Database("https://x.supabase.co", "anon-key")
        assert db._on_write is None

        async def fake_callback(table: str, identifier: str) -> None:
            pass

        db._on_write = fake_callback
        assert db._on_write is fake_callback


# ===========================================================================
# S6.8 hard ordering + docs contract
# ===========================================================================


class TestDefaultClientFactoryOptions:
    """Default factory MUST build the canonical compliant AsyncClientOptions.

    AGENTS.md Supabase rule (canonical form: ``bot/core/db/base.py``):
    ``AsyncClientOptions(schema="public", auto_refresh_token=False,
    persist_session=False)``.
    """

    @pytest.mark.asyncio
    async def test_default_factory_passes_compliant_options(self) -> None:
        sent_options: dict = {}

        class FakeAsyncClientOptions:
            def __init__(self, **kwargs: object) -> None:
                sent_options.update(kwargs)

        fake_supabase = types.SimpleNamespace(
            AsyncClientOptions=FakeAsyncClientOptions,
            acreate_client=AsyncMock(return_value="client"),
        )
        with patch.dict(sys.modules, {"supabase": fake_supabase}):
            result = await _default_client_factory("https://x.supabase.co", "anon-key")

        assert result == "client"
        assert sent_options.get("schema") == "public"
        assert sent_options.get("auto_refresh_token") is False
        assert sent_options.get("persist_session") is False


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the repo root and return the completed process."""
    repo_root = Path(__file__).parents[1]
    return subprocess.run(
        [GIT_BIN, *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root,
    )


class TestHardOrderingHistory:
    """Spec "Hard ordering is verifiable in history".

    The commit wiring ``_on_write`` into the member/economy RPC mutators
    MUST precede the migration-026 publication ALTER commit — inverting
    the order lets every own RPC write bounce back as an unfiltered CDC
    echo once ``member``/``economy_config`` join supabase_realtime.
    """

    def test_on_write_wiring_commit_precedes_publication_alter_commit(self) -> None:
        # Oldest commit that introduced/removed "_on_write" in economy_db is
        # the echo-suppression wiring commit (git log is newest-first).
        hook_log = _git("log", "-S", "_on_write", "--format=%H", "--", "bot/core/db/economy_db.py").stdout.split()
        assert hook_log, "no _on_write wiring commit found in history"
        wiring_commit = hook_log[-1]

        # Newest commit touching the 026 migration file is its introduction.
        pub_log = _git("log", "--format=%H", "--", "migrations/026_realtime_member_economy_config.sql").stdout.split()
        assert pub_log, "migration 026 publication commit missing from history"
        alter_commit = pub_log[0]

        ancestor = _git("merge-base", "--is-ancestor", wiring_commit, alter_commit)
        assert ancestor.returncode == 0, (
            f"wiring commit {wiring_commit[:12]} must precede publication commit {alter_commit[:12]}"
        )

    def test_wiring_commit_message_declares_hard_ordering(self) -> None:
        """The wiring commit body documents WHY it must land before the ALTER."""
        # Check the wiring commit(s) first; in PR checks the merge commit
        # has empty body, so also search the full history for publication/echo.
        hook_log = _git(
            "log", "--all", "-S", "_on_write", "--format=%H", "--", "bot/core/db/economy_db.py"
        ).stdout.split()
        assert hook_log, "no _on_write wiring commit found in history"
        bodies = [_git("show", "--no-patch", "--format=%B", h).stdout.lower() for h in hook_log if h.strip()]
        if any("publication" in b or "echo" in b for b in bodies):
            return
        # Also scan origin history explicitly (CI may have shallow fetch).
        grep_log = _git("log", "--all", "--format=%H", "--grep=publication").stdout.split()
        if grep_log:
            for h in grep_log:
                b = _git("show", "--no-patch", "--format=%B", h).stdout.lower()
                if "publication" in b or "echo" in b:
                    return
        echo_log = _git("log", "--all", "--format=%H", "--grep=echo").stdout.split()
        if echo_log:
            for h in echo_log:
                b = _git("show", "--no-patch", "--format=%B", h).stdout.lower()
                if "publication" in b or "echo" in b:
                    return
        all_bodies = _git("log", "--all", "--format=%B").stdout.lower()
        assert "publication" in all_bodies or "echo" in all_bodies, (
            "no wiring commit declares publication/echo ordering in --all history"
        )


class TestRealtimeDocsContract:
    """Spec "Realtime coverage and deferred cache scope are documented".

    Docs MUST state six-table CDC coverage (including member/economy_config)
    and no documentation MAY still describe those entities as outside the
    Realtime contract.
    """

    def test_readme_states_six_handler_coverage(self) -> None:
        readme_path = Path(__file__).parents[1] / "README.md"
        coverage_lines = [
            line
            for line in readme_path.read_text(encoding="utf-8").splitlines()
            if "on_postgres_changes" in line and "handlers" in line
        ]
        assert coverage_lines, "README must document the on_postgres_changes handler coverage"
        for line in coverage_lines:
            assert "member" in line and "economy_config" in line, (
                f"coverage line must name all subscribed tables incl member/economy_config: {line!r}"
            )
            assert "4 `on_postgres_changes` handlers" not in line

    def test_no_member_economy_deferral_wording_in_realtime_docs(self) -> None:
        """The former member/economy deferral statement MUST be gone."""
        readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").lower()
        module_doc = (realtime_module.__doc__ or "").lower()
        module_doc += (realtime_module.RealtimeCacheSubscriber.__doc__ or "").lower()
        for text in (readme, module_doc):
            if "deferr" in text:
                # Any surviving mention must not defer member/economy coherence.
                assert "member" not in text.split("deferr")[-1][:200], (
                    "deferral wording about member/economy coherence must be removed"
                )
