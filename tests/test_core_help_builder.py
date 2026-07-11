"""Unit tests for help builder internals in bot.cogs.core.

Tests _build_cog_help_embed, _build_help_pages, and _resolve_prefix
using mock bot/cog/context objects. No Discord API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.core import _build_cog_help_embed, _build_help_pages, _resolve_prefix
from bot.constants import FALLBACK_PREFIX
from bot.core.i18n import load_locales, set_guild_language

# Ensure real locales are loaded for i18n-aware tests.
load_locales()


def _make_command(name: str, description: str = "", hidden: bool = False, hybrid: bool = False) -> commands.Command:
    """Create a minimal Command or HybridCommand mock for testing."""
    if hybrid:
        cmd = MagicMock(spec=commands.HybridCommand)
        # isinstance check needs to work
        cmd.__class__ = commands.HybridCommand
    else:
        cmd = MagicMock(spec=commands.Command)
        cmd.__class__ = commands.Command
    cmd.name = name
    cmd.description = description
    cmd.hidden = hidden
    return cmd


def _make_cog(commands_list: list) -> MagicMock:
    """Create a mock cog that returns the given commands."""
    cog = MagicMock()
    cog.get_commands.return_value = commands_list
    return cog


def _make_bot(cogs_map: dict[str, MagicMock]) -> MagicMock:
    """Create a mock bot with the given cog name → cog mapping."""
    bot = MagicMock()
    bot.cogs = cogs_map
    bot.get_cog.side_effect = lambda name: cogs_map.get(name)
    return bot


def _make_ctx(prefix: str | None = None, guild_id: int = 123456789) -> MagicMock:
    """Create a mock NebulosaContext with optional guild config."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    if prefix is not None:
        ctx.guild_config = MagicMock()
        ctx.guild_config.prefix = prefix
    else:
        ctx.guild_config = None
    return ctx


# ---------------------------------------------------------------------------
# _resolve_prefix
# ---------------------------------------------------------------------------


