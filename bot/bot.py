"""NebulosaBot — the main bot class.

Wires together the database, cache, services, and cogs during
``setup_hook()`` following the startup sequence defined in the design.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from bot.constants import FALLBACK_PREFIX
from bot.core.cache import TTLCache
from bot.core.context import NebulosaContext
from bot.core.database import Database, create_realtime_client
from bot.core.i18n import load_locales, t
from bot.core.realtime import RealtimeCacheSubscriber
from bot.services.economy_service import EconomyService
from bot.services.greeting_service import GreetingService
from bot.services.guild_service import GuildService
from bot.services.image_service import ImageService
from bot.services.infraction_service import InfractionService
from bot.services.logging_service import LoggingService
from bot.services.ticket_service import TicketService
from bot.services.transcript_service import TranscriptService
from bot.utils.embeds import error_embed
from bot.views.tickets import TicketActionsView, TicketPanelView, deploy_ticket_panel

if TYPE_CHECKING:
    from bot.config import BotConfig

# Concurrency cap for on_ready guild backfill. Bounded to avoid overwhelming
# Supabase with concurrent requests when the bot is in many guilds at once.
BACKFILL_CONCURRENCY_LIMIT = 50

logger = logging.getLogger(__name__)

# -- Sentry for missing guild config (used by get_prefix fallback) ----------


def _build_prefix_callable(
    bot: NebulosaBot,
) -> Callable[..., Any]:
    """Return an async callable that resolves the prefix per-message.

    Closure over *bot* so it can access ``guild_service`` at runtime.
    """

    async def get_prefix(bot_ref: NebulosaBot, message: discord.Message) -> list[str]:
        prefix = FALLBACK_PREFIX
        if message.guild is not None:
            try:
                if bot_ref.guild_service is not None:
                    config = await bot_ref.guild_service.get_config(str(message.guild.id))
                    prefix = config.prefix or FALLBACK_PREFIX
            except Exception:
                logger.exception(
                    "Failed to resolve prefix for guild %s — using fallback",
                    message.guild.id,
                )
        return [prefix, ","]

    return get_prefix


# ======================================================================
# NebulosaBot
# ======================================================================


class NebulosaBot(commands.Bot):
    """Discord bot with cache-first guild config and hybrid commands.

    Instantiate with a validated :class:`~bot.config.BotConfig` and the
    desired Discord intents.  Cogs are loaded in ``setup_hook()`` before
    the gateway connects.

    Attributes:
        config: The validated bot configuration.
        db: Supabase-backed :class:`Database` instance.
        cache: In-memory :class:`TTLCache` instance.
        guild_service: Cache-first :class:`GuildService` instance.
        infraction_service: Moderation business-logic :class:`InfractionService` instance.
        ticket_service: Ticket lifecycle :class:`~bot.services.ticket_service.TicketService` instance.
        transcript_service: HTML transcript :class:`~bot.services.transcript_service.TranscriptService` instance.
        economy_service: Economy system :class:`~bot.services.economy_service.EconomyService` instance.
        image_service: Rank card :class:`~bot.services.image_service.ImageService` instance (PR 3).
    """

    __slots__ = (
        "_guild_mod_role_cache",
        "_realtime_subscriber",
        "cache",
        "config",
        "db",
        "economy_service",
        "greeting_service",
        "guild_service",
        "image_service",
        "infraction_service",
        "logging_service",
        "ticket_service",
        "transcript_service",
    )

    def __init__(
        self,
        *,
        config: BotConfig,
        intents: discord.Intents,
    ) -> None:
        self.config = config

        # Instantiated during setup_hook() after DB connects.
        self.db: Database | None = None
        self.cache: TTLCache | None = None
        self.guild_service: GuildService | None = None
        self.infraction_service: InfractionService | None = None
        self.ticket_service: TicketService | None = None
        self.transcript_service: TranscriptService | None = None
        self.economy_service: EconomyService | None = None
        self.greeting_service: GreetingService | None = None
        self.image_service: ImageService | None = None
        self.logging_service: LoggingService | None = None

        # Used by bot/utils/checks.py is_mod() to resolve the moderator
        # role without a DB query.  Populated by GuildService.
        self._guild_mod_role_cache: dict[int, str] = {}

        # Realtime CDC subscriber (replaces the webhook in PR 2).  Started in
        # setup_hook() and stopped in close(); None in degraded mode.
        self._realtime_subscriber: RealtimeCacheSubscriber | None = None

        # Build the prefix callable.  We pass `self` by reference so the
        # closure calls back into guild_service at message time.
        prefix_callable = _build_prefix_callable(self)

        super().__init__(
            command_prefix=prefix_callable,
            intents=intents,
            # discord.py 2.x requires explicit help_command disable when
            # we provide our own /help hybrid command.
            help_command=None,
        )

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def setup_hook(self) -> None:
        """Initialise infrastructure before the gateway connects.

        Sequence (per design):
            1. Database.connect() + health check
            2. TTLCache init
            3. GuildService init
            4. Load cogs
            5. Tree sync (register slash commands)
        """
        logger.info("NebulosaBot.setup_hook() starting ...")

        # --- 1. Database ---
        self.db = Database(self.config.supabase_url, self.config.supabase_key)
        await self.db.connect()

        # --- 2. Cache ---
        self.cache = TTLCache()

        # --- 2b. Realtime cache-sync subscriber ---
        await self._start_realtime()

        # --- 3. GuildService ---
        self.guild_service = GuildService(
            db=self.db,
            cache=self.cache,
            mod_role_cache=self._guild_mod_role_cache,
        )

        # --- 3b. InfractionService ---
        self.infraction_service = InfractionService(db=self.db)
        logger.info("InfractionService initialised")

        # --- 3c. TicketService + TranscriptService ---
        self.ticket_service = TicketService(db=self.db, cache=self.cache)
        self.transcript_service = TranscriptService()
        logger.info("TicketService and TranscriptService initialised")

        # --- 3d. EconomyService ---
        self.economy_service = EconomyService(db=self.db, cache=self.cache)
        logger.info("EconomyService initialised")

        # --- 3e. ImageService ---
        self.image_service = ImageService()
        logger.info("ImageService initialised")

        # --- 3f. GreetingService ---
        self.greeting_service = GreetingService(
            db=self.db,
            cache=self.cache,
            image_service=self.image_service,
        )
        logger.info("GreetingService initialised")

        # --- 3g. LoggingService ---
        self.logging_service = LoggingService(self)
        logger.info("LoggingService initialised")

        # --- 3d. Register persistent views ---
        self.add_view(TicketPanelView())
        self.add_view(TicketActionsView())
        logger.info("Persistent ticket views registered")

        # --- 3h. Load i18n locales ---
        load_locales(Path("bot/locales"))
        logger.info("i18n locales loaded")

        # --- 4. Load cogs ---
        await self.load_extension("bot.cogs.core")
        logger.info("Cog loaded: CoreCog")

        await self.load_extension("bot.cogs.sentinel")
        logger.info("Cog loaded: SentinelCog")

        await self.load_extension("bot.cogs.tickets")
        logger.info("Cog loaded: TicketsCog")

        await self.load_extension("bot.cogs.stellar")
        logger.info("Cog loaded: StellarCog")

        await self.load_extension("bot.cogs.greetings")
        logger.info("Cog loaded: GreetingsCog")

        await self.load_extension("bot.cogs.utility")
        logger.info("Cog loaded: UtilityCog")

        await self.load_extension("bot.cogs.ocio")
        logger.info("Cog loaded: OcioCog")

        await self.load_extension("bot.cogs.setup")
        logger.info("Cog loaded: SetupCog")

        await self.load_extension("bot.listeners.xp_listener")
        logger.info("Listener loaded: XPListener")

        await self.load_extension("bot.listeners.audit_listener")
        logger.info("Listener loaded: AuditListener")

        # --- 5. Tree sync ---
        logger.info("Syncing command tree ...")
        await self.tree.sync()
        logger.info("Command tree synced")

        logger.info("NebulosaBot.setup_hook() complete")

    # ==================================================================
    # Realtime cache-sync subscriber lifecycle
    # ==================================================================

    async def _start_realtime(self) -> None:
        """Start the Realtime CDC subscriber in degraded-safe mode.

        Mirrors the webhook's degraded-safe pattern: if the subscriber
        cannot start (network error, missing publication, etc.) the bot
        keeps running with a TTL-only cache rather than crashing the
        gateway.
        """
        if self.cache is None:
            return
        try:
            self._realtime_subscriber = RealtimeCacheSubscriber(
                supabase_url=self.config.supabase_url,
                supabase_key=self.config.supabase_key,
                cache=self.cache,
                client_factory=create_realtime_client,
            )
            await self._realtime_subscriber.start()
            # Wire self-echo filtering: database writes mark recent entries
            # so the Realtime CDC handler suppresses the echo.
            if self.db is not None:
                self.db._on_write = self._realtime_subscriber.mark_recent_write
        except Exception:
            logger.exception("Failed to start Realtime subscriber — continuing with TTL-only cache invalidation")
            self._realtime_subscriber = None

    async def _stop_realtime(self) -> None:
        """Stop the Realtime subscriber if it was started (idempotent)."""
        if self._realtime_subscriber is None:
            return
        try:
            # Disconnect the write callback before stopping.
            if self.db is not None:
                self.db._on_write = None
            await self._realtime_subscriber.stop()
        except Exception:
            logger.exception("Realtime subscriber stop() failed during shutdown")
        self._realtime_subscriber = None

    async def close(self) -> None:
        """Stop the Realtime subscriber, then close the Discord gateway.

        The subscriber is torn down BEFORE the gateway so cache-invalidation
        paths stop accepting/stripping events cleanly.
        """
        await self._stop_realtime()
        await super().close()

    # ==================================================================
    # Context
    # ==================================================================

    async def get_context(  # type: ignore[override]  # intentional: only Message, not Interaction
        self,
        message: discord.Message,
        *,
        cls: type[commands.Context[NebulosaBot]] = NebulosaContext,
    ) -> commands.Context[NebulosaBot]:
        """Create a :class:`NebulosaContext` with pre-fetched guild config.

        For guild messages the ``guild_config`` attribute is populated
        eagerly so every command handler can access it synchronously.
        """
        ctx = await super().get_context(message, cls=cls)

        if ctx.guild is not None and self.guild_service is not None:
            try:
                ctx._guild_config = await self.guild_service.get_config(str(ctx.guild.id))
            except Exception:
                logger.exception(
                    "Failed to pre-fetch guild config for context (guild=%s)",
                    ctx.guild.id,
                )
                ctx._guild_config = None

        return ctx

    # ==================================================================
    # Error handling
    # ==================================================================

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Global slash-command error handler — ephemeral embeds.

        Catches every unhandled app-command error and presents it to the
        user as a red embed.  Specific cogs can still override per-command
        error handling with ``@command.error``.
        """
        # Delegate to per-command handlers if they exist.
        if interaction.command is not None:
            cog = interaction.command.cog  # type: ignore[union-attr]  # both Command and ContextMenu have .cog
            if cog is not None and cog.has_app_command_error_handler():
                return

        embed = error_embed("Unexpected Error", str(error))

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Failed to send app-command error embed")

    async def on_command_error(
        self,
        ctx: commands.Context[NebulosaBot],  # type: ignore[override]  # supertype uses Context[BotT]
        error: commands.CommandError,
    ) -> None:
        """Global prefix-command error handler — DM-first with channel fallback.

        For prefix commands in a guild channel, the error embed is DM'd to the
        invoking user so it doesn't pollute the channel.  If the DM fails
        (user has DMs disabled), the embed falls back to the channel with a
        note.  In DMs (no guild), the error is sent directly.
        """
        # Ignore commands that have local error handlers.
        if hasattr(ctx.command, "on_error"):
            return

        # Ignore some common, harmless errors.
        ignored = (
            commands.CommandNotFound,
            commands.DisabledCommand,
        )
        if isinstance(error, ignored):
            return

        guild_id = ctx.guild.id if ctx.guild else None
        embed = error_embed(
            t(guild_id, "common.error.command_error_title"),
            str(error),
            guild_id=guild_id,
        )

        # In a guild channel: try DM first, fall back to channel.
        if ctx.guild is not None:
            try:
                await ctx.author.send(embed=embed)
                return
            except (discord.HTTPException, discord.Forbidden):
                logger.debug(
                    "DM failed for user %s — falling back to channel",
                    ctx.author.id,
                )
                # Channel fallback with a note.
                fallback_embed = error_embed(
                    t(guild_id, "common.error.command_error_title"),
                    t(guild_id, "common.error.dm_failed_description"),
                    guild_id=guild_id,
                )
                try:
                    await ctx.send(embed=fallback_embed)
                except discord.HTTPException:
                    logger.exception("Failed to send command error embed in channel")
            return

        # In DMs: send directly.
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            logger.exception("Failed to send command error embed in DM")

    # ==================================================================
    # Events
    # ==================================================================

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Insert default guild configuration when the bot joins a server."""
        if self.guild_service is not None:
            await self.guild_service.on_guild_join(str(guild.id))

    async def on_ready(self) -> None:
        """Called once when the bot has connected to the Discord gateway."""
        logger.info("NebulosaBot is online — logged in as %s", self.user)
        # Backfill guild config for guilds the bot was already a member of at
        # startup (on_guild_join only fires for joins during the session).
        if self.guild_service is not None:
            tasks: list[Coroutine[Any, Any, None]] = [
                self.guild_service.ensure_guild_exists(str(guild.id))
                for guild in self.guilds
            ]
            if len(tasks) > BACKFILL_CONCURRENCY_LIMIT:
                semaphore = asyncio.Semaphore(BACKFILL_CONCURRENCY_LIMIT)

                async def _bounded(coro: Coroutine[Any, Any, None]) -> None:
                    async with semaphore:
                        await coro

                tasks = [_bounded(t) for t in tasks]
            # return_exceptions=True so one bad guild doesn't abort backfill.
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Backfilled guild config for %d guild(s)", len(self.guilds))

        # --- Panel validation: verify stored panels and self-heal ---
        await self._validate_panels()

    # ==================================================================
    # Panel validation / self-heal
    # ==================================================================

    async def _validate_panels(self) -> None:
        """Validate stored ticket panels and self-heal missing/stripped ones.

        Runs AFTER guild backfill completes.  Only guilds with a stored
        ``ticket_panel_message_id`` are checked.  Uses bounded concurrency
        matching the backfill pattern.
        """
        if self.guild_service is None:
            return

        # Collect guilds with stored panel IDs.
        guild_ids: list[str] = []
        for guild in self.guilds:
            try:
                config = await self.guild_service.get_config(str(guild.id))
                if config.ticket_panel_message_id:
                    guild_ids.append(str(guild.id))
            except Exception:
                logger.exception(
                    "Failed to read config for guild %s during panel validation",
                    guild.id,
                )

        if not guild_ids:
            logger.info("No stored panel IDs — skipping panel validation")
            return

        logger.info("Validating panels for %d guild(s) ...", len(guild_ids))

        tasks = [self._validate_single_panel(gid) for gid in guild_ids]
        if len(tasks) > BACKFILL_CONCURRENCY_LIMIT:
            semaphore = asyncio.Semaphore(BACKFILL_CONCURRENCY_LIMIT)

            async def _bounded(coro: Coroutine[Any, Any, None]) -> None:
                async with semaphore:
                    await coro

            tasks = [_bounded(t) for t in tasks]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _validate_single_panel(self, guild_id: str) -> None:
        """Validate a single guild's ticket panel; self-heal if unhealthy."""
        assert self.guild_service is not None

        # Resolve guild from the guilds list (populated by the gateway).
        guild: discord.Guild | None = None
        for g in self.guilds:
            if str(g.id) == guild_id:
                guild = g
                break

        if guild is None:
            logger.warning(
                "Panel validation: guild %s not found in cache — skipping",
                guild_id,
            )
            return

        config = await self.guild_service.get_config(guild_id)
        msg_id = config.ticket_panel_message_id
        ch_id = config.ticket_panel_channel_id

        if not msg_id or not ch_id:
            return

        # Resolve channel.
        channel = guild.get_channel(int(ch_id))
        if channel is None:
            logger.warning(
                "Panel validation: channel %s not found for guild %s — clearing panel IDs",
                ch_id,
                guild_id,
            )
            await self.guild_service.update_guild_panel(guild_id, None, None)
            return

        # Fetch the message and check for the ticket:open button.
        try:
            message = await channel.fetch_message(int(msg_id))  # type: ignore[union-attr]
        except discord.NotFound:
            logger.warning(
                "Panel validation: message %s deleted in guild %s — re-deploying",
                msg_id,
                guild_id,
            )
            await deploy_ticket_panel(channel, guild_id, bot=self, guild=guild)  # type: ignore[arg-type]
            return
        except discord.Forbidden:
            logger.warning(
                "Panel validation: Forbidden fetching message %s in guild %s — skipping",
                msg_id,
                guild_id,
            )
            return
        except discord.HTTPException:
            logger.exception(
                "Panel validation: HTTP error fetching message %s in guild %s — skipping",
                msg_id,
                guild_id,
            )
            return

        # Check for ticket:open button in components.
        has_ticket_button = False
        for component in message.components:
            if hasattr(component, "children"):
                for child in component.children:
                    if getattr(child, "custom_id", None) == "ticket:open":
                        has_ticket_button = True
                        break

        if not has_ticket_button:
            logger.warning(
                "Panel validation: message %s in guild %s has no ticket:open button — re-deploying",
                msg_id,
                guild_id,
            )
            await deploy_ticket_panel(channel, guild_id, bot=self, guild=guild)  # type: ignore[arg-type]
