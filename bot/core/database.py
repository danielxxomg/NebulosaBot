"""Database — Supabase client wrapper for NebulosaBot.

Provides async access to the Supabase Postgres instance with health-check,
guild-config read/write, infraction CRUD, member management, and connection
lifecycle management.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import ClientOptions, create_client

from bot.models.guild import GuildConfig

logger = logging.getLogger(__name__)


async def create_realtime_client(supabase_url: str, supabase_key: str) -> Any:
    """Create the async Supabase client used by the Realtime subscriber.

    Realtime requires ``acreate_client`` (async) rather than the sync
    ``create_client`` used by :class:`Database` for data access.  Kept as a
    standalone coroutine so it can be injected as the subscriber's
    ``client_factory`` without binding to a ``Database`` instance.
    """
    from supabase import AsyncClientOptions, acreate_client

    return await acreate_client(
        supabase_url,
        supabase_key,
        AsyncClientOptions(schema="public"),
    )


# ------------------------------------------------------------------
# Postgrest response wrapper — adapts sync API for async callers
# ------------------------------------------------------------------


def _unwrap(response: Any) -> list[dict]:
    """Extract ``.data`` from a Postgrest sync response.

    Supabase-py's sync API returns objects with ``.data`` (list[dict]).
    """
    if response is None:
        return []
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------


class Database:
    """Async wrapper around a Supabase Python client.

    Instantiate with the project URL and API key (anon or service_role).
    Call ``connect()`` before any data-access methods.
    """

    __slots__ = ("_client", "_key", "_on_write", "_url")

    def __init__(self, url: str, key: str) -> None:
        self._url = url
        self._key = key
        self._client: Any = None
        # Optional callback wired by RealtimeCacheSubscriber for self-echo
        # filtering.  Signature: async (table: str, identifier: str) -> None
        self._on_write: Callable[[str, str], Awaitable[None]] | None = None

    # -- lifecycle ----------------------------------------------------

    async def connect(self) -> None:
        """Create the Supabase client and verify connectivity.

        The client is built via the sync ``create_client`` factory because
        supabase-py auto-negotiates the underlying HTTP adapter. This call
        is lightweight — real I/O happens on the first query.
        """
        logger.info("Connecting to Supabase at %s ...", self._url)
        self._client = create_client(
            self._url,
            self._key,
            ClientOptions(schema="public"),
        )
        healthy = await self.health_check()
        if not healthy:
            logger.warning("Supabase health check failed — continuing anyway")
        else:
            logger.info("Supabase connection verified")

    async def health_check(self) -> bool:
        """Ping the database by selecting 1 row from the guild table.

        Returns ``True`` if the query succeeds, ``False`` otherwise.
        """
        if self._client is None:
            logger.error("health_check called before connect()")
            return False

        try:
            # Lightweight probe — reads at most one row.
            response = self._client.table("guild").select("id").limit(1).execute()
            _unwrap(response)  # drain so we don't leak a cursor
            return True
        except Exception:
            logger.exception("Supabase health check query failed")
            return False

    # -- guild --------------------------------------------------------

    async def get_guild(self, guild_id: str) -> dict | None:
        """Fetch a guild row by its Discord snowflake *guild_id*.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        never been configured.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_guild(%r)", guild_id)
        response = self._client.table("guild").select("*").eq("id", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_guild(self, config: GuildConfig) -> None:
        """Insert or update a guild configuration row.

        Uses Supabase ``upsert`` so the same method handles both ``INSERT``
        (new guild) and ``UPDATE`` (changed prefix, language, etc.).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_guild(%r)", config.id)
        self._client.table("guild").upsert(config.to_db_dict()).execute()
        if self._on_write is not None:
            await self._on_write("guild", str(config.id))

    async def ensure_guild_exists(self, guild_id: str) -> None:
        """Insert default guild config only if the row doesn't exist.

        Uses ``ignore_duplicates=True`` (ON CONFLICT DO NOTHING) so existing
        custom config is preserved — unlike :meth:`upsert_guild` which
        overwrites. Used at startup to backfill guilds the bot was already a
        member of (``on_guild_join`` only fires for joins during the session).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB ensure_guild_exists(%r)", guild_id)
        self._client.table("guild").upsert(
            {"id": guild_id, "prefix": "nb!", "language": "es", "active": True},
            on_conflict="id",
            ignore_duplicates=True,
        ).execute()

    # -- infraction ---------------------------------------------------

    async def insert_infraction(
        self,
        guild_id: str,
        target_id: str,
        moderator_id: str,
        type: str,
        reason: str,
        expires_at: str | None = None,
    ) -> dict:
        """Insert a moderation infraction and return the persisted row.

        Generates a v4 UUID for the primary key.  The ``created_at``
        timestamp is set by the database default clause.

        Returns the camelCase row dict (matching ``Infraction.from_db_row``).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        infraction_id = str(uuid.uuid4())
        row = {
            "id": infraction_id,
            "guildId": guild_id,
            "targetId": target_id,
            "moderatorId": moderator_id,
            "type": type,
            "reason": reason,
            "active": True,
            "expiresAt": expires_at,
        }
        logger.debug("DB insert_infraction(%s) type=%s", infraction_id, type)
        response = self._client.table("infraction").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

    async def get_infractions(
        self,
        guild_id: str,
        target_id: str,
        type: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        """Return infraction rows for a guild member, with optional filters.

        Args:
            guild_id: Discord guild snowflake.
            target_id: Discord target user snowflake.
            type: Optional infraction type filter (``"WARN"``, ``"MUTE"``, …).
            after: Optional ISO-8601 datetime string; only rows with
                ``createdAt >= after`` are returned.

        Returns:
            List of camelCase row dicts ordered by ``createdAt`` descending.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        query = (
            self._client.table("infraction")
            .select("*")
            .eq("guildId", guild_id)
            .eq("targetId", target_id)
            .order("createdAt", desc=True)
        )
        if type is not None:
            query = query.eq("type", type)
        if after is not None:
            query = query.gte("createdAt", after)

        logger.debug("DB get_infractions(guild=%s, target=%s, type=%s)", guild_id, target_id, type)
        response = query.execute()
        return _unwrap(response)

    async def get_active_warnings(
        self, guild_id: str, target_id: str
    ) -> list[dict]:
        """Return all active WARN infractions for a guild member.

        Convenience wrapper around ``get_infractions`` with ``type="WARN"``
        and an explicit ``active`` filter.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_active_warnings(guild=%s, target=%s)", guild_id, target_id)
        response = (
            self._client.table("infraction")
            .select("*")
            .eq("guildId", guild_id)
            .eq("targetId", target_id)
            .eq("type", "WARN")
            .eq("active", True)
            .order("createdAt", desc=True)
            .execute()
        )
        return _unwrap(response)

    async def deactivate_infraction(self, infraction_id: str) -> None:
        """Soft-delete an infraction by setting ``active = false``."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB deactivate_infraction(%s)", infraction_id)
        self._client.table("infraction").update({"active": False}).eq(
            "id", infraction_id
        ).execute()

    # -- ticket -------------------------------------------------------

    async def insert_ticket(
        self,
        guild_id: str,
        author_id: str,
        channel_id: str,
        category_id: str | None,
        ticket_number: int,
        parent_id: str | None = None,
    ) -> dict:
        """Insert a new ticket row and return the persisted row.

        Generates a v4 UUID for the primary key. The ``created_at`` and
        ``last_activity`` timestamps are set by database defaults. When
        *parent_id* is provided the row is stored as a sub-ticket of that
        parent (one level deep — service-layer validation enforces this).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        ticket_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        row = {
            "id": ticket_id,
            "ticketNumber": ticket_number,
            "guildId": guild_id,
            "authorId": author_id,
            "channelId": channel_id,
            "categoryId": category_id,
            "status": "open",
            "lastActivity": now,
            "parentId": parent_id,
        }
        logger.debug(
            "DB insert_ticket(%s) number=%d parent=%s", ticket_id, ticket_number, parent_id
        )
        response = self._client.table("ticket").insert(row).execute()
        rows = _unwrap(response)
        if self._on_write is not None:
            await self._on_write("ticket", ticket_id)
        return rows[0] if rows else {}

    async def get_tickets_by_parent(self, parent_id: str) -> list[dict]:
        """Return all tickets whose ``parentId`` equals *parent_id*.

        Used to render a parent's sub-ticket children. Results are ordered
        newest-first by ``createdAt`` to match the project's list-query
        convention. Returns an empty list when the parent has no children.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_tickets_by_parent(%r)", parent_id)
        response = (
            self._client.table("ticket")
            .select("*")
            .eq("parentId", parent_id)
            .order("createdAt", desc=True)
            .execute()
        )
        return _unwrap(response)

    # -- ticket_note ---------------------------------------------------

    async def insert_ticket_note(
        self,
        ticket_id: str,
        author_id: str,
        content: str,
    ) -> dict:
        """Insert a staff note on a ticket and return the persisted row.

        Generates a v4 UUID for the primary key. The ``createdAt`` timestamp
        is set by the database default clause (``NOW()``) — it is not set
        client-side. Notes are staff-only (not visible to the ticket opener).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        note_id = str(uuid.uuid4())
        row = {
            "id": note_id,
            "ticketId": ticket_id,
            "authorId": author_id,
            "content": content,
        }
        logger.debug(
            "DB insert_ticket_note(%s) ticket=%s author=%s", note_id, ticket_id, author_id
        )
        response = self._client.table("ticket_note").insert(row).execute()
        rows = _unwrap(response)
        if self._on_write is not None:
            await self._on_write("ticket_note", note_id)
        return rows[0] if rows else {}

    async def get_ticket_notes(self, ticket_id: str, limit: int = 50) -> list[dict]:
        """Return notes for a ticket, newest-first, capped by *limit*.

        The caller controls the cap (default 50, the v1 per-ticket note limit
        enforced in the service layer). Results are ordered by ``createdAt``
        descending.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_notes(ticket=%s, limit=%d)", ticket_id, limit)
        response = (
            self._client.table("ticket_note")
            .select("*")
            .eq("ticketId", ticket_id)
            .order("createdAt", desc=True)
            .limit(limit)
            .execute()
        )
        return _unwrap(response)

    async def delete_ticket_note(self, note_id: str) -> None:
        """Delete a staff note by its UUID primary key.

        Ownership authorization is enforced in the service layer before this
        call — the database layer performs the delete only.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB delete_ticket_note(%s)", note_id)
        self._client.table("ticket_note").delete().eq("id", note_id).execute()

    async def get_ticket(self, ticket_id: str) -> dict | None:
        """Fetch a ticket by its UUID primary key."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket(%r)", ticket_id)
        response = (
            self._client.table("ticket")
            .select("*")
            .eq("id", ticket_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_channel(self, channel_id: str) -> dict | None:
        """Fetch a ticket by its Discord channel snowflake."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_by_channel(%r)", channel_id)
        response = (
            self._client.table("ticket")
            .select("*")
            .eq("channelId", channel_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def update_ticket(self, ticket_id: str, **kwargs: Any) -> None:
        """Update a ticket row with the given camelCase column values.

        Accepts keyword arguments matching the DB column names (e.g.
        ``status="closed"``, ``claimedBy=staff_id``).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB update_ticket(%s) %s", ticket_id, kwargs)
        self._client.table("ticket").update(kwargs).eq("id", ticket_id).execute()

    async def get_stale_tickets(
        self, guild_id: str, hours: int = 48
    ) -> list[dict]:
        """Return open/claimed tickets with ``lastActivity`` older than *hours*.

        Used by the auto-close task to identify inactive tickets.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        logger.debug(
            "DB get_stale_tickets(guild=%s, cutoff=%s)", guild_id, cutoff.isoformat()
        )
        response = (
            self._client.table("ticket")
            .select("*")
            .eq("guildId", guild_id)
            .in_("status", ["open", "claimed"])
            .lt("lastActivity", cutoff.isoformat())
            .execute()
        )
        return _unwrap(response)

    async def get_max_ticket_number(self, guild_id: str) -> int:
        """Return the highest ``ticketNumber`` for a guild, or 0 if none exist."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_max_ticket_number(guild=%s)", guild_id)
        response = (
            self._client.table("ticket")
            .select("ticketNumber")
            .eq("guildId", guild_id)
            .order("ticketNumber", desc=True)
            .limit(1)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0]["ticketNumber"] if rows else 0

    # -- ticket_category -----------------------------------------------

    async def insert_ticket_category(
        self,
        guild_id: str,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int = 0,
    ) -> dict:
        """Insert a ticket category and return the persisted row.

        Generates a v4 UUID for the primary key. The ``created_at`` timestamp
        is set by the database default clause.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        category_id = str(uuid.uuid4())
        row = {
            "id": category_id,
            "guildId": guild_id,
            "name": name,
            "emoji": emoji,
            "description": description,
            "position": position,
            "active": True,
        }
        logger.debug("DB insert_ticket_category(%s) name=%r", category_id, name)
        response = self._client.table("ticket_category").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

    async def get_ticket_categories(self, guild_id: str) -> list[dict]:
        """Return all active ticket categories for a guild, ordered by position."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_categories(guild=%s)", guild_id)
        response = (
            self._client.table("ticket_category")
            .select("*")
            .eq("guildId", guild_id)
            .eq("active", True)
            .order("position")
            .execute()
        )
        return _unwrap(response)

    async def get_ticket_category(self, category_id: str) -> dict | None:
        """Fetch a ticket category by its UUID primary key."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_category(%r)", category_id)
        response = (
            self._client.table("ticket_category")
            .select("*")
            .eq("id", category_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def delete_ticket_category(self, category_id: str) -> None:
        """Delete a ticket category by its UUID primary key."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB delete_ticket_category(%s)", category_id)
        self._client.table("ticket_category").delete().eq("id", category_id).execute()

    async def count_open_tickets_by_category(self, category_id: str) -> int:
        """Return the number of open/claimed tickets referencing *category_id*.

        Used to block deletion of a category that still has active tickets.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB count_open_tickets_by_category(%s)", category_id)
        response = (
            self._client.table("ticket")
            .select("id")
            .eq("categoryId", category_id)
            .in_("status", ["open", "claimed"])
            .execute()
        )
        return len(_unwrap(response))

    # -- ticket_channel ------------------------------------------------

    async def get_open_ticket_channel_ids(self, guild_id: str) -> list[str]:
        """Return channel IDs of all open/claimed tickets for a guild.

        Used on startup to rebuild the ticket channel cache for O(1)
        ``on_message`` lookups.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_open_ticket_channel_ids(guild=%s)", guild_id)
        response = (
            self._client.table("ticket")
            .select("channelId")
            .eq("guildId", guild_id)
            .in_("status", ["open", "claimed"])
            .execute()
        )
        rows = _unwrap(response)
        return [r["channelId"] for r in rows]

    async def update_ticket_last_activity(self, channel_id: str) -> None:
        """Set ``lastActivity`` to now for the ticket with the given channel ID.

        Called by the ``on_message`` listener — avoids a separate
        lookup-then-update round-trip.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        now = datetime.now(UTC).isoformat()
        logger.debug("DB update_ticket_last_activity(ch=%s)", channel_id)
        self._client.table("ticket").update(
            {"lastActivity": now}
        ).eq("channelId", channel_id).execute()

    # -- guild_panel ---------------------------------------------------

    async def update_guild_panel(
        self, guild_id: str, message_id: str, channel_id: str
    ) -> None:
        """Persist the ticket panel message and channel IDs on the guild row.

        Called after deploying a panel so it survives bot restarts.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB update_guild_panel(guild=%s, msg=%s, ch=%s)",
            guild_id, message_id, channel_id,
        )
        self._client.table("guild").update({
            "ticketPanelMessageId": message_id,
            "ticketPanelChannelId": channel_id,
        }).eq("id", guild_id).execute()

    # -- member -------------------------------------------------------

    async def get_member(self, guild_id: str, user_id: str) -> dict | None:
        """Fetch a member row by guild and user snowflake.

        Returns the camelCase row dict, or ``None`` if the member has no
        row yet (e.g. never warned, no XP).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_member(guild=%s, user=%s)", guild_id, user_id)
        response = (
            self._client.table("member")
            .select("*")
            .eq("guildId", guild_id)
            .eq("userId", user_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def update_member_warnings(
        self, guild_id: str, user_id: str, delta: int
    ) -> None:
        """Increment or decrement the warnings counter for a member.

        If the member does not have a row yet, an initial row with
        ``warnings = delta`` is upserted.  This is safe for the first
        warn action on a previously unknown member.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_warnings = max(existing.get("warnings", 0) + delta, 0)
            logger.debug(
                "DB update_member_warnings(%s/%s): %d → %d",
                guild_id, user_id, existing.get("warnings", 0), new_warnings,
            )
            self._client.table("member").update(
                {"warnings": new_warnings}
            ).eq("guildId", guild_id).eq("userId", user_id).execute()
        else:
            # First interaction — create the row.
            initial = max(delta, 0)
            logger.debug(
                "DB update_member_warnings(%s/%s): new member, warnings=%d",
                guild_id, user_id, initial,
            )
            self._client.table("member").upsert({
                "guildId": guild_id,
                "userId": user_id,
                "warnings": initial,
            }).execute()

    # -- economy_config ------------------------------------------------

    async def get_economy_config(self, guild_id: str) -> dict | None:
        """Fetch an economy_config row by guild ID.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        no economy configuration yet.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_economy_config(%r)", guild_id)
        response = (
            self._client.table("economy_config")
            .select("*")
            .eq("guildId", guild_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_economy_config(self, config: Any) -> None:
        """Insert or update an economy_config row.

        Args:
            config: An :class:`~bot.models.economy_config.EconomyConfig`
                instance whose ``to_db_dict()`` produces camelCase keys.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_economy_config(%r)", config.guild_id)
        self._client.table("economy_config").upsert(config.to_db_dict()).execute()

    # -- member economy --------------------------------------------------

    async def update_member_xp(
        self, guild_id: str, user_id: str, xp_delta: int,
        new_level: int | None = None,
    ) -> dict:
        """Increment a member's XP and return the updated row.

        Optionally updates the stored level and sets ``lastXpGain`` to now.
        If the member does not have a row yet, an initial row is upserted.
        Returns the camelCase row dict with at least ``xp`` and ``level``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        now = datetime.now(UTC).isoformat()
        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_xp_val = max(existing.get("xp", 0) + xp_delta, 0)
            level = new_level if new_level is not None else existing.get("level", 0)
            logger.debug(
                "DB update_member_xp(%s/%s): xp %d → %d, level=%d",
                guild_id, user_id, existing.get("xp", 0), new_xp_val, level,
            )
            self._client.table("member").update({
                "xp": new_xp_val,
                "level": level,
                "lastXpGain": now,
            }).eq("guildId", guild_id).eq("userId", user_id).execute()
            return {"xp": new_xp_val, "level": level}
        else:
            level = new_level if new_level is not None else 0
            logger.debug(
                "DB update_member_xp(%s/%s): new member, xp=%d",
                guild_id, user_id, xp_delta,
            )
            self._client.table("member").upsert({
                "guildId": guild_id,
                "userId": user_id,
                "xp": max(xp_delta, 0),
                "level": level,
                "lastXpGain": now,
            }).execute()
            return {"xp": xp_delta, "level": level}

    async def update_member_coins(
        self, guild_id: str, user_id: str, coin_delta: int
    ) -> dict:
        """Increment a member's coins and return the updated row.

        If the member does not have a row yet, an initial row with
        ``coins = coin_delta`` is upserted.  Returns the camelCase row
        dict with at least ``coins``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_coins = max(existing.get("coins", 0) + coin_delta, 0)
            logger.debug(
                "DB update_member_coins(%s/%s): coins %d → %d",
                guild_id, user_id, existing.get("coins", 0), new_coins,
            )
            self._client.table("member").update(
                {"coins": new_coins}
            ).eq("guildId", guild_id).eq("userId", user_id).execute()
            return {"coins": new_coins}
        else:
            logger.debug(
                "DB update_member_coins(%s/%s): new member, coins=%d",
                guild_id, user_id, coin_delta,
            )
            self._client.table("member").upsert({
                "guildId": guild_id,
                "userId": user_id,
                "coins": max(coin_delta, 0),
            }).execute()
            return {"coins": coin_delta}

    async def update_member_daily(
        self,
        guild_id: str,
        user_id: str,
        coin_delta: int,
        streak: int,
        last_daily_reset: str | None,
        last_daily: str | None,
    ) -> dict:
        """Apply a daily claim: increment coins, set streak + timestamps.

        If the member does not have a row yet, an initial row is upserted.
        Returns the camelCase row dict with at least ``coins``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        existing = await self.get_member(guild_id, user_id)
        if existing is not None:
            new_coins = max(existing.get("coins", 0) + coin_delta, 0)
            logger.debug(
                "DB update_member_daily(%s/%s): coins %d → %d, streak=%d",
                guild_id, user_id, existing.get("coins", 0), new_coins, streak,
            )
            self._client.table("member").update({
                "coins": new_coins,
                "dailyStreak": streak,
                "lastDailyReset": last_daily_reset,
                "lastDaily": last_daily,
            }).eq("guildId", guild_id).eq("userId", user_id).execute()
            return {"coins": new_coins}
        else:
            logger.debug(
                "DB update_member_daily(%s/%s): new member, coins=%d, streak=%d",
                guild_id, user_id, coin_delta, streak,
            )
            self._client.table("member").upsert({
                "guildId": guild_id,
                "userId": user_id,
                "coins": max(coin_delta, 0),
                "dailyStreak": streak,
                "lastDailyReset": last_daily_reset,
                "lastDaily": last_daily,
            }).execute()
            return {"coins": coin_delta}

    async def get_leaderboard(
        self,
        guild_id: str,
        sort_by: str = "xp",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Return leaderboard rows for a guild, sorted by *sort_by* descending.

        Args:
            guild_id: Discord guild snowflake.
            sort_by: Column to sort by (``"xp"`` or ``"coins"``).
            limit: Maximum rows to return.
            offset: Pagination offset.

        Returns:
            List of camelCase row dicts ordered by *sort_by* DESC.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        column = "xp" if sort_by == "xp" else "coins"
        logger.debug(
            "DB get_leaderboard(guild=%s, sort=%s, limit=%d, offset=%d)",
            guild_id, column, limit, offset,
        )
        response = (
            self._client.table("member")
            .select("guildId,userId,xp,level,coins")
            .eq("guildId", guild_id)
            .order(column, desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        return _unwrap(response)

    # -- greeting_config -----------------------------------------------

    async def get_greeting_config(self, guild_id: str) -> dict | None:
        """Fetch a greeting_config row by guild ID.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        no greeting configuration yet.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_greeting_config(%r)", guild_id)
        response = (
            self._client.table("greeting_config")
            .select("*")
            .eq("guildId", guild_id)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_greeting_config(self, config: Any) -> None:
        """Insert or update a greeting_config row.

        Args:
            config: A :class:`~bot.models.greeting_config.GreetingConfig`
                instance whose ``to_db_dict()`` produces camelCase keys.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_greeting_config(%r)", config.guild_id)
        self._client.table("greeting_config").upsert(config.to_db_dict()).execute()
        if self._on_write is not None:
            await self._on_write("greeting_config", str(config.guild_id))

    async def get_member_rank(
        self, guild_id: str, user_id: str, sort_by: str = "xp"
    ) -> int | None:
        """Return the 1-indexed rank position of a member on the leaderboard.

        Counts how many members have a higher *sort_by* value than the
        target member.  Returns ``None`` if the member has no row.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        member = await self.get_member(guild_id, user_id)
        if member is None:
            return None

        column = "xp" if sort_by == "xp" else "coins"
        target_value = member.get(column, 0)
        if target_value == 0:
            return 0

        logger.debug(
            "DB get_member_rank(guild=%s, user=%s, sort=%s)",
            guild_id, user_id, column,
        )
        # Count members with higher value → rank = count + 1
        response = (
            self._client.table("member")
            .select("userId", count="exact")
            .eq("guildId", guild_id)
            .gt(column, target_value)
            .execute()
        )
        rows = _unwrap(response)
        count = response.count if hasattr(response, "count") else len(rows)
        return count + 1
