"""Unit tests for help builder internals in bot.cogs.core.

Tests _build_cog_help_embed, _build_help_pages, and _resolve_prefix
using mock bot/cog/context objects. No Discord API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
from discord.ext import commands

from bot.cogs.core import _build_cog_help_embed, _build_help_pages, _resolve_prefix
from bot.constants import FALLBACK_PREFIX


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
