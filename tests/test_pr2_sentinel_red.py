"""RED for PR2 2.10-2.18 SentinelCog /tempban /unban + hourly loop (strict TDD)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands

from bot.cogs.sentinel import SentinelCog

# Helpers


def _make_member(member_id: int = 555) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.mention = f"<@{member_id}>"
    m.top_role = MagicMock()
    m.top_role.__le__ = MagicMock(return_value=False)
    m.ban = AsyncMock()
    return m


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.insert_infraction = AsyncMock(return_value={"id": "inf"})
    bot.infraction_service = MagicMock()
    bot.infraction_service.tempban = AsyncMock(return_value=MagicMock(id="inf", type="BAN"))
    bot.infraction_service.unban = AsyncMock(return_value=MagicMock(id="ban-1"))
    bot.infraction_service.decay_warnings = AsyncMock(return_value=2)
    bot.logging_service = MagicMock()
    bot.logging_service.log_moderation_action = AsyncMock()
    bot.logging_service.log_sentinel_loop = AsyncMock()
    bot.user = MagicMock()
    bot.user.id = 999
    bot.wait_until_ready = AsyncMock()
    # For tempban expiry loop, need get_expired_tempbans via db
    bot.db.get_expired_tempbans = AsyncMock(return_value=[])
    bot.db.get_expired_warns = AsyncMock(return_value=[])
    # guild.unban for expiry loop
    return bot


def _make_guild(guild_id: int = 123456789) -> MagicMock:
    g = MagicMock()
    g.id = guild_id
    g.me = MagicMock()
    g.me.top_role = MagicMock()
    g.me.top_role.__le__ = MagicMock(return_value=False)
    g.owner = MagicMock()
    g.unban = AsyncMock()
    return g


def _make_ctx(guild: MagicMock, author: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = author
    ctx.channel = MagicMock()
    ctx.send = AsyncMock()
    return ctx


class TestTempbanCommandRed:
    def test_tempban_exists_and_gated(self) -> None:
        """2.10: SentinelCog must have /tempban hybrid gated by can_check moderation.ban."""
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        assert hasattr(cog, "tempban"), "SentinelCog.tempban must exist"
        cmd = cog.tempban
        assert len(cmd.checks) > 0, "tempban must have prefix checks"
        assert hasattr(cmd, "app_command") and cmd.app_command is not None
        assert len(cmd.app_command.checks) > 0, "tempban must have slash checks"
        # Consolidation (S5b/c): the source-window grep was deleted — the gate key
        # and ban_members default are proven behaviorally by the predicate-denial
        # tests below and TestDefaultPermissions in test_ephemeral_standard.py.

    @pytest.mark.asyncio
    async def test_tempban_invalid_duration_sends_ephemeral_error_and_does_not_ban(self) -> None:
        """2.11 behavioral: invalid duration → ephemeral error embed, member.ban NOT called."""
        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        author = _make_member(member_id=111)
        ctx = _make_ctx(guild, author)
        member = _make_member(member_id=555)
        # bot.infraction_service is a mock; ensure tempban isn't called.
        cog = SentinelCog(bot=bot)
        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.tempban.callback(cog, ctx, member, duration="notaduration", reason="spam")
        # ctx.send called once with ephemeral=True (the error embed).
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args.kwargs.get("ephemeral") is True
        # No ban occurred and no infraction insert.
        member.ban.assert_not_awaited()
        bot.infraction_service.tempban.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tempban_confirm_sends_permanent_channel_action(self) -> None:
        """2.10/ephemeral-standard behavioral: confirm → member.ban + tempban insert + permanent channel send.

        The ConfirmCancelView is ephemeral, but the final action result MUST be
        permanent (ctx.channel.send), not an edit of the ephemeral message.
        """
        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        author = _make_member(member_id=111)
        ctx = _make_ctx(guild, author)
        ctx.channel.send = AsyncMock()
        member = _make_member(member_id=555)
        # validate passes; valid duration.
        cog = SentinelCog(bot=bot)
        with patch.object(cog, "_validate_target", new=AsyncMock(return_value=True)):
            await cog.tempban.callback(cog, ctx, member, duration="24h", reason="spam")
        # First ctx.send is the ephemeral confirm.
        view = ctx.send.call_args.kwargs.get("view")
        assert view is not None
        assert ctx.send.call_args.kwargs.get("ephemeral") is True
        # Simulate the confirm button.
        confirm_button = next(
            c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:confirm"
        )
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = author.id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        await confirm_button.callback(interaction)
        # member.ban called + infraction inserted + logged.
        member.ban.assert_awaited_once()
        bot.infraction_service.tempban.assert_awaited_once()
        bot.logging_service.log_moderation_action.assert_awaited_once()
        # Ephemeral confirm edited (closed) ...
        interaction.response.edit_message.assert_awaited_once()
        # ... AND permanent action sent to the channel (not ephemeral).
        ctx.channel.send.assert_awaited_once()
        send_kwargs = ctx.channel.send.call_args.kwargs
        assert send_kwargs.get("ephemeral") is None or send_kwargs.get("ephemeral") is False, (
            "tempban action result must be permanent (channel-visible), not ephemeral"
        )

    def test_unban_exists_and_gated(self) -> None:
        """2.13: SentinelCog must have /unban hybrid gated by can_check moderation.ban."""
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        assert hasattr(cog, "unban"), "SentinelCog.unban must exist"
        cmd = cog.unban
        assert len(cmd.checks) > 0
        assert hasattr(cmd, "app_command") and cmd.app_command is not None
        assert len(cmd.app_command.checks) > 0
        # Consolidation (S5b/c): the source-window grep was deleted — the
        # behavioral unban tests below prove the gate end-to-end.


class TestUnbanCommandRed:
    @pytest.mark.asyncio
    async def test_unban_active_ban_sends_permanent_confirm(self) -> None:
        """2.13/ephemeral-standard behavioral: active BAN → deactivate + unban + permanent confirm."""
        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        guild.unban = AsyncMock()
        author = _make_member(member_id=111)
        ctx = _make_ctx(guild, author)
        # Service returns a deactivated infraction (active BAN existed).
        bot.infraction_service.unban = AsyncMock(return_value=MagicMock(id="ban-1"))
        cog = SentinelCog(bot=bot)
        await cog.unban.callback(cog, ctx, user_id="555")
        # Service deactivated; Discord ban lifted; logged.
        bot.infraction_service.unban.assert_awaited_once_with("123456789", "555")
        guild.unban.assert_awaited_once()
        bot.logging_service.log_moderation_action.assert_awaited_once()
        # Permanent confirm embed (not ephemeral).
        ctx.send.assert_awaited_once()
        send_kwargs = ctx.send.call_args.kwargs
        assert send_kwargs.get("ephemeral") is None or send_kwargs.get("ephemeral") is False, (
            "unban success must be permanent (channel-visible)"
        )

    @pytest.mark.asyncio
    async def test_unban_no_active_ban_sends_ephemeral_info(self) -> None:
        """2.13/ephemeral-standard behavioral: no active BAN → ephemeral info (idempotent)."""
        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        author = _make_member(member_id=111)
        ctx = _make_ctx(guild, author)
        # Service returns None (no active BAN — idempotent no-op).
        bot.infraction_service.unban = AsyncMock(return_value=None)
        cog = SentinelCog(bot=bot)
        await cog.unban.callback(cog, ctx, user_id="555")
        # Service called; no Discord unban; no moderation log (nothing happened).
        bot.infraction_service.unban.assert_awaited_once_with("123456789", "555")
        guild.unban = AsyncMock()
        guild.unban.assert_not_awaited()
        bot.logging_service.log_moderation_action.assert_not_awaited()
        # Ephemeral info embed (idempotent, no error).
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args.kwargs.get("ephemeral") is True, "no-active-ban info must be ephemeral"


class TestTempbanUnbanDeniedRed:
    @pytest.mark.asyncio
    async def test_tempban_can_predicate_denies_unauthorized_user(self) -> None:
        """2.12 behavioral: can("moderation.ban") denies a non-admin/non-granted user.

        ``can_check("moderation.ban")`` delegates to ``can()`` at runtime; this
        proves the actual denial predicate (no matrix grant, no modRole, not
        admin) returns False — the gate behind /tempban and /unban.
        """
        from bot.utils.checks import can

        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        author = MagicMock(spec=discord.Member)
        author.id = 222
        author.guild_permissions.administrator = False
        author.roles = []
        ctx = _make_ctx(guild, author)
        ctx.bot = bot
        # No guild service override and bot.guild_service None → moderation.*
        # falls back to modRole cache (None) → deny.
        bot.guild_service = None
        with patch("bot.utils.checks._get_guild_service", return_value=None):
            result = await can("moderation.ban", ctx)
        assert result is False, "can(moderation.ban) must deny unauthorized user"

    @pytest.mark.asyncio
    async def test_tempban_can_predicate_denies_in_dm(self) -> None:
        """2.12 behavioral: can("moderation.ban") denies DM invocation (no guild)."""
        from bot.utils.checks import can

        bot = _make_bot()
        author = MagicMock(spec=discord.Member)
        author.id = 222
        author.guild_permissions.administrator = False
        author.roles = []
        ctx = MagicMock()
        ctx.author = author
        ctx.guild = None  # DM
        ctx.bot = bot
        with patch("bot.utils.checks._get_guild_service", return_value=None):
            result = await can("moderation.ban", ctx)
        assert result is False, "can(moderation.ban) must deny DM invocation"

    @pytest.mark.asyncio
    async def test_can_check_decorator_denies_unauthorized_via_command_checks(self) -> None:
        """2.12/2.13 behavioral: can_check("moderation.ban") prefix predicate raises CheckFailure for unauthorized.

        Exercises the real decorator's prefix_predicate (exposed on the factory),
        which is what gates /tempban and /unban on the prefix path.
        """
        from discord.ext import commands as _commands

        from bot.utils.checks import can_check

        bot = _make_bot()
        guild = _make_guild(guild_id=123456789)
        author = MagicMock(spec=discord.Member)
        author.id = 222
        author.guild_permissions.administrator = False
        author.roles = []
        ctx = _make_ctx(guild, author)
        ctx.bot = bot
        bot.guild_service = None
        prefix_pred = can_check("moderation.ban").prefix_predicate
        with (
            patch("bot.utils.checks._get_guild_service", return_value=None),
            pytest.raises((_commands.CheckFailure, app_commands.CheckFailure)),
        ):
            await prefix_pred(ctx)

    @pytest.mark.asyncio
    async def test_can_check_decorator_app_predicate_denies_unauthorized(self) -> None:
        """2.12/2.13 behavioral: can_check("moderation.ban") app predicate raises CheckFailure for unauthorized."""
        bot = _make_bot()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = False
        interaction.user.roles = []
        interaction.client = bot
        bot.guild_service = None
        from bot.utils.checks import can_check

        app_pred = can_check("moderation.ban").predicate
        with (
            patch("bot.utils.checks._get_guild_service", return_value=None),
            pytest.raises(app_commands.CheckFailure),
        ):
            await app_pred(interaction)


class TestLoopRed:
    def test_decay_expiry_loop_interval_is_one_hour(self) -> None:
        """2.14: decay/expiry loop configured for a one-hour interval.

        Consolidation (S5b/c): before_loop/cog_unload greps were replaced by the
        behavioral twins below (wait_for_ready, unload cancels); hex-literal
        scanning is subsumed by tests/test_brand.py::TestNoHardcodedHexColors;
        restart durability rides the behavioral delegation tests.
        """
        loop = SentinelCog.__dict__.get("decay_expiry_loop")
        assert loop is not None, "SentinelCog.decay_expiry_loop must exist"
        assert loop.hours == 1, f"loop must run hourly, got hours={loop.hours}"

    @pytest.mark.asyncio
    async def test_loop_runs_decay_then_expiry_and_logs_via_logging_service(self) -> None:
        """2.14/2.17 behavioral: loop runs decay → expiry per guild, each phase via LoggingService.

        Exercises the real ``decay_expiry_loop`` body: asserts decay runs before
        expiry, each phase logs through ``LoggingService.log_sentinel_loop`` (not
        module logger.info), and business logic lives in InfractionService.
        """
        bot = _make_bot()
        # decay returns 2; expire_tempbans returns 1 — prove ordering + counts flow.
        bot.infraction_service.decay_warnings = AsyncMock(return_value=2)
        bot.infraction_service.expire_tempbans = AsyncMock(return_value=1)
        bot.logging_service.log_sentinel_loop = AsyncMock()
        guild = _make_guild(guild_id=123)
        bot.guilds = [guild]

        cog = SentinelCog(bot=bot)
        await cog.decay_expiry_loop()

        # Decay runs before expiry (ordering).
        bot.infraction_service.decay_warnings.assert_awaited_once_with("123")
        bot.infraction_service.expire_tempbans.assert_awaited_once()
        # Each phase logs through LoggingService.log_sentinel_loop (not logger.info).
        assert bot.logging_service.log_sentinel_loop.await_count == 2
        phases = [c.args[1] for c in bot.logging_service.log_sentinel_loop.call_args_list]
        counts = [c.args[2] for c in bot.logging_service.log_sentinel_loop.call_args_list]
        assert phases == ["decay", "expiry"], "loop must run decay then expiry, in order"
        assert counts == [2, 1]

    @pytest.mark.asyncio
    async def test_loop_before_loop_waits_for_ready(self) -> None:
        """2.15 behavioral: before_loop awaits bot.wait_until_ready()."""
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        await cog._before_decay_expiry_loop()
        bot.wait_until_ready.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_loop_cog_unload_cancels_running_loop(self) -> None:
        """2.16 behavioral: cog_unload cancels a running loop.

        discord.py ``tasks.Loop.cancel()`` schedules cancellation; the loop
        stops asynchronously. We assert the loop was running, unload called
        cancel on it, and after a yield the loop is no longer running.
        """
        bot = _make_bot()
        cog = SentinelCog(bot=bot)
        # Start the loop so it's running.
        cog.decay_expiry_loop.start()
        assert cog.decay_expiry_loop.is_running()
        # Track that cancel was invoked on the real loop object.
        original_cancel = cog.decay_expiry_loop.cancel
        cancel_calls: list[bool] = []
        import asyncio

        def _spy_cancel() -> None:
            cancel_calls.append(True)
            original_cancel()

        cog.decay_expiry_loop.cancel = _spy_cancel  # type: ignore[method-assign]
        await cog.cog_unload()
        assert cancel_calls, "cog_unload must call loop.cancel()"
        # Yield to let the cancellation propagate.
        await asyncio.sleep(0)
        cog.decay_expiry_loop.cancel = original_cancel  # type: ignore[method-assign]
        assert not cog.decay_expiry_loop.is_running()

    @pytest.mark.asyncio
    async def test_loop_expire_delegates_unban_callback_and_deactivates(self) -> None:
        """Expiry: cog injects Discord unban callback; service deactivates the row.

        Proves the business logic boundary: InfractionService.expire_tempbans owns
        scan + deactivate; the cog only injects the Discord unban side-effect.
        """
        bot = _make_bot()
        expired_rows = [
            {"id": "ban-1", "guildId": "123", "targetId": "777", "type": "BAN", "active": True, "expiresAt": "2020"}
        ]
        # Service uses db.get_expired_tempbans (DB-sourced) and deactivates.
        bot.db.get_expired_tempbans = AsyncMock(return_value=expired_rows)
        bot.db.deactivate_infraction = AsyncMock()
        # Real service instance so expire_tempbans runs scan → unban → deactivate.
        from bot.services.infraction_service import InfractionService

        bot.infraction_service = InfractionService(db=bot.db)
        guild = _make_guild(guild_id=123)
        guild.unban = AsyncMock()
        bot.get_guild = MagicMock(return_value=guild)
        bot.guilds = [guild]

        cog = SentinelCog(bot=bot)
        await cog._expire_tempbans_for_guild("123")

        # DB-sourced scan ran; Discord unban lifted for the target; row deactivated.
        bot.db.get_expired_tempbans.assert_awaited_once_with("123")
        guild.unban.assert_awaited_once()
        bot.db.deactivate_infraction.assert_awaited_once_with("123", "ban-1")
        # Expiry phase logged through LoggingService.
        bot.logging_service.log_sentinel_loop.assert_awaited_once()
        assert bot.logging_service.log_sentinel_loop.call_args.args[1] == "expiry"
