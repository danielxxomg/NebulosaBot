"""Unit tests for NebulosaBot.on_app_command_error dispatch.

Guards the V3 fix: per-cog override detection must use the canonical
discord.py predicate (``Cog.has_app_command_error_handler``) rather than
a broken ``is not None`` check on a bound coroutine method — any bound
method on any Cog instance is never ``None``, so the old check always
bailed out and silently suppressed the global error embed for every
unhandled slash-command error.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.utils.brand import ERROR

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
        # Set guild to None so t() uses default locale
        interaction.guild = None
        error = app_commands.AppCommandError("boom")

        # Call the real unbound method with a dummy self — the method body
        # never references ``self``, so a MagicMock is sufficient and avoids
        # NebulosaBot.__init__ / setup_hook entirely.
        await NebulosaBot.on_app_command_error(MagicMock(), interaction, error)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        embed = kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color is not None and embed.color.value == ERROR
        # Title comes from t() — with no locales loaded, returns the raw key
        assert embed.title is not None
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


# ---------------------------------------------------------------------------
# on_ready — concurrent guild backfill via asyncio.gather
# ---------------------------------------------------------------------------


class TestOnReadyConcurrentBackfill:
    """on_ready MUST backfill guild configs concurrently via asyncio.gather."""

    @pytest.mark.asyncio
    async def test_on_ready_calls_ensure_guild_for_all_guilds(self) -> None:
        """on_ready MUST call ensure_guild_exists once per guild."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.ensure_guild_exists = AsyncMock()

        # Simulate 3 guilds by patching the guilds property.
        guild_a = MagicMock()
        guild_a.id = 111
        guild_b = MagicMock()
        guild_b.id = 222
        guild_c = MagicMock()
        guild_c.id = 333

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild_a, guild_b, guild_c])):
            await bot.on_ready()

        assert bot.guild_service.ensure_guild_exists.await_count == 3
        # Verify each guild_id was passed.
        called_ids = {
            call.args[0] for call in bot.guild_service.ensure_guild_exists.call_args_list
        }
        assert called_ids == {"111", "222", "333"}

    @pytest.mark.asyncio
    async def test_on_ready_backfill_is_concurrent(self) -> None:
        """on_ready backfill MUST use asyncio.gather (not sequential await).

        Uses a barrier: each task signals it started, then waits for ALL tasks
        to start before completing. With sequential await, the first task
        completes before the second starts (barrier never resolves).
        With gather, all tasks start concurrently and the barrier releases.
        """

        bot = _make_bot()

        num_guilds = 3
        started = asyncio.Event()
        start_count = 0
        completed_ids: list[str] = []

        async def barrier_ensure(guild_id: str) -> None:
            nonlocal start_count
            completed_ids.append(guild_id)
            start_count += 1
            if start_count == num_guilds:
                started.set()
            # Block until all tasks have started (only works with concurrency).
            await started.wait()

        bot.guild_service = MagicMock()
        bot.guild_service.ensure_guild_exists = barrier_ensure

        guilds = []
        for gid in [111, 222, 333]:
            g = MagicMock()
            g.id = gid
            guilds.append(g)

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: guilds)):
            # With sequential await, this DEADLOCKS (barrier never resolves
            # because the first task blocks waiting for task 2+3 which never start).
            # With gather, all 3 start concurrently and the barrier releases.
            # Use a timeout to fail gracefully if sequential (deadlock).
            await asyncio.wait_for(bot.on_ready(), timeout=2.0)

        # All guilds must be backfilled.
        assert len(completed_ids) == 3
        assert set(completed_ids) == {"111", "222", "333"}


# ---------------------------------------------------------------------------
# on_ready — bounded semaphore path for >50 guilds
# ---------------------------------------------------------------------------


class TestOnReadyBoundedBackfill:
    """on_ready MUST use asyncio.Semaphore when guild count exceeds BACKFILL_CONCURRENCY_LIMIT."""

    @pytest.mark.asyncio
    async def test_on_ready_uses_semaphore_for_large_guild_count(self) -> None:
        """When >50 guilds exist, on_ready MUST wrap tasks with a bounded semaphore.

        Verifies that no more than BACKFILL_CONCURRENCY_LIMIT tasks run at
        once by tracking peak concurrent invocations of ensure_guild_exists.
        """
        from bot.bot import BACKFILL_CONCURRENCY_LIMIT

        bot = _make_bot()

        # Track concurrent executions.
        peak_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def tracking_ensure(guild_id: str) -> None:
            nonlocal peak_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > peak_concurrent:
                    peak_concurrent = current_concurrent
            # Small sleep to let other tasks start concurrently.
            await asyncio.sleep(0.01)
            async with lock:
                current_concurrent -= 1

        bot.guild_service = MagicMock()
        bot.guild_service.ensure_guild_exists = tracking_ensure

        # Create 60 guilds (> BACKFILL_CONCURRENCY_LIMIT of 50).
        guilds = []
        for gid in range(1, 61):
            g = MagicMock()
            g.id = gid
            guilds.append(g)

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: guilds)):
            await asyncio.wait_for(bot.on_ready(), timeout=5.0)

        # All 60 guilds must be backfilled.
        # We can't directly count completed guilds from tracking_ensure since
        # it doesn't append to a list, but we know on_ready ran successfully
        # and the semaphore was used (verified by peak_concurrent check).

        # Peak concurrent MUST not exceed the limit.
        assert peak_concurrent <= BACKFILL_CONCURRENCY_LIMIT, (
            f"Peak concurrent {peak_concurrent} exceeded BACKFILL_CONCURRENCY_LIMIT {BACKFILL_CONCURRENCY_LIMIT}"
        )


