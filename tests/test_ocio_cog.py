"""Unit tests for bot.cogs.ocio — OcioCog hybrid commands.

Covers:
    - /dados — dice roll with default and custom sides, result validation
    - /banana — random measurement + image attachment, missing asset error

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales, set_guild_language
from bot.services.ocio_service import OcioService
from tests.conftest import make_ctx

# ---------------------------------------------------------------------------
# i18n setup
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n() -> None:
    """Load real locale files so t() returns actual strings."""
    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    load_locales(Path("bot/locales"))
    set_guild_language(str(_GUILD_ID), "es")


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
    """Delegates to the shared factory; keeps the DM-capable default."""
    return make_ctx(guild_id=guild_id, spec=commands.Context)


# ---------------------------------------------------------------------------
# /dados — dice roll
# ---------------------------------------------------------------------------


class TestDadosCommand:
    """Tests for /dice (alias dados probes compat)."""

    @pytest.mark.asyncio
    async def test_dados_default_six_sided(
        self,
        cog: OcioCog,
    ) -> None:
        """Default roll (sides=6) via dice produces result in [1, 6]; dados alias mirrors dice."""
        ctx = _make_ctx()

        await cog.dice.callback(cog, ctx, sides=6)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        desc = embed.description
        assert desc is not None
        assert "d6" in desc
        # alias must resolve to same command object (name stays dice)
        assert cog.dados is cog.dice
        assert cog.dados.name == "dice"

    @pytest.mark.asyncio
    async def test_dados_custom_sides(
        self,
        cog: OcioCog,
    ) -> None:
        """Custom sides (e.g., 20) via dice."""
        ctx = _make_ctx()

        await cog.dice.callback(cog, ctx, sides=20)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "d20" in embed.description
        assert cog.dados is cog.dice

    @pytest.mark.asyncio
    async def test_dados_max_sides_100(
        self,
        cog: OcioCog,
    ) -> None:
        """Max sides (100) via dice."""
        ctx = _make_ctx()

        await cog.dice.callback(cog, ctx, sides=100)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert "d100" in embed.description
        assert cog.dados is cog.dice

    @pytest.mark.asyncio
    async def test_dados_result_in_range(
        self,
        cog: OcioCog,
    ) -> None:
        """The random result should be between 1 and sides (inclusive)."""
        ctx = _make_ctx()

        for sides in [6, 20, 100]:
            await cog.dice.callback(cog, ctx, sides=sides)

            call_args = ctx.send.call_args
            embed = call_args[1]["embed"]
            desc = embed.description
            parts = desc.split("**")
            if len(parts) >= 3:
                result = int(parts[1])
                assert 1 <= result <= sides, f"Result {result} not in [1, {sides}]"

    @pytest.mark.asyncio
    async def test_dados_works_in_dm(
        self,
        cog: OcioCog,
    ) -> None:
        """Dice roll should work in DM context."""
        ctx = _make_ctx(guild_id=None)

        await cog.dice.callback(cog, ctx, sides=6)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)


# ---------------------------------------------------------------------------
# /banana — random banana measurement + image
# ---------------------------------------------------------------------------


class TestBananaCommand:
    """Tests for /banana hybrid command (via OcioService pool)."""

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_returns_embed_with_file(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """Normal banana sends embed + discord.File attachment."""
        ctx = _make_ctx()

        await cog.banana.callback(cog, ctx)

        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        assert "file" in call_args[1]
        sent_file = call_args[1]["file"]
        assert isinstance(sent_file, discord.File)
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "cm" in embed.description
        assert "banana" in embed.title.lower() or "\U0001f34c" in embed.title

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_measurement_in_range(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """Measurement should be between 2 and 30 cm."""
        ctx = _make_ctx()
        for _ in range(5):
            await cog.banana.callback(cog, ctx)
            call_args = ctx.send.call_args
            embed = call_args[1]["embed"]
            desc = embed.description
            parts = desc.split("**")
            if len(parts) >= 3:
                size = int(parts[1].split()[0])
                assert 2 <= size <= 30, f"Size {size} not in [2, 30]"

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_missing_asset_shows_error(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """OcioService fallback ensures delivery — embed still has cm even when asset missing."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)
        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)
        assert "cm" in embed.description

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_works_in_dm(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """Banana should work in DM context."""
        ctx = _make_ctx(guild_id=None)
        await cog.banana.callback(cog, ctx)
        ctx.send.assert_called_once()
        call_args = ctx.send.call_args
        assert "file" in call_args[1]
        embed = call_args[1]["embed"]
        assert isinstance(embed, discord.Embed)


# ---------------------------------------------------------------------------
# S1 — banana pool assets via OcioService
# ---------------------------------------------------------------------------


class TestBananaWebpAsset:
    """Tests for S1 — banana images served via OcioService pool."""

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_file_uses_webp_filename(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """discord.File MUST use .webp filename from pool."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)
        call_args = ctx.send.call_args
        sent_file = call_args[1]["file"]
        assert isinstance(sent_file, discord.File)
        assert sent_file.filename.endswith(".webp")

    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebpbytes", "banana_01.webp", 12)
    )
    async def test_banana_embed_uses_webp_attachment_url(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """Embed image URL MUST use attachment://*.webp."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)
        call_args = ctx.send.call_args
        embed = call_args[1]["embed"]
        assert embed.image.url == "attachment://banana_01.webp"

    @pytest.mark.asyncio
    async def test_banana_uses_assets_images_path(self) -> None:
        """Pool dir MUST be assets/images/banana."""
        svc = OcioService()
        assert "assets/images/banana" in str(svc._banana_dir)
