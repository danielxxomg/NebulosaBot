# ruff: noqa: S311
"""RED tests for NebulosaBot ROUND 5 — 2 GGA C blockers.

Strict TDD: these tests MUST FAIL before the fixes are applied, then pass.

Blocker 1 — SentinelCog.cog_load never starts decay_expiry_loop (dead code):
    The hourly decay+expiry loop is defined with before_loop and cog_unload
    cancellation, but NOTHING calls .start(). Tempban auto-expiry + 30d warn
    decay never run in production. Fix: add ``async def cog_load`` mirroring
    TicketsCog L78-95 guard style.

Blocker 2 — OcioCog.on_command_error listener is unscoped + duplicates feedback:
    The ``@commands.Cog.listener() on_command_error`` reacts to
    CommandOnCooldown from ANY command bot-wide. Combined with
    NebulosaBot.on_command_error (which does NOT defer to cog handlers),
    rapid /banana or /8ball produce duplicate user-facing messages. Fix:
    convert to ``cog_command_error`` (auto-scoped by discord.py to this cog's
    commands) and make the global prefix handler defer for CommandOnCooldown
    when the cog has an error handler (mirrors the app-command deferral at
    bot.py L386-389).
"""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.cogs.sentinel import SentinelCog
from bot.config import BotConfig

# ===========================================================================
# Helpers
# ===========================================================================


def _make_sentinel_bot() -> MagicMock:
    """Return a mock bot wired for SentinelCog instantiation."""
    bot = MagicMock()
    bot.db = MagicMock()
    bot.infraction_service = MagicMock()
    bot.logging_service = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 999
    bot.wait_until_ready = AsyncMock()
    bot.guilds = []
    return bot


def _make_bot_real() -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    config = BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )
    return NebulosaBot(config=config, intents=discord.Intents.default())


def _make_prefix_ctx(guild_id: int | None = 123456789) -> MagicMock:
    """Build a mock context for prefix command error tests.

    ``command.cog`` is set to ``None`` by default (no cog attached — accurate
    for commands that don't belong to a cog with an error handler).
    """
    ctx = MagicMock()
    ctx.command = MagicMock()
    # Must NOT have on_error — hasattr check in the global handler.
    del ctx.command.on_error
    ctx.command.cog = None
    ctx.guild = MagicMock() if guild_id else None
    if ctx.guild:
        ctx.guild.id = guild_id
    ctx.author = MagicMock()
    ctx.author.id = 111111111
    ctx.author.send = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


# ===========================================================================
# Blocker 1 — SentinelCog.cog_load starts decay_expiry_loop
# ===========================================================================


class TestSentinelCogLoadRed:
    """Blocker 1 — cog_load must start the hourly decay+expiry loop."""

    @pytest.mark.asyncio
    async def test_cog_load_starts_decay_expiry_loop(self) -> None:
        """Behavioral: cog_load calls decay_expiry_loop.start() when not running.

        Mirrors TicketsCog.cog_load L78-95 guard pattern: check is_running()
        before calling start(). Without cog_load the loop is dead code —
        tempban auto-expiry + 30d warn decay never run in production.
        """
        bot = _make_sentinel_bot()
        cog = SentinelCog(bot=bot)

        # Replace the real Loop with a mock to observe .start().
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_loop.start = MagicMock()
        cog.decay_expiry_loop = mock_loop

        await cog.cog_load()

        mock_loop.is_running.assert_called_once()
        mock_loop.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_load_skips_start_if_loop_already_running(self) -> None:
        """Idempotency: cog_load does NOT call start() when already running.

        Matches TicketsCog guard: ``if not self.<loop>.is_running(): .start()``.
        """
        bot = _make_sentinel_bot()
        cog = SentinelCog(bot=bot)

        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_loop.start = MagicMock()
        cog.decay_expiry_loop = mock_loop

        await cog.cog_load()

        mock_loop.start.assert_not_called()

    def test_source_contains_cog_load_with_start_call(self) -> None:
        """Structural guard: sentinel.py source contains cog_load starting the loop.

        Comment-aware like prior structural guards — checks the literal
        ``decay_expiry_loop.start()`` appears inside a ``cog_load`` method.
        """
        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "async def cog_load" in src, "SentinelCog MUST define async def cog_load"
        assert "decay_expiry_loop.start()" in src, (
            "cog_load MUST call decay_expiry_loop.start() — feature is dead code without it"
        )


