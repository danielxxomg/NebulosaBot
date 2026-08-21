"""TicketRepairService — single owner for repair/channel/transcript orchestration (S3.3B)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from bot.config import INTEGRITY_BATCH_SIZE
from bot.core.i18n import t
from bot.models.ticket import IntegrityEvidence, RepairResult, Ticket
from bot.services.ticket_invariants import (
    GlobalMutationGrant,
    RepairAuthority,
    check_one_ticket_per_user_per_category,
    evaluate_repair_authority,
    parse_ticket_ref,
)
from bot.services.ticket_repair import (
    backoff_delay,
    evaluate_repair_eligibility,
    plan_sweep_batch,
    probe_channel_absence,
)
from bot.utils.brand import WARNING
from bot.utils.ticket_helpers import build_ticket_overwrites, sanitize_channel_name
from bot.utils.time import format_remaining, parse_duration_strict

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.database import Database
    from bot.services.ticket_lifecycle_service import TicketLifecycleService
    from bot.services.ticket_query_service import TicketQueryService

logger = logging.getLogger(__name__)

CHANNEL_DELETE_DELAY = 5

# Timer threshold constants (business rules): durations below MIN or above MAX
# require explicit confirmation via ConfirmCancelView before being scheduled.
TIMER_MIN_SECONDS = 2 * 3600  # 2 hours
TIMER_MAX_SECONDS = 5 * 86400  # 5 days
TIMER_CONFIRM_TIMEOUT = 30  # seconds before the confirm view times out

_ACTIVE_TICKET_STATUSES = ("open", "claimed")


class TicketRepairService:
    """Single owner for repair eligibility + channel/transcript orchestration.

    All repair entry points converge on ``repair_ticket_from_evidence``
    (single ``evaluate_repair_eligibility`` seam). Transcript/channel
    orchestration lives here so TicketService stays a thin facade.
    """

    __slots__ = ("_db", "_lifecycle", "_query")

    def __init__(
        self,
        db: Database,
        query: TicketQueryService,
        lifecycle: TicketLifecycleService,
    ) -> None:
        self._db: Database = db
        self._query = query
        self._lifecycle = lifecycle

    # -- repair coordinator (single seam) ---------------------------------

    async def repair_ticket_from_evidence(
        self,
        evidence: IntegrityEvidence,
        *,
        preflight: object | None = None,
        close_reason: str = "zombie:repair",
        actor_id: str | None = "system",
    ) -> RepairResult:
        """Repair a ticket from immutable, guild-matched :class:`IntegrityEvidence`.

        Fail-closed gates (single ``evaluate_repair_eligibility`` seam):
        1. Preflight unresolved -> skipped/gate_unresolved, no mutation.
        2. Evidence not corroborated -> skipped/evidence_unresolved or not_corroborated.
        3. Conditional transition: one winner; loser -> already_closed.
        """
        now = datetime.now(UTC)
        ticket_id = evidence.ticket_id
        guild_id = evidence.guild_id

        preflight_allows = getattr(preflight, "repair_activation_allowed", None) is True
        denial = evaluate_repair_eligibility(
            preflight_allows=preflight_allows,
            corroborated=evidence.corroborated,
        )
        if denial is not None:
            outcome, reason = denial
            try:
                await self._db.insert_audit_row(
                    guild_id,
                    ticket_id,
                    "repair",
                    actor_id,
                    "denied",
                    reason,
                )
            except Exception:
                logger.warning(
                    "Failed to write repair denied audit row for ticket %s",
                    ticket_id,
                    exc_info=True,
                )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome=outcome,
                reason=reason,
                evidence_id=None,
                timestamp=now,
            )

        try:
            closed_row = await self._db.transition_ticket_to_closed(
                guild_id,
                ticket_id,
                expected_statuses=("open", "claimed"),
                close_reason=close_reason,
            )
        except Exception as exc:
            logger.warning(
                "Repair transition failed for ticket %s: %s",
                ticket_id,
                exc,
                exc_info=True,
            )
            try:
                await self._db.insert_audit_row(
                    guild_id,
                    ticket_id,
                    "repair",
                    actor_id,
                    "error",
                    type(exc).__name__,
                )
            except Exception:
                logger.warning(
                    "Failed to write repair error audit row for ticket %s",
                    ticket_id,
                    exc_info=True,
                )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="error",
                reason=type(exc).__name__,
                evidence_id=None,
                timestamp=now,
            )

        if closed_row is None:
            try:
                await self._db.insert_audit_row(
                    guild_id,
                    ticket_id,
                    "repair",
                    actor_id,
                    "denied",
                    "already_closed",
                )
            except Exception:
                logger.warning(
                    "Failed to write repair already-closed audit row for ticket %s",
                    ticket_id,
                    exc_info=True,
                )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="already_closed",
                reason=None,
                evidence_id=None,
                timestamp=now,
            )

        audit_persisted = True
        try:
            is_manual = actor_id != "system" or close_reason == "zombie:manual_repair"
            action_name = "manual_repair" if is_manual else "repair"
            await self._db.insert_audit_row(
                guild_id,
                ticket_id,
                action_name,
                actor_id,
                "repaired",
                None,
            )
        except Exception:
            audit_persisted = False
            logger.warning(
                "Failed to write repair audit row for ticket %s",
                ticket_id,
                exc_info=True,
            )
        if not audit_persisted:
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="close",
                outcome="error",
                reason="audit_persistence_failed",
                evidence_id=None,
                timestamp=now,
            )
        return RepairResult(
            ticket_id=ticket_id,
            guild_id=guild_id,
            action="close",
            outcome="repaired",
            reason=None,
            evidence_id=evidence.evidence_id,
            timestamp=now,
            corroborated=True,
        )

    async def handle_channel_delete(
        self,
        guild_id: str,
        channel_id: str,
        *,
        preflight: object | None = None,
    ) -> RepairResult | None:
        """Route an exact channel-delete event to the shared repair path."""
        try:
            row = await self._db.get_active_ticket_by_channel(guild_id, channel_id)
        except Exception as exc:
            logger.warning(
                "Channel-delete lookup failed (guild=%s, channel=%s, reason=lookup_error): %s",
                guild_id,
                channel_id,
                exc,
                exc_info=True,
            )
            await self._audit_denied(
                guild_id,
                "",
                "lookup_error",
                "system",
            )
            return RepairResult(
                ticket_id="",
                guild_id=guild_id,
                action="no_op",
                outcome="skipped",
                reason="lookup_error",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )
        if row is None:
            return None
        evidence = IntegrityEvidence(
            ticket_id=row["id"],
            guild_id=guild_id,
            channel_id=row.get("channelId"),
            status=row["status"],
            channel_exists=False,
            source="channel_delete",
        )
        return await self.repair_ticket_from_evidence(
            evidence,
            preflight=preflight,
            close_reason="zombie:channel_deleted",
            actor_id="system",
        )

    async def sweep_integrity(
        self,
        guild_id: str,
        bot: Any,
        *,
        preflight: object | None = None,
        batch_size: int = INTEGRITY_BATCH_SIZE,
    ) -> list[RepairResult]:
        """Run one bounded integrity sweep for *guild_id*."""
        try:
            channel_ids = await self._db.get_open_ticket_channel_ids(guild_id)
        except Exception as exc:
            logger.warning(
                "Integrity sweep failed to discover candidate channels (guild=%s, reason=sweep_discovery_error): %s",
                guild_id,
                exc,
                exc_info=True,
            )
            await self._audit_denied(
                guild_id,
                "",
                "sweep_discovery_error",
                "system",
            )
            return [
                RepairResult(
                    ticket_id="",
                    guild_id=guild_id,
                    action="no_op",
                    outcome="skipped",
                    reason="sweep_discovery_error",
                    evidence_id=None,
                    timestamp=datetime.now(UTC),
                )
            ]
        candidates: list[dict[str, Any]] = []
        results: list[RepairResult] = []
        for channel_id in channel_ids:
            try:
                row = await self._db.get_active_ticket_by_channel(guild_id, channel_id)
            except Exception as exc:
                logger.warning(
                    "Integrity sweep failed to resolve candidate "
                    "(guild=%s, channel=%s, reason=sweep_discovery_error): %s",
                    guild_id,
                    channel_id,
                    exc,
                    exc_info=True,
                )
                await self._audit_denied(
                    guild_id,
                    "",
                    "sweep_discovery_error",
                    "system",
                )
                results.append(
                    RepairResult(
                        ticket_id="",
                        guild_id=guild_id,
                        action="no_op",
                        outcome="skipped",
                        reason="sweep_discovery_error",
                        evidence_id=None,
                        timestamp=datetime.now(UTC),
                    )
                )
                continue
            if row is not None:
                candidates.append(row)

        batch = plan_sweep_batch(candidates, batch_size=batch_size)
        attempt = 0
        for candidate in batch:
            raw_channel_id = candidate.get("channelId")
            channel_exists = await probe_channel_absence(bot, guild_id, str(raw_channel_id))
            if channel_exists is None:
                await asyncio.sleep(backoff_delay(attempt))
                attempt += 1
                evidence_unresolved = IntegrityEvidence(
                    ticket_id=candidate["id"],
                    guild_id=guild_id,
                    channel_id=raw_channel_id,
                    status=candidate["status"],
                    channel_exists=None,
                    observed_at=datetime.now(UTC),
                    source="sweep",
                )
                preflight_allows = getattr(preflight, "repair_activation_allowed", None) is True
                if not preflight_allows:
                    results.append(
                        RepairResult(
                            ticket_id=candidate["id"],
                            guild_id=guild_id,
                            action="no_op",
                            outcome="skipped",
                            reason="gate_unresolved",
                            evidence_id=evidence_unresolved.evidence_id,
                            timestamp=datetime.now(UTC),
                            corroborated=evidence_unresolved.corroborated,
                        )
                    )
                else:
                    results.append(
                        RepairResult(
                            ticket_id=candidate["id"],
                            guild_id=guild_id,
                            action="no_op",
                            outcome="skipped",
                            reason="probe_unresolved",
                            evidence_id=evidence_unresolved.evidence_id,
                            timestamp=datetime.now(UTC),
                            corroborated=evidence_unresolved.corroborated,
                        )
                    )
                continue

            if channel_exists is True:
                evidence_live = IntegrityEvidence(
                    ticket_id=candidate["id"],
                    guild_id=guild_id,
                    channel_id=raw_channel_id,
                    status=candidate["status"],
                    channel_exists=True,
                    observed_at=datetime.now(UTC),
                    source="sweep",
                )
                results.append(
                    RepairResult(
                        ticket_id=candidate["id"],
                        guild_id=guild_id,
                        action="no_op",
                        outcome="skipped",
                        reason="not_corroborated",
                        evidence_id=evidence_live.evidence_id,
                        timestamp=datetime.now(UTC),
                        corroborated=evidence_live.corroborated,
                    )
                )
                continue

            evidence = IntegrityEvidence(
                ticket_id=candidate["id"],
                guild_id=guild_id,
                channel_id=raw_channel_id,
                status=candidate["status"],
                channel_exists=channel_exists,
                observed_at=datetime.now(UTC),
                source="sweep",
            )
            preflight_allows = getattr(preflight, "repair_activation_allowed", None) is True
            if not preflight_allows:
                results.append(
                    RepairResult(
                        ticket_id=candidate["id"],
                        guild_id=guild_id,
                        action="no_op",
                        outcome="skipped",
                        reason="gate_unresolved",
                        evidence_id=evidence.evidence_id,
                        timestamp=datetime.now(UTC),
                        corroborated=evidence.corroborated,
                    )
                )
                continue
            results.append(
                await self.repair_ticket_from_evidence(
                    evidence,
                    preflight=preflight,
                    close_reason="zombie:sweep",
                    actor_id="system",
                )
            )
        return results

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
        """Resolve *ticket_ref* and repair the ticket through the shared path."""
        ref = parse_ticket_ref(ticket_ref)
        if ref is None or (ref.number is None and ref.uuid is None):
            logger.warning(
                "repair_ticket_by_ref: unparseable reference (guild=%s, ref=%r)",
                guild_id,
                ticket_ref,
            )
            return None

        row: dict[str, Any] | None = None
        if ref.number is not None:
            try:
                row = await self._db.get_ticket_by_number(guild_id, ref.number)
            except Exception as exc:
                logger.warning(
                    "repair_ticket_by_ref: number lookup failed (guild=%s, ref=%r): %s",
                    guild_id,
                    ticket_ref,
                    exc,
                    exc_info=True,
                )
                logger.warning(
                    "repair_ticket_by_ref: audit skipped for database_error without ticketId (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                return RepairResult(
                    ticket_id="",
                    guild_id=guild_id,
                    action="no_op",
                    outcome="error",
                    reason="database_error",
                    evidence_id=None,
                    timestamp=datetime.now(UTC),
                )
            if row is None:
                logger.warning(
                    "repair_ticket_by_ref: number not found (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                logger.warning(
                    "repair_ticket_by_ref: audit skipped for ticket_not_found without ticketId (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                return RepairResult(
                    ticket_id="",
                    guild_id=guild_id,
                    action="no_op",
                    outcome="error",
                    reason="ticket_not_found",
                    evidence_id=None,
                    timestamp=datetime.now(UTC),
                )
        else:
            if ref.uuid is None:
                msg = "uuid not initialised"
                raise RuntimeError(msg)
            try:
                row = await self._db.get_ticket(ref.uuid, guild_id=guild_id)
            except Exception as exc:
                logger.warning(
                    "repair_ticket_by_ref: uuid lookup failed (guild=%s, ref=%r): %s",
                    guild_id,
                    ticket_ref,
                    exc,
                    exc_info=True,
                )
                logger.warning(
                    "repair_ticket_by_ref: audit skipped for database_error without ticketId (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                return RepairResult(
                    ticket_id="",
                    guild_id=guild_id,
                    action="no_op",
                    outcome="error",
                    reason="database_error",
                    evidence_id=None,
                    timestamp=datetime.now(UTC),
                )
            if row is None:
                logger.warning(
                    "repair_ticket_by_ref: uuid not found (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                logger.warning(
                    "repair_ticket_by_ref: audit skipped for ticket_not_found without ticketId (guild=%s, ref=%r)",
                    guild_id,
                    ticket_ref,
                )
                return RepairResult(
                    ticket_id="",
                    guild_id=guild_id,
                    action="no_op",
                    outcome="error",
                    reason="ticket_not_found",
                    evidence_id=None,
                    timestamp=datetime.now(UTC),
                )

        if row.get("guildId") != guild_id:
            logger.warning(
                "repair_ticket_by_ref: row guild mismatch (requested=%s, row=%s, ref=%r)",
                guild_id,
                row.get("guildId"),
                ticket_ref,
            )
            await self._audit_denied(
                guild_id,
                row.get("id") or "",
                "cross_guild_denied",
                actor_id,
            )
            return RepairResult(
                ticket_id=row.get("id") or "",
                guild_id=guild_id,
                action="no_op",
                outcome="skipped",
                reason="cross_guild_denied",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )

        return await self.repair_ticket_manual(
            row["id"],
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
        """Manually repair one ticket using explicit authority + fresh probe."""
        _ = preflight
        decision = evaluate_repair_authority(authority, global_grant=global_grant)
        if authority.target_guild_id != guild_id:
            await self._audit_denied(
                authority.guild_id or guild_id,
                ticket_id,
                "cross_guild_denied",
                actor_id,
            )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="skipped",
                reason="cross_guild_denied",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )
        if not decision.allowed:
            await self._audit_denied(
                guild_id,
                ticket_id,
                decision.reason or "insufficient_authority",
                actor_id,
            )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="skipped",
                reason=decision.reason or "insufficient_authority",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )

        row = None
        try:
            row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        except Exception:
            logger.warning(
                "Manual repair DB lookup failed for ticket %s (guild %s)",
                ticket_id,
                guild_id,
                exc_info=True,
            )
            await self._audit_denied(
                guild_id,
                ticket_id,
                "database_error",
                actor_id,
                outcome="error",
            )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="error",
                reason="database_error",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )
        if row is None:
            await self._audit_denied(
                guild_id,
                ticket_id,
                "ticket_not_found",
                actor_id,
                outcome="error",
            )
            return RepairResult(
                ticket_id=ticket_id,
                guild_id=guild_id,
                action="no_op",
                outcome="error",
                reason="ticket_not_found",
                evidence_id=None,
                timestamp=datetime.now(UTC),
            )

        channel_id = row.get("channelId")
        channel_exists = await probe_channel_absence(bot, guild_id, str(channel_id)) if channel_id else None

        evidence = IntegrityEvidence(
            ticket_id=ticket_id,
            guild_id=guild_id,
            channel_id=channel_id,
            status=row.get("status", ""),
            channel_exists=channel_exists,
            observed_at=datetime.now(UTC),
            source="manual",
        )

        from bot.services.integrity_report import evaluate_live_preflight

        manual_preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            observed_at=datetime.now(UTC).isoformat(),
        )
        return await self.repair_ticket_from_evidence(
            evidence,
            preflight=manual_preflight,
            close_reason="zombie:manual_repair",
            actor_id=actor_id,
        )

    async def _audit_denied(
        self,
        guild_id: str,
        ticket_id: str,
        reason: str,
        actor_id: str | None,
        *,
        outcome: str = "denied",
    ) -> None:
        """Persist best-effort structured audit evidence for a failed repair."""
        try:
            await self._db.insert_audit_row(
                guild_id,
                ticket_id,
                "repair",
                actor_id,
                outcome,
                reason,
            )
        except Exception:
            logger.warning(
                "Failed to write repair %s audit row for ticket %s (guild %s)",
                outcome,
                ticket_id,
                guild_id,
                exc_info=True,
            )

    async def schedule_close(
        self, guild_id: str, ticket_id: str, scheduled_close_at: str, scheduled_close_by: str
    ) -> None:
        """Set scheduledCloseAt/By for a ticket (guild-scoped)."""
        await self._db.update_ticket(
            ticket_id, guild_id=guild_id, scheduledCloseAt=scheduled_close_at, scheduledCloseBy=scheduled_close_by
        )

    async def cancel_scheduled_close(self, guild_id: str, ticket_id: str) -> None:
        """Clear scheduledCloseAt/By (guild-scoped, safe no-op when already null)."""
        await self._db.update_ticket(ticket_id, guild_id=guild_id, scheduledCloseAt=None, scheduledCloseBy=None)

    # -- scheduled-close timer message handling ---------------------------

    async def handle_timer_message(
        self,
        guild_id: str,
        ticket_row: dict[str, Any],
        content: str,
        author_id: str,
    ) -> TimerMessageResult | None:
        """Process a ``,<duration>`` or ``,cancel`` mod timer message.

        Encapsulates the timer state-machine: parses the duration, applies the
        2h..5d threshold gate, and either schedules the close immediately or
        signals the cog to show a :class:`ConfirmCancelView`. ``None`` return
        means the message is not a valid timer command (silent ignore).

        Args:
            guild_id: Guild snowflake as string (guild-scoped DB writes).
            ticket_row: The active ticket DB row (status already validated open/claimed).
            content: The raw message content (must start with ``,``).
            author_id: The invoking member's snowflake as string.

        Returns:
            - ``TimerMessageResult(action="scheduled", ...)``: close was scheduled
              immediately and the timer embed posted (or failed — see error flags).
            - ``TimerMessageResult(action="cancelled", ...)``: timer was cleared.
            - ``TimerMessageResult(action="needs_confirmation", ...)``: duration is
              outside 2h..5d; the cog MUST show a :class:`ConfirmCancelView` and
              call :meth:`confirm_timer_schedule` on confirm.
            - ``None``: content is not a valid timer command (e.g. ``,hola``).
        """
        ticket_id = ticket_row.get("id")
        if not ticket_id:
            return None
        content_lower = content.lower()

        if content_lower.startswith(",cancel"):
            try:
                await self.cancel_scheduled_close(guild_id, ticket_id)
            except Exception:
                logger.exception("Failed to cancel scheduled close for ticket %s", ticket_id)
            return TimerMessageResult(
                action="cancelled",
                guild_id=guild_id,
                ticket_id=ticket_id,
                author_id=author_id,
            )

        seconds = parse_duration_strict(content)
        if seconds is None:
            return None  # ,hola etc: silent ignore, no error embed

        if seconds < TIMER_MIN_SECONDS or seconds > TIMER_MAX_SECONDS:
            # Threshold breach: cog must show ConfirmCancelView, then call
            # confirm_timer_schedule on confirm.
            return TimerMessageResult(
                action="needs_confirmation",
                guild_id=guild_id,
                ticket_id=ticket_id,
                author_id=author_id,
                seconds=seconds,
                prompt_title=self._confirm_prompt_title(guild_id),
                prompt_desc=self._confirm_prompt_desc(guild_id, seconds),
            )

        # Immediate schedule (within 2h..5d)
        due_ts = datetime.now(UTC).timestamp() + seconds
        due_iso = datetime.fromtimestamp(due_ts, tz=UTC).isoformat()
        try:
            await self.schedule_close(guild_id, ticket_id, due_iso, author_id)
        except Exception:
            logger.exception("Failed to schedule close for ticket %s", ticket_id)
            return TimerMessageResult(
                action="scheduled",
                guild_id=guild_id,
                ticket_id=ticket_id,
                author_id=author_id,
                seconds=seconds,
                due_ts=due_ts,
                schedule_failed=True,
            )
        return TimerMessageResult(
            action="scheduled",
            guild_id=guild_id,
            ticket_id=ticket_id,
            author_id=author_id,
            seconds=seconds,
            due_ts=due_ts,
        )

    async def confirm_timer_schedule(
        self,
        guild_id: str,
        ticket_id: str,
        seconds: int,
        author_id: str,
    ) -> TimerMessageResult:
        """Execute the schedule on confirm-view confirmation.

        Called by the cog's ConfirmCancelView ``on_confirm`` callback after the
        mod confirms an out-of-threshold (``<2h`` or ``>5d``) duration.

        Args:
            guild_id: Guild snowflake as string.
            ticket_id: The ticket UUID to schedule the close for.
            seconds: The duration in seconds (passed through from the original parse).
            author_id: The confirming member's snowflake as string.

        Returns:
            A :class:`TimerMessageResult` with ``action="scheduled"`` and the
            computed ``due_ts``. The ``schedule_failed`` flag is set if the
            DB write raised.
        """
        due_ts = datetime.now(UTC).timestamp() + seconds
        due_iso = datetime.fromtimestamp(due_ts, tz=UTC).isoformat()
        schedule_failed = False
        try:
            await self.schedule_close(guild_id, ticket_id, due_iso, author_id)
        except Exception:
            logger.exception("Failed to schedule close on confirm for ticket %s", ticket_id)
            schedule_failed = True
        return TimerMessageResult(
            action="scheduled",
            guild_id=guild_id,
            ticket_id=ticket_id,
            author_id=author_id,
            seconds=seconds,
            due_ts=due_ts,
            schedule_failed=schedule_failed,
        )

    async def get_due_scheduled_tickets(self, guild_id: str, *, batch_size: int = 50) -> list[dict[str, Any]]:
        """Return due scheduled-close candidate rows for *guild_id* (guild-scoped).

        Encapsulates the DB query so the cog loop stays a thin facade. Each row
        is the raw camelCase DB row; the cog resolves the channel and fetches
        the full row for :meth:`close_ticket_full` (or clears stale fields if
        the ticket is no longer active).
        """
        return await self._db.get_scheduled_close_candidates(guild_id, batch_size=batch_size)

    async def upsert_timer_embed(
        self,
        channel: discord.TextChannel,
        guild_id: str,
        ticket_id: str,
        due_ts: float,
        seconds: int,
    ) -> None:
        """Post or edit the pinned timer embed carrying ``<t:R>``/``<t:F>``.

        Posts a fresh embed and pins it; if a pinned timer embed already exists
        (title contains ``<t:``), edits it in place instead of creating a duplicate.
        """
        unix = int(due_ts)
        remaining = format_remaining(seconds, guild_id=guild_id)
        title = t(guild_id, "tickets.timer.scheduled_title")
        if title.startswith("tickets.timer"):
            title = f"\u23f3 Cierra <t:{unix}:R> (<t:{unix}:F>)"
        else:
            try:
                title = title.format(unix=unix, remaining=remaining)
            except Exception:
                title = f"\u23f3 Cierra <t:{unix}:R> (<t:{unix}:F>)"
        if f"<t:{unix}:R>" not in title:
            title = f"\u23f3 Cierra <t:{unix}:R> (<t:{unix}:F>)"
        desc = t(guild_id, "tickets.timer.scheduled_description", remaining=remaining, unix=unix)
        if desc.startswith("tickets.timer"):
            desc = f"Cierre programado {remaining} — <t:{unix}:F>"
        embed = discord.Embed(title=title, description=desc, color=WARNING)
        with contextlib.suppress(Exception):
            pins = await channel.pins()
            for m in pins:
                if m.embeds and m.embeds[0].title and "<t:" in (m.embeds[0].title or ""):
                    with contextlib.suppress(Exception):
                        await m.edit(embed=embed)
                        return
        try:
            msg = await channel.send(embed=embed)
            with contextlib.suppress(Exception):
                await msg.pin(reason="Scheduled close by timer")
        except Exception:
            logger.exception("Failed to send timer embed for ticket %s", ticket_id)

    @staticmethod
    def _confirm_prompt_title(guild_id: str) -> str:
        """Resolve the localized confirm-prompt title (with fallback)."""
        title = t(guild_id, "tickets.timer.confirm_title")
        return "Confirm Scheduled Close" if title.startswith("tickets.timer") else title

    @staticmethod
    def _confirm_prompt_desc(guild_id: str, seconds: int) -> str:
        """Resolve the localized confirm-prompt description (with fallback)."""
        desc = t(guild_id, "tickets.timer.confirm_description")
        if desc.startswith("tickets.timer"):
            return f"Schedule close in {format_remaining(seconds, guild_id=guild_id)}? Confirm within 30s."
        return desc

    # -- orchestration (channel + transcript) -----------------------------

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
        """Create a ticket Discord channel, insert the ticket row, and rename if needed."""
        if parent_id is None and category_id is not None:
            count = await self._db.count_user_open_tickets_in_category(
                guild_id,
                str(author.id),
                category_id,
            )
            check_one_ticket_per_user_per_category(
                str(author.id),
                category_id,
                parent_id=None,
                count_fn=lambda _u, _c: count,
            )

        tentative_max = await self._db.get_max_ticket_number(guild_id)
        tentative_name = sanitize_channel_name(
            category_name,
            author.display_name,
            tentative_max + 1,
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
                ticket = await self._lifecycle.create_subticket(
                    parent_id=parent_id,
                    author_id=str(author.id),
                    category_id=category_id,
                    channel_id=str(channel.id),
                    guild_id=guild_id,
                )
            else:
                ticket = await self._lifecycle.create_ticket(
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
            category_name,
            author.display_name,
            ticket.ticket_number,
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
        """Close a single ticket end-to-end: transcript -> upload -> DB -> delete."""
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

        await self._lifecycle.close_ticket(
            ticket.id, closed_by=closed_by, transcript_url=transcript_url, guild_id=ticket.guild_id
        )
        # PR2: clear scheduled timer fields on close so no stale timer lingers.
        with contextlib.suppress(Exception):
            await self._db.update_ticket(
                ticket.id, guild_id=ticket.guild_id, scheduledCloseAt=None, scheduledCloseBy=None
            )

        if manual:
            await self._countdown_and_delete(channel, closed_by)
        else:
            await asyncio.sleep(CHANNEL_DELETE_DELAY)
            try:
                await channel.delete(reason=f"Ticket closed by {closed_by}")
            except discord.NotFound:
                logger.info("Ticket channel %s already deleted on silent close", channel.id)
            except discord.HTTPException:
                logger.exception("Failed to delete ticket channel %s", channel.id)

        return transcript_url

    @staticmethod
    async def _countdown_and_delete(
        channel: discord.TextChannel,
        closed_by: str,
    ) -> None:
        """Count down from 5 to 1, then delete the channel."""
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


@dataclass(frozen=True)
class TimerMessageResult:
    """Outcome of processing one ``,<duration>``/``,cancel`` timer message.

    Returned by :meth:`TicketRepairService.handle_timer_message` and
    :meth:`confirm_timer_schedule`. The cog inspects ``action`` to decide
    whether to upsert the timer embed, show a :class:`ConfirmCancelView`, or
    post a cancellation confirmation.
    """

    action: str  # "scheduled" | "cancelled" | "needs_confirmation"
    guild_id: str
    ticket_id: str
    author_id: str
    seconds: int = 0
    due_ts: float = 0.0
    schedule_failed: bool = False
    prompt_title: str = ""
    prompt_desc: str = ""
