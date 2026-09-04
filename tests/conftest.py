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
import contextlib
import io
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
def _isolate_i18n_state() -> object:
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
def _asyncio_loop_factory() -> object:
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
    # Shim aliases for divergent call shapes (tests-slim S2 — D1):
    # ``guild_id`` sites attach a greeting-scoped guild; ``name`` aliases display_name.
    guild_id: int | None = None,
    name: str | None = None,
    # Greeting-scoped scaffolding — kept minimal; callers may override.
    # Channel scaffolding stays opt-in (with_channel) but defaults ON when
    # guild_id is supplied so legacy greeting sites remain one-liners.
    guild_name: str | None = None,
    member_count: int | None = None,
    avatar_url: str | None = None,
    guild_icon_url: str | None = None,
    with_channel: bool | None = None,
) -> MagicMock:
    """Return a mock discord.Member.

    No ``spec`` — avoids auto-created async children whose coroutines leak
    on GC (same rationale as the ``mock_member`` fixture). ``__class__`` is
    overridden so ``isinstance(member, discord.Member)`` still works.

    Shim: ``name`` aliases ``display_name`` (ticket/native-kwargs sites);
    ``guild_id`` attaches ``member.guild`` with minimal greeting scaffolding
    (guild.name/member_count/get_channel/icon + display_avatar) so guild_id
    call sites can use the canonical factory without a bespoke local def.
    Channel scaffolding is created when ``guild_id`` is given unless
    ``with_channel is False``.     ``guild_icon_url=None`` leaves ``guild.icon``
    as ``None``; a string installs a MagicMock icon with that url (native-kwargs).
    """
    if name is not None and display_name == "TestUser":
        # ``name`` provided without explicit display_name — use it.
        display_name = name
    member = MagicMock()
    member.__class__ = discord.Member
    member.id = member_id
    member.display_name = display_name
    if name is not None:
        member.name = name
    else:
        with contextlib.suppress(Exception):
            member.name = display_name
    member.mention = f"<@{member_id}>"
    member.guild_permissions.administrator = admin
    member.roles = list(roles)
    if guild_id is not None:
        guild = MagicMock()
        guild.id = guild_id
        guild.name = guild_name if guild_name is not None else "TestServer"
        guild.member_count = member_count if member_count is not None else 150
        if guild_icon_url is not None:
            icon = MagicMock()
            icon.url = guild_icon_url
            guild.icon = icon
        else:
            guild.icon = None
        do_channel = with_channel if with_channel is not None else True
        if do_channel:
            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.send = AsyncMock(return_value=None)
            guild.get_channel.return_value = mock_channel
        else:
            guild.get_channel.return_value = None
        member.guild = guild
        av = MagicMock()
        av.url = avatar_url if avatar_url is not None else f"https://cdn/{member_id}.png"
        member.display_avatar = av
        member.avatar = av
        with contextlib.suppress(Exception):
            if not hasattr(member, "bot") or isinstance(member.bot, MagicMock):
                member.bot = False
    else:
        if not hasattr(member, "display_avatar"):
            av = MagicMock()
            av.url = avatar_url if avatar_url is not None else f"https://cdn/{member_id}.png"
            member.display_avatar = av
            member.avatar = av
        if not hasattr(member, "bot"):
            with contextlib.suppress(Exception):
                member.bot = False
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
# Greeting/ticket setup-module builders (tests-slim-fase-3 Slice A — 1.3).
# Hoists the per-file ``_make_bot_with_greeting`` / ``_make_interaction`` /
# ``_make_bot`` twins into shared plain functions next to make_interaction.
# ``_isolate_i18n_state`` remains outermost and untouched.
# ---------------------------------------------------------------------------


def make_greeting_bot(
    kind: str,
    *,
    guild_id: str = "123456789",
    config: MagicMock | None = None,
    language: str = "es",
) -> MagicMock:
    """Return a mock bot wired with GreetingService for setup-module tests.

    ``kind`` selects the default config shape: ``welcome`` seeds the welcome
    fields enabled, ``goodbye`` seeds the goodbye fields enabled, and any
    other value seeds an all-neutral config. ``config`` overrides the default
    config entirely (its ``guild_id`` is re-asserted onto ``cfg.guild_id``).
    """
    bot = MagicMock()
    bot.greeting_service = MagicMock()
    if kind == "welcome":
        cfg = config or MagicMock(
            guild_id=guild_id,
            welcome_channel_id="111222333",
            welcome_enabled=True,
            welcome_message="Welcome {mention}",
            welcome_card_enabled=True,
            theme_id=None,
            goodbye_channel_id=None,
            goodbye_enabled=False,
            goodbye_message=None,
            goodbye_card_enabled=False,
            onboarding_channel_id=None,
            card_enabled=True,
            updated_at=None,
        )
    elif kind == "goodbye":
        cfg = config or MagicMock(
            guild_id=guild_id,
            welcome_channel_id=None,
            welcome_enabled=False,
            welcome_message=None,
            welcome_card_enabled=False,
            theme_id=None,
            goodbye_channel_id="222333444",
            goodbye_enabled=True,
            goodbye_message="Bye {mention}",
            goodbye_card_enabled=True,
            onboarding_channel_id=None,
        )
    else:
        cfg = config or MagicMock(
            guild_id=guild_id,
            welcome_channel_id=None,
            welcome_enabled=False,
            welcome_message=None,
            welcome_card_enabled=False,
            theme_id=None,
            goodbye_channel_id=None,
            goodbye_enabled=False,
            goodbye_message=None,
            goodbye_card_enabled=False,
            onboarding_channel_id=None,
        )
    cfg.guild_id = guild_id
    bot.greeting_service.get_config = AsyncMock(return_value=cfg)
    bot.greeting_service.save_config = AsyncMock(return_value=None)
    bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"fake-card"))
    bot.greeting_service.dispatch_greeting = AsyncMock()
    # For dispatch_welcome preview path we also mock GreetingService internals indirectly via real render path
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language=language))
    return bot


