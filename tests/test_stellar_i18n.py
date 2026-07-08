"""Unit tests for StellarCog i18n migration.

Verifies that stellar commands return localized embeds using t()
instead of hardcoded strings.

Uses custom locale overrides with distinctive marker strings to prove
t() is called — same pattern as test_utility_i18n.py.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.stellar import StellarCog
from bot.core.i18n import load_locales, set_guild_language

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GUILD_ID_ES = 111111111
_GUILD_ID_EN = 222222222

# Marker strings — intentionally ugly so they're unmistakable in assertions.
_ES_MARKERS = {
    "stellar": {
        "daily": {
            "failed_title": "DAILY_FAIL_TITLE_ES",
            "failed_description": "DAILY_FAIL_DESC_ES",
            "success_title": "DAILY_SUCCESS_TITLE_ES",
            "success_description": "DAILY_SUCCESS_DESC_ES_{coins}_{streak}_{plural}",
            "cooldown_title": "DAILY_COOLDOWN_TITLE_ES",
            "cooldown_description": "DAILY_COOLDOWN_DESC_ES_{streak}",
        },
        "coins": {
            "failed_title": "COINS_FAIL_TITLE_ES",
            "failed_description": "COINS_FAIL_DESC_ES",
            "balance_title": "COINS_BALANCE_TITLE_ES",
            "self_description": "COINS_SELF_DESC_ES_{balance}",
            "target_description": "COINS_TARGET_DESC_ES_{name}_{balance}",
        },
        "leaderboard": {
            "error_title": "LB_ERROR_TITLE_ES",
            "error_description": "LB_ERROR_DESC_ES",
            "empty_title": "LB_EMPTY_TITLE_ES",
            "empty_description": "LB_EMPTY_DESC_ES_{type}",
            "xp_title": "LB_XP_TITLE_ES",
            "coins_title": "LB_COINS_TITLE_ES",
            "footer": "LB_FOOTER_ES_{count}",
        },
        "rank": {
            "failed_title": "RANK_FAIL_TITLE_ES",
            "failed_description": "RANK_FAIL_DESC_ES",
            "no_data_title": "RANK_NODATA_TITLE_ES",
            "no_data_description": "RANK_NODATA_DESC_ES_{name}",
        },
    },
}

_EN_MARKERS = {
    "stellar": {
        "daily": {
            "failed_title": "DAILY_FAIL_TITLE_EN",
            "failed_description": "DAILY_FAIL_DESC_EN",
            "success_title": "DAILY_SUCCESS_TITLE_EN",
            "success_description": "DAILY_SUCCESS_DESC_EN_{coins}_{streak}_{plural}",
            "cooldown_title": "DAILY_COOLDOWN_TITLE_EN",
            "cooldown_description": "DAILY_COOLDOWN_DESC_EN_{streak}",
        },
        "coins": {
            "failed_title": "COINS_FAIL_TITLE_EN",
            "failed_description": "COINS_FAIL_DESC_EN",
            "balance_title": "COINS_BALANCE_TITLE_EN",
            "self_description": "COINS_SELF_DESC_EN_{balance}",
            "target_description": "COINS_TARGET_DESC_EN_{name}_{balance}",
        },
        "leaderboard": {
            "error_title": "LB_ERROR_TITLE_EN",
            "error_description": "LB_ERROR_DESC_EN",
            "empty_title": "LB_EMPTY_TITLE_EN",
            "empty_description": "LB_EMPTY_DESC_EN_{type}",
            "xp_title": "LB_XP_TITLE_EN",
            "coins_title": "LB_COINS_TITLE_EN",
            "footer": "LB_FOOTER_EN_{count}",
        },
        "rank": {
            "failed_title": "RANK_FAIL_TITLE_EN",
            "failed_description": "RANK_FAIL_DESC_EN",
            "no_data_title": "RANK_NODATA_TITLE_EN",
            "no_data_description": "RANK_NODATA_DESC_EN_{name}",
        },
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> Generator[None, None, None]:
    """Load custom locale overrides for stellar i18n tests."""
    from bot.core import i18n as i18n_mod

    # Save original state.
    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)

    (locale_dir / "es.json").write_text(json.dumps(_ES_MARKERS), encoding="utf-8")
    (locale_dir / "en.json").write_text(json.dumps(_EN_MARKERS), encoding="utf-8")

    load_locales(locale_dir)
    set_guild_language(str(_GUILD_ID_ES), "es")
    set_guild_language(str(_GUILD_ID_EN), "en")

    yield

    # Restore original state so other test modules are not affected.
    i18n_mod._locales.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.clear()
    i18n_mod._guild_languages.update(orig_guild_langs)


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock NebulosaBot with economy_service attached."""
    bot = MagicMock(spec=commands.Bot)
    bot.economy_service = MagicMock()
    bot.economy_service.claim_daily = AsyncMock()
    bot.economy_service.get_balance = AsyncMock()
    bot.economy_service.get_leaderboard = AsyncMock()
    bot.economy_service.get_rank_info = AsyncMock()
    bot.image_service = MagicMock()
    bot.image_service.generate_rank_card = MagicMock()
    return bot


