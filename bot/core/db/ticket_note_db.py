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

        Guild-scoped: the ticket's ownership is validated before insert — the
        ticket must exist and have ``guildId==guild_id``, otherwise
        ``ValueError("cross_guild_denied")`` is raised and no row is inserted.
        A missing ``guild_id`` raises ``ValueError("guild_id required")``.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

        ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
        ticket_data = _unwrap(ticket_rows)
        if not ticket_data or ticket_data[0].get("guildId") != guild_id:
            msg = "cross_guild_denied"
            raise ValueError(msg)

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

        Guild-scoped: ownership is validated first — a mismatched guild returns
        ``[]`` without leaking notes. A missing ``guild_id`` raises
        ``ValueError("guild_id required")``.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

        ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
        ticket_data = _unwrap(ticket_rows)
        if not ticket_data or ticket_data[0].get("guildId") != guild_id:
            return []

        logger.debug("DB get_ticket_notes(ticket=%s, limit=%d, guild=%s)", ticket_id, limit, guild_id)
        response = await (
            self._client
            .table("ticket_note")
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

        Guild-scoped: ticket ownership is validated before delete; a missing
        ``guild_id``/``ticket_id`` raises ``ValueError("guild_id required")``,
        and a cross-guild request raises ``ValueError("cross_guild_denied")``.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None or ticket_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

        ticket_rows = await self._client.table("ticket").select("guildId").eq("id", ticket_id).execute()
        ticket_data = _unwrap(ticket_rows)
        if not ticket_data or ticket_data[0].get("guildId") != guild_id:
            msg = "cross_guild_denied"
            raise ValueError(msg)
        # Also ensure the note belongs to the claimed ticket
        note_rows = await self._client.table("ticket_note").select("ticketId").eq("id", note_id).execute()
        note_data = _unwrap(note_rows)
        if not note_data or note_data[0].get("ticketId") != ticket_id:
            msg = "cross_guild_denied"
            raise ValueError(msg)

        logger.debug("DB delete_ticket_note(%s, guild=%s)", note_id, guild_id)
        await self._client.table("ticket_note").delete().eq("id", note_id).execute()

    async def get_recent_notes_for_dedup(
        self: Any, ticket_id: str, author_id: str, window_seconds: int = 2, *, guild_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return notes by *author_id* on *ticket_id* created in the dedup window.

        Guild-scoped: ownership validated first; missing ``guild_id`` raises
        ``ValueError("guild_id required")``, mismatched guild returns ``[]``.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

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
            self._client
            .table("ticket_note")
            .select("content")
            .eq("ticketId", ticket_id)
            .eq("authorId", author_id)
            .gte("createdAt", cutoff.isoformat())
            .execute()
        )
        return _unwrap(response)
