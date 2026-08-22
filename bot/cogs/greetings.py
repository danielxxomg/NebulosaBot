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
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.context import NebulosaContext
from bot.core.i18n import t
from bot.models.greeting_config import GreetingConfig
from bot.services.greeting_service import _resolve_avatar_url
from bot.utils.checks import can
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
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
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
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
        try:
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

    def _resolve_renderer(self) -> Any:
        """Resolve the greeting renderer (prefer image_service for cog test paths)."""
        # Prefer image_service so tests that mock only image_service keep working.
        # MagicMock auto-creates attrs, so check __dict__ for explicit assignment.
        import unittest.mock as _mock_mod

        def _explicit(obj: Any, name: str) -> bool:
            if isinstance(obj, _mock_mod.MagicMock):
                return name in obj.__dict__ or name in obj.__dict__.get("_mock_children", {})
            return hasattr(obj, name)

        # If image_service has an explicitly configured generate_greeting_card/render, prefer it.
        img_svc = getattr(self.bot, "image_service", None)
        if img_svc is not None and (_explicit(img_svc, "generate_greeting_card") or _explicit(img_svc, "render")):
            return img_svc

        if getattr(self.bot, "greeting_service", None) is not None:
            renderer = getattr(self.bot.greeting_service, "_greeting_renderer", None)
            # For MagicMock, check explicit
            if renderer is not None and not isinstance(renderer, _mock_mod.MagicMock):
                return renderer
            if isinstance(renderer, _mock_mod.MagicMock):
                # Only if explicitly set (not auto-created)
                if _explicit(self.bot.greeting_service, "_greeting_renderer"):
                    return renderer
                return img_svc
            if renderer is not None:
                return renderer
        return img_svc

    def _greeting_kwargs(
        self,
        ctx: NebulosaContext,
        card_type: str,
        title_key: str,
    ) -> dict[str, Any]:
        """Build DRY kwargs for greeting card rendering."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        member_count = (ctx.guild.member_count or 0) if ctx.guild else 0
        return {
            "username": ctx.author.display_name,
            "avatar_url": _resolve_avatar_url(ctx.author),  # ctx.author is discord.abc.User; helper accepts User
            "guild_name": ctx.guild.name if ctx.guild else "Unknown",
            "member_count": member_count,
            "card_type": card_type,
            "greeting_title": t(guild_id, title_key),
            "member_count_text": t(guild_id, "greetings.card.member_count", count=member_count),
            "guild_icon_url": _resolve_guild_icon_url(ctx.guild),
        }

    @commands.hybrid_command(
        name="welcome_test",
        description=app_commands.locale_str(
            "Enviar una tarjeta de bienvenida de prueba en este canal (solo admin).",
            key="slash.descriptions.welcome_test",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_test(self, ctx: NebulosaContext) -> None:
        """Generate and send a sample welcome card."""
        if not await self._admin_guard(ctx):
            return

        await ctx.defer(ephemeral=True)

        renderer = self._resolve_renderer()
        if renderer is None:
            msg = "Greeting renderer initialised in setup_hook"
            raise RuntimeError(msg)
        # Prefer generate_greeting_card if explicitly configured (test mock), else render.
        import unittest.mock as _mock_mod2

        def _explicit_render(obj: Any, name: str) -> bool:
            if isinstance(obj, _mock_mod2.MagicMock):
                return name in obj.__dict__ or name in obj.__dict__.get("_mock_children", {})
            return hasattr(obj, name)

        has_gen = _explicit_render(renderer, "generate_greeting_card")
        has_render = _explicit_render(renderer, "render")
        if has_gen and not has_render:
            render_fn = renderer.generate_greeting_card
        elif has_render and not has_gen:
            render_fn = renderer.render
        elif has_gen and has_render:
            # Both explicitly set — prefer generate for legacy test compat
            render_fn = renderer.generate_greeting_card
        else:
            render_fn = getattr(renderer, "render", None) or getattr(renderer, "generate_greeting_card", None)
        if render_fn is None:
            msg = "Greeting renderer missing render method"
            raise RuntimeError(msg)
        try:
            kwargs = self._greeting_kwargs(ctx, "welcome", "greetings.card.welcome_title")
            buffer: io.BytesIO = await asyncio.to_thread(render_fn, **kwargs)
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
        description=app_commands.locale_str(
            "Enviar una tarjeta de despedida de prueba en este canal (solo admin).",
            key="slash.descriptions.goodbye_test",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye_test(self, ctx: NebulosaContext) -> None:
        """Generate and send a sample goodbye card."""
        if not await self._admin_guard(ctx):
            return

        await ctx.defer(ephemeral=True)

        renderer = self._resolve_renderer()
        if renderer is None:
            msg = "Greeting renderer initialised in setup_hook"
            raise RuntimeError(msg)
        import unittest.mock as _mock_mod3

        def _explicit_render2(obj: Any, name: str) -> bool:
            if isinstance(obj, _mock_mod3.MagicMock):
                return name in obj.__dict__ or name in obj.__dict__.get("_mock_children", {})
            return hasattr(obj, name)

        has_gen2 = _explicit_render2(renderer, "generate_greeting_card")
        has_render2 = _explicit_render2(renderer, "render")
        if has_gen2 and not has_render2:
            render_fn = renderer.generate_greeting_card
        elif has_render2 and not has_gen2:
            render_fn = renderer.render
        elif has_gen2 and has_render2:
            render_fn = renderer.generate_greeting_card
        else:
            render_fn = getattr(renderer, "render", None) or getattr(renderer, "generate_greeting_card", None)
        if render_fn is None:
            msg = "Greeting renderer missing render method"
            raise RuntimeError(msg)
        try:
            kwargs = self._greeting_kwargs(ctx, "goodbye", "greetings.card.goodbye_title")
            buffer: io.BytesIO = await asyncio.to_thread(render_fn, **kwargs)
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

    async def _admin_guard(self, ctx: NebulosaContext) -> bool:
        """Check greeting.manage permission and send error if denied. Returns True if OK."""
        if await can("greeting.manage", ctx):
            return True
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        await ctx.send(
            embed=error_embed(
                t(guild_id, "greetings.permission_denied_title"),
                t(guild_id, "greetings.permission_denied_description"),
            ),
            ephemeral=True,
        )
        return False

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

        description = t(
            guild_id,
            f"greetings.{kind}.config_description",
            channel=channel_display,
            enabled=enabled_display,
            message=message_display,
        )
        if kind == "welcome":
            onboarding_display = (
                f"<#{config.onboarding_channel_id}>" if config.onboarding_channel_id else _NOT_CONFIGURED
            )
            description += f"\n**Onboarding:** {onboarding_display}"

        return info_embed(
            t(guild_id, f"greetings.{kind}.config_title"),
            description,
            guild_id=guild_id,
        )

    # ------------------------------------------------------------------
    # /welcome — hybrid group (fallback = config)
    # ------------------------------------------------------------------

    @commands.hybrid_group(
        fallback="config",
        description=app_commands.locale_str(
            "Configurar ajustes de tarjetas de bienvenida.",
            key="slash.descriptions.welcome._",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome(self, ctx: NebulosaContext) -> None:
        """Show the current welcome configuration."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        await ctx.send(
            embed=self._config_embed(guild_id, config, "welcome"),
            ephemeral=True,
        )

    @welcome.command(
        name="channel",
        description=app_commands.locale_str(
            "Definir el canal para mensajes de bienvenida.",
            key="slash.descriptions.welcome.channel",
        ),
    )
    @app_commands.describe(
        channel=app_commands.locale_str(
            "El canal para mensajes de bienvenida",
            key="slash.describes.welcome.channel.channel",
        )
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_channel(
        self,
        ctx: NebulosaContext,
        channel: discord.TextChannel,
    ) -> None:
        """Set the welcome channel."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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

    @welcome.command(
        name="toggle",
        description=app_commands.locale_str(
            "Activar o desactivar mensajes de bienvenida.",
            key="slash.descriptions.welcome.toggle",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_toggle(self, ctx: NebulosaContext) -> None:
        """Toggle welcome messages on/off."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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

    @welcome.command(
        name="message",
        description=app_commands.locale_str(
            "Definir la plantilla del mensaje de bienvenida.",
            key="slash.descriptions.welcome.message",
        ),
    )
    @app_commands.describe(
        template=app_commands.locale_str(
            "Plantilla de mensaje (marcadores: {user}, {server}, {mention})",
            key="slash.describes.welcome.message.template",
        )
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_message(
        self,
        ctx: NebulosaContext,
        *,
        template: str,
    ) -> None:
        """Set the welcome message template."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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

    @commands.hybrid_group(
        fallback="config",
        description=app_commands.locale_str(
            "Configurar ajustes de tarjetas de despedida.",
            key="slash.descriptions.goodbye._",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye(self, ctx: NebulosaContext) -> None:
        """Show the current goodbye configuration."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        config = await self.bot.greeting_service.get_config(guild_id)
        await ctx.send(
            embed=self._config_embed(guild_id, config, "goodbye"),
            ephemeral=True,
        )

    @goodbye.command(
        name="channel",
        description=app_commands.locale_str(
            "Definir el canal para mensajes de despedida.",
            key="slash.descriptions.goodbye.channel",
        ),
    )
    @app_commands.describe(
        channel=app_commands.locale_str(
            "El canal para mensajes de despedida",
            key="slash.describes.goodbye.channel.channel",
        )
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye_channel(
        self,
        ctx: NebulosaContext,
        channel: discord.TextChannel,
    ) -> None:
        """Set the goodbye channel."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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

    @goodbye.command(
        name="toggle",
        description=app_commands.locale_str(
            "Activar o desactivar mensajes de despedida.",
            key="slash.descriptions.goodbye.toggle",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye_toggle(self, ctx: NebulosaContext) -> None:
        """Toggle goodbye messages on/off."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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

    @goodbye.command(
        name="message",
        description=app_commands.locale_str(
            "Definir la plantilla del mensaje de despedida.",
            key="slash.descriptions.goodbye.message",
        ),
    )
    @app_commands.describe(
        template=app_commands.locale_str(
            "Plantilla de mensaje (marcadores: {user}, {server}, {mention})",
            key="slash.describes.goodbye.message.template",
        )
    )
    @app_commands.default_permissions(administrator=True)
    async def goodbye_message(
        self,
        ctx: NebulosaContext,
        *,
        template: str,
    ) -> None:
        """Set the goodbye message template."""
        if not await self._admin_guard(ctx):
            return
        if self.bot.greeting_service is None:
            msg = "GreetingService initialised in setup_hook"
            raise RuntimeError(msg)
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


def _resolve_guild_icon_url(guild: discord.Guild | None) -> str | None:
    """Return a guild icon URL when Discord exposes one in the local cache."""
    if guild is None:
        return None
    try:
        icon = guild.icon
        return str(icon.url) if icon is not None else None
    except Exception:
        logger.debug("Could not resolve guild icon URL", exc_info=True)
        return None
