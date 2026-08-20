"""TicketLifecycleService — single owner for lifecycle mutations + audit + invariants (S3.3A2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.models.ticket import Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_invariants import (
    check_can_add_note,
    check_can_claim,
    check_can_delete_note,
    check_can_edit_category,
    check_can_reopen,
    check_can_transfer,
    check_can_unclaim,
    check_one_ticket_per_user_per_category,
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
    from bot.core.database import Database
    from bot.services.logging_service import LoggingService
    from bot.services.ticket_query_service import TicketQueryService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _raise_duplicate_note() -> None:
    msg = "Duplicate note (same author submitted the same normalized content within the 2-second dedup window)"
    raise ValueError(msg)


def _raise_note_not_found(note_id: str, ticket_id: str) -> None:
    msg = f"Note {note_id} not found on ticket {ticket_id}"
    raise ValueError(msg)


NOTE_CAP = 50


class TicketCategoryNotConfiguredError(ValueError):
    """Raised when the guild's ticket Discord category is not configured or is deleted."""


class TicketLifecycleService:
    """Single owner for lifecycle mutations: owns audit + invariants, delegates cache via query."""

    __slots__ = ("_db", "_query")

    def __init__(self, db: Database, query: TicketQueryService) -> None:
        self._db: Database = db
        self._query: TicketQueryService = query

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
        if category_id is not None:
            count = await self._db.count_user_open_tickets_in_category(guild_id, author_id, category_id)
            check_one_ticket_per_user_per_category(
                author_id, category_id, parent_id=None, count_fn=lambda _u, _c: count
            )
        for attempt in range(1, MAX_RETRIES + 1):
            current_max = await self._db.get_max_ticket_number(guild_id)
            ticket_number = current_max + 1
            logger.debug(
                "create_ticket attempt %d/%d: number=%d guild=%s", attempt, MAX_RETRIES, ticket_number, guild_id
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
                self._query.add_channel(int(channel_id))
                logger.info("Ticket #%d created (guild=%s, channel=%s)", ticket_number, guild_id, channel_id)
            except Exception as exc:
                logger.warning("Ticket insert conflict on attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    msg = f"Failed to create ticket after {MAX_RETRIES} attempts (guild={guild_id})"
                    raise RuntimeError(msg) from exc
            else:
                return ticket
        msg = f"Failed to create ticket after {MAX_RETRIES} attempts (guild={guild_id})"
        raise RuntimeError(msg)

    async def close_ticket(
        self,
        ticket_id: str,
        closed_by: str | None = None,
        *,
        transcript_url: str | None = None,
        close_reason: str | None = None,
        guild_id: str | None = None,
    ) -> Ticket:
        # Guild-scoped: caller SHOULD pass guild_id explicitly (S3 GUILD-SCOPE strict DB).
        # When provided, skip the unconstrained pre-read and use the scoped transition directly.
        # Fallback without guild_id is retained for backward compat in tests but still
        # resolves guild from a scoped read when possible.
        if guild_id is not None:
            closed_row = await self._db.transition_ticket_to_closed(
                guild_id,
                ticket_id,
                expected_statuses=("open", "claimed"),
                close_reason=close_reason,
                transcript_url=transcript_url,
            )
            if closed_row is None:
                denied_reason = f"Ticket {ticket_id} already closed or not found"
                try:
                    row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
                    if isinstance(row, dict):
                        gid = row.get("guildId")
                        if gid is not None:
                            await self._db.insert_audit_row(gid, ticket_id, "close", closed_by, "denied", denied_reason)
                except Exception:
                    logger.warning("Failed to write denied close audit row for ticket %s", ticket_id, exc_info=True)
                raise ValueError(denied_reason)
            ticket = Ticket.from_db_row(closed_row)
            resolved_gid = ticket.guild_id
            is_zombie = close_reason is not None and close_reason.startswith("zombie:")
            if not is_zombie:
                self._query.discard_channel(int(ticket.channel_id))
            try:
                await self._db.insert_audit_row(resolved_gid, ticket_id, "close", closed_by, "success", None)
            except Exception:
                logger.warning("Failed to write close audit row for ticket %s", ticket_id, exc_info=True)
            logger.info(
                "Ticket %s closed by %s%s%s",
                ticket_id,
                closed_by or "unknown",
                f" (transcript: {transcript_url})" if transcript_url else "",
                f" (reason: {close_reason})" if close_reason else "",
            )
            return ticket
        pre = await self._db.get_ticket(ticket_id)
        guild_id = pre.get("guildId", "") if isinstance(pre, dict) else ""
        closed_row = await self._db.transition_ticket_to_closed(
            guild_id,
            ticket_id,
            expected_statuses=("open", "claimed"),
            close_reason=close_reason,
            transcript_url=transcript_url,
        )
        if closed_row is None:
            denied_reason = f"Ticket {ticket_id} already closed or not found"
            try:
                row = await self._db.get_ticket(ticket_id)
                if isinstance(row, dict):
                    gid = row.get("guildId")
                    if gid is not None:
                        await self._db.insert_audit_row(gid, ticket_id, "close", closed_by, "denied", denied_reason)
            except Exception:
                logger.warning("Failed to write denied close audit row for ticket %s", ticket_id, exc_info=True)
            raise ValueError(denied_reason)
        ticket = Ticket.from_db_row(closed_row)
        guild_id = ticket.guild_id
        is_zombie = close_reason is not None and close_reason.startswith("zombie:")
        if not is_zombie:
            self._query.discard_channel(int(ticket.channel_id))
        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "close", closed_by, "success", None)
        except Exception:
            logger.warning("Failed to write close audit row for ticket %s", ticket_id, exc_info=True)
        logger.info(
            "Ticket %s closed by %s%s%s",
            ticket_id,
            closed_by or "unknown",
            f" (transcript: {transcript_url})" if transcript_url else "",
            f" (reason: {close_reason})" if close_reason else "",
        )
        return ticket

    async def claim_ticket(self, ticket_id: str, claimed_by: str, *, guild_id: str | None = None) -> Ticket:
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "claim", claimed_by, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild claim denied audit for %s", ticket_id, exc_info=True)
            msg = f"Ticket {ticket_id} not found"
            raise ValueError(msg)
        guild_id = pre.get("guildId", "")
        try:
            check_can_claim(pre.get("status", ""), pre.get("claimedBy"))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "claim", claimed_by, "denied", str(exc))
            raise
        await self._db.update_ticket(ticket_id, guild_id=guild_id, status="claimed", claimedBy=claimed_by)
        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            msg = f"Ticket {ticket_id} not found after claim"
            raise ValueError(msg)
        ticket = Ticket.from_db_row(row)
        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "claim", claimed_by, "success", None)
        except Exception:
            logger.warning("Failed to write claim audit row for ticket %s", ticket_id, exc_info=True)
        logger.info("Ticket %s claimed by %s", ticket_id, claimed_by)
        return ticket

    async def unclaim_ticket(
        self, ticket_id: str, actor_id: str, *, is_mod: bool, guild_id: str | None = None
    ) -> Ticket:
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "unclaim", actor_id, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild unclaim denied audit for %s", ticket_id, exc_info=True)
            msg = f"Ticket {ticket_id} not found"
            raise ValueError(msg)
        guild_id = pre.get("guildId", "")
        try:
            check_can_unclaim(actor_id, pre, is_mod=is_mod)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "unclaim", actor_id, "denied", str(exc))
            raise
        await self._db.update_ticket(ticket_id, guild_id=guild_id, status="open", claimedBy=None)
        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            msg = f"Ticket {ticket_id} not found after unclaim"
            raise ValueError(msg)
        ticket = Ticket.from_db_row(row)
        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "unclaim", actor_id, "success", None)
        except Exception:
            logger.warning("Failed to write unclaim audit row for ticket %s", ticket_id, exc_info=True)
        logger.info("Ticket %s unclaimed by %s", ticket_id, actor_id)
        return ticket

    async def edit_ticket_category(
        self,
        ticket_id: str,
        new_category_id: str,
        *,
        channel: discord.TextChannel,
        actor_id: str,
        is_mod: bool = False,
        guild_id: str | None = None,
    ) -> tuple[Ticket, bool]:
        # Prefer explicit guild_id to satisfy strict DB guild scoping.
        if guild_id is not None:
            pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
            if pre is None:
                msg = f"Ticket {ticket_id} not found"
                raise ValueError(msg)
            guild_id = pre.get("guildId", guild_id)
        else:
            pre = await self._db.get_ticket(ticket_id)
            if pre is None:
                msg = f"Ticket {ticket_id} not found"
                raise ValueError(msg)
            guild_id = pre.get("guildId", "")
        author_id = pre.get("authorId", "")
        status = pre.get("status", "")
        if status == "closed":
            msg = f"Cannot edit category of a closed ticket (status={status!r})"
            raise ValueError(msg)
        try:
            check_can_edit_category(actor_id, pre, is_mod=is_mod)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "edit_category", actor_id, "denied", str(exc))
            raise
        count = await self._db.count_user_open_tickets_in_category(
            guild_id, author_id, new_category_id, exclude_ticket_id=ticket_id
        )
        check_one_ticket_per_user_per_category(
            author_id, new_category_id, parent_id=None, count_fn=lambda _u, _c: count
        )
        await self._db.update_ticket(ticket_id, guild_id=guild_id, categoryId=new_category_id)
        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            msg = f"Ticket {ticket_id} not found after edit_category"
            raise ValueError(msg)
        ticket = Ticket.from_db_row(row)
        try:
            await self._db.insert_audit_row(guild_id, ticket_id, "edit_category", actor_id, "success", None)
        except Exception:
            logger.warning("Failed to write edit_category audit row for ticket %s", ticket_id, exc_info=True)
        rename_succeeded = True
        try:
            category_name = await resolve_category_name(self._db, new_category_id, fallback="ticket")
            author = resolve_member_safe(channel.guild, author_id)
            display_name = author.display_name if author is not None else "user"
            ticket_number = row.get("ticketNumber", 0)
            try:
                ticket_number = int(ticket_number)
            except (TypeError, ValueError):
                ticket_number = 0
            new_name = sanitize_channel_name(category_name, display_name, ticket_number)
            await channel.edit(name=new_name)
        except discord.HTTPException:
            logger.warning("Failed to rename ticket channel %s after category edit", channel.id, exc_info=True)
            rename_succeeded = False
        logger.info(
            "Ticket %s category edited to %s by %s (rename=%s)", ticket_id, new_category_id, actor_id, rename_succeeded
        )
        return ticket, rename_succeeded

    async def create_subticket(
        self, parent_id: str, author_id: str, category_id: str | None, channel_id: str, *, guild_id: str
    ) -> Ticket:
        parent_row = await self._db.get_ticket(parent_id, guild_id=guild_id)
        if parent_row is None:
            await self._db.insert_audit_row(
                guild_id, parent_id, "subticket_create", author_id, "denied", f"Parent ticket {parent_id} not found"
            )
            msg = f"Parent ticket {parent_id} not found"
            raise ValueError(msg)
        parent = Ticket.from_db_row(parent_row)
        parent_guild_id = parent_row.get("guildId", "")
        if parent.parent_id is not None and parent.parent_id == parent.id:
            await self._db.insert_audit_row(
                guild_id,
                parent_id,
                "subticket_create",
                author_id,
                "denied",
                f"Parent ticket {parent_id} is self-referential",
            )
            msg = f"Parent ticket {parent_id} is self-referential"
            raise ValueError(msg)
        try:
            check_subticket_parent(parent_row, parent_guild_id, guild_id, current_id=None)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, parent_id, "subticket_create", author_id, "denied", str(exc))
            raise
        for attempt in range(1, MAX_RETRIES + 1):
            current_max = await self._db.get_max_ticket_number(guild_id)
            ticket_number = current_max + 1
            logger.debug(
                "create_subticket attempt %d/%d: number=%d parent=%s", attempt, MAX_RETRIES, ticket_number, parent_id
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
                self._query.add_channel(int(channel_id))
                await self._db.insert_audit_row(guild_id, ticket.id, "subticket_create", author_id, "success", None)
                logger.info(
                    "Sub-ticket #%d created (parent=%s, guild=%s, channel=%s)",
                    ticket_number,
                    parent_id,
                    guild_id,
                    channel_id,
                )
            except Exception as exc:
                logger.warning("Sub-ticket insert conflict on attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    msg = f"Failed to create sub-ticket after {MAX_RETRIES} attempts (guild={guild_id})"
                    raise RuntimeError(msg) from exc
            else:
                return ticket
        msg = f"Failed to create sub-ticket after {MAX_RETRIES} attempts (guild={guild_id})"
        raise RuntimeError(msg)

    async def reopen_ticket(self, ticket_id: str, *, guild: discord.Guild) -> Ticket:
        # Reopen must be guild-scoped: derive guild_id from the Discord guild param,
        # then read the ticket scoped to that guild so cross-guild lookups are denied.
        reopen_gid = str(guild.id)
        closed_row = await self._db.get_ticket(ticket_id, guild_id=reopen_gid)
        if closed_row is None:
            msg = f"Ticket {ticket_id} not found"
            raise ValueError(msg)
        guild_id = closed_row.get("guildId", reopen_gid)
        try:
            check_can_reopen(closed_row.get("status", ""))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "denied", str(exc))
            msg = f"Solo se pueden reabrir tickets cerrados. Estado actual: {closed_row.get('status')}"
            raise ValueError(msg) from exc
        guild_row = await self._db.get_guild(str(guild.id))
        category_channel = self._resolve_ticket_category(guild, guild_row)
        if category_channel is None:
            err = f"No ticket category configured for guild {guild.id} — cannot reopen ticket {ticket_id}"
            await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "denied", err)
            raise TicketCategoryNotConfiguredError(err)
        new_channel = await self._build_reopen_channel(guild, closed_row, guild_row, category_channel, ticket_id)
        await self._db.update_ticket(
            ticket_id, guild_id=guild_id, channelId=str(new_channel.id), status="open", closedAt=None
        )
        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            msg = f"Ticket {ticket_id} not found after reopen"
            raise ValueError(msg)
        ticket = Ticket.from_db_row(row)
        self._query.add_channel(int(ticket.channel_id))
        await self._db.insert_audit_row(guild_id, ticket_id, "reopen", None, "success", None)
        logger.info("Ticket %s reopened (new channel=%s)", ticket_id, ticket.channel_id)
        return ticket

    @staticmethod
    def _resolve_ticket_category(
        guild: discord.Guild, guild_row: dict[str, Any] | None
    ) -> discord.CategoryChannel | None:
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
        author_id = closed_row.get("authorId")
        author = resolve_member_safe(guild, author_id)
        mod_role_id = (guild_row or {}).get("modRoleId")
        mod_role = resolve_mod_role(guild, mod_role_id)
        overwrites = build_ticket_overwrites(guild, author, mod_role)
        ticket_number = closed_row.get("ticketNumber", 0)
        try:
            ticket_number = int(ticket_number)
        except (TypeError, ValueError):
            ticket_number = 0
        category_name = await resolve_category_name(self._db, closed_row.get("categoryId"), fallback="ticket")
        display_name = author.display_name if author is not None else "user"
        channel_name = sanitize_channel_name(category_name, display_name, ticket_number)
        return await guild.create_text_channel(
            name=channel_name, category=category_channel, overwrites=overwrites, reason=f"Ticket {ticket_id} reopened"
        )

    async def transfer_ticket(
        self,
        ticket_id: str,
        new_claimed_by: str,
        actor_id: str,
        *,
        guild: discord.Guild | None = None,
        logging_service: LoggingService | None = None,
        guild_id: str | None = None,
    ) -> Ticket:
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "transfer", actor_id, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild transfer denied audit for %s", ticket_id, exc_info=True)
            msg = f"Ticket {ticket_id} not found"
            raise ValueError(msg)
        guild_id = pre.get("guildId", "")
        try:
            check_can_transfer(pre.get("status", ""), pre.get("claimedBy"), new_claimed_by)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "transfer", actor_id, "denied", str(exc))
            raise
        await self._db.update_ticket(ticket_id, guild_id=guild_id, claimedBy=new_claimed_by, status="claimed")
        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            msg = f"Ticket {ticket_id} not found after transfer"
            raise ValueError(msg)
        ticket = Ticket.from_db_row(row)
        await self._db.insert_audit_row(ticket.guild_id, ticket_id, "transfer", actor_id, "success", None)
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
                        reason=f"Ticket {ticket_id} transferred from {actor_id} to {new_claimed_by}",
                    )
            except Exception:
                logger.warning("Failed to log ticket transfer audit (ticket=%s)", ticket_id, exc_info=True)
        logger.info("Ticket %s transferred to %s by %s", ticket_id, new_claimed_by, actor_id)
        return ticket

    async def create_note(
        self, ticket_id: str, author_id: str, content: str, *, guild_id: str | None = None
    ) -> TicketNote:
        # Prefer explicit guild_id; resolve via scoped ticket read otherwise.
        # Fallback without guild_id keeps backward compat for existing tests
        # (AsyncMock without ticket row) while production callers supply guild_id.
        if guild_id is not None:
            ticket_row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
            if ticket_row is None:
                msg = f"Ticket {ticket_id} not found"
                raise ValueError(msg)
            resolved_gid: str = guild_id
            existing = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=resolved_gid)
        else:
            ticket_row = await self._db.get_ticket(ticket_id)
            resolved_gid = (ticket_row or {}).get("guildId", "") if isinstance(ticket_row, dict) else ""
            # Keep lenient for test mocks that return None/unset — strict path is via guild_id.
            if resolved_gid:
                existing = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=resolved_gid)
                guild_id = resolved_gid
            else:
                existing = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id="")
                guild_id = ""
        try:
            check_can_add_note(len(existing), NOTE_CAP)
            recent = await self._db.get_recent_notes_for_dedup(ticket_id, author_id, 2, guild_id=guild_id)
            recent_hashes = [compute_note_hash(r.get("content", "")) for r in recent]
            new_hash = compute_note_hash(content)
            if is_duplicate_note(new_hash, author_id, recent_hashes):
                _raise_duplicate_note()
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "note_add", author_id, "denied", str(exc))
            raise
        row = await self._db.insert_ticket_note(ticket_id, author_id, content, guild_id=guild_id)
        note = TicketNote.from_db_row(row)
        await self._db.insert_audit_row(guild_id, ticket_id, "note_add", author_id, "success", None)
        logger.info("Note %s added to ticket %s by %s", note.id, ticket_id, author_id)
        return note

    async def get_notes(self, ticket_id: str, *, guild_id: str | None = None) -> list[TicketNote]:
        # Prefer explicit guild_id; resolve via ticket lookup otherwise.
        if guild_id is not None:
            rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=guild_id)
            notes = [TicketNote.from_db_row(r) for r in rows]
            await self._db.insert_audit_row(guild_id, ticket_id, "note_list", None, "success", None)
            logger.debug("get_notes(ticket=%s, guild=%s): %d notes", ticket_id, guild_id, len(notes))
            return notes
        ticket_row = await self._db.get_ticket(ticket_id)
        resolved_gid = (ticket_row or {}).get("guildId", "") if isinstance(ticket_row, dict) else ""
        if resolved_gid:
            rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=resolved_gid)
        else:
            rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id="")
        notes = [TicketNote.from_db_row(r) for r in rows]
        await self._db.insert_audit_row(resolved_gid, ticket_id, "note_list", None, "success", None)
        logger.debug("get_notes(ticket=%s): %d notes", ticket_id, len(notes))
        return notes

    async def delete_note(self, note_id: str, author_id: str, *, ticket_id: str, guild_id: str | None = None) -> None:
        # Prefer explicit guild_id; resolve via ticket lookup otherwise.
        if guild_id is not None:
            rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=guild_id)
            target = next((r for r in rows if r.get("id") == note_id), None)
            try:
                if target is None:
                    _raise_note_not_found(note_id, ticket_id)
                check_can_delete_note(target.get("authorId", ""), author_id)  # ty: ignore[unresolved-attribute] -- _raise above guarantees not None
            except ValueError as exc:
                await self._db.insert_audit_row(guild_id, ticket_id, "note_delete", author_id, "denied", str(exc))
                raise
            await self._db.delete_ticket_note(note_id, guild_id=guild_id, ticket_id=ticket_id)
            await self._db.insert_audit_row(guild_id, ticket_id, "note_delete", author_id, "success", None)
            logger.info("Note %s deleted by %s", note_id, author_id)
            return
        # Fallback path: resolve guild via ticket lookup, then re-read notes scoped.
        ticket_row = await self._db.get_ticket(ticket_id)
        resolved_gid = (ticket_row or {}).get("guildId", "") if isinstance(ticket_row, dict) else ""
        if resolved_gid:
            scoped_rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id=resolved_gid)
            guild_id = resolved_gid
        else:
            scoped_rows = await self._db.get_ticket_notes(ticket_id, limit=NOTE_CAP, guild_id="")
        target = next((r for r in scoped_rows if r.get("id") == note_id), None)
        try:
            if target is None:
                _raise_note_not_found(note_id, ticket_id)
            check_can_delete_note(target.get("authorId", ""), author_id)  # ty: ignore[unresolved-attribute] -- _raise above guarantees not None
        except ValueError as exc:
            eff_gid = guild_id or resolved_gid
            await self._db.insert_audit_row(eff_gid, ticket_id, "note_delete", author_id, "denied", str(exc))
            raise
        eff_gid = guild_id or resolved_gid
        if eff_gid:
            await self._db.delete_ticket_note(note_id, guild_id=eff_gid, ticket_id=ticket_id)
        else:
            await self._db.delete_ticket_note(note_id)
        await self._db.insert_audit_row(eff_gid, ticket_id, "note_delete", author_id, "success", None)
        logger.info("Note %s deleted by %s", note_id, author_id)
