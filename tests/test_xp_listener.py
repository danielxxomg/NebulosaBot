"""Unit tests for bot.listeners.xp_listener — XP gain listener.

Covers:
    - Bot/DM messages are ignored
    - Valid messages trigger gain_xp()
    - Level-up notification embed + role assignment
    - levelRoleMap and levelUpChannelId handling

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

# mypy: disable-error-code="union-attr,operator"
# Test file: heavy MagicMock usage causes false-positive union-attr errors
# on service attributes (EconomyService | None) and mock return_value chains.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.listeners.xp_listener import XPListener

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock bot with economy_service attached."""
    bot = MagicMock(spec=commands.Bot)
    bot.economy_service = MagicMock()
    bot.economy_service.gain_xp = AsyncMock()
    bot.economy_service.get_economy_config = AsyncMock()
    return bot


@pytest.fixture
def mock_guild() -> MagicMock:
    """Return a mock discord.Guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    return guild


@pytest.fixture
def mock_message(mock_guild: MagicMock) -> MagicMock:
    """Return a mock discord.Message from a non-bot user in a guild."""
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(spec=discord.Member)
    msg.author.bot = False
    msg.guild = mock_guild
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.send = AsyncMock()
    return msg


@pytest.fixture
def listener(mock_bot: MagicMock) -> XPListener:
    """Return a fresh XPListener with a mock bot."""
    return XPListener(mock_bot)


# ---------------------------------------------------------------------------
# Bot / DM guard
# ---------------------------------------------------------------------------


class TestXpListenerGuard:
    """Bot and DM messages must be ignored."""

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """Messages from bots should not trigger XP gain."""
        mock_message.author.bot = True

        await listener.on_message(mock_message)

        listener.bot.economy_service.gain_xp.assert_not_called()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_ignores_dm_messages(
        self,
        listener: XPListener,
        mock_bot: MagicMock,
    ) -> None:
        """Direct messages (no guild) should not trigger XP gain."""
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock(spec=discord.User)
        msg.author.bot = False
        msg.guild = None

        await listener.on_message(msg)

        listener.bot.economy_service.gain_xp.assert_not_called()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# XP Gain — normal path
# ---------------------------------------------------------------------------


class TestXpListenerGain:
    """Normal XP gain flow: call service, detect level-up."""

    @pytest.mark.asyncio
    async def test_calls_gain_xp_with_correct_ids(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """Valid message should call gain_xp(guild_id, user_id)."""
        mock_message.author.id = 111111111
        listener.bot.economy_service.gain_xp.return_value = (10, 0, False)

        await listener.on_message(mock_message)

        listener.bot.economy_service.gain_xp.assert_called_once_with("123456789", "111111111")

    @pytest.mark.asyncio
    async def test_gain_xp_no_level_up_does_nothing_extra(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """When gain_xp returns leveled_up=False, no embed or role change."""
        listener.bot.economy_service.gain_xp.return_value = (260, 2, False)

        await listener.on_message(mock_message)

        # No embed sent, no role assigned.
        mock_message.channel.send.assert_not_called()
        mock_message.guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_gain_xp_level_up_sends_embed(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """Level-up should send a notification embed."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 3, True)
        # No config → fallback to message channel, no roles.
        listener.bot.economy_service.get_economy_config.return_value = None

        await listener.on_message(mock_message)

        # Should send embed to message channel (fallback — no levelUpChannelId).
        mock_message.channel.send.assert_called_once()
        call_args = mock_message.channel.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "Level 3" in embed.description or "level 3" in embed.description.lower()

    @pytest.mark.asyncio
    async def test_gain_xp_zero_xp_on_cooldown(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """When gain_xp returns (0, 0, False), no embed or role action."""
        listener.bot.economy_service.gain_xp.return_value = (0, 0, False)

        await listener.on_message(mock_message)

        # No embed, no role, no channel lookup, no config lookup.
        mock_message.channel.send.assert_not_called()
        mock_message.guild.get_channel.assert_not_called()
        listener.bot.economy_service.get_economy_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_gain_xp_level_up_high_level(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """Level-up to a high level (e.g., 50) should still work."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (500000, 50, True)
        listener.bot.economy_service.get_economy_config.return_value = None

        await listener.on_message(mock_message)

        call_args = mock_message.channel.send.call_args
        embed = call_args[1]["embed"]
        assert "Level 50" in embed.description


# ---------------------------------------------------------------------------
# Level-up: channel routing
# ---------------------------------------------------------------------------


class TestXpListenerLevelUpChannel:
    """Level-up embed should respect levelUpChannelId config."""

    @pytest.mark.asyncio
    async def test_level_up_uses_configured_channel(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When levelUpChannelId is set, embed goes to that channel."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 3, True)
        listener.bot.economy_service.get_economy_config.return_value = {
            "guildId": "123456789",
            "levelUpChannelId": "999999999",
            "levelRoles": {},
        }

        level_up_channel = MagicMock(spec=discord.TextChannel)
        level_up_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = level_up_channel

        await listener.on_message(mock_message)

        # Embed should go to configured channel, not message channel.
        level_up_channel.send.assert_called_once()
        mock_message.channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_up_fallback_to_message_channel(
        self,
        listener: XPListener,
        mock_message: MagicMock,
    ) -> None:
        """When levelUpChannelId is None, embed goes to message.channel."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 3, True)
        listener.bot.economy_service.get_economy_config.return_value = None

        await listener.on_message(mock_message)

        # Embed should go to message channel.
        mock_message.channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_level_up_configured_channel_not_found(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When configured channel doesn't exist, fallback to message channel."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 3, True)
        listener.bot.economy_service.get_economy_config.return_value = {
            "guildId": "123456789",
            "levelUpChannelId": "999999999",
            "levelRoles": {},
        }

        mock_guild.get_channel.return_value = None  # Channel not found

        await listener.on_message(mock_message)

        # Should fallback to message.channel
        mock_message.channel.send.assert_called_once()


# ---------------------------------------------------------------------------
# Level-up: role assignment
# ---------------------------------------------------------------------------


class TestXpListenerRoleAssignment:
    """Level-up should auto-assign roles from levelRoleMap."""

    @pytest.mark.asyncio
    async def test_level_up_assigns_role_from_config(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When levelRoleMap has a role for the new level, assign it."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 5, True)
        listener.bot.economy_service.get_economy_config.return_value = {
            "guildId": "123456789",
            "levelUpChannelId": None,
            "levelRoles": {"5": "555555555"},
        }

        role = MagicMock(spec=discord.Role)
        mock_guild.get_role.return_value = role

        await listener.on_message(mock_message)

        mock_guild.get_role.assert_called_once_with(555555555)
        mock_message.author.add_roles.assert_called_once_with(role)

    @pytest.mark.asyncio
    async def test_level_up_no_role_for_level(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When levelRoleMap has no entry for new level, skip role assignment."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 5, True)
        listener.bot.economy_service.get_economy_config.return_value = {
            "guildId": "123456789",
            "levelUpChannelId": None,
            "levelRoles": {"10": "999999999"},  # Only level 10
        }

        await listener.on_message(mock_message)

        mock_guild.get_role.assert_not_called()
        mock_message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_up_role_not_found(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When role ID from config doesn't exist, skip gracefully."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 5, True)
        listener.bot.economy_service.get_economy_config.return_value = {
            "guildId": "123456789",
            "levelUpChannelId": None,
            "levelRoles": {"5": "555555555"},
        }

        mock_guild.get_role.return_value = None  # Role doesn't exist

        await listener.on_message(mock_message)

        mock_message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_up_no_config_skips_role(
        self,
        listener: XPListener,
        mock_message: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """When no economy_config exists, skip role assignment entirely."""
        mock_message.author.id = 111111111
        mock_message.author.mention = "<@111111111>"
        listener.bot.economy_service.gain_xp.return_value = (400, 5, True)
        listener.bot.economy_service.get_economy_config.return_value = None

        await listener.on_message(mock_message)

        mock_guild.get_role.assert_not_called()
        mock_message.author.add_roles.assert_not_called()
