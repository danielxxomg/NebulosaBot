"""Unit tests for bot.cogs.ocio — OcioCog with i18n migration.

Covers:
    - /dados — localized title and description
    - /banana — localized title, description, error; uses banana.webp path

Uses distinct locale overrides to prove t() is called.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core.i18n import load_locales, set_guild_language

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> None:
    """Load custom locale overrides."""
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    es_data = {
        "common": {"footer": "NB • {timestamp}"},
        "ocio": {
            "dados": {
                "title": "TEST_DICE",
                "description": "ROLLED_{result}_d{sides}",
            },
            "banana": {
                "title": "TEST_BANANA",
                "description": "BANANA_{size}cm",
                "error_title": "BANANA_ERR",
                "error_description": "BANANA_ERR_DESC",
            },
        },
    }

    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "es.json").write_text(json.dumps(es_data), encoding="utf-8")

    load_locales(locale_dir)
    set_guild_language(str(_GUILD_ID), "es")


@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    return OcioCog(mock_bot)


def _make_ctx(guild_id: int | None = _GUILD_ID) -> MagicMock:
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
# /dados — calls t()
# ---------------------------------------------------------------------------


class TestDadosI18n:
    @pytest.mark.asyncio
    async def test_dados_title_from_locale(self, cog: OcioCog) -> None:
        """Dados embed title MUST use t()."""
        ctx = _make_ctx()
        await cog.dados.callback(cog, ctx, sides=6)

        embed = ctx.send.call_args[1]["embed"]
        assert "TEST_DICE" in embed.title

    @pytest.mark.asyncio
    async def test_dados_description_from_locale(self, cog: OcioCog) -> None:
        """Dados embed description MUST use t() with interpolated values."""
        ctx = _make_ctx()
        await cog.dados.callback(cog, ctx, sides=6)

        embed = ctx.send.call_args[1]["embed"]
        assert "d6" in embed.description


# ---------------------------------------------------------------------------
# /banana — calls t()
# ---------------------------------------------------------------------------


class TestBananaI18n:
    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=True)
    @patch("discord.File")
    async def test_banana_title_from_locale(
        self, mock_file: MagicMock, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Banana embed title MUST use t()."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "TEST_BANANA" in embed.title

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=True)
    @patch("discord.File")
    async def test_banana_description_from_locale(
        self, mock_file: MagicMock, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Banana embed description MUST use t() with interpolated size."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "cm" in embed.description

    @pytest.mark.asyncio
    @patch("bot.cogs.ocio.Path.exists", return_value=False)
    async def test_banana_error_from_locale(
        self, mock_exists: MagicMock, cog: OcioCog,
    ) -> None:
        """Banana missing asset error MUST use t()."""
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "BANANA_ERR" in embed.title

    @pytest.mark.asyncio
    async def test_banana_uses_webp_path(self) -> None:
        """Banana MUST use banana.webp path (not banana.png)."""
        from bot.cogs.ocio import _BANANA_IMAGE_PATH

        assert _BANANA_IMAGE_PATH.suffix == ".webp"
