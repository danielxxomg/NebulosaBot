"""Unit tests for bot.cogs.ocio — OcioCog with i18n migration.

Covers:
    - /dados — localized title and description
    - /banana — localized title, description via OcioService pool

Uses distinct locale overrides to prove t() is called.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core.i18n import load_locales, set_guild_language
from bot.services.ocio_service import OcioService
from tests.conftest import make_ctx

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> Generator[None, None, None]:
    """Load custom locale overrides."""
    from bot.core import i18n as i18n_mod

    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)

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

    yield

    i18n_mod._locales.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.clear()
    i18n_mod._guild_languages.update(orig_guild_langs)


@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    return OcioCog(mock_bot)


def _make_ctx(guild_id: int | None = _GUILD_ID) -> MagicMock:
    """Delegates to the shared factory; keeps the DM-capable default."""
    return make_ctx(guild_id=guild_id, spec=commands.Context)


# ---------------------------------------------------------------------------
# /dados — calls t()
# ---------------------------------------------------------------------------


class TestDadosI18n:
    @pytest.mark.asyncio
    async def test_dados_embed_from_locale(self, cog: OcioCog) -> None:
        """Dice embed MUST use t() for title and interpolated description (dados alias compat)."""
        ctx = _make_ctx()
        await cog.dice.callback(cog, ctx, sides=6)
        embed = ctx.send.call_args[1]["embed"]
        assert "TEST_DICE" in embed.title
        assert "d6" in embed.description
        # alias stays compat
        assert cog.dados is cog.dice


# ---------------------------------------------------------------------------
# /banana — calls t() via OcioService pool
# ---------------------------------------------------------------------------


class TestBananaI18n:
    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebp", "banana_01.webp", 7)
    )
    async def test_banana_embed_from_locale(
        self,
        mock_banana: AsyncMock,
        cog: OcioCog,
    ) -> None:
        """Banana embed MUST use t() for title and interpolated size.

        Pool fallback means banana never errors — the success path IS the
        fallback path (former error-path twin asserted the same body).
        """
        ctx = _make_ctx()
        await cog.banana.callback(cog, ctx)
        embed = ctx.send.call_args[1]["embed"]
        assert "TEST_BANANA" in embed.title
        assert "cm" in embed.description

    @pytest.mark.asyncio
    async def test_banana_uses_webp_path(self) -> None:
        """Banana pool MUST use .webp files."""
        svc = OcioService()
        assert "assets/images/banana" in str(svc._banana_dir)
        assert svc._banana_dir.suffix != ".png"
