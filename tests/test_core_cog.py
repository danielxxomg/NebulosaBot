"""Unit tests for bot.cogs.core — CoreCog hybrid commands with i18n.

Covers:
    - /ping — calls t() for title and latency description
    - /status — calls t() for title, field names
    - /help — calls t() for error messages

Uses distinct locale overrides so tests prove t() is called, not hardcoded strings.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.core import CoreCog
from bot.core.i18n import load_locales, set_guild_language

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n(tmp_path: Path) -> None:
    """Load custom locale overrides that differ from hardcoded strings.

    This proves t() is being called — if the embed contains our custom
    text, the migration works; if it contains the old hardcoded text, it
    doesn't.
    """
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    # Custom es locale with distinctive strings
    es_data = {
        "common": {
            "footer": "NB • {timestamp}",
            "error": {"title": "ERR"},
        },
        "core": {
            "ping": {
                "title": "TEST_PONG",
                "description": "WS: **{latency}ms**",
            },
            "status": {
                "title": "TEST_STATUS",
                "db_field": "DB_FIELD",
                "db_connected": "DB_OK",
                "db_unreachable": "DB_FAIL",
                "cache_field": "CACHE_FIELD",
                "cache_ok": "CACHE_OK_{count}",
                "cache_none": "CACHE_NONE",
                "guild_config_field": "GUILD_FIELD",
                "guild_config_dm": "GUILD_DM",
                "guild_config_loaded": "LOADED {prefix} {language}",
                "guild_config_missing": "GUILD_MISSING",
                "latency_field": "LAT_FIELD",
                "latency_value": "{latency}ms",
                "footer": "NB_CORE",
            },
            "help": {
                "title": "HELP_{module}",
                "description": "{count} cmds {prefix} /",
                "no_module": "NO_MOD_{module}",
                "no_module_desc": "USE_HELP",
                "no_commands": "NO_CMDS",
                "footer": "NB_HELP",
                "prev_button": "PREV",
                "next_button": "NEXT",
            },
            "sync": {
                "title": "SYNC_OK",
                "description": "{count} synced",
                "failed_title": "SYNC_FAIL",
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
    """Return a mock NebulosaBot with latency."""
    bot = MagicMock(spec=commands.Bot)
    bot.latency = 0.042  # 42ms
    bot.cogs = {"Core": MagicMock(), "Utility": MagicMock(), "Ocio": MagicMock()}
    for cog in bot.cogs.values():
        cog.get_commands.return_value = []
    return bot


@pytest.fixture
def cog(mock_bot: MagicMock) -> CoreCog:
    """Return a fresh CoreCog with mocked bot."""
    return CoreCog(mock_bot)


def _make_ctx(
    guild_id: int | None = _GUILD_ID,
) -> MagicMock:
    """Build a mock NebulosaContext for CoreCog tests."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.guild = MagicMock(spec=discord.Guild) if guild_id else None
    if ctx.guild:
        ctx.guild.id = guild_id
    ctx.guild_config = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.display_name = "TestUser"
    return ctx


# ---------------------------------------------------------------------------
# /ping — calls t()
# ---------------------------------------------------------------------------


class TestPingI18n:
    """Tests for /ping with i18n."""

    @pytest.mark.asyncio
    async def test_ping_title_from_locale(self, cog: CoreCog) -> None:
        """Ping embed title MUST use t(), not a hardcoded string."""
        ctx = _make_ctx()
        await cog.ping.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        # If t() is used, we get our custom locale string
        assert embed.title == "TEST_PONG"

    @pytest.mark.asyncio
    async def test_ping_description_from_locale(self, cog: CoreCog) -> None:
        """Ping embed description MUST use t() with interpolated latency."""
        ctx = _make_ctx()
        await cog.ping.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "42ms" in embed.description


# ---------------------------------------------------------------------------
# /status — calls t()
# ---------------------------------------------------------------------------


class TestStatusI18n:
    """Tests for /status with i18n."""

    @pytest.mark.asyncio
    async def test_status_title_from_locale(self, cog: CoreCog) -> None:
        """Status embed title MUST use t()."""
        cog.bot.db = AsyncMock()
        cog.bot.db.health_check = AsyncMock(return_value=True)
        cog.bot.cache = MagicMock()
        cog.bot.cache._store = {}

        ctx = _make_ctx()
        ctx.guild_config = MagicMock()
        ctx.guild_config.prefix = "nb!"
        ctx.guild_config.language = "es"

        await cog.status.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "TEST_STATUS" in embed.title

    @pytest.mark.asyncio
    async def test_status_db_field_from_locale(self, cog: CoreCog) -> None:
        """Status DB field name MUST use t()."""
        cog.bot.db = AsyncMock()
        cog.bot.db.health_check = AsyncMock(return_value=True)
        cog.bot.cache = MagicMock()
        cog.bot.cache._store = {}

        ctx = _make_ctx()
        ctx.guild_config = MagicMock()
        ctx.guild_config.prefix = "nb!"
        ctx.guild_config.language = "es"

        await cog.status.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert "DB_FIELD" in fields
        assert "CACHE_FIELD" in fields


# ---------------------------------------------------------------------------
# /help — calls t()
# ---------------------------------------------------------------------------


class TestHelpI18n:
    """Tests for /help with i18n."""

    @pytest.mark.asyncio
    async def test_help_unknown_module_error_from_locale(
        self, cog: CoreCog,
    ) -> None:
        """Help error for unknown module MUST use t()."""
        cog.bot.get_cog = MagicMock(return_value=None)

        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, module="Foo")

        embed = ctx.send.call_args[1]["embed"]
        assert "NO_MOD_Foo" in embed.title


# ---------------------------------------------------------------------------
# /sync — calls t()
# ---------------------------------------------------------------------------


class TestSyncI18n:
    """Tests for /sync with i18n."""

    @pytest.mark.asyncio
    async def test_sync_title_from_locale(self, cog: CoreCog) -> None:
        """Sync success embed title MUST use t()."""
        ctx = _make_ctx()
        ctx.defer = AsyncMock()
        cog.bot.tree = AsyncMock()
        cog.bot.tree.sync = AsyncMock(return_value=[MagicMock()])

        # Mock is_admin check to pass
        with patch("bot.cogs.core.is_admin", return_value=lambda f: f):
            await cog.sync.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        assert "SYNC_OK" in embed.title
