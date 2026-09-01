"""SentinelCog — moderation commands for NebulosaBot.

Provides 9 slash moderation commands: warn, unwarn, mute, unmute, kick,
ban, lock, unlock, and modlogs.  Moderation commands are gated by the
permission matrix via ``@can_check("moderation.<key>")``; lock/unlock/
modlogs keep ``@is_mod()`` and sync stays ``@is_admin()``.  Actions log
to the configured mod-log channel when enabled.

NOTE: Slash command descriptions are Discord UI metadata, not runtime responses.
They remain in English; t() localizes runtime responses only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.watchdog import get_watchdog
from bot.core.context import NebulosaContext  # noqa: F401 -- kept for shim compat
from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.checks import can_check, is_mod
from bot.utils.embeds import (
    error_embed,
    info_embed,
    success_embed,
)
from bot.utils.paginator import EmbedPaginator
from bot.utils.time import parse_duration, parse_duration_optional
from bot.views.confirmation import ConfirmCancelView

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

MODLOGS_PER_PAGE = 5


@dataclass(slots=True)
class UnbanTarget:
    """Typed ``/unban`` target value object (spec sentinel-commands).

    Carries the user id plus display metadata (mention/name) so
    ``guild.unban`` (Snowflake) and moderation-log embeds render correctly
    WITHOUT fabricating attributes on framework objects like
    ``discord.Object``.
    """

    id: int
    name: str
    mention: str


# ======================================================================
# SentinelCog
# ======================================================================


class SentinelCog(commands.Cog, name="Sentinel"):
    """Moderation commands with auto-escalation and audit logging."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def cog_unload(self) -> None:
        """Cancel the hourly decay+expiry loop when the cog is unloaded."""
        try:
            if hasattr(self, "decay_expiry_loop") and self.decay_expiry_loop.is_running():
                self.decay_expiry_loop.cancel()
        except Exception:
            logger.debug("cog_unload cancel failed", exc_info=True)

    async def cog_load(self) -> None:
        """Start the hourly decay+expiry loop when the cog loads.

        Mirrors :meth:`TicketsCog.cog_load` guard style: only start when the
        loop attribute exists and is not already running. Without this the
        ``@tasks.loop(hours=1) decay_expiry_loop`` is dead code — tempban
        auto-expiry + 30d warn decay never run in production.
        """
        if hasattr(self, "decay_expiry_loop") and not self.decay_expiry_loop.is_running():
            self.decay_expiry_loop.start()
            logger.info("Sentinel decay+expiry loop started (interval: 1h)")
            wd = get_watchdog(self.bot)
            if wd:
                wd.register("decay_expiry_loop", 3600)

    def _to_ctx(self, src: object):
        from bot.cogs._slash_compat import is_context_like as _is_ctx  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        if _is_ctx(src):
            return src
        from bot.cogs._slash_compat import InteractionContext as _InteractionContext  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        return _InteractionContext(src, self.bot)  # type: ignore[arg-type]

    @staticmethod
    def _gid(src: object) -> str:
        guild = getattr(src, "guild", None) or getattr(getattr(src, "interaction", None), "guild", None)
        if guild is None:
            msg = "Guild-only command"
            raise RuntimeError(msg)
        return str(guild.id)

    def _collect_guild_ids(self) -> list[str]:
        """Collect guild IDs from bot.guilds (best-effort, no throw)."""
        ids: list[str] = []
        for g in getattr(self.bot, "guilds", []) or []:
            gid = getattr(g, "id", None)
            if gid is not None:
                ids.append(str(gid))
        return ids

    async def _expire_tempbans_for_guild(self, guild_id: str) -> None:
        """DB-sourced tempban expiry for one guild — thin orchestration.

        Business logic (scan + deactivate + count) lives in
        ``InfractionService.expire_tempbans``; this cog only resolves the
        guild object, builds the Discord ``unban`` callback, logs the phase
        through ``LoggingService.log_sentinel_loop``, and keeps restart
        durability via the DB source of truth.
        """
        if self.bot.infraction_service is None:
            return

        guild_obj = None
        try:
            getter = getattr(self.bot, "get_guild", None)
            guild_obj = getter(int(guild_id)) if callable(getter) and guild_id.isdigit() else None
        except Exception:  # noqa: BLE001 -- guild cache best-effort; any lookup failure falls back to None
            guild_obj = None

        async def _unban_target(target_id: str) -> None:
            """Lift the Discord ban for an expired tempban (cog side-effect)."""
            if guild_obj is None or not target_id:
                return
            uid = int(target_id) if target_id.isdigit() else None
            if uid is None:
                return
            await guild_obj.unban(discord.Object(id=uid), reason="Tempban expired")

        try:
            expired_count = await self.bot.infraction_service.expire_tempbans(
                guild_id,
                unban_fn=_unban_target,
            )
        except Exception:
            logger.exception("tempban expiry scan failed for guild %s", guild_id)
            return

        if self.bot.logging_service is not None:
            try:
                await self.bot.logging_service.log_sentinel_loop(guild_id, "expiry", expired_count)
            except Exception:
                logger.exception("log_sentinel_loop(expiry) failed for %s (non-fatal)", guild_id)

    @tasks.loop(hours=1)
    async def decay_expiry_loop(self) -> None:
        """Hourly: decay 30d WARNs then expire tempbans (DB-sourced, restart-durable).

        Each phase (decay then expiry) logs through ``LoggingService.log_sentinel_loop``
        so loop activity is auditable in the guild's log channel. Business logic
        (scan + deactivate + count) stays in ``InfractionService``; this cog only
        orchestrates per-guild iteration and injects the Discord unban callback.
        """
        wd = get_watchdog(self.bot)
        if wd:
            wd.heartbeat("decay_expiry_loop")
        if self.bot.db is None or self.bot.infraction_service is None:
            return
        for gid in self._collect_guild_ids():
            try:
                decayed = await self.bot.infraction_service.decay_warnings(gid)
                if self.bot.logging_service is not None:
                    await self.bot.logging_service.log_sentinel_loop(gid, "decay", decayed)
            except Exception:
                logger.exception("decay_warnings failed for guild %s", gid)
            await self._expire_tempbans_for_guild(gid)

    @decay_expiry_loop.before_loop
    async def _before_decay_expiry_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _guild_id(ctx: NebulosaContext) -> str:
        """Return the guild ID as a string for the current context."""
        if ctx.guild is None:
            msg = "Guild-only command"
            raise RuntimeError(msg)
        return str(ctx.guild.id)

    async def _validate_target(
        self,
        ctx: NebulosaContext,
        target: discord.Member,
        action: str,
    ) -> bool:
        """Validate that *target* is a legal moderation target.

        Returns ``True`` if the target passes all guards.  Sends an
        appropriate error embed to *ctx* and returns ``False`` when
        a guard fails.
        """
        guild_id = self._guild_id(ctx)
        if self.bot.user is None:
            msg = "Bot user available after on_ready"
            raise RuntimeError(msg)
        if target.id == self.bot.user.id:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.validate.self_target_title"),
                    t(guild_id, "sentinel.validate.self_target_description"),
                )
            )
            return False

        if target.id == ctx.author.id:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.validate.self_target_title"),
                    t(guild_id, "sentinel.validate.cannot_self_description", action=action),
                )
            )
            return False

        # Role hierarchy: the bot's top role must be above the target's.
        bot_member = ctx.guild.me if ctx.guild is not None else None
        if (
            ctx.guild is not None
            and bot_member is not None
            and bot_member.top_role <= target.top_role
            and target != ctx.guild.owner
        ):
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.validate.role_hierarchy_title"),
                    t(guild_id, "sentinel.validate.role_hierarchy_description", action=action, mention=target.mention),
                )
            )
            return False

        # Author hierarchy: author's top role must be strictly above target's (owner exempt).
        if ctx.guild is not None and ctx.author != ctx.guild.owner:
            try:
                author_role = getattr(ctx.author, "top_role", None)
                if author_role is not None and author_role <= target.top_role:
                    await ctx.send(
                        embed=error_embed(
                            t(guild_id, "sentinel.validate.role_hierarchy_title"),
                            t(
                                guild_id,
                                "sentinel.validate.role_hierarchy_description",
                                action=action,
                                mention=target.mention,
                            ),
                        )
                    )
                    return False
            except Exception:
                logger.debug("author hierarchy check failed — keeping bot-hierarchy only", exc_info=True)

        return True

    async def _handle_mod_error(
        self,
        ctx: NebulosaContext,
        error: Exception,
        action: str,
        target: discord.Member,
    ) -> None:
        """Map common moderation exceptions to user-friendly embeds."""
        guild_id = self._guild_id(ctx)
        if isinstance(error, discord.Forbidden):
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.error.permission_denied_title"),
                    t(guild_id, "sentinel.error.permission_denied_description", action=action, mention=target.mention),
                )
            )
        elif isinstance(error, discord.HTTPException):
            logger.exception("HTTP error during %s on %s", action, target.id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.error.action_failed_title"),
                    t(guild_id, "sentinel.error.action_failed_description", action=action, mention=target.mention),
                )
            )
        else:
            logger.exception("Unexpected error during %s on %s", action, target.id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.error.unexpected_title"),
                    t(guild_id, "sentinel.error.unexpected_description", action=action, mention=target.mention),
                )
            )

    # ==================================================================
    # 5.2 — /warn + /unwarn
    # ==================================================================

    @app_commands.command(
        name="warn",
        description=app_commands.locale_str(
            "Advertir a un miembro.",
            key="slash.descriptions.warn",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str("El miembro a advertir", key="slash.describes.warn.member"),
        reason=app_commands.locale_str("Razón de la advertencia", key="slash.describes.warn.reason"),
    )
    @app_commands.default_permissions(moderate_members=True)
    @can_check("moderation.warn")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, *, reason: str) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Issue a warning and check for auto-escalation."""
        if not await self._validate_target(ctx, member, "warn"):
            return

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        if self.bot.infraction_service is None:
            msg = "InfractionService initialised in setup_hook"
            raise RuntimeError(msg)
        infraction_service = self.bot.infraction_service
        try:
            _infraction, escalation = await infraction_service.warn(
                guild_id,
                target_id,
                moderator_id,
                reason,
            )
        except Exception:
            logger.exception("InfractionService.warn() failed")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.warn.failed_title"),
                    t(guild_id, "sentinel.warn.failed_description"),
                )
            )
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        moderator = ctx.author
        if not isinstance(moderator, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Warn",
            member,
            moderator,
            reason,
        )

        # Execute escalation side-effects through the service (cycle-4-debt-zero D1).
        escalation_msg = ""
        if escalation is not None:
            escalation_msg = await infraction_service.apply_escalation(
                guild_id=guild_id,
                member=member,
                moderator=moderator,
                escalation=escalation,
            )

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.warn.success_title"),
                t(
                    guild_id,
                    "sentinel.warn.success_description",
                    mention=member.mention,
                    reason=reason,
                )
                + escalation_msg,
            )
        )

    @app_commands.command(
        name="unwarn",
        description=app_commands.locale_str(
            "Quitar la advertencia más reciente de un miembro.",
            key="slash.descriptions.unwarn",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro a quitar advertencia",
            key="slash.describes.unwarn.member",
        )
    )
    @app_commands.default_permissions(moderate_members=True)
    @can_check("moderation.warn")
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Deactivate the most recent active warning."""
        if not await self._validate_target(ctx, member, "unwarn"):
            return

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)

        if self.bot.infraction_service is None:
            msg = "InfractionService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            result = await self.bot.infraction_service.unwarn(guild_id, target_id)
        except Exception:
            logger.exception("InfractionService.unwarn() failed")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.unwarn.failed_title"),
                    t(guild_id, "sentinel.unwarn.failed_description"),
                )
            )
            return

        if result is None:
            await ctx.send(
                embed=info_embed(
                    t(guild_id, "sentinel.unwarn.no_warnings_title"),
                    t(guild_id, "sentinel.unwarn.no_warnings_description", mention=member.mention),
                )
            )
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unwarn",
            member,
            ctx.author,
            t(guild_id, "sentinel.unwarn.audit_reason", id=result.id),
        )
        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.unwarn.success_title"),
                t(guild_id, "sentinel.unwarn.success_description", mention=member.mention),
            )
        )

    # ==================================================================
    # 5.3 — /mute + /unmute
    # ==================================================================

    @app_commands.command(
        name="mute",
        description=app_commands.locale_str(
            "Silenciar (timeout) a un miembro.",
            key="slash.descriptions.mute",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro a silenciar",
            key="slash.describes.mute.member",
        ),
        duration=app_commands.locale_str(
            'Duración (ej. "1h", "30m", "1h30m"). Por defecto: 1h',
            key="slash.describes.mute.duration",
        ),
        reason=app_commands.locale_str(
            "Razón del silencio",
            key="slash.describes.mute.reason",
        ),
    )
    @app_commands.default_permissions(moderate_members=True)
    @can_check("moderation.mute")
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str = "1h",
        *,
        reason: str = "",
    ) -> None:
        """Apply a timeout to *member*."""
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        if not await self._validate_target(ctx, member, "mute"):
            return

        duration_seconds = parse_duration(duration)
        guild_id = self._guild_id(ctx)
        if not reason:
            reason = t(guild_id, "sentinel.default_reason")
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        try:
            await member.timeout(
                timedelta(seconds=duration_seconds),
                reason=reason,
            )
        except discord.DiscordException as exc:
            await self._handle_mod_error(ctx, exc, "mute", member)
            return

        # Create MUTE infraction via the service (spec infraction-service:
        # cogs never insert rows directly). The audit below is the single
        # caller-side log site; the service performs no Discord action.
        if self.bot.infraction_service is None:
            msg = "InfractionService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            await self.bot.infraction_service.mute(
                guild_id,
                target_id,
                moderator_id,
                reason,
            )
        except Exception:
            logger.exception("Failed to persist MUTE infraction (non-fatal)")

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Mute",
            member,
            ctx.author,
            reason,
        )

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.mute.success_title"),
                t(
                    guild_id,
                    "sentinel.mute.success_description",
                    mention=member.mention,
                    duration=duration,
                    reason=reason,
                ),
            )
        )

    @app_commands.command(
        name="unmute",
        description=app_commands.locale_str(
            "Quitar el silencio de un miembro.",
            key="slash.descriptions.unmute",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "El miembro a quitar silencio",
            key="slash.describes.unmute.member",
        )
    )
    @app_commands.default_permissions(moderate_members=True)
    @can_check("moderation.mute")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Remove the timeout from *member*."""
        if not await self._validate_target(ctx, member, "unmute"):
            return

        guild_id = self._guild_id(ctx)

        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
        except discord.DiscordException as exc:
            await self._handle_mod_error(ctx, exc, "unmute", member)
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unmute",
            member,
            ctx.author,
            t(guild_id, "sentinel.unmute.audit_reason"),
        )

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.unmute.success_title"),
                t(guild_id, "sentinel.unmute.success_description", mention=member.mention),
            )
        )

    # ==================================================================
    # 5.4 — /kick + /ban
    # ==================================================================

    @app_commands.command(
        name="kick",
        description=app_commands.locale_str(
            "Expulsar a un miembro del servidor.",
            key="slash.descriptions.kick",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str("El miembro a expulsar", key="slash.describes.kick.member"),
        reason=app_commands.locale_str("Razón de la expulsión", key="slash.describes.kick.reason"),
    )
    @app_commands.default_permissions(moderate_members=True)
    @can_check("moderation.kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, *, reason: str) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Kick *member* from the guild after confirmation."""
        if not await self._validate_target(ctx, member, "kick"):
            return

        guild_id = self._guild_id(ctx)

        async def _do_kick(interaction: discord.Interaction) -> None:
            safe_reason = discord.utils.escape_markdown(reason)
            target_id = str(member.id)
            moderator_id = str(ctx.author.id)
            try:
                await member.kick(reason=reason)
            except discord.DiscordException as exc:
                await self._handle_mod_error(ctx, exc, "kick", member)
                return

            # Persist KICK via the service (cogs never insert rows
            # directly); the audit below is the single caller-side log site.
            if self.bot.infraction_service is None:
                msg = "InfractionService initialised in setup_hook"
                raise RuntimeError(msg)
            try:
                await self.bot.infraction_service.kick(
                    guild_id,
                    target_id,
                    moderator_id,
                    reason,
                )
            except Exception:
                logger.exception("Failed to persist KICK infraction (non-fatal)")

            if self.bot.logging_service is None:
                msg = "LoggingService initialised in setup_hook"
                raise RuntimeError(msg)
            if not isinstance(ctx.author, discord.Member):
                msg = "ctx.author must be discord.Member"
                raise TypeError(msg)
            await self.bot.logging_service.log_moderation_action(
                guild_id,
                "Kick",
                member,
                ctx.author,
                reason,
            )

            # Ephemeral-standard: the confirmation dialog is ephemeral, but
            # the final action result MUST be permanent (visible to the
            # channel). Edit the ephemeral confirm to a closed notice, then
            # send the permanent action embed to the channel (tempban pattern).
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=t(guild_id, "confirm.confirmed_title"),
                    color=INFO,
                ),
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await ctx.channel.send(
                embed=success_embed(
                    t(guild_id, "sentinel.kick.success_title"),
                    t(guild_id, "sentinel.kick.success_description", mention=member.mention, reason=safe_reason),
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        view = ConfirmCancelView(
            guild_id=guild_id,
            owner_id=ctx.author.id,
            on_confirm=_do_kick,
        )
        safe_kick_reason = discord.utils.escape_markdown(reason)
        msg = await ctx.send(
            embed=discord.Embed(
                title=t(guild_id, "confirm.kick_confirm_title"),
                description=t(
                    guild_id,
                    "confirm.kick_confirm_description",
                    mention=member.mention,
                    reason=safe_kick_reason,
                ),
                color=INFO,
            ),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = msg

    @app_commands.command(
        name="ban",
        description=app_commands.locale_str(
            "Prohibir a un miembro del servidor.",
            key="slash.descriptions.ban",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str("El miembro a prohibir", key="slash.describes.ban.member"),
        reason=app_commands.locale_str("Razón de la prohibición", key="slash.describes.ban.reason"),
        delete_days=app_commands.locale_str(
            "Días de mensajes a eliminar (0-7, por defecto: 0)",
            key="slash.describes.ban.delete_days",
        ),
    )
    @app_commands.default_permissions(ban_members=True)
    @can_check("moderation.ban")
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        reason: str,
        delete_days: int = 0,
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Ban *member* from the guild after confirmation.  Requires Administrator permission."""
        if not await self._validate_target(ctx, member, "ban"):
            return

        # Clamp delete_days to [0, 7].
        delete_days = max(0, min(7, delete_days))

        guild_id = self._guild_id(ctx)

        async def _do_ban(interaction: discord.Interaction) -> None:
            safe_reason = discord.utils.escape_markdown(reason)
            target_id = str(member.id)
            moderator_id = str(ctx.author.id)
            try:
                await member.ban(reason=reason, delete_message_days=delete_days)
            except discord.DiscordException as exc:
                await self._handle_mod_error(ctx, exc, "ban", member)
                return

            # Persist BAN via the service (cogs never insert rows
            # directly); the audit below is the single caller-side log site.
            if self.bot.infraction_service is None:
                msg = "InfractionService initialised in setup_hook"
                raise RuntimeError(msg)
            try:
                await self.bot.infraction_service.ban(
                    guild_id,
                    target_id,
                    moderator_id,
                    reason,
                )
            except Exception:
                logger.exception("Failed to persist BAN infraction (non-fatal)")

            if self.bot.logging_service is None:
                msg = "LoggingService initialised in setup_hook"
                raise RuntimeError(msg)
            if not isinstance(ctx.author, discord.Member):
                msg = "ctx.author must be discord.Member"
                raise TypeError(msg)
            await self.bot.logging_service.log_moderation_action(
                guild_id,
                "Ban",
                member,
                ctx.author,
                reason,
            )

            # Ephemeral-standard: dialog ephemeral, final result permanent
            # (tempban two-step pattern — see _do_kick).
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=t(guild_id, "confirm.confirmed_title"),
                    color=INFO,
                ),
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await ctx.channel.send(
                embed=success_embed(
                    t(guild_id, "sentinel.ban.success_title"),
                    t(guild_id, "sentinel.ban.success_description", mention=member.mention, reason=safe_reason),
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        view = ConfirmCancelView(
            guild_id=guild_id,
            owner_id=ctx.author.id,
            on_confirm=_do_ban,
        )
        safe_ban_reason = discord.utils.escape_markdown(reason)
        msg = await ctx.send(
            embed=discord.Embed(
                title=t(guild_id, "confirm.ban_confirm_title"),
                description=t(
                    guild_id,
                    "confirm.ban_confirm_description",
                    mention=member.mention,
                    reason=safe_ban_reason,
                    delete_days=delete_days,
                ),
                color=INFO,
            ),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = msg

    # ==================================================================
    # 5.5 — /lock + /unlock
    # ==================================================================

    @app_commands.command(
        name="lock",
        description=app_commands.locale_str(
            "Bloquear un canal (denegar send_messages para @everyone).",
            key="slash.descriptions.lock",
        ),
    )
    @app_commands.describe(
        channel=app_commands.locale_str(
            "El canal a bloquear (por defecto: canal actual)",
            key="slash.describes.lock.channel",
        )
    )
    @app_commands.default_permissions(moderate_members=True)
    @is_mod()
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Deny ``send_messages`` for @everyone in *channel*."""
        target_channel = channel or ctx.channel
        guild_id = self._guild_id(ctx)

        if ctx.guild is None:
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
        overwrite.send_messages = False

        try:
            await target_channel.set_permissions(  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel locked by {ctx.author}",
            )
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.lock.permission_denied_title"),
                    t(guild_id, "sentinel.lock.permission_denied_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                )
            )
            return
        except Exception:
            logger.exception("Unexpected error during lock")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.lock.failed_title"),
                    t(guild_id, "sentinel.lock.failed_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                )
            )
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Lock",
            ctx.author,
            ctx.author,
            t(guild_id, "sentinel.lock.audit_reason", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
        )

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.lock.success_title"),
                t(guild_id, "sentinel.lock.success_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
            )
        )

    @app_commands.command(
        name="unlock",
        description=app_commands.locale_str(
            "Desbloquear un canal (permitir send_messages para @everyone).",
            key="slash.descriptions.unlock",
        ),
    )
    @app_commands.describe(
        channel=app_commands.locale_str(
            "El canal a desbloquear (por defecto: canal actual)",
            key="slash.describes.unlock.channel",
        )
    )
    @app_commands.default_permissions(moderate_members=True)
    @is_mod()
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Allow ``send_messages`` for @everyone in *channel*."""
        target_channel = channel or ctx.channel
        guild_id = self._guild_id(ctx)

        if ctx.guild is None:
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
        overwrite.send_messages = None

        try:
            await target_channel.set_permissions(  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel unlocked by {ctx.author}",
            )
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.unlock.permission_denied_title"),
                    t(guild_id, "sentinel.unlock.permission_denied_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                )
            )
            return
        except Exception:
            logger.exception("Unexpected error during unlock")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.unlock.failed_title"),
                    t(guild_id, "sentinel.unlock.failed_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
                )
            )
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unlock",
            ctx.author,
            ctx.author,
            t(guild_id, "sentinel.unlock.audit_reason", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
        )

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.unlock.success_title"),
                t(guild_id, "sentinel.unlock.success_description", channel=target_channel.mention),  # noqa: E501  # guild-only: ctx.channel is TextChannel in guild context
            )
        )

    # ==================================================================
    # 5.6 — /modlogs
    # ==================================================================

    @app_commands.command(
        name="modlogs",
        description=app_commands.locale_str(
            "Ver historial de moderación de un miembro.",
            key="slash.descriptions.modlogs",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str("El miembro cuyo historial ver", key="slash.describes.modlogs.member"),
        type=app_commands.locale_str(
            "Filtrar por tipo de infracción (WARN, MUTE, KICK, BAN)",
            key="slash.describes.modlogs.type",
        ),
        after=app_commands.locale_str(
            "Mostrar solo infracciones después de esta fecha (ISO, ej. 2026-01-01)",
            key="slash.describes.modlogs.after",
        ),
    )
    @app_commands.default_permissions(moderate_members=True)
    @is_mod()
    async def modlogs(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        type: str | None = None,  # noqa: A002 -- discord slash param `type` is wire contract
        after: str | None = None,
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Display paginated moderation history for *member*."""
        guild_id = self._guild_id(ctx)
        target_id = str(member.id)

        if self.bot.infraction_service is None:
            msg = "InfractionService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            infractions = await self.bot.infraction_service.get_modlogs(
                guild_id,
                target_id,
                type_filter=type,
                after=after,
            )
        except Exception:
            logger.exception("InfractionService.get_modlogs() failed")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.modlogs.failed_title"),
                    t(guild_id, "sentinel.modlogs.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if not infractions:
            filters_active = bool(type or after)
            desc_key = (
                "sentinel.modlogs.no_modlogs_description_filtered"
                if filters_active
                else "sentinel.modlogs.no_modlogs_description"
            )
            await ctx.send(
                embed=info_embed(
                    t(guild_id, "sentinel.modlogs.no_modlogs_title"),
                    t(guild_id, desc_key, mention=member.mention),
                ),
                ephemeral=True,
            )
            return

        pages = _build_modlog_pages(member, infractions, guild_id=guild_id)

        if len(pages) == 1:
            await ctx.send(embed=pages[0], ephemeral=True)
        else:
            view = EmbedPaginator(pages, guild_id=guild_id, custom_id_prefix="modlogs:")
            await ctx.send(embed=pages[0], view=view, ephemeral=True)

    # ==================================================================
    # PR2 — /tempban + /unban (2.10-2.13)
    # ==================================================================

    @app_commands.command(
        name="tempban",
        description=app_commands.locale_str(
            "Prohibir temporalmente a un miembro.",
            key="slash.descriptions.tempban",
        ),
    )
    @app_commands.describe(
        member=app_commands.locale_str("El miembro a prohibir temporalmente", key="slash.describes.tempban.member"),
        duration=app_commands.locale_str(
            'Duración (ej. "24h", "7d"). Requerido.',
            key="slash.describes.tempban.duration",
        ),
        reason=app_commands.locale_str("Razón de la prohibición temporal", key="slash.describes.tempban.reason"),
    )
    @app_commands.default_permissions(ban_members=True)
    @can_check("moderation.ban")
    async def tempban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "",
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Tempban *member* for *duration* after confirmation."""
        if not await self._validate_target(ctx, member, "tempban"):
            return

        guild_id = self._guild_id(ctx)
        if not reason:
            reason = t(guild_id, "sentinel.default_reason")
        seconds = parse_duration_optional(duration)
        if seconds is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.tempban.invalid_duration_title"),
                    t(guild_id, "sentinel.tempban.invalid_duration_description", duration=duration),
                ),
                ephemeral=True,
            )
            return

        async def _do_tempban(interaction: discord.Interaction) -> None:
            # C11 (no-drift): compute expires_at exactly once at EXECUTION
            # time — after the moderator confirms — so the DB value and all
            # logs reflect the real ban start, not invocation + dialog latency.
            expires_at = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
            safe_reason = discord.utils.escape_markdown(reason)
            target_id = str(member.id)
            moderator_id = str(ctx.author.id)
            try:
                await member.ban(reason=reason)
            except discord.DiscordException as exc:
                await self._handle_mod_error(ctx, exc, "tempban", member)
                return
            if self.bot.infraction_service is None:
                msg = "InfractionService initialised in setup_hook"
                raise RuntimeError(msg)
            try:
                await self.bot.infraction_service.tempban(
                    guild_id, target_id, moderator_id, reason, expires_at=expires_at
                )
            except Exception:
                logger.exception("tempban infraction insert failed (non-fatal)")

            if self.bot.logging_service is None:
                msg = "LoggingService initialised in setup_hook"
                raise RuntimeError(msg)
            if not isinstance(ctx.author, discord.Member):
                msg = "ctx.author must be discord.Member"
                raise TypeError(msg)
            await self.bot.logging_service.log_moderation_action(guild_id, "Tempban", member, ctx.author, reason)
            # Ephemeral-standard: the confirmation dialog is ephemeral, but the
            # final action result MUST be permanent (visible to the channel).
            # Edit the ephemeral confirm to a closed notice, then send the
            # permanent action embed to the channel.
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=t(guild_id, "confirm.confirmed_title"),
                    description=t(
                        guild_id,
                        "confirm.tempban_confirmed_description",
                        mention=member.mention,
                    ),
                    color=INFO,
                ),
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await ctx.channel.send(
                embed=success_embed(
                    t(guild_id, "sentinel.tempban.success_title"),
                    t(guild_id, "sentinel.tempban.success_description", mention=member.mention, reason=safe_reason),
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        view = ConfirmCancelView(guild_id=guild_id, owner_id=ctx.author.id, on_confirm=_do_tempban)
        msg = await ctx.send(
            embed=discord.Embed(
                title=t(guild_id, "confirm.tempban_confirm_title"),
                description=t(
                    guild_id,
                    "confirm.tempban_confirm_description",
                    mention=member.mention,
                    duration=duration,
                    reason=discord.utils.escape_markdown(reason),
                ),
                color=INFO,
            ),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = msg

    @app_commands.command(
        name="unban",
        description=app_commands.locale_str(
            "Levantar la prohibición de un usuario.",
            key="slash.descriptions.unban",
        ),
    )
    @app_commands.describe(
        user_id=app_commands.locale_str("ID del usuario a desbanear", key="slash.describes.unban.user_id"),
    )
    @app_commands.default_permissions(ban_members=True)
    @can_check("moderation.ban")
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
    ) -> None:
        ctx = self._to_ctx(interaction)  # compat: Context or Interaction
        """Unban a user by ID (idempotent)."""
        guild_id = self._guild_id(ctx)
        if ctx.guild is None:
            return
        if self.bot.infraction_service is None:
            msg = "InfractionService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
            result = await self.bot.infraction_service.unban(guild_id, user_id)
        except Exception:
            logger.exception("InfractionService.unban() failed")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.unban.failed_title"),
                    t(guild_id, "sentinel.unban.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if result is None:
            await ctx.send(
                embed=info_embed(
                    t(guild_id, "sentinel.unban.no_ban_title"),
                    t(guild_id, "sentinel.unban.no_ban_description", user_id=user_id),
                ),
                ephemeral=True,
            )
            return

        # Lift Discord ban — typed value object (spec sentinel-commands):
        # UnbanTarget satisfies the Snowflake protocol structurally and
        # carries display metadata, so no framework object is ever patched.
        uid = int(user_id) if user_id.isdigit() else 0
        target = UnbanTarget(id=uid, name=user_id, mention=f"<@{user_id}>")
        try:
            await ctx.guild.unban(target, reason=f"Unbanned by {ctx.author}")
        except Exception:
            # Log but still confirm DB deactivation
            logger.exception("guild.unban failed for %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "sentinel.unban.failed_title"),
                    t(guild_id, "sentinel.unban.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if self.bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        if not isinstance(ctx.author, discord.Member):
            msg = "ctx.author must be discord.Member"
            raise TypeError(msg)
        # Log with the same typed target — mention/name come from UnbanTarget.
        try:
            await self.bot.logging_service.log_moderation_action(
                guild_id,
                "Unban",
                target,
                ctx.author,
                t(guild_id, "sentinel.unban.audit_reason", user_id=user_id),
            )
        except Exception:
            logger.exception("log_moderation_action failed for unban (non-fatal)")

        await ctx.send(
            embed=success_embed(
                t(guild_id, "sentinel.unban.success_title"),
                t(guild_id, "sentinel.unban.success_description", user_id=user_id),
            ),
        )


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register SentinelCog with the bot."""
    await bot.add_cog(SentinelCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove SentinelCog from the bot."""
    await bot.remove_cog("Sentinel")


# ======================================================================
# Modlogs page builder (internal)
# ======================================================================


def _build_modlog_pages(
    member: discord.Member,
    infractions: list[Any],
    guild_id: str = "",
) -> list[discord.Embed]:
    """Build paginated embeds for /modlogs output.

    Each page shows up to ``MODLOGS_PER_PAGE`` infractions with type,
    moderator, reason, and date.
    """
    pages: list[discord.Embed] = []
    total = len(infractions)
    total_pages = (total + MODLOGS_PER_PAGE - 1) // MODLOGS_PER_PAGE

    for i in range(0, total, MODLOGS_PER_PAGE):
        chunk = infractions[i : i + MODLOGS_PER_PAGE]
        page_num = (i // MODLOGS_PER_PAGE) + 1

        description = t(guild_id, "sentinel.modlogs.page_infractions", total=total)
        if total_pages > 1:
            description += t(guild_id, "sentinel.modlogs.page_info", page=page_num, total_pages=total_pages)

        embed = discord.Embed(
            title=t(guild_id, "sentinel.modlogs.title", name=member.display_name),
            description=description,
            color=INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for inf in chunk:
            type_emoji = _type_emoji(inf.type)
            created = (
                inf.created_at.strftime("%Y-%m-%d %H:%M UTC")
                if inf.created_at
                else t(guild_id, "sentinel.modlogs.unknown_date")
            )
            value = t(
                guild_id,
                "sentinel.modlogs.field_value",
                moderator=inf.moderator_id,
                reason=inf.reason,
                date=created,
            )
            if not inf.active:
                value += t(guild_id, "sentinel.modlogs.revoked")

            embed.add_field(
                name=f"{type_emoji} {inf.type}",
                value=value,
                inline=False,
            )

        embed.set_footer(
            text=t(guild_id, "sentinel.modlogs.footer", id=member.id),
            icon_url=member.display_avatar.url,
        )
        pages.append(embed)

    return pages


def _type_emoji(infraction_type: str) -> str:
    """Return an emoji for an infraction type."""
    return {
        "WARN": "⚠️",
        "MUTE": "🔇",
        "KICK": "👢",
        "BAN": "🔨",
    }.get(infraction_type, "📌")
