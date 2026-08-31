"""Unit tests for StellarCog i18n migration.

Verifies that stellar commands return localized embeds using t()
instead of hardcoded strings.

Uses custom locale overrides with distinctive marker strings to prove
t() is called — same pattern as test_utility_i18n.py.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from bot.cogs.stellar import StellarCog
from bot.services.rank_renderer import RankRenderer
from tests.conftest import load_test_locales, make_ctx, make_member

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
            "cooldown_description": "DAILY_COOLDOWN_DESC_ES_{streak}_{remaining}",
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
            "cooldown_description": "DAILY_COOLDOWN_DESC_EN_{streak}_{remaining}",
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
    load_test_locales(
        tmp_path,
        _ES_MARKERS,
        _EN_MARKERS,
        guild_langs={str(_GUILD_ID_ES): "es", str(_GUILD_ID_EN): "en"},
    )
    yield


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock NebulosaBot with economy_service attached."""
    bot = MagicMock(spec=commands.Bot)
    bot.economy_service = MagicMock()
    bot.economy_service.claim_daily = AsyncMock()
    bot.economy_service.get_balance = AsyncMock()
    bot.economy_service.get_leaderboard = AsyncMock()
    bot.economy_service.get_rank_info = AsyncMock()
    # rank_renderer is owned by the bot (stored in setup_hook) and used
    # directly by stellar.rank(); mock it for parity with the real bot shape.
    bot.rank_renderer = MagicMock(spec=RankRenderer)
    bot.rank_renderer.generate_rank_card = MagicMock()
    return bot


@pytest.fixture
def cog(mock_bot: MagicMock) -> StellarCog:
    """Return a StellarCog (locale resolved per-call via guild language)."""
    return StellarCog(mock_bot)


def _make_ctx(guild_id: int, user_id: int = 111111111) -> MagicMock:
    """Build a spec'd Context from the shared factory plus stellar extras."""
    author = make_member(member_id=user_id)
    author.display_avatar = MagicMock()
    author.display_avatar.url = "https://cdn.discord.com/avatars/test.png"
    ctx = make_ctx(guild_id=guild_id, author=author, spec=commands.Context)
    ctx.defer = AsyncMock()
    return ctx


# Locale matrix shared by every command concept below.
_LOCALE_MATRIX = [
    pytest.param(_GUILD_ID_ES, "ES", id="es"),
    pytest.param(_GUILD_ID_EN, "EN", id="en"),
]


# ---------------------------------------------------------------------------
# /daily — localized per guild language
# ---------------------------------------------------------------------------


class TestDailyI18n:
    """daily returns localized strings for every guild language."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_success_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """claim_daily(True) renders the localized success title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.claim_daily.return_value = (True, 130, 4, 0)

        await cog.daily.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"DAILY_SUCCESS_TITLE_{suffix}" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_cooldown_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """claim_daily(False) renders the localized cooldown title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.claim_daily.return_value = (False, 0, 3, 22 * 3600)

        await cog.daily.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"DAILY_COOLDOWN_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# /coins — localized per guild language
# ---------------------------------------------------------------------------


class TestCoinsI18n:
    """coins returns localized strings for every guild language."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_self_balance_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Self balance embed renders the localized title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.get_balance.return_value = 500

        await cog.coins.callback(cog, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"COINS_BALANCE_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# /leaderboard — localized per guild language
# ---------------------------------------------------------------------------


class TestLeaderboardI18n:
    """leaderboard returns localized strings for every guild language."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    @pytest.mark.parametrize("lb_type", ["xp", "coins"])
    async def test_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        lb_type: str,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Both leaderboard types render their localized title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.get_leaderboard.return_value = [
            {"userId": "111", "xp": 500, "coins": 50},
        ]

        await cog.leaderboard.callback(cog, ctx, lb_type=lb_type)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"LB_{lb_type.upper()}_TITLE_{suffix}" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_empty_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Empty leaderboard renders the localized empty state."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.get_leaderboard.return_value = []

        await cog.leaderboard.callback(cog, ctx, lb_type="xp")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"LB_EMPTY_TITLE_{suffix}" in embed.title


# ---------------------------------------------------------------------------
# /rank — localized per guild language
# ---------------------------------------------------------------------------


class TestRankI18n:
    """rank returns localized strings for every guild language."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_no_data_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Missing rank info renders the localized no-data title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.get_rank_info.return_value = None

        await cog.rank.callback(cog, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"RANK_NODATA_TITLE_{suffix}" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_error_title_is_localized(
        self,
        cog: StellarCog,
        mock_bot: MagicMock,
        guild_id: int,
        suffix: str,
    ) -> None:
        """Rank lookup failure renders the localized failure title."""
        ctx = _make_ctx(guild_id)
        mock_bot.economy_service.get_rank_info.side_effect = RuntimeError("DB down")

        await cog.rank.callback(cog, ctx, member=None)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"RANK_FAIL_TITLE_{suffix}" in embed.title
