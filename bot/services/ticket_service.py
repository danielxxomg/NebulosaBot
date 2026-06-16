"""TicketService — ticket lifecycle management with sequential numbering.

Implements the ticket business layer: create, close, claim, stale detection,
and a cached set of ticket channel IDs for fast O(1) ``on_message`` queries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bot.models.ticket import Ticket

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class TicketService:
    """Manages ticket lifecycle with sequential numbering and cache sync.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
    """

    __slots__ = ("_db", "_cache", "_ticket_channel_cache")

    def __init__(self, db: Database, cache: TTLCache) -> None:
        self._db = db
        self._cache = cache
        # Channel IDs (int) of currently open tickets — used by the
        # on_message listener for O(1) early-return check.
        self._ticket_channel_cache: set[int] = set()

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def create_ticket(
        self,
        guild_id: str,
        author_id: str,
        category_id: str | None,
        channel_id: str,
    ) -> Ticket:
        """Create a new ticket with sequential numbering per guild.

        Uses ``MAX(ticketNumber) + 1`` with up to 3 retries on insert
        conflict.  The caller is responsible for creating the Discord
        channel first.

        Args:
            guild_id: Discord guild snowflake.
            author_id: Discord user snowflake of the ticket opener.
            category_id: Optional UUID of a :class:`TicketCategory`.
            channel_id: Discord channel snowflake for the ticket.

        Returns:
            The newly created :class:`Ticket`.

        Raises:
            RuntimeError: If all numbering retries are exhausted.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            current_max = await self._db.get_max_ticket_number(guild_id)
            ticket_number = current_max + 1
            logger.debug(
                "create_ticket attempt %d/%d: number=%d guild=%s",
                attempt,
                MAX_RETRIES,
                ticket_number,
                guild_id,
            )
            try:
                row = await self._db.insert_ticket(
                    guild_id=guild_id,
                    author_id=author_id,
                    channel_id=channel_id,
                    category_id=category_id,
                    ticket_number=ticket_number,
                )
                ticket = Ticket.from_db_row(row)
                self._ticket_channel_cache.add(int(channel_id))
                logger.info(
                    "Ticket #%d created (guild=%s, channel=%s)",
                    ticket_number,
                    guild_id,
                    channel_id,
                )
                return ticket
            except Exception as exc:
                logger.warning(
                    "Ticket insert conflict on attempt %d/%d: %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"Failed to create ticket after {MAX_RETRIES} "
                        f"attempts (guild={guild_id})"
                    ) from exc

        # Unreachable — keep the type checker happy.
        raise RuntimeError(
            f"Failed to create ticket after {MAX_RETRIES} attempts (guild={guild_id})"
        )

    async def close_ticket(
        self,
        ticket_id: str,
        closed_by: str | None = None,
        *,
        transcript_url: str | None = None,
    ) -> Ticket:
        """Close a ticket and optionally attach a transcript URL.

        Sets ``status='closed'`` and ``closedAt`` to the current UTC time.

        Args:
            ticket_id: UUID of the ticket to close.
            closed_by: Discord user snowflake of the closer (logged only).
            transcript_url: Optional URL pointing to the uploaded transcript.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist after the update.
        """
        now = datetime.now(timezone.utc).isoformat()
        update_kwargs: dict[str, str | None] = {
            "status": "closed",
            "closedAt": now,
        }
        if transcript_url is not None:
            update_kwargs["transcriptUrl"] = transcript_url

        await self._db.update_ticket(ticket_id, **update_kwargs)

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after close")
        ticket = Ticket.from_db_row(row)

        # Remove channel from cache so the on_message listener skips it.
        self._ticket_channel_cache.discard(int(ticket.channel_id))

        logger.info(
            "Ticket %s closed by %s%s",
            ticket_id,
            closed_by or "unknown",
            f" (transcript: {transcript_url})" if transcript_url else "",
        )
        return ticket

    async def claim_ticket(
        self, ticket_id: str, claimed_by: str
    ) -> Ticket:
        """Claim a ticket, assigning it to a staff member.

        Sets ``status='claimed'`` and ``claimedBy`` to the given user ID.

        Args:
            ticket_id: UUID of the ticket to claim.
            claimed_by: Discord user snowflake of the claiming staff member.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist after the update.
        """
        await self._db.update_ticket(
            ticket_id,
            status="claimed",
            claimedBy=claimed_by,
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after claim")
        ticket = Ticket.from_db_row(row)

        logger.info("Ticket %s claimed by %s", ticket_id, claimed_by)
        return ticket

    async def get_stale_tickets(
        self, guild_id: str, hours: int = 48
    ) -> list[Ticket]:
        """Return open/claimed tickets with no activity for *hours*.

        Args:
            guild_id: Discord guild snowflake.
            hours: Inactivity threshold in hours (default 48).

        Returns:
            List of :class:`Ticket` models that are stale.
        """
        rows = await self._db.get_stale_tickets(guild_id, hours=hours)
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
        """Rebuild the ticket channel cache.

        If *channel_ids* is provided, replaces the cache with those IDs
        (used by the cog after a startup DB scan).  If omitted, clears
        the cache — the cog is expected to repopulate it afterwards.

        Args:
            channel_ids: Optional set of Discord channel IDs (int) for
                all currently open or claimed tickets.
        """
        if channel_ids is not None:
            self._ticket_channel_cache = channel_ids.copy()
            logger.debug(
                "ticket_channel_cache synced: %d channels", len(channel_ids)
            )
        else:
            self._ticket_channel_cache.clear()
            logger.debug("ticket_channel_cache cleared")
