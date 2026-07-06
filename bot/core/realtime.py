"""Supabase Realtime CDC subscriber for cache invalidation.

Replaces the inbound webhook model with an outbound WebSocket subscription
to the ``supabase_realtime`` publication. Dashboard writes flow into
Supabase tables, Realtime broadcasts CDC events, and this module routes
them to :meth:`TTLCache.invalidate_guild` so the cache stays in sync
without an HTTP server.

Architecture decisions (see ``design.md`` for the full rationale):

* One Realtime channel (``cache-sync``) with four ``on_postgres_changes``
  handlers — one per published table — to keep a single lifecycle.
* Sync CDC callback schedules an ``asyncio.create_task`` for the async
  handler (awaiting inside the SDK callback is not supported per Context7).
* Self-echo filtering via an in-memory TTL set so the bot's own writes do
  not trigger redundant invalidations.
* Health check every 60 s; a 30 s poll fallback kicks in after the socket
  has been unhealthy for more than 60 s.
* Migration watchdog warns if no CDC events arrive within 30 s of the
  first ``SUBSCRIBED`` status (points at a missing publication).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from bot.core.cache import TTLCache

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Tunables
# ------------------------------------------------------------------

RECENT_WRITE_TTL: float = 5.0  # self-echo entries expire after 5 s
TICKET_GUILD_TTL: float = 400.0  # ticket_id -> guild_id cache lifetime
HEALTH_INTERVAL: float = 60.0  # status log / fallback toggle cadence
POLL_INTERVAL: float = 30.0  # poll fallback cadence when WS is down
WATCHDOG_DELAY: float = 30.0  # warn if zero CDC events in this window
UNHEALTHY_THRESHOLD: float = 60.0  # >60 s unhealthy -> enable poll fallback

CHANNEL_NAME = "cache-sync"
SUBSCRIBED_TABLES: tuple[str, ...] = (
    "guild",
    "greeting_config",
    "ticket",
    "ticket_note",
)

# Type alias for the injectable async client factory (eases testing).
ClientFactory = Callable[[str, str], Awaitable[Any]]


# ------------------------------------------------------------------
# Pure helpers — record selection + guild_id extraction
# ------------------------------------------------------------------


def _record_for_event(payload: dict) -> dict:
    """Return the record dict relevant to *payload*.

    INSERT/UPDATE (and any non-DELETE type) read from ``record``; DELETE
    reads from ``old_record`` because the live ``record`` is empty on
    deletion.  A missing ``old_record`` yields an empty dict so callers
    can treat the result uniformly.
    """
    if payload.get("type") == "DELETE":
        return payload.get("old_record") or {}
    return payload.get("record") or {}


def _extract_guild_id(table: str, record: dict) -> str | None:
    """Map a CDC *record* to its guild_id based on the source *table*.

    ``guild`` rows carry the guild snowflake as ``id``; ``greeting_config``
    and ``ticket`` carry it as ``guildId``.  ``ticket_note`` has no direct
    guild column and returns ``None`` — the caller resolves it via the
    ticket cache / DB fallback.  Numeric ids are coerced to ``str`` so
    cache keys stay consistent across write/read paths.
    """
    if table == "guild":
        value = record.get("id")
    elif table in ("greeting_config", "ticket"):
        value = record.get("guildId")
    else:
        return None
    if value is None:
        return None
    return str(value)


def _extract_ticket_id(record: dict) -> str | None:
    """Return the ``ticketId`` from a ``ticket_note`` record (or ``None``)."""
    value = record.get("ticketId")
    if value is None:
        return None
    return str(value)


# ------------------------------------------------------------------
# RecentWriteSet — self-echo filtering (5 s TTL, lazy eviction)
# ------------------------------------------------------------------


class RecentWriteSet:
    """Async-safe TTL set keyed ``{table}:{identifier}``.

    Used to suppress CDC events for rows the bot just wrote itself.  The
    5 s TTL matches the worst-case Realtime delivery latency; entries are
    evicted lazily on :meth:`contains` so no background task is needed.
    """

    __slots__ = ("_entries", "_lock", "_ttl")

    def __init__(self, ttl: float = RECENT_WRITE_TTL) -> None:
        self._entries: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl

    @staticmethod
    def _key(table: str, identifier: str) -> str:
        return f"{table}:{identifier}"

    async def mark(self, table: str, identifier: str) -> None:
        """Record that the bot just wrote to ``(table, identifier)``."""
        key = self._key(table, identifier)
        async with self._lock:
            self._entries[key] = time.monotonic()

    async def contains(self, table: str, identifier: str) -> bool:
        """Return ``True`` if ``(table, identifier)`` was marked recently.

        Expired entries are evicted in place so stale markers never match.
        """
        key = self._key(table, identifier)
        now = time.monotonic()
        async with self._lock:
            stamped = self._entries.get(key)
            if stamped is None:
                return False
            if now - stamped >= self._ttl:
                del self._entries[key]
                return False
            return True


# ------------------------------------------------------------------
# TicketGuildCache — ticket_id -> guild_id TTL mapping
# ------------------------------------------------------------------


class TicketGuildCache:
    """Resolve ``ticket_note`` CDC events to a guild_id without a DB hit.

    Populated opportunistically when ``ticket`` CDC events arrive (which
    carry both ``id`` and ``guildId``) and on DB fallback resolution.  The
    TTL is long enough to cover a typical support conversation.
    """

    __slots__ = ("_entries", "_lock", "_ttl")

    def __init__(self, ttl: float = TICKET_GUILD_TTL) -> None:
        self._entries: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl

    async def store(self, ticket_id: str, guild_id: str) -> None:
        """Cache a ``ticket_id -> guild_id`` mapping."""
        async with self._lock:
            self._entries[ticket_id] = (guild_id, time.monotonic())

    async def get(self, ticket_id: str) -> str | None:
        """Return the cached guild_id, or ``None`` on miss/expiry."""
        async with self._lock:
            entry = self._entries.get(ticket_id)
            if entry is None:
                return None
            guild_id, stamped = entry
            if time.monotonic() - stamped >= self._ttl:
                del self._entries[ticket_id]
                return None
            return guild_id


# ------------------------------------------------------------------
# Default async client factory (production path)
# ------------------------------------------------------------------


async def _default_client_factory(supabase_url: str, supabase_key: str) -> Any:
    """Create the async Supabase client used for Realtime.

    Imported lazily so the module loads in test environments that mock the
    factory without instantiating a real HTTP transport.
    """
    from supabase import AsyncClientOptions, acreate_client

    return await acreate_client(
        supabase_url,
        supabase_key,
        AsyncClientOptions(schema="public"),
    )


# ------------------------------------------------------------------
# RealtimeCacheSubscriber
# ------------------------------------------------------------------


class RealtimeCacheSubscriber:
    """Subscribe to Supabase Realtime CDC and invalidate the bot cache.

    The subscriber owns one Realtime channel (``cache-sync``) with four
    ``on_postgres_changes`` handlers (guild, greeting_config, ticket,
    ticket_note).  CDC events are dispatched by table name, the guild_id
    is extracted, self-echo writes are filtered, and
    :meth:`TTLCache.invalidate_guild` is called for the affected guild.

    A 60 s health task tracks the socket status; when unhealthy for more
    than 60 s a 30 s poll fallback takes over.  A 30 s migration watchdog
    warns if no events arrive after the first ``SUBSCRIBED`` (publication
    not configured).
    """

    __slots__ = (
        "_cache",
        "_channel",
        "_client",
        "_client_factory",
        "_event_count",
        "_health_task",
        "_last_check",
        "_pending_tasks",
        "_poll_fallback_enabled",
        "_poll_task",
        "_started",
        "_status",
        "_status_since",
        "_stopped",
        "_subscribed_at",
        "_supabase_key",
        "_supabase_url",
        "_watchdog_task",
        "recent_writes",
        "ticket_guild_cache",
    )

    def __init__(
        self,
        *,
        supabase_url: str,
        supabase_key: str,
        cache: TTLCache,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key
        self._cache = cache
        self._client_factory = client_factory or _default_client_factory

        # Runtime state — populated by start().
        self._client: Any = None
        self._channel: Any = None
        self._status: str | None = None
        self._status_since: float = 0.0
        self._subscribed_at: float = 0.0
        self._event_count: int = 0
        self._poll_fallback_enabled: bool = False
        # Poll from epoch zero so the first cycle covers the full history.
        self._last_check: str = "1970-01-01T00:00:00+00:00"

        # Self-echo + ticket resolver.
        self.recent_writes = RecentWriteSet()
        self.ticket_guild_cache = TicketGuildCache()

        # Background asyncio tasks.
        self._health_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        # Strong references to fire-and-forget CDC tasks so they are not
        # garbage-collected before completion (RUF006).
        self._pending_tasks: set[asyncio.Task[None]] = set()

        # Lifecycle guards (idempotent start/stop).
        self._started: bool = False
        self._stopped: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> Any:
        """Return the async client, creating it lazily on first use.

        ``start()`` creates the client eagerly, but CDC handlers and the
        poll fallback may run before/without ``start()`` in tests or when
        the socket is down — they all go through this lazy initializer so
        a client is always available without duplicating the factory call.
        """
        if self._client is None:
            self._client = await self._client_factory(
                self._supabase_url,
                self._supabase_key,
            )
        return self._client

    async def start(self) -> None:
        """Create the async client, subscribe to the 4 tables, spawn tasks."""
        if self._started:
            return
        self._started = True

        self._client = await self._ensure_client()
        self._channel = self._client.channel(CHANNEL_NAME)

        for table in SUBSCRIBED_TABLES:
            self._channel.on_postgres_changes(
                event="*",
                schema="public",
                table=table,
                callback=self._cdc_callback,
            )

        await self._channel.subscribe(self._on_subscribe)

        self._health_task = asyncio.create_task(self._health_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.info("Realtime subscriber started on channel %r", CHANNEL_NAME)

    async def stop(self) -> None:
        """Cancel tasks, remove the channel, and best-effort close the client.

        Idempotent: safe to call before :meth:`start` or multiple times.
        """
        if self._stopped:
            return
        self._stopped = True

        for task in (self._health_task, self._poll_task, self._watchdog_task):
            if task is not None:
                task.cancel()
        for task in (self._health_task, self._poll_task, self._watchdog_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Realtime background task raised on cancel")

        if self._client is not None and self._channel is not None:
            try:
                await self._client.remove_channel(self._channel)
            except Exception:
                logger.exception("remove_channel failed during stop()")

        if self._client is not None:
            try:
                await self._client.remove_all_channels()
            except Exception:
                logger.exception("remove_all_channels failed during stop()")
            await self._best_effort_close(self._client)

        self._channel = None
        self._client = None

    @staticmethod
    async def _best_effort_close(client: Any) -> None:
        """Close the client, preferring ``aclose`` over ``close``."""
        for attr in ("aclose", "close"):
            close = getattr(client, attr, None)
            if close is None:
                continue
            try:
                await close()
            except Exception:
                logger.exception("Realtime client %s() failed", attr)
            return

    # ------------------------------------------------------------------
    # Public integration hook
    # ------------------------------------------------------------------

    async def mark_recent_write(self, table: str, identifier: str) -> None:
        """Record a bot-originated write so its CDC echo is suppressed."""
        await self.recent_writes.mark(table, identifier)

    # ------------------------------------------------------------------
    # CDC callback + handler
    # ------------------------------------------------------------------

    def _cdc_callback(self, payload: dict) -> None:
        """Sync SDK callback — schedule the async handler on the loop.

        The Supabase Realtime SDK invokes postgres_changes callbacks
        synchronously; awaiting inside the callback is not supported, so
        we hand off to an ``asyncio.create_task`` (per Context7 guidance).
        The task is tracked in ``_pending_tasks`` to prevent premature
        garbage collection.
        """
        try:
            task = asyncio.create_task(self._handle_cdc(payload))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        except RuntimeError:
            # No running loop (e.g. during shutdown) — drop the event.
            logger.debug("Dropping CDC event — no running event loop")

    async def _handle_cdc(self, payload: dict) -> None:
        """Route a CDC payload to the correct guild invalidation."""
        table = payload.get("table")
        record = _record_for_event(payload)
        guild_id = _extract_guild_id(table, record)

        if guild_id is None and table == "ticket_note":
            ticket_id = _extract_ticket_id(record)
            if ticket_id is not None:
                guild_id = await self._resolve_ticket_guild(ticket_id)

        if guild_id is None:
            logger.warning(
                "CDC event for %s could not resolve a guild_id — skipping",
                table,
            )
            return

        # Self-echo filter: suppress events for rows the bot just wrote.
        # Key by the row's own primary-key id for every table so
        # mark_recent_write("{table}", row_id) matches reliably.
        if table in ("ticket", "ticket_note"):
            echo_identifier = record.get("id")
            if echo_identifier is not None:
                echo_identifier = str(echo_identifier)
        else:
            echo_identifier = guild_id
        if echo_identifier is not None and await self.recent_writes.contains(table, echo_identifier):
            logger.debug(
                "Self-echo detected for %s:%s — skipping invalidation",
                table,
                echo_identifier,
            )
            return

        # Opportunistically cache ticket_id -> guild_id for ticket_note
        # resolution (the ticket row carries both fields).
        if table == "ticket":
            ticket_row_id = record.get("id")
            if ticket_row_id is not None:
                await self.ticket_guild_cache.store(str(ticket_row_id), guild_id)

        self._cache.invalidate_guild(guild_id)
        self._event_count += 1
        logger.debug("Invalidated cache for guild %s via %s CDC", guild_id, table)

    async def _resolve_ticket_guild(self, ticket_id: str) -> str | None:
        """Resolve a ticket_note event to a guild_id (cache then DB)."""
        cached = await self.ticket_guild_cache.get(ticket_id)
        if cached is not None:
            return cached

        client = await self._ensure_client()

        try:
            response = await client.table("ticket").select("guildId").eq("id", ticket_id).limit(1).execute()
        except Exception:
            logger.exception("ticket guild lookup failed for %s", ticket_id)
            return None

        data = getattr(response, "data", None)
        if isinstance(data, list) and data:
            row = data[0]
            guild_id = row.get("guildId") if isinstance(row, dict) else None
            if guild_id is not None:
                guild_id = str(guild_id)
                await self.ticket_guild_cache.store(ticket_id, guild_id)
                return guild_id

        logger.warning(
            "ticket_note event for ticket %s could not resolve a guild — skipping",
            ticket_id,
        )
        return None

    # ------------------------------------------------------------------
    # on_subscribe callback
    # ------------------------------------------------------------------

    def _on_subscribe(self, status: str, err: object) -> None:
        """Synchronous callback for channel.subscribe().

        The Supabase Realtime SDK invokes this callback synchronously;
        all operations are non-blocking attribute updates and logging so
        no ``asyncio.create_task`` wrapper is needed.
        """
        self._status = status
        now = time.monotonic()
        if self._status_since == 0.0:
            self._status_since = now

        if status == "SUBSCRIBED":
            if self._subscribed_at == 0.0:
                self._subscribed_at = now
            self._status_since = now
            self._poll_fallback_enabled = False
            # Reset poll timestamp so the next fallback cycle covers
            # the full history window if the WS drops again.
            self._last_check = "1970-01-01T00:00:00+00:00"
            logger.info("Realtime channel SUBSCRIBED")
        elif status == "CHANNEL_ERROR":
            self._status_since = now
            logger.warning("Realtime channel error: %s", err)
        elif status == "TIMED_OUT":
            self._status_since = now
            logger.warning("Realtime channel timed out")
        else:
            logger.debug("Realtime subscription status: %s", status)

    # ------------------------------------------------------------------
    # Health check (60 s)
    # ------------------------------------------------------------------

    async def _health_check_once(self) -> None:
        """Log status and enable poll fallback after >60 s unhealthy."""
        now = time.monotonic()
        if self._status == "SUBSCRIBED":
            logger.debug("Realtime healthy — status=SUBSCRIBED")
            self._poll_fallback_enabled = False
        elif self._status in ("CHANNEL_ERROR", "TIMED_OUT"):
            if now - self._status_since > UNHEALTHY_THRESHOLD:
                logger.warning(
                    "Realtime unhealthy for %.0fs — enabling poll fallback",
                    now - self._status_since,
                )
                self._poll_fallback_enabled = True
        else:
            logger.debug("Realtime status=%s", self._status)

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_INTERVAL)
            await self._health_check_once()

    # ------------------------------------------------------------------
    # Poll fallback (30 s)
    # ------------------------------------------------------------------

    async def _poll_once(self) -> None:
        """Brute-force invalidation when the WebSocket is down.

        Tickets are queried incrementally via the ``lastActivity`` window;
        guild + greeting_config lack an ``updated_at`` column so they are
        full-scanned.  ``last_check`` advances only after the cycle runs.
        """
        client = await self._ensure_client()
        now = datetime.now(UTC).isoformat()
        window_end = now

        # Incremental ticket query — only tickets touched since last_check.
        ticket_builder = (
            client.table("ticket")
            .select("guildId")
            .gt("lastActivity", self._last_check)
            .lte("lastActivity", window_end)
        )
        for row in await self._safe_rows(ticket_builder):
            guild_id = _row_value(row, "guildId")
            if guild_id is not None:
                self._cache.invalidate_guild(guild_id)

        # Config tables have no updated_at — invalidate every guild row.
        for table, key in (("guild", "id"), ("greeting_config", "guildId")):
            builder = client.table(table).select(key)
            for row in await self._safe_rows(builder):
                guild_id = _row_value(row, key)
                if guild_id is not None:
                    self._cache.invalidate_guild(guild_id)

        self._last_check = window_end

    async def _safe_rows(self, builder: Any) -> list[dict]:
        """Execute *builder* and return its ``data`` list, resiliently.

        Real Supabase builders expose an awaitable ``execute``; some test
        doubles hand back a pre-executed object with ``data`` already set.
        Both paths are handled so the poll fallback stays robust.
        """
        execute = getattr(builder, "execute", None)
        if execute is not None:
            try:
                result = await execute()
                data = getattr(result, "data", None)
                if isinstance(data, list):
                    return data
            except Exception:
                logger.exception("poll execute() failed — falling back to .data")

        data = getattr(builder, "data", None)
        return data if isinstance(data, list) else []

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            if self._poll_fallback_enabled and self._client is not None:
                try:
                    await self._poll_once()
                except Exception:
                    logger.exception("poll fallback cycle failed")

    # ------------------------------------------------------------------
    # Migration watchdog (30 s after first SUBSCRIBED)
    # ------------------------------------------------------------------

    async def _watchdog_check_once(self) -> None:
        """Warn if no CDC events arrive 30 s after the first SUBSCRIBED."""
        if self._status != "SUBSCRIBED" or self._subscribed_at == 0.0:
            return
        now = time.monotonic()
        elapsed = now - self._subscribed_at
        if elapsed >= WATCHDOG_DELAY and self._event_count == 0:
            logger.warning(
                "No CDC events received — check that supabase_realtime publication includes the required tables"
            )

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_DELAY)
            await self._watchdog_check_once()


# ------------------------------------------------------------------
# Row helpers
# ------------------------------------------------------------------


def _row_value(row: object, key: str) -> str | None:
    """Safely extract a stringifiable value from a CDC/poll row."""
    if not isinstance(row, dict):
        return None
    value = row.get(key)
    if value is None:
        return None
    return str(value)
