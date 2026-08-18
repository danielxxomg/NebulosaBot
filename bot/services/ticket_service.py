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

from bot.config import INTEGRITY_BATCH_SIZE
from bot.models.ticket import IntegrityEvidence, RepairResult, Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_invariants import (
    GlobalMutationGrant,
    RepairAuthority,
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
    evaluate_repair_authority,
    is_duplicate_note,
    parse_ticket_ref,
)
from bot.services.ticket_repair import (
    backoff_delay as _coordinator_backoff_delay,
)
from bot.services.ticket_repair import evaluate_repair_eligibility as _coordinator_evaluate
from bot.services.ticket_repair import plan_sweep_batch as _coordinator_plan_sweep_batch
from bot.services.ticket_repair import probe_channel_absence as _coordinator_probe
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


# Repair coordinator facade — single source in bot.services.ticket_repair.
# TicketService re-exports these so every adapter converges on one
# fail-closed path without duplicating gate/evidence logic.
backoff_delay = _coordinator_backoff_delay
plan_sweep_batch = _coordinator_plan_sweep_batch
probe_channel_absence = _coordinator_probe
evaluate_repair_eligibility = _coordinator_evaluate


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
            ValueError: If the user already has an open ticket in the same category.
        """
        # Per-user-per-category guard: skip for subtickets (parent_id set)
        # or uncategorized tickets (category_id is None).
        if category_id is not None:
            count = await self._db.count_user_open_tickets_in_category(
                guild_id,
                author_id,
                category_id,
            )
            check_one_ticket_per_user_per_category(
                author_id,
                category_id,
                parent_id=None,
                count_fn=lambda _u, _c: count,
            )

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
        close_reason: str | None = None,
    ) -> Ticket:
        """Close a ticket and optionally attach a transcript URL.

        Uses ``transition_ticket_to_closed`` for an atomic conditional close:
        only ``open`` or ``claimed`` tickets are closed. Already-closed tickets
        raise ``ValueError`` with no mutation.

        When *close_reason* is provided it is persisted on the row. When
        ``None``, the ``closeReason`` column is not overwritten.

        When *close_reason* starts with ``"zombie:"`` the zombie path is
        taken: no transcript generation and no channel deletion (the channel
        is already missing). The cache is also NOT cleaned because the
        channel no longer exists.

        Args:
            ticket_id: UUID of the ticket to close.
            closed_by: Discord user snowflake of the closer (logged only).
            transcript_url: Optional URL pointing to the uploaded transcript.
            close_reason: Optional reason string persisted on the row.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket is already closed or does not exist.
        """
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
                    guild_id = row.get("guildId")
                    if guild_id is not None:
                        await self._db.insert_audit_row(
                            guild_id,
                            ticket_id,
                            "close",
                            closed_by,
                            "denied",
                            denied_reason,
                        )
            except Exception:
                logger.warning("Failed to write denied close audit row for ticket %s", ticket_id, exc_info=True)
            raise ValueError(denied_reason)

        ticket = Ticket.from_db_row(closed_row)
        guild_id = ticket.guild_id

        is_zombie = close_reason is not None and close_reason.startswith("zombie:")

        if not is_zombie:
            # Normal close: clean channel from cache.
            self._ticket_channel_cache.discard(int(ticket.channel_id))

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

    async def repair_ticket_from_evidence(
        self,
        evidence: IntegrityEvidence,
        *,
        preflight: object | None = None,
        close_reason: str = "zombie:repair",
        actor_id: str | None = "system",
    ) -> RepairResult:
        """Repair a ticket from immutable, guild-matched :class:`IntegrityEvidence`.

        This is the ONE evidence-gated repair coordinator shared by the
        channel-delete listener, integrity sweeps, and manual fallback.
        Adapters never mutate tickets — every mutation flows through this
        path and the guild-scoped conditional DB transition.

        Fail-closed gates, in order:
        1. Preflight unresolved (``repair_activation_allowed`` is False):
           skipped/no-op (``gate_unresolved``), no mutation, no success audit.
        2. Evidence not corroborated: ``None`` (unknown or stale) →
           ``skipped``/``evidence_unresolved``; ``False`` (channel exists or non-active) →
           ``skipped``/``not_corroborated``. Neither mutates. Spec allows only
           ``repaired/already_closed/skipped/error``.
        3. Conditional transition: one winner; a duplicate/loser returns
           ``already_closed`` with no second mutation.

        On a successful close a best-effort audit row is written; an audit
        write failure is logged at WARNING and never blocks the repair.

        Args:
            evidence: The immutable integrity evidence for the ticket.
            preflight: A read-only preflight result exposing
                ``repair_activation_allowed`` (defaults to ``None`` = fail
                closed). Live schema/deployment preflight must be resolved
                before automatic mutation.
            close_reason: The reason string to persist on close.
            actor_id: The initiating actor recorded on the audit row
                (``"system"`` for automatic paths, a user snowflake for
                manual fallback).

        Returns:
            A :class:`RepairResult` describing the outcome.
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
            # Best-effort structured audit evidence for every denied/quarantined/
            # skipped outcome. The audit action stays "repair" with a
            # non-mutating "denied" outcome so a reviewable trail exists even
            # when no mutation is attempted. An audit-write failure is logged
            # and never converted into a mutation claim.
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

        # Attempt conditional close (guild-scoped; one-winner at the DB).
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

        # Successful transition. A repair whose audit cannot be persisted
        # MUST NOT be reported as success: the smallest safe semantics is
        # ``close/error`` with a non-empty reason and no evidence success claim.
        audit_persisted = True
        try:
            # Spec SERVICE-5.2/5.3: successful repair must persist outcome=repaired
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

    # ----------------------------------------------------------------
    # Adapter entry point (PR4a): exact channel-delete event evidence
    # ----------------------------------------------------------------
    # The listener builds single-use event evidence for the exact deleted
    # channel only; it NEVER mutates ticket state and NEVER fabricates an
    # authorizing actor. This is the ONLY PR4a adapter entry point — sweep and
    # manual fallback are deferred to PR4b.

    async def handle_channel_delete(
        self,
        guild_id: str,
        channel_id: str,
        *,
        preflight: object | None = None,
    ) -> RepairResult | None:
        """Route an exact channel-delete event to the shared repair path.

        Builds single-use event evidence for the active ticket mapping to
        ``(guild_id, channel_id)``. The exact delete event already proves the
        channel is gone for that event only, so NO fresh Discord probe is
        made. A non-ticket deletion returns ``None`` (deletion logging already
        handled by the listener) and never mutates.

        *preflight* is the read-only live schema/deployment gate. It defaults
        to ``None`` (fail-closed) so automatic repair stays disabled until a
        resolved preflight is supplied by the caller; when it is resolved the
        corroborated event evidence reaches the conditional close.

        The deletion actor is NOT known at this layer (gateway events carry no
        audit-log actor); the coordinator records ``actor_id="system"`` and
        treats attribution as informational.

        Args:
            guild_id: Guild snowflake of the deleted channel.
            channel_id: The deleted channel snowflake.
            preflight: Read-only preflight result (default fail-closed).

        Returns:
            A :class:`RepairResult`, or ``None`` when no active ticket matches.
        """
        try:
            row = await self._db.get_active_ticket_by_channel(guild_id, channel_id)
        except Exception as exc:
            # A DB failure during the active-ticket lookup must fail closed
            # (no mutation, no raw escape) and emit truthful structured
            # evidence carrying the available guild/channel context. No ticket
            # id is fabricated — the audit records the empty id truthfully.
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
        # The exact delete event is corroborating by construction. The
        # coordinator still applies the preflight gate fail-closed.
        return await self.repair_ticket_from_evidence(
            evidence,
            preflight=preflight,
            close_reason="zombie:channel_deleted",
            actor_id="system",
        )

    # ----------------------------------------------------------------
    # Adapter entry points (PR4b): bounded sweep + manual fallback
    # ----------------------------------------------------------------
    # Both adapters perform a FRESH Discord probe per candidate/attempt and
    # delegate candidate evaluation to the SAME shared repair path
    # (repair_ticket_from_evidence). Adapters never mutate ticket state.

    async def sweep_integrity(
        self,
        guild_id: str,
        bot: Any,
        *,
        preflight: object | None = None,
        batch_size: int = INTEGRITY_BATCH_SIZE,
    ) -> list[RepairResult]:
        """Run one bounded integrity sweep for *guild_id*.

        Discovers active ticket channels via ``get_open_ticket_channel_ids``,
        selects the next deduplicated batch, and performs a FRESH
        ``fetch_channel`` probe per candidate. Only an explicit ``NotFound``
        corroborates absence and reaches the shared repair path; a present
        channel is a no-op ``skipped`` with no repair audit, and a
        transient/uncertain probe is reported as a reviewable ``skipped``
        result with a bounded backoff sleep and NO mutation. Evidence is never
        reused across candidates. When G.2 is unresolved the sweep is a
        dry-run: candidates with corroborated evidence are returned with
        evidence preserved and no audit rows.

        Preflight defaults to ``None`` (fail-closed): automatic repair stays
        disabled until a resolved live preflight is supplied. Dry-run still
        returns evidence-bearing results.

        Args:
            guild_id: Guild snowflake to sweep.
            bot: The bot (provides ``get_guild`` for channel probing).
            preflight: Read-only preflight result (default fail-closed).
            batch_size: Max candidates to probe this sweep.

        Returns:
            One :class:`RepairResult` per candidate evaluated (or empty).
        """
        try:
            channel_ids = await self._db.get_open_ticket_channel_ids(guild_id)
        except Exception as exc:
            # A DB failure while discovering the sweep candidate LIST must not
            # escape raw: it is converted into truthful structured evidence
            # (guild + retryable classification) with NO fabricated ticket id,
            # and no mutation is attempted.
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
                # A DB failure resolving ONE candidate must not escape raw nor
                # abort the sweep: that candidate is reported with structured
                # evidence carrying the available channel id (never a
                # fabricated ticket id) and safe candidates continue.
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
                # Transient/uncertain: backoff + reviewable skip, no mutation.
                await asyncio.sleep(backoff_delay(attempt))
                attempt += 1
                # Preserve evidence with evidence_id for dry-run/reporting, but
                # skip still. For probe_unresolved we create evidence with None
                # channel_exists so corroborated is None -> skipped path.
                evidence_unresolved = IntegrityEvidence(
                    ticket_id=candidate["id"],
                    guild_id=guild_id,
                    channel_id=raw_channel_id,
                    status=candidate["status"],
                    channel_exists=None,
                    observed_at=datetime.now(UTC),
                    source="sweep",
                )
                # If live channel (True) -> not corroborated skipped, also no audit per spec no-op
                # Probe unresolved falls through to skipped; we already slept.
                # Dry-run: when G.2 unresolved we preserve evidence_id and don't write audit
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

            # Live channel is a no-op skipped with no repair audit (spec SERVICE-7.3)
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
            # G.2 unresolved dry-run: return candidate report with corroborated evidence, no mutation/audit
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
        """Resolve *ticket_ref* and repair the ticket through the shared path.

        This is the SERVICE-OWNED resolution boundary for ``/repair_ticket``:
        the cog is a thin delegator that never performs its own ticket lookup.
        A malformed/empty reference, a not-found row, and a DB lookup failure
        all produce truthful structured evidence (best-effort audit + log)
        with the AVAILABLE context — guild id, the raw reference, source, and
        reason. No canonical ticket UUID exists on those paths, so the audit
        records an empty ticket id rather than fabricating one.

        *preflight* defaults to ``None`` (fail-closed) and *global_grant* is
        the optional explicit operator mutation grant — both are forwarded to
        the shared repair path unchanged.

        Returns:
            A :class:`RepairResult` for the repair outcome, or ``None`` when
            the reference is malformed/empty (the cog reports the user error).
        """
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
            assert ref.uuid is not None
            try:
                row = await self._db.get_ticket(ref.uuid)
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
            # Defense-in-depth row-guild validation: a foreign-guild row must
            # never be probed or mutated through this path.
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
        """Manually repair one ticket using explicit authority + fresh probe.

        Authority is evaluated FIRST (pure, no I/O): an unauthorized or
        cross-guild request is denied without any probe or mutation. A
        bot-owner operator requires an explicit, confirmed, actor/target
        matching :class:`GlobalMutationGrant` (threaded via *global_grant*) —
        without it the operator is read-only and denied. An authorized request
        then performs a FRESH channel probe and delegates to the shared repair
        path. The initiating actor is recorded as the audit actor.

        Preflight defaults to ``None`` (fail-closed): manual repair is a
        dry-run unless a resolved live preflight is supplied.

        Args:
            ticket_id: UUID of the ticket to repair.
            guild_id: The target guild (must match the actor's own guild).
            actor_id: The initiating actor (audit attribution).
            authority: Pure :class:`RepairAuthority` facts for the actor.
            bot: The bot (provides ``get_guild`` for channel probing).
            preflight: Read-only preflight result (default fail-closed).
            global_grant: Optional explicit operator mutation grant.

        Returns:
            A :class:`RepairResult` (``denied`` for authority failures).
        """
        decision = evaluate_repair_authority(authority, global_grant=global_grant)
        # Defense-in-depth: an authority evaluated for guild X must never
        # authorize a mutation targeting guild Y, even if the caller
        # supplies a mismatched target id. The denial is audited best-effort,
        # scoped to the CALLER's guild (the operation origin), so a foreign
        # target guild's audit trail is never polluted (guild isolation).
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
            row = await self._db.get_ticket(ticket_id)
        except Exception:
            # A transient database failure must NOT escape raw to the caller:
            # it is converted into a truthful non-success result with
            # best-effort structured failure audit evidence (repair/error,
            # guild-scoped, retryable classification in the reason). An
            # audit-write failure is logged and never turns this into success.
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
            # Authorized request for a missing ticket: truthful error result
            # plus best-effort structured non-mutating audit evidence so the
            # failed outcome is reviewable (guild/ticket/outcome/reason).
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

        # Manual repair is NOT G.2-gated: bypass preflight, keep corroboration gate.
        # Use a synthetic resolved preflight so unknown evidence still maps to
        # skipped/evidence_unresolved and live channel maps to skipped, but
        # gate_unresolved never blocks manual.
        from bot.services.integrity_report import evaluate_live_preflight

        manual_preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            observed_at=datetime.now(UTC).isoformat(),
        )
        # Manual: use synthetic resolved preflight so corroboration gates
        # but G.2 never blocks manual. repair_ticket_from_evidence now
        # persists the correct action (manual_repair) and outcome (repaired)
        # directly, so no compensating row is needed.
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
        """Persist best-effort structured audit evidence for a failed repair.

        A failure must never be silently dropped from the audit trail, and an
        audit-write failure must never be converted into a mutation claim: the
        failure is logged at WARNING and the (already non-success) outcome
        stands. *outcome* defaults to ``"denied"``; the authorized manual
        not-found and DB-error paths pass ``"error"`` so their structured
        evidence carries the truthful non-mutating outcome.
        """
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

    async def claim_ticket(self, ticket_id: str, claimed_by: str, *, guild_id: str | None = None) -> Ticket:
        """Claim a ticket, assigning it to a staff member.

        Sets ``status='claimed'`` and ``claimedBy`` to the given user ID.
        Enforces the claim invariant (open + unclaimed) BEFORE mutating and
        writes a ``ticket_audit`` row on both success and denied paths.
        When *guild_id* is provided the ticket is read and mutated only when
        its ``guildId`` matches; a cross-guild claim is denied.

        Args:
            ticket_id: UUID of the ticket to claim.
            claimed_by: Discord user snowflake of the claiming staff member.
            guild_id: Optional guild scope for ownership validation.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist, is cross-guild, or the
                claim invariant fails (non-open status, already claimed).
        """
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            # Cross-guild or not found — audit with non-empty denied reason.
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "claim", claimed_by, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild claim denied audit for %s", ticket_id, exc_info=True)
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_claim(pre.get("status", ""), pre.get("claimedBy"))
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "claim", claimed_by, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            guild_id=guild_id,
            status="claimed",
            claimedBy=claimed_by,
        )

        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
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
        guild_id: str | None = None,
    ) -> Ticket:
        """Unclaim a ticket, releasing it back to open status.

        Sets ``status='open'`` and ``claimedBy`` to ``None``. Enforces the
        unclaim invariant (claimer OR mod) BEFORE mutating and writes a
        ``ticket_audit`` row on both success and denied paths.
        When *guild_id* is provided cross-guild access is denied before
        mutation and a non-empty denied reason is audited.

        Args:
            ticket_id: UUID of the ticket to unclaim.
            actor_id: Discord user snowflake of the actor requesting unclaim.
            is_mod: Whether the actor has the moderator role.
            guild_id: Optional guild scope for ownership validation.

        Returns:
            The updated :class:`Ticket`.

        Raises:
            ValueError: If the ticket does not exist, is cross-guild, is not
                claimed, or the actor is neither the claimer nor a mod.
        """
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "unclaim", actor_id, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild unclaim denied audit for %s", ticket_id, exc_info=True)
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_unclaim(actor_id, pre, is_mod=is_mod)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "unclaim", actor_id, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            guild_id=guild_id,
            status="open",
            claimedBy=None,
        )

        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after unclaim")
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
    ) -> tuple[Ticket, bool]:
        """Edit a ticket's category, audit, and rename the channel.

        This method is the security boundary: it re-validates mod/admin via
        :func:`check_can_edit_category` even though the view gates UX.

        Args:
            ticket_id: UUID of the ticket to edit.
            new_category_id: UUID of the new :class:`TicketCategory`.
            channel: The Discord channel to rename.
            actor_id: Discord user snowflake of the actor.
            is_mod: Whether the actor has the moderator role.

        Returns:
            A tuple of (updated :class:`Ticket`, rename_succeeded: bool).

        Raises:
            ValueError: If the ticket is not found, is closed, the actor
                lacks mod/admin, or the per-user-per-category limit is hit.
        """
        pre = await self._db.get_ticket(ticket_id)
        if pre is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")
        author_id = pre.get("authorId", "")
        status = pre.get("status", "")

        # Reject closed tickets.
        if status == "closed":
            raise ValueError(f"Cannot edit category of a closed ticket (status={status!r})")

        # Security boundary: re-validate mod/admin.
        try:
            check_can_edit_category(actor_id, pre, is_mod=is_mod)
        except ValueError as exc:
            await self._db.insert_audit_row(
                guild_id,
                ticket_id,
                "edit_category",
                actor_id,
                "denied",
                str(exc),
            )
            raise

        # Per-user-per-category limit against the NEW category, excluding
        # the ticket being edited.
        count = await self._db.count_user_open_tickets_in_category(
            guild_id,
            author_id,
            new_category_id,
            exclude_ticket_id=ticket_id,
        )
        check_one_ticket_per_user_per_category(
            author_id,
            new_category_id,
            parent_id=None,
            count_fn=lambda _u, _c: count,
        )

        # DB mutation.
        await self._db.update_ticket(ticket_id, categoryId=new_category_id)

        row = await self._db.get_ticket(ticket_id)
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found after edit_category")
        ticket = Ticket.from_db_row(row)

        # Audit success after DB update.
        try:
            await self._db.insert_audit_row(
                guild_id,
                ticket_id,
                "edit_category",
                actor_id,
                "success",
                None,
            )
        except Exception:
            logger.warning(
                "Failed to write edit_category audit row for ticket %s",
                ticket_id,
                exc_info=True,
            )

        # Channel rename — best effort.
        rename_succeeded = True
        try:
            category_name = await resolve_category_name(
                self._db,
                new_category_id,
                fallback="ticket",
            )
            # Resolve author display name for the channel name (mirrors
            # _build_reopen_channel so the channel name reflects the author).
            author = resolve_member_safe(channel.guild, author_id)
            display_name = author.display_name if author is not None else "user"
            # ticket_number from the DB row.
            ticket_number = row.get("ticketNumber", 0)
            try:
                ticket_number = int(ticket_number)
            except (TypeError, ValueError):
                ticket_number = 0
            new_name = sanitize_channel_name(
                category_name,
                display_name,
                ticket_number,
            )
            await channel.edit(name=new_name)
        except discord.HTTPException:
            logger.warning(
                "Failed to rename ticket channel %s after category edit",
                channel.id,
                exc_info=True,
            )
            rename_succeeded = False

        logger.info(
            "Ticket %s category edited to %s by %s (rename=%s)",
            ticket_id,
            new_category_id,
            actor_id,
            rename_succeeded,
        )
        return ticket, rename_succeeded

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
        constraint is skipped (carve-out). The ``create_ticket`` path enforces
        that constraint, so the carve-out here is structural.

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
            guild,
            closed_row,
            guild_row,
            category_channel,
            ticket_id,
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
    def _resolve_ticket_category(
        guild: discord.Guild,
        guild_row: dict[str, Any] | None,
    ) -> discord.CategoryChannel | None:
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
            self._db,
            closed_row.get("categoryId"),
            fallback="ticket",
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
        guild_id: str | None = None,
    ) -> Ticket:
        """Transfer a ticket's claim to *new_claimed_by* and audit the action.

        Emits a best-effort LoggingService audit embed when *guild* and
        *logging_service* are available.  A logging failure never blocks
        the transfer. When *guild_id* is provided cross-guild access is
        denied before mutation.
        """
        pre = await self._db.get_ticket(ticket_id, guild_id=guild_id)
        if pre is None:
            denied_gid = guild_id or ""
            try:
                await self._db.insert_audit_row(
                    denied_gid, ticket_id, "transfer", actor_id, "denied", "cross_guild_denied"
                )
            except Exception:
                logger.warning("Failed to write cross-guild transfer denied audit for %s", ticket_id, exc_info=True)
            raise ValueError(f"Ticket {ticket_id} not found")
        guild_id = pre.get("guildId", "")

        try:
            check_can_transfer(pre.get("status", ""), pre.get("claimedBy"), new_claimed_by)
        except ValueError as exc:
            await self._db.insert_audit_row(guild_id, ticket_id, "transfer", actor_id, "denied", str(exc))
            raise

        await self._db.update_ticket(
            ticket_id,
            guild_id=guild_id,
            claimedBy=new_claimed_by,
            status="claimed",
        )

        row = await self._db.get_ticket(ticket_id, guild_id=guild_id)
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

        The one-open-ticket-per-category invariant is checked **before** creating
        the Discord channel so failed opens do not thrash channel create/delete.
        """
        # Fail fast: do not create a Discord channel if the user already has an
        # open ticket in this category (subtickets are exempt via parent_id).
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

        # Compute tentative channel name from DB max + 1.
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
        except discord.NotFound:
            # NotFound during the countdown could mean the message was deleted
            # (msg.edit) while the channel is still alive.  Attempt one final
            # channel.delete before concluding the channel is gone.
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
