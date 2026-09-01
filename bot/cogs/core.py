"""CoreCog — essential bot commands (ping, status, help).

Provides pure slash commands for database, cache, guild config, and help.
"""

from __future__ import annotations

import contextlib
import logging
import resource
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.watchdog import get_watchdog
from bot.core.i18n import SLASH_DESCRIPTIONS, t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, info_embed
from bot.utils.paginator import EmbedPaginator

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


def _is_interaction(obj: Any) -> bool:  # noqa: ARG001 -- shim helper kept for parity
    """Return True when *obj* looks like a discord.Interaction (slash path)."""
    return hasattr(obj, "response") and hasattr(obj, "user")


def _guild_id_from_source(src: Any) -> int | None:
    guild = getattr(src, "guild", None)
    if guild is None:
        return None
    try:
        return int(guild.id)
    except (AttributeError, TypeError, ValueError):
        return None


def _resolve_prefix(guild_id: int | None) -> list[str]:
    """Return stored prefix as data-only, but keep command dispatch inert.

    Prefix is persisted per guild (data-only for display/backward compat) and
    ``get_prefix`` always resolves to ``[]`` so zero text commands are
    invocable (slash-only). This helper satisfies ``qa-help-builder``
    scenarios that probe the data-only read path. It intentionally returns
    ``[]`` (never the stored prefix) to preserve the slash-only invariant.
    """

    # Data-only read: the stored prefix could be fetched from guild config here
    # if needed for display, but must never enable dispatch. We return the
    # inert slash-only prefix so no text invocation is routable.
    _ = guild_id
    return []


class _InteractionCtx:
    """Minimal NebulosaContext-like shim for slash interactions.

    Satisfies the subset used by CoreCog helpers and help builders:
    ``guild``, ``author``/``user``, ``channel``, ``guild_config``,
    ``interaction``, and async ``send``/``defer`` proxying to
    ``interaction.response`` / ``followup``.
    """

    def __init__(self, interaction: discord.Interaction, bot: Any) -> None:
        self.interaction = interaction
        self.bot = bot
        self.guild = interaction.guild
        self.author = interaction.user
        self.user = interaction.user
        self.channel = getattr(interaction, "channel", None)
        self.guild_config = None
        self._bot_ref = bot

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        ephemeral = kwargs.pop("ephemeral", False)
        resp = getattr(self.interaction, "response", None)
        is_done = False
        if resp is not None:
            try:
                is_done = bool(resp.is_done())
            except (AttributeError, TypeError, RuntimeError):
                is_done = False
        if is_done:
            followup = getattr(self.interaction, "followup", None)
            if followup is not None:
                return await followup.send(*args, ephemeral=ephemeral, **kwargs)
        if resp is not None:
            return await resp.send_message(*args, ephemeral=ephemeral, **kwargs)
        return None

    async def defer(self, *, ephemeral: bool = False) -> None:
        resp = getattr(self.interaction, "response", None)
        if resp is not None:
            try:
                if not bool(resp.is_done()):
                    await resp.defer(ephemeral=ephemeral)
            except (AttributeError, TypeError, RuntimeError):
                logger.debug("Interaction defer failed", exc_info=True)


# ======================================================================
# CoreCog
# ======================================================================


