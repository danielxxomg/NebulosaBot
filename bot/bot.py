"""NebulosaBot — the main bot class.

Wires together the database, cache, services, and cogs during
``setup_hook()`` following the startup sequence defined in the design.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import traceback
from collections.abc import Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.cache import TTLCache
from bot.core.context import NebulosaContext
from bot.core.database import Database, create_realtime_client
from bot.core.i18n import LocaleTranslator, load_locales, t, validate_slash_localizations
from bot.core.realtime import RealtimeCacheSubscriber
from bot.services.crash_report_service import CrashReportService
from bot.services.economy_service import EconomyService
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.greeting_service import GreetingService
from bot.services.guild_service import GuildService
from bot.services.infraction_service import InfractionService
from bot.services.logging_service import LoggingService
from bot.services.rank_renderer import RankRenderer
from bot.services.ticket_service import TicketService
from bot.services.transcript_service import TranscriptService
from bot.utils.embeds import error_embed
from bot.views.tickets import TicketActionsView, TicketPanelView, deploy_ticket_panel

if TYPE_CHECKING:
    from bot.config import BotConfig  # noqa: PLC0415 -- optional-dependency probe — cairosvg may be absent

from bot.config import RANK_RENDER_MAX_CONCURRENT

# Concurrency cap for on_ready guild backfill. Bounded to avoid overwhelming
# Supabase with concurrent requests when the bot is in many guilds at once.
BACKFILL_CONCURRENCY_LIMIT = 50

logger = logging.getLogger(__name__)

# Ordered extension paths loaded during setup_hook(). Each path is attempted
# once in order; a failure is logged at ERROR and does not prevent subsequent
# paths or tree.sync().
EXTENSIONS: tuple[str, ...] = (
    "bot.cogs.core",
    "bot.cogs.sentinel",
    "bot.cogs.tickets",
    "bot.cogs.stellar",
    "bot.cogs.greetings",
    "bot.cogs.utility",
    "bot.cogs.ocio",
    "bot.cogs.setup",
    "bot.listeners.xp_listener",
    "bot.listeners.audit_listener",
    "bot.listeners.voice_listener",
)

# -- Slash-only command surface: inert prefix resolver -----------------------


async def _noop_prefix(bot_ref: NebulosaBot, message: discord.Message) -> list[str]:
    """Return an empty prefix list — the text-command surface is slash-only.

    bot-core spec: zero text-invocable commands; ``nb!``/`,` invocations are
    inert and guild config is never consulted here. The ticket-channel ``,``
    timer operates in ``TicketsCog.on_message``, outside the command framework
    (close-confirmation spec, unchanged by this policy).

    Signature matches what discord.py expects for ``command_prefix``
    (``(bot, message) -> list[str] | str``).
    """
    _ = (bot_ref, message)
    return []


# ======================================================================
# NebulosaBot
# ======================================================================


class NebulosaBot(commands.Bot):
    """Discord bot with cache-first guild config and slash-only commands.

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
        rank_renderer: Shared :class:`~bot.services.rank_renderer.RankRenderer` instance for /rank.
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
        "infraction_service",
        "logging_service",
        "rank_render_sem",
        "rank_renderer",
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
        self.logging_service: LoggingService | None = None
        self.rank_renderer: RankRenderer | None = None

        # Used by bot/utils/checks.py is_mod() to resolve the moderator
        # role without a DB query.  Populated by GuildService.
        self._guild_mod_role_cache: dict[int, str] = {}

        # S0.11: bot-wide semaphore capping concurrent /rank Pillow renders
        # so burst requests cannot saturate the thread pool.
        self.rank_render_sem = asyncio.Semaphore(RANK_RENDER_MAX_CONCURRENT)

        # Realtime CDC subscriber (replaces the webhook in PR 2).  Started in
        # setup_hook() and stopped in close(); None in degraded mode.
        self._realtime_subscriber: RealtimeCacheSubscriber | None = None

        # Slash-only surface (bot-core spec): static empty prefix — no text
        # command is invocable. The ticket ',' timer lives outside the
        # framework, so no per-message guild-config resolution happens here.
        super().__init__(
            command_prefix=_noop_prefix,
            intents=intents,
            # discord.py 2.x requires explicit help_command disable when
            # we provide our own /help slash command.
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

        # --- 3b. TicketService + TranscriptService ---
        self.ticket_service = TicketService(db=self.db, cache=self.cache)
        self.transcript_service = TranscriptService()
        logger.info("TicketService and TranscriptService initialised")

        # --- 3d. EconomyService ---
        self.economy_service = EconomyService(db=self.db, cache=self.cache)
        logger.info("EconomyService initialised")

        # --- 3f. GreetingRenderer probe (cairosvg → Pillow fallback) ---
        try:
            import cairosvg  # ty: ignore[unresolved-import]  # noqa: F401, PLC0415 -- optional-dependency probe; lazy import keeps module loadable when cairosvg missing

            _cairosvg_available = True
        except ImportError:
            _cairosvg_available = False
            logger.warning("cairosvg not available — using PillowGreetingRenderer")

        # Cycle 1: Pillow is always the injected renderer (cairosvg path reserved for Cycle 2).
        _greeting_renderer = PillowGreetingRenderer()
        if _cairosvg_available:
            logger.info("cairosvg available but Cycle 1 uses PillowGreetingRenderer (probe acknowledged)")

        # Store the RankRenderer on the bot so cog code uses a single shared
        # instance (self.bot.rank_renderer) instead of building one per /rank;
        # the cog needs no lazy import or legacy fallback branch.
        self.rank_renderer = RankRenderer()

        # --- 3g. GreetingService ---
        self.greeting_service = GreetingService(
            db=self.db,
            cache=self.cache,
            greeting_renderer=_greeting_renderer,
        )
        logger.info("GreetingService initialised")

        # --- 3h. LoggingService ---
        self.logging_service = LoggingService(self)
        logger.info("LoggingService initialised")

        # --- 3i. InfractionService (needs LoggingService for escalation audit) ---
        self.infraction_service = InfractionService(db=self.db, logging_service=self.logging_service)
        logger.info("InfractionService initialised")

        # --- 3j. Register persistent views ---
        self.add_view(TicketPanelView())
        self.add_view(TicketActionsView())
        # S2a: Setup panel persistent view (static custom_ids, breadcrumb token)
        try:
            from bot.views.setup_panel import (  # noqa: PLC0415 -- optional-dependency probe: panel may not be landed in S0
                SetupPanelView,
                set_setup_bot,
            )

            self.add_view(SetupPanelView())
            set_setup_bot(self)
            logger.info("Persistent setup panel view registered")
        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
            logger.exception("Failed to register SetupPanelView")
        logger.info("Persistent ticket views registered")

        # --- 3k. Load i18n locales ---
        load_locales(Path("bot/locales"))
        logger.info("i18n locales loaded")

        # --- 4. Load cogs ---
        for ext_path in EXTENSIONS:
            try:
                await self.load_extension(ext_path)
                logger.info("Extension loaded: %s", ext_path)
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                logger.exception("Failed to load extension %s", ext_path)

        # --- 4b. Retention upsert + cron reconcile (S3.8) ---
        await self._setup_retention()

        # --- 5. Validate slash localizations + set translator + tree sync ---
        logger.info("Validating slash localizations ...")
        validate_slash_localizations(self.tree)

        logger.info("Setting translator ...")
        await self.tree.set_translator(LocaleTranslator())

        logger.info("Syncing command tree ...")
        await self.tree.sync()
        logger.info("Command tree synced")

        logger.info("NebulosaBot.setup_hook() complete")

    # ==================================================================
    # Retention upsert + cron reconcile (S3.8)
    # ==================================================================

    async def _setup_retention(self) -> None:  # noqa: C901 -- retention upsert + cron reconcile branches intentional for S3
        """Upsert retention_setting from config and reconcile pg_cron.

        Reads TTLs from an optional OperationalConfig (bot/operational_config.py,
        S4) if present, else falls back to seeded defaults (30/180/30). The
        cron schedule itself lives in SQL (028/029 DO $guard$ blocks); this
        hook reconciles the flag: when retention is disabled, unschedule the
        jobs. All paths are best-effort — failure never crashes setup_hook.
        """
        if self.db is None:
            return
        # Try to load OperationalConfig if S4 has landed; otherwise use defaults.
        retention_enabled = True
        retention_defaults: dict[str, int] = {"tickets": 30, "infractions": 180, "crash": 30}
        try:
            # Import lazily so S3 works before S4 lands (config file may not exist yet).
            spec = importlib.util.find_spec("bot.operational_config")
            if spec is not None:
                import bot.operational_config as op_mod  # noqa: PLC0415 -- optional-dependency probe: S4 not yet landed

                # OperationalConfig may expose retention via .retention or .flags
                cfg = None
                # Try factory/load if available
                load_fn = getattr(op_mod, "load_operational_config", None)
                if callable(load_fn):
                    try:
                        cfg = load_fn()
                    except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                        cfg = None
                if cfg is not None:
                    ret = getattr(cfg, "retention", None)
                    if ret is not None:
                        for k in ("tickets", "infractions", "crash"):
                            v = getattr(ret, k, None)
                            if isinstance(v, int) and v > 0:
                                retention_defaults[k] = v
                    flags = getattr(cfg, "flags", None)
                    if flags is not None:
                        enabled = getattr(flags, "retention_enabled", None)
                        if isinstance(enabled, bool):
                            retention_enabled = enabled
        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
            logger.debug("OperationalConfig not available — using seeded retention defaults", exc_info=True)

        # Upsert retention_setting via direct SQL (via _client if available)
        try:
            client = getattr(self.db, "_client", None)
            if client is not None:
                for key, days in retention_defaults.items():
                    try:
                        await (
                            client
                            .table("retention_setting")
                            .upsert({"key": key, "days": days}, on_conflict="key")
                            .execute()
                        )
                    except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                        # Fallback: raw RPC / execute_sql if table helper fails
                        logger.debug("retention_setting upsert via table failed for %s", key, exc_info=True)
                        # Try via rpc if available
                        try:
                            await client.rpc("upsert_retention_setting", {"p_key": key, "p_days": days}).execute()
                        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                            logger.warning("retention_setting upsert fallback also failed for %s", key, exc_info=True)
            logger.info("Retention settings upserted: %s (enabled=%s)", retention_defaults, retention_enabled)
        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
            logger.warning("Failed to upsert retention_setting", exc_info=True)

        # Cron reconcile: flag off → unschedule
        if not retention_enabled:
            try:
                client = getattr(self.db, "_client", None)
                if client is not None:
                    for job in (
                        "retention_purge_tickets",
                        "retention_purge_storage",
                        "retention_purge_infractions",
                        "retention_purge_crash_reports",
                    ):
                        try:
                            await client.rpc("cron_unschedule", {"jobname": job}).execute()
                        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                            # Fallback: direct SQL via rpc
                            try:
                                await client.rpc("exec_sql", {"q": f"SELECT cron.unschedule('{job}')"}).execute()
                            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                                logger.debug("cron unschedule failed for %s", job, exc_info=True)
                logger.info("Retention disabled — cron jobs unscheduled")
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
                logger.warning("Failed to unschedule retention cron jobs", exc_info=True)

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
        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
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
        except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
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
        if not isinstance(ctx, NebulosaContext):
            msg = "get_context did not return NebulosaContext"
            raise TypeError(msg)

        if ctx.guild is not None and self.guild_service is not None:
            try:
                ctx._guild_config = await self.guild_service.get_config(str(ctx.guild.id))
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
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
        user as a red embed.  The full exception is logged with traceback
        BEFORE any user-facing response (spec logging-service). Specific
        cogs can still override per-command error handling with
        ``@command.error``.
        """
        # Delegate to per-command handlers if they exist.
        if interaction.command is not None:
            cog = interaction.command.cog  # type: ignore[union-attr]  # both Command and ContextMenu have .cog
            if cog is not None and cog.has_app_command_error_handler():
                return

        guild_id = interaction.guild.id if interaction.guild else None

        # S6B: CommandOnCooldown → ephemeral localized retry_after (ocio + stellar)
        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = getattr(error, "retry_after", 5.0)
            embed = error_embed(
                t(guild_id, "ocio.cooldown.title"),
                t(guild_id, "ocio.cooldown.description", retry_after=retry_after),
                guild_id=guild_id,
            )
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except discord.HTTPException:
                logger.exception("Failed to send app-cooldown embed")
            return

        # Permission denials get dedicated ephemeral replies (bot-core delta):
        # localized, naming the missing permissions when applicable, and with
        # NO full traceback shown to the user. MissingPermissions is a
        # CheckFailure subclass, so it MUST be matched first.
        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = error_embed(
                t(guild_id, "common.error.missing_permissions_title"),
                t(guild_id, "common.error.missing_permissions_description", permissions=missing),
                guild_id=guild_id,
            )
        elif isinstance(error, app_commands.CheckFailure):
            logger.warning(
                "App-command check denied (guild=%s, command=%s)",
                guild_id,
                getattr(interaction.command, "qualified_name", None),
            )
            embed = error_embed(
                t(guild_id, "common.error.check_failure_title"),
                t(guild_id, "common.error.check_failure_description"),
                guild_id=guild_id,
            )
        else:
            # Log first (spec logging-service): full exception + traceback must
            # be on record before the user-facing embed is produced.
            logger.error(
                "Unhandled app-command error (guild=%s, command=%s)",
                interaction.guild_id,
                getattr(interaction.command, "qualified_name", None),
                exc_info=error,
            )
            # S3.6: record crash_report ONLY for unhandled exceptions (F4 scope)
            try:
                if self.db is not None:
                    svc = CrashReportService(self.db)
                    tb_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                    qname = getattr(interaction.command, "qualified_name", None)
                    await svc.record(
                        guild_id=str(guild_id) if guild_id is not None else None,
                        command=qname,
                        traceback_text=tb_text,
                    )
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook  # noqa: BLE001 -- crash reporting never breaks error handler
                logger.warning("Failed to record crash_report for app command", exc_info=True)
            embed = error_embed(
                t(guild_id, "common.error.unexpected_title"),
                t(guild_id, "common.error.unexpected_message"),
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Failed to send app-command error embed")

    async def on_command_error(
        self,
        ctx: commands.Context[NebulosaBot],
        error: commands.CommandError,
    ) -> None:
        """Global command error handler — single channel-path embed.

        With the prefix surface inert (bot-core spec), this handler defines
        NO DM delivery path: the error embed goes directly to the channel
        where the context originated, localized via ``t(guild_id, ...)``.
        """
        # Ignore commands that have local error handlers.
        if hasattr(ctx.command, "on_error"):
            return

        # Defer to the cog's cog_command_error handler when the cog owns one
        # (mirrors the app-command deferral above at on_app_command_error).
        # discord.py's dispatch_error runs cog_command_error FIRST, then
        # always dispatches the command_error event here — without this
        # deferral the user gets two messages (the cog's embed + ours).
        # Scoped to CommandOnCooldown: cogs that handle cooldown own that
        # surface; other errors still flow through here so they are not
        # silently swallowed (AGENTS.md: all commands MUST handle errors).
        if isinstance(error, commands.CommandOnCooldown) and ctx.command is not None:
            cog = getattr(ctx.command, "cog", None)
            if cog is not None and cog.has_error_handler():
                return

        # Ignore some common, harmless errors.
        ignored = (
            commands.CommandNotFound,
            commands.DisabledCommand,
        )
        if isinstance(error, ignored):
            return

        guild_id = ctx.guild.id if ctx.guild else None
        ephemeral = False

        # Permission denials get dedicated ephemeral localized replies
        # (bot-core delta) — no tracebacks surfaced, no DM path. The prefix
        # surface is inert (bot-core), but the contract holds if it fires.
        # MissingPermissions is a CheckFailure subclass — matched first.
        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = error_embed(
                t(guild_id, "common.error.missing_permissions_title"),
                t(guild_id, "common.error.missing_permissions_description", permissions=missing),
                guild_id=guild_id,
            )
            ephemeral = True
        elif isinstance(error, commands.CheckFailure):
            logger.warning(
                "Command check denied (guild=%s, command=%s)",
                guild_id,
                getattr(ctx.command, "qualified_name", None),
            )
            embed = error_embed(
                t(guild_id, "common.error.check_failure_title"),
                t(guild_id, "common.error.check_failure_description"),
                guild_id=guild_id,
            )
            ephemeral = True
        else:
            # Log first (spec logging-service): full exception + traceback must
            # be on record before any user-facing response is produced.
            logger.error(
                "Unhandled command error (guild=%s, command=%s)",
                guild_id,
                getattr(ctx.command, "qualified_name", None),
                exc_info=error,
            )
            # S3.6: record crash_report ONLY for unhandled exceptions (F4 scope)
            try:
                if self.db is not None:
                    svc = CrashReportService(self.db)
                    tb_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                    qname = getattr(ctx.command, "qualified_name", None)
                    await svc.record(
                        guild_id=str(guild_id) if guild_id is not None else None,
                        command=qname,
                        traceback_text=tb_text,
                    )
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook  # noqa: BLE001 -- crash reporting never breaks error handler
                logger.warning("Failed to record crash_report for command", exc_info=True)
            embed = error_embed(
                t(guild_id, "common.error.command_error_title"),
                str(error),
                guild_id=guild_id,
            )

        try:
            await ctx.send(embed=embed, ephemeral=ephemeral)
        except discord.HTTPException:
            logger.exception("Failed to send command error embed")

    # ==================================================================
    # Events
    # ==================================================================

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Insert default guild configuration when the bot joins a server."""
        if self.guild_service is not None:
            await self.guild_service.on_guild_join(str(guild.id))

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Evict ALL guild-scoped state when the bot leaves a server (S0.9/S0.10).

        Cache-layer spec: every ``{guild_id}:*`` TTLCache key is evicted in
        one pass (post-eviction reads miss → DB fallback), the mod-role RAM
        map entry is dropped, and greeting raid semaphores are released.
        Other guilds are untouched.
        """
        gid = str(guild.id)
        if self.cache is not None:
            self.cache.invalidate_guild(gid)
        self._guild_mod_role_cache.pop(guild.id, None)
        if self.greeting_service is not None:
            self.greeting_service.evict_guild_sync(gid)

    async def on_ready(self) -> None:
        """Called once when the bot has connected to the Discord gateway."""
        logger.info("NebulosaBot is online — logged in as %s", self.user)
        # Backfill guild config for guilds the bot was already a member of at
        # startup (on_guild_join only fires for joins during the session).
        if self.guild_service is not None:
            tasks: list[Coroutine[Any, Any, None]] = [
                self.guild_service.ensure_guild_exists(str(guild.id)) for guild in self.guilds
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
            except Exception:  # noqa: BLE001 -- best-effort retention/cron, never crash setup_hook
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
        if self.guild_service is None:
            msg = "GuildService not initialised"
            raise RuntimeError(msg)

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
                for child in component.children:  # ty: ignore[not-iterable]  # discord.py MessageComponent.children is Any at runtime; guarded by hasattr above
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
