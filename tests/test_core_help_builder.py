"""Unit tests for help builder internals in bot.cogs.core.

Tests _build_cog_help_embed and _build_help_pages using mock bot/cog/context
objects. No Discord API calls. Slash-only policy: every entry renders
``/command`` syntax (prefix resolution was removed with the inert prefix
surface — see tests/test_bot_core_prefix.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
from discord.ext import commands

from bot.cogs.core import _build_cog_help_embed, _build_help_pages
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


def _make_ctx(guild_id: int = 123456789) -> MagicMock:
    """Create a mock NebulosaContext (guild config no longer read by builders)."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.guild_config = None
    return ctx


# ---------------------------------------------------------------------------
# Slash-only help syntax (cycle-5-quality-zero, bot-core spec)
# ---------------------------------------------------------------------------


class TestHelpSlashOnlySyntax:
    """Help output MUST show /command syntax only — zero prefix examples."""

    def test_entries_show_slash_name_only(self) -> None:
        """Every entry renders as `/name` — no prefix-prefixed variants."""
        cmd = _make_command("ping", description="Check latency", hybrid=True)
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=None)

        assert embed is not None
        assert embed.fields[0].name == "`/ping`"

    def test_prefix_only_commands_also_show_slash_syntax(self) -> None:
        """Non-hybrid legacy entries still display `/name` (no `[prefix]` suffix)."""
        cmd = _make_command("legacy", description="Old command", hybrid=False)
        cog = _make_cog([cmd])
        bot = _make_bot({"Legacy": cog})

        embed = _build_cog_help_embed(bot, "Legacy", guild_id=None)

        assert embed is not None
        assert embed.fields[0].name == "`/legacy`"
        assert embed.fields[0].value is not None and "[prefix]" not in embed.fields[0].value

    def test_no_hybrid_suffix_in_values(self) -> None:
        """The `[prefix + slash]` suffix is gone from every entry."""
        cmd = _make_command("ping", description="Check latency", hybrid=True)
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=None)

        assert embed is not None
        assert embed.fields[0].value is not None and "[prefix" not in embed.fields[0].value

    def test_no_prefix_example_in_embed_text(self) -> None:
        """Real locales: neither the fallback nor any `Prefix:` line appears."""
        cmd = _make_command("ping", description="Check latency", hybrid=True)
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=None)

        assert embed is not None
        description = embed.description or ""
        assert "nb!" not in description
        assert "Prefijo" not in description and "Prefix" not in description


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

        embed = _build_cog_help_embed(bot, "Core")

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert len(embed.fields) == 3

    def test_returns_none_for_empty_cog(self) -> None:
        """Cog with no visible commands returns None."""
        hidden = _make_command("secret", hidden=True)
        cog = _make_cog([hidden])
        bot = _make_bot({"Core": cog})

        assert _build_cog_help_embed(bot, "Core") is None

    def test_returns_none_for_missing_cog(self) -> None:
        """Non-existent cog name returns None."""
        bot = _make_bot({})

        assert _build_cog_help_embed(bot, "Nonexistent") is None

    def test_field_values_have_no_visibility_suffix(self) -> None:
        """Entries carry the plain localized description — no suffix markers."""
        cmd = _make_command("ping", description="Check latency", hybrid=True)
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core")
        assert embed is not None
        value = embed.fields[0].value
        assert value is not None and "[prefix" not in value


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
        ctx = _make_ctx()

        pages = _build_help_pages(bot, ctx)

        assert len(pages) == 2

    def test_all_empty_cogs_produce_no_pages(self) -> None:
        """All cogs empty → empty list."""
        cogs = {
            "Empty1": _make_cog([]),
            "Empty2": _make_cog([]),
        }
        bot = _make_bot(cogs)
        ctx = _make_ctx()

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
        set_guild_language("111111111", "en")
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=111111111)

        assert embed is not None
        assert embed.fields[0].value is not None
        field_value = embed.fields[0].value
        # English description from en.json for slash.descriptions.ping
        assert "WebSocket latency" in field_value
        # Must NOT contain the Spanish text
        assert "Muestra la latencia" not in field_value

    def test_spanish_guild_sees_spanish_description(self) -> None:
        """Spanish guild MUST see the Spanish description."""
        set_guild_language("222222222", "es")
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=222222222)

        assert embed is not None
        assert embed.fields[0].value is not None
        field_value = embed.fields[0].value
        # Spanish description from es.json for slash.descriptions.ping
        assert "latencia WebSocket" in field_value

    def test_unknown_command_uses_raw_description_fallback(self) -> None:
        """Command NOT in SLASH_DESCRIPTIONS falls back to raw cmd.description."""
        set_guild_language("333333333", "en")
        cmd = _make_locale_str_command(
            "custom_cmd",
            es_description="Some raw description",
            key="slash.descriptions.custom_cmd",  # not in registry
        )
        cmd.name = "custom_cmd"
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=333333333)

        assert embed is not None
        assert embed.fields[0].value is not None and "Some raw description" in embed.fields[0].value

    def test_empty_description_uses_localized_fallback(self) -> None:
        """Commands with no description MUST get the localized fallback text.

        Blocks the hardcoded 'No description.' English literal — user-facing
        strings in cogs go through t() (AGENTS.md i18n rule).
        """
        set_guild_language("444444444", "en")
        cmd = _make_locale_str_command(
            "custom_cmd",
            es_description="",
            key="slash.descriptions.custom_cmd",
        )
        cmd.name = "custom_cmd"
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=444444444)

        assert embed is not None
        value = embed.fields[0].value or ""
        assert value == "No description available yet.", "must resolve via core.help.no_description"

    def test_none_guild_id_uses_default_locale(self) -> None:
        """guild_id=None MUST use the default locale (Spanish)."""
        cmd = _make_locale_str_command(
            "ping",
            es_description="Muestra la latencia WebSocket del bot.",
            key="slash.descriptions.ping",
        )
        cog = _make_cog([cmd])
        bot = _make_bot({"Core": cog})

        embed = _build_cog_help_embed(bot, "Core", guild_id=None)

        assert embed is not None
        assert embed.fields[0].value is not None and "latencia WebSocket" in embed.fields[0].value
