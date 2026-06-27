"""Unit tests for NebulosaBot.on_app_command_error dispatch.

Guards the V3 fix: per-cog override detection must use the canonical
discord.py predicate (``Cog.has_app_command_error_handler``) rather than
a broken ``is not None`` check on a bound coroutine method — any bound
method on any Cog instance is never ``None``, so the old check always
bailed out and silently suppressed the global error embed for every
unhandled slash-command error.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.bot import NebulosaBot
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
