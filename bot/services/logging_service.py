"""LoggingService — centralized audit log embed routing.

Replaces the private ``SentinelCog._log_action()`` with a shared service
consumed by both ``SentinelCog`` and ``AuditListener``.

Also exposes the two structured record builders that separate guild-scoped
ticket audit from bot-operator systemic diagnosis (product-artifact-audit).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import guild_footer_icon

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.services.ticket_invariants import GlobalMutationGrant

logger = logging.getLogger(__name__)

LOG_COLOR = INFO
MAX_FIELD_LENGTH = 1024

# Voice-state transition → (title key, description key). Reuses the
# pre-existing ``voice.*`` locale family (previously orphaned) instead of
# duplicating it — spec logging-service (cycle-5-quality-zero S3).
_VOICE_EVENT_KEYS: dict[str, tuple[str, str]] = {
    "join": ("voice.join_title", "voice.join_description"),
    "leave": ("voice.leave_title", "voice.leave_description"),
    "move": ("voice.move_title", "voice.move_description"),
    "mute": ("voice.mute_title", "voice.mute_description"),
    "deafen": ("voice.deafen_title", "voice.deafen_description"),
}


def _voice_channel_label(channel: object | None) -> str | None:
    """Return the display name of a voice channel, or ``None`` if absent."""
    if channel is None:
        return None
    return getattr(channel, "name", str(channel))


class ModerationTarget(Protocol):
    """Structural target accepted by :meth:`LoggingService.log_moderation_action`.

    ``discord.Member``/``discord.User`` satisfy it natively; cogs may pass
    their own typed value objects (e.g. an unban target dataclass) instead
    of fabricating attributes on framework objects.
    """

    id: int
    name: str
    mention: str


# Outcomes that represent a real ticket mutation (a conditional close executed).
_MUTATING_OUTCOMES = frozenset({"repaired"})


def _truncate(text: str, max_len: int = MAX_FIELD_LENGTH) -> str:
    """Truncate *text* to *max_len* characters, appending '…' if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


