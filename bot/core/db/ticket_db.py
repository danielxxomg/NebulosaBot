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

    async def get_tickets_by_parent(self: Any, parent_id: str, *, guild_id: str | None = None) -> list[dict[str, Any]]:
        """Return all tickets whose ``parentId`` equals *parent_id*.

        Guild-scoped by ``guildId`` — cross-guild children are never returned.
        Results are ordered newest-first by ``createdAt``. A missing
        ``guild_id`` raises ``ValueError("guild_id required")``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")
        if guild_id is None:
            raise ValueError("guild_id required")

        logger.debug("DB get_tickets_by_parent(%r, guild=%s)", parent_id, guild_id)
        query = self._client.table("ticket").select("*").eq("parentId", parent_id).eq("guildId", guild_id)
        response = await query.order("createdAt", desc=True).execute()
        return _unwrap(response)

    async def get_ticket(self: Any, ticket_id: str, *, guild_id: str | None = None) -> dict[str, Any] | None:
        """Fetch a ticket by its UUID primary key.

        Guild-scoped as ``WHERE guildId=:gid AND id=:id`` so a guild A caller
        cannot read a guild B ticket even when the UUID is known. Returns
        ``None`` when no eligible row exists. A missing ``guild_id`` raises
        ``ValueError("guild_id required")``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")
        if guild_id is None:
            raise ValueError("guild_id required")

        logger.debug("DB get_ticket(%r, guild=%s)", ticket_id, guild_id)
        query = self._client.table("ticket").select("*").eq("id", ticket_id).eq("guildId", guild_id)
        response = await query.execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def get_ticket_by_channel(
        self: Any, channel_id: str, *, guild_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch a ticket by its Discord channel snowflake.

        Guild-scoped as ``WHERE guildId=:gid AND channelId=:cid`` so
        cross-guild channel lookups return ``None``. A missing ``guild_id``
        raises ``ValueError("guild_id required")``.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")
        if guild_id is None:
            raise ValueError("guild_id required")

        logger.debug("DB get_ticket_by_channel(%r, guild=%s)", channel_id, guild_id)
        query = self._client.table("ticket").select("*").eq("channelId", channel_id).eq("guildId", guild_id)
        response = await query.execute()
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

        When ``guild_id`` is supplied as a keyword (``update_ticket(tid,
        guild_id=gid, status=...)``) the update is scoped as ``WHERE
        guildId=:gid AND id=:tid`` so cross-guild mutations match 0 rows.
        The ``guild_id`` key is not persisted as a column.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        guild_id = kwargs.pop("guild_id", None)
        logger.debug("DB update_ticket(%s, guild=%s) %s", ticket_id, guild_id, kwargs)
        query = self._client.table("ticket").update(kwargs).eq("id", ticket_id)
        if guild_id is not None:
            query = query.eq("guildId", guild_id)
        await query.execute()
        if self._on_write is not None and guild_id is not None:
            # Only echo when guild-scoped (ownership established by DB).
            await self._on_write("ticket", ticket_id)

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
        """Fetch the active (open/claimed) ticket for a guild+channel pair.

        Returns ``None`` when no active ticket maps to the given channel —
        either the channel has no ticket or the ticket is already closed.
        Used by the authoritative ``on_guild_channel_delete`` event and
        evidence-gated sweeps to detect zombie tickets.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_active_ticket_by_channel(guild=%s, ch=%s)", guild_id, channel_id)
        response = (
            await self._client.table("ticket")
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
        guild_id: str,
        ticket_id: str,
        *,
        expected_statuses: tuple[str, ...] = ("open", "claimed"),
        close_reason: str | None = None,
        transcript_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Conditionally close a ticket whose status is in *expected_statuses*.

        The transition is scoped by BOTH ``guild_id`` and ``ticket_id`` on the
        SELECT and the UPDATE, so a ticket in another guild can never be
        mutated even when its UUID is known. Returns the closed row on
        success, or ``None`` when the ticket is not in an expected status
        (already closed, nonexistent, other guild, or wrong status).

        The DB-level ``in_`` filter eliminates read-then-write races: two
        concurrent callers both targeting ``("open", "claimed")`` produce
        exactly one close mutation and one deterministic ``already_closed``
        (``None`` return). Because both the SELECT and the UPDATE carry the
        same status predicate, a status change between the two queries makes
        the UPDATE match 0 rows and the method returns ``None``.

        When *close_reason* is provided it is persisted on the row. When
        ``None``, the ``closeReason`` column is NOT included in the update
        so an existing value is preserved. When *transcript_url* is provided
        it is persisted as ``transcriptUrl``.

        Backwards compatibility: callers that already know the ticket's
        guild may pass ``ticket_id`` positionally with an explicit
        ``guild_id`` keyword (``transition_ticket_to_closed("t1",
        guild_id="g1")``) so the ``(ticket_id, ...)`` form keeps working.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug(
            "DB transition_ticket_to_closed(guild=%s, %s, expected=%s, reason=%s)",
            guild_id,
            ticket_id,
            expected_statuses,
            close_reason,
        )
        # Step 1: fetch the ticket only if it belongs to the guild AND
        # matches expected_statuses.
        response = (
            await self._client.table("ticket")
            .select("*")
            .eq("guildId", guild_id)
            .eq("id", ticket_id)
            .in_("status", list(expected_statuses))
            .execute()
        )
        rows = _unwrap(response)
        if not rows:
            return None

        # Step 2: update to closed, guarded by the same guild + status
        # predicates so a race or cross-guild probe mutates 0 rows.
        now = datetime.now(UTC).isoformat()
        update_data: dict[str, Any] = {
            "status": "closed",
            "closedAt": now,
        }
        if close_reason is not None:
            update_data["closeReason"] = close_reason
        if transcript_url is not None:
            update_data["transcriptUrl"] = transcript_url

        update_response = (
            await self._client.table("ticket")
            .update(update_data)
            .eq("guildId", guild_id)
            .eq("id", ticket_id)
            .in_("status", list(expected_statuses))
            .execute()
        )
        updated_rows = _unwrap(update_response)
        if not updated_rows:
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
