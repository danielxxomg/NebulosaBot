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

import discord
import pytest
from discord import app_commands
from discord.ext import commands, tasks

import bot.cogs.core
import bot.cogs.core as core_mod
from bot.cogs.core import CoreCog, _InteractionCtx
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


# ---------------------------------------------------------------------------
# cov-headroom-guard — branch exits for bot/cogs/core.py (merged from
# tests/test_core_branch_coverage.py; file cap: 181 — see verify-report
# CRITICAL #1 / tasks Phase 5)
# ---------------------------------------------------------------------------


def _mock_core_bot(**kw: object) -> MagicMock:
    bot = MagicMock()
    bot.latency = 0.05
    bot.guilds = []
    bot.cache = None
    bot.db = None
    bot.cogs = {}
    bot.get_cog.return_value = None
    for k, v in kw.items():
        setattr(bot, k, v)
    return bot


def test_is_interaction_and_guild_id_and_prefix() -> None:
    inter = MagicMock(spec=discord.Interaction)
    inter.response = MagicMock()
    inter.user = MagicMock()
    assert core_mod._is_interaction(inter) is True
    assert core_mod._is_interaction(object()) is False
    assert core_mod._guild_id_from_source(MagicMock(guild=MagicMock(id=123))) == 123
    assert core_mod._guild_id_from_source(MagicMock(guild=None)) is None
    assert core_mod._resolve_prefix(123) == []
    assert core_mod._resolve_prefix(None) == []


@pytest.mark.asyncio
async def test_interaction_ctx_send_and_defer() -> None:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock()
    inter.user = MagicMock()
    inter.channel = MagicMock()
    inter.response.is_done.return_value = False
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.followup.send = AsyncMock()
    ctx = _InteractionCtx(inter, MagicMock())
    assert ctx.guild is inter.guild
    await ctx.send(embed=MagicMock())
    inter.response.send_message.assert_awaited_once()
    await ctx.defer(ephemeral=True)
    inter.response.defer.assert_awaited_once()
    # followup branch
    inter.response.is_done.return_value = True
    await ctx.send(embed=MagicMock())
    inter.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_via_and_ping_status_help() -> None:
    bot = _mock_core_bot()
    cog = CoreCog(bot)

    # _send_via
    ctx = make_ctx(guild_id=1)
    _src, is_inter = await cog._send_via(ctx)
    assert is_inter is False
    inter = MagicMock(spec=discord.Interaction)
    inter.user = MagicMock()
    inter.response = MagicMock()
    _, is_inter2 = await cog._send_via(inter)
    assert is_inter2 is True

    # ping/status/help via shim vs slash (parametrized-style shorthand: one function exercises the distinct shim vs slash paths)
    ping_ctx = make_ctx(guild_id=1)
    await cog.ping.callback(cog, ping_ctx)
    assert ping_ctx.send.await_count == 1
    embed = ping_ctx.send.call_args.kwargs["embed"]
    assert embed.title is not None

    # status shim
    status_ctx = make_ctx(guild_id=1)
    status_ctx.guild_config = None
    await cog.status.callback(cog, status_ctx)
    assert status_ctx.send.await_count == 1

    # status slash
    bot2 = _mock_core_bot()
    bot2.guild_service = MagicMock()
    bot2.guild_service.get_config = AsyncMock(return_value=None)
    cog2 = CoreCog(bot2)
    inter2 = MagicMock(spec=discord.Interaction)
    inter2.guild = MagicMock()
    inter2.guild.id = 1
    inter2.response.send_message = AsyncMock()
    await cog2.status.callback(cog2, inter2)
    inter2.response.send_message.assert_awaited_once()

    # help shim
    help_bot = _mock_core_bot()
    help_bot.cogs = {"Core": MagicMock()}
    help_bot.cogs["Core"].get_commands.return_value = []
    help_bot.get_cog.side_effect = lambda n: help_bot.cogs.get(n)
    help_bot.cogs["Core"].walk_app_commands.return_value = []
    cog3 = CoreCog(help_bot)
    help_ctx = make_ctx(guild_id=1)
    await cog3.help_command.callback(cog3, help_ctx, module=None)
    assert help_ctx.send.await_count == 1

    # help slash + module lookup
    pag_bot = _mock_core_bot()
    cmd = MagicMock()
    cmd.name = "ping"
    cmd.description = "desc"
    cmd.hidden = False
    cmd.qualified_name = "ping"
    cog_obj = MagicMock()
    cog_obj.get_commands.return_value = [cmd]
    pag_bot.cogs = {"Core": cog_obj}
    pag_bot.get_cog.side_effect = lambda n: pag_bot.cogs.get(n)
    cog4 = CoreCog(pag_bot)
    mod_ctx = make_ctx(guild_id=1)
    await cog4.help_command.callback(cog4, mod_ctx, module="Core")
    assert mod_ctx.send.await_count == 1
    unk_ctx = make_ctx(guild_id=1)
    await cog4.help_command.callback(cog4, unk_ctx, module="Missing")
    assert unk_ctx.send.await_count == 1


@pytest.mark.parametrize(
    ("hidden", "group_child"),
    [
        pytest.param(True, False, id="hidden-filtered"),
        pytest.param(False, True, id="group-expansion"),
    ],
)
def test_build_cog_help_embed_hidden_and_group(hidden: bool, group_child: bool) -> None:
    """_build_cog_help_embed: hidden filtered + group walk expansion (tightened vs the smoke ``or`` — distinct behavioral postconditions per case)."""
    bot = _mock_core_bot()
    if hidden:
        h = MagicMock()
        h.hidden = True
        h.name = "secret"
        cog = MagicMock()
        cog.get_commands.return_value = [h]
        cog.walk_app_commands.return_value = []
        bot.get_cog.return_value = cog
        assert core_mod._build_cog_help_embed(bot, "Core", guild_id=1) is None
        return
    # Tightened (verify-report WARNING @167-169): group path MUST assert a real outcome,
    # not ``embed is None or isinstance``. Miss by trimmed name → None; exact hit → embed with child field.
    cog2 = MagicMock()
    cog2.get_commands.return_value = []
    child = MagicMock(spec=app_commands.Command)
    child.name = "child"
    child.hidden = False
    child.qualified_name = "grp child"
    group = MagicMock(spec=app_commands.Group)
    group.walk_commands.return_value = [child]
    cog2.walk_app_commands.return_value = [group]
    bot.cogs = {}
    bot.get_cog.side_effect = lambda n: bot.cogs.get(n) if isinstance(n, str) else None
    # Provide cog2 via dict only when name matches after strip semantics expected by the parametrized contract
    # Original smoke used return_value (always hit) for " grp " — tightened expects dict-hit semantics:
    #   " grp ".strip() != "Core" → miss → None; "Core" → hit → embed
    bot.cogs["Core"] = cog2
    assert core_mod._build_cog_help_embed(bot, " grp ", guild_id=None) is None
    embed = core_mod._build_cog_help_embed(bot, "Core", guild_id=1)
    assert embed is not None
    assert isinstance(embed, discord.Embed)
    assert any(f.name == "`/child`" for f in embed.fields)
