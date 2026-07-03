"""Unit tests for bot.cogs.ocio — OcioCog hybrid commands.

Covers:
    - /dados — dice roll with default and custom sides, result validation
    - /banana — random measurement + image attachment, missing asset error

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock commands.Bot — no services needed by OcioCog."""
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    """Return a fresh OcioCog with mocked bot."""
    return OcioCog(mock_bot)


def _make_ctx(guild_id: int | None = 123456789) -> MagicMock:
    """Build a mock commands.Context for OcioCog tests.

    Provides ``.send()``, ``.author``, and ``.guild``.
    If guild_id is None, simulates a DM context.
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.display_name = "TestUser"

    if guild_id is not None:
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = guild_id
    else:
        ctx.guild = None

    return ctx


# ---------------------------------------------------------------------------
# /dados — dice roll
# ---------------------------------------------------------------------------


class TestDadosCommand:
    """Tests for /dados hybrid command."""

    @pytest.mark.asyncio
    async def test_dados_default_six_sided(
        self, cog: OcioCog,
    ) -> None:
        """Default roll (sides=6) produces result in [1, 6]."""
        ctx = _make_ctx()

        await cog.dados.callback(cog, ctx, sides=6)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)

        # result should be mentioned in the description
        desc = embed.description
        assert desc is not None
        # Extract the result number from "You rolled a **{result}** (d{sides})"
        assert "d6" in desc

    @pytest.mark.asyncio
    async def test_dados_custom_sides(
        self, cog: OcioCog,
    ) -> None:
        """Custom sides (e.g., 20) produces result in [1, 20]."""
        ctx = _make_ctx()

        await cog.dados.callback(cog, ctx, sides=20)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "d20" in embed.description

    @pytest.mark.asyncio
    async def test_dados_max_sides_100(
        self, cog: OcioCog,
    ) -> None:
        """Max sides (100) produces result in [1, 100]."""
        ctx = _make_ctx()

        await cog.dados.callback(cog, ctx, sides=100)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert "d100" in embed.description

    @pytest.mark.asyncio
    async def test_dados_result_in_range(
        self, cog: OcioCog,
    ) -> None:
        """The random result should be between 1 and sides (inclusive)."""
        ctx = _make_ctx()

        for sides in [6, 20, 100]:
            await cog.dados.callback(cog, ctx, sides=sides)

            call_args = ctx.send.call_args
            embed = call_args[1]["embed"]
            desc = embed.description

            # Parse the result: "You rolled a **{result}** (d{sides})"
            parts = desc.split("**")
            if len(parts) >= 3:
                result = int(parts[1])
                assert 1 <= result <= sides, f"Result {result} not in [1, {sides}]"

    @pytest.mark.asyncio
    async def test_dados_works_in_dm(
        self, cog: OcioCog,
    ) -> None:
        """Dice roll should work in DM context."""
        ctx = _make_ctx(guild_id=None)

        await cog.dados.callback(cog, ctx, sides=6)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)


# ---------------------------------------------------------------------------
# /banana — random banana measurement + image
# ---------------------------------------------------------------------------


class TestBananaCommand:
    """Tests for /banana hybrid command."""

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=True)
    async def test_banana_returns_embed_with_file(
        self, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Normal banana sends embed + discord.File attachment."""
        ctx = _make_ctx()

        await cog.banana.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args

        # Should send file
        assert "file" in call_args[1]
        sent_file = call_args[1]["file"]
        assert isinstance(sent_file, discord.File)

        # Should send embed
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "cm" in embed.description
        assert "🍌" in embed.title

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=True)
    async def test_banana_measurement_in_range(
        self, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Measurement should be between 2 and 30 cm."""
        ctx = _make_ctx()

        for _ in range(10):  # Run multiple times to catch range issues
            await cog.banana.callback(cog, ctx)

            call_args = ctx.send.call_args
            embed = call_args[1]["embed"]
            desc = embed.description

            # Parse "This banana is **{size} cm**"
            parts = desc.split("**")
            if len(parts) >= 3:
                size = int(parts[1].split()[0])
                assert 2 <= size <= 30, f"Size {size} not in [2, 30]"

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=False)
    async def test_banana_missing_asset_shows_error(
        self, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """When banana.png is missing, reply with error embed."""
        ctx = _make_ctx()

        await cog.banana.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color.value == 0xE74C3C  # COLOR_ERROR

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=True)
    async def test_banana_works_in_dm(
        self, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Banana should work in DM context."""
        ctx = _make_ctx(guild_id=None)

        await cog.banana.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        assert "file" in call_args[1]
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
