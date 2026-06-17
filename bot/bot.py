"""NebulosaBot — the main bot class.

Wires together the database, cache, services, and cogs during
``setup_hook()`` following the startup sequence defined in the design.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import discord
from discord.ext import commands

from bot.core.cache import TTLCache
from bot.core.context import NebulosaContext
from bot.core.database import Database
from bot.cogs.tickets import TicketActionsView, TicketPanelView
from bot.services.economy_service import EconomyService
from bot.services.greeting_service import GreetingService
from bot.services.guild_service import GuildService
from bot.services.image_service import ImageService
from bot.services.infraction_service import InfractionService
from bot.services.ticket_service import TicketService
from bot.services.transcript_service import TranscriptService
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.config import BotConfig

logger = logging.getLogger(__name__)

# -- Sentry for missing guild config (used by get_prefix fallback) ----------
_FALLBACK_PREFIX = "nb!"


def _build_prefix_callable(
    bot: NebulosaBot,
) -> Callable:
    """Return an async callable that resolves the prefix per-message.

    Closure over *bot* so it can access ``guild_service`` at runtime.
    """

    async def get_prefix(bot_ref: NebulosaBot, message: discord.Message) -> str:
        if message.guild is None:
            return _FALLBACK_PREFIX

        try:
            config = await bot_ref.guild_service.get_config(str(message.guild.id))
            return config.prefix or _FALLBACK_PREFIX
        except Exception:
            logger.exception(
                "Failed to resolve prefix for guild %s — using fallback",
                message.guild.id,
            )
            return _FALLBACK_PREFIX

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
        "config",
        "db",
        "cache",
        "guild_service",
        "infraction_service",
        "ticket_service",
        "transcript_service",
        "economy_service",
        "greeting_service",
        "image_service",
        "_guild_mod_role_cache",
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

        # Used by bot/utils/checks.py is_mod() to resolve the moderator
        # role without a DB query.  Populated by GuildService.
        self._guild_mod_role_cache: dict[int, str] = {}

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

        # --- 3d. Register persistent views ---
        self.add_view(TicketPanelView())
        self.add_view(TicketActionsView())
        logger.info("Persistent ticket views registered")

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

        await self.load_extension("bot.listeners.xp_listener")
        logger.info("Listener loaded: XPListener")

        # --- 5. Tree sync ---
        logger.info("Syncing command tree ...")
        await self.tree.sync()
        logger.info("Command tree synced")

        logger.info("NebulosaBot.setup_hook() complete")

    # ==================================================================
    # Context
    # ==================================================================

    async def get_context(
        self,
        message: discord.Message,
        *,
        cls: type[commands.Context] = NebulosaContext,
    ) -> commands.Context:
        """Create a :class:`NebulosaContext` with pre-fetched guild config.

        For guild messages the ``guild_config`` attribute is populated
        eagerly so every command handler can access it synchronously.
        """
        ctx = await super().get_context(message, cls=cls)

        if ctx.guild is not None and self.guild_service is not None:
            try:
                ctx._guild_config = await self.guild_service.get_config(  # type: ignore[attr-defined]
                    str(ctx.guild.id)
                )
            except Exception:
                logger.exception(
                    "Failed to pre-fetch guild config for context (guild=%s)",
                    ctx.guild.id,
                )
                ctx._guild_config = None  # type: ignore[attr-defined]

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
            cog = interaction.command.cog
            if cog is not None and cog.cog_app_command_error is not None:
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
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Global prefix-command error handler — channel embeds.

        Sends the error as a visible embed in the channel (non-ephemeral)
        so other users can see why the command failed.
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

        embed = error_embed("Command Error", str(error))
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            logger.exception("Failed to send command error embed in channel")

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
