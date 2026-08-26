"""Global error handler — CheckFailure/MissingPermissions branches (S0.5/S0.6).

bot-core delta (clean-1.0): permission denials MUST produce an ephemeral,
localized reply naming the missing permission when applicable — they MUST
NOT surface as unhandled errors and MUST NOT show tracebacks to the user.
Applies to BOTH the app-command handler and the (inert) prefix handler;
the no-DM guarantee and interaction-guild resolution still hold.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.app_commands import errors as app_errors
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.i18n import load_locales, set_guild_language, t

load_locales()

_GID_ES = 888001
_GID_EN = 888002


def _make_bot() -> NebulosaBot:
    config = BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )
    return NebulosaBot(config=config, intents=discord.Intents.default())


def _make_interaction(guild_id: int) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.command = None
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild_id = guild_id
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_ctx(guild_id: int) -> MagicMock:
    ctx = MagicMock()
    ctx.command = MagicMock()
    del ctx.command.on_error  # hasattr check in the global handler
    ctx.command.cog = None
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    ctx.author = MagicMock()
    ctx.author.send = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


# ===========================================================================
# App-command handler branches
# ===========================================================================


class TestAppCommandCheckFailureBranch:
    @pytest.mark.asyncio
    async def test_check_failure_gets_ephemeral_localized_denial(self) -> None:
        """CheckFailure → ephemeral localized denial; no traceback text."""
        set_guild_language(str(_GID_ES), "es")
        bot = _make_bot()
        interaction = _make_interaction(_GID_ES)

        await bot.on_app_command_error(interaction, app_errors.CheckFailure())

        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        expected = t(str(_GID_ES), "common.error.check_failure_title")
        assert embed.title == expected and expected != "common.error.check_failure_title"
        assert "CheckFailure" not in (embed.description or "")
        assert "Traceback" not in (embed.description or "")

    @pytest.mark.asyncio
    async def test_check_failure_localized_in_english(self) -> None:
        set_guild_language(str(_GID_EN), "en")
        bot = _make_bot()
        interaction = _make_interaction(_GID_EN)

        await bot.on_app_command_error(interaction, app_errors.CheckFailure())

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert embed.title == t(str(_GID_EN), "common.error.check_failure_title")


class TestAppCommandMissingPermissionsBranch:
    @pytest.mark.asyncio
    async def test_missing_permissions_named_ephemerally(self) -> None:
        """MissingPermissions → ephemeral reply NAMES the missing permission."""
        set_guild_language(str(_GID_ES), "es")
        bot = _make_bot()
        interaction = _make_interaction(_GID_ES)

        error = app_errors.MissingPermissions(missing_permissions=["Ban Members"])
        await bot.on_app_command_error(interaction, error)

        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        assert "Ban Members" in (embed.description or ""), (
            f"reply MUST name the missing permission; got {embed.description!r}"
        )

    @pytest.mark.asyncio
    async def test_missing_permissions_multiple_names_joined(self) -> None:
        set_guild_language(str(_GID_EN), "en")
        bot = _make_bot()
        interaction = _make_interaction(_GID_EN)

        error = app_errors.MissingPermissions(missing_permissions=["Manage Roles", "Kick Members"])
        await bot.on_app_command_error(interaction, error)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        description = embed.description or ""
        assert "Manage Roles" in description and "Kick Members" in description


# ===========================================================================
# Prefix handler branches (prefix surface inert — contract kept anyway)
# ===========================================================================


class TestPrefixHandlerBranches:
    @pytest.mark.asyncio
    async def test_check_failure_ephemeral_no_dm(self) -> None:
        set_guild_language(str(_GID_ES), "es")
        bot = _make_bot()
        ctx = _make_ctx(_GID_ES)

        await bot.on_command_error(ctx, commands.CheckFailure())  # ty: ignore[invalid-argument-type]

        ctx.author.send.assert_not_awaited()  # no DM-first branch
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        assert embed.title == t(str(_GID_ES), "common.error.check_failure_title")

    @pytest.mark.asyncio
    async def test_missing_permissions_names_permission(self) -> None:
        set_guild_language(str(_GID_EN), "en")
        bot = _make_bot()
        ctx = _make_ctx(_GID_EN)

        await bot.on_command_error(
            ctx,
            commands.MissingPermissions(missing_permissions=["Manage Messages"]),  # ty: ignore[invalid-argument-type]
        )

        ctx.author.send.assert_not_awaited()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        assert "Manage Messages" in (embed.description or "")


# ===========================================================================
# Regression guards — unexpected errors keep their path
# ===========================================================================


class TestUnexpectedStillHandled:
    @pytest.mark.asyncio
    async def test_generic_error_still_uses_unexpected_embed(self) -> None:
        set_guild_language(str(_GID_ES), "es")
        bot = _make_bot()
        interaction = _make_interaction(_GID_ES)

        await bot.on_app_command_error(interaction, app_errors.AppCommandError("boom"))

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert embed.title == t(str(_GID_ES), "common.error.unexpected_title")

    @pytest.mark.asyncio
    async def test_check_failure_branches_do_not_log_full_traceback_as_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        set_guild_language(str(_GID_ES), "es")
        bot = _make_bot()
        interaction = _make_interaction(_GID_ES)

        with caplog.at_level(logging.ERROR, logger="bot"):
            await bot.on_app_command_error(interaction, app_errors.CheckFailure())

        denial_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not any("NoneType" in r.getMessage() or "CheckFailure" in r.getMessage() for r in denial_logs)
