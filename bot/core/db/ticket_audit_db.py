"""TicketAuditDBMixin — ticket_audit table operations for the Database facade."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class TicketAuditDBMixin:
    """Ticket audit log operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def insert_audit_row(
        self: Any,
        guild_id: str,
        ticket_id: str,
        action: str,
        actor_id: str | None,
        outcome: str,
        reason: str | None,
    ) -> dict:
        """Insert a ``ticket_audit`` row and return the persisted row.

        Generates a v4 UUID for the primary key (matches the project's
        ``insert_ticket_note`` / ``insert_infraction`` convention). The
        ``createdAt`` timestamp is set by the database ``DEFAULT now()`` — it
        is NOT set client-side. ``actor_id`` and ``reason`` are nullable to
        support system-originated actions (auto-close) and success rows
        without a detail reason.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        audit_id = str(uuid.uuid4())
        row = {
            "id": audit_id,
            "guildId": guild_id,
            "ticketId": ticket_id,
            "action": action,
            "actorId": actor_id,
            "outcome": outcome,
            "reason": reason,
        }
        logger.debug("DB insert_audit_row(%s) action=%s outcome=%s", audit_id, action, outcome)
        response = await self._client.table("ticket_audit").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

    async def get_audit_rows(self: Any, guild_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return ``ticket_audit`` rows for a guild, newest-first, paginated.

        Guild-scoped by an ``eq("guildId")`` filter so rows from other guilds
        cannot leak. Ordered by ``createdAt`` DESC. Pagination via *limit* and
        *offset* backs the dashboard audit panel.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_audit_rows(guild=%s, limit=%d, offset=%d)", guild_id, limit, offset)
        response = await (
            self._client.table("ticket_audit")
            .select("*")
            .eq("guildId", guild_id)
            .order("createdAt", desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        return _unwrap(response)