def make_greeting_interaction(
    *,
    guild_id: int = 123456789,
    user_id: int = 111,
    client: MagicMock | None = None,
    custom_id: str = "setup:welcome:test",
    display_name: str = "Tester",
    avatar_url: str = "https://cdn.example/ava.png",
) -> MagicMock:
    """Return a setup-panel interaction mock with greeting scaffolding.

    Mirrors the per-file ``_make_interaction`` twins: spec'd Interaction with
    guild (get_channel → TextChannel AsyncMock send), user (administrator),
    full response/followup/message AsyncMocks, and ``data`` custom_id.
    ``client`` defaults to ``make_greeting_bot("welcome")`` for the given
    guild (matching the legacy welcome-file default).
    """
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = guild_id
    inter.guild_id = guild_id
    inter.guild.name = "TestGuild"
    # guild.get_channel for preview delivery
    chan = MagicMock(spec=discord.TextChannel)
    chan.send = AsyncMock()
    inter.guild.get_channel = MagicMock(return_value=chan)
    inter.guild.member_count = 42
    inter.guild.icon = None
    inter.user = MagicMock(spec=discord.Member)
    inter.user.id = user_id
    inter.user.display_name = display_name
    inter.user.display_avatar = MagicMock()
    inter.user.display_avatar.url = avatar_url
    inter.user.guild_permissions.administrator = True
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()
    inter.response.send_modal = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.response.edit_message = AsyncMock()
    inter.response.is_done.return_value = False
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    inter.message = MagicMock()
    inter.message.edit = AsyncMock()
    inter.client = client or make_greeting_bot("welcome", guild_id=str(guild_id))
    inter.data = {"custom_id": custom_id}
    return inter


def make_ticket_bot(guild_id: str = "123456789") -> MagicMock:
    """Return a mock bot wired with ticket-category DB mocks (setup-module tickets tests).

    Mirrors the per-file ``_make_bot`` twin: db insert/get/delete/update/count
    AsyncMocks pre-seeded with two categories, plus guild_service language es.
    """
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.insert_ticket_category = AsyncMock(return_value={"id": "new-uuid", "name": "Support", "guildId": guild_id})
    bot.db.get_ticket_categories = AsyncMock(
        return_value=[
            {
                "id": "cat-1",
                "name": "Support",
                "guildId": guild_id,
                "position": 0,
                "active": True,
                "emoji": None,
                "description": None,
            },
            {
                "id": "cat-2",
                "name": "Reports",
                "guildId": guild_id,
                "position": 1,
                "active": True,
                "emoji": None,
                "description": None,
            },
        ]
    )
    bot.db.get_ticket_category = AsyncMock(return_value={"id": "cat-1", "name": "Support", "guildId": guild_id})
    bot.db.delete_ticket_category = AsyncMock(return_value=None)
    bot.db.update_ticket_category_field_definitions = AsyncMock(return_value=None)
    bot.db.count_open_tickets_by_category = AsyncMock(return_value=0)
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
    return bot


# ---------------------------------------------------------------------------
# PR2 ticket timer builders (tests-slim-fase-3 Slice B — 2.1).
# Hoists _make_bot / _make_message from test_pr2_on_message_red into shared
# plain functions beside make_ticket_bot. Plain builders, not fixtures.
# ---------------------------------------------------------------------------


def make_pr2_bot() -> MagicMock:
    """Return a mock bot wired for TicketsCog on_message / timer tests.

    Mirrors ``tests/test_pr2_on_message_red.py:_make_bot`` verbatim so that
    hoisted call sites can switch to the shared builder without behavior change.
    """
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.update_ticket_last_activity = AsyncMock()
    bot.db.get_ticket_by_channel = AsyncMock(return_value=None)
    bot.db.get_active_ticket_by_channel = AsyncMock(return_value=None)
    bot.db.update_ticket = AsyncMock()
    bot.db.get_scheduled_close_candidates = AsyncMock(return_value=[])
    bot.db.get_ticket = AsyncMock(return_value=None)
    bot.ticket_service = MagicMock()
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=True)
    bot.ticket_service.schedule_close = AsyncMock()
    bot.ticket_service.cancel_scheduled_close = AsyncMock()
    bot.ticket_service.close_ticket_full = AsyncMock()
    bot.ticket_service.handle_timer_message = AsyncMock(return_value=None)
    bot.ticket_service.confirm_timer_schedule = AsyncMock(return_value=None)
    bot.ticket_service.get_due_scheduled_tickets = AsyncMock(return_value=[])
    bot.ticket_service.upsert_timer_embed = AsyncMock()
    bot.guilds = []
    bot._guild_mod_role_cache = {}
    bot.get_channel = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    return bot


