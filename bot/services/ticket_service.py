"""TicketService — ticket lifecycle management with sequential numbering.

Implements the ticket business layer: create, close, claim, stale detection,
sub-ticket derivation, reopen, transfer, staff notes, and a cached set of
ticket channel IDs for fast O(1) ``on_message`` queries.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from bot.models.ticket import Ticket
from bot.models.ticket_note import TicketNote

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.logging_service import LoggingService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
NOTE_CAP = 50  # v1 per-ticket staff note limit (see design.md non-goals)


class TicketService:
    """Manages ticket lifecycle with sequential numbering and cache sync.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
    """

    __slots__ = ("_cache", "_db", "_ticket_channel_cache")

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
                        f"Failed to create ticket after {MAX_RETRIES} attempts (guild={guild_id})"
                    ) from exc

        # Unreachable — keep the type checker happy.
        raise RuntimeError(f"Failed to create ticket after {MAX_RETRIES} attempts (guild={guild_id})")

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
        now = datetime.now(UTC).isoformat()
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

    async def claim_ticket(self, ticket_id: str, claimed_by: str) -> Ticket:
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

    async def get_stale_tickets(self, guild_id: str, hours: int = 48) -> list[Ticket]:
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
            logger.debug("ticket_channel_cache synced: %d channels", len(channel_ids))
        else:
            self._ticket_channel_cache.clear()
            logger.debug("ticket_channel_cache cleared")

    # ----------------------------------------------------------------
    # Sub-tickets, reopen, transfer (slice 2)
    # ----------------------------------------------------------------

    async def create_subticket(
        self,
        parent_id: str,
        author_id: str,
        category_id: str | None,
        channel_id: str,
        *,
        guild_id: str,
    ) -> Ticket:
        """Create a child ticket linked to *parent_id*.

        Performs the four ``parentId`` integrity validations mandated by
        the spec — Supabase Transaction Mode has no DB FK enforcement, so
        these checks are the ONLY guard for the parent link:

        1. parent exists
        2. parent is not self-referential (``parent.parentId == parent.id``)
        3. parent is not itself a child (one level deep — no sub-of-sub)
        4. parent belongs to the same guild as the caller-supplied *guild_id*

        When ``parent_id`` is set the "one open ticket per user per category"
        constraint is skipped (carve-out). The current ``create_ticket`` path
        does not enforce that constraint, so the carve-out is structural.

        The caller creates the Discord channel first (mirrors
        :meth:`create_ticket`).

        Args:
            parent_id: UUID of the parent ticket.
            author_id: Discord user snowflake of the sub-ticket opener.
            category_id: Optional ticket_category UUID (label, not a channel).
            channel_id: Discord channel snowflake for the new sub-ticket.
            guild_id: Discord guild snowflake — MUST match the parent's guild.

        Returns:
            The newly created sub-ticket :class:`Ticket`.

        Raises:
            ValueError: If any parentId validation fails.
            RuntimeError: If all numbering retries are exhausted.
        """
        parent_row = await self._db.get_ticket(parent_id)
        if parent_row is None:
            raise ValueError(f"Parent ticket {parent_id} not found")
        parent = Ticket.from_db_row(parent_row)

        # 1. self-reference: the parent points to itself (corrupted row).
        if parent.parent_id is not None and parent.parent_id == parent.id:
            raise ValueError(f"Parent ticket {parent_id} is self-referential")

        # 2. one level deep: the parent must not already be a child.
        if parent.parent_id is not None:
            raise ValueError(f"Parent ticket {parent_id} is already a sub-ticket")

        # 3. same guild: the sub-ticket inherits the parent's guild.
        if parent.guild_id != guild_id:
            raise ValueError(f"Parent ticket {parent_id} belongs to a different guild")

        # Sequential numbering + insert (mirrors create_ticket). Carve-out:
        # parentId set → no one-open-ticket-per-user check is performed.
        for attempt in range(1, MAX_RETRIES + 1):
            current_max = await self._db.get_max_ticket_number(guild_id)
            ticket_number = current_max + 1
            logger.debug(
                "create_subticket attempt %d/%d: number=%d parent=%s",
                attempt,
                MAX_RETRIES,
                ticket_number,
                parent_id,
            )
            try:
                row = await self._db.insert_ticket(
                    guild_id=guild_id,
                    author_id=author_id,
                    channel_id=channel_id,
                    category_id=category_id,
                    ticket_number=ticket_number,
                    parent_id=parent_id,
                )
                ticket = Ticket.from_db_row(row)
                self._ticket_channel_cache.add(int(channel_id))
                logger.info(
                    "Sub-ticket #%d created (parent=%s, guild=%s, channel=%s)",
                    ticket_number,
                    parent_id,
                    guild_id,
                    channel_id,
                )
                return ticket
            except Exception as exc:
                logger.warning(
                    "Sub-ticket insert conflict on attempt %d/%d: %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"Failed to create sub-ticket after {MAX_RETRIES} attempts (guild={guild_id})"
                    ) from exc

        # Unreachable — keep the type checker happy.
        raise RuntimeError(f"Failed to create sub-ticket after {MAX_RETRIES} attempts (guild={guild_id})")

    async def reopen_ticket(self, ticket_id: str, *, guild: discord.Guild) -> Ticket:
        """Reopen a closed ticket in a freshly created Discord channel.

        Loads the closed ticket, creates a new channel in the guild's
        configured ticket Discord category (falling back to that same
        default — v1 stores only one Discord category per guild), then
        updates ``channelId``, sets ``status='open'``, clears
        ``closedAt``, and adds the new channel to the cache.

        The ticket row's ``categoryId`` is a ticket_category UUID (a
        label), not a Discord channel, so the guild-configured
        ``ticketCategoryId`` is the only resolvable Discord category.
        If it is missing or deleted, reopen fails.

        Args:
            ticket_id: UUID of the closed ticket to reopen.
            guild: The Discord guild the ticket lives in.

        Returns:
            The reopened :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist or no Discord ticket
                category is configured/available.
        """
        closed_row = await self._db.get_ticket(ticket_id)
        if closed_row is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        # B2: defense-in-depth status guard — only closed tickets can be
        # reopened. Prevents duplicate channel creation for open/claimed
        # tickets even if a caller bypasses the cog-layer guard. The cog
        # surfaces this message verbatim, so it MUST contain the actual
        # status and the user-facing Spanish wording.
        status = closed_row.get("status")
        if status != "closed":
            raise ValueError(
                f"Solo se pueden reabrir tickets cerrados. Estado actual: {status}"
            )

        guild_row = await self._db.get_guild(str(guild.id))
        category_channel = self._resolve_ticket_category(guild, guild_row)
        if category_channel is None:
            raise ValueError(f"No ticket category configured for guild {guild.id} — cannot reopen ticket {ticket_id}")

        # Build permission overwrites (everyone denied, bot + author + mod).
        overwrites: dict[
            discord.Role | discord.Member | discord.Object,
            discord.PermissionOverwrite,
        ] = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        author_id = closed_row.get("authorId")
        if author_id:
            try:
                author = guild.get_member(int(author_id))
                if author is not None:
                    overwrites[author] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            except (ValueError, TypeError):
                pass
        mod_role_id = (guild_row or {}).get("modRoleId")
        if mod_role_id:
            try:
                mod_role = guild.get_role(int(mod_role_id))
                if mod_role is not None:
                    overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            except (ValueError, TypeError):
                pass

        # Channel name from the existing ticket number (kept stable on reopen).
        ticket_number = closed_row.get("ticketNumber", 0)
        try:
            channel_name = f"ticket-{int(ticket_number):04d}"
        except (TypeError, ValueError):
            channel_name = "ticket"

        new_channel = await guild.create_text_channel(
            name=channel_name,
            category=category_channel,
            overwrites=overwrites,
            reason=f"Ticket {ticket_id} reopened",
        )

        await self._db.update_ticket(
            ticket_id,
            channelId=str(new_channel.id),
            status="open",
            closedAt=None,
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after reopen")
        ticket = Ticket.from_db_row(row)

        # New channel is now an active ticket channel — cache it.
        self._ticket_channel_cache.add(int(ticket.channel_id))

        logger.info("Ticket %s reopened (new channel=%s)", ticket_id, ticket.channel_id)
        return ticket

    @staticmethod
    def _resolve_ticket_category(guild: discord.Guild, guild_row: dict | None) -> discord.CategoryChannel | None:
        """Resolve the guild's configured Discord ticket category, or None.

        Returns ``None`` when no category is configured, the configured id
        is not a valid snowflake, the channel is missing, or the channel is
        not a ``CategoryChannel``.
        """
        if not guild_row:
            return None
        raw_id = guild_row.get("ticketCategoryId")
        if not raw_id:
            return None
        try:
            channel = guild.get_channel(int(raw_id))
        except (ValueError, TypeError):
            return None
        if isinstance(channel, discord.CategoryChannel):
            return channel
        return None

    async def transfer_ticket(
        self,
        ticket_id: str,
        new_claimed_by: str,
        actor_id: str,
        *,
        guild: discord.Guild | None = None,
        logging_service: LoggingService | None = None,
    ) -> Ticket:
        """Transfer a ticket's claim to *new_claimed_by* and audit the action.

        Mutates ``claimedBy`` (and sets ``status='claimed'`` — a transfer is
        an implicit (re)claim). After the DB mutation, emits a
        :class:`~bot.services.logging_service.LoggingService` audit embed
        (NOT a DB audit row — the current schema has no audit table, per the
        design decision). The audit is best-effort: it is skipped silently
        when *guild*/*logging_service* are unavailable or members cannot be
        resolved, so a logging failure never blocks the transfer.

        Args:
            ticket_id: UUID of the ticket to transfer.
            new_claimed_by: Discord user snowflake of the new claimer.
            actor_id: Discord user snowflake of the staff member performing
                the transfer (recorded in the audit).
            guild: The Discord guild — used to resolve Member objects for the
                audit embed. Optional (audit skipped when ``None``).
            logging_service: The bot's LoggingService. Optional.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist after the update.
        """
        await self._db.update_ticket(
            ticket_id,
            claimedBy=new_claimed_by,
            status="claimed",
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after transfer")
        ticket = Ticket.from_db_row(row)

        # Best-effort audit embed (LoggingService, not a DB audit table).
        if logging_service is not None and guild is not None:
            try:
                target = guild.get_member(int(new_claimed_by))
                moderator = guild.get_member(int(actor_id))
                if target is not None and moderator is not None:
                    await logging_service.log_moderation_action(
                        guild_id=str(guild.id),
                        action="Ticket Transfer",
                        target=target,
                        moderator=moderator,
                        reason=(f"Ticket {ticket_id} transferred from {actor_id} to {new_claimed_by}"),
                    )
            except Exception:
                logger.warning(
                    "Failed to log ticket transfer audit (ticket=%s)",
                    ticket_id,
                    exc_info=True,
                )

        logger.info(
            "Ticket %s transferred to %s by %s",
            ticket_id,
            new_claimed_by,
            actor_id,
        )
        return ticket

    # ----------------------------------------------------------------
    # Staff notes (slice 2)
    # ----------------------------------------------------------------

    async def create_note(self, ticket_id: str, author_id: str, content: str) -> TicketNote:
        """Add a staff note to a ticket.

        Notes are capped at :data:`NOTE_CAP` (50) per ticket. The cap is
        enforced by counting existing notes before insert.

        Args:
            ticket_id: UUID of the ticket to annotate.
            author_id: Discord user snowflake of the staff member.
            content: The note text.

        Returns:
            The newly created :class:`TicketNote`.

        Raises:
            ValueError: If the per-ticket note cap has been reached.
        """
        existing = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP)
        if len(existing) >= NOTE_CAP:
            raise ValueError(f"Note limit reached ({NOTE_CAP} notes per ticket)")
        row = await self._db.insert_ticket_note(ticket_id, author_id, content)
        note = TicketNote.from_db_row(row)
        logger.info("Note %s added to ticket %s by %s", note.id, ticket_id, author_id)
        return note

    async def get_notes(self, ticket_id: str) -> list[TicketNote]:
        """Return all staff notes for a ticket, newest-first.

        Delegates to :meth:`Database.get_ticket_notes` which orders by
        ``createdAt`` descending and caps at :data:`NOTE_CAP`.

        Args:
            ticket_id: UUID of the ticket.

        Returns:
            List of :class:`TicketNote` models (empty when none exist).
        """
        rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP)
        notes = [TicketNote.from_db_row(r) for r in rows]
        logger.debug("get_notes(ticket=%s): %d notes", ticket_id, len(notes))
        return notes

    async def delete_note(self, note_id: str, author_id: str, *, ticket_id: str) -> None:
        """Delete a staff note, enforcing author-only ownership.

        Ownership is verified by fetching the ticket's notes and matching
        the note's ``authorId``. A non-author or a note not attached to the
        given ticket is rejected before the DB delete.

        Args:
            note_id: UUID of the note to delete.
            author_id: Discord user snowflake of the requesting staff member.
            ticket_id: UUID of the ticket the note belongs to (required
                because the database layer exposes no single-note fetch).

        Raises:
            ValueError: If the note does not exist on the ticket or the
                requester is not the note's author.
        """
        rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP)
        target = next((r for r in rows if r.get("id") == note_id), None)
        if target is None:
            raise ValueError(f"Note {note_id} not found on ticket {ticket_id}")
        if target.get("authorId") != author_id:
            raise ValueError("Only the note author may delete this note")
        await self._db.delete_ticket_note(note_id)
        logger.info("Note %s deleted by %s", note_id, author_id)
