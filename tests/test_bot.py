"""Unit tests for NebulosaBot.on_app_command_error dispatch.

Guards the V3 fix: per-cog override detection must use the canonical
discord.py predicate (``Cog.has_app_command_error_handler``) rather than
a broken ``is not None`` check on a bound coroutine method — any bound
method on any Cog instance is never ``None``, so the old check always
bailed out and silently suppressed the global error embed for every
unhandled slash-command error.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.cache import TTLCache
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
# Webhook lifecycle wiring — cache-sync-webhook spec: Server lifecycle
# ---------------------------------------------------------------------------


def _webhook_config() -> BotConfig:
    """BotConfig with the webhook enabled (secret + non-default host/port)."""
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
        webhook_secret="webhook-secret",
        webhook_host="0.0.0.0",
        webhook_port=9090,
    )


def _make_bot(config: BotConfig | None = None) -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    return NebulosaBot(config=config or _webhook_config(), intents=discord.Intents.default())


class TestStartWebhook:
    """_start_webhook — extracted webhook-startup unit (behavioural, low-mock)."""

    @pytest.mark.asyncio
    async def test_calls_start_webhook_server_with_config_and_stores_runner(self) -> None:
        """Spec: server starts on connect — _start_webhook invokes the server
        factory with (host, port, cache, secret) and stores the returned runner."""
        self_obj = SimpleNamespace(
            config=_webhook_config(),
            cache=TTLCache(),
            _webhook_runner=None,
        )
        fake_runner = MagicMock()

        with patch("bot.bot.start_webhook_server", new=AsyncMock(return_value=fake_runner)) as mock_start:
            await NebulosaBot._start_webhook(self_obj)

        mock_start.assert_awaited_once_with(
            self_obj.config.webhook_host,
            self_obj.config.webhook_port,
            self_obj.cache,
            self_obj.config.webhook_secret,
        )
        assert self_obj._webhook_runner is fake_runner

    @pytest.mark.asyncio
    async def test_degraded_mode_stores_none_without_raising(self) -> None:
        """Spec: port conflict degraded mode — start returns None (port in use /
        no secret) and the bot MUST continue without raising."""
        self_obj = SimpleNamespace(
            config=_webhook_config(),
            cache=TTLCache(),
            _webhook_runner="stale",
        )

        with patch("bot.bot.start_webhook_server", new=AsyncMock(return_value=None)):
            await NebulosaBot._start_webhook(self_obj)

        assert self_obj._webhook_runner is None

    @pytest.mark.asyncio
    async def test_skips_when_cache_not_initialized(self) -> None:
        """Defensive: if the cache isn't ready yet, the webhook MUST NOT start
        (no-op) rather than binding a server with nothing to invalidate."""
        self_obj = SimpleNamespace(
            config=_webhook_config(),
            cache=None,
            _webhook_runner=None,
        )

        with patch("bot.bot.start_webhook_server", new=AsyncMock()) as mock_start:
            await NebulosaBot._start_webhook(self_obj)

        mock_start.assert_not_awaited()
        assert self_obj._webhook_runner is None


class TestStopWebhook:
    """_stop_webhook — graceful, idempotent shutdown cleanup."""

    @pytest.mark.asyncio
    async def test_calls_stop_server_with_runner_and_clears(self) -> None:
        """Spec: close() cleans up — _stop_webhook delegates to stop_webhook_server
        with the stored runner and then clears the slot."""
        fake_runner = MagicMock()
        self_obj = SimpleNamespace(_webhook_runner=fake_runner)

        with patch("bot.bot.stop_webhook_server", new=AsyncMock()) as mock_stop:
            await NebulosaBot._stop_webhook(self_obj)

        mock_stop.assert_awaited_once_with(fake_runner)
        assert self_obj._webhook_runner is None

    @pytest.mark.asyncio
    async def test_safe_when_runner_is_none(self) -> None:
        """Degraded mode (runner is None) — stop MUST be a safe pass-through."""
        self_obj = SimpleNamespace(_webhook_runner=None)

        with patch("bot.bot.stop_webhook_server", new=AsyncMock()) as mock_stop:
            await NebulosaBot._stop_webhook(self_obj)

        mock_stop.assert_awaited_once_with(None)
        assert self_obj._webhook_runner is None


class TestCloseWebhookWiring:
    """close() — webhook server stopped BEFORE the Discord gateway closes."""

    @pytest.mark.asyncio
    async def test_stops_webhook_before_closing_gateway(self) -> None:
        """Spec: graceful shutdown stops the webhook runner, then closes the
        gateway — in that order."""
        bot = _make_bot()
        runner = MagicMock()
        bot._webhook_runner = runner
        order: list[str] = []

        async def fake_stop(_runner: object) -> None:
            order.append("stop")

        async def fake_super_close(*_args: object, **_kwargs: object) -> None:
            order.append("super_close")

        with (
            patch("bot.bot.stop_webhook_server", new=fake_stop),
            patch("discord.ext.commands.Bot.close", new=fake_super_close),
        ):
            await bot.close()

        assert order == ["stop", "super_close"]
        assert bot._webhook_runner is None


class TestSetupHookWebhookWiring:
    """setup_hook — starts the webhook server AFTER cache initialization."""

    @pytest.mark.asyncio
    async def test_starts_webhook_with_initialized_cache(self) -> None:
        """Spec: server starts on connect — setup_hook calls start_webhook_server
        with the cache it just initialised, and stores the runner."""
        bot = _make_bot()
        fake_runner = MagicMock()

        with (
            patch("bot.bot.start_webhook_server", new=AsyncMock(return_value=fake_runner)) as mock_start,
            patch("bot.bot.Database") as mock_db_cls,
            patch.object(bot, "load_extension", new=AsyncMock()),
            patch.object(bot.tree, "sync", new=AsyncMock()),
        ):
            mock_db_cls.return_value.connect = AsyncMock()
            await bot.setup_hook()

        mock_start.assert_awaited_once()
        args = mock_start.call_args.args
        assert args[0] == bot.config.webhook_host
        assert args[1] == bot.config.webhook_port
        assert args[2] is bot.cache  # cache initialised BEFORE webhook start
        assert args[3] == bot.config.webhook_secret
        assert bot._webhook_runner is fake_runner
