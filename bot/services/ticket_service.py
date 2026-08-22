"""TicketService — thin facade over TicketQuery/Lifecycle/Repair services (S3).

Implements the ticket business layer: create, close, claim, stale detection,
sub-ticket derivation, reopen, transfer, staff notes, and a cached set of
ticket channel IDs for fast O(1) ``on_message`` queries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.models.ticket import IntegrityEvidence, RepairResult, Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_invariants import (
    GlobalMutationGrant,
    RepairAuthority,
)
from bot.services.ticket_lifecycle_service import (
    NOTE_CAP as _LC_NOTE_CAP,  # noqa: F401 — re-export for backward compat
)
from bot.services.ticket_lifecycle_service import (
    TicketCategoryNotConfiguredError as _LC_TicketCategoryNotConfiguredError,
)
from bot.services.ticket_lifecycle_service import (
    TicketLifecycleService,
)
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair import (
    backoff_delay as _coordinator_backoff_delay,
)
from bot.services.ticket_repair import evaluate_repair_eligibility as _coordinator_evaluate
from bot.services.ticket_repair import plan_sweep_batch as _coordinator_plan_sweep_batch
from bot.services.ticket_repair import probe_channel_absence as _coordinator_probe
from bot.services.ticket_repair_service import TimerMessageResult

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.logging_service import LoggingService
    from bot.services.ticket_repair_service import TicketRepairService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
NOTE_CAP = 50  # v1 per-ticket staff note limit (see design.md non-goals)
CHANNEL_DELETE_DELAY = 5  # seconds before deleting a closed ticket channel


# Lifecycle exception — single owner is lifecycle service; re-export for compat.
TicketCategoryNotConfiguredError = _LC_TicketCategoryNotConfiguredError


# Repair coordinator facade — single source in bot.services.ticket_repair.
# TicketService re-exports these so every adapter converges on one
# fail-closed path without duplicating gate/evidence logic.
backoff_delay = _coordinator_backoff_delay
plan_sweep_batch = _coordinator_plan_sweep_batch
probe_channel_absence = _coordinator_probe
evaluate_repair_eligibility = _coordinator_evaluate


class TicketService:
    """Manages ticket lifecycle with sequential numbering and cache sync.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.

    Facade over the S3 decomposition: query/cache ownership lives in
    :class:`TicketQueryService` (single cache-mutation owner),
    lifecycle in :class:`TicketLifecycleService`, and repair/channel/
    transcript in :class:`TicketRepairService`.
    """

    __slots__ = ("_cache", "_db", "_lifecycle", "_query", "_repair")

    def __init__(self, db: Database, cache: TTLCache) -> None:
        self._db: Database = db
        self._cache: TTLCache = cache
        self._query: TicketQueryService = TicketQueryService(db)
        self._lifecycle: TicketLifecycleService = TicketLifecycleService(db, self._query)
        from bot.services.ticket_repair_service import TicketRepairService as RepairService

        self._repair: TicketRepairService = RepairService(db, self._query, self._lifecycle)

    # ----------------------------------------------------------------
    # Public API — lifecycle (delegates to lifecycle service)
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
        """Create a new ticket (delegates to lifecycle service)."""
        return await self._lifecycle.create_ticket(
            guild_id=guild_id,
            author_id=author_id,
            category_id=category_id,
            channel_id=channel_id,
            subject=subject,
            description=description,
            custom_fields=custom_fields,
        )

    async def close_ticket(
        self,
        ticket_id: str,
        closed_by: str | None = None,
        *,
        transcript_url: str | None = None,
        close_reason: str | None = None,
        guild_id: str | None = None,
    ) -> Ticket:
        """Close a ticket (delegates to lifecycle service)."""
        return await self._lifecycle.close_ticket(
            ticket_id,
            closed_by=closed_by,
            transcript_url=transcript_url,
            close_reason=close_reason,
            guild_id=guild_id,
        )

    # ----------------------------------------------------------------
    # Repair coordinator — single seam delegates to repair service
    # ----------------------------------------------------------------

    async def repair_ticket_from_evidence(
        self,
        evidence: IntegrityEvidence,
        *,
        preflight: object | None = None,
        close_reason: str = "zombie:repair",
        actor_id: str | None = "system",
    ) -> RepairResult:
        """Repair a ticket from immutable, guild-matched :class:`IntegrityEvidence` (delegates to repair service)."""
        return await self._repair.repair_ticket_from_evidence(
            evidence,
            preflight=preflight,
            close_reason=close_reason,
            actor_id=actor_id,
        )

    async def handle_channel_delete(
        self,
        guild_id: str,
        channel_id: str,
        *,
        preflight: object | None = None,
    ) -> RepairResult | None:
        """Route an exact channel-delete event to the shared repair path (delegates to repair service)."""
        return await self._repair.handle_channel_delete(
            guild_id=guild_id,
            channel_id=channel_id,
            preflight=preflight,
        )

    async def sweep_integrity(
        self,
        guild_id: str,
        bot: Any,
        *,
        preflight: object | None = None,
        batch_size: int = 50,
    ) -> list[RepairResult]:
        """Run one bounded integrity sweep for *guild_id* (delegates to repair service)."""
        return await self._repair.sweep_integrity(
            guild_id=guild_id,
            bot=bot,
            preflight=preflight,
            batch_size=batch_size,
        )

    async def repair_ticket_by_ref(
        self,
        ticket_ref: str,
        *,
        guild_id: str,
        actor_id: str,
        authority: RepairAuthority,
        bot: Any,
        preflight: object | None = None,
        global_grant: GlobalMutationGrant | None = None,
    ) -> RepairResult | None:
        """Resolve *ticket_ref* and repair the ticket through the shared path (delegates to repair service)."""
        return await self._repair.repair_ticket_by_ref(
            ticket_ref,
            guild_id=guild_id,
            actor_id=actor_id,
            authority=authority,
            bot=bot,
            preflight=preflight,
            global_grant=global_grant,
        )

    async def repair_ticket_manual(
        self,
        ticket_id: str,
        *,
        guild_id: str,
        actor_id: str,
        authority: RepairAuthority,
        bot: Any,
        preflight: object | None = None,
        global_grant: GlobalMutationGrant | None = None,
    ) -> RepairResult:
        """Manually repair one ticket using explicit authority + fresh probe (delegates to repair service)."""
        return await self._repair.repair_ticket_manual(
            ticket_id=ticket_id,
            guild_id=guild_id,
            actor_id=actor_id,
            authority=authority,
            bot=bot,
            preflight=preflight,
            global_grant=global_grant,
        )

    # Delegated audit helper — kept for backward compat, delegates to repair service.
    async def _audit_denied(
        self,
        guild_id: str,
        ticket_id: str,
        reason: str,
        actor_id: str | None,
        *,
        outcome: str = "denied",
    ) -> None:
        """Persist best-effort structured audit evidence for a failed repair (delegates to repair service)."""
        return await self._repair._audit_denied(guild_id, ticket_id, reason, actor_id, outcome=outcome)

    async def claim_ticket(self, ticket_id: str, claimed_by: str, *, guild_id: str | None = None) -> Ticket:
        """Claim a ticket (delegates to lifecycle service)."""
        return await self._lifecycle.claim_ticket(ticket_id, claimed_by, guild_id=guild_id)

    async def unclaim_ticket(
        self,
        ticket_id: str,
        actor_id: str,
        *,
        is_mod: bool,
        guild_id: str | None = None,
    ) -> Ticket:
        """Unclaim a ticket (delegates to lifecycle service)."""
        return await self._lifecycle.unclaim_ticket(ticket_id, actor_id, is_mod=is_mod, guild_id=guild_id)

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
        """Edit a ticket's category (delegates to lifecycle service)."""
        return await self._lifecycle.edit_ticket_category(
            ticket_id,
            new_category_id,
            channel=channel,
            actor_id=actor_id,
            is_mod=is_mod,
            guild_id=guild_id,
        )

    async def schedule_close(
        self, guild_id: str, ticket_id: str, scheduled_close_at: str, scheduled_close_by: str
    ) -> None:
        """Set scheduledCloseAt/By (delegates to repair service)."""
        return await self._repair.schedule_close(guild_id, ticket_id, scheduled_close_at, scheduled_close_by)

    async def cancel_scheduled_close(self, guild_id: str, ticket_id: str) -> None:
        """Clear scheduledCloseAt/By (delegates to repair service)."""
        return await self._repair.cancel_scheduled_close(guild_id, ticket_id)

    async def handle_timer_message(
        self,
        guild_id: str,
        ticket_row: dict[str, Any],
        content: str,
        author_id: str,
    ) -> TimerMessageResult | None:
        """Process a ``,<duration>``/``,cancel`` mod timer message (delegates to repair service)."""
        return await self._repair.handle_timer_message(guild_id, ticket_row, content, author_id)

    async def confirm_timer_schedule(
        self,
        guild_id: str,
        ticket_id: str,
        seconds: int,
        author_id: str,
    ) -> TimerMessageResult:
        """Execute the schedule on confirm-view confirmation (delegates to repair service)."""
        return await self._repair.confirm_timer_schedule(guild_id, ticket_id, seconds, author_id)

    async def get_due_scheduled_tickets(self, guild_id: str, *, batch_size: int = 50) -> list[dict[str, Any]]:
        """Return due scheduled-close candidate rows for *guild_id* (delegates to repair service)."""
        return await self._repair.get_due_scheduled_tickets(guild_id, batch_size=batch_size)

    async def resolve_due_ticket_for_close(
        self,
        guild_id: str,
        candidate_row: dict[str, Any],
    ) -> Ticket | None:
        """Resolve a due candidate into a closable Ticket (delegates to repair service).

        The cog loop resolves the Discord channel and calls this to fetch the
        full row + branch on status. Returns the Ticket when still open/claimed,
        or ``None`` when already closed (stale scheduled fields cleared by the
        service).
        """
        return await self._repair.resolve_due_ticket_for_close(guild_id, candidate_row)

    async def upsert_timer_embed(
        self,
        channel: discord.TextChannel,
        guild_id: str,
        ticket_id: str,
        due_ts: float,
        seconds: int,
    ) -> None:
        """Post or edit the pinned timer embed carrying ``<t:R>``/``<t:F>`` (delegates to repair service)."""
        await self._repair.upsert_timer_embed(channel, guild_id, ticket_id, due_ts, seconds)

    # -- Query/cache facade (S3.3A): single owner is TicketQueryService --

    @property
    def _ticket_channel_cache(self) -> set[int]:
        """Alias to the single cache owner (backward compat for callers/tests)."""
        return self._query._ticket_channel_cache

    @_ticket_channel_cache.setter
    def _ticket_channel_cache(self, value: set[int]) -> None:
        self._query._ticket_channel_cache = value.copy() if isinstance(value, set) else set(value)

    async def get_stale_tickets(self, guild_id: str, hours: int = 48) -> list[Ticket]:
        """Return open/claimed tickets with no activity for *hours* (delegates to query service)."""
        return await self._query.get_stale_tickets(guild_id, hours=hours)

    def is_ticket_channel(self, channel_id: int) -> bool:
        """Check whether *channel_id* belongs to an open/claimed ticket (delegates to query service)."""
        return self._query.is_ticket_channel(channel_id)

    def sync_channel_cache(self, channel_ids: set[int] | None = None) -> None:
        """Rebuild the ticket channel cache (delegates to query service)."""
        self._query.sync_channel_cache(channel_ids)

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
        """Create a child ticket (delegates to lifecycle service)."""
        return await self._lifecycle.create_subticket(
            parent_id=parent_id, author_id=author_id, category_id=category_id, channel_id=channel_id, guild_id=guild_id
        )

    async def reopen_ticket(self, ticket_id: str, *, guild: discord.Guild) -> Ticket:
        """Reopen a closed ticket (delegates to lifecycle service)."""
        return await self._lifecycle.reopen_ticket(ticket_id, guild=guild)

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
        """Transfer a ticket's claim (delegates to lifecycle service)."""
        return await self._lifecycle.transfer_ticket(
            ticket_id, new_claimed_by, actor_id, guild=guild, logging_service=logging_service, guild_id=guild_id
        )

    # ----------------------------------------------------------------
    # Staff notes (slice 2)
    # ----------------------------------------------------------------

    async def create_note(
        self, ticket_id: str, author_id: str, content: str, *, guild_id: str | None = None
    ) -> TicketNote:
        """Add a staff note (delegates to lifecycle service)."""
        return await self._lifecycle.create_note(ticket_id, author_id, content, guild_id=guild_id)

    async def get_notes(self, ticket_id: str, *, guild_id: str | None = None) -> list[TicketNote]:
        """Return staff notes (delegates to lifecycle service)."""
        return await self._lifecycle.get_notes(ticket_id, guild_id=guild_id)

    async def delete_note(self, note_id: str, author_id: str, *, ticket_id: str, guild_id: str | None = None) -> None:
        """Delete a staff note (delegates to lifecycle service)."""
        return await self._lifecycle.delete_note(note_id, author_id, ticket_id=ticket_id, guild_id=guild_id)

    # ----------------------------------------------------------------
    # Orchestration helpers — delegate to repair service (S3.3B)
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
        """Create a ticket Discord channel, insert row, and rename if needed (delegates to repair service)."""
        return await self._repair.create_ticket_channel(
            guild=guild,
            category=category,
            author=author,
            guild_id=guild_id,
            category_name=category_name,
            category_id=category_id,
            mod_role=mod_role,
            parent_id=parent_id,
            subject=subject,
            description=description,
            custom_fields=custom_fields,
        )

    async def close_ticket_full(
        self,
        channel: discord.TextChannel,
        ticket: Ticket,
        closed_by: str,
        *,
        bot: NebulosaBot,
        manual: bool = True,
    ) -> str | None:
        """Close a single ticket end-to-end: transcript -> upload -> DB -> delete (delegates to repair service)."""
        return await self._repair.close_ticket_full(
            channel=channel,
            ticket=ticket,
            closed_by=closed_by,
            bot=bot,
            manual=manual,
        )

    @staticmethod
    async def _countdown_and_delete(
        channel: discord.TextChannel,
        closed_by: str,
    ) -> None:
        """Count down from 5 to 1, then delete the channel (kept here so test patches/loggers match)."""
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
        except discord.NotFound:
            logger.info(
                "Resource disappeared during countdown for channel %s — attempting final delete",
                channel.id,
            )
            try:
                await channel.delete(reason=f"Ticket closed by {closed_by}")
            except discord.NotFound:
                logger.info("Ticket channel %s already deleted during countdown", channel.id)
            except discord.HTTPException:
                logger.exception(
                    "Failed to delete ticket channel %s after countdown NotFound",
                    channel.id,
                )
        except discord.HTTPException:
            logger.warning(
                "Countdown failed for channel %s — falling back to silent delete",
                channel.id,
                exc_info=True,
            )
            try:
                await channel.delete(reason=f"Ticket closed by {closed_by} (countdown fallback)")
            except discord.NotFound:
                logger.info("Ticket channel %s already deleted during countdown fallback", channel.id)
            except discord.HTTPException:
                logger.exception("Failed to delete ticket channel %s after countdown failure", channel.id)