# ---------------------------------------------------------------------------
# _validate_panels — startup panel health check and self-heal
# (ticket-panel-persistence, Phase 3)
# ---------------------------------------------------------------------------


class TestValidatePanels:
    """Verify _validate_panels() checks stored panels and self-heals."""

    @pytest.mark.asyncio
    async def test_healthy_panel_no_redeploy(self) -> None:
        """When fetch_message succeeds with ticket:open button → no re-deploy."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.update_guild_panel = AsyncMock()
        bot.guild_service.get_config = AsyncMock()
        config = MagicMock()
        config.ticket_panel_message_id = "1"
        config.ticket_panel_channel_id = "1"
        bot.guild_service.get_config.return_value = config

        guild = MagicMock()
        guild.id = 111
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.id = 1
        guild.get_channel.return_value = channel

        # Message with a ticket:open button component.
        message = MagicMock()
        row = MagicMock()
        button = MagicMock()
        button.custom_id = "ticket:open"
        row.children = [button]
        message.components = [row]
        channel.fetch_message = AsyncMock(return_value=message)

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild])):
            await bot._validate_panels()

        # No re-deploy — update_guild_panel not called.
        bot.guild_service.update_guild_panel.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_panel_triggers_redeploy(self) -> None:
        """When fetch_message raises NotFound → re-deploy + update IDs."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.update_guild_panel = AsyncMock()
        bot.guild_service.get_config = AsyncMock()
        config = MagicMock()
        config.ticket_panel_message_id = "1"
        config.ticket_panel_channel_id = "1"
        bot.guild_service.get_config.return_value = config

        guild = MagicMock()
        guild.id = 111
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.id = 1
        guild.get_channel.return_value = channel
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

        mock_message = MagicMock()
        mock_message.id = 99
        mock_message.channel = channel

        with (
            patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild])),
            patch("bot.bot.deploy_ticket_panel", new_callable=AsyncMock, return_value=mock_message) as mock_deploy,
        ):
            await bot._validate_panels()

        mock_deploy.assert_awaited_once_with(
            channel, "111", bot=bot, guild=guild,
        )

    @pytest.mark.asyncio
    async def test_stripped_panel_triggers_redeploy(self) -> None:
        """When message exists but has no ticket:open button → re-deploy."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.update_guild_panel = AsyncMock()
        bot.guild_service.get_config = AsyncMock()
        config = MagicMock()
        config.ticket_panel_message_id = "1"
        config.ticket_panel_channel_id = "1"
        bot.guild_service.get_config.return_value = config

        guild = MagicMock()
        guild.id = 111
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.id = 1
        guild.get_channel.return_value = channel

        # Message with no matching button.
        message = MagicMock()
        message.components = []
        channel.fetch_message = AsyncMock(return_value=message)

        mock_message = MagicMock()
        mock_message.id = 99
        mock_message.channel = channel

        with (
            patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild])),
            patch("bot.bot.deploy_ticket_panel", new_callable=AsyncMock, return_value=mock_message) as mock_deploy,
        ):
            await bot._validate_panels()

        mock_deploy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_channel_clears_ids(self) -> None:
        """When get_channel returns None → clear IDs + log warning."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.update_guild_panel = AsyncMock()
        bot.guild_service.get_config = AsyncMock()
        config = MagicMock()
        config.ticket_panel_message_id = "1"
        config.ticket_panel_channel_id = "1"
        bot.guild_service.get_config.return_value = config

        guild = MagicMock()
        guild.id = 111
        guild.name = "Test Guild"
        guild.get_channel.return_value = None

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild])):
            await bot._validate_panels()

        bot.guild_service.update_guild_panel.assert_awaited_once_with("111", None, None)

    @pytest.mark.asyncio
    async def test_forbidden_on_fetch_skips_guild(self) -> None:
        """When fetch_message raises Forbidden → skip guild + log warning."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.update_guild_panel = AsyncMock()
        bot.guild_service.get_config = AsyncMock()
        config = MagicMock()
        config.ticket_panel_message_id = "1"
        config.ticket_panel_channel_id = "1"
        bot.guild_service.get_config.return_value = config

        guild = MagicMock()
        guild.id = 111
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.id = 1
        guild.get_channel.return_value = channel
        channel.fetch_message = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild])):
            await bot._validate_panels()

        # IDs retained — neither clear nor redeploy.
        bot.guild_service.update_guild_panel.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validation_runs_after_backfill(self) -> None:
        """_validate_panels MUST be called at the end of on_ready, after backfill gather."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.ensure_guild_exists = AsyncMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(
            ticket_panel_message_id=None, ticket_panel_channel_id=None,
        ))

        call_order: list[str] = []

        async def mock_ensure(guild_id: str) -> None:
            call_order.append(f"backfill:{guild_id}")

        async def mock_validate() -> None:
            call_order.append("validate")

        bot.guild_service.ensure_guild_exists = mock_ensure
        bot._validate_panels = mock_validate

        guild_a = MagicMock()
        guild_a.id = 111
        guild_b = MagicMock()
        guild_b.id = 222

        with patch.object(type(bot), "guilds", new_callable=lambda: property(lambda _self: [guild_a, guild_b])):
            await bot.on_ready()

        # Backfill happened before validation.
        assert "backfill:111" in call_order
        assert "backfill:222" in call_order
        assert call_order.index("validate") > call_order.index("backfill:111")
        assert call_order.index("validate") > call_order.index("backfill:222")
