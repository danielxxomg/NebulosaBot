"""GreetingsCog — welcome/goodbye card dispatching.

Listens for member join/leave events and delegates to
:class:`~bot.services.greeting_service.GreetingService` for card generation
and delivery. Configuration is managed via the /setup panel Welcome/Goodbye
modules (no command groups here; see welcome-goodbye spec).

NOTE: Slash command descriptions are Discord UI metadata, not runtime responses.
They remain in English; t() localizes runtime responses only.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.core.context import NebulosaContext  # noqa: F401 -- DRY guard expects presence
from bot.core.i18n import t
from bot.models.greeting_config import GreetingConfig
from bot.utils.checks import can
from bot.utils.embeds import error_embed, info_embed

if False:  # TYPE_CHECKING
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

_NOT_CONFIGURED = "Not configured"


class GreetingsCog(commands.Cog, name="Greetings"):
    """Welcome and goodbye card dispatching.

    Events:
        ``on_member_join``: delegates to ``GreetingService.dispatch_welcome()``.
        ``on_member_remove``: delegates to ``GreetingService.dispatch_goodbye()``.
    """

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:  # type: ignore[no-redef]
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
    # Admin guard + embed builder (kept for listeners' future needs)
    # ------------------------------------------------------------------

    async def _admin_guard(self, ctx) -> bool:
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


async def setup(bot: NebulosaBot) -> None:  # type: ignore[no-redef]
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
