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
    ) -> dict[str, Any]:
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
        logger.debug("DB insert_ticket_note(%s) ticket=%s author=%s", note_id, ticket_id, author_id)
        response = await self._client.table("ticket_note").insert(row).execute()
        rows = _unwrap(response)
        if self._on_write is not None:
            await self._on_write("ticket_note", note_id)
        return rows[0] if rows else {}

    async def get_ticket_notes(self: Any, ticket_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return notes for a ticket, newest-first, capped by *limit*.

        The caller controls the cap (default 50, the v1 per-ticket note limit
        enforced in the service layer). Results are ordered by ``createdAt``
        descending.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_ticket_notes(ticket=%s, limit=%d)", ticket_id, limit)
        response = await (
            self._client.table("ticket_note")
            .select("*")
            .eq("ticketId", ticket_id)
            .order("createdAt", desc=True)
            .limit(limit)
            .execute()
        )
        return _unwrap(response)

    async def delete_ticket_note(self: Any, note_id: str) -> None:
        """Delete a staff note by its UUID primary key.

        Ownership authorization is enforced in the service layer before this
        call — the database layer performs the delete only.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB delete_ticket_note(%s)", note_id)
        await self._client.table("ticket_note").delete().eq("id", note_id).execute()

    async def get_recent_notes_for_dedup(
        self: Any, ticket_id: str, author_id: str, window_seconds: int = 2
    ) -> list[dict[str, Any]]:
        """Return notes by *author_id* on *ticket_id* created in the dedup window.

        Computes a cutoff of ``now() - window_seconds`` client-side and pushes
        it down as a ``createdAt >= cutoff`` filter, then returns the matching
        rows (``content`` is selected so callers can compare normalized hashes).
        The composite index ``idx_ticket_note_ticket_author_created`` backs this
        query. Dedup comparison itself happens in the service layer
        (:mod:`bot.services.ticket_invariants`) — this method only fetches the
        candidate rows.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        logger.debug(
            "DB get_recent_notes_for_dedup(ticket=%s, author=%s, cutoff=%s)",
            ticket_id,
            author_id,
            cutoff.isoformat(),
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
