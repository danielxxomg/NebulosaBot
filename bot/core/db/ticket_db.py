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
    ) -> dict[str, Any]:
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

    async def get_tickets_by_parent(self: Any, parent_id: str) -> list[dict[str, Any]]:
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

    async def get_ticket(self: Any, ticket_id: str) -> dict[str, Any] | None:
        """Fetch a ticket by its UUID primary key."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket(%r)", ticket_id)
        response = await self._client.table("ticket").select("*").eq("id", ticket_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_channel(self: Any, channel_id: str) -> dict[str, Any] | None:
        """Fetch a ticket by its Discord channel snowflake."""
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_by_channel(%r)", channel_id)
        response = await self._client.table("ticket").select("*").eq("channelId", channel_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_number(self: Any, guild_id: str, ticket_number: int) -> dict[str, Any] | None:
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

    async def get_stale_tickets(self: Any, guild_id: str, hours: int = 48) -> list[dict[str, Any]]:
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

    async def count_user_open_tickets_in_category(
        self: Any,
        guild_id: str,
        author_id: str,
        category_id: str,
        *,
        exclude_ticket_id: str | None = None,
    ) -> int:
        """Return the number of open/claimed tickets for *author_id* in *category_id*.

        Uses ``count="exact"`` to avoid fetching all rows — the server
        returns the count directly.  Scoped by *guild_id* so one guild
        cannot see another guild's ticket counts.

        When *exclude_ticket_id* is provided, that ticket is excluded from
        the count (used on the edit path so the ticket being edited does not
        count against itself).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB count_user_open_tickets_in_category(%s, %s, %s, exclude=%s)",
            guild_id,
            author_id,
            category_id,
            exclude_ticket_id,
        )
        query = (
            self._client.table("ticket")
            .select("id", count="exact")
            .eq("guildId", guild_id)
            .eq("authorId", author_id)
            .eq("categoryId", category_id)
            .in_("status", ["open", "claimed"])
        )
        if exclude_ticket_id is not None:
            query = query.neq("id", exclude_ticket_id)
        response = await query.execute()
        return response.count or 0

    async def get_active_ticket_by_channel(
        self: Any,
        guild_id: str,
        channel_id: str,
    ) -> dict[str, Any] | None:
        """Fetch an active (open/claimed) ticket by guild + channel.

        Used by channel-delete repair to find the ticket that maps to a
        deleted Discord channel. Returns ``None`` when no active ticket
        matches.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_active_ticket_by_channel(guild=%s, ch=%s)", guild_id, channel_id)
        response = await (
            self._client.table("ticket")
            .select("*")
            .eq("guildId", guild_id)
            .eq("channelId", channel_id)
            .in_("status", ["open", "claimed"])
            .execute()
        )
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def transition_ticket_to_closed(
        self: Any,
        ticket_id: str,
        *,
        expected_statuses: tuple[str, ...] = ("open", "claimed"),
        close_reason: str | None = None,
        transcript_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Conditionally close a ticket only if its status matches *expected_statuses*.

        Eliminates read-then-write races by applying the status predicate to
        both the SELECT and the UPDATE. When the ticket is already outside
        the expected statuses (e.g. already closed), returns ``None`` and
        performs no mutation.

        Args:
            ticket_id: UUID of the ticket to close.
            expected_statuses: Statuses eligible for this transition.
            close_reason: Optional close reason to persist. When ``None``,
                the column is NOT included in the update (non-overwriting).
            transcript_url: Optional transcript URL to persist. When
                ``None``, the column is NOT included in the update.

        Returns:
            The closed row dict on success, or ``None`` when the ticket
            was not in an expected status.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB transition_ticket_to_closed(%s) expected=%s", ticket_id, expected_statuses)

        # SELECT with status predicate — the DB filters to eligible rows.
        select_response = await (
            self._client.table("ticket")
            .select("*")
            .eq("id", ticket_id)
            .in_("status", list(expected_statuses))
            .execute()
        )
        rows = _unwrap(select_response)
        if not rows:
            return None

        # Build the update payload — only include fields that were provided.
        now = datetime.now(UTC).isoformat()
        update_payload: dict[str, Any] = {
            "status": "closed",
            "closedAt": now,
        }
        if close_reason is not None:
            update_payload["closeReason"] = close_reason
        if transcript_url is not None:
            update_payload["transcriptUrl"] = transcript_url

        # UPDATE with the same status predicate — zero-row guard.
        update_response = await (
            self._client.table("ticket")
            .update(update_payload)
            .eq("id", ticket_id)
            .in_("status", list(expected_statuses))
            .select("*")
            .execute()
        )
        updated_rows = _unwrap(update_response)
        if not updated_rows:
            # Race: status changed between SELECT and UPDATE. No mutation.
            return None

        if self._on_write is not None:
            await self._on_write("ticket", ticket_id)

        return updated_rows[0]

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
