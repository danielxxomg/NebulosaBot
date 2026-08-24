"""CoreCog — essential bot commands (ping, status, help, sync).

Provides the first four hybrid commands that prove the full stack works:
database, cache, guild config, and the bot itself.
"""

from __future__ import annotations

import contextlib
import logging
import resource
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.context import NebulosaContext
from bot.core.i18n import SLASH_DESCRIPTIONS, t, validate_slash_localizations
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
    # Background tasks (S4.6 — resource snapshot)
    # ==================================================================

    @tasks.loop(minutes=5)
    async def resource_log_loop(self) -> None:
        """Log a periodic process-resource snapshot (S4.6).

        DB-sourced durability is not applicable: the loop reads live
        process metrics only, so there is no state to persist across
        restarts. AGENTS.md background-loop rules honored via
        ``before_loop`` wait + ``cog_unload`` cancel.
        """
        await self._log_resource_usage()

    @resource_log_loop.before_loop
    async def _before_resource_log(self) -> None:
        await self.bot.wait_until_ready()

    async def _log_resource_usage(self) -> None:
        """Emit one resource snapshot: peak RSS, cache entries, guild count."""
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cache_size = self.bot.cache.size if self.bot.cache is not None else 0
        logger.info(
            "resources: ru_maxrss=%dkB cache_entries=%s guilds=%d",
            usage.ru_maxrss,
            cache_size,
            len(self.bot.guilds),
        )

    async def cog_unload(self) -> None:
        """Cancel the resource loop when the cog is unloaded."""
        if self.resource_log_loop.is_running():
            self.resource_log_loop.cancel()

    # ==================================================================
    # Commands
    # ==================================================================

    @commands.hybrid_command(
        name="ping",
        description=app_commands.locale_str(
            "Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        ),
    )
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
        description=app_commands.locale_str(
            "Muestra el estado de la base de datos y la caché.",
            key="slash.descriptions.status",
        ),
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
            with contextlib.suppress(Exception):
                cache_keys = self.bot.cache.size

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
                # Slash-only policy: prefix is unread at runtime.
                guild_label = t(guild_id, "core.status.guild_config_loaded", language=config.language)
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
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="help",
        description=app_commands.locale_str(
            "Muestra los comandos disponibles agrupados por módulo.",
            key="slash.descriptions.help",
        ),
    )
    @app_commands.describe(
        module=app_commands.locale_str(
            "Mostrar ayuda para un módulo específico",
            key="slash.describes.help.module",
        )
    )
    async def help_command(self, ctx: NebulosaContext, module: str | None = None) -> None:
        """Display help — all modules (paginated), or a single module if specified.

        For Phase 1 only the Core module exists. Future cogs will
        register their commands in additional modules automatically.
        """
        guild_id = ctx.guild.id if ctx.guild else None

        # -- single-module help --
        if module is not None:
            embed = _build_cog_help_embed(self.bot, module, guild_id=guild_id)
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

        view = EmbedPaginator(pages, guild_id=guild_id, custom_id_prefix="help:")
        await ctx.send(embed=pages[0], view=view, ephemeral=True)

    @commands.hybrid_command(
        name="sync",
        description=app_commands.locale_str(
            "Sincronizar el árbol de comandos (solo admin).",
            key="slash.descriptions.sync",
        ),
    )
    @is_admin()
    async def sync(self, ctx: NebulosaContext) -> None:
        """Re-sync slash commands globally.

        Gated behind the Administrator permission via ``@is_admin()``.
        Validates slash localizations before syncing.
        """
        guild_id = ctx.guild.id if ctx.guild else None
        await ctx.defer(ephemeral=True)
        try:
            validate_slash_localizations(self.bot.tree)
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


def _resolve_command_description(
    cmd: commands.Command[Any, Any, Any],
    guild_id: int | None,
) -> str:
    """Resolve a command's description in the guild's language.

    Priority:
        1. If cmd.qualified_name or cmd.name is in SLASH_DESCRIPTIONS → t(guild_id, key)
        2. Else → str(cmd.description) raw fallback
        3. If description is empty → "No description."
    """
    i18n_key = SLASH_DESCRIPTIONS.get(cmd.qualified_name) or SLASH_DESCRIPTIONS.get(cmd.name)
    if i18n_key is not None:
        return t(guild_id, i18n_key)
    if cmd.description:
        return cmd.description
    # Slash-only help: localized fallback for undescribed commands.
    return t(guild_id, "core.help.no_description")


def _build_cog_help_embed(
    bot: NebulosaBot,
    cog_name: str,
    *,
    guild_id: int | None = None,
) -> discord.Embed | None:
    """Build a single embed for *cog_name* showing its commands.

    Every entry renders slash syntax only (bot-core spec): zero prefix
    examples appear anywhere in the output.

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
        ),
        color=INFO,
        timestamp=datetime.now(UTC),
    )

    for cmd in visible:
        desc = _resolve_command_description(cmd, guild_id)

        embed.add_field(
            name=f"`/{cmd.name}`",
            value=desc,
            inline=False,
        )

    embed.set_footer(
        text=t(guild_id, "core.help.footer"),
    )
    return embed


def _build_help_pages(bot: NebulosaBot, ctx: NebulosaContext) -> list[discord.Embed]:
    """Build one embed per loaded cog showing its commands.

    Each embed shows the module name, command count, and one `/command`
    entry per visible command with its localized description.
    """
    guild_id = ctx.guild.id if ctx.guild else None
    pages: list[discord.Embed] = []

    for cog_name in bot.cogs:
        embed = _build_cog_help_embed(bot, cog_name, guild_id=guild_id)
        if embed is None:
            continue  # skip empty / missing cogs
        pages.append(embed)

    return pages
