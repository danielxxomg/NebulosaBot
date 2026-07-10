"""Shared test fixtures for NebulosaBot unit tests.

Provides mocked Database, real TTLCache, sample GuildConfig, and Discord
mock objects that avoid hitting the real Discord API or Supabase.

Also provides ``frozen_clock`` — a deterministic ``datetime.now()`` fixture
using ``freezegun`` to eliminate date-time flake risk under ``pytest-randomly``.
"""

from __future__ import annotations

import asyncio
import gc
import selectors
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from freezegun import freeze_time

from bot.core.cache import TTLCache
from bot.core.database import Database
from bot.core.i18n import load_locales
from bot.models.guild import GuildConfig

# Frozen deterministic timestamp: 2024-06-15 12:00:00 UTC
_FROZEN_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Load real locales once per session so t() works in all test modules.
# Individual i18n test modules override with their own marker locales and
# restore the originals on teardown.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _load_real_locales() -> None:
    """Load the real es.json/en.json locale files for the test session."""
    load_locales()


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

    No ``spec`` — avoids auto-creating AsyncMock children for every
    Database method, which would leak unawaited coroutines when tests
    only use a subset of methods.  Individual tests set the specific
    AsyncMock children they need.

    ``return_value`` is explicitly set on every child because
    ``AsyncMock()`` auto-creates its children as ``AsyncMock``, and
    ``AsyncMock().return_value`` is also an ``AsyncMock``.  When
    production code calls ``.get()`` on that implicit return value, it
    creates an unawaited ``AsyncMockMixin._execute_mock_call`` coroutine.
    """
    db = AsyncMock()
    db.get_guild = AsyncMock(return_value=None)
    db.upsert_guild = AsyncMock(return_value=None)
    # Methods accessed by production code via bot.db — must have explicit
    # return_value to avoid AsyncMock chain leaks.
    db.get_ticket_by_channel = AsyncMock(return_value=None)
    db.get_ticket_by_number = AsyncMock(return_value=None)
    db.get_ticket = AsyncMock(return_value=None)
    db.get_ticket_categories = AsyncMock(return_value=[])
    db.get_ticket_category = AsyncMock(return_value=None)
    db.get_max_ticket_number = AsyncMock(return_value=0)
    db.insert_ticket_category = AsyncMock(return_value=None)
    db.delete_ticket_category = AsyncMock(return_value=None)
    db.count_open_tickets_by_category = AsyncMock(return_value=0)
    db.update_ticket_category_field_definitions = AsyncMock(return_value=None)
    db.update_ticket_last_activity = AsyncMock(return_value=None)
    db.get_open_ticket_channel_ids = AsyncMock(return_value=[])
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
    """Return a MagicMock standing in for discord.Guild.

    No ``spec`` — avoids auto-creating AsyncMock children for async Guild
    methods (fetch_member, ban, etc.) that leak unawaited coroutines.
    """
    guild = MagicMock()
    guild.id = 123456789
    return guild


@pytest.fixture
def mock_member() -> MagicMock:
    """Return a MagicMock standing in for a discord.Member (no roles).

    No ``spec`` — avoids auto-creating AsyncMock children for unused async
    Member methods (ban, kick, timeout, etc.) whose coroutines leak on GC.
    ``__class__`` is overridden so ``isinstance(member, discord.Member)``
    still works.
    """
    member = MagicMock()
    member.__class__ = discord.Member
    member.guild_permissions.administrator = False
    member.roles = []
    return member


@pytest.fixture
def mock_admin_member() -> MagicMock:
    """Return a MagicMock standing in for a discord.Member with Administrator."""
    member = MagicMock()
    member.__class__ = discord.Member
    member.guild_permissions.administrator = True
    member.roles = []
    return member


@pytest.fixture
def mock_mod_member() -> MagicMock:
    """Return a MagicMock standing in for a Member with a moderator role."""
    role = MagicMock()
    role.__class__ = discord.Role
    role.id = 987654321

    member = MagicMock()
    member.__class__ = discord.Member
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


# ---------------------------------------------------------------------------
# frozen_clock — deterministic datetime.now() fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_clock():
    """Freeze ``datetime.now()`` to a deterministic value for the test duration.

    Uses ``freezegun.freeze_time`` to globally patch ``datetime.now`` so
    that BOTH test-side direct calls (``datetime.now(timezone.utc)``) AND
    service-side datetime access return the frozen value.  The clock is
    automatically restored when the fixture tears down.

    Usage::

        async def test_cooldown(frozen_clock):
            assert frozen_clock == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            # both test code and economy_service.gain_xp() see frozen time
    """
    with freeze_time(_FROZEN_NOW):
        yield _FROZEN_NOW