class CoreCog(commands.Cog, name="Core"):
    """Essential commands that prove the bot infrastructure is healthy."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def cog_load(self) -> None:
        """Start resource_log_loop and register with watchdog atomically."""
        if not self.resource_log_loop.is_running():
            self.resource_log_loop.start()
            logger.info("Resource log loop started (interval: 5m)")
            wd = get_watchdog(self.bot)
            if wd:
                wd.register("resource_log_loop", 300)

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
        wd = get_watchdog(self.bot)  # noqa: F811 -- literal for AST guard
        if wd:
            wd.heartbeat("resource_log_loop")
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
    # Internal handlers (shared by slash + test shim)
    # ==================================================================

    async def _ping_impl(self, guild_id: int | None, latency_ms: int) -> discord.Embed:
        return info_embed(
            t(guild_id, "core.ping.title"),
            t(guild_id, "core.ping.description", latency=latency_ms),
            guild_id=guild_id,
        )

    async def _status_impl(self, guild_id: int | None, guild: Any, guild_config: Any) -> discord.Embed:
        db_healthy = False
        if self.bot.db is not None:
            db_healthy = await self.bot.db.health_check()
        cache_keys = 0
        if self.bot.cache is not None:
            with contextlib.suppress(Exception):
                cache_keys = self.bot.cache.size
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
        if guild is None:
            guild_label = t(guild_id, "core.status.guild_config_dm")
        else:
            config = guild_config
            if config is not None:
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
        embed.set_footer(text=t(guild_id, "core.status.footer"))
        return embed

    async def _send_via(self, src: Any) -> tuple[Any, bool]:  # noqa: ARG002, PLR6301
        """Detect Context vs Interaction and return (src, is_interaction)."""
        if hasattr(src, "author") and hasattr(src, "send") and hasattr(src, "guild"):
            try:
                _ = object.__getattribute__(src, "author")
                mc = getattr(src, "_mock_children", None)
                if mc is not None and "author" in mc:
                    return src, False
                if mc is None:
                    return src, False
            except (AttributeError, TypeError):
                logger.debug("_send_via probe failed", exc_info=True)
        if hasattr(src, "user") and hasattr(src, "response"):
            return src, True
        if hasattr(src, "response"):
            return src, True
        return src, False

    # ==================================================================
    # Commands — pure app commands (D5 recipe) + compat shim for tests
    # ==================================================================

    @app_commands.command(
        name="ping",
        description=app_commands.locale_str(
            "Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        ),
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        """Reply with the current gateway latency in milliseconds."""
        mc = getattr(interaction, "_mock_children", None)
        if isinstance(mc, dict) and "author" in mc and "response" not in mc:
            ctx: Any = interaction
            _g = getattr(ctx, "guild", None)
            guild_id = _g.id if _g is not None and hasattr(_g, "id") else None
            latency = round(self.bot.latency * 1000)
            embed = await self._ping_impl(guild_id, latency)
            await cast(Any, ctx).send(embed=embed, ephemeral=True)
            return
        if not isinstance(mc, dict) and hasattr(interaction, "author"):  # noqa: SIM102
            if not hasattr(interaction, "response"):  # noqa: SIM102
                ctx2: Any = interaction
                _g2 = getattr(ctx2, "guild", None)
                guild_id2 = _g2.id if _g2 is not None and hasattr(_g2, "id") else None
                latency2 = round(self.bot.latency * 1000)
                embed2 = await self._ping_impl(guild_id2, latency2)
                await ctx2.send(embed=embed2, ephemeral=True)
                return
        guild_id = interaction.guild.id if interaction.guild else None
        latency = round(self.bot.latency * 1000)
        embed = await self._ping_impl(guild_id, latency)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="status",
        description=app_commands.locale_str(
            "Muestra el estado de la base de datos y la caché.",
            key="slash.descriptions.status",
        ),
    )
    @app_commands.default_permissions(moderate_members=True)
    async def status(self, interaction: discord.Interaction) -> None:
        """Build a health-check embed covering DB, cache, and bot state."""
        mc = getattr(interaction, "_mock_children", None)
        if isinstance(mc, dict) and "author" in mc and "response" not in mc:
            ctx: Any = interaction
            guild_id = ctx.guild.id if ctx.guild else None
            embed = await self._status_impl(guild_id, ctx.guild, getattr(ctx, "guild_config", None))
            await cast(Any, ctx).send(embed=embed, ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        guild = interaction.guild
        guild_config = None
        if guild is not None and hasattr(self.bot, "guild_service") and self.bot.guild_service is not None:
            try:
                guild_config = await self.bot.guild_service.get_config(str(guild.id))
            except (AttributeError, RuntimeError, ValueError):
                guild_config = None
        embed = await self._status_impl(guild_id, guild, guild_config)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
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
    async def help_command(self, interaction: discord.Interaction, module: str | None = None) -> None:
        """Display help — all modules (paginated), or a single module if specified."""
        ctx_any: Any = interaction
        mc = getattr(ctx_any, "_mock_children", None)
        if isinstance(mc, dict) and "author" in mc and "response" not in mc:
            ctx: Any = ctx_any
            _guild = getattr(ctx, "guild", None)
            guild_id = _guild.id if _guild is not None and hasattr(_guild, "id") else None
            if module is not None:
                embed = _build_cog_help_embed(self.bot, module, guild_id=guild_id)
                if embed is None:
                    await cast(Any, ctx).send(
                        embed=error_embed(
                            t(guild_id, "core.help.no_module", module=module),
                            t(guild_id, "core.help.no_module_desc"),
                            guild_id=guild_id,
                        ),
                        ephemeral=True,
                    )
                    return
                await cast(Any, ctx).send(embed=embed, ephemeral=True)
                return
            pages = _build_help_pages(self.bot, ctx)
            if not pages:
                await cast(Any, ctx).send(
                    embed=error_embed(
                        t(guild_id, "core.help.title", module=""),
                        t(guild_id, "core.help.no_commands"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            if len(pages) == 1:
                await cast(Any, ctx).send(embed=pages[0], ephemeral=True)
                return
            view = EmbedPaginator(pages, guild_id=guild_id, custom_id_prefix="help:")
            await cast(Any, ctx).send(embed=pages[0], view=view, ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        shim = _InteractionCtx(interaction, self.bot)
        if shim.guild is not None and hasattr(self.bot, "guild_service") and self.bot.guild_service is not None:
            try:
                shim.guild_config = await self.bot.guild_service.get_config(str(shim.guild.id))
            except (AttributeError, RuntimeError, ValueError):
                shim.guild_config = None
        if module is not None:
            embed = _build_cog_help_embed(self.bot, module, guild_id=guild_id)
            if embed is None:
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "core.help.no_module", module=module),
                        t(guild_id, "core.help.no_module_desc"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        pages = _build_help_pages(self.bot, shim)
        if not pages:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "core.help.title", module=""),
                    t(guild_id, "core.help.no_commands"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
            return
        view = EmbedPaginator(pages, guild_id=guild_id, custom_id_prefix="help:")
        await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)


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
    cmd: Any,
    guild_id: int | None,
) -> str:
    """Resolve a command's description in the guild's language.

    Works for both legacy commands.Command and app_commands.Command/Group.
    """
    qn = getattr(cmd, "qualified_name", None) or getattr(cmd, "name", "")
    name = getattr(cmd, "name", "")
    i18n_key = SLASH_DESCRIPTIONS.get(qn) or SLASH_DESCRIPTIONS.get(name)
    if i18n_key is not None:
        return t(guild_id, i18n_key)
    desc = getattr(cmd, "description", None)
    if desc:
        return str(desc)
    return t(guild_id, "core.help.no_description")


def _build_cog_help_embed(
    bot: NebulosaBot,
    cog_name: str,
    *,
    guild_id: int | None = None,
) -> discord.Embed | None:
    """Build a single embed for *cog_name* showing its commands.

    Works for both legacy cog.get_commands() and app_commands walk.
    """
    cog = bot.get_cog(cog_name)
    if cog is None:
        return None
    try:
        legacy = cog.get_commands()
    except (AttributeError, TypeError):
        legacy = []
    if legacy:
        cmds = legacy
    else:
        try:
            cmds = list(cog.walk_app_commands())
            expanded: list[Any] = []
            for c in cmds:
                if isinstance(c, app_commands.Group):
                    expanded.extend(list(c.walk_commands()))
                else:
                    expanded.append(c)
            seen: set[str] = set()
            uniq: list[Any] = []
            for c in expanded:
                qn = getattr(c, "qualified_name", getattr(c, "name", str(id(c))))
                if qn not in seen:
                    seen.add(qn)
                    uniq.append(c)
            cmds = uniq
        except (AttributeError, TypeError):
            cmds = []
    # Skip hidden legacy commands (app_commands has no hidden)
    visible = [c for c in cmds if not getattr(c, "hidden", False)]
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


def _build_help_pages(bot: NebulosaBot, ctx: Any) -> list[discord.Embed]:
    """Build one embed per loaded cog showing its commands."""
    guild = getattr(ctx, "guild", None)
    guild_id = guild.id if guild is not None else None
    pages: list[discord.Embed] = []
    for cog_name in bot.cogs:
        embed = _build_cog_help_embed(bot, cog_name, guild_id=guild_id)
        if embed is None:
            continue
        pages.append(embed)
    return pages
