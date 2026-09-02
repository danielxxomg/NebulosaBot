"""Unit tests for bot.cogs.greetings — GreetingsCog.

Covers:
    - on_member_join calls greeting_service.dispatch_welcome
    - on_member_remove calls greeting_service.dispatch_goodbye
    - /welcome_test command (admin-only)
    - /goodbye_test command (admin-only)
    - /welcome config|channel|toggle|message (admin-only)
    - /goodbye config|channel|toggle|message (admin-only)
    - Non-admin users blocked from test/config commands

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.greetings import GreetingsCog
from bot.models.greeting_config import GreetingConfig
from bot.utils.checks import can

# Minimal valid PNG for mock card buffers — avoids fd corruption when
# discord.File opens the buffer (MagicMock.__index__() returns 1, which
# makes open() interpret it as fd 1 / stdout).
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_greeting_service() -> MagicMock:
    """Return a mock GreetingService with async dispatch and config methods."""
    svc = MagicMock()
    svc.dispatch_welcome = AsyncMock()
    svc.dispatch_goodbye = AsyncMock()
    svc.get_config = AsyncMock(return_value=GreetingConfig(guild_id="123456789"))
    svc.save_config = AsyncMock()
    return svc


@pytest.fixture
def mock_renderer() -> MagicMock:
    """Return a mock greeting renderer whose ``render`` yields a BytesIO PNG.

    Returns a real io.BytesIO so discord.File receives a seekable/readable
    buffer instead of MagicMock (whose __index__ returns 1, causing
    open(MagicMock, 'rb') to corrupt stdout fd 1).
    """
    renderer = MagicMock(spec=["render"])

    def _make_card(**_kwargs: object) -> io.BytesIO:
        return io.BytesIO(_MINIMAL_PNG)

    renderer.render = MagicMock(side_effect=_make_card)
    return renderer


@pytest.fixture
def mock_bot(mock_greeting_service: MagicMock, mock_renderer: MagicMock) -> MagicMock:
    """Return a mock NebulosaBot with greeting_service attached.

    The cog resolves the render callable via ``greeting_service.resolve_renderer()``
    (Phase 2: renderer-dispatch policy lives in the service, single copy). Wire
    the mock so the resolver returns the renderer's ``render`` — tests that
    assert on its ``call_args`` keep working, and error-side tests that set
    ``side_effect`` on it still propagate through the cog.
    """
    bot = MagicMock(spec=commands.Bot)
    bot.greeting_service = mock_greeting_service
    mock_greeting_service.resolve_renderer = MagicMock(return_value=mock_renderer.render)
    return bot


@pytest.fixture
def cog(mock_bot: MagicMock) -> GreetingsCog:
    """Return a fresh GreetingsCog with mocked bot."""
    return GreetingsCog(mock_bot)


def _make_member(
    member_id: int = 111111111,
    guild_id: int = 123456789,
    display_name: str = "TestUser",
) -> MagicMock:
    """Build a mock discord.Member for event testing."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.name = display_name
    member.display_name = display_name
    member.bot = False
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = guild_id
    member.avatar = MagicMock()
    member.avatar.url = "https://cdn.discordapp.com/avatars/111/abc.png"
    return member


def _make_context(
    user_id: int = 111111111,
    guild_id: int = 123456789,
    admin: bool = True,
) -> MagicMock:
    """Build a mock commands.Context for testing hybrid commands.

    Args:
        admin: If True, the user has administrator permission.
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = user_id
    ctx.author.display_name = "TestUser"
    ctx.author.guild_permissions.administrator = admin
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    ctx.guild.member_count = 150
    return ctx


# ---------------------------------------------------------------------------
# on_member_join
# ---------------------------------------------------------------------------


class TestOnMemberJoin:
    """Tests for GreetingsCog.on_member_join()."""

    @pytest.mark.asyncio
    async def test_calls_dispatch_welcome(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """on_member_join must delegate to greeting_service.dispatch_welcome."""
        member = _make_member()
        await cog.on_member_join(member)
        mock_bot.greeting_service.dispatch_welcome.assert_awaited_once_with(member)

    @pytest.mark.asyncio
    async def test_ignore_bot_members(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Bot members should not trigger welcome cards."""
        member = _make_member()
        member.bot = True
        await cog.on_member_join(member)
        mock_bot.greeting_service.dispatch_welcome.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_member_remove
