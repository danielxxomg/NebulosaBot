"""Shared test fixtures for NebulosaBot unit tests.

Provides mocked Database, real TTLCache, sample GuildConfig, and Discord
mock objects that avoid hitting the real Discord API or Supabase.

Also provides ``frozen_clock`` -- a deterministic ``datetime.now()`` fixture
using ``freezegun`` to eliminate date-time flake risk under ``pytest-randomly``.

Also configures the ``live`` marker (S2.3): credential-gated live Supabase
read-only verifier behind ``--run-live`` / ``LIVE_SUPABASE=1``.
"""

from __future__ import annotations

import asyncio
import json
import os
import selectors
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from freezegun import freeze_time

from bot.core import i18n as i18n_mod
from bot.core.cache import TTLCache
from bot.core.i18n import load_locales, set_guild_language
from bot.models.guild import GuildConfig

# Frozen deterministic timestamp: 2024-06-15 12:00:00 UTC
_FROZEN_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Load real locales once per session so t() works in all test modules.
# Individual i18n test modules override with their own marker locales and
# restore the originals on teardown.
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run live Supabase read-only tests (also gated by LIVE_SUPABASE=1 or SUPABASE_URL)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_live = bool(config.getoption("--run-live")) or os.getenv("LIVE_SUPABASE") == "1"
    if run_live:
        return
    skip_live = pytest.mark.skip(
        reason="live Supabase not enabled -- pass --run-live with LIVE_SUPABASE=1 + SUPABASE_URL"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session", autouse=True)
def _load_real_locales() -> None:
    """Load the real es.json/en.json locale files for the test session."""
    load_locales()


@pytest.fixture(autouse=True)
def _isolate_i18n_state():
    """Snapshot and restore i18n module globals around every test.

    Several suites deliberately overwrite module-level i18n state
    (``_locales`` / ``_guild_languages``) with distinctive test locales.
    Under pytest-randomly those mutations leaked into unrelated modules,
    producing seed-dependent failures (core-help-builder resolving raw
    keys, xp-listener/confirm-view trios, etc.). Restoring after each
    test makes order irrelevant. Cost: two small dict copies per test.
    """
    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)
    yield
    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.update(orig_guild_langs)


# ---------------------------------------------------------------------------
# Shared locale helpers (tests-slim S1 — D1)
# ---------------------------------------------------------------------------
# Import-only from bot.core.i18n (conftest never imports cog/service code).
# _isolate_i18n_state remains outermost; hoisted fixtures yield and rely on it
# for restore, exactly as the per-file fixtures did before the hoist.


def build_nested_locale(markers: dict[str, str]) -> dict:
    """Convert flat dot-notation keys into a nested dict for locale JSON."""
    result: dict = {}
    for key, value in markers.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            nxt = current.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                current[part] = nxt
            current = nxt
        current[parts[-1]] = value
    return result


def swap_suffix(markers: dict[str, str], sfx: str) -> dict[str, str]:
    """Derive a sibling-locale marker set by swapping the ``_ES`` suffix."""
    return {key: value.replace("_ES", sfx) for key, value in markers.items()}


def load_test_locales(
    tmp_path: Path,
    es_markers: dict,
    en_markers: dict | None = None,
    *,
    guild_langs: dict[str, str] | None = None,
) -> None:
    """Write locale JSON files to tmp_path and load them via i18n.

    Args:
        tmp_path: pytest tmp_path fixture root.
        es_markers: Flat (dot-notation) or already-nested ES marker dict.
            Flat dicts are converted via build_nested_locale; nested dicts
            are written as-is (e.g. stellar's {"stellar": {"daily": ...}}).
        en_markers: Optional EN marker dict; when None and es_markers is
            flat, EN is derived via swap_suffix(es_markers, "_EN").
            When None and es_markers is nested, caller must have built EN
            separately — pass it explicitly.
        guild_langs: Optional guild_id(str)->language mapping to install
            after load (e.g. {"111...": "es", "222...": "en"}).
    """
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)

    def _needs_nesting(m: dict) -> bool:
        return any("." in k for k in m)

    # Detect flat vs already-nested by presence of dots in keys.
    es_is_flat = _needs_nesting(es_markers)
    if en_markers is None and es_is_flat:
        en_markers = swap_suffix(es_markers, "_EN")

    def _dump(markers: dict) -> dict:
        if any("." in k for k in markers):
            return build_nested_locale(markers)
        return markers

    (locale_dir / "es.json").write_text(json.dumps(_dump(es_markers)), encoding="utf-8")
    if en_markers is not None:
        (locale_dir / "en.json").write_text(json.dumps(_dump(en_markers)), encoding="utf-8")

    load_locales(locale_dir)
    if guild_langs:
        for gid, lang in guild_langs.items():
            set_guild_language(str(gid), lang)


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
# Discord mock factories — shared builders (cycle-5 S5b/c factory hoist).
# Import from tests.conftest: ``from tests.conftest import make_ctx`` etc.
# These replace the per-file _make_ctx/_make_member local variants.
# ---------------------------------------------------------------------------


def make_member(
    *,
    roles: list[MagicMock] | tuple[MagicMock, ...] = (),
    admin: bool = False,
    member_id: int = 111222333,
    display_name: str = "TestUser",
) -> MagicMock:
    """Return a mock discord.Member.

    No ``spec`` — avoids auto-created async children whose coroutines leak
    on GC (same rationale as the ``mock_member`` fixture). ``__class__`` is
    overridden so ``isinstance(member, discord.Member)`` still works.
    """
    member = MagicMock()
    member.__class__ = discord.Member
    member.id = member_id
    member.display_name = display_name
    member.mention = f"<@{member_id}>"
    member.guild_permissions.administrator = admin
    member.roles = list(roles)
    return member


def make_ctx(
    *,
    guild_id: int | None = 123456789,
    author: MagicMock | None = None,
    send: bool = True,
    spec: type | None = None,
) -> MagicMock:
    """Return a mock prefix-command context (NebulosaContext stand-in).

    ``guild_id=None`` simulates a DM context; ``spec=commands.Context``
    serves red-file needs for a spec'd mock; ``send=False`` omits the
    ``ctx.send`` AsyncMock for builders that never send.
    """
    ctx = MagicMock(spec=spec) if spec is not None else MagicMock()
    ctx.author = author if author is not None else make_member()
    if guild_id is not None:
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = guild_id
    else:
        ctx.guild = None
    if send:
        ctx.send = AsyncMock()
    return ctx


def make_interaction(
    *,
    guild_id: int | None = 123456789,
    user: MagicMock | None = None,
    client: MagicMock | None = None,
) -> MagicMock:
    """Return a mock discord.Interaction wired with guild/user/client."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id if guild_id is not None else 123456789
    interaction.user = user if user is not None else make_member()
    interaction.client = client if client is not None else MagicMock()
    interaction.guild_id = interaction.guild.id
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