@dataclass(frozen=True)
class RepairAuditRecord:
    """Structured, guild-scoped audit evidence for one repair outcome.

    Truthful by construction: ``mutated`` is ``True`` ONLY for a
    ``repaired`` outcome. Denied, quarantined, skipped, already-closed, and
    error outcomes never report mutation. ``reason`` and ``source`` are
    preserved as structured context for later review.
    """

    guild_id: str
    ticket_id: str
    outcome: str
    mutated: bool
    reason: str | None = None
    source: str | None = None
    actor_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record using camelCase persistence keys."""
        return {
            "guildId": self.guild_id,
            "ticketId": self.ticket_id,
            "outcome": self.outcome,
            "mutated": self.mutated,
            "reason": self.reason,
            "source": self.source,
            "actorId": self.actor_id,
        }


@dataclass(frozen=True)
class OperatorDiagnosisRecord:
    """Structured, cross-guild operator diagnosis — read-only without a grant.

    ``mutated`` is ``False`` unless an explicit, confirmed
    :class:`~bot.services.ticket_invariants.GlobalMutationGrant` authorizes
    mutation. The record always names the target guilds it aggregates over.
    """

    target_guild_ids: tuple[str, ...]
    mutated: bool
    reason: str | None = None
    findings: tuple[str, ...] = ()


def build_repair_audit_record(
    *,
    guild_id: str,
    ticket_id: str,
    outcome: str,
    reason: str | None = None,
    source: str | None = None,
    actor_id: str | None = None,
) -> RepairAuditRecord:
    """Build a guild-scoped repair audit record from a repair outcome.

    ``mutated`` is derived strictly from *outcome*: only ``"repaired"``
    reports a mutation. Every other outcome (denied, quarantined, skipped,
    already_closed, error) is a non-mutating no-op/audit record.
    """
    return RepairAuditRecord(
        guild_id=guild_id,
        ticket_id=ticket_id,
        outcome=outcome,
        mutated=outcome in _MUTATING_OUTCOMES,
        reason=reason,
        source=source,
        actor_id=actor_id,
    )


def build_operator_diagnosis_record(
    *,
    target_guild_ids: list[str] | tuple[str, ...],
    findings: list[str] | tuple[str, ...] = (),
    grant: GlobalMutationGrant | None = None,
    actor_id: str | None = None,
) -> OperatorDiagnosisRecord:
    """Build a read-only (by default) cross-guild operator diagnosis record.

    Without an explicit, confirmed, actor-matching, target-matching,
    scope-matching :class:`~bot.services.ticket_invariants.GlobalMutationGrant`
    (validated against the *actor_id* performing the diagnosis), the record
    reports ``mutated=False``. The record always names every target guild it
    aggregates over and never implies mutation authority on its own.

    Mutation truthfulness requires the grant to satisfy EVERY binding: it must
    be confirmed, carry a non-empty reason, name the acting *actor_id*, name a
    target guild present in *target_guild_ids*, and use the ``"global"`` scope.
    Any mismatch is reported as a non-mutating record with a precise reason.
    """
    target = tuple(target_guild_ids)
    if grant is None:
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="operator_mutation_requires_grant",
            findings=tuple(findings),
        )
    if not grant.confirmed:
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_unconfirmed",
            findings=tuple(findings),
        )
    if not grant.reason or not grant.reason.strip():
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_missing_reason",
            findings=tuple(findings),
        )
    if actor_id is None:
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_actor_missing",
            findings=tuple(findings),
        )
    if grant.actor_id != actor_id:
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_actor_mismatch",
            findings=tuple(findings),
        )
    if grant.scope != "global":
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_scope_mismatch",
            findings=tuple(findings),
        )
    if grant.target_guild_id not in target:
        return OperatorDiagnosisRecord(
            target_guild_ids=target,
            mutated=False,
            reason="grant_target_mismatch",
            findings=tuple(findings),
        )
    return OperatorDiagnosisRecord(
        target_guild_ids=target,
        mutated=True,
        reason=grant.reason,
        findings=tuple(findings),
    )


class LoggingService:
    """Centralized audit log service.

    Resolves ``log_channel_id`` and ``log_enabled`` via ``GuildService``.
    Builds formatted embeds for 9 event types and routes them to the
    configured log channel.  Skips silently when logging is disabled or
    the channel is unavailable.
    """

    __slots__ = ("_bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self._bot = bot

    # ------------------------------------------------------------------
    # Public log methods
    # ------------------------------------------------------------------

    async def log_moderation_action(
        self,
        guild_id: str,
        action: str,
        target: discord.Member | discord.User | ModerationTarget,
        moderator: discord.Member,
        reason: str,
    ) -> None:
        """Log a moderation action (warn, mute, kick, ban, …).

        Args:
            guild_id: Discord guild snowflake.
            action: Human-readable action name (e.g. ``"Warn"``).
            target: The user or member who received the action. May also be
                any :class:`ModerationTarget`-compatible value object (e.g.
                ``SentinelCog.UnbanTarget``) carrying id/name/mention.
            moderator: The moderator who performed the action.
            reason: Free-text reason for the action.
        """
        if not await self._should_log(guild_id):
            return

        # The ``action`` fragment is a caller-supplied stable token (e.g.
        # "Warn"/"Mute"); the surrounding label is guild-localized. Audit
        # asymmetry note: cog callers own this audit call (design D3).
        embed = discord.Embed(
            title=t(guild_id, "log.moderation.title", action=action),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name=t(guild_id, "log.moderation.target"),
            value=f"{target.mention} ({target.name})",
            inline=True,
        )
        embed.add_field(
            name=t(guild_id, "log.moderation.moderator"),
            value=f"{moderator.mention} ({moderator.name})",
            inline=True,
        )
        if reason:
            embed.add_field(name=t(guild_id, "log.moderation.reason"), value=_truncate(reason), inline=False)

        await self._send_log(guild_id, embed)

    async def log_sentinel_loop(
        self,
        guild_id: str,
        phase: str,
        count: int,
    ) -> None:
        """Log a SentinelCog decay/expiry loop phase (hourly task).

        Each loop phase (``decay`` and ``expiry``) MUST log through this
        method so loop activity is auditable in the guild's log channel
        alongside other moderation actions. Brand-token colored, config-gated
        via ``_should_log`` (logEnabled + logChannelId), async-only.

        Args:
            guild_id: Guild snowflake as string.
            phase: ``"decay"`` (warning decay) or ``"expiry"`` (tempban expiry).
            count: Number of rows the phase processed (may be 0).
        """
        # Zero-count digest suppression (spec logging-service): an idle
        # cycle produces no embed at all.
        if count <= 0:
            return

        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=t(guild_id, "log.loop.title", phase=phase),
            description=t(guild_id, "log.loop.description", count=count),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name=t(guild_id, "log.loop.phase"), value=phase, inline=True)
        embed.add_field(name=t(guild_id, "log.loop.guild"), value=guild_id, inline=True)

        await self._send_log(guild_id, embed)

    async def log_message_edit(
        self,
        guild_id: str,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        """Log a message edit event.

        Embeds both the original and the updated content.
        Skips if the source channel is invisible to @everyone.
        """
        if not await self._should_log(guild_id):
            return
        if not self.can_log_in_channel(before.channel):  # type: ignore[arg-type]  # discord.py Message.channel is broader union than GuildChannel; runtime guard in can_log_in_channel handles non-text
            return

        channel_name = getattr(before.channel, "name", "unknown")
        embed = discord.Embed(
            title=t(guild_id, "log.message_edit.title", channel=channel_name),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        no_content = t(guild_id, "log.no_content")
        embed.add_field(
            name=t(guild_id, "log.message_edit.before"),
            value=_truncate(before.content or no_content),
            inline=False,
        )
        embed.add_field(
            name=t(guild_id, "log.message_edit.after"),
            value=_truncate(after.content or no_content),
            inline=False,
        )
        embed.set_footer(text=t(guild_id, "log.footer.message_id", id=before.id))

        await self._send_log(guild_id, embed)

    async def log_message_delete(
        self,
        guild_id: str,
        message: discord.Message,
    ) -> None:
        """Log a message delete event.

        Embeds the deleted message content and its author.
        Skips if the source channel is invisible to @everyone.
        """
        if not await self._should_log(guild_id):
            return
        if not self.can_log_in_channel(message.channel):  # type: ignore[arg-type]  # discord.py Message.channel is broader union than GuildChannel; runtime guard in can_log_in_channel handles non-text
            return

        channel_name = getattr(message.channel, "name", "unknown")
        content = message.content or t(guild_id, "log.no_content")
        embed = discord.Embed(
            title=t(guild_id, "log.message_delete.title", channel=channel_name),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name=t(guild_id, "log.message_delete.author"),
            value=f"{message.author.mention} ({message.author.name})",
            inline=True,
        )
        embed.add_field(name=t(guild_id, "log.message_delete.content"), value=_truncate(content), inline=False)
        embed.set_footer(text=t(guild_id, "log.footer.message_id", id=message.id))

        await self._send_log(guild_id, embed)

    async def log_member_join(
        self,
        guild_id: str,
        member: discord.Member,
    ) -> None:
        """Log a member joining the guild.

        Embeds the member mention, account creation date, and member count.
        """
        if not await self._should_log(guild_id):
            return

        created = (
            member.created_at.strftime("%Y-%m-%d")
            if member.created_at
            else t(guild_id, "log.member_join.unknown_created")
        )
        member_count = getattr(member.guild, "member_count", 0)
        embed = discord.Embed(
            title=t(guild_id, "log.member_join.title", mention=member.mention),
            description=t(guild_id, "log.member_join.description", created=created),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        if member_count:
            embed.set_footer(text=t(guild_id, "log.member_join.footer", count=member_count))

        await self._send_log(guild_id, embed)

    async def log_member_leave(
        self,
        guild_id: str,
        member: discord.Member,
    ) -> None:
        """Log a member leaving the guild.

        Embeds the member mention and their role names.
        """
        if not await self._should_log(guild_id):
            return

        role_names = [r.name for r in member.roles if r.name != "@everyone"]
        roles_text = ", ".join(f"@{r}" for r in role_names) if role_names else t(guild_id, "log.none")

        embed = discord.Embed(
            title=t(guild_id, "log.member_leave.title", mention=member.mention),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name=t(guild_id, "log.member_leave.roles"), value=roles_text, inline=False)

        await self._send_log(guild_id, embed)

    async def log_member_update(
        self,
        guild_id: str,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        """Log a member update event (e.g. role changes).

        Only logs when roles actually change — no-ops otherwise.
        """
        if not await self._should_log(guild_id):
            return

        before_names = {r.name for r in before.roles if r.name != "@everyone"}
        after_names = {r.name for r in after.roles if r.name != "@everyone"}

        added = after_names - before_names
        removed = before_names - after_names

        if not added and not removed:
            return  # Nothing changed — skip

        embed = discord.Embed(
            title=t(guild_id, "log.member_update.title", mention=after.mention),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        if added:
            embed.add_field(
                name=t(guild_id, "log.member_update.added"),
                value=", ".join(f"@{r}" for r in sorted(added)),
                inline=True,
            )
        if removed:
            embed.add_field(
                name=t(guild_id, "log.member_update.removed"),
                value=", ".join(f"@{r}" for r in sorted(removed)),
                inline=True,
            )

        await self._send_log(guild_id, embed)

    async def log_channel_create(
        self,
        guild_id: str,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log a channel creation event."""
        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=t(guild_id, "log.channel_create.title", channel=channel.name),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )

        await self._send_log(guild_id, embed)

    async def log_channel_delete(
        self,
        guild_id: str,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log a channel deletion event."""
        if not await self._should_log(guild_id):
            return

        embed = discord.Embed(
            title=t(guild_id, "log.channel_delete.title", channel=channel.name),
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )

        await self._send_log(guild_id, embed)

    async def log_voice_event(
        self,
        guild_id: str,
        member: discord.Member,
        transition: str,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Log a voice-state transition to the guild's configured log channel.

        Guild-scoped, async-only, brand-token colored, config-gated via
        ``_should_log`` (logEnabled + logChannelId). No blocking I/O.
        Routes strictly to guild G's logChannelId.

        Args:
            guild_id: Guild snowflake as string.
            member: Member whose voice state changed.
            transition: One of ``join|leave|move|mute|deafen``.
            before: Voice state before the change.
            after: Voice state after the change.
        """
        if not await self._should_log(guild_id):
            return

        # Guild-localized title + description: reuses the pre-existing
        # voice.* locale family (spec logging-service). The ``{from}``
        # placeholder is a reserved word, so its kwarg goes through a
        # dict unpack (valid at runtime).
        before_ch = getattr(before, "channel", None)
        after_ch = getattr(after, "channel", None)
        keys = _VOICE_EVENT_KEYS.get(transition)
        title = t(guild_id, "log.voice.unknown_title", transition=transition)
        description: str | None = None
        channel_value: str | None = None

        if keys is not None:
            title_key, desc_key = keys
            title = t(guild_id, title_key)
            if transition == "join" and after_ch is not None:
                channel_value = _voice_channel_label(after_ch)
                description = t(guild_id, desc_key, mention=member.mention, channel=channel_value)
            elif transition == "leave" and before_ch is not None:
                channel_value = _voice_channel_label(before_ch)
                description = t(guild_id, desc_key, mention=member.mention, channel=channel_value)
            elif transition == "move" and before_ch is not None and after_ch is not None:
                from_label = _voice_channel_label(before_ch)
                to_label = _voice_channel_label(after_ch)
                channel_value = f"{from_label} → {to_label}"
                description = t(
                    guild_id,
                    desc_key,
                    mention=member.mention,
                    **{"from": from_label, "to": to_label},
                )
            elif transition in {"mute", "deafen"} and after_ch is not None:
                channel_value = _voice_channel_label(after_ch)
                if transition == "mute":
                    state = t(
                        guild_id,
                        "voice.state_muted" if getattr(after, "self_mute", False) else "voice.state_unmuted",
                    )
                else:
                    state = t(
                        guild_id,
                        "voice.state_deafened" if getattr(after, "self_deaf", False) else "voice.state_undeafened",
                    )
                description = t(guild_id, desc_key, mention=member.mention, state=state, channel=channel_value)

        embed = discord.Embed(
            title=title,
            description=description,
            color=LOG_COLOR,
            timestamp=datetime.now(UTC),
        )
        # Member field always useful.
        embed.add_field(
            name=t(guild_id, "log.voice.member"),
            value=f"{member.mention} ({member.name})",
            inline=True,
        )

        # Channel context per transition.
        if channel_value is not None:
            embed.add_field(name=t(guild_id, "log.voice.channel"), value=channel_value, inline=True)

        embed.add_field(name=t(guild_id, "log.voice.transition"), value=transition, inline=True)

        await self._send_log(guild_id, embed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _should_log(self, guild_id: str) -> bool:
        """Return ``True`` if logging is enabled and a log channel is configured."""
        if self._bot.guild_service is None:
            msg = "GuildService initialised in setup_hook"
            raise RuntimeError(msg)
        config = await self._bot.guild_service.get_config(guild_id)
        if not config.log_enabled:
            return False
        return bool(config.log_channel_id)

    def can_log_in_channel(self, channel: discord.abc.GuildChannel) -> bool:
        """Return ``True`` if ``@everyone`` can read messages in *channel*.

        Only applies to ``discord.TextChannel`` — non-text channels always
        return ``False``.
        """
        if not isinstance(channel, discord.TextChannel):
            return False

        everyone_overwrites = channel.overwrites_for(channel.guild.default_role)
        return everyone_overwrites.read_messages is not False

    async def _send_log(self, guild_id: str, embed: discord.Embed) -> None:
        """Resolve the log channel and send *embed*."""
        if self._bot.guild_service is None:
            msg = "GuildService initialised in setup_hook"
            raise RuntimeError(msg)
        config = await self._bot.guild_service.get_config(guild_id)
        if not config.log_channel_id:
            return

        # Apply guild icon as footer icon (falls back to bot avatar).
        guild = self._bot.get_guild(int(guild_id))
        embed.set_footer(
            text=embed.footer.text or "",
            icon_url=guild_footer_icon(guild, self._bot),
        )

        log_channel = self._bot.get_channel(int(config.log_channel_id))
        if log_channel is None:
            logger.warning(
                "Log channel %s not found for guild %s — skipping log",
                config.log_channel_id,
                guild_id,
            )
            return

        try:
            await log_channel.send(embed=embed)  # type: ignore[union-attr]  # log channels are text channels in practice
        except discord.HTTPException:
            logger.exception(
                "Failed to send log embed to channel %s (guild=%s)",
                config.log_channel_id,
                guild_id,
            )
