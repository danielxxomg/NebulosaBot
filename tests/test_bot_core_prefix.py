"""Slash-only prefix surface: the text-prefix resolver MUST be inert.

bot-core spec (cycle-5-quality-zero delta):
    - Prefix invocation is inert  -> ``nb!ping`` invokes nothing
    - Comma invocation is inert outside ticket channels -> ``,ping`` invokes
      nothing (the ticket-channel ``,`` timer lives in TicketsCog.on_message,
      governed by close-confirmation and out of scope here)
    - Zero text-invocable commands -> the resolver never consults guild config

Strict TDD: RED phase — written BEFORE the implementation change.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.bot import NebulosaBot, _noop_prefix
from bot.config import BotConfig


def _make_config() -> BotConfig:
    """Minimal BotConfig for tests."""
    return BotConfig(
        discord_token="t",
        supabase_url="https://x.supabase.co",
        supabase_key="k",
    )


def _make_bot() -> NebulosaBot:
    """Construct a real NebulosaBot (cheap — no gateway connection)."""
    return NebulosaBot(config=_make_config(), intents=discord.Intents.default())


def _make_message(guild_id: int | None) -> MagicMock:
    """Return a mock discord.Message for prefix-resolution tests."""
    msg = MagicMock(spec=discord.Message)
    msg.guild = None if guild_id is None else MagicMock(spec=discord.Guild)
    if msg.guild is not None:
        msg.guild.id = guild_id
    return msg


class TestNoopPrefixInertness:
    """The resolver MUST return [] unconditionally — prefix surface is dead."""

    @pytest.mark.asyncio
    async def test_guild_with_config_returns_empty_list(self) -> None:
        """`nb!ping` is inert: resolver returns [] and never reads config."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(prefix="nb!"))

        result = await _noop_prefix(bot, _make_message(123456789))

        assert result == [], "prefix resolver MUST be inert ([]) for guild messages"
        bot.guild_service.get_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_comma_is_inert_outside_ticket_channels(self) -> None:
        """`,` no longer acts as a framework command prefix anywhere."""
        bot = _make_bot()
        bot.guild_service = None

        # A `,ping` message resolves through get_context with an empty prefix
        # list — the resolver itself must not yield "," under any circumstance.
        result = await _noop_prefix(bot, _make_message(123456789))

        assert result == [], "',' MUST NOT resolve as a command prefix"
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_dm_message_returns_empty_list(self) -> None:
        """DM messages (no guild) also resolve to an empty prefix list."""
        bot = _make_bot()
        bot.guild_service = MagicMock()

        result = await _noop_prefix(bot, _make_message(None))

        assert result == []

    @pytest.mark.asyncio
    async def test_custom_guild_config_is_ignored(self) -> None:
        """A configured guild prefix MUST be unread — zero text commands exist."""
        bot = _make_bot()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(prefix="!"))

        result = await _noop_prefix(bot, _make_message(42))

        assert result == []


class TestResolverContract:
    """Structural contract: static module-level callable wired as command_prefix."""

    def test_resolver_signature_matches_discord_py_expectation(self) -> None:
        """Keep the (bot, message) -> list[str] signature discord.py expects."""
        sig = inspect.signature(_noop_prefix)
        assert len(sig.parameters) == 2, "resolver MUST take (bot, message)"
        assert inspect.iscoroutinefunction(_noop_prefix)

    def test_command_prefix_is_the_static_resolver(self) -> None:
        """NebulosaBot wires _noop_prefix directly — no closure over services."""
        bot = _make_bot()
        assert bot.command_prefix is _noop_prefix
