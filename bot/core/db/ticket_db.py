"""TicketDBMixin — ticket table operations for the Database facade."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class TicketDBMixin:
    """Ticket CRUD and query operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def insert_ticket(
        self: Any,
        guild_id: str,
        author_id: str,
        channel_id: str,
        category_id: str | None,
        ticket_number: int,
        parent_id: str | None = None,
        *,
        subject: str | None = None,
        description: str | None = None,
        custom_fields: dict[str, str] | None = None,
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
            "subject": subject,
            "description": description,
            "customFields": custom_fields or {},
        }
        logger.debug("DB insert_ticket(%s) number=%d parent=%s", ticket_id, ticket_number, parent_id)
        response = await self._client.table("ticket").insert(row).execute()
        rows = _unwrap(response)
        if self._on_write is not None:
            await self._on_write("ticket", ticket_id)
        return rows[0] if rows else {}

    async def get_tickets_by_parent(self: Any, parent_id: str) -> list[dict]:
        """Return all tickets whose ``parentId`` equals *parent_id*.

        Used to render a parent's sub-ticket children. Results are ordered
        newest-first by ``createdAt`` to match the project's list-query
        convention. Returns an empty list when the parent has no children.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_tickets_by_parent(%r)", parent_id)
        response = await (
            self._client.table("ticket").select("*").eq("parentId", parent_id).order("createdAt", desc=True).execute()
        )
        return _unwrap(response)

    async def get_ticket(self: Any, ticket_id: str) -> dict | None:
        """Fetch a ticket by its UUID primary key."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket(%r)", ticket_id)
        response = await self._client.table("ticket").select("*").eq("id", ticket_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_channel(self: Any, channel_id: str) -> dict | None:
        """Fetch a ticket by its Discord channel snowflake."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_by_channel(%r)", channel_id)
        response = await self._client.table("ticket").select("*").eq("channelId", channel_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_number(self: Any, guild_id: str, ticket_number: int) -> dict | None:
        """Fetch a ticket by guild snowflake and sequential *ticket_number*.

        Used by ``/reopen ticket:#0003`` to resolve a closed ticket from any
        channel — the original channel is deleted on close, so channel-scoped
        lookup is unusable for closed tickets. Guild-scoped by construction.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_by_number(guild=%s, number=%d)", guild_id, ticket_number)
        response = await (
            self._client.table("ticket").select("*").eq("guildId", guild_id).eq("ticketNumber", ticket_number).execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def update_ticket(self: Any, ticket_id: str, **kwargs: Any) -> None:
        """Update a ticket row with the given camelCase column values.

        Accepts keyword arguments matching the DB column names (e.g.
        ``status="closed"``, ``claimedBy=staff_id``).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB update_ticket(%s) %s", ticket_id, kwargs)
        await self._client.table("ticket").update(kwargs).eq("id", ticket_id).execute()

    async def get_stale_tickets(self: Any, guild_id: str, hours: int = 48) -> list[dict]:
        """Return open/claimed tickets with ``lastActivity`` older than *hours*.

        Used by the auto-close task to identify inactive tickets.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        logger.debug("DB get_stale_tickets(guild=%s, cutoff=%s)", guild_id, cutoff.isoformat())
        response = await (
            self._client.table("ticket")
            .select("*")
            .eq("guildId", guild_id)
            .in_("status", ["open", "claimed"])
            .lt("lastActivity", cutoff.isoformat())
            .execute()
        )
        return _unwrap(response)

    async def get_max_ticket_number(self: Any, guild_id: str) -> int:
        """Return the highest ``ticketNumber`` for a guild, or 0 if none exist."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_max_ticket_number(guild=%s)", guild_id)
        response = await (
            self._client.table("ticket")
            .select("ticketNumber")
            .eq("guildId", guild_id)
            .order("ticketNumber", desc=True)
            .limit(1)
            .execute()
        )
        rows = _unwrap(response)
        return rows[0]["ticketNumber"] if rows else 0

    async def get_open_ticket_channel_ids(self: Any, guild_id: str) -> list[str]:
        """Return channel IDs of all open/claimed tickets for a guild.

        Used on startup to rebuild the ticket channel cache for O(1)
        ``on_message`` lookups.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_open_ticket_channel_ids(guild=%s)", guild_id)
        response = await (
            self._client.table("ticket")
            .select("channelId")
            .eq("guildId", guild_id)
            .in_("status", ["open", "claimed"])
            .execute()
        )
        rows = _unwrap(response)
        return [r["channelId"] for r in rows]

    async def update_ticket_last_activity(self: Any, guild_id: str, channel_id: str, timestamp: str) -> None:
        """Set ``lastActivity`` for the ticket with the given channel ID in a guild.

        Called by the ``on_message`` listener — avoids a separate
        lookup-then-update round-trip.  Scoped by *guild_id* so one guild
        cannot modify another guild's tickets.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB update_ticket_last_activity(guild=%s, ch=%s)", guild_id, channel_id)
        await (
            self._client.table("ticket")
            .update({"lastActivity": timestamp})
            .eq("guildId", guild_id)
            .eq("channelId", channel_id)
            .execute()
        )
