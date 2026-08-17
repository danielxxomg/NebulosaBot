"""AuditListener — passive event listeners for audit logging.

Listens to 7 Discord gateway events and routes them to
:class:`~bot.services.logging_service.LoggingService` for embed
generation and delivery.  Early exits for bot messages and DMs
keep the listener cheap; all config-based guards (enabled/disabled,
channel visibility, role-diff no-ops) are handled inside the service.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class AuditListener(commands.Cog):
    """Passive listeners for audit-logging 7 event types.

    Early exits (bot, DM, non-loggable channel) happen here before
    delegating to :class:`LoggingService`.  The service owns the
    remaining guards: ``log_enabled``, ``log_channel_id``,
    ``can_log_in_channel``, and role-diff detection.
    """

    __slots__ = ("_logging", "bot")

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot
        assert bot.logging_service is not None, "LoggingService initialised in setup_hook"
        self._logging = bot.logging_service

    # ------------------------------------------------------------------
    # Message events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        """Log edited messages — skip bots, DMs, and invisible channels."""
        if before.author.bot:
            return
        if before.guild is None:
            return
        if not isinstance(before.channel, discord.abc.GuildChannel):
            return
        if not self._logging.can_log_in_channel(before.channel):
            return

        guild_id = str(before.guild.id)
        await self._logging.log_message_edit(guild_id, before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Log deleted messages — skip bots and DMs."""
        if message.author.bot:
            return
        if message.guild is None:
            return

        guild_id = str(message.guild.id)
        await self._logging.log_message_delete(guild_id, message)

    # ------------------------------------------------------------------
    # Member events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        """Log member updates — role-diff handled by LoggingService."""
        if before.guild is None:
            return

        guild_id = str(before.guild.id)
        await self._logging.log_member_update(guild_id, before, after)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log member joins — skip bots."""
        if member.bot:
            return
        if member.guild is None:
            return

        guild_id = str(member.guild.id)
        await self._logging.log_member_join(guild_id, member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log member leaves — skip bots."""
        if member.bot:
            return
        if member.guild is None:
            return

        guild_id = str(member.guild.id)
        await self._logging.log_member_leave(guild_id, member)

    # ------------------------------------------------------------------
    # Channel events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log channel creation events."""
        if channel.guild is None:
            return

        guild_id = str(channel.guild.id)
        await self._logging.log_channel_create(guild_id, channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Log channel deletion and route active-ticket detection to the coordinator.

        Preserves deletion logging and hands the exact (guild, channel) facts
        to ``TicketService.handle_channel_delete`` so the shared, evidence-gated
        repair path can detect a matching active ticket. The listener NEVER
        mutates ticket state and NEVER fabricates an authorizing actor — the
        gateway event carries no audit-log actor, so the coordinator treats
        the deletion actor as informational only. A missing ticket_service is
        tolerated (deletion logging continues, no repair is attempted).
        """
        if channel.guild is None:
            return

        guild_id = str(channel.guild.id)
        await self._logging.log_channel_delete(guild_id, channel)

        ticket_service = getattr(self.bot, "ticket_service", None)
        if ticket_service is None:
            return
        handler = getattr(ticket_service, "handle_channel_delete", None)
        if handler is None:
            return
        # Resolve live G.2 preflight (read-only) and forward resolved evidence
        # through the real listener so resolved repair is reachable.
        preflight = None
        live_preflight_fn = getattr(self.bot, "live_preflight", None)
        if callable(live_preflight_fn):
            try:
                preflight = live_preflight_fn()
            except Exception:
                logger.exception("Failed to resolve live preflight for channel_delete")
                preflight = None
        else:
            # Fallback: try evaluate_live_preflight from bot if available
            evaluator = getattr(ticket_service, "_live_preflight_evaluator", None)
            if callable(evaluator):
                try:
                    preflight = evaluator()
                except Exception:
                    logger.exception("Failed to evaluate live preflight for channel_delete")
        await handler(guild_id, str(channel.id), preflight=preflight)


# ------------------------------------------------------------------
# cog load / unload (discord.py v2.x requirement)
# ------------------------------------------------------------------


async def setup(bot: NebulosaBot) -> None:
    """Register AuditListener with the bot."""
    await bot.add_cog(AuditListener(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove AuditListener from the bot."""
    await bot.remove_cog("AuditListener")
