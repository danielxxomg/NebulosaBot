"""Shared test fixtures for NebulosaBot unit tests.

Provides mocked Database, real TTLCache, sample GuildConfig, and Discord
mock objects that avoid hitting the real Discord API or Supabase.
"""

from __future__ import annotations

import asyncio
import selectors
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.cache import TTLCache
from bot.core.database import Database
from bot.models.guild import GuildConfig


# ---------------------------------------------------------------------------
# Event-loop factory — force PollSelector on Python ≥ 3.14
# ---------------------------------------------------------------------------
# Python 3.14's asyncio.Runner + EpollSelector can hit OSError EINVAL
# (epoll fd invalidated) when many function-scoped loops are created and
# destroyed in a single pytest session.  PollSelector avoids the epoll
# syscall entirely and eliminates the flake.  See GH issue #TBD.


@pytest.fixture(scope="session")
def _asyncio_loop_factory():
    """Return a loop factory that uses PollSelector instead of EpollSelector."""

    def _factory() -> asyncio.AbstractEventLoop:
        return asyncio.SelectorEventLoop(selectors.PollSelector())

    return _factory


# ---------------------------------------------------------------------------
# Infrastructure fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache() -> TTLCache:
    """Return a fresh, empty TTLCache instance."""
    return TTLCache()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return an AsyncMock standing in for the Database class.

    ``get_guild`` and ``upsert_guild`` are AsyncMock instances so callers
    can set ``return_value`` / ``side_effect`` per test.
    """
    db = AsyncMock(spec=Database)
    db.get_guild = AsyncMock()
    db.upsert_guild = AsyncMock()
    return db


@pytest.fixture
def mod_role_cache() -> dict[int, str]:
    """Return a fresh dict used by GuildService as the mod-role lookup."""
    return {}


# ---------------------------------------------------------------------------
# Model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> GuildConfig:
    """Return a representative GuildConfig for testing."""
    return GuildConfig(
        id="123456789",
        prefix="!",
        language="en",
        mod_role_id="987654321",
    )


@pytest.fixture
def default_config() -> GuildConfig:
    """Return the default GuildConfig (as created on guild join)."""
    return GuildConfig(id="999888777", prefix="nb!", language="es")


# ---------------------------------------------------------------------------
# Discord mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_guild() -> MagicMock:
    """Return a MagicMock standing in for discord.Guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    return guild


@pytest.fixture
def mock_member() -> MagicMock:
    """Return a MagicMock standing in for discord.Member (no roles)."""
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    member.roles = []
    return member


@pytest.fixture
def mock_admin_member() -> MagicMock:
    """Return a MagicMock standing in for a discord.Member with Administrator."""
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = True
    member.roles = []
    return member


@pytest.fixture
def mock_mod_member() -> MagicMock:
    """Return a MagicMock standing in for a Member with a moderator role."""
    role = MagicMock(spec=discord.Role)
    role.id = 987654321

    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    member.roles = [role]
    return member


@pytest.fixture
def mock_interaction(mock_guild: MagicMock, mock_member: MagicMock) -> MagicMock:
    """Return a MagicMock standing in for discord.Interaction in a guild.

    Exposes ``guild``, ``user``, ``client``, and ``guild_id``.
    Callers can override individual attributes per test.
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = mock_guild
    interaction.user = mock_member
    interaction.client = MagicMock()
    interaction.guild_id = mock_guild.id
    return interaction