@pytest.fixture
def cog_es(mock_bot: MagicMock) -> StellarCog:
    """Return a StellarCog for the ES guild."""
    return StellarCog(mock_bot)


def _make_ctx(guild_id: int, user_id: int = 111111111) -> MagicMock:
    """Build a mock Context with the given guild_id."""
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = user_id
    ctx.author.display_name = "TestUser"
    ctx.author.display_avatar = MagicMock()
    ctx.author.display_avatar.url = "https://cdn.discord.com/avatars/test.png"
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    return ctx


# ---------------------------------------------------------------------------
# /daily — ES vs EN
# ---------------------------------------------------------------------------


class TestDailyI18n:
    """daily command returns localized strings."""

    async def test_daily_success_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish daily success title."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.claim_daily.return_value = (True, 130, 4)

        await cog_es.daily.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DAILY_SUCCESS_TITLE_ES" in embed.title

    async def test_daily_success_en(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """EN guild gets English daily success title."""
        cog = StellarCog(mock_bot)
        ctx = _make_ctx(_GUILD_ID_EN)
        mock_bot.economy_service.claim_daily.return_value = (True, 130, 4)

        await cog.daily.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DAILY_SUCCESS_TITLE_EN" in embed.title

    async def test_daily_cooldown_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish cooldown title."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.claim_daily.return_value = (False, 0, 3)

        await cog_es.daily.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DAILY_COOLDOWN_TITLE_ES" in embed.title


# ---------------------------------------------------------------------------
# /coins — ES vs EN
# ---------------------------------------------------------------------------


class TestCoinsI18n:
    """coins command returns localized strings."""

    async def test_coins_self_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish coin balance title."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.get_balance.return_value = 500

        await cog_es.coins.callback(cog_es, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "COINS_BALANCE_TITLE_ES" in embed.title

    async def test_coins_self_en(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """EN guild gets English coin balance title."""
        cog = StellarCog(mock_bot)
        ctx = _make_ctx(_GUILD_ID_EN)
        mock_bot.economy_service.get_balance.return_value = 500

        await cog.coins.callback(cog, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "COINS_BALANCE_TITLE_EN" in embed.title


# ---------------------------------------------------------------------------
# /leaderboard — ES vs EN
# ---------------------------------------------------------------------------


class TestLeaderboardI18n:
    """leaderboard command returns localized strings."""

    async def test_leaderboard_xp_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish XP leaderboard title."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.get_leaderboard.return_value = [
            {"userId": "111", "xp": 500, "coins": 50},
        ]

        await cog_es.leaderboard.callback(cog_es, ctx, lb_type="xp")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "LB_XP_TITLE_ES" in embed.title

    async def test_leaderboard_coins_en(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """EN guild gets English coins leaderboard title."""
        cog = StellarCog(mock_bot)
        ctx = _make_ctx(_GUILD_ID_EN)
        mock_bot.economy_service.get_leaderboard.return_value = [
            {"userId": "111", "xp": 50, "coins": 500},
        ]

        await cog.leaderboard.callback(cog, ctx, lb_type="coins")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "LB_COINS_TITLE_EN" in embed.title

    async def test_leaderboard_empty_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish empty leaderboard message."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.get_leaderboard.return_value = []

        await cog_es.leaderboard.callback(cog_es, ctx, lb_type="xp")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "LB_EMPTY_TITLE_ES" in embed.title


# ---------------------------------------------------------------------------
# /rank — ES
# ---------------------------------------------------------------------------


class TestRankI18n:
    """rank command returns localized strings."""

    async def test_rank_no_data_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish 'no rank data' message."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.get_rank_info.return_value = None

        await cog_es.rank.callback(cog_es, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "RANK_NODATA_TITLE_ES" in embed.title

    async def test_rank_error_es(
        self,
        cog_es: StellarCog,
        mock_bot: MagicMock,
    ) -> None:
        """ES guild gets Spanish rank error message."""
        ctx = _make_ctx(_GUILD_ID_ES)
        mock_bot.economy_service.get_rank_info.side_effect = RuntimeError("DB down")

        await cog_es.rank.callback(cog_es, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "RANK_FAIL_TITLE_ES" in embed.title
