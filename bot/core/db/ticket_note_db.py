"""TicketNoteDBMixin — ticket_note table operations for the Database facade."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class TicketNoteDBMixin:
    """Ticket note CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def insert_ticket_note(
        self: Any,
        ticket_id: str,
        author_id: str,
        content: str,
        *,
        guild_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a staff note on a ticket and return the persisted row.

        Generates a v4 UUID for the primary key. The ``createdAt`` timestamp
        is set by the database default clause (``NOW()``) — it is not set
        client-side. Notes are staff-only (not visible to the ticket opener).

        When *guild_id* is provided the ticket's ownership is validated before
        insert: the ticket must exist and have ``guildId==guild_id``, otherwise
        ``ValueError("cross_guild_denied")`` is raised and no row is inserted.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        if guild_id is not None:
            ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
            ticket_data = _unwrap(ticket_rows)
            if not ticket_data or ticket_data[0].get("guildId") != guild_id:
                raise ValueError("cross_guild_denied")

        note_id = str(uuid.uuid4())
        row = {
            "id": note_id,
            "ticketId": ticket_id,
            "authorId": author_id,
            "content": content,
        }
        logger.debug("DB insert_ticket_note(%s) ticket=%s author=%s guild=%s", note_id, ticket_id, author_id, guild_id)
        response = await self._client.table("ticket_note").insert(row).execute()
        rows = _unwrap(response)
        if self._on_write is not None:
            await self._on_write("ticket_note", note_id)
        return rows[0] if rows else {}

    async def get_ticket_notes(
        self: Any, ticket_id: str, limit: int = 50, *, guild_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return notes for a ticket, newest-first, capped by *limit*.

        The caller controls the cap (default 50, the v1 per-ticket note limit
        enforced in the service layer). Results are ordered by ``createdAt``
        descending. When *guild_id* is provided ownership is validated first:
        a mismatched guild returns ``[]`` without leaking notes.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        if guild_id is not None:
            ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
            ticket_data = _unwrap(ticket_rows)
            if not ticket_data or ticket_data[0].get("guildId") != guild_id:
                return []

        logger.debug("DB get_ticket_notes(ticket=%s, limit=%d, guild=%s)", ticket_id, limit, guild_id)
        response = await (
            self._client.table("ticket_note")
            .select("*")
            .eq("ticketId", ticket_id)
            .order("createdAt", desc=True)
            .limit(limit)
            .execute()
        )
        return _unwrap(response)

    async def delete_ticket_note(
        self: Any, note_id: str, *, guild_id: str | None = None, ticket_id: str | None = None
    ) -> None:
        """Delete a staff note by its UUID primary key.

        When *guild_id* and *ticket_id* are provided the ticket ownership is
        validated before delete; a cross-guild request raises
        ``ValueError("cross_guild_denied")`` and performs no delete.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        if guild_id is not None and ticket_id is not None:
            ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
            ticket_data = _unwrap(ticket_rows)
            if not ticket_data or ticket_data[0].get("guildId") != guild_id:
                raise ValueError("cross_guild_denied")
            # Also ensure the note belongs to the claimed ticket
            note_rows = await self._client.table("ticket_note").select("ticketId").eq("id", note_id).execute()
            note_data = _unwrap(note_rows)
            if not note_data or note_data[0].get("ticketId") != ticket_id:
                raise ValueError("cross_guild_denied")

        logger.debug("DB delete_ticket_note(%s, guild=%s)", note_id, guild_id)
        await self._client.table("ticket_note").delete().eq("id", note_id).execute()

    async def get_recent_notes_for_dedup(
        self: Any, ticket_id: str, author_id: str, window_seconds: int = 2, *, guild_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return notes by *author_id* on *ticket_id* created in the dedup window.

        Computes a cutoff of ``now() - window_seconds`` client-side and pushes
        it down as a ``createdAt >= cutoff`` filter, then returns the matching
        rows (``content`` is selected so callers can compare normalized hashes).
        The composite index ``idx_ticket_note_ticket_author_created`` backs this
        query. When *guild_id* is provided ownership is validated first; a
        mismatched guild returns ``[]`` without leaking content.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        if guild_id is not None:
            ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
            ticket_data = _unwrap(ticket_rows)
            if not ticket_data or ticket_data[0].get("guildId") != guild_id:
                return []

        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        logger.debug(
            "DB get_recent_notes_for_dedup(ticket=%s, author=%s, cutoff=%s, guild=%s)",
            ticket_id,
            author_id,
            cutoff.isoformat(),
            guild_id,
        )
        response = await (
            self._client.table("ticket_note")
            .select("content")
            .eq("ticketId", ticket_id)
            .eq("authorId", author_id)
            .gte("createdAt", cutoff.isoformat())
            .execute()
        )
        return _unwrap(response)
