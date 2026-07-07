"""Unit tests for bot.core.realtime — Supabase Realtime CDC subscriber.

Covers the cache-sync-realtime spec scenarios:
    - Realtime subscriber lifecycle (start creates client + subscribes to 4
      tables; stop removes channel + closes client; idempotent shutdown)
    - CDC handler dispatch (guild / greeting_config / ticket / ticket_note)
    - DELETE events use old_record
    - Self-echo filtering (recent-writes set, 5s TTL, lazy eviction)
    - Health check (60s status log, CHANNEL_ERROR > 60s -> poll fallback)
    - Poll fallback (30s ticket lastActivity window + guild/greeting scan)
    - Migration watchdog (30s no events -> warning)

Time is controlled via ``patch("bot.core.realtime.time.monotonic", ...)``
matching the established test_cache.py pattern (freezegun does not advance
``time.monotonic``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.cache import TTLCache
from bot.core.realtime import (
    RealtimeCacheSubscriber,
    RecentWriteSet,
    TicketGuildCache,
    _extract_guild_id,
    _extract_ticket_id,
    _record_for_event,
)

# ===========================================================================
# Pure helpers — record selection + guild_id extraction (task 3.5 helpers)
# ===========================================================================


class TestRecordForEvent:
    """_record_for_event — INSERT/UPDATE use ``record``, DELETE uses ``old_record``."""

    def test_insert_uses_record(self) -> None:
        payload = {"type": "INSERT", "record": {"id": "G1"}, "old_record": {}}
        assert _record_for_event(payload) == {"id": "G1"}

    def test_update_uses_record(self) -> None:
        payload = {"type": "UPDATE", "record": {"guildId": "G2"}, "old_record": {"guildId": "G0"}}
        assert _record_for_event(payload) == {"guildId": "G2"}

    def test_delete_uses_old_record(self) -> None:
        """Spec: DELETE event with empty record MUST read from old_record."""
        payload = {"type": "DELETE", "record": {}, "old_record": {"id": "G3"}}
        assert _record_for_event(payload) == {"id": "G3"}

    def test_delete_missing_old_record_returns_empty(self) -> None:
        payload = {"type": "DELETE", "record": {}}
        assert _record_for_event(payload) == {}

    def test_missing_type_treats_as_record(self) -> None:
        payload = {"record": {"id": "G4"}}
        assert _record_for_event(payload) == {"id": "G4"}


class TestExtractGuildId:
    """_extract_guild_id — pure table -> guild_id mapping."""

    def test_guild_table_uses_id(self) -> None:
        assert _extract_guild_id("guild", {"id": "111222333"}) == "111222333"

    def test_greeting_config_uses_guild_id(self) -> None:
        assert _extract_guild_id("greeting_config", {"guildId": "444555666"}) == "444555666"

    def test_ticket_uses_guild_id(self) -> None:
        assert _extract_guild_id("ticket", {"guildId": "777888999"}) == "777888999"

    def test_ticket_note_returns_none(self) -> None:
        """ticket_note has no direct guildId — async resolver handles it."""
        assert _extract_guild_id("ticket_note", {"ticketId": "T1"}) is None

    def test_unknown_table_returns_none(self) -> None:
        assert _extract_guild_id("other", {"id": "X"}) is None

    def test_missing_field_returns_none(self) -> None:
        assert _extract_guild_id("guild", {}) is None

    def test_coerces_non_string_to_string(self) -> None:
        """Numeric ids MUST be coerced to str for cache key consistency."""
        assert _extract_guild_id("guild", {"id": 123456}) == "123456"


class TestExtractTicketId:
    """_extract_ticket_id — ticket_note -> ticket_id for guild resolution."""

    def test_returns_ticket_id(self) -> None:
        assert _extract_ticket_id({"ticketId": "ticket-uuid-001"}) == "ticket-uuid-001"

    def test_missing_returns_none(self) -> None:
        assert _extract_ticket_id({}) is None

    def test_coerces_to_string(self) -> None:
        assert _extract_ticket_id({"ticketId": 99}) == "99"


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

    @pytest.mark.asyncio
    async def test_entry_expires_after_5s(self) -> None:
        """Spec: entries older than ~5s MUST NOT filter (lazy eviction)."""
        rws = RecentWriteSet()
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await rws.mark("guild", "G1")
        # Advance past the 5s TTL window.
        with patch("bot.core.realtime.time.monotonic", return_value=1006.0):
            assert await rws.contains("guild", "G1") is False

    @pytest.mark.asyncio
    async def test_entry_still_present_within_5s(self) -> None:
        rws = RecentWriteSet()
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            await rws.mark("guild", "G1")
        with patch("bot.core.realtime.time.monotonic", return_value=1004.0):
            assert await rws.contains("guild", "G1") is True

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
    """start() — creates async client, one channel, 4 on_postgres_changes, subscribe."""

    @pytest.mark.asyncio
    async def test_start_creates_client_and_subscribes(self, cache: TTLCache) -> None:
        channel = _make_channel_mock()
        client = _make_client_mock(channel)
        sub = _make_subscriber(cache, client)

        await sub.start()

        client.channel.assert_called_once_with("cache-sync")
        assert channel.on_postgres_changes.call_count == 4
        channel.subscribe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_subscribes_to_four_tables(self, cache: TTLCache) -> None:
        channel = _make_channel_mock()
        client = _make_client_mock(channel)
        sub = _make_subscriber(cache, client)

        await sub.start()

        tables_called = {call.kwargs.get("table") for call in channel.on_postgres_changes.call_args_list}
        assert tables_called == {"guild", "greeting_config", "ticket", "ticket_note"}

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

        assert health.cancelled() or health.done()
        assert poll.cancelled() or poll.done()
        assert watchdog.cancelled() or watchdog.done()

    @pytest.mark.asyncio
    async def test_stop_idempotent_when_not_started(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        # stop() before start() MUST NOT raise.
        await sub.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent_when_called_twice(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        await sub.start()

        await sub.stop()
        await sub.stop()  # second call MUST NOT raise

        # remove_all_channels called on the first stop; second is a no-op.
        assert client.remove_all_channels.await_count == 1


class TestMarkRecentWrite:
    """mark_recent_write — public API for database.py integration (task 3.10)."""

    @pytest.mark.asyncio
    async def test_mark_then_cdc_skips(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub.mark_recent_write("guild", "G1")

        assert await sub.recent_writes.contains("guild", "G1") is True


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
        import logging

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
    async def test_nested_sdk_payload_invalidates_guild(self, cache: TTLCache) -> None:
        """SDK delivers payload as {data: {type, table, record}, ids: [...]}.
        _handle_cdc MUST normalize to extract table and record from data."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-nested:config", "v")

        sdk_payload = {
            "data": {
                "type": "UPDATE",
                "table": "guild",
                "schema": "public",
                "record": {"id": "G-nested"},
                "old_record": {},
                "commit_timestamp": "2025-06-15T10:00:00Z",
            },
            "ids": [1],
        }
        await sub._handle_cdc(sdk_payload)

        assert cache.get("G-nested:config") is None  # invalidated

    @pytest.mark.asyncio
    async def test_table_hint_fallback_when_data_table_missing(self, cache: TTLCache) -> None:
        """When data.table is None/missing, table_hint from callback registration MUST be used."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-hint:config", "v")

        sdk_payload = {
            "data": {
                "type": "INSERT",
                "table": None,
                "schema": "public",
                "record": {"guildId": "G-hint"},
                "old_record": {},
            },
            "ids": [2],
        }
        await sub._handle_cdc(sdk_payload, table_hint="greeting_config")

        assert cache.get("G-hint:config") is None  # invalidated via table_hint

    @pytest.mark.asyncio
    async def test_delete_nested_sdk_uses_old_record(self, cache: TTLCache) -> None:
        """DELETE event in nested SDK format MUST read old_record from data."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-del-nested:config", "v")

        sdk_payload = {
            "data": {
                "type": "DELETE",
                "table": "guild",
                "schema": "public",
                "record": {},
                "old_record": {"id": "G-del-nested"},
            },
            "ids": [3],
        }
        await sub._handle_cdc(sdk_payload)

        assert cache.get("G-del-nested:config") is None

    @pytest.mark.asyncio
    async def test_legacy_top_level_payload_still_works(self, cache: TTLCache) -> None:
        """Legacy top-level payload format MUST still work for backward compatibility."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        cache.set("G-legacy:config", "v")

        legacy_payload = {
            "type": "INSERT",
            "table": "guild",
            "schema": "public",
            "record": {"id": "G-legacy"},
            "old_record": {},
        }
        await sub._handle_cdc(legacy_payload)

        assert cache.get("G-legacy:config") is None  # still works


# ===========================================================================
# Self-echo filtering integration (task 2.5)
# ===========================================================================


class TestSelfEchoFiltering:
    """A CDC event for a row the bot just wrote MUST be skipped."""

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


# ===========================================================================
# on_subscribe callback (task 3.4)
# ===========================================================================


class TestOnSubscribe:
    """on_subscribe(status, err) — synchronous callback, tracks status, resets poll."""

    def test_on_subscribe_is_synchronous(self, cache: TTLCache) -> None:
        """Spec: subscribe callback MUST be synchronous (SDK invokes it directly)."""
        import inspect

        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        assert not inspect.iscoroutinefunction(sub._on_subscribe)

    def test_subscribed_status_stored(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        sub._on_subscribe("SUBSCRIBED", None)

        assert sub._status == "SUBSCRIBED"

    def test_channel_error_status_stored(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        sub._on_subscribe("CHANNEL_ERROR", Exception("boom"))

        assert sub._status == "CHANNEL_ERROR"

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


# ===========================================================================
# Health check (tasks 2.6, 3.6)
# ===========================================================================


class TestHealthCheck:
    """_health_check_once — logs status; enables poll fallback after >60s unhealthy."""

    @pytest.mark.asyncio
    async def test_healthy_subscribed_logs_debug(self, cache: TTLCache, caplog) -> None:
        """Spec: healthy subscription MUST log a DEBUG message."""
        import logging

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
        import logging

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
                    "unhealthy" in r.message.lower() or "poll fallback" in r.message.lower()
                    for r in caplog.records
                ), "Expected a WARNING log about unhealthy state or poll fallback"
        finally:
            # _health_check_once now recreates the poll task when enabling the
            # fallback — clean it up so no background task leaks past the test.
            await sub.stop()

    @pytest.mark.asyncio
    async def test_recovery_disables_fallback(self, cache: TTLCache, caplog) -> None:
        """Spec: reconnection to SUBSCRIBED MUST disable poll fallback and log."""
        import logging

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
        import logging

        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._subscribed_at = 965.0  # 35s ago
            sub._event_count = 0
            with caplog.at_level(logging.WARNING, logger="bot.core.realtime"):
                await sub._watchdog_check_once()

        assert any("supabase_realtime publication" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_silent_when_events_received(self, cache: TTLCache, caplog) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"
        import logging

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
        import logging

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
        import logging

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
        import logging

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
        import logging

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
    async def test_health_escalation_after_three_unhealthy_cycles(self, cache: TTLCache, caplog) -> None:
        """After 3 consecutive unhealthy cycles, log level escalates to ERROR."""
        import logging

        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "CHANNEL_ERROR"
        sub._unhealthy_cycles = 0

        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._status_since = 930.0  # 70s ago

            # First 3 unhealthy cycles: WARNING level
            for i in range(3):
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
            r.lte = MagicMock(side_effect=lambda col, val: (lte_values.append(val), r)[-1])
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
        from bot.core.database import Database

        db = Database("https://x.supabase.co", "anon-key")
        assert db._on_write is None

        async def fake_callback(table: str, identifier: str) -> None:
            pass

        db._on_write = fake_callback
        assert db._on_write is fake_callback
