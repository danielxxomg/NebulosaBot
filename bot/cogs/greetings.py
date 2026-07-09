"""GreetingsCog — welcome/goodbye card dispatching and configuration.

Listens for member join/leave events and delegates to
:class:`~bot.services.greeting_service.GreetingService` for card generation
and delivery.  Provides admin-only test commands to preview cards and
configuration commands to manage welcome/goodbye settings.

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
from bot.models.greeting_config import GreetingConfig
from bot.services.greeting_service import _resolve_avatar_url
from bot.utils.embeds import error_embed, info_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

_NOT_CONFIGURED = "Not configured"


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
    # Admin guard + embed builder
    # ------------------------------------------------------------------

    async def _admin_guard(self, ctx: commands.Context) -> bool:
        """Check admin permission and send error if denied. Returns True if OK."""
        if not isinstance(ctx.author, discord.Member) or not ctx.author.guild_permissions.administrator:
            guild_id = str(ctx.guild.id) if ctx.guild else ""
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "greetings.permission_denied_title"),
                    t(guild_id, "greetings.permission_denied_description"),
                ),
                ephemeral=True,
            )
            return False
        return True

    def _config_embed(
        self,
        guild_id: str,
        config: GreetingConfig,
        kind: str,
    ) -> discord.Embed:
        """Build an info embed showing the greeting config for *kind*.

        Args:
            guild_id: Discord guild ID as string.
            config: The current GreetingConfig.
            kind: ``"welcome"`` or ``"goodbye"``.
        """
        if kind == "welcome":
            channel_id = config.welcome_channel_id
            enabled = config.welcome_enabled
            message = config.welcome_message
        else:
            channel_id = config.goodbye_channel_id
            enabled = config.goodbye_enabled
            message = config.goodbye_message

        channel_display = f"<#{channel_id}>" if channel_id else _NOT_CONFIGURED
        enabled_display = "✅" if enabled else "❌"
        message_display = message or _NOT_CONFIGURED

        return info_embed(
            t(guild_id, f"greetings.{kind}.config_title"),
            t(
                guild_id,
                f"greetings.{kind}.config_description",
                channel=channel_display,
                enabled=enabled_display,
                message=message_display,
            ),
            guild_id=guild_id,
        )

    # ------------------------------------------------------------------
    # /welcome — hybrid group (fallback = config)
    # ------------------------------------------------------------------

    @commands.hybrid_group(fallback="config")
    @app_commands.default_permissions(administrator=True)
    async def welcome(self, ctx: commands.Context) -> None:
        """Show the current welcome configuration."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        await ctx.send(
            embed=self._config_embed(guild_id, config, "welcome"),
            ephemeral=True,
        )

    @welcome.command(name="channel")
    @app_commands.describe(channel="The channel for welcome messages")
    @app_commands.default_permissions(administrator=True)
    async def welcome_channel(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
    ) -> None:
        """Set the welcome channel."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.welcome_channel_id = str(channel.id)
        await self.bot.greeting_service.save_config(config)
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.welcome.config_title"),
                t(guild_id, "greetings.welcome.channel_set_description", channel=channel.mention),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    @welcome.command(name="toggle")
    @app_commands.default_permissions(administrator=True)
    async def welcome_toggle(self, ctx: commands.Context) -> None:
        """Toggle welcome messages on/off."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.welcome_enabled = not config.welcome_enabled
        await self.bot.greeting_service.save_config(config)
        key = (
            "greetings.welcome.toggle_enabled_description"
            if config.welcome_enabled
            else "greetings.welcome.toggle_disabled_description"
        )
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.welcome.config_title"),
                t(guild_id, key),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    @welcome.command(name="message")
    @app_commands.describe(template="Message template (placeholders: {user}, {server}, {mention})")
    @app_commands.default_permissions(administrator=True)
    async def welcome_message(
        self,
        ctx: commands.Context,
        *,
        template: str,
    ) -> None:
        """Set the welcome message template."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.welcome_message = template
        await self.bot.greeting_service.save_config(config)
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.welcome.config_title"),
                t(guild_id, "greetings.welcome.message_set_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /goodbye — hybrid group (fallback = config)
    # ------------------------------------------------------------------

    @commands.hybrid_group(fallback="config")
    @app_commands.default_permissions(administrator=True)
    async def goodbye(self, ctx: commands.Context) -> None:
        """Show the current goodbye configuration."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        await ctx.send(
            embed=self._config_embed(guild_id, config, "goodbye"),
            ephemeral=True,
        )

    @goodbye.command(name="channel")
    @app_commands.describe(channel="The channel for goodbye messages")
    @app_commands.default_permissions(administrator=True)
    async def goodbye_channel(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
    ) -> None:
        """Set the goodbye channel."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.goodbye_channel_id = str(channel.id)
        await self.bot.greeting_service.save_config(config)
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.goodbye.config_title"),
                t(guild_id, "greetings.goodbye.channel_set_description", channel=channel.mention),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    @goodbye.command(name="toggle")
    @app_commands.default_permissions(administrator=True)
    async def goodbye_toggle(self, ctx: commands.Context) -> None:
        """Toggle goodbye messages on/off."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.goodbye_enabled = not config.goodbye_enabled
        await self.bot.greeting_service.save_config(config)
        key = (
            "greetings.goodbye.toggle_enabled_description"
            if config.goodbye_enabled
            else "greetings.goodbye.toggle_disabled_description"
        )
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.goodbye.config_title"),
                t(guild_id, key),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    @goodbye.command(name="message")
    @app_commands.describe(template="Message template (placeholders: {user}, {server}, {mention})")
    @app_commands.default_permissions(administrator=True)
    async def goodbye_message(
        self,
        ctx: commands.Context,
        *,
        template: str,
    ) -> None:
        """Set the goodbye message template."""
        if not await self._admin_guard(ctx):
            return
        assert self.bot.greeting_service is not None, "GreetingService initialised in setup_hook"
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        config.goodbye_message = template
        await self.bot.greeting_service.save_config(config)
        await ctx.send(
            embed=info_embed(
                t(guild_id, "greetings.goodbye.config_title"),
                t(guild_id, "greetings.goodbye.message_set_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )


async def setup(bot: NebulosaBot) -> None:
    """Load the GreetingsCog into the bot."""
    await bot.add_cog(GreetingsCog(bot))
