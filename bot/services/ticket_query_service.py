"""TicketQueryService — single owner for query + channel cache (S3.3A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bot.models.ticket import Ticket

if TYPE_CHECKING:
    from bot.core.database import Database

logger = logging.getLogger(__name__)


class TicketQueryService:
    """Single owner for ticket query + cached channel-id set.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
    """

    __slots__ = ("__dict__", "_db", "_ticket_channel_cache")

    def __init__(self, db: Database) -> None:
        self._db: Database = db
        self._ticket_channel_cache: set[int] = set()

    async def get_stale_tickets(self, guild_id: str, hours: int = 48) -> list[Ticket]:
        """Return open/claimed tickets with no activity for *hours*."""
        rows: list[dict[str, Any]] = await self._db.get_stale_tickets(guild_id, hours=hours)
        tickets = [Ticket.from_db_row(r) for r in rows]
        logger.debug(
            "get_stale_tickets(guild=%s, hours=%d): %d stale",
            guild_id,
            hours,
            len(tickets),
        )
        return tickets

    def is_ticket_channel(self, channel_id: int) -> bool:
        """Check whether *channel_id* belongs to an open/claimed ticket.

        O(1) set lookup — safe to call on every ``on_message`` event.
        """
        return channel_id in self._ticket_channel_cache

    def sync_channel_cache(self, channel_ids: set[int] | None = None) -> None:
        """Rebuild the ticket channel cache (replace or clear)."""
        if channel_ids is not None:
            self._ticket_channel_cache = channel_ids.copy()
            logger.debug("ticket_channel_cache synced: %d channels", len(channel_ids))
        else:
            self._ticket_channel_cache.clear()
            logger.debug("ticket_channel_cache cleared")

    def add_channel(self, channel_id: int) -> None:
        """Track *channel_id* as an active ticket channel."""
        self._ticket_channel_cache.add(channel_id)

    def discard_channel(self, channel_id: int) -> None:
        """Drop *channel_id* from the active ticket channel set (no error if absent)."""
        self._ticket_channel_cache.discard(channel_id)
