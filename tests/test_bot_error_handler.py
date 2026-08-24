"""Global error handler: channel-direct delivery, no DM-first branch.

bot-core spec (cycle-5-quality-zero delta):
    - No DM-first branch in prefix handler path -> ``on_command_error``
      MUST NOT attempt DM delivery; the embed goes directly to the channel
      where the command was invoked.
    - Unexpected error shows guild language (ES/EN) -> the app-command
      handler resolves title/message via ``t()`` with the guild's language.
    - Guild resolved from interaction -> ``guild_id`` comes from the
      interaction, not any ambient state.
    - Slash command error -> ephemeral embed to the invoking user.

The silent-ignore tuple ``(CommandNotFound, DisabledCommand)`` and both
deferral guards (local ``on_error`` handlers, scoped ``CommandOnCooldown``
cog deferral) are KEPT by design decision D2.

Strict TDD: RED phase — written BEFORE the handler simplification.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.i18n import load_locales, set_guild_language

# Real locale data so t() assertions exercise actual translations.
load_locales()


def _make_bot() -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    config = BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )
    return NebulosaBot(config=config, intents=discord.Intents.default())


def _make_ctx(guild_id: int | None = 314159265) -> MagicMock:
    """Build a mock prefix-command context with DM and channel send spies."""
    ctx = MagicMock()
    ctx.command = MagicMock()
    # Must NOT have on_error — hasattr check in the global handler.
    del ctx.command.on_error
    ctx.command.cog = None
    ctx.guild = MagicMock(spec=discord.Guild) if guild_id is not None else None
    if ctx.guild is not None:
        ctx.guild.id = guild_id
    ctx.author = MagicMock()
    ctx.author.id = 111222333
    ctx.author.send = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


# ===========================================================================
# No DM-first branch — channel-direct delivery
# ===========================================================================


class TestNoDmFirstBranch:
    """on_command_error MUST deliver to the channel and NEVER attempt a DM."""

    @pytest.mark.asyncio
    async def test_guild_error_sends_channel_embed_without_dm(self) -> None:
        """Guild-channel error → single channel embed, zero DM attempts."""
        bot = _make_bot()
        ctx = _make_ctx()

        await bot.on_command_error(ctx, commands.CommandError("boom"))

        # The handler defines no DM path (bot-core spec).
        ctx.author.send.assert_not_awaited()
        ctx.send.assert_awaited_once()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("embed") is not None, "channel delivery MUST carry an embed"

    @pytest.mark.asyncio
    async def test_channel_embed_is_localized(self) -> None:
        """Channel embed title comes from t() in the guild's language."""
        set_guild_language("314159265", "es")
        bot = _make_bot()
        ctx = _make_ctx(314159265)

        await bot.on_command_error(ctx, commands.CommandError("kaputt"))

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None and embed.title == "Error de Comando"

    @pytest.mark.asyncio
    async def test_no_dm_attempt_even_if_author_dms_blocked(self) -> None:
        """DMs-blocked authors change nothing — no send call is ever made."""
        bot = _make_bot()
        ctx = _make_ctx()
        ctx.author.send = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "DMs disabled"),
        )

        await bot.on_command_error(ctx, commands.CommandError("boom"))

        ctx.author.send.assert_not_awaited()
        ctx.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dm_context_sends_directly(self) -> None:
        """No-guild context → direct ctx.send, still zero author.send calls."""
        bot = _make_bot()
        ctx = _make_ctx(guild_id=None)

        await bot.on_command_error(ctx, commands.CommandError("boom"))

        ctx.send.assert_awaited_once()
        ctx.author.send.assert_not_awaited()


class TestSilentIgnoresKept:
    """Design D2: the silent-ignore tuple survives the simplification."""

    @pytest.mark.asyncio
    async def test_command_not_found_is_silent(self) -> None:
        bot = _make_bot()
        ctx = _make_ctx()

        await bot.on_command_error(ctx, commands.CommandNotFound("nope"))

        ctx.send.assert_not_awaited()
        ctx.author.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_command_is_silent(self) -> None:
        bot = _make_bot()
        ctx = _make_ctx()

        await bot.on_command_error(ctx, commands.DisabledCommand("off"))

        ctx.send.assert_not_awaited()
        ctx.author.send.assert_not_awaited()


class TestCooldownDeferralKept:
    """Design D2: the CommandOnCooldown cog-deferral guard survives."""

    @pytest.mark.asyncio
    async def test_cooldown_defers_to_cog_error_handler(self) -> None:
        bot = _make_bot()
        ctx = _make_ctx()
        ctx.command.cog = MagicMock()
        ctx.command.cog.has_error_handler.return_value = True

        err = commands.CommandOnCooldown(commands.Cooldown(1, 5.0), 3.5, commands.BucketType.user)
        await bot.on_command_error(ctx, err)

        ctx.send.assert_not_awaited()
        ctx.author.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_cooldown_still_handled_despite_cog_handler(self) -> None:
        bot = _make_bot()
        ctx = _make_ctx()
        ctx.command.cog = MagicMock()
        ctx.command.cog.has_error_handler.return_value = True

        await bot.on_command_error(ctx, commands.CommandError("boom"))

        ctx.send.assert_awaited_once()
        ctx.author.send.assert_not_awaited()


# ===========================================================================
# App-command errors — guild language via t(), guild resolved from interaction
# ===========================================================================


class TestAppCommandErrorGuildLanguage:
    """on_app_command_error resolves embed text via t() with interaction guild."""

    @staticmethod
    def _make_interaction(guild_id: int | None) -> MagicMock:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = None
        interaction.guild = MagicMock(spec=discord.Guild) if guild_id is not None else None
        if interaction.guild is not None:
            interaction.guild.id = guild_id
        interaction.guild_id = guild_id
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_spanish_guild_sees_spanish_unexpected_error(self) -> None:
        set_guild_language("777001", "es")
        bot = _make_bot()
        interaction = self._make_interaction(777001)

        await bot.on_app_command_error(interaction, commands.CommandError("x"))  # ty: ignore[invalid-argument-type]

        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True, "slash error MUST be ephemeral"
        embed = kwargs.get("embed")
        assert embed is not None
        assert embed.title == "Error Inesperado"
        assert embed.description is not None and "inesperado" in embed.description.lower()

    @pytest.mark.asyncio
    async def test_english_guild_sees_english_unexpected_error(self) -> None:
        set_guild_language("777002", "en")
        bot = _make_bot()
        interaction = self._make_interaction(777002)

        await bot.on_app_command_error(interaction, commands.CommandError("x"))  # ty: ignore[invalid-argument-type]

        kwargs = interaction.response.send_message.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        assert embed.title == "Unexpected Error"
        assert embed.description is not None and "unexpected" in embed.description.lower()

    @pytest.mark.asyncio
    async def test_followup_path_when_response_done(self) -> None:
        """Already-responded interactions deliver the error via followup."""
        set_guild_language("777003", "en")
        bot = _make_bot()
        interaction = self._make_interaction(777003)
        interaction.response.is_done.return_value = True
        interaction.followup.send = AsyncMock()

        await bot.on_app_command_error(interaction, commands.CommandError("x"))  # ty: ignore[invalid-argument-type]

        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