class TestResolvePrefix:
    """_resolve_prefix reads guild config prefix or falls back to default."""

    def test_prefix_from_guild_config(self) -> None:
        """Guild with custom prefix returns that prefix."""
        ctx = _make_ctx(prefix="!")
        assert _resolve_prefix(ctx) == "!"

    def test_prefix_fallback_no_guild(self) -> None:
        """DM context (no guild) returns FALLBACK_PREFIX."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.guild_config = None
        assert _resolve_prefix(ctx) == FALLBACK_PREFIX

    def test_prefix_fallback_no_config(self) -> None:
        """Guild present but no config returns FALLBACK_PREFIX."""
        ctx = _make_ctx(prefix=None)
        assert _resolve_prefix(ctx) == FALLBACK_PREFIX


# ---------------------------------------------------------------------------
# _build_cog_help_embed
# ---------------------------------------------------------------------------


class TestBuildCogHelpEmbed:
    """_build_cog_help_embed returns embed for visible commands, None otherwise."""

    def test_returns_embed_for_visible_commands(self) -> None:
        """Cog with 3 visible hybrid commands produces an embed with 3 fields."""
        cmd1 = _make_command("ping", description="Check latency", hybrid=True)
        cmd2 = _make_command("help", description="Show help", hybrid=True)
        cmd3 = _make_command("status", description="Bot status", hybrid=True)
        cog = _make_cog([cmd1, cmd2, cmd3])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!")

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert len(embed.fields) == 3

    def test_returns_none_for_empty_cog(self) -> None:
        """Cog with no visible commands returns None."""
        hidden = _make_command("secret", hidden=True)
        cog = _make_cog([hidden])
        bot = _make_bot({"Core": cog})

        assert _build_cog_help_embed(bot, "Core", "nb!") is None

    def test_returns_none_for_missing_cog(self) -> None:
        """Non-existent cog name returns None."""
        bot = _make_bot({})

        assert _build_cog_help_embed(bot, "Nonexistent", "nb!") is None

    def test_hybrid_commands_show_slash_suffix(self) -> None:
        """Hybrid commands get [prefix + slash] suffix in field value."""
        cmd = _make_command("ping", description="Check latency", hybrid=True)
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!")
        assert embed is not None
        assert "[prefix + slash]" in embed.fields[0].value

    def test_prefix_only_commands_show_prefix_suffix(self) -> None:
        """Non-hybrid commands get [prefix] suffix in field value."""
        cmd = _make_command("legacy", description="Old command", hybrid=False)
        cog = _make_cog([cmd])
        bot = _make_bot({"Legacy": cog})

        embed = _build_cog_help_embed(bot, "Legacy", "nb!")
        assert embed is not None
        assert "[prefix]" in embed.fields[0].value


# ---------------------------------------------------------------------------
# _build_help_pages
# ---------------------------------------------------------------------------


class TestBuildHelpPages:
    """_build_help_pages produces one embed per cog with visible commands."""

    def test_multiple_cogs_produce_multiple_pages(self) -> None:
        """3 cogs (2 with commands, 1 empty) produce exactly 2 embeds."""
        cmd1 = _make_command("ping", description="Ping", hybrid=True)
        cmd2 = _make_command("warn", description="Warn user", hybrid=True)
        empty_cog = _make_cog([])

        cogs = {
            "Core": _make_cog([cmd1]),
            "Sentinel": _make_cog([cmd2]),
            "Empty": empty_cog,
        }
        bot = _make_bot(cogs)
        ctx = _make_ctx(prefix="nb!")

        pages = _build_help_pages(bot, ctx)

        assert len(pages) == 2

    def test_all_empty_cogs_produce_no_pages(self) -> None:
        """All cogs empty → empty list."""
        cogs = {
            "Empty1": _make_cog([]),
            "Empty2": _make_cog([]),
        }
        bot = _make_bot(cogs)
        ctx = _make_ctx(prefix="nb!")

        pages = _build_help_pages(bot, ctx)

        assert pages == []


# ---------------------------------------------------------------------------
# Localized command descriptions in help embed
# ---------------------------------------------------------------------------


def _make_locale_str_command(
    name: str,
    *,
    es_description: str,
    key: str,
    hybrid: bool = True,
) -> commands.Command:
    """Create a mock command whose description is a locale_str (Spanish default).

    Mirrors how production decorators attach ``locale_str(message, key=...)``.
    The ``cmd.description`` attribute is the Spanish message string.
    """
    if hybrid:
        cmd = MagicMock(spec=commands.HybridCommand)
        cmd.__class__ = commands.HybridCommand
    else:
        cmd = MagicMock(spec=commands.Command)
        cmd.__class__ = commands.Command
    cmd.name = name
    cmd.description = es_description  # locale_str.message = Spanish string
    cmd.hidden = False
    return cmd


class TestHelpDescriptionsLocalized:
    """_build_cog_help_embed MUST resolve descriptions via SLASH_DESCRIPTIONS + t().

    Defect JD-B-FULL-001: cmd.description is the Spanish locale_str.message;
    English guilds must see the English translation from locale files.
    """

    def test_english_guild_sees_english_description(self) -> None:
        """English guild MUST see the English description, not the Spanish default."""
        set_guild_language("eng_guild", "en")
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!", guild_id="eng_guild")

        assert embed is not None
        field_value = embed.fields[0].value
        # English description from en.json for slash.descriptions.ping
        assert "WebSocket latency" in field_value
        # Must NOT contain the Spanish text
        assert "Muestra la latencia" not in field_value

    def test_spanish_guild_sees_spanish_description(self) -> None:
        """Spanish guild MUST see the Spanish description."""
        set_guild_language("spa_guild", "es")
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!", guild_id="spa_guild")

        assert embed is not None
        field_value = embed.fields[0].value
        # Spanish description from es.json for slash.descriptions.ping
        assert "latencia WebSocket" in field_value

    def test_unknown_command_uses_raw_description_fallback(self) -> None:
        """Command NOT in SLASH_DESCRIPTIONS falls back to raw cmd.description."""
        set_guild_language("eng_guild2", "en")
        cmd = _make_locale_str_command(
            "custom_cmd",
            es_description="Some raw description",
            key="slash.descriptions.custom_cmd",  # not in registry
        )
        cmd.name = "custom_cmd"
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!", guild_id="eng_guild2")

        assert embed is not None
        assert "Some raw description" in embed.fields[0].value

    def test_none_guild_id_uses_default_locale(self) -> None:
        """guild_id=None MUST use the default locale (Spanish)."""
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", "nb!", guild_id=None)

        assert embed is not None
        assert "latencia WebSocket" in embed.fields[0].value