# ===========================================================================
# Blocker 2 — OcioCog cog_command_error (scoped) + bot deferral
# ===========================================================================


class TestOcioCogCommandErrorRed:
    """Blocker 2 — convert unscoped on_command_error listener to cog_command_error."""

    @pytest.mark.asyncio
    async def test_cog_command_error_handles_cooldown_ephemeral(self) -> None:
        """Behavioral: cog_command_error turns CommandOnCooldown into ephemeral embed.

        ``cog_command_error`` is a discord.py special method auto-scoped to
        the cog's own commands — unlike ``@Cog.listener() on_command_error``
        which fires for ANY command bot-wide. Preserves the same cooldown-embed
        logic (ephemeral=True, localized retry_after).
        """
        from bot.cogs.ocio import OcioCog

        cog = OcioCog(MagicMock())
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock()
        ctx.guild.id = 999
        ctx.send = AsyncMock()

        err = commands.CommandOnCooldown(commands.Cooldown(1, 5.0), 3.5, commands.BucketType.user)
        await cog.cog_command_error(ctx, err)

        ctx.send.assert_awaited_once()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True, "cooldown embed MUST be ephemeral"
        assert kwargs.get("embed") is not None, "cooldown embed MUST be present"

    def test_source_has_cog_command_error_no_listener(self) -> None:
        """Structural: ocio.py uses cog_command_error, NOT @Cog.listener on_command_error.

        The old ``@commands.Cog.listener() async def on_command_error`` was
        unscoped — it reacted to CommandOnCooldown from ANY command bot-wide.
        ``cog_command_error`` is auto-scoped by discord.py to this cog's commands.
        """
        src = pathlib.Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        assert "async def cog_command_error" in src, "OcioCog MUST define cog_command_error (auto-scoped by discord.py)"
        assert "async def on_command_error" not in src, (
            "OcioCog MUST NOT have on_command_error listener — it is unscoped and "
            "fires for ANY command bot-wide, duplicating cooldown feedback"
        )


class TestBotOnCommandErrorDeferRed:
    """Blocker 2 (cont.) — global prefix handler defers to cog error handlers.

    discord.py ``dispatch_error`` runs ``cog_command_error`` FIRST, then ALWAYS
    dispatches the ``command_error`` event (core.py L685) — which fires the
    bot's global ``on_command_error``. Without a deferral check, the user gets
    TWO messages: the cog's cooldown embed AND the bot's DM. This mirrors the
    existing app-command deferral at bot.py L386-389
    (``cog.has_app_command_error_handler()``).
    """

    @pytest.mark.asyncio
    async def test_defers_to_cog_error_handler_for_cooldown(self) -> None:
        """CommandOnCooldown from a cog with an error handler → bot MUST defer.

        Without deferral, the bot sends a DM on top of the cog's cooldown embed
        — duplicate user-facing messages on rapid /banana or /8ball.
        """
        bot = _make_bot_real()
        ctx = _make_prefix_ctx()
        # Attach a cog with an error handler (like OcioCog.cog_command_error).
        ctx.command.cog = MagicMock()
        ctx.command.cog.has_error_handler.return_value = True

        error = commands.CommandOnCooldown(commands.Cooldown(1, 5.0), 3.5, commands.BucketType.user)
        await bot.on_command_error(ctx, error)

        # Bot MUST defer — no DM, no channel send.
        ctx.author.send.assert_not_awaited()
        ctx.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_still_handles_non_cooldown_with_cog_handler(self) -> None:
        """Non-cooldown errors MUST still be handled globally even when cog has handler.

        The deferral is scoped to CommandOnCooldown (the only error OcioCog
        handles). Other errors (CommandInvokeError, etc.) MUST still flow
        through the global handler so the user gets a message — no silent
        swallowing (AGENTS.md: all commands MUST handle errors gracefully).
        """
        bot = _make_bot_real()
        ctx = _make_prefix_ctx()
        ctx.command.cog = MagicMock()
        ctx.command.cog.has_error_handler.return_value = True

        error = commands.CommandError("something broke")
        await bot.on_command_error(ctx, error)

        # Non-cooldown error MUST still be handled (DM sent).
        ctx.author.send.assert_awaited_once()
