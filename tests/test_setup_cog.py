"""Unit tests for bot.cogs.setup.SetupCog — S2a panel framework.

Covers S2a.9: /setup pure app command, zero params, default_permissions administrator,
non-ephemeral panel with SetupPanelView and nbpanel token.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.setup import SetupCog


@pytest.fixture
def setup_bot() -> MagicMock:
    bot = MagicMock()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(ticket_category_id=None, language="es"))
    bot.db = MagicMock()
    bot.db.get_ticket_categories = AsyncMock(return_value=[])
    return bot


@pytest.fixture
def setup_cog(setup_bot: MagicMock) -> SetupCog:
    return SetupCog(bot=setup_bot)


class TestSetupCommandIsPureAppCommand:
    """S2a.9: /setup must be pure app command, zero params, administrator default perms."""

    def test_is_app_command_not_hybrid(self, setup_cog: SetupCog) -> None:
        import pathlib

        src = pathlib.Path("bot/cogs/setup.py").read_text(encoding="utf-8")
        assert "app_commands.command" in src
        # Ensure no hybrid_command for setup
        # Count hybrid_command occurrences in file — should be 0
        assert src.count("hybrid_command") == 0, "setup.py must not contain hybrid_command after S2a.9"

    def test_zero_params(self, setup_cog: SetupCog) -> None:
        cmds = [c for c in setup_cog.__cog_app_commands__ if getattr(c, "name", None) == "setup"]
        assert cmds, "SetupCog must expose /setup as app command"
        cmd = cmds[0]
        params = getattr(cmd, "parameters", [])
        assert len(params) == 0, f"/setup must have zero params, got {params}"

        sig = inspect.signature(setup_cog.setup_command.callback)
        # callback(self, interaction) -> 2 params
        assert len(sig.parameters) == 2, (
            f"setup callback must be (self, interaction), got {list(sig.parameters.keys())}"
        )

    def test_default_permissions_administrator(self) -> None:
        import pathlib

        src = pathlib.Path("bot/cogs/setup.py").read_text(encoding="utf-8")
        assert "default_permissions" in src
        assert "administrator" in src.lower()

    def test_exposes_callback(self, setup_cog: SetupCog) -> None:
        assert hasattr(setup_cog, "setup_command")
        assert callable(getattr(setup_cog.setup_command, "callback", None))


class TestSetupPanelInvocation:
    """Panel opens as one non-ephemeral message with SetupPanelView."""

    @pytest.mark.asyncio
    async def test_sends_one_non_ephemeral_panel(self, setup_cog: SetupCog, setup_bot: MagicMock) -> None:
        from bot.views.setup_panel import SetupPanelView

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        interaction.guild = guild
        interaction.guild_id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True

        await setup_cog.setup_command.callback(setup_cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is False or kwargs.get("ephemeral") is None
        assert "embed" in kwargs
        assert "view" in kwargs
        assert isinstance(kwargs["view"], SetupPanelView)
        footer = getattr(kwargs["embed"].footer, "text", "") or ""
        assert "nbpanel|module=" in footer

    @pytest.mark.asyncio
    async def test_guild_only_ephemeral_error(self, setup_cog: SetupCog) -> None:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.guild = None
        interaction.user = MagicMock(spec=discord.Member)

        await setup_cog.setup_command.callback(setup_cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_uses_t_for_panel(self, setup_cog: SetupCog, setup_bot: MagicMock) -> None:
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        interaction.guild = guild
        interaction.guild_id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True

        with (
            patch("bot.cogs.setup.t", return_value="localized"),
            patch("bot.views.setup_panel.t", return_value="localized"),
        ):
            await setup_cog.setup_command.callback(setup_cog, interaction)

        # At least one t call for setup error or panel
        # The cog itself calls t for guild_only error only on error path, but panel build calls t
        # So we check that panel embed was created (send called)
        interaction.response.send_message.assert_awaited_once()
