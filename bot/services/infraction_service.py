"""InfractionService — warning CRUD and auto-escalation logic.

Implements the moderation business layer: creates infractions, keeps the
denormalised ``Member.warnings`` counter in sync, determines whether a
warning should trigger an automatic escalation (mute / kick), and executes
the full escalation side-effect chain (Discord action → DB row → log).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.models.infraction import Infraction

if TYPE_CHECKING:
    from bot.core.database import Database
    from bot.services.logging_service import LoggingService

logger = logging.getLogger(__name__)

# Escalation thresholds — hardcoded per design decision.
ESCALATION_MUTE_THRESHOLD = 3
ESCALATION_KICK_THRESHOLD = 5
ESCALATION_MUTE_DURATION = 3600  # 1 hour

# i18n fragments per escalation action (success / Forbidden failure).
_ESCALATION_SUCCESS_KEYS = {
    "MUTE": "sentinel.warn.auto_mute_description",
    "KICK": "sentinel.warn.auto_kick_description",
}
_ESCALATION_FAILED_KEYS = {
    "MUTE": "sentinel.warn.auto_mute_failed_description",
    "KICK": "sentinel.warn.auto_kick_failed_description",
}
# Log-channel action titles per escalation action.
_ESCALATION_LOG_TITLES = {
    "MUTE": "Mute (Auto-escalation)",
    "KICK": "Kick (Auto-escalation)",
}


@dataclass
class EscalationAction:
    """Describes an automatic moderation action triggered by warnings."""

    action: str  # "MUTE" | "KICK"
    duration: int  # seconds (MUTE only), 0 for KICK
    threshold: int  # warning count that triggered the action


class InfractionService:
    """Business logic for moderation infractions.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        logging_service: Optional :class:`~bot.services.logging_service.LoggingService`
            used by :meth:`apply_escalation` to audit executed escalations.
            Omitted by tests and callers that never escalate.
    """

    __slots__ = ("_db", "_logging_service")

    def __init__(self, db: Database, logging_service: LoggingService | None = None) -> None:
        self._db = db
        self._logging_service = logging_service

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def warn(
        self,
        guild_id: str,
        target_id: str,
        moderator_id: str,
        reason: str,
    ) -> tuple[Infraction, EscalationAction | None]:
        """Issue a WARN infraction and check for escalation.

        1. Persists the infraction.
        2. Increments the member's warning counter.
        3. Evaluates escalation thresholds.

        Returns:
            A tuple of ``(infraction, escalation)``.  ``escalation`` is
            ``None`` when the warning count is below the mute threshold.
        """
        row = await self._db.insert_infraction(
            guild_id=guild_id,
            target_id=target_id,
            moderator_id=moderator_id,
            type="WARN",
            reason=reason,
        )
        infraction = Infraction.from_db_row(row)

        await self._db.update_member_warnings(guild_id, target_id, delta=1)

        escalation = await self.check_escalation(guild_id, target_id)
        return infraction, escalation

    async def unwarn(self, guild_id: str, target_id: str) -> Infraction | None:
        """Deactivate the most recent active WARN and decrement warnings.

        Returns:
            The deactivated :class:`Infraction`, or ``None`` if there are
            no active warnings to revoke.
        """
        active = await self._db.get_active_warnings(guild_id, target_id)
        if not active:
            return None

        most_recent = active[0]  # ordered by createdAt DESC
        await self._db.deactivate_infraction(guild_id, most_recent["id"])
        await self._db.update_member_warnings(guild_id, target_id, delta=-1)

        return Infraction.from_db_row(most_recent)

    async def get_modlogs(
        self,
        guild_id: str,
        target_id: str,
        type_filter: str | None = None,
        after: str | None = None,
    ) -> list[Infraction]:
        """Retrieve infractions for a guild member with optional filters.

        Args:
            guild_id: Discord guild snowflake.
            target_id: Discord target user snowflake.
            type_filter: Optional type (``"WARN"``, ``"MUTE"``, …).
            after: Optional ISO-8601 lower bound for ``createdAt``.

        Returns:
            List of :class:`Infraction` objects (most recent first).
        """
        rows = await self._db.get_infractions(
            guild_id=guild_id,
            target_id=target_id,
            type=type_filter,
            after=after,
        )
        return [Infraction.from_db_row(r) for r in rows]

    async def tempban(
        self,
        guild_id: str,
        target_id: str,
        moderator_id: str,
        reason: str,
        expires_at: str,
    ) -> Infraction:
        """Insert a BAN infraction with ``expiresAt`` (tempban).

        Persists the infraction via ``insert_infraction(expires_at=...)``
        and returns the :class:`Infraction`. The caller (SentinelCog)
        is responsible for ``member.ban()`` and logging.
        """
        row = await self._db.insert_infraction(
            guild_id=guild_id,
            target_id=target_id,
            moderator_id=moderator_id,
            type="BAN",
            reason=reason,
            expires_at=expires_at,
        )
        return Infraction.from_db_row(row)

    async def unban(self, guild_id: str, target_id: str) -> Infraction | None:
        """Deactivate the active BAN for *target* in *guild* (idempotent).

        Returns the deactivated :class:`Infraction`, or ``None`` when no
        active BAN exists (no mutation, no error).
        """
        rows = await self._db.get_infractions(guild_id, target_id, type="BAN")
        active = [r for r in rows if r.get("active")]
        if not active:
            return None
        most_recent = active[0]
        await self._db.deactivate_infraction(guild_id, most_recent["id"])
        return Infraction.from_db_row(most_recent)

    async def decay_warnings(self, guild_id: str) -> int:
        """Deactivate 30d-old WARNs and decrement ``member.warnings``.

        For each expired WARN row: deactivates the infraction and
        decrements ``member.warnings`` by 1 via
        ``update_member_warnings(delta=-1)``. Floors at 0 — when the
        member's counter is already 0, the delta is clamped so warnings
        never goes negative (RPC also has GREATEST, service clamps as
        defense in depth). Returns the number of rows decayed.
        """
        expired = await self._db.get_expired_warns(guild_id)
        if not expired:
            return 0
        decayed = 0
        for row in expired:
            target_id = row.get("targetId") or row.get("target_id") or ""
            if not target_id:
                continue
            await self._db.deactivate_infraction(guild_id, row["id"])
            # Floor clamp: read current warnings, only decrement if >0
            try:
                member_row = await self._db.get_member(guild_id, target_id)
                current = int(member_row.get("warnings", 0)) if member_row else 0
            except Exception:
                # Lookup failed — assume 0 so the floor guarantee holds: we
                # deactivate the stale WARN row but never drive warnings
                # negative. Defense in depth with the RPC's GREATEST floor.
                current = 0
            if current > 0:
                await self._db.update_member_warnings(guild_id, target_id, delta=-1)
            decayed += 1
        return decayed

    async def expire_tempbans(
        self,
        guild_id: str,
        unban_fn: Callable[[str], Awaitable[None]] | None = None,
    ) -> int:
        """Expire past-expiry tempbans: scan → unban FIRST → deactivate on success.

        DB-sourced (restart-durable): scans ``get_expired_tempbans`` each
        call so a bot restart recovers pending unbans without an in-memory
        timer. Business logic (scan + deactivate + count) stays in the
        service; the caller injects ``unban_fn(target_id)`` to lift the
        Discord ban (Discord side-effect belongs to the cog). Returns the
        number of expired tempbans processed.

        Unban-first ordering (design D3): ``NotFound`` counts as success
        (manual ``/unban`` race) and deactivates; any other unban failure
        leaves the row ACTIVE with a warning so the next hourly scan
        re-selects and retries it — no retry flag or schema change.
        """
        expired = await self._db.get_expired_tempbans(guild_id)
        if not expired:
            return 0
        count = 0
        for row in expired:
            target_id = row.get("targetId") or row.get("target_id") or ""
            if not target_id:
                continue
            if unban_fn is not None:
                try:
                    await unban_fn(target_id)
                except discord.NotFound:
                    # Ban already lifted manually — treat as success.
                    pass
                except Exception:
                    # Keep the row ACTIVE: the next DB-sourced scan retries it.
                    logger.warning(
                        "unban failed for %s in guild %s — infraction kept active for retry",
                        target_id,
                        guild_id,
                        exc_info=True,
                    )
                    continue
            await self._db.deactivate_infraction(guild_id, row["id"])
            count += 1
        return count

    async def check_escalation(self, guild_id: str, target_id: str) -> EscalationAction | None:
        """Evaluate whether the member's warning count triggers auto-escalation.

        Thresholds (hardcoded):
            - **3 warnings** → mute for 1 hour
            - **5 warnings** → kick

        Uses exact-equality semantics (``count == threshold``) so escalation
        fires once per threshold crossing and does not repeat on subsequent
        warns (design decision #4).
        """
        member_row = await self._db.get_member(guild_id, target_id)
        if member_row is None:
            return None

        warnings_count: int = member_row.get("warnings", 0)

        if warnings_count == ESCALATION_KICK_THRESHOLD:
            return EscalationAction(
                action="KICK",
                duration=0,
                threshold=ESCALATION_KICK_THRESHOLD,
            )

        if warnings_count == ESCALATION_MUTE_THRESHOLD:
            return EscalationAction(
                action="MUTE",
                duration=ESCALATION_MUTE_DURATION,
                threshold=ESCALATION_MUTE_THRESHOLD,
            )

        return None

    async def apply_escalation(
        self,
        *,
        guild_id: str,
        member: discord.Member,
        moderator: discord.Member,
        escalation: EscalationAction,
    ) -> str:
        """Execute an escalation's full side-effect chain and report the outcome.

        The service owns the business chain (design D1): execute the Discord
        action implied by ``escalation.action`` (MUTE → ``timeout(duration)``;
        KICK → ``kick()``), persist the corresponding infraction row, and log
        the moderation action via :class:`~bot.services.logging_service.LoggingService`.
        The caller (cog) keeps input validation and embed delivery only.

        Only :class:`discord.Forbidden` is caught — it means the bot lacks
        permission for the action, so the localized failure fragment is
        returned WITHOUT persisting a row or logging success. Any other
        exception propagates to the caller untouched.

        Args:
            guild_id: Guild snowflake as string.
            member: The target member receiving the escalation.
            moderator: The moderator whose warn triggered the escalation.
            escalation: The :class:`EscalationAction` returned by
                :meth:`check_escalation`.

        Returns:
            The localized result message fragment for the caller to embed.
        """
        success_key = _ESCALATION_SUCCESS_KEYS.get(escalation.action)
        if success_key is None or escalation.action not in _ESCALATION_FAILED_KEYS:
            msg = f"Unsupported escalation action: {escalation.action}"
            raise ValueError(msg)

        try:
            match escalation.action:
                case "MUTE":
                    await member.timeout(
                        timedelta(seconds=escalation.duration),
                        reason=f"Auto-escalation: {escalation.threshold} warnings",
                    )
                case "KICK":
                    await member.kick(
                        reason=f"Auto-escalation: {escalation.threshold} warnings",
                    )
        except discord.Forbidden:
            # Permission denied → failure fragment; nothing persisted, nothing logged.
            logger.info("Escalation %s forbidden for %s in guild %s", escalation.action, member.id, guild_id)
            return t(guild_id, _ESCALATION_FAILED_KEYS[escalation.action], mention=member.mention)

        await self._db.insert_infraction(
            guild_id=guild_id,
            target_id=str(member.id),
            moderator_id=str(moderator.id),
            type=escalation.action,
            reason=f"Auto-escalation after {escalation.threshold} warnings",
        )

        if self._logging_service is not None:
            await self._logging_service.log_moderation_action(
                guild_id,
                _ESCALATION_LOG_TITLES[escalation.action],
                member,
                moderator,
                f"{escalation.threshold} warnings reached",
            )

        return t(guild_id, success_key, mention=member.mention, threshold=escalation.threshold)
