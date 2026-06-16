"""Unit tests for bot.cogs.stellar — StellarCog hybrid commands.

Covers:
    - /daily — claim daily coins, success/cooldown embeds
    - /coins — balance display for self and target
    - /leaderboard — XP/coins leaderboard, empty state
    - Cooldown display (time remaining)

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.stellar import StellarCog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock NebulosaBot with economy_service attached."""
    bot = MagicMock(spec=commands.Bot)
    bot.economy_service = MagicMock()
    bot.economy_service.claim_daily = AsyncMock()
    bot.economy_service.get_balance = AsyncMock()
    bot.economy_service.get_leaderboard = AsyncMock()
    return bot


@pytest.fixture
def cog(mock_bot: MagicMock) -> StellarCog:
    """Return a fresh StellarCog with mocked bot."""
    return StellarCog(mock_bot)


def _make_context(
    user_id: int = 111111111,
    guild_id: int = 123456789,
    user_display_name: str = "TestUser",
) -> MagicMock:
    """Build a mock commands.Context for testing hybrid commands.

    Provides ``.send()``, ``.author``, ``.guild`` with the minimal
    interface used by StellarCog commands.
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = user_id
    ctx.author.display_name = user_display_name
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    return ctx


# ---------------------------------------------------------------------------
# /daily — daily coin claim
# ---------------------------------------------------------------------------


class TestDailyCommand:
    """Tests for /daily hybrid command."""

    @pytest.mark.asyncio
    async def test_daily_success_embed(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Successful claim should send a green embed with coins and streak."""
        ctx = _make_context()
        mock_bot.economy_service.claim_daily.return_value = (True, 130, 4)

        await cog.daily.callback(cog, ctx)

        mock_bot.economy_service.claim_daily.assert_called_once_with(
            "123456789", "111111111"
        )
        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color.value == 0x2ECC71  # COLOR_SUCCESS
        assert "130" in embed.description  # coins_awarded
        assert call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_daily_cooldown_embed(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Claim on cooldown should show a yellow embed with streak."""
        ctx = _make_context()
        mock_bot.economy_service.claim_daily.return_value = (False, 0, 3)

        await cog.daily.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.color.value == 0xF1C40F  # COLOR_WARNING

    @pytest.mark.asyncio
    async def test_daily_error_handling(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Service errors should produce a red error embed."""
        ctx = _make_context()
        mock_bot.economy_service.claim_daily.side_effect = RuntimeError("DB down")

        await cog.daily.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR


# ---------------------------------------------------------------------------
# /coins — balance display
# ---------------------------------------------------------------------------


class TestCoinsCommand:
    """Tests for /coins hybrid command."""

    @pytest.mark.asyncio
    async def test_coins_self_balance(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Show own balance in an info embed."""
        ctx = _make_context(user_id=111111111)
        mock_bot.economy_service.get_balance.return_value = 500

        await cog.coins.callback(cog, ctx, member=None)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert "500" in embed.description
        assert embed.color.value == 0x3498DB  # COLOR_INFO

    @pytest.mark.asyncio
    async def test_coins_target_balance(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Show a target member's balance."""
        ctx = _make_context(user_id=111111111)
        target = MagicMock(spec=discord.Member)
        target.id = 222222222
        target.display_name = "TargetUser"
        mock_bot.economy_service.get_balance.return_value = 1200

        await cog.coins.callback(cog, ctx, member=target)

        mock_bot.economy_service.get_balance.assert_called_once_with(
            "123456789", "222222222"
        )
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert "1200" in embed.description

    @pytest.mark.asyncio
    async def test_coins_zero_balance(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Zero balance should still display 0."""
        ctx = _make_context()
        mock_bot.economy_service.get_balance.return_value = 0

        await cog.coins.callback(cog, ctx, member=None)

        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert "0" in embed.description

    @pytest.mark.asyncio
    async def test_coins_error_handling(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Service errors in coins should produce error embed."""
        ctx = _make_context()
        mock_bot.economy_service.get_balance.side_effect = RuntimeError("DB down")

        await cog.coins.callback(cog, ctx, member=None)

        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR


# ---------------------------------------------------------------------------
# /leaderboard — XP and coins top 10
# ---------------------------------------------------------------------------


class TestLeaderboardCommand:
    """Tests for /leaderboard hybrid command."""

    @pytest.mark.asyncio
    async def test_leaderboard_xp_displays_top_10(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """XP leaderboard should show top 10 with rank numbers."""
        ctx = _make_context()
        members = [
            {"userId": f"{1000 + i}", "xp": 1000 - i * 90, "coins": i * 10}
            for i in range(10)
        ]
        mock_bot.economy_service.get_leaderboard.return_value = members

        await cog.leaderboard.callback(cog, ctx, type="xp")

        mock_bot.economy_service.get_leaderboard.assert_called_once_with(
            "123456789", sort_by="xp", limit=10, offset=0
        )
        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "#1" in embed.description or "1." in embed.description

    @pytest.mark.asyncio
    async def test_leaderboard_coins_displays_top_10(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Coins leaderboard should query with sort_by='coins'."""
        ctx = _make_context()
        members = [
            {"userId": f"{1000 + i}", "xp": i * 10, "coins": 5000 - i * 450}
            for i in range(10)
        ]
        mock_bot.economy_service.get_leaderboard.return_value = members

        await cog.leaderboard.callback(cog, ctx, type="coins")

        mock_bot.economy_service.get_leaderboard.assert_called_once_with(
            "123456789", sort_by="coins", limit=10, offset=0
        )

    @pytest.mark.asyncio
    async def test_leaderboard_empty(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Empty leaderboard should show an appropriate embed."""
        ctx = _make_context()
        mock_bot.economy_service.get_leaderboard.return_value = []

        await cog.leaderboard.callback(cog, ctx, type="xp")

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR or similar

    @pytest.mark.asyncio
    async def test_leaderboard_error_handling(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Service errors in leaderboard should produce error embed."""
        ctx = _make_context()
        mock_bot.economy_service.get_leaderboard.side_effect = RuntimeError("DB down")

        await cog.leaderboard.callback(cog, ctx, type="xp")

        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    async def test_leaderboard_invalid_type_defaults_to_xp(
        self, cog: StellarCog, mock_bot: MagicMock,
    ) -> None:
        """Invalid leaderboard type should default to XP."""
        ctx = _make_context()
        members = [{"userId": "1111", "xp": 500, "coins": 50}]
        mock_bot.economy_service.get_leaderboard.return_value = members

        await cog.leaderboard.callback(cog, ctx, type="invalid")

        mock_bot.economy_service.get_leaderboard.assert_called_once_with(
            "123456789", sort_by="xp", limit=10, offset=0
        )
