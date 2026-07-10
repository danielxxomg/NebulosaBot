"""CoreCog — essential bot commands (ping, status, help, sync).

Provides the first four hybrid commands that prove the full stack works:
database, cache, guild config, and the bot itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.constants import FALLBACK_PREFIX
from bot.core.context import NebulosaContext
from bot.core.i18n import t
from bot.utils.brand import INFO, SUCCESS
from bot.utils.checks import is_admin
from bot.utils.embeds import error_embed, info_embed
from bot.utils.paginator import EmbedPaginator

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


# ======================================================================
# CoreCog
# ======================================================================


class CoreCog(commands.Cog, name="Core"):
    """Essential commands that prove the bot infrastructure is healthy."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # ==================================================================
    # Commands
    # ==================================================================

    @commands.hybrid_command(name="ping", description="Show the bot's WebSocket latency.")
    async def ping(self, ctx: NebulosaContext) -> None:
        """Reply with the current gateway latency in milliseconds."""
        guild_id = ctx.guild.id if ctx.guild else None
        latency = round(self.bot.latency * 1000)
        embed = info_embed(
            t(guild_id, "core.ping.title"),
            t(guild_id, "core.ping.description", latency=latency),
            guild_id=guild_id,
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="status",
        description="Show database and cache health.",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def status(self, ctx: NebulosaContext) -> None:
        """Build a health-check embed covering DB, cache, and bot state."""
        guild_id = ctx.guild.id if ctx.guild else None

        # Database health
        db_healthy = False
        if self.bot.db is not None:
            db_healthy = await self.bot.db.health_check()

        # Cache stats
        cache_keys = 0
        if self.bot.cache is not None:
            try:
                cache_keys = self.bot.cache.size
            except Exception:
                pass

        # Build embed
        embed = discord.Embed(
            title=t(guild_id, "core.status.title"),
            color=INFO,
            timestamp=datetime.now(UTC),
        )

        embed.add_field(
            name=t(guild_id, "core.status.db_field"),
            value=t(guild_id, "core.status.db_connected") if db_healthy else t(guild_id, "core.status.db_unreachable"),
            inline=True,
        )
        embed.add_field(
            name=t(guild_id, "core.status.cache_field"),
            value=t(guild_id, "core.status.cache_ok", count=cache_keys)
            if self.bot.cache is not None
            else t(guild_id, "core.status.cache_none"),
            inline=True,
        )

        # Guild config status
        if ctx.guild is None:
            guild_label = t(guild_id, "core.status.guild_config_dm")
        else:
            config = ctx.guild_config
            if config is not None:
                guild_label = t(
                    guild_id,
                    "core.status.guild_config_loaded",
                    prefix=config.prefix,
                    language=config.language,
                )
            else:
                guild_label = t(guild_id, "core.status.guild_config_missing")

        embed.add_field(
            name=t(guild_id, "core.status.guild_config_field"),
            value=guild_label,
            inline=False,
        )

        embed.add_field(
            name=t(guild_id, "core.status.latency_field"),
            value=t(
                guild_id,
                "core.status.latency_value",
                latency=round(self.bot.latency * 1000),
            ),
            inline=True,
        )

        embed.set_footer(
            text=t(guild_id, "core.status.footer"),
            icon_url="https://i.imgur.com/fvE4b0c.png",
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="help",
        description="Show available commands grouped by module.",
    )
    @app_commands.describe(module="Show help for a specific module")
    async def help_command(self, ctx: NebulosaContext, module: str | None = None) -> None:
        """Display help — all modules (paginated), or a single module if specified.

        For Phase 1 only the Core module exists. Future cogs will
        register their commands in additional modules automatically.
        """
        guild_id = ctx.guild.id if ctx.guild else None

        # -- single-module help --
        if module is not None:
            prefix = _resolve_prefix(ctx)
            embed = _build_cog_help_embed(self.bot, module, prefix, guild_id=guild_id)
            if embed is None:
                await ctx.send(
                    embed=error_embed(
                        t(guild_id, "core.help.no_module", module=module),
                        t(guild_id, "core.help.no_module_desc"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            await ctx.send(embed=embed, ephemeral=True)
            return

        # -- all-modules paginated help --
        pages = _build_help_pages(self.bot, ctx)
        if not pages:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "core.help.title", module=""),
                    t(guild_id, "core.help.no_commands"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        if len(pages) == 1:
            await ctx.send(embed=pages[0], ephemeral=True)
            return

        view = EmbedPaginator(pages, custom_id_prefix="help:")
        await ctx.send(embed=pages[0], view=view, ephemeral=True)

    @commands.hybrid_command(
        name="sync",
        description="Sync the command tree (admin only).",
    )
    @is_admin()
    async def sync(self, ctx: NebulosaContext) -> None:
        """Re-sync slash commands globally.

        Gated behind the Administrator permission via ``@is_admin()``.
        """
        guild_id = ctx.guild.id if ctx.guild else None
        await ctx.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            embed = discord.Embed(
                title=t(guild_id, "core.sync.title"),
                description=t(guild_id, "core.sync.description", count=len(synced)),
                color=SUCCESS,
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.exception("Tree sync failed")
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "core.sync.failed_title"),
                    str(exc),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register CoreCog with the bot (v2.x pattern)."""
    await bot.add_cog(CoreCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove CoreCog from the bot."""
    await bot.remove_cog("Core")


# ======================================================================
# Help page builder (internal)
# ======================================================================


def _resolve_prefix(ctx: NebulosaContext) -> str:
    """Return the active prefix for the context, or the fallback default."""
    if ctx.guild is not None and ctx.guild_config is not None:
        return ctx.guild_config.prefix
    return FALLBACK_PREFIX


def _build_cog_help_embed(
    bot: NebulosaBot,
    cog_name: str,
    prefix: str,
    *,
    guild_id: int | None = None,
) -> discord.Embed | None:
    """Build a single embed for *cog_name* showing its commands.

    Returns ``None`` if the cog is not loaded or has no commands.
    """
    cog = bot.get_cog(cog_name)
    if cog is None:
        return None

    cmds = cog.get_commands()
    # Skip hidden commands
    visible = [c for c in cmds if not c.hidden]
    if not visible:
        return None

    embed = discord.Embed(
        title=t(guild_id, "core.help.title", module=cog_name),
        description=t(
            guild_id,
            "core.help.description",
            count=len(visible),
            prefix=prefix,
        ),
        color=INFO,
        timestamp=datetime.now(UTC),
    )

    for cmd in visible:
        desc = cmd.description or "No description."
        is_hybrid = isinstance(cmd, commands.HybridCommand)
        suffix = " [prefix + slash]" if is_hybrid else " [prefix]"

        embed.add_field(
            name=(f"`{prefix}{cmd.name}` / `/{cmd.name}`" if is_hybrid else f"`{prefix}{cmd.name}`"),
            value=f"{desc}{suffix}",
            inline=False,
        )

    embed.set_footer(
        text=t(guild_id, "core.help.footer"),
        icon_url="https://i.imgur.com/fvE4b0c.png",
    )
    return embed


def _build_help_pages(bot: NebulosaBot, ctx: NebulosaContext) -> list[discord.Embed]:
    """Build one embed per loaded cog showing its commands.

    Each embed shows:
    - Module name and command count
    - Command name, description, and whether it's hybrid (prefix + slash)
    - Fetches prefix from context for consistent display
    """
    prefix = _resolve_prefix(ctx)
    guild_id = ctx.guild.id if ctx.guild else None
    pages: list[discord.Embed] = []

    for cog_name in bot.cogs:
        embed = _build_cog_help_embed(bot, cog_name, prefix, guild_id=guild_id)
        if embed is None:
            continue  # skip empty / missing cogs
        pages.append(embed)

    return pages