# ---------------------------------------------------------------------------


class TestOnMemberRemove:
    """Tests for GreetingsCog.on_member_remove()."""

    @pytest.mark.asyncio
    async def test_calls_dispatch_goodbye(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """on_member_remove must delegate to greeting_service.dispatch_goodbye."""
        member = _make_member()
        await cog.on_member_remove(member)
        mock_bot.greeting_service.dispatch_goodbye.assert_awaited_once_with(member)

    @pytest.mark.asyncio
    async def test_ignore_bot_members(
        self,
        cog: GreetingsCog,
        mock_bot: MagicMock,
    ) -> None:
        """Bot members should not trigger goodbye cards."""
        member = _make_member()
        member.bot = True
        await cog.on_member_remove(member)
        mock_bot.greeting_service.dispatch_goodbye.assert_not_awaited()


# ---------------------------------------------------------------------------
# Legacy greeting commands — REMOVED in S2b.8 (welcome-goodbye spec)
# /welcome and /goodbye hybrid groups + welcome_test/goodbye_test deleted
# after parity verified via /setup modules. Guard ensures deletion sticks.
# ---------------------------------------------------------------------------


class TestLegacyWelcomeCommandsRemoved:
    def test_welcome_group_removed(self) -> None:
        from bot.cogs.greetings import GreetingsCog

        assert not hasattr(GreetingsCog, "welcome"), "welcome must be deleted (S2b.8)"
        assert not hasattr(GreetingsCog, "welcome_channel"), "welcome_channel must be deleted"
        assert not hasattr(GreetingsCog, "welcome_toggle"), "welcome_toggle must be deleted"
        assert not hasattr(GreetingsCog, "welcome_message"), "welcome_message must be deleted"
        assert not hasattr(GreetingsCog, "welcome_test"), "welcome_test must be deleted"

    def test_goodbye_group_removed(self) -> None:
        from bot.cogs.greetings import GreetingsCog

        assert not hasattr(GreetingsCog, "goodbye"), "goodbye must be deleted (S2b.8)"
        assert not hasattr(GreetingsCog, "goodbye_channel"), "goodbye_channel must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_toggle"), "goodbye_toggle must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_message"), "goodbye_message must be deleted"
        assert not hasattr(GreetingsCog, "goodbye_test"), "goodbye_test must be deleted"

    def test_no_hybrid_greeting_in_source(self) -> None:
        import pathlib as _pl  # noqa: PLC0415 -- facade indirection (pathlib alias scoped to this probe)

        src = _pl.Path("bot/cogs/greetings.py").read_text(encoding="utf-8")
        assert "hybrid_group" not in src, "greetings.py must not contain hybrid_group"
        assert "hybrid_command" not in src, "greetings.py must not contain hybrid_command"


# ---------------------------------------------------------------------------
# Guard twin (tests-slim-fase-2 B1) — replaces tests/test_pr4_greetings_red.py.
# D3 proof: GreetingsCog._admin_guard deny path (error_embed + ephemeral),
# admin pass, matrix grant, and can("greeting.manage") matrix semantics
# (modRoleId must NOT grant a non-moderation key).
# ---------------------------------------------------------------------------


def _make_guard_ctx(
    admin: bool,
    role_ids: tuple[int, ...],
    mod_role_id: str | None = None,
) -> MagicMock:
    """Build a mock prefix context for guard invocation."""
    member = MagicMock(spec=discord.Member)
    member.__class__ = discord.Member
    member.guild_permissions.administrator = admin
    member.id = 111
    roles = []
    for rid in role_ids:
        role = MagicMock(spec=discord.Role)
        role.id = rid
        roles.append(role)
    member.roles = roles

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = guild
    ctx.author = member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {123456789: mod_role_id} if mod_role_id else {}
    ctx.send = AsyncMock()
    return ctx