def make_pr2_message(
    content: str,
    guild_id: int = 123,
    channel_id: int = 444,
    is_mod: bool = True,
    status: str = "open",  # kept for call-site compatibility; not used by builder
) -> MagicMock:
    """Return a mock discord.Message for PR2 timer tests.

    Mirrors ``tests/test_pr2_on_message_red.py:_make_message`` verbatim.
    ``status`` is accepted for compatibility with legacy call sites but does
    not affect the mock shape.
    """
    _ = status
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    msg.author = MagicMock(spec=discord.Member)
    msg.author.bot = False
    msg.author.id = 999
    msg.author.guild_permissions.administrator = is_mod
    msg.author.roles = []
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = guild_id
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.send.return_value = AsyncMock(pin=AsyncMock(), edit=AsyncMock())
    msg.channel.pins = AsyncMock(return_value=[])
    return msg


def make_pr2_manager_message(
    *,
    role_id: int | None = None,
    administrator: bool = False,
    guild_id: int = 123,
    channel_id: int = 444,
    content: str = ",12h",
) -> MagicMock:
    """Return a Message whose author is a non-admin, non-modRole member.

    Mirrors ``tests/test_pr2_on_message_red.py:_make_ticket_manager_message``.
    When ``role_id`` is given the author carries that role — used to simulate
    a matrix-granted ticket manager (``permissionMatrix["tickets.manage"]``).
    """
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    author = MagicMock(spec=discord.Member)
    author.bot = False
    author.id = 999
    author.guild_permissions.administrator = administrator
    roles: list[MagicMock] = []
    if role_id is not None:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        roles.append(role)
    author.roles = roles
    msg.author = author
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = guild_id
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.send.return_value = AsyncMock(pin=AsyncMock(), edit=AsyncMock())
    msg.channel.pins = AsyncMock(return_value=[])
    return msg


# ---------------------------------------------------------------------------
# Live/S5 scoped-SQL helpers (tests-slim-fase-3 Slice B — 2.2).
# Shared fake-psycopg scaffolding for live_catalog + production_live_close_s5.
# ---------------------------------------------------------------------------


def fake_db_with_token(  # noqa: PLR0913 -- helper mirrors 4-query provenance shape
    db_url: str = "postgresql://" + "user:pass@localhost" + "/db",
    *,
    fk_rows: list[tuple[str, str, str]] | None = None,
    rls_enabled: int = 9,
    rls_forced: int = 7,
    policy_count: int = 0,
) -> tuple[MagicMock, list[str]]:
    """Return a ``(fake_connect, executed)`` pair for psycopg provenance tests.

    ``fake_connect`` is a ``MagicMock`` whose ``return_value`` is a context-manager
    connection whose cursor records every ``execute(sql)`` into ``executed`` and
    returns canned rows for the 4 provenance queries. Use via::

        fake_connect, executed = fake_db_with_token()
        with patch("psycopg.connect", fake_connect):
            fks, pols, pubs, migs, tok = await fetch_catalog_via_db(db_url)

    The canned FK row defaults to one ``("ticket","guild","CASCADE")`` entry so
    that ``pg_constraint`` provenance is satisfied without a real DB.
    """
    _ = db_url  # URL is not inspected by the fake; caller passes it to the code under test.
    executed: list[str] = []
    _fk_rows = fk_rows if fk_rows is not None else [("ticket", "guild", "CASCADE")]

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, sql: str, *_: object, **__: object) -> None:
            executed.append(sql)

        def fetchall(self) -> list[tuple[str, ...]]:
            if executed and "pg_constraint" in executed[-1]:
                return list(_fk_rows)
            return []

        def fetchone(self) -> tuple[int, ...] | None:
            # Used by fetch_rls_counts_via_db and _sync_fetch_catalog;
            # callers that need specific counts override via side_effect, so
            # this generic return is only for catalog FK path.
            return (0,)

    class FakeConn:
        def __enter__(self) -> FakeConn:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    fake_connect = MagicMock(return_value=FakeConn())
    # Attach a helper for RLS-count callers that need fetchone sequencing.
    # The default fake above returns 0; tests that assert 9/7/0 override
    # fetchone via a dedicated MagicMock — this helper does not interfere.
    _ = (rls_enabled, rls_forced, policy_count)
    return fake_connect, executed


def mocked_fks_for_live() -> list[dict[str, str]]:
    """Return the canonical 6-FK list used by live_catalog parity tests."""
    return [
        {"child": "economy_config", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "greeting_config", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "infraction", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "member", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "ticket", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "ticket_category", "parent": "guild", "on_delete": "CASCADE"},
    ]


# ---------------------------------------------------------------------------
# frozen_clock — deterministic datetime.now() fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_clock() -> object:
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
