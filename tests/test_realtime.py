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
    async def test_ticket_note_unresolvable_skips_invalidation(self, cache: TTLCache) -> None:
        """ticket_note unresolved (cache miss + DB None) MUST skip, not invalidate wrong guild."""
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

        await sub._handle_cdc(_cdc_payload(table="ticket_note", record={"ticketId": "T3"}))

        # Nothing invalidated.
        assert cache.get("some:config") == "v"

    @pytest.mark.asyncio
    async def test_cdc_event_increments_counter(self, cache: TTLCache) -> None:
        """Each handled CDC event MUST increment the event counter (watchdog input)."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G1"}))
        await sub._handle_cdc(_cdc_payload(table="guild", record={"id": "G2"}))

        assert sub._event_count == 2


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
    """on_subscribe(status, err) — tracks status/timestamp, logs, toggles fallback."""

    @pytest.mark.asyncio
    async def test_subscribed_status_stored(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub._on_subscribe("SUBSCRIBED", None)

        assert sub._status == "SUBSCRIBED"

    @pytest.mark.asyncio
    async def test_channel_error_status_stored(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)

        await sub._on_subscribe("CHANNEL_ERROR", Exception("boom"))

        assert sub._status == "CHANNEL_ERROR"


# ===========================================================================
# Health check (tasks 2.6, 3.6)
# ===========================================================================


class TestHealthCheck:
    """_health_check_once — logs status; enables poll fallback after >60s unhealthy."""

    @pytest.mark.asyncio
    async def test_healthy_subscribed_logs_debug(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "SUBSCRIBED"

        await sub._health_check_once()

        assert sub._poll_fallback_enabled is False

    @pytest.mark.asyncio
    async def test_channel_error_over_60s_enables_fallback(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._status = "CHANNEL_ERROR"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._status_since = 930.0  # 70s ago

        await sub._health_check_once()

        assert sub._poll_fallback_enabled is True

    @pytest.mark.asyncio
    async def test_recovery_disables_fallback(self, cache: TTLCache) -> None:
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._poll_fallback_enabled = True
        sub._status = "CHANNEL_ERROR"
        with patch("bot.core.realtime.time.monotonic", return_value=1000.0):
            sub._status_since = 930.0

        # Recover.
        await sub._on_subscribe("SUBSCRIBED", None)
        await sub._health_check_once()

        assert sub._poll_fallback_enabled is False


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
                responses.append(r)
                return r
            if name == "guild":
                r = MagicMock()
                r.data = [{"id": "G-scan1"}, {"id": "G-scan2"}]
                responses.append(r)
                return r
            if name == "greeting_config":
                r = MagicMock()
                r.data = [{"guildId": "G-scan1"}]
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

        with patch("bot.core.realtime.time.monotonic", return_value=5000.0):
            await sub._poll_once()

        assert sub._last_check > old

    @pytest.mark.asyncio
    async def test_poll_stops_on_recovery(self, cache: TTLCache) -> None:
        """When status returns to SUBSCRIBED, _poll_loop MUST cancel and reset."""
        client = _make_client_mock()
        sub = _make_subscriber(cache, client)
        sub._poll_fallback_enabled = True

        await sub._on_subscribe("SUBSCRIBED", None)
        await sub._health_check_once()

        assert sub._poll_fallback_enabled is False


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
            sub._event_count = 3
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