class TestAdminGuardDeny:
    """_admin_guard denies an ungranted member with False + ephemeral error embed."""

    @pytest.mark.asyncio
    async def test_guard_denies_ungranted_member_with_ephemeral_error(self) -> None:
        """Ungranted member → False + localized ephemeral error embed."""
        cog = GreetingsCog.__new__(GreetingsCog)  # guard touches no other state
        ctx = _make_guard_ctx(admin=False, role_ids=())

        cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await cog._admin_guard(ctx)

        assert result is False
        ctx.send.assert_awaited_once()
        assert ctx.send.call_args.kwargs.get("ephemeral") is True
        assert ctx.send.call_args.kwargs.get("embed") is not None


class TestAdminGuardPassScenarios:
    """_admin_guard allows admin and matrix-granted members (parametrized)."""

    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param("admin", id="admin-passes"),
            pytest.param("matrix", id="matrix-granted-passes"),
        ],
    )
    @pytest.mark.asyncio
    async def test_guard_allows_admin_and_matrix_grants(self, scenario: str) -> None:
        """Administrator and matrix-granted members pass the guard."""
        cog = GreetingsCog.__new__(GreetingsCog)
        if scenario == "admin":
            ctx = _make_guard_ctx(admin=True, role_ids=())
            cfg = MagicMock(permission_matrix={}, mod_role_id=None)
        else:
            ctx = _make_guard_ctx(admin=False, role_ids=(9002,))
            cfg = MagicMock(permission_matrix={"greeting.manage": ["9002"]}, mod_role_id=None)

        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await cog._admin_guard(ctx)

        assert result is True
        ctx.send.assert_not_awaited()


class TestGreetingManageMatrix:
    """can("greeting.manage") matrix semantics — no moderation fallback."""

    @pytest.mark.asyncio
    async def test_mod_role_does_not_grant_greeting_manage(self) -> None:
        """modRoleId must NOT grant greeting.manage (non-moderation, no fallback)."""
        guild_id = 123456789
        mod_role = 777
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        role = MagicMock(spec=discord.Role)
        role.id = mod_role
        member.roles = [role]
        member.id = 111

        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id

        ctx = MagicMock(spec=commands.Context)
        ctx.guild = guild
        ctx.author = member
        ctx.bot = MagicMock()
        ctx.bot._guild_mod_role_cache = {guild_id: str(mod_role)}

        cfg = MagicMock(permission_matrix={}, mod_role_id=str(mod_role))
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            result = await can("greeting.manage", ctx)
            assert result is False, "modRoleId must NOT grant greeting.manage"

    @pytest.mark.asyncio
    async def test_admin_and_matrix_grant_greeting_manage(self) -> None:
        """admin and matrix-granted role must pass greeting.manage."""
        guild_id = 123456789
        role_c = 9002
        guild = MagicMock(spec=discord.Guild)
        guild.id = guild_id

        # admin
        admin = MagicMock(spec=discord.Member)
        admin.__class__ = discord.Member
        admin.guild_permissions.administrator = True
        admin.roles = []
        admin.id = 111
        ctx_admin = MagicMock(spec=commands.Context)
        ctx_admin.guild = guild
        ctx_admin.author = admin
        ctx_admin.bot = MagicMock()
        ctx_admin.bot._guild_mod_role_cache = {}
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=MagicMock(permission_matrix={}, mod_role_id=None))
            assert await can("greeting.manage", ctx_admin) is True

        # matrix
        member = MagicMock(spec=discord.Member)
        member.__class__ = discord.Member
        member.guild_permissions.administrator = False
        granted = MagicMock(spec=discord.Role)
        granted.id = role_c
        member.roles = [granted]
        member.id = 222
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = guild
        ctx.author = member
        ctx.bot = MagicMock()
        ctx.bot._guild_mod_role_cache = {}
        cfg = MagicMock(permission_matrix={"greeting.manage": [str(role_c)]}, mod_role_id=None)
        with patch("bot.utils.checks._get_guild_service") as gs_mock:
            gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
            assert await can("greeting.manage", ctx) is True
