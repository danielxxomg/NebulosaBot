"""SentinelCog — moderation commands for NebulosaBot.

Provides 9 hybrid moderation commands: warn, unwarn, mute, unmute, kick,
ban, lock, unlock, and modlogs.  All commands are permission-gated via
``@is_mod()`` or ``@is_admin()`` and log actions to the configured
mod-log channel when enabled.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.checks import is_admin, is_mod
from bot.utils.embeds import (
    COLOR_INFO,
    error_embed,
    info_embed,
    success_embed,
)
from bot.utils.time import parse_duration

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

MODLOGS_PER_PAGE = 5


# ======================================================================
# Modlogs Paginator
# ======================================================================


class _ModlogsPaginator(discord.ui.View):
    """Two-button paginator for /modlogs embeds.

    Shows prev/next buttons that cycle through a list of pre-built
    :class:`discord.Embed` pages.
    """

    __slots__ = ("_current", "_pages")

    def __init__(self, pages: list[discord.Embed]) -> None:
        super().__init__(timeout=120)
        self._pages = pages
        self._current = 0
        self._update_buttons()

    # -- button callbacks ----------------------------------------------

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._current = max(0, self._current - 1)
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self._pages[self._current],
            view=self,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._current = min(len(self._pages) - 1, self._current + 1)
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self._pages[self._current],
            view=self,
        )

    # -- helpers -------------------------------------------------------

    def _update_buttons(self) -> None:
        """Disable prev/next at boundaries."""
        children = list(self.children)
        if len(children) >= 2:
            children[0].disabled = self._current == 0
            children[1].disabled = self._current == len(self._pages) - 1


# ======================================================================
# SentinelCog
# ======================================================================


class SentinelCog(commands.Cog, name="Sentinel"):
    """Moderation commands with auto-escalation and audit logging."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _guild_id(ctx: commands.Context) -> str:
        """Return the guild ID as a string for the current context."""
        assert ctx.guild is not None, "Guild-only command"
        return str(ctx.guild.id)

    async def _validate_target(
        self,
        ctx: commands.Context,
        target: discord.Member,
        action: str,
    ) -> bool:
        """Validate that *target* is a legal moderation target.

        Returns ``True`` if the target passes all guards.  Sends an
        appropriate error embed to *ctx* and returns ``False`` when
        a guard fails.
        """
        assert self.bot.user is not None, "Bot user available after on_ready"
        assert self.bot.user is not None, "Bot user available after on_ready"
        if target.id == self.bot.user.id:
            await ctx.send(embed=error_embed("Invalid Target", "I cannot moderate myself."))
            return False

        if target.id == ctx.author.id:
            await ctx.send(embed=error_embed("Invalid Target", f"You cannot {action} yourself."))
            return False

        # Role hierarchy: the bot's top role must be above the target's.
        if ctx.guild is not None and ctx.guild.me is not None and ctx.guild.me.top_role <= target.top_role and target != ctx.guild.owner:
            await ctx.send(
                embed=error_embed(
                    "Role Hierarchy",
                    f"I cannot {action} {target.mention} — their highest role is above or equal to mine.",
                )
            )
            return False

        return True

    async def _handle_mod_error(
        self,
        ctx: commands.Context,
        error: Exception,
        action: str,
        target: discord.Member,
    ) -> None:
        """Map common moderation exceptions to user-friendly embeds."""
        if isinstance(error, discord.Forbidden):
            await ctx.send(
                embed=error_embed(
                    "Permission Denied",
                    f"I don't have permission to {action} {target.mention}. "
                    "Check my role position and server permissions.",
                )
            )
        elif isinstance(error, discord.HTTPException):
            logger.exception("HTTP error during %s on %s", action, target.id)
            await ctx.send(
                embed=error_embed(
                    "Action Failed",
                    f"Failed to {action} {target.mention}. Discord returned an error.",
                )
            )
        else:
            logger.exception("Unexpected error during %s on %s", action, target.id)
            await ctx.send(
                embed=error_embed(
                    "Unexpected Error",
                    f"An unexpected error occurred while trying to {action} {target.mention}.",
                )
            )

    # ==================================================================
    # 5.2 — /warn + /unwarn
    # ==================================================================

    @commands.hybrid_command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @is_mod()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str) -> None:
        """Issue a warning and check for auto-escalation."""
        if not await self._validate_target(ctx, member, "warn"):
            return

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        try:
            assert self.bot.infraction_service is not None, "InfractionService initialised in setup_hook"
            infraction, escalation = await self.bot.infraction_service.warn(
                guild_id,
                target_id,
                moderator_id,
                reason,
            )
        except Exception:
            logger.exception("InfractionService.warn() failed")
            await ctx.send(
                embed=error_embed(
                    "Warn Failed",
                    "Could not record the warning. Please try again.",
                )
            )
            return

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Warn",
            member,
            ctx.author,
            reason,
        )

        # Report escalation if triggered.
        escalation_msg = ""
        if escalation is not None:
            if escalation.action == "MUTE":
                try:
                    await member.timeout(
                        timedelta(seconds=escalation.duration),
                        reason=f"Auto-escalation: {escalation.threshold} warnings",
                    )
                    assert self.bot.db is not None, "Database initialised in setup_hook"
                    await self.bot.db.insert_infraction(
                        guild_id=guild_id,
                        target_id=target_id,
                        moderator_id=moderator_id,
                        type="MUTE",
                        reason=(f"Auto-escalation after {escalation.threshold} warnings"),
                    )
                    assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
                    await self.bot.logging_service.log_moderation_action(
                        guild_id,
                        "Mute (Auto-escalation)",
                        member,
                        ctx.author,
                        f"{escalation.threshold} warnings reached",
                    )
                    escalation_msg = (
                        f"\n⚠️ {member.mention} has been **automatically muted** "
                        f"for 1 hour ({escalation.threshold} warnings)."
                    )
                except discord.Forbidden:
                    escalation_msg = f"\n⚠️ Auto-mute failed — I lack permission to timeout {member.mention}."
            elif escalation.action == "KICK":
                try:
                    await member.kick(
                        reason=(f"Auto-escalation: {escalation.threshold} warnings"),
                    )
                    assert self.bot.db is not None, "Database initialised in setup_hook"
                    await self.bot.db.insert_infraction(
                        guild_id=guild_id,
                        target_id=target_id,
                        moderator_id=moderator_id,
                        type="KICK",
                        reason=(f"Auto-escalation after {escalation.threshold} warnings"),
                    )
                    assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
                    await self.bot.logging_service.log_moderation_action(
                        guild_id,
                        "Kick (Auto-escalation)",
                        member,
                        ctx.author,
                        f"{escalation.threshold} warnings reached",
                    )
                    escalation_msg = (
                        f"\n🚫 {member.mention} has been **automatically kicked** ({escalation.threshold} warnings)."
                    )
                except discord.Forbidden:
                    escalation_msg = f"\n⚠️ Auto-kick failed — I lack permission to kick {member.mention}."

        await ctx.send(
            embed=success_embed(
                "Member Warned",
                f"{member.mention} has been warned.\n**Reason:** {reason}{escalation_msg}",
            )
        )

    @commands.hybrid_command(name="unwarn", description="Remove the most recent warning from a member")
    @app_commands.describe(member="The member to unwarn")
    @is_mod()
    async def unwarn(self, ctx: commands.Context, member: discord.Member) -> None:
        """Deactivate the most recent active warning."""
        if not await self._validate_target(ctx, member, "unwarn"):
            return

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)

        try:
            assert self.bot.infraction_service is not None, "InfractionService initialised in setup_hook"
            result = await self.bot.infraction_service.unwarn(guild_id, target_id)
        except Exception:
            logger.exception("InfractionService.unwarn() failed")
            await ctx.send(
                embed=error_embed(
                    "Unwarn Failed",
                    "Could not remove the warning. Please try again.",
                )
            )
            return

        if result is None:
            await ctx.send(
                embed=info_embed(
                    "No Warnings",
                    f"{member.mention} has no active warnings to remove.",
                )
            )
            return

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unwarn",
            member,
            ctx.author,
            f"Revoked warning (ID: {result.id})",
        )
        await ctx.send(
            embed=success_embed(
                "Warning Revoked",
                f"Removed the most recent warning from {member.mention}.",
            )
        )

    # ==================================================================
    # 5.3 — /mute + /unmute
    # ==================================================================

    @commands.hybrid_command(name="mute", description="Timeout a member")
    @app_commands.describe(
        member="The member to mute",
        duration='Duration (e.g. "1h", "30m", "1h30m"). Default: 1h',
        reason="Reason for the mute",
    )
    @is_mod()
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str = "1h",
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Apply a timeout to *member*."""
        if not await self._validate_target(ctx, member, "mute"):
            return

        duration_seconds = parse_duration(duration)
        guild_id = self._guild_id(ctx)
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        try:
            await member.timeout(
                timedelta(seconds=duration_seconds),
                reason=reason,
            )
        except Exception as exc:
            await self._handle_mod_error(ctx, exc, "mute", member)
            return

        # Create MUTE infraction for audit trail.
        try:
            assert self.bot.db is not None, "Database initialised in setup_hook"
            await self.bot.db.insert_infraction(
                guild_id=guild_id,
                target_id=target_id,
                moderator_id=moderator_id,
                type="MUTE",
                reason=reason,
            )
        except Exception:
            logger.exception("Failed to insert MUTE infraction (non-fatal)")

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Mute",
            member,
            ctx.author,
            reason,
        )

        await ctx.send(
            embed=success_embed(
                "Member Muted",
                f"{member.mention} has been muted for **{duration}**.\n**Reason:** {reason}",
            )
        )

    @commands.hybrid_command(name="unmute", description="Remove a member's timeout")
    @app_commands.describe(member="The member to unmute")
    @is_mod()
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        """Remove the timeout from *member*."""
        if not await self._validate_target(ctx, member, "unmute"):
            return

        guild_id = self._guild_id(ctx)

        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
        except Exception as exc:
            await self._handle_mod_error(ctx, exc, "unmute", member)
            return

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unmute",
            member,
            ctx.author,
            "Timeout removed",
        )

        await ctx.send(
            embed=success_embed(
                "Member Unmuted",
                f"{member.mention}'s timeout has been removed.",
            )
        )

    # ==================================================================
    # 5.4 — /kick + /ban
    # ==================================================================

    @commands.hybrid_command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @is_mod()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str) -> None:
        """Kick *member* from the guild."""
        if not await self._validate_target(ctx, member, "kick"):
            return

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        try:
            await member.kick(reason=reason)
        except Exception as exc:
            await self._handle_mod_error(ctx, exc, "kick", member)
            return

        # Create KICK infraction for audit trail.
        try:
            assert self.bot.db is not None, "Database initialised in setup_hook"
            await self.bot.db.insert_infraction(
                guild_id=guild_id,
                target_id=target_id,
                moderator_id=moderator_id,
                type="KICK",
                reason=reason,
            )
        except Exception:
            logger.exception("Failed to insert KICK infraction (non-fatal)")

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Kick",
            member,
            ctx.author,
            reason,
        )

        await ctx.send(
            embed=success_embed(
                "Member Kicked",
                f"{member.mention} has been kicked.\n**Reason:** {reason}",
            )
        )

    @commands.hybrid_command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_days="Days of messages to delete (0-7, default: 0)",
    )
    @is_admin()
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str,
        delete_days: int = 0,
    ) -> None:
        """Ban *member* from the guild.  Requires Administrator permission."""
        if not await self._validate_target(ctx, member, "ban"):
            return

        # Clamp delete_days to [0, 7].
        delete_days = max(0, min(7, delete_days))

        guild_id = self._guild_id(ctx)
        target_id = str(member.id)
        moderator_id = str(ctx.author.id)

        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
        except Exception as exc:
            await self._handle_mod_error(ctx, exc, "ban", member)
            return

        # Create BAN infraction for audit trail.
        try:
            assert self.bot.db is not None, "Database initialised in setup_hook"
            await self.bot.db.insert_infraction(
                guild_id=guild_id,
                target_id=target_id,
                moderator_id=moderator_id,
                type="BAN",
                reason=reason,
            )
        except Exception:
            logger.exception("Failed to insert BAN infraction (non-fatal)")

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Ban",
            member,
            ctx.author,
            reason,
        )

        await ctx.send(
            embed=success_embed(
                "Member Banned",
                f"{member.mention} has been banned.\n**Reason:** {reason}",
            )
        )

    # ==================================================================
    # 5.5 — /lock + /unlock
    # ==================================================================

    @commands.hybrid_command(
        name="lock",
        description="Lock a channel (deny send_messages for @everyone)",
    )
    @app_commands.describe(channel="The channel to lock (default: current channel)")
    @is_mod()
    async def lock(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Deny ``send_messages`` for @everyone in *channel*."""
        target_channel = channel or ctx.channel
        guild_id = self._guild_id(ctx)

        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send(embed=error_embed("Invalid Channel", "Lock only works on text channels."))
            return

        assert ctx.guild is not None, "Guild-only command"
        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False  # type: ignore[misc]  # discord.py stub limitation: PermissionOverwrite dynamic __slots__

        try:
            await target_channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel locked by {ctx.author}",
            )
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    "Permission Denied",
                    f"I don't have permission to lock {target_channel.mention}. Check my role permissions.",
                )
            )
            return
        except Exception:
            logger.exception("Unexpected error during lock")
            await ctx.send(
                embed=error_embed(
                    "Lock Failed",
                    f"Could not lock {target_channel.mention}.",
                )
            )
            return

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Lock",
            ctx.author,
            ctx.author,
            f"Locked {target_channel.mention}",
        )

        await ctx.send(
            embed=success_embed(
                "Channel Locked",
                f"{target_channel.mention} has been locked. @everyone can no longer send messages.",
            )
        )

    @commands.hybrid_command(
        name="unlock",
        description="Unlock a channel (allow send_messages for @everyone)",
    )
    @app_commands.describe(channel="The channel to unlock (default: current channel)")
    @is_mod()
    async def unlock(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Allow ``send_messages`` for @everyone in *channel*."""
        target_channel = channel or ctx.channel
        guild_id = self._guild_id(ctx)

        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send(embed=error_embed("Invalid Channel", "Unlock only works on text channels."))
            return

        assert ctx.guild is not None, "Guild-only command"
        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # type: ignore[misc]  # discord.py stub limitation: PermissionOverwrite dynamic __slots__

        try:
            await target_channel.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Channel unlocked by {ctx.author}",
            )
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    "Permission Denied",
                    f"I don't have permission to unlock {target_channel.mention}. Check my role permissions.",
                )
            )
            return
        except Exception:
            logger.exception("Unexpected error during unlock")
            await ctx.send(
                embed=error_embed(
                    "Unlock Failed",
                    f"Could not unlock {target_channel.mention}.",
                )
            )
            return

        assert self.bot.logging_service is not None, "LoggingService initialised in setup_hook"
        await self.bot.logging_service.log_moderation_action(
            guild_id,
            "Unlock",
            ctx.author,
            ctx.author,
            f"Unlocked {target_channel.mention}",
        )

        await ctx.send(
            embed=success_embed(
                "Channel Unlocked",
                f"{target_channel.mention} has been unlocked. @everyone can send messages again.",
            )
        )

    # ==================================================================
    # 5.6 — /modlogs
    # ==================================================================

    @commands.hybrid_command(name="modlogs", description="View moderation history for a member")
    @app_commands.describe(
        member="The member whose modlogs to view",
        type="Filter by infraction type (WARN, MUTE, KICK, BAN)",
        after="Show only infractions after this date (ISO, e.g. 2026-01-01)",
    )
    @is_mod()
    async def modlogs(
        self,
        ctx: commands.Context,
        member: discord.Member,
        type: str | None = None,
        after: str | None = None,
    ) -> None:
        """Display paginated moderation history for *member*."""
        guild_id = self._guild_id(ctx)
        target_id = str(member.id)

        try:
            assert self.bot.infraction_service is not None, "InfractionService initialised in setup_hook"
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
                    "Modlogs Failed",
                    "Could not retrieve moderation history. Please try again.",
                )
            )
            return

        if not infractions:
            await ctx.send(
                embed=info_embed(
                    "No Modlogs",
                    f"{member.mention} has no moderation history{' matching the filters' if type or after else ''}.",
                )
            )
            return

        pages = _build_modlog_pages(member, infractions)

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            view = _ModlogsPaginator(pages)
            await ctx.send(embed=pages[0], view=view)


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
    infractions: list,
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

        description = f"{total} infraction(s) total"
        if total_pages > 1:
            description += f" — page {page_num}/{total_pages}"

        embed = discord.Embed(
            title=f"📋 Modlogs for {member.display_name}",
            description=description,
            color=COLOR_INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for inf in chunk:
            type_emoji = _type_emoji(inf.type)
            created = inf.created_at.strftime("%Y-%m-%d %H:%M UTC") if inf.created_at else "Unknown"
            value = f"**Moderator:** <@{inf.moderator_id}>\n**Reason:** {inf.reason}\n**Date:** {created}"
            if not inf.active:
                value += "\n*(Revoked)*"

            embed.add_field(
                name=f"{type_emoji} {inf.type}",
                value=value,
                inline=False,
            )

        embed.set_footer(
            text=f"NebulosaBot • Sentinel • {member.id}",
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
