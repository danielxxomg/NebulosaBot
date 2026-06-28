"""CoreCog — essential bot commands (ping, status, help, sync).

Provides the first four hybrid commands that prove the full stack works:
database, cache, guild config, and the bot itself.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.context import NebulosaContext
from bot.utils.checks import is_admin
from bot.utils.embeds import COLOR_INFO, COLOR_SUCCESS, error_embed, info_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Help pagination — View with prev/next for multi-page embeds
# ------------------------------------------------------------------


class _HelpPaginator(discord.ui.View):
    """Simple two-button paginator for the /help command.

    Shows prev/next buttons that cycle through a list of pre-built
    :class:`discord.Embed` pages.  Buttons disable themselves at the
    first/last page.
    """

    __slots__ = ("_pages", "_current")

    def __init__(self, pages: list[discord.Embed]) -> None:
        super().__init__(timeout=120)  # auto-remove after 2 min idle
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
            children[0].disabled = self._current == 0  # prev
            children[1].disabled = self._current == len(self._pages) - 1  # next


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
        latency = round(self.bot.latency * 1000)
        embed = info_embed("🏓 Pong!", f"WebSocket latency: **{latency} ms**")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="status",
        description="Show database and cache health.",
    )
    async def status(self, ctx: NebulosaContext) -> None:
        """Build a health-check embed covering DB, cache, and bot state."""
        # Database health
        db_healthy = False
        if self.bot.db is not None:
            db_healthy = await self.bot.db.health_check()

        # Cache stats
        cache_keys = 0
        if self.bot.cache is not None:
            try:
                cache_keys = len(self.bot.cache._store)
            except Exception:
                pass

        # Build embed
        embed = discord.Embed(
            title="📊 NebulosaBot Status",
            color=COLOR_INFO,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="Database",
            value="✅ Connected" if db_healthy else "❌ Unreachable",
            inline=True,
        )
        embed.add_field(
            name="Cache",
            value=f"✅ {cache_keys} key(s) in memory" if self.bot.cache is not None
            else "❌ Not initialised",
            inline=True,
        )

        # Guild config status
        guild_label = "N/A (DM)"
        if ctx.guild is not None:
            config = ctx.guild_config
            if config is not None:
                guild_label = (
                    f"✅ Loaded\n"
                    f"Prefix: `{config.prefix}`\n"
                    f"Language: `{config.language}`"
                )
            else:
                guild_label = "⚠️ Not loaded"

        embed.add_field(name="Guild Config", value=guild_label, inline=False)

        embed.add_field(
            name="Latency",
            value=f"{round(self.bot.latency * 1000)} ms",
            inline=True,
        )

        embed.set_footer(text="NebulosaBot • CoreCog")
        await ctx.send(embed=embed)

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
        # -- single-module help --
        if module is not None:
            prefix = _resolve_prefix(ctx)
            embed = _build_cog_help_embed(self.bot, module, prefix)
            if embed is None:
                await ctx.send(
                    embed=error_embed(
                        f"Module '{module}' not found.",
                        "Use `/help` without arguments to see available modules.",
                    )
                )
                return
            await ctx.send(embed=embed)
            return

        # -- all-modules paginated help --
        pages = _build_help_pages(self.bot, ctx)
        if not pages:
            await ctx.send(embed=error_embed("Help", "No commands are registered yet."))
            return

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
            return

        view = _HelpPaginator(pages)
        await ctx.send(embed=pages[0], view=view)

    @commands.hybrid_command(
        name="sync",
        description="Sync the command tree (admin only).",
    )
    @is_admin()
    async def sync(self, ctx: NebulosaContext) -> None:
        """Re-sync slash commands globally.

        Gated behind the Administrator permission via ``@is_admin()``.
        """
        await ctx.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            embed = discord.Embed(
                title="✅ Commands Synced",
                description=f"{len(synced)} slash command(s) registered.",
                color=COLOR_SUCCESS,
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.exception("Tree sync failed")
            await ctx.send(
                embed=error_embed("Sync Failed", str(exc)),
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
    return "nb!"


def _build_cog_help_embed(
    bot: NebulosaBot, cog_name: str, prefix: str
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
        title=f"📚 {cog_name} Commands",
        description=(
            f"{len(visible)} command(s) available.\n"
            f"Prefix: `{prefix}`  •  Slash: `/`"
        ),
        color=COLOR_INFO,
        timestamp=datetime.now(timezone.utc),
    )

    for cmd in visible:
        desc = cmd.description or "No description."
        is_hybrid = isinstance(cmd, commands.HybridCommand)
        suffix = " [prefix + slash]" if is_hybrid else " [prefix]"

        embed.add_field(
            name=(
                f"`{prefix}{cmd.name}` / `/{cmd.name}`" if is_hybrid
                else f"`{prefix}{cmd.name}`"
            ),
            value=f"{desc}{suffix}",
            inline=False,
        )

    embed.set_footer(text="NebulosaBot • /help")
    return embed


def _build_help_pages(bot: NebulosaBot, ctx: NebulosaContext) -> list[discord.Embed]:
    """Build one embed per loaded cog showing its commands.

    Each embed shows:
    - Module name and command count
    - Command name, description, and whether it's hybrid (prefix + slash)
    - Fetches prefix from context for consistent display
    """
    prefix = _resolve_prefix(ctx)
    pages: list[discord.Embed] = []

    for cog_name in bot.cogs:
        embed = _build_cog_help_embed(bot, cog_name, prefix)
        if embed is None:
            continue  # skip empty / missing cogs
        pages.append(embed)

    return pages
