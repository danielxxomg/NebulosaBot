"""GreetingsCog — welcome/goodbye card dispatching.

Listens for member join/leave events and delegates to
:class:`~bot.services.greeting_service.GreetingService` for card generation
and delivery.  Provides admin-only test commands to preview cards.

NOTE: Slash command descriptions are Discord UI metadata, not runtime responses.
They remain in English; t() localizes runtime responses only.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class GreetingsCog(commands.Cog, name="Greetings"):
    """Welcome and goodbye card dispatching.

    Events:
        ``on_member_join``: delegates to ``GreetingService.dispatch_welcome()``.
        ``on_member_remove``: delegates to ``GreetingService.dispatch_goodbye()``.

    Commands (admin-only):
        ``/welcome_test``: generate and send a sample welcome card.
        ``/goodbye_test``: generate and send a sample goodbye card.
    """

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Dispatch a welcome card when a member joins."""
        if member.bot:
            return
        try:
            assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
            await self.bot.greeting_service.dispatch_welcome(member)
        except Exception:
            logger.exception(
                "on_member_join dispatch_welcome failed for %s in guild %s",
                member.name,
                member.guild.id,
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Dispatch a goodbye card when a member leaves."""
        if member.bot:
            return
        try:
            assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
            await self.bot.greeting_service.dispatch_goodbye(member)
        except Exception:
            logger.exception(
                "on_member_remove dispatch_goodbye failed for %s in guild %s",
                member.name,
                member.guild.id,
            )

    # ------------------------------------------------------------------
    # /welcome_test
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="welcome_test",
        description="Send a test welcome card in this channel (admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_test(self, ctx: commands.Context) -> None:  # type: ignore[override]
        """Generate and send a sample welcome card."""
        if not isinstance(ctx.author, discord.Member) or not ctx.author.guild_permissions.administrator:
            guild_id = str(ctx.guild.id) if ctx.guild else ""
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "greetings.permission_denied_title"),
                    t(guild_id, "greetings.permission_denied_description"),
                ),
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            avatar_url = _resolve_avatar_url(ctx.author)
            assert self.bot.image_service is not None, "ImageService initialised in setup_hook"
            buffer: io.BytesIO = await asyncio.to_thread(
                self.bot.image_service.generate_greeting_card,
                username=ctx.author.display_name,
                avatar_url=avatar_url,
                guild_name=ctx.guild.name if ctx.guild else "Unknown",
                member_count=ctx.guild.member_count if ctx.guild else 0,
                card_type="welcome",
            )
        except Exception:
            logger.exception("Failed to generate welcome test card")
            guild_id = str(ctx.guild.id) if ctx.guild else ""
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "greetings.welcome_test.failed_title"),
                    t(guild_id, "greetings.welcome_test.failed_description"),
                ),
                ephemeral=True,
            )
            return

        file = discord.File(buffer, filename="welcome.png")
        await ctx.send(file=file, ephemeral=True)

    # ------------------------------------------------------------------
    # /goodbye_test
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="goodbye_test",
        description="Send a test goodbye card in this channel (admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye_test(self, ctx: commands.Context) -> None:  # type: ignore[override]
        """Generate and send a sample goodbye card."""
        if not isinstance(ctx.author, discord.Member) or not ctx.author.guild_permissions.administrator:
            guild_id = str(ctx.guild.id) if ctx.guild else ""
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "greetings.permission_denied_title"),
                    t(guild_id, "greetings.permission_denied_description"),
                ),
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            avatar_url = _resolve_avatar_url(ctx.author)
            assert self.bot.image_service is not None, "ImageService initialised in setup_hook"
            buffer: io.BytesIO = await asyncio.to_thread(
                self.bot.image_service.generate_greeting_card,
                username=ctx.author.display_name,
                avatar_url=avatar_url,
                guild_name=ctx.guild.name if ctx.guild else "Unknown",
                member_count=ctx.guild.member_count if ctx.guild else 0,
                card_type="goodbye",
            )
        except Exception:
            logger.exception("Failed to generate goodbye test card")
            guild_id = str(ctx.guild.id) if ctx.guild else ""
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "greetings.goodbye_test.failed_title"),
                    t(guild_id, "greetings.goodbye_test.failed_description"),
                ),
                ephemeral=True,
            )
            return

        file = discord.File(buffer, filename="goodbye.png")
        await ctx.send(file=file, ephemeral=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _resolve_avatar_url(member: discord.Member | discord.User) -> str | None:
    """Return the display avatar URL for *member*, or ``None`` on failure."""
    try:
        return str(member.display_avatar.url)
    except Exception:
        logger.debug("Could not resolve avatar URL for user %s", member.id, exc_info=True)
        return None


async def setup(bot: NebulosaBot) -> None:
    """Load the GreetingsCog into the bot."""
    await bot.add_cog(GreetingsCog(bot))
