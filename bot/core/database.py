"""Database — Supabase client wrapper for NebulosaBot.

Provides async access to the Supabase Postgres instance with health-check,
guild-config read/write, infraction CRUD, member management, and connection
lifecycle management.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import ClientOptions, create_client

from bot.models.guild import GuildConfig

logger = logging.getLogger(__name__)

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

    __slots__ = ("_url", "_key", "_client")

    def __init__(self, url: str, key: str) -> None:
        self._url = url
        self._key = key
        self._client: Any = None

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
    ) -> dict:
        """Insert a new ticket row and return the persisted row.

        Generates a v4 UUID for the primary key. The ``created_at`` and
        ``last_activity`` timestamps are set by database defaults.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        ticket_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": ticket_id,
            "ticketNumber": ticket_number,
            "guildId": guild_id,
            "authorId": author_id,
            "channelId": channel_id,
            "categoryId": category_id,
            "status": "open",
            "lastActivity": now,
        }
        logger.debug("DB insert_ticket(%s) number=%d", ticket_id, ticket_number)
        response = self._client.table("ticket").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

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

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
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
