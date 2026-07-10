"""TicketService — ticket lifecycle management with sequential numbering.

Implements the ticket business layer: create, close, claim, stale detection,
sub-ticket derivation, reopen, transfer, staff notes, and a cached set of
ticket channel IDs for fast O(1) ``on_message`` queries.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from bot.models.ticket import Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_invariants import (
    check_can_add_note,
    check_can_claim,
    check_can_close,
    check_can_delete_note,
    check_can_reopen,
    check_can_transfer,
    check_can_unclaim,
    check_subticket_parent,
    compute_note_hash,
    is_duplicate_note,
)
from bot.utils.ticket_helpers import (
    build_ticket_overwrites,
    resolve_category_name,
    resolve_member_safe,
    resolve_mod_role,
    sanitize_channel_name,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.logging_service import LoggingService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
NOTE_CAP = 50  # v1 per-ticket staff note limit (see design.md non-goals)
CHANNEL_DELETE_DELAY = 5  # seconds before deleting a closed ticket channel


class TicketCategoryNotConfiguredError(ValueError):
    """Raised when the guild's ticket Discord category is not configured or is deleted.

    The cog catches this and surfaces an actionable i18n embed mentioning
    /setup, /create_category, and the dashboard URL.
    """


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
        *,
        subject: str | None = None,
        description: str | None = None,
        custom_fields: dict[str, str] | None = None,
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
                    subject=subject,
                    description=description,
                    custom_fields=custom_fields,
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
        pre = await self._db.get_ticket(ticket_id)
        if pre is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_close(pre.get("status", ""))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "close", closed_by, "denied", str(exc))
            raise

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

        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "close", closed_by, "success", None)
        except Exception:
            logger.warning("Failed to write close audit row for ticket %s", ticket_id, exc_info=True)
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
        Enforces the claim invariant (open + unclaimed) BEFORE mutating and
        writes a ``ticket_audit`` row on both success and denied paths.

        Args:
            ticket_id: UUID of the ticket to claim.
            claimed_by: Discord user snowflake of the claiming staff member.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist or the claim invariant
                fails (non-open status, already claimed).
        """
        pre = await self._db.get_ticket(ticket_id)
        if pre is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_claim(pre.get("status", ""), pre.get("claimedBy"))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "claim", claimed_by, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            status="claimed",
            claimedBy=claimed_by,
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after claim")
        ticket = Ticket.from_db_row(row)

        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "claim", claimed_by, "success", None)
        except Exception:
            logger.warning("Failed to write claim audit row for ticket %s", ticket_id, exc_info=True)
        logger.info("Ticket %s claimed by %s", ticket_id, claimed_by)
        return ticket

    async def unclaim_ticket(
        self,
        ticket_id: str,
        actor_id: str,
        *,
        is_mod: bool,
    ) -> Ticket:
        """Unclaim a ticket, releasing it back to open status.

        Sets ``status='open'`` and ``claimedBy`` to ``None``. Enforces the
        unclaim invariant (claimer OR mod) BEFORE mutating and writes a
        ``ticket_audit`` row on both success and denied paths.

        Args:
            ticket_id: UUID of the ticket to unclaim.
            actor_id: Discord user snowflake of the actor requesting unclaim.
            is_mod: Whether the actor has the moderator role.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist, is not claimed, or
                the actor is neither the claimer nor a mod.
        """
        pre = await self._db.get_ticket(ticket_id)
        if pre is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_unclaim(actor_id, pre, is_mod=is_mod)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "unclaim", actor_id, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            status="open",
            claimedBy=None,
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after unclaim")
        ticket = Ticket.from_db_row(row)

        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "unclaim", actor_id, "success", None)
        except Exception:
            logger.warning("Failed to write unclaim audit row for ticket %s", ticket_id, exc_info=True)
        logger.info("Ticket %s unclaimed by %s", ticket_id, actor_id)
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
            await self._db.insert_audit_row(
                guild_id,
                parent_id,
                "subticket_create",
                author_id,
                "denied",
                f"Parent ticket {parent_id} not found",
            )
            raise ValueError(f"Parent ticket {parent_id} not found")
        parent = Ticket.from_db_row(parent_row)
        parent_guild_id = parent_row.get("guildId", "")

        # 1. self-reference: the parent points to itself (corrupted row) —
        #    kept inline for a more specific message than the pure helper's
        #    depth-limit message (check_subticket_parent would raise "depth"
        #    because parentId is non-None, which is less actionable).
        if parent.parent_id is not None and parent.parent_id == parent.id:
            await self._db.insert_audit_row(
                guild_id,
                parent_id,
                "subticket_create",
                author_id,
                "denied",
                f"Parent ticket {parent_id} is self-referential",
            )
            raise ValueError(f"Parent ticket {parent_id} is self-referential")

        # 2+3. FK / depth / cross-guild — delegated to the pure invariant.
        #    current_id is None because the child UUID is generated inside
        #    insert_ticket (server-side default), so the parent==child self
        #    check is structurally unreachable here.
        try:
            check_subticket_parent(parent_row, parent_guild_id, guild_id, current_id=None)
        except ValueError as exc:
            # CRITICAL 4: audit the denial scoped to the CALLER's guild (the
            # operation origin), not the parent's guild — a cross-guild
            # attempt's denial must land in the caller's audit trail, not the
            # parent guild's.
            await self._db.insert_audit_row(guild_id, parent_id, "subticket_create", author_id, "denied", str(exc))
            raise

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
                await self._db.insert_audit_row(guild_id, ticket.id, "subticket_create", author_id, "success", None)
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

        Creates a new channel, updates ``channelId``/``status``/``closedAt``,
        and adds the new channel to the cache.
        """
        closed_row = await self._db.get_ticket(ticket_id)
        if closed_row is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = closed_row.get("guildId", "")

        # B2: defense-in-depth status guard — only closed tickets can be
        # reopened. Prevents duplicate channel creation for open/claimed
        # tickets even if a caller bypasses the cog-layer guard. The cog
        # surfaces this message verbatim, so it MUST contain the actual
        # status and the user-facing Spanish wording. Reuse the pure
        # invariant helper so the rule lives in ONE place.
        try:
            check_can_reopen(closed_row.get("status", ""))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "denied", str(exc))
            # Translate to the user-facing Spanish message the cog surfaces
            # verbatim (preserves the existing contract).
            raise ValueError(
                f"Solo se pueden reabrir tickets cerrados. Estado actual: {closed_row.get('status')}"
            ) from exc

        guild_row = await self._db.get_guild(str(guild.id))
        category_channel = self._resolve_ticket_category(guild, guild_row)
        if category_channel is None:
            err = f"No ticket category configured for guild {guild.id} — cannot reopen ticket {ticket_id}"
            await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "denied", err)
            raise TicketCategoryNotConfiguredError(err)

        new_channel = await self._build_reopen_channel(
            guild, closed_row, guild_row, category_channel, ticket_id,
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

        await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "success", None)
        logger.info("Ticket %s reopened (new channel=%s)", ticket_id, ticket.channel_id)
        return ticket

    @staticmethod
    def _resolve_ticket_category(guild: discord.Guild, guild_row: dict[str, Any] | None) -> discord.CategoryChannel | None:
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

    async def _build_reopen_channel(
        self,
        guild: discord.Guild,
        closed_row: dict[str, Any],
        guild_row: dict[str, Any] | None,
        category_channel: discord.CategoryChannel,
        ticket_id: str,
    ) -> discord.TextChannel:
        """Build and create the Discord channel for a ticket reopen.

        Resolves permission overwrites, category name, and author via
        the pure helper functions in ``ticket_helpers``.
        """
        # Resolve principals via pure helpers.
        author_id = closed_row.get("authorId")
        author = resolve_member_safe(guild, author_id)
        mod_role_id = (guild_row or {}).get("modRoleId")
        mod_role = resolve_mod_role(guild, mod_role_id)

        overwrites = build_ticket_overwrites(guild, author, mod_role)

        # Channel name from sanitized category + author + ticket number.
        ticket_number = closed_row.get("ticketNumber", 0)
        try:
            ticket_number = int(ticket_number)
        except (TypeError, ValueError):
            ticket_number = 0

        category_name = await resolve_category_name(
            self._db, closed_row.get("categoryId"), fallback="ticket",
        )

        display_name = author.display_name if author is not None else "user"
        channel_name = sanitize_channel_name(category_name, display_name, ticket_number)

        return await guild.create_text_channel(
            name=channel_name,
            category=category_channel,
            overwrites=overwrites,
            reason=f"Ticket {ticket_id} reopened",
        )

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

        Emits a best-effort LoggingService audit embed when *guild* and
        *logging_service* are available.  A logging failure never blocks
        the transfer.
        """
        pre = await self._db.get_ticket(ticket_id)
        if pre is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_transfer(pre.get("status", ""), pre.get("claimedBy"), new_claimed_by)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "transfer", actor_id, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            claimedBy=new_claimed_by,
            status="claimed",
        )

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after transfer")
        ticket = Ticket.from_db_row(row)

        await self._db.insert_audit_row(ticket.guild_id, ticket_id, "transfer", actor_id, "success", None)

        # Best-effort audit embed (LoggingService, not a DB audit table).
        if logging_service is not None and guild is not None:
            try:
                target = resolve_member_safe(guild, new_claimed_by)
                moderator = resolve_member_safe(guild, actor_id)
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
        ticket_row = await self._db.get_ticket(ticket_id)
        guild_id = (ticket_row or {}).get("guildId", "")

        try:
            check_can_add_note(len(existing), NOTE_CAP)
            recent = await self._db.get_recent_notes_for_dedup(ticket_id, author_id, 2)
            recent_hashes = [compute_note_hash(r.get("content", "")) for r in recent]
            new_hash = compute_note_hash(content)
            if is_duplicate_note(new_hash, author_id, recent_hashes):
                raise ValueError(
                    "Duplicate note (same author submitted the same normalized "
                    "content within the 2-second dedup window)"
                )
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "note_add", author_id, "denied", str(exc))
            raise

        row = await self._db.insert_ticket_note(ticket_id, author_id, content)
        note = TicketNote.from_db_row(row)
        await self._db.insert_audit_row(guild_id, ticket_id, "note_add", author_id, "success", None)
        logger.info("Note %s added to ticket %s by %s", note.id, ticket_id, author_id)
        return note

    async def get_notes(self, ticket_id: str) -> list[TicketNote]:
        """Return all staff notes for a ticket, newest-first.

        Delegates to :meth:`Database.get_ticket_notes` which orders by
        ``createdAt`` descending and caps at :data:`NOTE_CAP`. Per the
        ``ticket-service`` audit requirement, the list operation writes a
        ``note_list`` audit row (outcome=success) scoped to the ticket's
        guild (resolved via a pre-read of the ticket row).

        Args:
            ticket_id: UUID of the ticket.

        Returns:
            List of :class:`TicketNote` models (empty when none exist).
        """
        rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP)
        notes = [TicketNote.from_db_row(r) for r in rows]
        ticket_row = await self._db.get_ticket(ticket_id)
        guild_id = (ticket_row or {}).get("guildId", "")
        await self._db.insert_audit_row(guild_id, ticket_id, "note_list", None, "success", None)
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
        ticket_row = await self._db.get_ticket(ticket_id)
        guild_id = (ticket_row or {}).get("guildId", "")
        target = next((r for r in rows if r.get("id") == note_id), None)

        try:
            if target is None:
                raise ValueError(f"Note {note_id} not found on ticket {ticket_id}")
            check_can_delete_note(target.get("authorId", ""), author_id)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "note_delete", author_id, "denied", str(exc))
            raise

        await self._db.delete_ticket_note(note_id)
        await self._db.insert_audit_row(guild_id, ticket_id, "note_delete", author_id, "success", None)
        logger.info("Note %s deleted by %s", note_id, author_id)

    # ----------------------------------------------------------------
    # Orchestration helpers (PR4 extraction)
    # ----------------------------------------------------------------

    async def create_ticket_channel(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        author: discord.Member,
        *,
        guild_id: str,
        category_name: str,
        category_id: str | None = None,
        mod_role: discord.Role | None = None,
        parent_id: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        custom_fields: dict[str, str] | None = None,
    ) -> tuple[discord.TextChannel, Ticket]:
        """Create a ticket Discord channel, insert the ticket row, and rename if needed.

        When *parent_id* is set, uses :meth:`create_subticket` to enforce
        parentId invariants.  On row-insert failure the channel is deleted
        before re-raising.
        """
        # Compute tentative channel name from DB max + 1.
        tentative_max = await self._db.get_max_ticket_number(guild_id)
        tentative_name = sanitize_channel_name(
            category_name, author.display_name, tentative_max + 1,
        )

        overwrites = build_ticket_overwrites(guild, author, mod_role)

        channel = await guild.create_text_channel(
            name=tentative_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {author}",
        )
        logger.info("Ticket channel created: %s (guild=%s, author=%s)", channel.id, guild.id, author.id)

        try:
            if parent_id is not None:
                ticket = await self.create_subticket(
                    parent_id=parent_id,
                    author_id=str(author.id),
                    category_id=category_id,
                    channel_id=str(channel.id),
                    guild_id=guild_id,
                )
            else:
                ticket = await self.create_ticket(
                    guild_id=guild_id,
                    author_id=str(author.id),
                    category_id=category_id,
                    channel_id=str(channel.id),
                    subject=subject,
                    description=description,
                    custom_fields=custom_fields,
                )
        except Exception:
            logger.exception("Ticket row creation failed — cleaning up channel %s", channel.id)
            with contextlib.suppress(discord.HTTPException):
                await channel.delete(reason="Ticket row creation failed")
            raise

        actual_name = sanitize_channel_name(
            category_name, author.display_name, ticket.ticket_number,
        )
        if channel.name != actual_name:
            try:
                await channel.edit(name=actual_name)
            except discord.HTTPException:
                logger.warning("Failed to rename ticket channel %s to %s", channel.id, actual_name)

        return channel, ticket

    async def close_ticket_full(
        self,
        channel: discord.TextChannel,
        ticket: Ticket,
        closed_by: str,
        *,
        bot: NebulosaBot,
        manual: bool = True,
    ) -> str | None:
        """Close a single ticket end-to-end: transcript -> upload -> DB -> delete.

        When *manual* is ``True``, a visual countdown edits a message
        from 5 to 1 before deletion.  When ``False``, the channel is
        deleted silently after a short delay.

        Returns:
            The transcript URL if uploaded, ``None`` otherwise.
        """
        guild = channel.guild
        transcript_url: str | None = None
        transcript_service = bot.transcript_service
        if transcript_service is not None:
            try:
                transcript_file = await transcript_service.generate(channel)
                log_channel: discord.TextChannel | None = None
                guild_service = bot.guild_service
                if guild_service is not None:
                    try:
                        config = await guild_service.get_config(str(guild.id))
                        if config.log_channel_id:
                            ch = guild.get_channel(int(config.log_channel_id))
                            if isinstance(ch, discord.TextChannel):
                                log_channel = ch
                    except (ValueError, TypeError):
                        logger.warning(
                            "Invalid log_channel_id %r in guild %s config",
                            config.log_channel_id,
                            guild.id,
                        )
                if log_channel is not None:
                    transcript_url = await transcript_service.upload(transcript_file, log_channel)
                else:
                    logger.warning("No log channel configured for guild %s — skipping transcript upload", guild.id)
            except discord.HTTPException:
                logger.exception("Transcript generation failed for ticket %s", ticket.id)

        await self.close_ticket(ticket.id, closed_by=closed_by, transcript_url=transcript_url)

        if manual:
            await self._countdown_and_delete(channel, closed_by)
        else:
            await asyncio.sleep(CHANNEL_DELETE_DELAY)
            try:
                await channel.delete(reason=f"Ticket closed by {closed_by}")
            except discord.HTTPException:
                logger.exception("Failed to delete ticket channel %s", channel.id)

        return transcript_url

    @staticmethod
    async def _countdown_and_delete(
        channel: discord.TextChannel,
        closed_by: str,
    ) -> None:
        """Count down from 5 to 1, then delete the channel.

        ``CancelledError`` is logged and re-raised so a cancelled task
        never deletes the channel.  ``discord.HTTPException`` during the
        countdown falls back to a silent delete.
        """
        try:
            msg = await channel.send("5")
            for i in range(4, 0, -1):
                await asyncio.sleep(1)
                await msg.edit(content=str(i))
            await asyncio.sleep(1)
            await channel.delete(reason=f"Ticket closed by {closed_by}")
        except asyncio.CancelledError:
            logger.warning(
                "Countdown cancelled for channel %s — channel NOT deleted",
                channel.id,
            )
            raise
        except discord.HTTPException:
            logger.warning(
                "Countdown failed for channel %s — falling back to silent delete",
                channel.id,
                exc_info=True,
            )
            try:
                await channel.delete(reason=f"Ticket closed by {closed_by} (countdown fallback)")
            except discord.HTTPException:
                logger.exception("Failed to delete ticket channel %s after countdown failure", channel.id)
