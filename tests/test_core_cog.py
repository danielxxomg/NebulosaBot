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
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import commands, tasks

import bot.cogs.core
from bot.cogs.core import CoreCog
from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales, set_guild_language
from tests.conftest import make_ctx

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
                "guild_config_loaded": "LOADED {language}",
                "guild_config_missing": "GUILD_MISSING",
                "latency_field": "LAT_FIELD",
                "latency_value": "{latency}ms",
                "footer": "NB_CORE",
            },
            "help": {
                "title": "HELP_{module}",
                "description": "{count} cmds /",
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
    """Shared factory plus CoreCog extras (config attr, display name)."""
    ctx = make_ctx(guild_id=guild_id)
    ctx.guild_config = None
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
        ctx.guild_config.language = "es"

        await cog.status.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert "DB_FIELD" in fields
        assert "CACHE_FIELD" in fields

    @pytest.mark.asyncio
    async def test_status_guild_config_field_has_no_prefix(self, cog: CoreCog) -> None:
        """Slash-only policy: the guild-config field MUST NOT mention a prefix."""
        cog.bot.db = AsyncMock()
        cog.bot.db.health_check = AsyncMock(return_value=True)
        cog.bot.cache = MagicMock()
        cog.bot.cache._store = {}

        ctx = _make_ctx()
        ctx.guild_config = MagicMock()
        ctx.guild_config.language = "es"

        await cog.status.callback(cog, ctx)

        embed = ctx.send.call_args[1]["embed"]
        fields = {f.name: f.value for f in embed.fields}
        value = fields["GUILD_FIELD"]
        assert value == "LOADED es", "guild_config_loaded must interpolate language only"
        assert "nb!" not in value and "prefix" not in value.lower()


# ---------------------------------------------------------------------------
# /help — calls t()
# ---------------------------------------------------------------------------


class TestHelpI18n:
    """Tests for /help with i18n."""

    @pytest.mark.asyncio
    async def test_help_unknown_module_error_from_locale(
        self,
        cog: CoreCog,
        mock_bot: MagicMock,
    ) -> None:
        """Help error for unknown module MUST use t()."""
        mock_bot.get_cog = MagicMock(return_value=None)

        ctx = _make_ctx()
        await cog.help_command.callback(cog, ctx, module="Foo")

        embed = ctx.send.call_args[1]["embed"]
        assert "NO_MOD_Foo" in embed.title


# ---------------------------------------------------------------------------
# /sync — calls t()
# ---------------------------------------------------------------------------


class TestSyncI18n:
    """Tests for /sync — removed in S6A (core-commands REMOVED)."""

    def test_sync_removed(self) -> None:
        """S6A.3: /sync must not exist — command deletion precedes survivor migration."""
        assert not hasattr(CoreCog, "sync"), "/sync must be deleted (S6A.3)"
        src = Path(bot.cogs.core.__file__).read_text(encoding="utf-8")
        assert "def sync(" not in src
        assert "hybrid_command" not in src or "sync" not in src.split("hybrid_command")[1][:500]  # noqa: S101 -- allow assert
        # slash tree sync stays in setup_hook
        assert "tree.sync" not in src


# ---------------------------------------------------------------------------
# S4.6 — resource-log background task
# ---------------------------------------------------------------------------


class TestResourceLogLoop:
    """CoreCog logs a resource snapshot every 5 minutes (AGENTS.md loop rules)."""

    def test_loop_registered_five_minutes(self, cog: CoreCog) -> None:
        loop = cog.resource_log_loop
        assert isinstance(loop, tasks.Loop)
        # discord.py only materializes the computed interval at start time;
        # the declared cadence is pinned structurally in the source test below.
        assert loop.coro.__name__ == "resource_log_loop"

    def test_loop_wiring_structural(self) -> None:
        """before_loop waits ready; cog_unload cancels the loop."""
        src = Path(bot.cogs.core.__file__).read_text(encoding="utf-8")
        assert "@tasks.loop(minutes=5)" in src
        assert "wait_until_ready" in src
        assert ".before_loop" in src
        assert "self.resource_log_loop.cancel()" in src

    @pytest.mark.asyncio
    async def test_tick_logs_rss_cache_and_guilds(
        self,
        cog: CoreCog,
        mock_bot: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mock_bot.cache = MagicMock()
        mock_bot.cache.size = 7
        mock_bot.guilds = [MagicMock(), MagicMock(), MagicMock()]

        with caplog.at_level(logging.INFO, logger="bot.cogs.core"):
            await cog._log_resource_usage()

        messages = [r.getMessage() for r in caplog.records]
        assert any("ru_maxrss=" in m and "cache_entries=7" in m and "guilds=3" in m for m in messages), messages

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_running_loop(self, cog: CoreCog) -> None:
        with (
            patch.object(cog.resource_log_loop, "is_running", return_value=True),
            patch.object(cog.resource_log_loop, "cancel") as cancel_mock,
        ):
            await cog.cog_unload()
        cancel_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_skips_idle_loop(self, cog: CoreCog) -> None:
        with (
            patch.object(cog.resource_log_loop, "is_running", return_value=False),
            patch.object(cog.resource_log_loop, "cancel") as cancel_mock,
        ):
            await cog.cog_unload()
        cancel_mock.assert_not_called()
