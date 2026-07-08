"""SetupCog — guild configuration via /setup hybrid command.

Provides the ``/setup`` command gated by ``@is_admin()`` that lets guild
administrators configure ``ticket_category_id``, ``mod_role_id``,
``log_channel_id``, and ``language`` without leaving Discord.

Design: ``openspec/changes/ticket-category-id-null/design.md``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.checks import is_admin
from bot.utils.embeds import error_embed, success_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class SetupCog(commands.Cog, name="Setup"):
    """Guild configuration commands."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    @commands.hybrid_command(
        name="setup",
        description="Configure guild settings (ticket category, mod role, log channel, language)",
    )
    @commands.has_permissions(administrator=True)
    @is_admin()
    async def setup_command(
        self,
        ctx: commands.Context,
        ticket_category: discord.CategoryChannel,
        mod_role: discord.Role | None = None,
        log_channel: discord.TextChannel | None = None,
        language: Literal["es", "en"] | None = None,
    ) -> None:
        """Configure guild settings.

        Args:
            ctx: Command context.
            ticket_category: Required Discord category channel for tickets.
            mod_role: Optional moderator role.
            log_channel: Optional logging channel.
            language: Optional guild language (es or en).
        """
        if ctx.guild is None:
            await ctx.send(
                embed=error_embed(
                    t(None, "setup.error_title"),
                    t(None, "setup.error_guild_only"),
                ),
            )
            return

        guild_id = str(ctx.guild.id)
        assert self.bot.guild_service is not None

        try:
            config = await self.bot.guild_service.get_config(guild_id)
        except Exception:
            logger.exception("Failed to fetch guild config for setup (guild=%s)", guild_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "setup.error_title"),
                    t(guild_id, "setup.error_config_load"),
                ),
            )
            return

        # Merge: required param always set; optional params only if provided.
        config.ticket_category_id = str(ticket_category.id)
        if mod_role is not None:
            config.mod_role_id = str(mod_role.id)
        if log_channel is not None:
            config.log_channel_id = str(log_channel.id)
        if language is not None:
            config.language = language

        try:
            await self.bot.guild_service.save_config(config)
        except Exception:
            logger.exception("Failed to save guild config (guild=%s)", guild_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "setup.error_title"),
                    t(guild_id, "setup.error_save"),
                ),
            )
            return

        # Success response — ephemeral for slash, channel for prefix.
        ephemeral = ctx.interaction is not None
        embed = success_embed(
            t(guild_id, "setup.success_title"),
            t(guild_id, "setup.success_description"),
            guild_id=guild_id,
        )
        await ctx.send(embed=embed, ephemeral=ephemeral)

        logger.info(
            "Guild %s configured via /setup: category=%s mod=%s log=%s lang=%s",
            guild_id,
            ticket_category.id,
            mod_role.id if mod_role else None,
            log_channel.id if log_channel else None,
            language,
        )


async def setup(bot: NebulosaBot) -> None:
    """Register SetupCog with the bot."""
    await bot.add_cog(SetupCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove SetupCog from the bot."""
    await bot.remove_cog("Setup")
