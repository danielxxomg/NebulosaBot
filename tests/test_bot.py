"""Unit tests for NebulosaBot.on_app_command_error dispatch.

Guards the V3 fix: per-cog override detection must use the canonical
discord.py predicate (``Cog.has_app_command_error_handler``) rather than
a broken ``is not None`` check on a bound coroutine method — any bound
method on any Cog instance is never ``None``, so the old check always
bailed out and silently suppressed the global error embed for every
unhandled slash-command error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.utils.embeds import COLOR_ERROR

# ---------------------------------------------------------------------------
# Minimal Cog fixtures — override vs no-override
# ---------------------------------------------------------------------------


class _PlainCog(commands.Cog):
    """Cog that does NOT override cog_app_command_error."""

    pass


class _OverrideCog(commands.Cog):
    """Cog that DOES override cog_app_command_error with a no-op."""

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        return


# ---------------------------------------------------------------------------
# Interaction builder
# ---------------------------------------------------------------------------


def _build_interaction(cog: commands.Cog | None) -> MagicMock:
    """Build a mocked interaction whose ``command.cog`` is *cog*.

    ``response.is_done()`` returns ``False`` so the ``send_message``
    branch is the one exercised.
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.command = MagicMock(spec=app_commands.Command)
    interaction.command.cog = cog
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


class TestOnAppCommandErrorDispatch:
    """Verify global app-command error dispatch honours per-cog overrides."""

    @pytest.mark.asyncio
    async def test_global_handler_runs_when_cog_has_no_override(self) -> None:
        """PlainCog (no override) -> global handler sends the error embed."""
        cog = _PlainCog()
        interaction = _build_interaction(cog)
        error = app_commands.AppCommandError("boom")

        # Call the real unbound method with a dummy self — the method body
        # never references ``self``, so a MagicMock is sufficient and avoids
        # NebulosaBot.__init__ / setup_hook entirely.
        await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        embed = kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color is not None and embed.color.value == COLOR_ERROR
        assert embed.title == "Unexpected Error"
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_global_handler_skips_when_cog_overrides_app_error(self) -> None:
        """OverrideCog -> global handler bails; per-cog handler takes over."""
        cog = _OverrideCog()
        interaction = _build_interaction(cog)
        error = app_commands.AppCommandError("boom")

        await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Bot config + factory helpers
# ---------------------------------------------------------------------------


def _make_config() -> BotConfig:
    """Minimal BotConfig for tests (webhook fields removed in PR 2)."""
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )


def _make_bot(config: BotConfig | None = None) -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    return NebulosaBot(config=config or _make_config(), intents=discord.Intents.default())


# ---------------------------------------------------------------------------
# Realtime subscriber lifecycle wiring — cache-sync-realtime spec
# ---------------------------------------------------------------------------


class TestStartRealtimeSubscriber:
    """setup_hook — starts the Realtime subscriber AFTER cache initialization."""

    @pytest.mark.asyncio
    async def test_starts_subscriber_after_cache(self) -> None:
        """Spec: subscriber start() called after cache is initialized."""
        bot = _make_bot()
        with (
            patch("bot.bot.RealtimeCacheSubscriber") as mock_sub_cls,
            patch("bot.bot.Database") as mock_db_cls,
            patch.object(bot, "load_extension", new=AsyncMock()),
            patch.object(bot.tree, "sync", new=AsyncMock()),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            mock_sub_cls.return_value.start = AsyncMock()
            await bot.setup_hook()

        mock_sub_cls.assert_called_once()
        mock_sub_cls.return_value.start.assert_awaited_once()
        assert bot._realtime_subscriber is mock_sub_cls.return_value


class TestCloseRealtimeSubscriber:
    """close() — subscriber stopped BEFORE the Discord gateway closes."""

    @pytest.mark.asyncio
    async def test_stops_subscriber_before_closing_gateway(self) -> None:
        """Spec: graceful shutdown stops the subscriber, then closes gateway."""
        bot = _make_bot()
        order: list[str] = []

        async def fake_sub_stop() -> None:
            order.append("sub_stop")

        sub = MagicMock()
        sub.stop = fake_sub_stop
        bot._realtime_subscriber = sub

        async def fake_super_close(*_args: object, **_kwargs: object) -> None:
            order.append("super_close")

        with (
            patch("discord.ext.commands.Bot.close", new=fake_super_close),
        ):
            await bot.close()

        assert order == ["sub_stop", "super_close"]


# ---------------------------------------------------------------------------
# cache-sync-realtime PR 2 — webhook server surface MUST be removed
# ---------------------------------------------------------------------------


class TestNoWebhookServer:
    """cache-sync-realtime: setup_hook MUST NOT start an aiohttp webhook runner.

    The webhook server import, ``_webhook_runner`` slot, ``_start_webhook``/
    ``_stop_webhook`` methods, and the setup_hook/close calls were removed in
    PR 2 (replaced by the Realtime subscriber).  These guards prevent
    re-introduction of the inbound webhook capability.
    """

    def test_bot_module_does_not_import_webhook_server(self) -> None:
        """bot.bot MUST NOT import start_webhook_server / stop_webhook_server."""
        import bot.bot as bot_mod

        assert not hasattr(bot_mod, "start_webhook_server")
        assert not hasattr(bot_mod, "stop_webhook_server")

    def test_bot_has_no_webhook_runner_slot(self) -> None:
        """NebulosaBot.__slots__ MUST NOT carry _webhook_runner."""
        assert "_webhook_runner" not in NebulosaBot.__slots__

    def test_bot_has_no_webhook_lifecycle_methods(self) -> None:
        """NebulosaBot MUST NOT define _start_webhook / _stop_webhook."""
        assert not hasattr(NebulosaBot, "_start_webhook")
        assert not hasattr(NebulosaBot, "_stop_webhook")
