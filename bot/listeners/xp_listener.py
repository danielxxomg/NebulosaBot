"""XPListener — awards XP on message, detects level-ups, sends embeds.

Uses ``economy_service.gain_xp()`` for cooldown enforcement (DB-backed).
On level-up, auto-assigns roles from ``levelRoleMap`` and sends an embed
to the configured channel (or the message channel as fallback).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.utils.embeds import COLOR_INFO

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class XPListener(commands.Cog):
    """Awards XP on every valid (non-bot, guild) message.

    Cooldown is enforced by :meth:`~bot.services.economy_service.EconomyService.gain_xp`
    using the DB ``lastXpGain`` timestamp.

    Level-up notifications respect ``levelUpChannelId`` (or fallback to
    the current channel) and auto-assign roles from ``levelRoleMap``.
    """

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle an incoming message: award XP if eligible."""
        # Guard: bots, system/webhook messages, and DMs.
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        # Delegate to EconomyService — handles cooldown via DB timestamp.
        new_xp, new_level, leveled_up = await self.bot.economy_service.gain_xp(
            guild_id, user_id
        )

        # No XP awarded (cooldown or zero config).
        if new_xp == 0 and not leveled_up:
            return

        # Level-up: notify and assign roles.
        if leveled_up:
            await self._handle_level_up(message, guild_id, new_level)

    # ------------------------------------------------------------------
    # Level-up helpers
    # ------------------------------------------------------------------

    async def _handle_level_up(
        self, message: discord.Message, guild_id: str, new_level: int
    ) -> None:
        """Send level-up embed and auto-assign roles for *new_level*.

        Fetches economy config ONCE and passes it to both sub-helpers.
        """
        config = await self.bot.economy_service.get_economy_config(guild_id)

        await self._send_level_up_embed(message, new_level, config)
        await self._assign_level_role(message, new_level, config)

    async def _send_level_up_embed(
        self,
        message: discord.Message,
        new_level: int,
        config: dict | None,
    ) -> None:
        """Send a level-up notification to the appropriate channel."""
        guild = message.guild
        assert guild is not None  # Guarded earlier.

        # Determine target channel from config, or fallback to message channel.
        target_channel: discord.abc.Messageable = message.channel
        if config:
            channel_id = config.get("levelUpChannelId")
            if channel_id:
                resolved = guild.get_channel(int(channel_id))
                if resolved is not None:
                    target_channel = resolved

        embed = discord.Embed(
            title="Level Up! 🎉",
            description=f"{message.author.mention} has reached **Level {new_level}**!",
            color=COLOR_INFO,
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)

        try:
            await target_channel.send(embed=embed)
        except discord.HTTPException:
            logger.exception(
                "Failed to send level-up embed for user %s in guild %s",
                message.author.id, guild.id,
            )

    async def _assign_level_role(
        self,
        message: discord.Message,
        new_level: int,
        config: dict | None,
    ) -> None:
        """Assign the role mapped to *new_level* from economy_config if present."""
        if config is None:
            return

        level_roles: dict = config.get("levelRoles", {})
        if not level_roles:
            return

        role_id_str = level_roles.get(str(new_level))
        if role_id_str is None:
            return

        guild = message.guild
        assert guild is not None

        try:
            role_id = int(role_id_str)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid role ID %r in levelRoleMap for guild %s",
                role_id_str, guild.id,
            )
            return

        role = guild.get_role(role_id)
        if role is None:
            logger.debug(
                "Role %s not found in guild %s for level %d",
                role_id_str, guild.id, new_level,
            )
            return

        if not isinstance(message.author, discord.Member):
            return  # Can't assign roles to non-members.

        try:
            await message.author.add_roles(role)
            logger.info(
                "Assigned role %s to %s (level %d) in guild %s",
                role.name, message.author, new_level, guild.id,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to assign role %s to %s in guild %s",
                role.name, message.author, guild.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Failed to assign role %s to %s in guild %s",
                role.name, message.author, guild.id,
            )


# ----------------------------------------------------------------------
# cog load / unload (discord.py v2.x requirement)
# ----------------------------------------------------------------------


async def setup(bot: NebulosaBot) -> None:
    """Register XPListener with the bot."""
    await bot.add_cog(XPListener(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove XPListener from the bot."""
    await bot.remove_cog("XPListener")
